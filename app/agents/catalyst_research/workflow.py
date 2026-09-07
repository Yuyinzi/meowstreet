import inspect
import re
import sqlite3
from collections.abc import Mapping
from datetime import UTC, datetime
from urllib.parse import urljoin

from app.agents.catalyst_research import domain, statistics
from app.agents.catalyst_research.adapters import executor as adapter_executor
from app.agents.catalyst_research.adapters import generator as adapter_generator
from app.agents.catalyst_research.adapters import validator as adapter_validator
from app.agents.catalyst_research.config import load_inference_bundle, load_search_config
from app.agents.catalyst_research.extraction import build_structural_snapshot, fetch_html_page
from app.agents.catalyst_research.persistence import repository as default_repository
from app.agents.catalyst_research.providers.ddgs import DDGSSearchProvider
from app.agents.catalyst_research.providers.native_search import NativeSearchProvider
from app.agents.catalyst_research.providers.router import SearchRouter
from app.agents.catalyst_research.providers.tavily import TavilySearchProvider
from app.data_sources import sec_edgar
from app.db import edgar_filings as edgar_db
from app.http_client import HttpClient
from app.runtime_logging import get_runtime_logger


LOGGER = get_runtime_logger(__name__)
_REQUIRED_CHANNELS = ("press_releases", "events_presentations")
_DISCOVERY_CHANNELS = ("ir_home", "press_releases", "events_presentations", "earnings_results")
_MAX_TRAVERSAL_ORIGINS = 2
_MAX_TRAVERSAL_TARGETS = 4
_TRAVERSAL_PURPOSE_TERMS = {
    "press_releases": ("press", "release", "news"),
    "events_presentations": ("event", "presentation", "webcast", "conference"),
}
_UNSUPPORTED_FETCH_TERMS = ("content type", "non-html", "non html", "javascript", "requires js", "requires javascript")


async def _invoke(function, *args, **kwargs):
    if function is None:
        raise ValueError("workflow stage is unavailable")
    try:
        signature = inspect.signature(function)
    except (TypeError, ValueError):
        signature = None
    if signature is not None and not any(parameter.kind == parameter.VAR_KEYWORD for parameter in signature.parameters.values()):
        kwargs = {key: value for key, value in kwargs.items() if key in signature.parameters}
    result = function(*args, **kwargs)
    if inspect.isawaitable(result):
        return await result
    return result


def _now(context):
    clock = context["clock"]
    value = clock() if callable(clock) else clock
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    return datetime.now(UTC)


def _iso(context):
    return _now(context).isoformat()


def _repo_call(context, name, *args, **kwargs):
    method = getattr(context["repository"], name)
    try:
        parameters = inspect.signature(method).parameters
    except (TypeError, ValueError):
        parameters = {}
    first = next(iter(parameters), None)
    connection = context["connection"]
    if first in {"con", "connection"}:
        return method(connection, *args, **kwargs)
    return method(*args, **kwargs)


def _connect_repository(repository, db_path):
    method = getattr(repository, "connect")
    try:
        parameters = inspect.signature(method).parameters
    except (TypeError, ValueError):
        parameters = {"db_path": object()}
    positional = [parameter for parameter in parameters.values() if parameter.kind in {inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD}]
    return method(db_path) if positional else method()


def _sanitized_error(error):
    message = " ".join(str(error).split())
    message = re.sub(r"(?i)\bauthorization\s*[:=]\s*(\S+)(?:\s+\S+)?", r"Authorization: \1 [redacted]", message)
    message = re.sub(r"(?i)\b(?:cookie|set-cookie)\s*[:=]\s*\S+", "Cookie: [redacted]", message)
    message = re.sub(r"(?i)\bbearer\s+\S+", "Bearer [redacted]", message)
    message = re.sub(r"(?i)(api[ _-]?key|token|client[ _-]?secret|password)\s*[:=]\s*\S+", r"\1=[redacted]", message)
    return message[:500] or "workflow failed"


def _source_model(context, name):
    models = context.get("models") or {}
    if isinstance(models, str):
        return models
    if not isinstance(models, Mapping):
        return None
    return models.get(name) or models.get(f"{name}_model")


def _source_text(snapshot):
    normalized = snapshot.get("normalized") if isinstance(snapshot, Mapping) else None
    values = []
    if isinstance(snapshot, Mapping):
        values.extend(snapshot.get(key) for key in ("title", "text", "description"))
    if isinstance(normalized, Mapping):
        values.extend(normalized.get(key) for key in ("title", "text"))
        values.extend(item.get("text") for item in normalized.get("headings", []) if isinstance(item, Mapping))
    return " ".join(str(value or "") for value in values).casefold()


def _identity_tokens(company):
    name = str(company.get("company_name") or company.get("name") or "").casefold()
    ticker = str(company.get("ticker") or "").casefold()
    return {token for token in (name.replace(".", " ").split() + [ticker]) if len(token) >= 3 and token not in {"and", "inc", "corp", "corporation", "company"}}


def _source_verified(company, source_type, source, snapshot):
    if not isinstance(snapshot, Mapping):
        return False, "source snapshot is invalid"
    requested = source.get("url") or source.get("source_url")
    final_url = snapshot.get("final_url") or requested
    try:
        requested_host = domain.url_host(domain.canonicalize_public_url(requested))
        final_host = domain.url_host(domain.canonicalize_public_url(final_url))
    except ValueError:
        return False, "source final url is unsafe"
    if requested_host != final_host:
        return False, "source final url host is inconsistent"
    text = _source_text(snapshot)
    if not any(token in text for token in _identity_tokens(company)):
        return False, "company identity is ambiguous"
    purpose = {
        "ir_home": ("investor relations", "investor", "shareholder"),
        "press_releases": ("press release", "news release", "press", "news"),
        "events_presentations": ("events", "presentations", "webcast", "conference"),
        "earnings_results": ("earnings", "financial results", "quarterly results"),
    }.get(source_type, ())
    if not any(term in text for term in purpose):
        return False, "IR archive purpose is ambiguous"
    return True, None


def _unsupported_fetch_error(error):
    text = str(error).casefold()
    return any(term in text for term in _UNSUPPORTED_FETCH_TERMS)


def _unsupported_warning_code(error):
    return "javascript_archive_unsupported" if "javascript archive" in str(error).casefold() else "source_javascript_unsupported"


def _javascript_archive_shell(page, snapshot):
    if not isinstance(page, Mapping) or not isinstance(snapshot, Mapping):
        return False
    html = page.get("html")
    normalized = snapshot.get("normalized") or {}
    if not isinstance(html, str) or not isinstance(normalized, Mapping):
        return False
    script_count = len(re.findall(r"<script\b", html, flags=re.IGNORECASE))
    text = str(normalized.get("text") or "").strip()
    visible_text = re.sub(r"<script\b.*?</script>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    visible_text = re.sub(r"<[^>]+>", " ", visible_text)
    visible_text = " ".join(visible_text.casefold().split())
    links = normalized.get("links")
    structural = str(snapshot.get("structural_html") or "")
    date_evidence = re.search(r"\b(?:19|20)\d{2}\b|data-date=|datetime=", visible_text + structural, flags=re.IGNORECASE)
    app_root = re.search(r"<(?:div|main|section)[^>]*(?:id|class)=[\"'][^\"']*(?:__next|root|app)[^\"']*[\"']", html, flags=re.IGNORECASE)
    archive_terms = ("press", "release", "news", "event", "presentation", "investor", "archive")
    zero_terms = ("no press", "no event", "no presentation", "no result", "no announcement", "no upcoming", "no item", "no content", "none available", "nothing found", "no archive", "no record")
    meaningful_archive_text = any(term in visible_text for term in archive_terms + zero_terms)
    script_bundle = script_count >= 4 or bool(re.search(r"<script\b[^>]+\bsrc=", html, flags=re.IGNORECASE))
    return bool(app_root and script_bundle and not meaningful_archive_text and not links and date_evidence is None)


def _candidate_links(snapshot, origin_url, target_type):
    normalized = snapshot.get("normalized") if isinstance(snapshot, Mapping) else None
    links = normalized.get("links", []) if isinstance(normalized, Mapping) else snapshot.get("links", [])
    if not links and isinstance(snapshot, Mapping):
        links = snapshot.get("links", [])
    if not isinstance(links, list):
        return []
    try:
        origin_host = domain.url_host(domain.canonicalize_public_url(origin_url))
    except ValueError:
        return []
    terms = _TRAVERSAL_PURPOSE_TERMS[target_type]
    output = []
    seen = set()
    for link in links:
        if not isinstance(link, Mapping):
            continue
        href = link.get("href") or link.get("url")
        if not isinstance(href, str) or not href.strip():
            continue
        text = " ".join(str(link.get(key) or "") for key in ("text", "title", "aria-label", "href")).casefold()
        if not any(term in text for term in terms):
            continue
        try:
            target = domain.canonicalize_public_url(urljoin(origin_url, href))
            if domain.url_host(target) != origin_host:
                continue
        except ValueError:
            continue
        if target in seen:
            continue
        seen.add(target)
        output.append(target)
        if len(output) >= _MAX_TRAVERSAL_TARGETS:
            break
    return output


def _default_resolver(request, *, connection=None, http_client=None, db_path=None):
    ticker = request["ticker"]
    con = edgar_db.connect(db_path or default_repository.DEFAULT_DB_PATH)
    try:
        row = edgar_db.load_cik(con, ticker)
        if row is None or row.get("cik") == edgar_db.UNMAPPED_CIK:
            mapping = sec_edgar.fetch_cik_map(http_client=http_client)
            entry = mapping.get(ticker)
            if entry is None:
                edgar_db.save_cik_miss(con, ticker)
                raise ValueError("company resolution failed")
            edgar_db.save_cik(con, ticker, entry["cik"], entry.get("title"))
            return {"ticker": ticker, "company_name": entry.get("title"), "cik": entry["cik"]}
        return {"ticker": ticker, "company_name": row.get("title"), "cik": row.get("cik")}
    finally:
        con.close()


def _default_search_router(inference):
    config = load_search_config()
    providers = []
    try:
        providers.append(TavilySearchProvider(config.get("tavily_api_key")))
    except Exception:
        pass
    try:
        client = inference.get("client")
        model = (inference.get("models") or {}).get("source_selection_model")
        if client and model:
            providers.append(NativeSearchProvider(client, model, base_url=(inference.get("config") or {}).get("base_url"), native_search_supported=config.get("native_search_supported", "auto")))
    except Exception:
        pass
    try:
        providers.append(DDGSSearchProvider())
    except Exception:
        pass
    return SearchRouter(config, providers)


class _UnavailableSearchRouter:
    def provider_chain(self):
        return []

    def provider_order(self):
        return []

    def unavailable(self):
        return ["search"]


def _default_inference():
    try:
        return load_inference_bundle()
    except Exception:
        return {"client": None, "models": {}, "warnings": ["catalyst_llm_configuration_failed"]}


def _default_dependencies(db_path, http_client):
    inference = _default_inference()
    try:
        search_router = _default_search_router(inference)
    except Exception:
        search_router = _UnavailableSearchRouter()
    return {
        "clock": lambda: datetime.now(UTC),
        "resolver": _default_resolver,
        "search_router": search_router,
        "llm_client": inference.get("client"),
        "models": inference.get("models", {}),
        "inference_warnings": inference.get("warnings", []),
        "fetch_page": lambda url, **kwargs: fetch_html_page(url, http_client=http_client, **kwargs),
        "repository": default_repository,
        "discover_sources": domain.discover_sources,
        "build_snapshot": build_structural_snapshot,
        "generate_adapter": adapter_generator.generate_adapter,
        "validate_candidate": adapter_validator.validate_candidate,
        "execute_adapter": adapter_executor.execute_adapter,
        "classify_observations": domain.classify_observations,
        "normalize_observations": domain.normalize_observations,
        "calculate_statistics": statistics.calculate_statistics,
    }


def _record_snapshot(context, source, page):
    snapshot = _invoke_sync(context["build_snapshot"], page, source=source)
    if not isinstance(snapshot, Mapping):
        raise ValueError("source snapshot is invalid")
    snapshot = dict(snapshot)
    if _javascript_archive_shell(page, snapshot):
        raise ValueError("javascript archive unsupported")
    if snapshot.get("requires_javascript") or snapshot.get("javascript_required") or snapshot.get("unsupported_access_mode") or snapshot.get("access_mode") in {"javascript", "rendered", "unsupported"}:
        raise ValueError("source requires javascript")
    snapshot.setdefault("requested_url", page.get("requested_url") or source["url"])
    snapshot.setdefault("final_url", page.get("final_url") or source["url"])
    snapshot["source_type"] = source["source_type"]
    content_hash = _repo_call(context, "save_snapshot", snapshot)
    snapshot["content_hash"] = content_hash
    return snapshot


def _invoke_sync(function, *args, **kwargs):
    if function is None:
        raise ValueError("workflow stage is unavailable")
    try:
        signature = inspect.signature(function)
    except (TypeError, ValueError):
        signature = None
    if signature is not None and not any(parameter.kind == parameter.VAR_KEYWORD for parameter in signature.parameters.values()):
        kwargs = {key: value for key, value in kwargs.items() if key in signature.parameters}
    return function(*args, **kwargs)


async def _fetch_snapshot(context, company, source, *, allowed_hosts=None):
    fetch_kwargs = {"allowed_hosts": allowed_hosts}
    if context.get("url_resolver") is not None:
        fetch_kwargs["resolver"] = context["url_resolver"]
    page = await _invoke(context["fetch_page"], source["url"], **fetch_kwargs)
    snapshot = await _invoke(context["build_snapshot"], page, source=source)
    if not isinstance(snapshot, Mapping):
        raise ValueError("source snapshot is invalid")
    snapshot = dict(snapshot)
    if _javascript_archive_shell(page, snapshot):
        raise ValueError("javascript archive unsupported")
    if snapshot.get("requires_javascript") or snapshot.get("javascript_required") or snapshot.get("unsupported_access_mode") or snapshot.get("access_mode") in {"javascript", "rendered", "unsupported"}:
        raise ValueError("source requires javascript")
    snapshot.setdefault("requested_url", page.get("requested_url") or source["url"])
    snapshot.setdefault("final_url", page.get("final_url") or source["url"])
    snapshot["source_type"] = source["source_type"]
    snapshot["company_verified"], snapshot["verification_error"] = _source_verified(company, source["source_type"], source, snapshot)
    snapshot["content_hash"] = _repo_call(context, "save_snapshot", snapshot)
    return snapshot


def _save_unaccepted_source(context, source, *, status, snapshot=None, extraction_status="failed", verification_reason=None):
    row = dict(source)
    row.update({"ticker": context["request"]["ticker"], "job_id": context["job"]["job_id"], "acceptance_status": status, "extraction_status": extraction_status, "verification_reason": verification_reason, "execution_path": "cold", "checked_at": _iso(context)})
    if isinstance(snapshot, Mapping):
        row.update({"final_url": snapshot.get("final_url"), "snapshot_hash": snapshot.get("content_hash"), "content_hash": snapshot.get("content_hash")})
    _repo_call(context, "save_source", row)


async def _traverse_source(context, company, origin_snapshots, source_type):
    attempts = 0
    seen = set()
    for origin in origin_snapshots[:_MAX_TRAVERSAL_ORIGINS]:
        origin_url = origin["snapshot"].get("final_url") or origin["source"]["url"]
        try:
            origin_host = domain.url_host(domain.canonicalize_public_url(origin_url))
        except ValueError:
            continue
        for target_url in _candidate_links(origin["snapshot"], origin_url, source_type):
            if target_url in seen or attempts >= _MAX_TRAVERSAL_TARGETS:
                continue
            seen.add(target_url)
            attempts += 1
            candidate = {"source_type": source_type, "url": target_url, "discovery_provider": "same_site_traversal", "evidence_result_ids": []}
            try:
                snapshot = await _fetch_snapshot(context, company, candidate, allowed_hosts=[origin_host])
            except ValueError:
                continue
            if not snapshot.get("company_verified"):
                continue
            try:
                if domain.url_host(domain.canonicalize_public_url(snapshot.get("final_url") or target_url)) != origin_host:
                    continue
            except ValueError:
                continue
            return candidate, snapshot
    return None, None


async def _resolve(context):
    resolver = context["resolver"]
    if not callable(resolver) and callable(getattr(resolver, "resolve", None)):
        resolver = resolver.resolve
    try:
        first_parameter = next(iter(inspect.signature(resolver).parameters.values()))
    except (StopIteration, TypeError, ValueError):
        first_parameter = None
    target = context["request"]["ticker"] if first_parameter and first_parameter.name in {"ticker", "symbol"} else context["request"]
    company = await _invoke(resolver, target, connection=context["connection"], http_client=context["http_client"], db_path=context["db_path"])
    if not isinstance(company, Mapping) or not company.get("company_name") and not company.get("name"):
        raise ValueError("company resolution failed")
    result = dict(company)
    result["ticker"] = context["request"]["ticker"]
    return result


async def _discover(context, company):
    context["call_counts"]["discovery"] += 1
    result = await _invoke(
        context["discover_sources"], company,
        router=context["search_router"],
        llm_client=context["llm_client"],
        model=_source_model(context, "source_selection"),
        repository=context["repository"],
        job_id=context["job"]["job_id"],
        connection=context["connection"],
        overrides=context["request"].get("source_overrides"),
    )
    if not isinstance(result, Mapping):
        raise ValueError("source discovery result is invalid")
    context["warnings"].extend(result.get("warnings", []))
    context["next_actions"].extend(result.get("next_actions", []))
    if result.get("status") == "search_unavailable":
        context["warnings"].append("catalyst_no_search_provider")
        context["next_actions"].append("configure_catalyst_search_provider")
    elif result.get("status") == "ambiguous":
        context["warnings"].append("source_identity_ambiguous")
        context["next_actions"].append("review_ambiguous_source")
    return result


async def _prepare_sources(context, company, discovery):
    raw_sources = list(discovery.get("sources", []))
    raw_sources.extend(discovery.get("alternate_sources", []))
    candidates = {}
    for source in raw_sources:
        if not isinstance(source, Mapping) or source.get("source_type") not in _DISCOVERY_CHANNELS or not source.get("url"):
            continue
        candidates.setdefault(source["source_type"], []).append(dict(source))
    origin_snapshots = []
    for source in candidates.get("ir_home", [])[:_MAX_TRAVERSAL_ORIGINS]:
        try:
            snapshot = await _fetch_snapshot(context, company, source)
        except ValueError as exc:
            if _unsupported_fetch_error(exc):
                context["warnings"].append(_unsupported_warning_code(exc))
                context["next_actions"].append("provide_extractable_archive_url")
                _save_unaccepted_source(context, source, status="pending", extraction_status="unsupported")
            else:
                context["warnings"].append("IR homepage fetch failed")
                _save_unaccepted_source(context, source, status="rejected")
            continue
        if snapshot.get("company_verified"):
            origin_snapshots.append({"source": source, "snapshot": snapshot})
            origin = dict(source)
            origin.update({"ticker": context["request"]["ticker"], "job_id": context["job"]["job_id"], "acceptance_status": "accepted", "extraction_status": "pending", "final_url": snapshot.get("final_url"), "snapshot_hash": snapshot.get("content_hash"), "content_hash": snapshot.get("content_hash"), "execution_path": "cold", "checked_at": _iso(context)})
            _repo_call(context, "save_source", origin)
        else:
            context["warnings"].append("source_identity_ambiguous")
            context["next_actions"].append("review_ambiguous_source")
            _save_unaccepted_source(context, source, status="ambiguous", snapshot=snapshot, verification_reason=snapshot.get("verification_error"))
    prepared = {}
    for source_type in _REQUIRED_CHANNELS:
        accepted = None
        for source in candidates.get(source_type, []):
            if source.get("status") == "rejected" or source.get("acceptance_status") == "rejected":
                continue
            try:
                snapshot = await _fetch_snapshot(context, company, source)
            except ValueError as exc:
                if _unsupported_fetch_error(exc):
                    context["warnings"].append(_unsupported_warning_code(exc))
                    context["next_actions"].append("provide_extractable_archive_url")
                    _save_unaccepted_source(context, source, status="pending", extraction_status="unsupported")
                else:
                    _save_unaccepted_source(context, source, status="rejected")
                continue
            if snapshot.get("company_verified"):
                accepted = (source, snapshot)
                break
            context["warnings"].append("source_identity_ambiguous")
            context["next_actions"].append("review_ambiguous_source")
            _save_unaccepted_source(context, source, status="ambiguous", snapshot=snapshot, verification_reason=snapshot.get("verification_error"))
        if accepted is None:
            accepted = await _traverse_source(context, company, origin_snapshots, source_type)
        prepared[source_type] = accepted
    return prepared, origin_snapshots


async def _run_channel(context, company, source_type, pair):
    if pair is None or pair[0] is None:
        return {"source_type": source_type, "status": "missing", "events": [], "source": None}
    source, snapshot = pair
    source = dict(source)
    source.update({"ticker": context["request"]["ticker"], "job_id": context["job"]["job_id"], "acceptance_status": "accepted", "requested_start": context["job"]["requested_start"], "requested_end": context["job"]["requested_end"], "final_url": snapshot.get("final_url"), "snapshot_hash": snapshot.get("content_hash"), "content_hash": snapshot.get("content_hash")})
    trusted_final_url = domain.canonicalize_public_url(source["final_url"] or source["url"])
    trusted_allowed_hosts = [domain.url_host(trusted_final_url)]
    source["final_url"] = trusted_final_url
    source["allowed_hosts"] = list(trusted_allowed_hosts)
    model = _source_model(context, "adapter_generation")
    if not context["llm_client"] or not model:
        context["warnings"].append("catalyst_llm_unavailable")
        context["next_actions"].append("configure_catalyst_llm")
        context["execution_paths"][source_type] = "cold"
        source.update({"extraction_status": "unsupported", "execution_path": "cold", "checked_at": _iso(context)})
        saved = _repo_call(context, "save_source", source)
        return {"source_type": source_type, "status": "partial", "events": [], "source": saved}
    context["call_counts"]["adapter_generation"] += 1
    try:
        candidate = await _invoke(context["generate_adapter"], company, source, snapshot, llm_client=context["llm_client"], model=model)
        if not isinstance(candidate, Mapping):
            raise ValueError("adapter candidate is invalid")
        candidate = {**candidate, "job_id": context["job"]["job_id"], "ticker": context["request"]["ticker"], "source_type": source_type, "source_url": source["url"], "allowed_hosts": list(trusted_allowed_hosts)}
        persisted_candidate = _repo_call(context, "create_adapter_candidate", candidate)
        adapter_value = persisted_candidate.get("adapter", candidate.get("adapter")) if isinstance(persisted_candidate, Mapping) else candidate.get("adapter")
        def adapter_fetch(url, **kwargs):
            fetch_kwargs = dict(kwargs)
            fetch_kwargs["allowed_hosts"] = list(trusted_allowed_hosts)
            if context.get("url_resolver") is not None:
                fetch_kwargs["resolver"] = context["url_resolver"]
            return _invoke_sync(context["fetch_page"], url, **fetch_kwargs)

        validation = await _invoke(context["validate_candidate"], adapter_value, snapshot, fetch_page=adapter_fetch, requested_start=context["job"]["requested_start"], requested_end=context["job"]["requested_end"])
        validation = dict(validation or {})
        validation.update({"adapter_id": persisted_candidate.get("adapter_id"), "job_id": context["job"]["job_id"], "source_type": source_type})
        _repo_call(context, "record_adapter_validation", validation)
        if validation.get("status") != "passed":
            source.update({"extraction_status": "failed", "execution_path": "cold", "checked_at": _iso(context), "truncation_reason": "adapter_validation_failed"})
            saved = _repo_call(context, "save_source", source)
            return {"source_type": source_type, "status": "partial", "events": [], "source": saved}
        context["call_counts"]["event_extraction"] += 1
        try:
            execution = await _invoke(context["execute_adapter"], adapter_value, fetch_page=adapter_fetch, requested_start=context["job"]["requested_start"], requested_end=context["job"]["requested_end"])
            if not isinstance(execution, Mapping) or not isinstance(execution.get("observations", []), list):
                raise ValueError("adapter execution result is invalid")
        except Exception as exc:
            failure = {"status": "failed", "report": {"errors": [_sanitized_error(exc)]}, "errors": [_sanitized_error(exc)]}
            failure.update({"adapter_id": persisted_candidate["adapter_id"], "job_id": context["job"]["job_id"], "source_type": source_type})
            _repo_call(context, "record_adapter_validation", failure)
            raise ValueError("adapter execution failed") from None
        execution = dict(execution or {})
        events = execution.get("observations", [])
        complete = bool(execution.get("boundary_reached") or execution.get("archive_exhausted")) and not execution.get("truncation_reason")
        coverage_start = execution.get("coverage_start") or context["job"]["requested_start"]
        coverage_end = execution.get("coverage_end") or context["job"]["requested_end"]
        source.update({"extraction_status": "complete" if complete else "partial", "execution_path": "cold", "active_adapter_id": persisted_candidate.get("adapter_id"), "coverage_start": coverage_start, "coverage_end": coverage_end, "coverage_continuous": complete, "page_count": execution.get("page_count", 0), "item_count": execution.get("item_count", len(events)), "truncation_reason": execution.get("truncation_reason"), "checked_at": _iso(context)})
        if complete and not events:
            context["warnings"].append("valid_archive_exhausted_zero")
        saved = _repo_call(context, "activate_adapter_with_source", persisted_candidate["adapter_id"], _iso(context), source)
        context["execution_paths"][source_type] = "cold"
        return {"source_type": source_type, "status": "complete" if complete else "partial", "events": events, "source": saved, "adapter": persisted_candidate}
    except (RuntimeError, sqlite3.Error):
        raise
    except Exception as exc:
        context["warnings"].append(f"{source_type} extraction failed")
        source.update({"extraction_status": "failed", "execution_path": "cold", "checked_at": _iso(context), "truncation_reason": "workflow_stage_failed"})
        try:
            saved = _repo_call(context, "save_source", source)
        except Exception:
            saved = source
        context["execution_paths"][source_type] = "cold"
        return {"source_type": source_type, "status": "partial", "events": [], "source": saved, "error": _sanitized_error(exc)}


async def run_research(request, *, db_path=None, http_client=None, dependencies=None):
    if not isinstance(request, Mapping):
        raise ValueError("research request is required")
    normalized = domain.normalize_request(request.get("ticker"), request.get("years", 4), request.get("as_of"))
    normalized.update({key: value for key, value in request.items() if key not in normalized})
    repository = (dependencies or {}).get("repository", default_repository)
    effective_db_path = db_path or getattr(repository, "DEFAULT_DB_PATH", default_repository.DEFAULT_DB_PATH)
    owns_http_client = http_client is None
    effective_http_client = http_client
    connection = None
    try:
        connection = _connect_repository(repository, effective_db_path)
        if owns_http_client:
            effective_http_client = HttpClient()
    except Exception:
        if connection is not None:
            close = getattr(connection, "close", None)
            if callable(close):
                close()
        raise
    context = {
        "request": normalized,
        "db_path": effective_db_path,
        "http_client": effective_http_client,
        "repository": repository,
        "connection": connection,
        "clock": (dependencies or {}).get("clock", lambda: datetime.now(UTC)),
        "call_counts": {"discovery": 0, "adapter_generation": 0, "event_extraction": 0, "classification": 0},
        "warnings": [],
        "next_actions": [],
        "execution_paths": {},
        "url_resolver": None,
    }
    context.update(_default_dependencies(context["db_path"], context["http_client"]))
    context.update(dependencies or {})
    context["warnings"].extend(context.get("inference_warnings", []))
    if context.get("inference_warnings"):
        context["next_actions"].append("configure_catalyst_llm")
    aliases = {
        "discover": "discover_sources",
        "inspect_snapshot": "build_snapshot",
        "generate": "generate_adapter",
        "validate": "validate_candidate",
        "execute": "execute_adapter",
        "classify": "classify_observations",
        "stats": "calculate_statistics",
        "normalize": "normalize_observations",
    }
    for alias, target in aliases.items():
        if alias in context and target not in (dependencies or {}):
            context[target] = context[alias]
    job = None
    try:
        job = _repo_call(context, "create_job", normalized, now=_now(context))
        context["job"] = job
        _repo_call(context, "start_job", job["job_id"], _iso(context))
        company = await _resolve(context)
        context["company"] = company
        _repo_call(context, "update_resolved_company", company=company, job_id=job["job_id"])
        discovery = await _discover(context, company)
        prepared, origins = await _prepare_sources(context, company, discovery)
        channel_results = {source_type: await _run_channel(context, company, source_type, prepared.get(source_type)) for source_type in _REQUIRED_CHANNELS}
        events = []
        source_rows = []
        for source_type, result in channel_results.items():
            source = result.get("source")
            if source:
                source_rows.append(source)
            for index, event in enumerate(result.get("events", []), 1):
                if not isinstance(event, Mapping):
                    continue
                event = dict(event)
                event.setdefault("id", len(events) + 1)
                event["source_id"] = source.get("source_id") if source else None
                event.setdefault("ticker", normalized["ticker"])
                event.setdefault("source_type", source_type)
                event.setdefault("adapter_id", result.get("adapter", {}).get("adapter_id") if isinstance(result.get("adapter"), Mapping) else None)
                events.append(event)
        normalized_events = []
        for source_type in _REQUIRED_CHANNELS:
            rows = [event for event in events if event.get("source_type") == source_type]
            normalized_result = _invoke_sync(context["normalize_observations"], normalized["ticker"], source_type, rows, job["requested_start"], job["requested_end"])
            normalized_events.extend(normalized_result["events"])
        for index, event in enumerate(normalized_events, 1):
            event.setdefault("id", index)
        classification = await _invoke(context["classify_observations"], normalized_events, llm_client=context["llm_client"], model=_source_model(context, "classification"))
        classification = dict(classification or {})
        context["call_counts"]["classification"] = classification.get("llm_call_count", 0)
        classified_events = classification.get("events", normalized_events)
        ambiguous = any(event.get("earnings_state") == "ambiguous" for event in classified_events)
        complete_channels = all(channel_results[item]["status"] == "complete" for item in _REQUIRED_CHANNELS)
        accepted_channels = sum(channel_results[item]["status"] in {"complete", "partial"} for item in _REQUIRED_CHANNELS)
        llm_unavailable = not context["llm_client"] or not _source_model(context, "adapter_generation")
        if llm_unavailable:
            context["warnings"].append("catalyst_llm_unavailable")
            context["next_actions"].append("configure_catalyst_llm")
        status = "completed" if complete_channels and not ambiguous else "completed_partial" if accepted_channels or events or llm_unavailable else "unsupported"
        stats = await _invoke(context["calculate_statistics"], classified_events, source_rows, {"start": job["requested_start"], "end": job["requested_end"]})
        if ambiguous:
            context["warnings"].append("classification is incomplete")
            context["warnings"].append("classification_ambiguous")
            context["next_actions"].append("review ambiguous earnings classifications")
            context["next_actions"].append("review_ambiguous_classification")
        if status == "completed_partial":
            context["next_actions"].append("provide missing archive coverage or review partial extraction")
        _repo_call(context, "finalize_job_with_observations", job["job_id"], classified_events, classified_events, {"status": status, "statistics": stats, "warnings": list(dict.fromkeys(context["warnings"])), "next_actions": list(dict.fromkeys(context["next_actions"])), "execution_paths": context["execution_paths"], "call_counts": context["call_counts"], "completed_at": _iso(context)})
    except Exception as exc:
        if job is not None:
            try:
                _repo_call(context, "fail_job", job["job_id"], _sanitized_error(exc), completed_at=_iso(context))
            except Exception:
                LOGGER.error("catalyst workflow finalization failed ticker=%s job_id=%s", normalized["ticker"], job["job_id"])
        else:
            try:
                connection.close()
            finally:
                if owns_http_client:
                    close = getattr(effective_http_client, "close", None)
                    if callable(close):
                        close()
            raise
    try:
        loaded = _repo_call(context, "load_job_result", context["job"]["job_id"])
        if isinstance(loaded, dict):
            loaded.setdefault("call_counts", dict(context["call_counts"]))
            loaded.setdefault("execution_paths", dict(context["execution_paths"]))
        return loaded
    finally:
        close = getattr(connection, "close", None)
        if callable(close):
            close()
        if owns_http_client:
            close = getattr(effective_http_client, "close", None)
            if callable(close):
                close()

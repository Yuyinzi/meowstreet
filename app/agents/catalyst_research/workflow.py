import inspect
import re
import sqlite3
from collections.abc import Mapping
from datetime import UTC, datetime
from urllib.parse import urljoin

from app.agents.catalyst_research import backfill as historical_backfill
from app.agents.catalyst_research import domain, statistics
from app.agents.catalyst_research import ingestion as candidate_ingestion
from app.agents.catalyst_research import registry as registry_state
from app.agents.catalyst_research import registry_discovery
from app.agents.catalyst_research import scheduler as update_scheduler
from app.agents.catalyst_research.adapters import executor as adapter_executor
from app.agents.catalyst_research.adapters import generator as adapter_generator
from app.agents.catalyst_research.adapters import validator as adapter_validator
from app.agents.catalyst_research.config import load_collection_config, load_inference_bundle, load_search_config
from app.agents.catalyst_research.extraction.articles import extract_direct_article
from app.agents.catalyst_research.extraction.router import ExtractionRouter
from app.agents.catalyst_research.extraction import build_structural_snapshot, fetch_html_page
from app.agents.catalyst_research.persistence import repository as default_repository
from app.agents.catalyst_research.providers.ddgs import DDGSSearchProvider
from app.agents.catalyst_research.providers.firecrawl import build_firecrawl_provider
from app.agents.catalyst_research.providers.native_search import NativeSearchProvider
from app.agents.catalyst_research.providers.router import SearchRouter
from app.agents.catalyst_research.providers.tavily import TavilySearchProvider
from app.data_sources import sec_edgar
from app.db import edgar_filings as edgar_db
from app.http_client import HttpClient
from app.runtime_logging import get_runtime_logger


LOGGER = get_runtime_logger(__name__)
_REQUIRED_CHANNELS = ("press_releases", "events_presentations")
_V1_1_CHANNELS = ("press_releases", "events_presentations", "earnings_results")
_DISCOVERY_CHANNELS = ("ir_home", "press_releases", "events_presentations", "earnings_results")
_INFORMATIONAL_SOURCE_TYPES = ("ir_home", "earnings_results")
_MAX_TRAVERSAL_ORIGINS = 2
_MAX_TRAVERSAL_TARGETS = 4
_TRAVERSAL_PURPOSE_TERMS = {
    "press_releases": ("press", "release", "news"),
    "events_presentations": ("event", "presentation", "webcast", "conference"),
}
_UNSUPPORTED_FETCH_TERMS = ("content type", "non-html", "non html", "javascript", "requires js", "requires javascript")
_ANSWERED_FEED_OUTCOMES = ("success_new", "success_empty")


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
    zero_state = bool(re.search(r"\b(?:no|none)\b[^.]{0,80}\b(?:press releases?|news releases?|events?|presentations?)\b[^.]{0,80}\b(?:available|currently)\b", visible_text))
    placeholder = bool(re.search(r"\b(?:loading|please wait)\b", visible_text)) and any(term in visible_text for term in archive_terms)
    placeholder = placeholder or bool(re.search(r"\b(?:enable|turn on) javascript\b|\bjavascript (?:is )?required\b", visible_text))
    script_bundle = script_count >= 4 or bool(re.search(r"<script\b[^>]+\bsrc=", html, flags=re.IGNORECASE))
    empty_shell = not meaningful_archive_text
    return bool(app_root and script_bundle and (empty_shell or placeholder) and not zero_state and not links and date_evidence is None)


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


def _default_search_router(inference, args=None):
    config = load_search_config(args)
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


def _default_inference(args=None):
    try:
        return load_inference_bundle(args)
    except Exception:
        return {"client": None, "models": {}, "warnings": ["catalyst_llm_configuration_failed"]}


def _default_dependencies(db_path, http_client, args=None):
    inference = _default_inference(args)
    try:
        search_router = _default_search_router(inference, args)
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
        "validate_active_adapter": adapter_validator.validate_active_adapter,
        "execute_adapter": adapter_executor.execute_adapter,
        "classify_observations": domain.classify_observations,
        "normalize_observations": domain.normalize_observations,
        "calculate_statistics": statistics.calculate_statistics,
        "discover_registry": registry_discovery.discover_registry,
        "run_historical_backfill": historical_backfill.run_historical_backfill,
        "run_daily_update": update_scheduler.run_daily_update,
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


def _progress(context, stage, **details):
    callback = context.get("progress")
    if not callable(callback):
        return
    try:
        callback(stage, **details)
    except Exception:
        pass


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


def _save_accepted_information_source(context, source, snapshot):
    row = dict(source)
    row.update({"ticker": context["request"]["ticker"], "job_id": context["job"]["job_id"], "acceptance_status": "accepted", "extraction_status": "pending", "final_url": snapshot.get("final_url"), "snapshot_hash": snapshot.get("content_hash"), "content_hash": snapshot.get("content_hash"), "execution_path": "cold", "checked_at": _iso(context)})
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


async def _discover(context, company, source_types=None):
    _progress(context, "discovery", channels=",".join(sorted(str(item) for item in source_types)) if source_types else "all")
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
        source_types=source_types,
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


async def _prepare_sources(context, company, discovery, source_types=None):
    source_types = tuple(source_types or _REQUIRED_CHANNELS)
    raw_sources = list(discovery.get("sources", []))
    raw_sources.extend(discovery.get("alternate_sources", []))
    candidates = {}
    for source in raw_sources:
        if not isinstance(source, Mapping) or source.get("source_type") not in _DISCOVERY_CHANNELS or not source.get("url"):
            continue
        candidates.setdefault(source["source_type"], []).append(dict(source))
    origin_snapshots = []
    for source_type in _INFORMATIONAL_SOURCE_TYPES:
        for source in candidates.get(source_type, [])[:_MAX_TRAVERSAL_ORIGINS]:
            try:
                snapshot = await _fetch_snapshot(context, company, source)
            except ValueError as exc:
                if _unsupported_fetch_error(exc):
                    context["warnings"].append(_unsupported_warning_code(exc))
                    context["next_actions"].append("provide_extractable_archive_url")
                    _save_unaccepted_source(context, source, status="pending", extraction_status="unsupported")
                else:
                    context["warnings"].append(f"{source_type} fetch failed")
                    _save_unaccepted_source(context, source, status="rejected")
                continue
            if snapshot.get("company_verified"):
                _save_accepted_information_source(context, source, snapshot)
                if source_type == "ir_home":
                    origin_snapshots.append({"source": source, "snapshot": snapshot})
                continue
            context["warnings"].append("source_identity_ambiguous")
            context["next_actions"].append("review_ambiguous_source")
            _save_unaccepted_source(context, source, status="ambiguous", snapshot=snapshot, verification_reason=snapshot.get("verification_error"))
    prepared = {}
    for source_type in source_types:
        accepted = []
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
                accepted.append((source, snapshot))
                continue
            context["warnings"].append("source_identity_ambiguous")
            context["next_actions"].append("review_ambiguous_source")
            _save_unaccepted_source(context, source, status="ambiguous", snapshot=snapshot, verification_reason=snapshot.get("verification_error"))
        if not accepted:
            traversed = await _traverse_source(context, company, origin_snapshots, source_type)
            if traversed and traversed[0] is not None:
                accepted.append(traversed)
        prepared[source_type] = accepted
    return prepared, origin_snapshots


async def _run_channel_candidate(context, company, source_type, pair):
    if pair is None or pair[0] is None:
        context["execution_paths"][source_type] = "cold"
        _progress(context, "source_missing", source=source_type)
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
    _progress(context, "adapter_generation", source=source_type)
    try:
        candidate = await _invoke(context["generate_adapter"], company, source, snapshot, llm_client=context["llm_client"], model=model)
    except Exception:
        context["warnings"].append("catalyst_llm_request_failed")
        context["next_actions"].append("configure_catalyst_llm")
        context["execution_paths"][source_type] = "cold"
        source.update({"extraction_status": "failed", "execution_path": "cold", "checked_at": _iso(context), "truncation_reason": "adapter_generation_failed"})
        saved = _repo_call(context, "save_source", source)
        return {"source_type": source_type, "status": "partial", "events": [], "source": saved}
    try:
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
        _progress(context, "adapter_validated", source=source_type, status=validation.get("status"))
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
        page_hashes = list(execution.get("content_hashes", []))
        source.update({"extraction_status": "complete" if complete else "partial", "execution_path": "cold", "active_adapter_id": persisted_candidate.get("adapter_id"), "adapter_version": persisted_candidate.get("version"), "executor_version": execution.get("executor_version"), "coverage_start": coverage_start, "coverage_end": coverage_end, "coverage_continuous": complete, "page_count": execution.get("page_count", 0), "item_count": execution.get("item_count", len(events)), "content_hash": page_hashes[-1] if page_hashes else source.get("content_hash"), "truncation_reason": execution.get("truncation_reason"), "checked_at": _iso(context)})
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


async def _run_channel(context, company, source_type, candidates):
    if not candidates:
        return await _run_channel_candidate(context, company, source_type, None)
    best_result = None
    for candidate in candidates:
        result = await _run_channel_candidate(context, company, source_type, candidate)
        if result.get("status") == "complete":
            return result
        if best_result is None or len(result.get("events", [])) > len(best_result.get("events", [])):
            best_result = result
    return best_result


def _bound_adapter_fetch(context, adapter, *, capture_snapshots=None):
    allowed_hosts = list(adapter.get("allowed_hosts", []))

    def fetch(url, **kwargs):
        fetch_kwargs = dict(kwargs)
        fetch_kwargs["allowed_hosts"] = allowed_hosts
        if context.get("url_resolver") is not None:
            fetch_kwargs["resolver"] = context["url_resolver"]
        page = _invoke_sync(context["fetch_page"], url, **fetch_kwargs)
        if capture_snapshots is None:
            return page
        if not isinstance(page, Mapping):
            raise ValueError("fetched page is invalid")
        html = page.get("html")
        if not isinstance(html, str):
            raise ValueError("fetched page html is invalid")
        source = {"source_type": adapter.get("source_type"), "url": adapter.get("source_url") or url}
        snapshot = _invoke_sync(context["build_snapshot"], page, source=source)
        if not isinstance(snapshot, Mapping):
            raise ValueError("source snapshot is invalid")
        snapshot = dict(snapshot)
        snapshot.setdefault("requested_url", page.get("requested_url") or url)
        snapshot.setdefault("final_url", page.get("final_url") or url)
        if "raw_html" not in snapshot:
            snapshot["raw_html"] = html
            snapshot.pop("content_hash", None)
        snapshot.setdefault("metadata", page.get("metadata") or {})
        normalized = snapshot.get("normalized")
        normalized = dict(normalized) if isinstance(normalized, Mapping) else {}
        normalized.setdefault("metadata", snapshot["metadata"])
        snapshot["normalized"] = normalized
        snapshot.setdefault("response_bytes", page.get("response_bytes") or len(html.encode()))
        snapshot.setdefault("content_type", page.get("content_type") or "text/html")
        snapshot.setdefault("truncated", bool(page.get("truncated", False)))
        content_hash = _repo_call(context, "save_snapshot", snapshot)
        capture_snapshots.append({"requested_url": snapshot["requested_url"], "final_url": snapshot["final_url"], "content_hash": content_hash})
        return page

    return fetch


def _hot_source(context, adapter_row, execution):
    adapter = adapter_row["adapter"]
    observations = list(execution.get("observations", []))
    report = execution.get("report") or {}
    truncation_reason = execution.get("truncation_reason") or report.get("pagination", {}).get("truncation_reason")
    coverage_dates = [item.get("count_date") for item in observations if item.get("count_date")]
    coverage_start = execution.get("coverage_start") or (min(coverage_dates) if coverage_dates else None)
    coverage_end = execution.get("coverage_end") or (max(coverage_dates) if coverage_dates else None)
    has_boundary_evidence = "boundary_reached" in execution or "archive_exhausted" in execution
    complete = (bool(execution.get("boundary_reached") or execution.get("archive_exhausted")) if has_boundary_evidence else bool(observations)) and not truncation_reason
    hashes = list(execution.get("content_hashes") or execution.get("page_content_hashes") or report.get("page_content_hashes", []))
    source = {
        "ticker": context["request"]["ticker"],
        "job_id": context["job"]["job_id"],
        "source_type": adapter_row["source_type"],
        "url": adapter_row.get("source_url") or str(adapter.get("source_url")),
        "final_url": adapter_row.get("source_url") or str(adapter.get("source_url")),
        "acceptance_status": "accepted",
        "extraction_status": "complete" if complete else "partial",
        "active_adapter_id": adapter_row.get("adapter_id"),
        "adapter_version": adapter_row.get("version"),
        "executor_version": execution.get("executor_version") or report.get("executor_version"),
        "requested_start": context["job"]["requested_start"],
        "requested_end": context["job"]["requested_end"],
        "coverage_start": coverage_start,
        "coverage_end": coverage_end,
        "coverage_continuous": complete,
        "page_count": execution.get("page_count") or report.get("pagination", {}).get("pages", 0),
        "item_count": execution.get("item_count") if execution.get("item_count") is not None else len(observations),
        "content_hash": hashes[-1] if hashes else None,
        "snapshot_hash": hashes[-1] if hashes else None,
        "truncation_reason": truncation_reason,
        "execution_path": "hot",
        "checked_at": _iso(context),
    }
    return source


def _record_runtime_validation(context, adapter_row, validation):
    record = getattr(context["repository"], "record_runtime_adapter_validation", None)
    if not callable(record):
        return
    if not adapter_row.get("adapter_id"):
        return
    report = validation.get("report") if isinstance(validation, Mapping) else {}
    report = report if isinstance(report, Mapping) else {}
    runtime_status = "passed" if isinstance(validation, Mapping) and validation.get("status") == "passed" else "failed"
    _repo_call(
        context,
        "record_runtime_adapter_validation",
        {
            "adapter_id": adapter_row.get("adapter_id"),
            "job_id": context["job"]["job_id"],
            "status": runtime_status,
            "report": report,
            "source_content_hashes": validation.get("source_content_hashes", report.get("source_content_hashes", [])) if isinstance(validation, Mapping) else [],
            "page_content_hashes": validation.get("page_content_hashes", report.get("page_content_hashes", [])) if isinstance(validation, Mapping) else [],
            "validator_version": validation.get("validator_version") if isinstance(validation, Mapping) else None,
            "executor_version": validation.get("executor_version") if isinstance(validation, Mapping) else report.get("executor_version"),
        },
    )


def _stale_source(context, adapter_row, validation):
    report = validation.get("report") if isinstance(validation, Mapping) else {}
    report = report if isinstance(report, Mapping) else {}
    errors = validation.get("errors", []) if isinstance(validation, Mapping) else []
    if not errors:
        errors = report.get("errors", [])
    page_hashes = validation.get("page_content_hashes", report.get("page_content_hashes", [])) if isinstance(validation, Mapping) else []
    return {
        "job_id": context["job"]["job_id"],
        "ticker": context["request"]["ticker"],
        "source_type": adapter_row.get("source_type"),
        "url": adapter_row.get("source_url") or str(adapter_row.get("adapter", {}).get("source_url", "")),
        "final_url": adapter_row.get("source_url"),
        "active_adapter_id": adapter_row.get("adapter_id"),
        "adapter_version": adapter_row.get("version"),
        "executor_version": validation.get("executor_version") if isinstance(validation, Mapping) else None,
        "verification_reason": _sanitized_error(errors[0] if errors else "runtime adapter validation failed"),
        "page_count": report.get("pagination", {}).get("pages", 0),
        "item_count": 0,
        "content_hash": page_hashes[-1] if page_hashes else None,
        "snapshot_hash": page_hashes[-1] if page_hashes else None,
        "execution_path": "hot",
        "checked_at": _iso(context),
    }


async def _run_hot_adapter(context, adapter_row):
    adapter = adapter_row.get("adapter")
    if not isinstance(adapter, Mapping):
        validation = {"status": "failed", "observations": [], "promotable_observations": [], "errors": ["active adapter is invalid"]}
        _record_runtime_validation(context, adapter_row, validation)
        return {"source_type": adapter_row.get("source_type"), "status": "stale", "events": [], "source": None, "validation": validation}
    captured_snapshots = []
    bound_fetch = _bound_adapter_fetch(context, adapter, capture_snapshots=captured_snapshots)
    try:
        validation = await _invoke(
            context["validate_active_adapter"],
            adapter,
            fetch_page=bound_fetch,
            requested_start=context["job"]["requested_start"],
            requested_end=context["job"]["requested_end"],
        )
    except Exception as exc:
        validation = {"status": "stale", "observations": [], "promotable_observations": [], "errors": [_sanitized_error(exc)]}
    if isinstance(validation, Mapping):
        report = validation.get("report") if isinstance(validation.get("report"), Mapping) else {}
        execution = validation.get("execution") if isinstance(validation.get("execution"), Mapping) else {}
        reported_hashes = list(validation.get("page_content_hashes") or report.get("page_content_hashes", []) or execution.get("content_hashes", []))
        captured_hashes = [item["content_hash"] for item in captured_snapshots]
        if reported_hashes and captured_hashes != reported_hashes:
            validation = {
                **validation,
                "status": "stale",
                "observations": [],
                "promotable_observations": [],
                "errors": ["runtime page hash mismatch"],
                "report": {**report, "errors": ["runtime page hash mismatch"], "page_content_hashes": captured_hashes},
                "page_content_hashes": captured_hashes,
            }
    _record_runtime_validation(context, adapter_row, validation)
    if not isinstance(validation, Mapping) or validation.get("status") != "passed":
        return {"source_type": adapter_row.get("source_type"), "status": "stale", "events": [], "source": None, "validation": dict(validation or {})}
    execution = validation.get("execution")
    if not isinstance(execution, Mapping):
        execution = {"observations": validation.get("promotable_observations", validation.get("observations", [])), "report": validation.get("report", {}), "page_content_hashes": validation.get("page_content_hashes", [])}
    events = list(validation.get("promotable_observations", execution.get("observations", [])))
    execution = {**execution, "observations": events, "report": validation.get("report", execution.get("report", {})), "page_content_hashes": validation.get("page_content_hashes", execution.get("page_content_hashes", [])), "executor_version": validation.get("executor_version")}
    source = _hot_source(context, adapter_row, execution)
    saved = _repo_call(context, "save_source", source)
    context["execution_paths"][adapter_row["source_type"]] = "hot"
    return {"source_type": adapter_row["source_type"], "status": "complete" if source["extraction_status"] == "complete" else "partial", "events": events, "source": saved, "adapter": adapter_row, "validation": validation}


async def _run_source(context, company, source_type, active_adapter):
    if active_adapter is not None:
        _progress(context, "hot_validation", source=source_type)
        hot = await _run_hot_adapter(context, active_adapter)
        if hot["status"] != "stale":
            _progress(context, "hot_complete", source=source_type, status=hot["status"])
            return hot
        _progress(context, "adapter_stale", source=source_type)
        mark_stale_with_source = getattr(context["repository"], "mark_adapter_stale_with_source", None)
        if callable(mark_stale_with_source):
            _repo_call(context, "mark_adapter_stale_with_source", active_adapter["adapter_id"], _iso(context), _stale_source(context, active_adapter, hot.get("validation", {})))
        else:
            mark_stale = getattr(context["repository"], "mark_adapter_stale", None)
            if callable(mark_stale):
                _repo_call(context, "mark_adapter_stale", active_adapter["adapter_id"], _iso(context))
        context["warnings"].append(f"{source_type} adapter drift detected")
        context["warnings"].append("source_discovery_required")
        context["next_actions"].append(f"discover {source_type} source")
    context["execution_paths"][source_type] = "cold"
    return None


def _registry_supported(repository):
    return callable(getattr(repository, "load_company_registry", None)) and callable(
        getattr(repository, "load_source_endpoints", None)
    )


def _collection_config(context):
    supplied = context.get("collection_config")
    if isinstance(supplied, dict):
        return supplied
    return load_collection_config(context.get("config_args"))


def _build_extraction_router(context):
    supplied = context.get("extraction_router")
    if supplied is not None:
        return supplied
    factory = context.get("build_extraction_router")
    if callable(factory):
        return _invoke_sync(factory, context)
    config = _collection_config(context)
    firecrawl_provider = build_firecrawl_provider(config)

    def direct_extractor(url, **kwargs):
        if context.get("url_resolver") is not None:
            kwargs.setdefault("resolver", context["url_resolver"])
        return extract_direct_article(url, http_client=context["http_client"], **kwargs)

    return ExtractionRouter(direct_extractor, firecrawl_provider=firecrawl_provider)


def _recording_ingester(context, recorded):
    ingester = context.get("ingest_candidates") or candidate_ingestion.ingest_candidates

    async def ingest(candidates, **kwargs):
        result = await ingester(candidates, **kwargs)
        if isinstance(result, dict):
            recorded["events"].extend(result.get("events") or [])
            recorded["sources"].extend(result.get("sources") or [])
        return result

    return ingest


def _archive_enrichment_runner(context, company):
    async def run_adapter(*, channel, company=None, request=None):
        loader = getattr(context["repository"], "load_active_adapter", None)
        if not callable(loader):
            return None
        active = _repo_call(context, "load_active_adapter", context["request"]["ticker"], channel)
        if not isinstance(active, Mapping):
            return None
        return await _run_source(context, company or context["company"], channel, active)

    return run_adapter


def _backfill_dependencies(context, company):
    dependencies = {
        "http_client": context["http_client"],
        "search_router": context.get("search_router"),
        "ingest_candidates": context.get("ingest_candidates") or candidate_ingestion.ingest_candidates,
        "extraction_router": _build_extraction_router(context),
        "repository": context["repository"],
        "connection": context["connection"],
        "job": context["job"],
        "run_adapter": _archive_enrichment_runner(context, company),
    }
    for key in ("fetch_feed", "adapter", "execute_query"):
        if context.get(key) is not None:
            dependencies[key] = context[key]
    return dependencies


async def _load_registry_state(context):
    _progress(context, "load_registry", ticker=context["request"]["ticker"])
    registry = _repo_call(context, "load_company_registry", context["request"]["ticker"])
    endpoints = _repo_call(context, "load_source_endpoints", context["request"]["ticker"])
    if registry is not None and not isinstance(registry, Mapping):
        raise ValueError("company registry is invalid")
    if not isinstance(endpoints, list):
        raise ValueError("source endpoints are invalid")
    return dict(registry) if isinstance(registry, Mapping) else None, endpoints


async def _discover_registry_stage(context, company):
    _progress(context, "discover_registry", ticker=context["request"]["ticker"])
    context["call_counts"]["discovery"] += 1
    result = await _invoke(
        context["discover_registry"],
        company,
        router=context["search_router"],
        llm_client=context["llm_client"],
        model=_source_model(context, "registry_selection"),
        repository=context["repository"],
        job_id=context["job"]["job_id"],
        connection=context["connection"],
        http_client=context["http_client"],
        overrides=context["request"].get("source_overrides"),
        resolver=context.get("url_resolver"),
    )
    if not isinstance(result, Mapping):
        raise ValueError("registry discovery result is invalid")
    result = dict(result)
    context["warnings"].extend(result.get("warnings") or [])
    context["next_actions"].extend(result.get("next_actions") or [])
    if result.get("status") == "search_unavailable":
        context["warnings"].append("catalyst_no_search_provider")
        context["next_actions"].append("configure_catalyst_search_provider")
    return result


async def _run_research_mode(context, company, registry, endpoints):
    if context["request"].get("force_discovery") or not registry_state.registry_ready(registry, endpoints):
        discovery = await _discover_registry_stage(context, company)
        registry = discovery.get("registry") or registry
        discovered_endpoints = discovery.get("endpoints")
        if isinstance(discovered_endpoints, list):
            endpoints = discovered_endpoints
    if not isinstance(registry, Mapping):
        context["next_actions"].append("provide a verified official source override")
        return {
            "events": [],
            "sources": [],
            "status": "unsupported",
            "channel_evidence": _channel_evidence_stub("unsupported"),
        }
    company = {**company, "official_domains": list(registry_state.approved_domains(dict(registry)))}
    context["company"] = company
    request = {
        **context["request"],
        "requested_start": context["job"]["requested_start"],
        "requested_end": context["job"]["requested_end"],
        "job_id": context["job"]["job_id"],
    }
    _progress(context, "historical_backfill", channels=",".join(_V1_1_CHANNELS))
    result = await _invoke(
        context["run_historical_backfill"],
        company,
        request,
        endpoints=endpoints,
        config=_collection_config(context),
        dependencies=_backfill_dependencies(context, company),
    )
    if not isinstance(result, Mapping):
        raise ValueError("historical backfill result is invalid")
    context["warnings"].extend(result.get("warnings") or [])
    channels = result.get("channels") or {}
    events = []
    sources = []
    statuses = []
    channel_evidence = []
    for channel in _V1_1_CHANNELS:
        payload = channels.get(channel) or {}
        channel_sources = payload.get("sources") or []
        fallback_source_id = next(
            (
                source.get("source_id")
                for source in reversed(channel_sources)
                if isinstance(source, Mapping) and source.get("source_id")
            ),
            None,
        )
        for event in payload.get("events") or []:
            event = dict(event)
            if fallback_source_id is not None:
                event.setdefault("source_id", fallback_source_id)
            events.append(event)
        sources.extend(channel_sources)
        coverage_status = payload.get("coverage_status") or "unsupported"
        statuses.append(coverage_status)
        channel_evidence.append(
            _channel_evidence_row(
                channel,
                coverage_status=coverage_status,
                discovery_methods=payload.get("discovery_methods"),
                observed_start=payload.get("observed_start"),
                observed_end=payload.get("observed_end"),
            )
        )
        context["execution_paths"][channel] = "v1_1"
    if all(status == "complete" for status in statuses):
        status = "completed"
    elif events or any(item in {"observed_partial", "missing"} for item in statuses):
        status = "completed_partial"
    else:
        status = "unsupported"
    return {"events": events, "sources": sources, "status": status, "channel_evidence": channel_evidence}


async def _run_update_mode(context, company, registry, endpoints):
    try:
        official_domains = registry_state.approved_domains(dict(registry)) if isinstance(registry, Mapping) else frozenset()
    except ValueError:
        official_domains = frozenset()
    if not official_domains:
        context["warnings"].append("catalyst_registry_unavailable")
        context["next_actions"].append("run catalyst research to establish a source registry")
        return {
            "events": [],
            "sources": [],
            "status": "unsupported",
            "channel_evidence": _channel_evidence_stub("unsupported"),
        }
    company = {**company, "official_domains": list(registry_state.approved_domains(dict(registry)))}
    context["company"] = company
    latest_gap_search = {}
    for channel in _V1_1_CHANNELS:
        loader = getattr(context["repository"], "load_latest_gap_search_at", None)
        if callable(loader):
            latest_gap_search[channel] = _repo_call(context, "load_latest_gap_search_at", context["request"]["ticker"], channel)
    recorded = {"events": [], "sources": []}
    dependencies = {
        "http_client": context["http_client"],
        "search_router": context.get("search_router"),
        "ingest_candidates": _recording_ingester(context, recorded),
        "extraction_router": _build_extraction_router(context),
        "latest_gap_search": latest_gap_search,
        "repository": context["repository"],
        "connection": context["connection"],
        "job": context["job"],
    }
    for key in ("fetch_feed", "execute_query", "record_endpoint_check", "update_endpoint_health"):
        if context.get(key) is not None:
            dependencies[key] = context[key]
    _progress(context, "daily_update", ticker=context["request"]["ticker"])
    result = await _invoke(
        context["run_daily_update"],
        company,
        registry=dict(registry),
        endpoints=endpoints,
        as_of=_now(context),
        config=_collection_config(context),
        dependencies=dependencies,
    )
    if not isinstance(result, Mapping):
        raise ValueError("daily update result is invalid")
    failure_outcomes = {"request_failed", "parse_failed"}
    feeds = [feed for feed in result.get("feeds") or [] if isinstance(feed, Mapping)]
    gaps = [gap for gap in result.get("gaps") or [] if isinstance(gap, Mapping)]
    if feeds:
        failures = sum(1 for feed in feeds if feed.get("outcome") in failure_outcomes)
        _progress(context, "feeds", count=len(feeds), failures=failures)
    if gaps:
        _progress(context, "gap_search", channels=",".join(sorted({str(gap.get("channel")) for gap in gaps})))
    feed_outcomes = [feed.get("outcome") for feed in feeds]
    status = "completed_partial" if any(outcome in failure_outcomes for outcome in feed_outcomes) else "completed"
    for channel in {feed.get("channel") for feed in feeds}:
        context["execution_paths"][channel] = "v1_1"
    endpoint_types = {
        endpoint.get("endpoint_id"): endpoint.get("endpoint_type")
        for endpoint in endpoints
        if isinstance(endpoint, Mapping)
    }
    channel_evidence = []
    for channel in _V1_1_CHANNELS:
        channel_events = [event for event in recorded["events"] if event.get("source_type") == channel]
        channel_evidence.append(
            _update_channel_evidence(
                channel,
                events=channel_events,
                feeds=feeds,
                gaps=gaps,
                endpoint_types=endpoint_types,
            )
        )
    return {
        "events": recorded["events"],
        "sources": recorded["sources"],
        "status": status,
        "channel_evidence": channel_evidence,
    }


async def _run_rediscover_mode(context, company, registry, endpoints):
    _progress(context, "rediscover", ticker=context["request"]["ticker"])
    try:
        discovery = await _discover_registry_stage(context, company)
    except Exception:
        context["warnings"].append("registry_rediscovery_failed")
        context["next_actions"].append("review source registry discovery inputs")
        return {
            "events": [],
            "sources": [],
            "status": "completed_partial" if isinstance(registry, Mapping) else "unsupported",
            "channel_evidence": _channel_evidence_stub("missing"),
        }
    if discovery.get("status") in {"accepted", "partial", "unchanged"} and isinstance(discovery.get("registry"), Mapping):
        return {
            "events": [],
            "sources": [],
            "status": "completed",
            "channel_evidence": _channel_evidence_stub("missing"),
        }
    if isinstance(registry, Mapping):
        context["next_actions"].append("review source registry coverage")
        return {
            "events": [],
            "sources": [],
            "status": "completed_partial",
            "channel_evidence": _channel_evidence_stub("missing"),
        }
    context["next_actions"].append("provide a verified official source override")
    return {
        "events": [],
        "sources": [],
        "status": "unsupported",
        "channel_evidence": _channel_evidence_stub("missing"),
    }


def _channel_evidence_row(channel, *, coverage_status, discovery_methods=None, observed_start=None, observed_end=None):
    return {
        "source_type": channel,
        "coverage_status": coverage_status,
        "discovery_methods": list(discovery_methods or []),
        "observed_start": observed_start,
        "observed_end": observed_end,
    }


def _channel_evidence_stub(coverage_status):
    return [_channel_evidence_row(channel, coverage_status=coverage_status) for channel in _V1_1_CHANNELS]


def _update_channel_evidence(channel, *, events, feeds, gaps, endpoint_types):
    channel_feeds = [feed for feed in feeds if feed.get("channel") == channel]
    answered_feeds = [feed for feed in channel_feeds if feed.get("outcome") in _ANSWERED_FEED_OUTCOMES]
    gap_searched = any(gap.get("channel") == channel for gap in gaps)
    if events:
        coverage_status = "observed_partial"
    elif answered_feeds or gap_searched:
        coverage_status = "missing"
    else:
        coverage_status = "unsupported"
    methods = []
    for event in events:
        discovered = event.get("discovery_methods")
        if not discovered and event.get("discovery_method"):
            discovered = [event.get("discovery_method")]
        for method in discovered or []:
            if method and method not in methods:
                methods.append(method)
    for feed in answered_feeds:
        method = endpoint_types.get(feed.get("endpoint_id"))
        if method and method not in methods:
            methods.append(method)
    days = sorted({event.get("count_date") for event in events if event.get("count_date")})
    return _channel_evidence_row(
        channel,
        coverage_status=coverage_status,
        discovery_methods=methods,
        observed_start=days[0] if days else None,
        observed_end=days[-1] if days else None,
    )


async def _classify_events(context, job, events):
    normalized_events = []
    for source_type in dict.fromkeys(event.get("source_type") for event in events):
        rows = [event for event in events if event.get("source_type") == source_type]
        normalized_result = _invoke_sync(
            context["normalize_observations"],
            context["request"]["ticker"],
            source_type,
            rows,
            job["requested_start"],
            job["requested_end"],
        )
        normalized_events.extend(normalized_result["events"])
    for index, event in enumerate(normalized_events, 1):
        event.setdefault("id", index)
    classification = await _invoke(
        context["classify_observations"],
        normalized_events,
        llm_client=context["llm_client"],
        model=_source_model(context, "classification"),
    )
    classification = dict(classification or {})
    context["call_counts"]["classification"] = classification.get("llm_call_count", 0)
    classified_events = classification.get("events", normalized_events)
    _progress(context, "classification", events=len(classified_events))
    ambiguous = any(event.get("earnings_state") == "ambiguous" for event in classified_events)
    return classified_events, ambiguous


async def _finalize_run(context, job, classified_events, source_rows, status, stats):
    _progress(context, "finalizing", status=status)
    _repo_call(
        context,
        "finalize_job_with_observations",
        job["job_id"],
        classified_events,
        classified_events,
        {
            "status": status,
            "statistics": stats,
            "warnings": list(dict.fromkeys(context["warnings"])),
            "next_actions": list(dict.fromkeys(context["next_actions"])),
            "execution_paths": context["execution_paths"],
            "call_counts": context["call_counts"],
            "completed_at": _iso(context),
        },
    )


async def _run_v1_1_workflow(context, company, job):
    mode = context["request"]["mode"]
    registry, endpoints = await _load_registry_state(context)
    if mode == "update":
        payload = await _run_update_mode(context, company, registry, endpoints)
    elif mode == "rediscover":
        payload = await _run_rediscover_mode(context, company, registry, endpoints)
    else:
        payload = await _run_research_mode(context, company, registry, endpoints)
    status = payload["status"]
    classified_events, ambiguous = await _classify_events(context, job, payload["events"])
    if ambiguous:
        context["warnings"].append("classification is incomplete")
        context["warnings"].append("classification_ambiguous")
        context["next_actions"].append("review ambiguous earnings classifications")
        context["next_actions"].append("review_ambiguous_classification")
        if status == "completed":
            status = "completed_partial"
    if status == "completed_partial":
        context["next_actions"].append("provide missing archive coverage or review partial extraction")
    stats = await _invoke(
        context["calculate_statistics"],
        classified_events,
        payload["channel_evidence"],
        {"start": job["requested_start"], "end": job["requested_end"]},
    )
    await _finalize_run(context, job, classified_events, payload["sources"], status, stats)


async def _run_legacy_workflow(context, company, normalized, repository, job):
    force_discovery = bool(normalized.get("force_discovery"))
    active_adapters = {}
    if not force_discovery:
        load_active = getattr(repository, "load_active_adapter", None)
        if callable(load_active):
            active_adapters = {
                source_type: _repo_call(context, "load_active_adapter", normalized["ticker"], source_type)
                for source_type in _REQUIRED_CHANNELS
            }
    channel_results = {}
    cold_channels = []
    for source_type in _REQUIRED_CHANNELS:
        result = await _run_source(context, company, source_type, active_adapters.get(source_type))
        if result is None:
            cold_channels.append(source_type)
        else:
            channel_results[source_type] = result
    if cold_channels:
        discovery = await _discover(context, company, {"ir_home", "earnings_results", *cold_channels})
        prepared, origins = await _prepare_sources(context, company, discovery, cold_channels)
        for source_type in cold_channels:
            channel_results[source_type] = await _run_channel(context, company, source_type, prepared.get(source_type))
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
            event.setdefault("adapter_version", result.get("adapter", {}).get("version") if isinstance(result.get("adapter"), Mapping) else source.get("adapter_version") if source else None)
            event.setdefault("executor_version", source.get("executor_version") if source else None)
            event.setdefault("content_hash", source.get("content_hash") if source else None)
            events.append(event)
    classified_events, ambiguous = await _classify_events(context, job, events)
    complete_channels = all(channel_results[item]["status"] == "complete" for item in _REQUIRED_CHANNELS)
    accepted_channels = sum(channel_results[item]["status"] in {"complete", "partial"} for item in _REQUIRED_CHANNELS)
    llm_unavailable = not context["llm_client"] or not _source_model(context, "adapter_generation")
    if llm_unavailable:
        context["warnings"].append("catalyst_llm_unavailable")
        context["next_actions"].append("configure_catalyst_llm")
    status = "completed" if complete_channels and not ambiguous else "completed_partial" if accepted_channels or events or llm_unavailable else "unsupported"
    if ambiguous:
        context["warnings"].append("classification is incomplete")
        context["warnings"].append("classification_ambiguous")
        context["next_actions"].append("review ambiguous earnings classifications")
        context["next_actions"].append("review_ambiguous_classification")
    if status == "completed_partial":
        context["next_actions"].append("provide missing archive coverage or review partial extraction")
    stats = await _invoke(context["calculate_statistics"], classified_events, source_rows, {"start": job["requested_start"], "end": job["requested_end"]})
    await _finalize_run(context, job, classified_events, source_rows, status, stats)


async def run_research(request, *, db_path=None, http_client=None, dependencies=None):
    if not isinstance(request, Mapping):
        raise ValueError("research request is required")
    v1_1_requested = "mode" in request
    normalized = domain.normalize_request(
        request.get("ticker"),
        request.get("years", 4),
        request.get("as_of"),
        request.get("mode") or "research",
    )
    normalized.update({key: value for key, value in request.items() if key not in normalized})
    repository = (dependencies or {}).get("repository", default_repository)
    if v1_1_requested and not _registry_supported(repository):
        raise ValueError("v1_1 research modes require registry persistence")
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
    extra_dependencies = dict(dependencies or {})
    config_args = extra_dependencies.pop("config_args", None)
    context.update(_default_dependencies(context["db_path"], context["http_client"], config_args))
    context.update(extra_dependencies)
    context["warnings"].extend(context.get("inference_warnings", []))
    if context.get("inference_warnings"):
        context["next_actions"].append("configure_catalyst_llm")
    aliases = {
        "discover": "discover_sources",
        "inspect_snapshot": "build_snapshot",
        "generate": "generate_adapter",
        "validate": "validate_candidate",
        "validate_active": "validate_active_adapter",
        "execute": "execute_adapter",
        "classify": "classify_observations",
        "stats": "calculate_statistics",
        "normalize": "normalize_observations",
    }
    for alias, target in aliases.items():
        if alias in context and target not in extra_dependencies:
            context[target] = context[alias]
    job = None
    try:
        job = _repo_call(context, "create_job", normalized, now=_now(context))
        context["job"] = job
        _repo_call(context, "start_job", job["job_id"], _iso(context))
        company = await _resolve(context)
        context["company"] = company
        _progress(context, "company_resolved", ticker=normalized["ticker"])
        _repo_call(context, "update_resolved_company", company=company, job_id=job["job_id"])
        if v1_1_requested:
            await _run_v1_1_workflow(context, company, job)
        else:
            await _run_legacy_workflow(context, company, normalized, repository, job)
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

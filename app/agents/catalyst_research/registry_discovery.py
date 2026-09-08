import hashlib
import inspect
import re
import sqlite3
from collections.abc import Mapping
from datetime import UTC, datetime
from html.parser import HTMLParser
from urllib.parse import urljoin

from app.agents.catalyst_research import registry as registry_state
from app.agents.catalyst_research.domain import canonicalize_public_url, url_host
from app.agents.catalyst_research.extraction.feeds import fetch_feed
from app.agents.catalyst_research.extraction.pages import fetch_html_page
from app.agents.catalyst_research.prompts import registry_selection_prompt
from app.agents.catalyst_research.providers.base import VALID_REASON_CODES, SearchProviderError
from app.agents.catalyst_research.schemas import RegistrySelectionResponse


_DISCOVERY_CHANNELS = ("press_releases", "events_presentations", "earnings_results")
_CHANNEL_QUERY_TERMS = {
    "press_releases": "press releases news feed",
    "events_presentations": "events presentations webcast",
    "earnings_results": "quarterly earnings financial results",
}
_FEED_ENDPOINT_TYPES = frozenset({"rss", "atom"})
_SEARCH_PURPOSE = "source_discovery"
_RESULT_LIMIT = 10
_TRANSPORT_OUTCOMES = frozenset(
    {
        "authentication_failed",
        "rate_limited",
        "timeout",
        "provider_error",
        "empty_results",
        "malformed_response",
        "not_configured",
    }
)
_THIRD_PARTY_HOST_MARKERS = (
    "bloomberg.",
    "businesswire.",
    "facebook.",
    "globenewswire.",
    "linkedin.",
    "marketwatch.",
    "prnewswire.",
    "reuters.",
    "seekingalpha.",
    "stockanalysis.",
    "yahoo.",
    "feedly.",
    "news.google",
)
_COMMON_IDENTITY_WORDS = {
    "and",
    "company",
    "corp",
    "corporation",
    "inc",
    "incorporated",
    "international",
    "limited",
    "ltd",
    "plc",
    "the",
}


class _AlternateLinkParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.feed_links = []

    def handle_starttag(self, tag, attrs):
        if tag.casefold() != "link":
            return
        values = {key.casefold(): (value or "") for key, value in attrs if key}
        rel = {part.strip().casefold() for part in values.get("rel", "").split() if part.strip()}
        if "alternate" not in rel:
            return
        feed_type = values.get("type", "").strip().casefold()
        href = values.get("href", "").strip()
        if feed_type in {"application/rss+xml", "application/atom+xml"} and href:
            self.feed_links.append(("atom" if feed_type == "application/atom+xml" else "rss", href))


def _company_parts(company):
    if not isinstance(company, Mapping):
        raise ValueError("company identity is required")
    name = " ".join(
        re.sub(r"[^A-Za-z0-9 .&-]", " ", str(company.get("company_name") or company.get("name") or "")).split()
    )[:120]
    ticker = re.sub(r"[^A-Za-z0-9.-]", "", str(company.get("ticker") or "").upper())[:24]
    if not name and not ticker:
        raise ValueError("company identity is required")
    return name, ticker


def _identity_tokens(company):
    name, ticker = _company_parts(company)
    tokens = {
        token.casefold()
        for token in re.findall(r"[A-Za-z0-9]+", name)
        if token.casefold() not in _COMMON_IDENTITY_WORDS and len(token) >= 3
    }
    if ticker:
        tokens.add(ticker.casefold())
    return tokens


def _has_identity_evidence(company, rows):
    tokens = _identity_tokens(company)
    haystack = " ".join(
        str(row.get(key) or "")
        for row in rows
        for key in ("title", "snippet")
    ).casefold()
    return bool(tokens) and any(re.search(rf"\b{re.escape(token)}\b", haystack) for token in tokens)


def _is_third_party(host):
    return any(marker in host for marker in _THIRD_PARTY_HOST_MARKERS)


def _repo_call(repository, method_name, *args, connection=None, **kwargs):
    method = getattr(repository, method_name, None)
    if method is None:
        raise ValueError(f"repository method {method_name} is unavailable")
    try:
        parameters = list(inspect.signature(method).parameters.values())
    except (TypeError, ValueError):
        parameters = []
    first = parameters[0].name if parameters else ""
    if first in {"con", "connection"}:
        if connection is None:
            raise ValueError("repository connection is required")
        return method(connection, *args, **kwargs)
    return method(*args, **kwargs)


def _bounded_request_id(value):
    if not isinstance(value, str) or not value.strip():
        return None
    cleaned = " ".join(value.split())[:200]
    return re.sub(r"(?i)(api[ _-]?key|token|secret|authorization)\s*[:=]?\s*\S+", "[redacted]", cleaned)


def _discovery_queries(company, channels):
    name, ticker = _company_parts(company)
    identity = name or ticker
    return [
        (
            channel,
            f"{identity} {ticker} official investor relations {_CHANNEL_QUERY_TERMS[channel]}".strip()[:240],
        )
        for channel in channels
    ]


def _normalize_rows(raw_rows, query, provider_name, ids_by_url):
    rows = []
    unsafe_count = 0
    for raw in raw_rows:
        if not isinstance(raw, Mapping) or not raw.get("url"):
            raise SearchProviderError("malformed_response", "search provider returned malformed results")
        try:
            canonical = canonicalize_public_url(" ".join(str(raw.get("url") or "").split())[:2000])
        except ValueError:
            unsafe_count += 1
            continue
        if canonical not in ids_by_url:
            ids_by_url[canonical] = len(ids_by_url) + 1
        rows.append(
            {
                "result_id": ids_by_url[canonical],
                "query": query,
                "provider": provider_name,
                "title": " ".join(str(raw.get("title") or "").split())[:500],
                "snippet": " ".join(str(raw.get("snippet") or "").split())[:1000],
                "url": canonical,
                "provider_rank": raw.get("provider_rank") if isinstance(raw.get("provider_rank"), int) else None,
                "metadata": {},
            }
        )
    return rows, unsafe_count


def detect_feed_links(html_text, page_url):
    if not isinstance(html_text, str) or not html_text.strip():
        raise ValueError("page html is required")
    canonical_page = canonicalize_public_url(page_url)
    page_host = url_host(canonical_page)
    parser = _AlternateLinkParser()
    parser.feed(html_text)
    discovered = []
    seen = set()
    for endpoint_type, href in parser.feed_links:
        try:
            feed_url = canonicalize_public_url(urljoin(canonical_page, href))
        except ValueError:
            continue
        if url_host(feed_url) != page_host or feed_url in seen:
            continue
        seen.add(feed_url)
        discovered.append({"endpoint_type": endpoint_type, "url": feed_url, "domain": page_host})
    return discovered


def _probe_feed(url, endpoint_type, *, http_client, approved_domains, resolver):
    probe = {
        "endpoint_id": f"cse_probe_{hashlib.sha256(url.encode()).hexdigest()[:12]}",
        "endpoint_type": endpoint_type,
        "url": url,
    }
    return fetch_feed(probe, http_client=http_client, approved_domains=approved_domains, resolver=resolver)


def _activate_feed(endpoint, *, http_client, approved_domains, resolver):
    parsed = _probe_feed(
        endpoint["url"],
        endpoint["endpoint_type"],
        http_client=http_client,
        approved_domains=approved_domains,
        resolver=resolver,
    )
    now = datetime.now(UTC).isoformat()
    activated = dict(endpoint)
    activated["endpoint_type"] = parsed["format"]
    activated["status"] = "active"
    activated["last_checked_at"] = now
    activated["last_success_at"] = now
    activated["last_item_at"] = parsed["newest_item_at"]
    activated["feed_check"] = {
        "outcome": "success_new" if parsed["item_count"] else "success_empty",
        "item_count": parsed["item_count"],
        "new_item_count": 0,
        "newest_item_at": parsed["newest_item_at"],
        "content_hash": parsed["content_hash"],
        "checked_at": now,
    }
    return activated


async def _select_endpoints(company, channel, rows, *, llm_client, model):
    if llm_client is None or not model or not rows:
        return [], None
    try:
        response = await llm_client.responses.parse(
            model=model,
            input=registry_selection_prompt(company, rows),
            text_format=RegistrySelectionResponse,
        )
        payload = getattr(response, "output_parsed", None)
        if not isinstance(payload, RegistrySelectionResponse):
            payload = RegistrySelectionResponse.model_validate(
                payload.model_dump(mode="json") if hasattr(payload, "model_dump") else payload
            )
        return [item for item in payload.endpoints if item.channel == channel], None
    except Exception:
        return [], "catalyst_llm_request_failed"


def _validate_selection(selection, rows_by_id, company):
    url = None
    host = None
    if selection.url:
        try:
            url = canonicalize_public_url(selection.url)
        except ValueError:
            return None, "selected url is unsafe"
        host = url_host(url)
        if host != selection.domain and not host.endswith(f".{selection.domain}"):
            return None, "selected url host does not match the selected domain"
    if _is_third_party(selection.domain) or (host is not None and _is_third_party(host)):
        return None, "third-party source is not an official registry endpoint"
    evidence_rows = [rows_by_id[item] for item in selection.evidence_result_ids if item in rows_by_id]
    if len(evidence_rows) != len(selection.evidence_result_ids):
        return None, "selection references unavailable evidence"
    if url is not None and not any(
        row.get("url") == url for row in evidence_rows
    ):
        return None, "selected url is not in current evidence"
    if not _has_identity_evidence(company, evidence_rows):
        return None, "company identity is not established by search evidence"
    return (
        {
            "channel": selection.channel,
            "endpoint_type": selection.endpoint_type,
            "url": url,
            "domain": selection.domain,
            "status": "unverified",
            "confidence": selection.confidence,
            "evidence_result_ids": list(selection.evidence_result_ids),
            "discovery_method": "model",
            "reason": selection.reason,
        },
        None,
    )


def _rejected_source(ticker, channel, url, reason, discovery_method):
    return {
        "ticker": ticker,
        "source_type": channel,
        "url": str(url or ""),
        "acceptance_status": "rejected",
        "verification_reason": reason,
        "discovery_method": discovery_method if discovery_method in {"search", "manual"} else "search",
        "checked_at": datetime.now(UTC).isoformat(),
    }


def _save_rejected_sources(repository, connection, job_id, ticker, rejected_sources):
    for source in rejected_sources:
        try:
            _repo_call(
                repository,
                "save_source",
                {**source, "job_id": job_id, "ticker": ticker},
                connection=connection,
            )
        except ValueError:
            continue


async def discover_registry(
    company,
    *,
    router,
    llm_client,
    model,
    repository,
    job_id,
    connection,
    http_client,
    overrides=None,
    resolver=None,
) -> dict:
    name, ticker = _company_parts(company)
    if not ticker:
        raise ValueError("company ticker is required")
    if not job_id:
        raise ValueError("job id is required")
    if overrides is not None and not isinstance(overrides, Mapping):
        raise ValueError("overrides are invalid")

    existing_registry = _repo_call(repository, "load_company_registry", ticker, connection=connection)
    existing_endpoints = _repo_call(repository, "load_source_endpoints", ticker, connection=connection)

    if existing_registry and not overrides and registry_state.registry_ready(existing_registry, existing_endpoints):
        return {
            "status": "unchanged",
            "registry": existing_registry,
            "endpoints": existing_endpoints,
            "warnings": [],
            "next_actions": [],
            "provider_provenance": [],
        }

    warnings = []
    next_actions = []
    provider_provenance = []
    accepted = []
    rejected_sources = []
    ids_by_url = {}
    llm_failed = False

    override_channels = set()
    for channel, raw_url in (overrides or {}).items():
        if channel not in _DISCOVERY_CHANNELS:
            warnings.append("manual override channel was ignored")
            continue
        override_channels.add(channel)
        if not isinstance(raw_url, str):
            raise ValueError("manual override url is invalid")
        try:
            canonical = canonicalize_public_url(raw_url)
        except ValueError:
            rejected_sources.append(_rejected_source(ticker, channel, raw_url, "manual override url is unsafe", "manual"))
            warnings.append("manual override url is unsafe")
            continue
        host = url_host(canonical)
        candidate = {
            "channel": channel,
            "endpoint_type": "rss",
            "url": canonical,
            "domain": host,
            "status": "unverified",
            "confidence": "high",
            "evidence_result_ids": [],
            "discovery_method": "manual",
            "reason": "manual override",
        }
        try:
            accepted.append(_activate_feed(candidate, http_client=http_client, approved_domains=[host], resolver=resolver))
        except ValueError:
            candidate["endpoint_type"] = "search_domain"
            accepted.append(candidate)

    channels_to_search = [channel for channel in _DISCOVERY_CHANNELS if channel not in override_channels]
    for channel, query in _discovery_queries(company, channels_to_search):
        accepted_for_channel = False
        for provider in router.provider_chain():
            started_at = datetime.now(UTC).isoformat()
            outcome = "provider_error"
            diagnostics = {}
            provider_rows = []
            try:
                raw_rows = await provider.search(query, limit=_RESULT_LIMIT)
                if not isinstance(raw_rows, list):
                    raise SearchProviderError("malformed_response", "search provider returned malformed results")
                provider_rows, unsafe_count = _normalize_rows(raw_rows, query, provider.name, ids_by_url)
                diagnostics["result_ids"] = [row["result_id"] for row in provider_rows]
                if unsafe_count:
                    diagnostics["rejected_unsafe_count"] = unsafe_count
                outcome = "candidate_results" if provider_rows else ("rejected" if unsafe_count else "empty_results")
            except SearchProviderError as exc:
                outcome = exc.reason_code if exc.reason_code in VALID_REASON_CODES else "provider_error"
                diagnostics = {"reason": outcome}
                if exc.disable_provider:
                    router.disable(provider.name)
                    warnings.append(f"{provider.name} was disabled for this process run")
            except Exception:
                outcome = "provider_error"
                diagnostics = {"reason": "search provider request failed"}
            completed_at = datetime.now(UTC).isoformat()
            request_id = _bounded_request_id(getattr(provider, "last_request_id", None))
            attempt = {
                "job_id": job_id,
                "provider": provider.name,
                "query": query,
                "requested_limit": _RESULT_LIMIT,
                "started_at": started_at,
                "completed_at": completed_at,
                "outcome": outcome,
                "diagnostics": diagnostics,
                "provider_request_id": request_id,
                "search_purpose": _SEARCH_PURPOSE,
            }
            attempt_id = _repo_call(repository, "record_search_attempt", attempt, connection=connection)
            if provider_rows:
                _repo_call(repository, "record_search_results", job_id, attempt_id, provider_rows, connection=connection)
            channel_selections = []
            if provider_rows:
                channel_selections, selection_warning = await _select_endpoints(
                    company, channel, provider_rows, llm_client=llm_client, model=model
                )
                if selection_warning:
                    warnings.append(selection_warning)
                    llm_failed = True
                outcome = "accepted" if channel_selections else "rejected"
            if hasattr(repository, "update_search_attempt"):
                _repo_call(
                    repository,
                    "update_search_attempt",
                    attempt_id,
                    outcome=outcome,
                    diagnostics=diagnostics,
                    completed_at=completed_at,
                    provider_request_id=request_id,
                    connection=connection,
                )
            provider_provenance.append(
                {
                    "provider": provider.name,
                    "query": query,
                    "outcome": outcome,
                    "provider_request_id": request_id,
                    "result_ids": diagnostics.get("result_ids", []),
                }
            )
            if channel_selections:
                rows_by_id = {row["result_id"]: row for row in provider_rows}
                for selection in channel_selections:
                    endpoint, reason = _validate_selection(selection, rows_by_id, company)
                    if endpoint is None:
                        rejected_sources.append(_rejected_source(ticker, channel, selection.url or selection.domain, reason, "search"))
                        warnings.append(f"{channel} registry candidate was rejected")
                        continue
                    accepted.append(endpoint)
                accepted_for_channel = True
                break
        if not accepted_for_channel and not router.provider_chain():
            warnings.append("search provider chain is unavailable")
            break

    official_domains = {endpoint["domain"] for endpoint in accepted}
    official_domains.update(url_host(endpoint["url"]) for endpoint in accepted if endpoint.get("url"))

    validated = []
    for endpoint in accepted:
        if endpoint["endpoint_type"] in _FEED_ENDPOINT_TYPES and endpoint.get("url") and endpoint["status"] != "active":
            try:
                validated.append(
                    _activate_feed(endpoint, http_client=http_client, approved_domains=sorted(official_domains), resolver=resolver)
                )
            except ValueError:
                rejected_sources.append(
                    _rejected_source(ticker, endpoint["channel"], endpoint["url"], "feed validation failed", endpoint["discovery_method"])
                )
                warnings.append(f"{endpoint['channel']} feed candidate failed validation")
                continue
        else:
            validated.append(endpoint)
    accepted = validated

    known_feed_urls = {
        endpoint["url"] for endpoint in accepted if endpoint.get("url") and endpoint["endpoint_type"] in _FEED_ENDPOINT_TYPES
    }
    html_discovered = []
    for endpoint in list(accepted):
        if endpoint["endpoint_type"] in _FEED_ENDPOINT_TYPES or not endpoint.get("url"):
            continue
        page_host = url_host(endpoint["url"])
        try:
            page = fetch_html_page(endpoint["url"], http_client=http_client, allowed_hosts=[page_host], resolver=resolver)
        except ValueError:
            warnings.append(f"{endpoint['channel']} official page fetch failed")
            continue
        for link in detect_feed_links(page["html"], page["final_url"]):
            if link["url"] in known_feed_urls or any(item["url"] == link["url"] for item in html_discovered):
                continue
            candidate = {
                "channel": endpoint["channel"],
                "endpoint_type": link["endpoint_type"],
                "url": link["url"],
                "domain": link["domain"],
                "status": "unverified",
                "confidence": "medium",
                "evidence_result_ids": [],
                "discovery_method": "html",
                "reason": "feed link discovered on an accepted official page",
            }
            try:
                activated = _activate_feed(
                    candidate,
                    http_client=http_client,
                    approved_domains=sorted(official_domains | {link["domain"]}),
                    resolver=resolver,
                )
            except ValueError:
                rejected_sources.append(_rejected_source(ticker, endpoint["channel"], link["url"], "feed validation failed", "search"))
                warnings.append(f"{endpoint['channel']} discovered feed failed validation")
                continue
            html_discovered.append(activated)
            known_feed_urls.add(link["url"])
    accepted.extend(html_discovered)

    deduped = []
    seen_identity = set()
    for endpoint in accepted:
        identity = (
            endpoint["channel"],
            endpoint["endpoint_type"],
            (endpoint.get("url") or "").casefold() or endpoint["domain"],
        )
        if identity in seen_identity:
            continue
        seen_identity.add(identity)
        deduped.append(endpoint)
    accepted = deduped

    _save_rejected_sources(repository, connection, job_id, ticker, rejected_sources)

    if not accepted:
        only_transport_failures = bool(provider_provenance) and all(
            item["outcome"] in _TRANSPORT_OUTCOMES for item in provider_provenance
        )
        status = "search_unavailable" if only_transport_failures else "insufficient"
        if status == "search_unavailable":
            next_actions.append("configure_catalyst_search_provider")
        next_actions.append("provide a verified official source override")
        if llm_failed:
            next_actions.append("configure_catalyst_llm")
        return {
            "status": status,
            "registry": existing_registry,
            "endpoints": existing_endpoints,
            "warnings": list(dict.fromkeys(warnings)),
            "next_actions": list(dict.fromkeys(next_actions)),
            "provider_provenance": provider_provenance,
        }

    domains = sorted(
        {endpoint["domain"] for endpoint in accepted}
        | {url_host(endpoint["url"]) for endpoint in accepted if endpoint.get("url")}
    )
    active_feed = any(
        endpoint["status"] == "active" and endpoint["endpoint_type"] in _FEED_ENDPOINT_TYPES for endpoint in accepted
    )
    registry_payload = {
        "ticker": ticker,
        "company_name": name or ticker,
        "cik": str(company.get("cik")) if company.get("cik") is not None else None,
        "official_domains": domains,
        "source_confidence": "high" if active_feed else "medium",
        "registry_version": (int(existing_registry["registry_version"]) + 1) if existing_registry else 1,
    }
    try:
        saved_registry = _repo_call(repository, "save_company_registry", registry_payload, connection=connection)
        saved_endpoints = []
        for endpoint in accepted:
            row = {
                "ticker": ticker,
                "channel": endpoint["channel"],
                "endpoint_type": endpoint["endpoint_type"],
                "url": endpoint.get("url"),
                "domain": endpoint["domain"],
                "status": endpoint["status"],
                "confidence": endpoint["confidence"],
            }
            for extra in ("last_checked_at", "last_success_at", "last_item_at"):
                if endpoint.get(extra):
                    row[extra] = endpoint[extra]
            saved = _repo_call(repository, "upsert_source_endpoint", row, connection=connection)
            saved_endpoints.append(
                {
                    **saved,
                    "evidence_result_ids": endpoint["evidence_result_ids"],
                    "discovery_method": endpoint["discovery_method"],
                    "reason": endpoint["reason"],
                }
            )
            if endpoint.get("feed_check"):
                _repo_call(
                    repository,
                    "record_endpoint_check",
                    {"endpoint_id": saved["endpoint_id"], "job_id": job_id, **endpoint["feed_check"]},
                    connection=connection,
                )
    except sqlite3.Error as exc:
        try:
            connection.rollback()
        except Exception:
            pass
        raise ValueError("registry persistence failed") from exc

    covered = {endpoint["channel"] for endpoint in accepted}
    status = "accepted" if covered == set(_DISCOVERY_CHANNELS) else "partial"
    if status != "accepted":
        next_actions.append("provide a verified official source override")
    if llm_failed:
        next_actions.append("configure_catalyst_llm")
    return {
        "status": status,
        "registry": saved_registry,
        "endpoints": saved_endpoints,
        "warnings": list(dict.fromkeys(warnings)),
        "next_actions": list(dict.fromkeys(next_actions)),
        "provider_provenance": provider_provenance,
    }

import hashlib
import json
import re
from collections.abc import Mapping
from datetime import date, datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from soupsieve import match as selector_matches

from app.agents.catalyst_research.adapters.executor import DEFAULT_LIMITS, execute_adapter
from app.agents.catalyst_research.adapters.schema import IRSourceAdapter
from app.agents.catalyst_research.domain import canonicalize_public_url, url_host, validate_redirect_chain


ADAPTER_VALIDATOR_VERSION = "adapter_validator_v1"
ADAPTER_EXECUTOR_VERSION = "adapter_executor_v1"
MAX_RESPONSE_BYTES = 2_000_000
_MAX_SNAPSHOT_HTML = 120_000
_EXCLUDED_TAGS = {"nav", "footer", "form", "aside", "iframe", "script", "style"}
_EXCLUDED_HINTS = {"banner", "consent", "cookie", "privacy", "terms"}
_HTML_ERROR_RE = re.compile(r"<[^>]*>")


class _LiveExecutionError(Exception):
    def __init__(self, cause, report):
        super().__init__(str(cause))
        self.report = report


def _as_adapter(adapter):
    if isinstance(adapter, IRSourceAdapter):
        return adapter
    try:
        return IRSourceAdapter.model_validate(adapter)
    except (TypeError, ValueError) as exc:
        raise ValueError("adapter is invalid") from exc


def _date(value, label):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} is required")
    try:
        return date.fromisoformat(value.strip())
    except ValueError as exc:
        raise ValueError(f"{label} is invalid") from exc


def _canonical_json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(value):
    return hashlib.sha256(_canonical_json(value).encode()).hexdigest()


def _error(value):
    message = str(value).replace("raw_html", "page").replace("structural_html", "page")
    message = _HTML_ERROR_RE.sub("", message)
    message = " ".join(message.split())
    return message[:240] or "validation failed"


def _report(source_hashes=None, page_hashes=None):
    return {
        "source_content_hashes": list(source_hashes or []),
        "page_content_hashes": list(page_hashes or []),
        "match_counts": {"items": 0, "titles": 0, "dates": 0, "urls": 0},
        "valid_observation_count": 0,
        "duplicate_count": 0,
        "parsed_date_formats": [],
        "pagination": {"type": "none", "pages": 0, "distinct_pages": True, "loop": False},
        "safety_failures": [],
        "limit_checks": {
            "within_bounds": True,
            "limits": dict(DEFAULT_LIMITS),
            "max_response_bytes": MAX_RESPONSE_BYTES,
            "observed_response_bytes": [],
            "response_bytes_within_bounds": True,
        },
        "repeatability": {"byte_equivalent": False},
        "errors": [],
    }


def _excluded_reason(item):
    for parent in [item, *item.parents]:
        if getattr(parent, "name", None) in _EXCLUDED_TAGS:
            return f"item is inside excluded {parent.name} region"
        attributes = parent.attrs or {}
        identity = " ".join(
            str(attributes.get(name, ""))
            for name in ("id", "class", "role", "aria-label")
        ).casefold()
        if any(hint in identity.split() or hint in identity for hint in _EXCLUDED_HINTS):
            return "item is inside excluded consent region"
    return None


def _field_value(node, field):
    selected = node if node.name and selector_matches(field.selector, node) else node.select_one(field.selector)
    if selected is None:
        raise ValueError("adapter selector did not match")
    if field.value_source == "text":
        value = selected.get_text(" ", strip=True)
    else:
        value = selected.get(field.attribute)
    if not isinstance(value, str) or not value.strip():
        raise ValueError("adapter field value is missing")
    return " ".join(value.split())


def _field_date(value, formats):
    for date_format in formats:
        try:
            return datetime.strptime(value, date_format).date(), date_format
        except ValueError:
            continue
    raise ValueError("adapter date value is invalid")


def _inspect_html(adapter, html, page_url, requested_start, requested_end, report):
    if not isinstance(html, str) or not html.strip():
        raise ValueError("page html is empty")
    if len(html) > _MAX_SNAPSHOT_HTML:
        raise ValueError("page exceeds validation bound")
    soup = BeautifulSoup(html, "html.parser")
    items = soup.select(adapter.extraction.item_selector)
    report["match_counts"]["items"] += len(items)
    if not items:
        raise ValueError("adapter item selector did not match")
    observations = []
    seen = set()
    formats = set()
    for item in items:
        excluded = _excluded_reason(item)
        if excluded:
            report["safety_failures"].append(excluded)
            raise ValueError(excluded)
        date_value = _field_value(item, adapter.extraction.date)
        item_date, parsed_format = _field_date(date_value, adapter.extraction.date.formats)
        formats.add(parsed_format)
        report["match_counts"]["dates"] += 1
        title = _field_value(item, adapter.extraction.title)
        report["match_counts"]["titles"] += 1
        event_url = None
        if adapter.extraction.url is not None:
            href = _field_value(item, adapter.extraction.url)
            event_url = canonicalize_public_url(urljoin(page_url, href))
            if url_host(event_url) not in set(adapter.allowed_hosts):
                report["safety_failures"].append("event url host is not allowed")
                raise ValueError("event url host is not allowed")
            report["match_counts"]["urls"] += 1
        if requested_start <= item_date <= requested_end:
            key = (item_date.isoformat(), title.casefold(), event_url or "")
            if key in seen:
                report["duplicate_count"] += 1
                raise ValueError("duplicate observation key")
            seen.add(key)
            observations.append(
                {
                    "ticker": adapter.ticker,
                    "source_type": adapter.source_type,
                    "title": title,
                    "url": event_url,
                    "canonical_url": event_url,
                    "published_date": item_date.isoformat() if adapter.source_type == "press_releases" else None,
                    "event_date": item_date.isoformat() if adapter.source_type == "events_presentations" else None,
                    "count_date": item_date.isoformat(),
                }
            )
    report["parsed_date_formats"] = sorted(set(report["parsed_date_formats"]) | formats)
    report["valid_observation_count"] += len(observations)
    return observations


def _snapshot_page(adapter, snapshot):
    if not isinstance(snapshot, Mapping):
        raise ValueError("snapshot is required")
    html = snapshot.get("structural_html")
    if not isinstance(html, str) or not html.strip():
        raise ValueError("bounded structural snapshot is required")
    if len(html) > _MAX_SNAPSHOT_HTML:
        raise ValueError("bounded structural snapshot exceeds validation bound")
    if snapshot.get("truncated", False):
        raise ValueError("snapshot is truncated")
    content_type = snapshot.get("content_type") or "text/html"
    if not isinstance(content_type, str) or content_type.split(";", 1)[0].strip().casefold() not in {"text/html", "application/xhtml+xml"}:
        raise ValueError("snapshot content type is not html")
    requested_url = canonicalize_public_url(str(snapshot.get("requested_url") or adapter.source_url))
    final_url = canonicalize_public_url(str(snapshot.get("final_url") or requested_url))
    expected_url = canonicalize_public_url(str(adapter.source_url))
    if requested_url != expected_url:
        raise ValueError("snapshot requested url does not match source url")
    allowed_hosts = set(adapter.allowed_hosts)
    if url_host(requested_url) not in allowed_hosts or url_host(final_url) not in allowed_hosts:
        raise ValueError("snapshot url host is not allowed")
    redirect_chain = snapshot.get("redirect_chain")
    if redirect_chain is None:
        redirect_chain = [requested_url] if requested_url == final_url else [requested_url, final_url]
    if not isinstance(redirect_chain, list) or not redirect_chain:
        raise ValueError("snapshot redirect chain is required")
    normalized_chain = validate_redirect_chain(redirect_chain)
    if normalized_chain[0] != requested_url or normalized_chain[-1] != final_url:
        raise ValueError("snapshot redirect chain is inconsistent")
    if any(url_host(url) not in allowed_hosts for url in normalized_chain):
        raise ValueError("snapshot redirect host is not allowed")
    response_bytes = snapshot.get("response_bytes")
    if response_bytes is not None and (isinstance(response_bytes, bool) or not isinstance(response_bytes, int) or response_bytes < len(html.encode())):
        raise ValueError("snapshot response bytes are inconsistent")
    supplied_hash = snapshot.get("content_hash")
    computed_hash = hashlib.sha256(html.encode()).hexdigest()
    if supplied_hash is not None and (not isinstance(supplied_hash, str) or supplied_hash != computed_hash):
        raise ValueError("snapshot content hash is invalid")
    return {
        "requested_url": requested_url,
        "final_url": final_url,
        "redirect_chain": normalized_chain,
        "content_type": content_type,
        "response_bytes": response_bytes or len(html.encode()),
        "truncated": bool(snapshot.get("truncated", False)),
        "html": html,
    }


def _record_response_size(page, report):
    if isinstance(page, str):
        html = page
        observed = len(html.encode())
    elif isinstance(page, Mapping):
        html = page.get("html")
        observed = page.get("response_bytes")
        if not isinstance(html, str) or not isinstance(observed, int) or isinstance(observed, bool):
            raise ValueError("page response bytes are invalid")
    else:
        raise ValueError("fetched page is invalid")
    actual = len(html.encode()) if isinstance(html, str) else 0
    report["limit_checks"]["observed_response_bytes"].append(observed)
    if observed < actual:
        report["limit_checks"]["response_bytes_within_bounds"] = False
        report["limit_checks"]["within_bounds"] = False
        raise ValueError("page response bytes are smaller than html")
    if observed > MAX_RESPONSE_BYTES:
        report["limit_checks"]["response_bytes_within_bounds"] = False
        report["limit_checks"]["within_bounds"] = False
        raise ValueError("page response bytes exceed maximum")
    return observed


def _execution_snapshot(adapter, snapshot, start, end):
    report = _report()
    snapshot_html = snapshot.get("structural_html") if isinstance(snapshot, Mapping) else None
    if isinstance(snapshot_html, str):
        report["source_content_hashes"] = [hashlib.sha256(snapshot_html.encode()).hexdigest()]
    try:
        if isinstance(snapshot_html, str):
            _record_response_size(
                {
                    "html": snapshot_html,
                    "response_bytes": snapshot.get("response_bytes", len(snapshot_html.encode())),
                },
                report,
            )
        page = _snapshot_page(adapter, snapshot)
        report["pagination"]["type"] = adapter.pagination.type
        observations = _inspect_html(adapter, page["html"], page["final_url"], start, end, report)
        report["pagination"]["pages"] = 1
        report["page_content_hashes"] = [hashlib.sha256(page["html"].encode()).hexdigest()]
        return observations, report
    except Exception as exc:
        raise _LiveExecutionError(exc, report) from exc


def _run_live(adapter, fetch_page, start, end, limits):
    pages = []
    report = _report()

    def recording_fetch(url):
        page = fetch_page(url)
        _record_response_size(page, report)
        pages.append(page)
        return page

    try:
        result = execute_adapter(
            adapter,
            fetch_page=recording_fetch,
            requested_start=start,
            requested_end=end,
            limits=limits,
        )
        report["page_content_hashes"] = result.get("content_hashes", [])
        report["pagination"] = {
            "type": adapter.pagination.type,
            "pages": result.get("page_count", 0),
            "distinct_pages": len(result.get("pages", [])) == len(set(result.get("pages", []))),
            "loop": result.get("truncation_reason") in {"repeated_url", "repeated_content"},
            "truncation_reason": result.get("truncation_reason"),
        }
        page_observations = []
        for page in pages:
            html = page.get("html") if isinstance(page, Mapping) else page
            page_url = page.get("final_url") if isinstance(page, Mapping) else None
            page_url = page_url or (page.get("requested_url") if isinstance(page, Mapping) else str(adapter.source_url))
            page_observations.append(_inspect_html(adapter, html, page_url, start, end, report))
        observation_keys = [
            {(row["count_date"], row["title"].casefold(), row["url"] or "") for row in observations}
            for observations in page_observations
        ]
        prior_keys = set()
        distinct_observations = True
        saw_distinct_observation = False
        for index, current_keys in enumerate(observation_keys):
            new_keys = current_keys - prior_keys
            if index > 0 and not new_keys:
                distinct_observations = False
            if new_keys:
                saw_distinct_observation = True
            prior_keys.update(current_keys)
        if len(observation_keys) > 1:
            distinct_observations = distinct_observations and saw_distinct_observation
        report["pagination"]["distinct_observations"] = distinct_observations
        report["limit_checks"]["within_bounds"] = result.get("truncation_reason") not in {"max_pages", "max_events", "max_elapsed_seconds", "response_truncated"}
        report["limit_checks"]["limits"] = dict(limits)
        report["limit_checks"]["within_bounds"] = report["limit_checks"]["within_bounds"] and report["limit_checks"]["response_bytes_within_bounds"]
        return result, report
    except Exception as exc:
        raise _LiveExecutionError(exc, report) from exc


def validate_candidate(adapter, snapshot, *, fetch_page, requested_start, requested_end, limits=None) -> dict:
    adapter = _as_adapter(adapter)
    if not callable(fetch_page):
        raise ValueError("fetch page is required")
    start = _date(requested_start, "requested start")
    end = _date(requested_end, "requested end")
    if start > end:
        raise ValueError("requested date range is invalid")
    bounds = dict(DEFAULT_LIMITS)
    if limits is not None:
        bounds.update(limits)
    report = _report()
    result = {"status": "failed", "observations": [], "errors": [], "report": report}
    try:
        first, first_report = _execution_snapshot(adapter, snapshot, start, end)
        second, second_report = _execution_snapshot(adapter, snapshot, start, end)
        first_bytes = _canonical_json(first).encode()
        second_bytes = _canonical_json(second).encode()
        report.update(first_report)
        report["repeatability"] = {
            "byte_equivalent": first_bytes == second_bytes,
            "first_hash": hashlib.sha256(first_bytes).hexdigest(),
            "second_hash": hashlib.sha256(second_bytes).hexdigest(),
        }
        if first_bytes != second_bytes:
            raise ValueError("snapshot observations are not byte-equivalent")
        live_result, live_report = _run_live(adapter, fetch_page, start, end, bounds)
        report["page_content_hashes"] = live_result.get("content_hashes", [])
        report["match_counts"] = live_report["match_counts"]
        report["valid_observation_count"] = live_result.get("item_count", 0)
        report["duplicate_count"] = live_report["duplicate_count"]
        report["parsed_date_formats"] = live_report["parsed_date_formats"]
        report["pagination"] = live_report["pagination"]
        report["safety_failures"] = live_report["safety_failures"]
        report["limit_checks"] = live_report["limit_checks"]
        if report["pagination"]["loop"]:
            raise ValueError("pagination loop detected")
        if not report["pagination"].get("distinct_observations", True):
            raise ValueError("pagination produced no distinct observations")
        if not report["limit_checks"]["within_bounds"]:
            raise ValueError("executor limits were reached")
        result["status"] = "passed"
        result["observations"] = live_result.get("observations", [])
    except Exception as exc:
        report = getattr(exc, "report", report)
        result["errors"] = [_error(exc)]
        report["errors"] = result["errors"]
        result["observations"] = []
        if not report["safety_failures"] and "region" in str(exc):
            report["safety_failures"] = [_error(exc)]
    report["validator_version"] = ADAPTER_VALIDATOR_VERSION
    report["executor_version"] = ADAPTER_EXECUTOR_VERSION
    result["report"] = report
    result["validator_version"] = ADAPTER_VALIDATOR_VERSION
    result["executor_version"] = ADAPTER_EXECUTOR_VERSION
    result["source_content_hashes"] = report["source_content_hashes"]
    result["page_content_hashes"] = report["page_content_hashes"]
    return result


def validate_active_adapter(adapter, *, fetch_page, requested_start, requested_end, limits=None) -> dict:
    adapter = _as_adapter(adapter)
    if not callable(fetch_page):
        raise ValueError("fetch page is required")
    start = _date(requested_start, "requested start")
    end = _date(requested_end, "requested end")
    if start > end:
        raise ValueError("requested date range is invalid")
    bounds = dict(DEFAULT_LIMITS)
    if limits is not None:
        bounds.update(limits)
    report = None
    try:
        result, report = _run_live(adapter, fetch_page, start, end, bounds)
        if report["pagination"]["loop"]:
            raise ValueError("pagination loop detected")
        if not report["pagination"].get("distinct_observations", True):
            raise ValueError("pagination produced no distinct observations")
        if not report["limit_checks"]["within_bounds"]:
            raise ValueError("executor limits were reached")
        status = "passed"
        observations = result.get("observations", [])
        errors = []
    except Exception as exc:
        report = getattr(exc, "report", None) or report or _report()
        report["safety_failures"] = [_error(exc)]
        report["pagination"]["type"] = adapter.pagination.type
        status = "stale"
        observations = []
        errors = [_error(exc)]
    report["validator_version"] = ADAPTER_VALIDATOR_VERSION
    report["executor_version"] = ADAPTER_EXECUTOR_VERSION
    report["errors"] = errors
    return {
        "status": status,
        "observations": observations if status == "passed" else [],
        "promotable_observations": observations if status == "passed" else [],
        "report": report,
        "errors": errors,
        "validator_version": ADAPTER_VALIDATOR_VERSION,
        "executor_version": ADAPTER_EXECUTOR_VERSION,
        "page_content_hashes": report["page_content_hashes"],
    }

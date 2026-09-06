import hashlib
import math
import time
from collections.abc import Mapping
from datetime import date, datetime
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup
from soupsieve import match as selector_matches

from app.agents.catalyst_research.adapters.schema import IRSourceAdapter
from app.agents.catalyst_research.domain import canonicalize_public_url, url_host, validate_redirect_chain


DEFAULT_LIMITS = {"max_pages": 40, "max_events": 2_000, "max_elapsed_seconds": 120}


def _parse_date(value, label):
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


def _positive_integer_limit(value, name):
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def _duration_limit(value, name):
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value) or value < 0:
        raise ValueError(f"{name} must be non-negative")
    return value


def _normalize_limits(limits):
    if limits is None:
        limits = {}
    if not isinstance(limits, Mapping):
        raise ValueError("limits are invalid")
    result = dict(DEFAULT_LIMITS)
    if "max_pages" in limits:
        result["max_pages"] = _positive_integer_limit(limits["max_pages"], "max pages")
    if "max_events" in limits:
        result["max_events"] = _positive_integer_limit(limits["max_events"], "max events")
    if "max_elapsed_seconds" in limits:
        result["max_elapsed_seconds"] = _duration_limit(limits["max_elapsed_seconds"], "max elapsed seconds")
    return result


def _page_payload(page, requested_url):
    if isinstance(page, str):
        html = page
        final_url = requested_url
        content_type = "text/html"
        truncated = False
        response_bytes = len(html.encode("utf-8"))
        redirect_chain = [requested_url]
    elif isinstance(page, Mapping):
        html = page.get("html")
        final_url = page.get("final_url") or page.get("requested_url") or requested_url
        content_type = page.get("content_type")
        if not isinstance(content_type, str) or content_type.split(";", 1)[0].strip().casefold() not in {"text/html", "application/xhtml+xml"}:
            raise ValueError("page content type is not html")
        truncated = page.get("truncated", False)
        if not isinstance(truncated, bool):
            raise ValueError("page truncation flag is invalid")
        response_bytes = page.get("response_bytes")
        if isinstance(response_bytes, bool) or not isinstance(response_bytes, int) or response_bytes < 0:
            raise ValueError("page response bytes are invalid")
        redirect_chain = page.get("redirect_chain")
        if not isinstance(redirect_chain, list) or not redirect_chain:
            raise ValueError("page redirect chain is required")
    else:
        raise ValueError("fetched page is invalid")
    if not isinstance(html, str) or not html.strip():
        raise ValueError("fetched page html is required")
    try:
        canonical_final_url = canonicalize_public_url(final_url)
    except ValueError as exc:
        raise ValueError("fetched page url is invalid") from exc
    try:
        canonical_chain = validate_redirect_chain(redirect_chain)
    except ValueError as exc:
        raise ValueError("page redirect chain is invalid") from exc
    if canonical_chain[0] != requested_url:
        raise ValueError("page redirect chain start is invalid")
    if canonical_chain[-1] != canonical_final_url:
        raise ValueError("page redirect chain final url is invalid")
    if not truncated and response_bytes < len(html.encode("utf-8")):
        raise ValueError("page response bytes are inconsistent")
    return html, canonical_final_url, hashlib.sha256(html.encode("utf-8")).hexdigest(), truncated, canonical_chain


def _ensure_host(url, allowed_hosts, label):
    try:
        host = url_host(url)
    except ValueError as exc:
        raise ValueError(f"{label} is invalid") from exc
    if host not in allowed_hosts:
        raise ValueError(f"{label} host is not allowed")


def _select_one(node, selector):
    if node.name and selector_matches(selector, node):
        return node
    return node.select_one(selector)


def _extract_value(node, field):
    selected = _select_one(node, field.selector)
    if selected is None:
        raise ValueError("adapter selector did not match")
    if field.value_source == "text":
        value = selected.get_text(" ", strip=True)
    else:
        value = selected.get(field.attribute)
    if not isinstance(value, str) or not value.strip():
        raise ValueError("adapter field value is missing")
    return " ".join(value.split())


def _parse_field_date(value, formats):
    for date_format in formats:
        try:
            return datetime.strptime(value, date_format).date()
        except ValueError:
            continue
    raise ValueError("adapter date value is invalid")


def _extract_observations(adapter, html, page_url, requested_start, requested_end):
    soup = BeautifulSoup(html, "html.parser")
    items = soup.select(adapter.extraction.item_selector)
    if not items:
        raise ValueError("adapter item selector did not match")
    observations = []
    all_dates = []
    for item in items:
        date_value = _extract_value(item, adapter.extraction.date)
        item_date = _parse_field_date(date_value, adapter.extraction.date.formats)
        all_dates.append(item_date)
        title = _extract_value(item, adapter.extraction.title)
        event_url = None
        if adapter.extraction.url is not None:
            href = _extract_value(item, adapter.extraction.url)
            event_url = canonicalize_public_url(urljoin(page_url, href))
            _ensure_host(event_url, set(adapter.allowed_hosts), "event url")
        if item_date < requested_start or item_date > requested_end:
            continue
        row = {
            "ticker": adapter.ticker,
            "source_type": adapter.source_type,
            "title": title,
            "url": event_url,
            "canonical_url": event_url,
            "published_date": item_date.isoformat() if adapter.source_type == "press_releases" else None,
            "event_date": item_date.isoformat() if adapter.source_type == "events_presentations" else None,
            "count_date": item_date.isoformat(),
        }
        observations.append(row)
    return observations, all_dates


def _next_url(adapter, soup, current_url, page_number):
    pagination = adapter.pagination
    if pagination.type == "none":
        return None
    if pagination.type == "next_link":
        node = soup.select_one(pagination.selector)
        if node is None:
            return None
        href = node.get("href")
        if not isinstance(href, str) or not href.strip():
            raise ValueError("next link href is missing")
        return canonicalize_public_url(urljoin(current_url, href))
    parsed = urlsplit(current_url)
    query = [(key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True) if key != pagination.parameter]
    query.append((pagination.parameter, str(page_number + 1)))
    return canonicalize_public_url(urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), "")))


def _initial_page(adapter):
    initial_url = canonicalize_public_url(str(adapter.source_url))
    if adapter.pagination.type != "page_parameter" or adapter.pagination.start is None:
        return initial_url, 0
    parsed = urlsplit(initial_url)
    query = [(key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True) if key != adapter.pagination.parameter]
    query.append((adapter.pagination.parameter, str(adapter.pagination.start)))
    initial_url = canonicalize_public_url(urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), "")))
    return initial_url, adapter.pagination.start - 1


def _execution_result(state):
    observations = []
    seen = set()
    for row in state["observations"]:
        key = (row["source_type"], row["count_date"], row["title"].casefold(), row["url"] or "")
        if key in seen:
            continue
        seen.add(key)
        observations.append(row)
    coverage_dates = [row["count_date"] for row in observations]
    return {
        "observations": observations,
        "pages": list(state["pages"]),
        "content_hashes": list(state["content_hashes"]),
        "coverage_start": min(coverage_dates) if coverage_dates else None,
        "coverage_end": max(coverage_dates) if coverage_dates else None,
        "boundary_reached": state["boundary_reached"],
        "archive_exhausted": state["archive_exhausted"],
        "truncation_reason": state["truncation_reason"],
        "page_count": len(state["pages"]),
        "item_count": len(observations),
    }


def execute_adapter(adapter, *, fetch_page, requested_start, requested_end, limits=None) -> dict:
    if not isinstance(adapter, IRSourceAdapter):
        try:
            adapter = IRSourceAdapter.model_validate(adapter)
        except (TypeError, ValueError) as exc:
            raise ValueError("adapter is invalid") from exc
    if not callable(fetch_page):
        raise ValueError("fetch page is required")
    start = _parse_date(requested_start, "requested start")
    end = _parse_date(requested_end, "requested end")
    if start > end:
        raise ValueError("requested date range is invalid")
    bounds = _normalize_limits(limits)
    initial_url, page_index = _initial_page(adapter)
    allowed_hosts = set(adapter.allowed_hosts)
    _ensure_host(initial_url, allowed_hosts, "source url")
    state = {
        "observations": [],
        "pages": [],
        "content_hashes": [],
        "visited_urls": set(),
        "visited_hashes": set(),
        "next_url": initial_url,
        "boundary_reached": False,
        "archive_exhausted": False,
        "truncation_reason": None,
        "started": time.monotonic(),
    }
    page_count = 0
    while state["next_url"] is not None:
        if page_count >= bounds["max_pages"]:
            state["truncation_reason"] = "max_pages"
            break
        if time.monotonic() - state["started"] >= bounds["max_elapsed_seconds"]:
            state["truncation_reason"] = "max_elapsed_seconds"
            break
        current_url = state["next_url"]
        _ensure_host(current_url, allowed_hosts, "page url")
        if current_url in state["visited_urls"]:
            state["truncation_reason"] = "repeated_url"
            break
        state["visited_urls"].add(current_url)
        html, final_url, content_hash, response_truncated, redirect_chain = _page_payload(fetch_page(current_url), current_url)
        for redirect_url in redirect_chain:
            _ensure_host(redirect_url, allowed_hosts, "page redirect")
        _ensure_host(final_url, allowed_hosts, "page redirect")
        if final_url in state["visited_urls"] and final_url != current_url:
            state["truncation_reason"] = "repeated_url"
            break
        state["visited_urls"].add(final_url)
        if content_hash in state["visited_hashes"]:
            state["truncation_reason"] = "repeated_content"
            break
        state["visited_hashes"].add(content_hash)
        page_count += 1
        page_index += 1
        state["pages"].append(final_url)
        state["content_hashes"].append(content_hash)
        if time.monotonic() - state["started"] >= bounds["max_elapsed_seconds"]:
            state["truncation_reason"] = "max_elapsed_seconds"
            break
        if response_truncated:
            state["truncation_reason"] = "response_truncated"
            break
        page_observations, all_dates = _extract_observations(adapter, html, final_url, start, end)
        if any(item <= start for item in all_dates):
            state["boundary_reached"] = True
        remaining_events = bounds["max_events"] - len(state["observations"])
        if len(page_observations) > remaining_events:
            state["observations"].extend(page_observations[:remaining_events])
            state["truncation_reason"] = "max_events"
            break
        state["observations"].extend(page_observations)
        if time.monotonic() - state["started"] >= bounds["max_elapsed_seconds"]:
            state["truncation_reason"] = "max_elapsed_seconds"
            break
        if state["boundary_reached"]:
            break
        soup = BeautifulSoup(html, "html.parser")
        next_url = _next_url(adapter, soup, final_url, page_index)
        if next_url is None:
            state["archive_exhausted"] = True
            break
        _ensure_host(next_url, allowed_hosts, "pagination url")
        state["next_url"] = next_url
    return _execution_result(state)

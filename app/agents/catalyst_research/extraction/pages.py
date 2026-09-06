from datetime import UTC, datetime
from collections.abc import Iterable

import httpx

from app.agents.catalyst_research.domain import (
    canonicalize_public_url,
    url_host,
    validate_redirect_chain,
)


_HTML_CONTENT_TYPES = {"text/html", "application/xhtml+xml"}


def _positive_integer(value, name):
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _normalized_allowed_hosts(allowed_hosts):
    if allowed_hosts is None:
        return None
    if isinstance(allowed_hosts, str) or not isinstance(allowed_hosts, Iterable):
        raise ValueError("allowed hosts are invalid")
    normalized = set()
    for value in allowed_hosts:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("allowed host is invalid")
        candidate = value.strip()
        if "://" in candidate:
            candidate = url_host(canonicalize_public_url(candidate))
        else:
            candidate = url_host(canonicalize_public_url(f"https://{candidate}"))
        normalized.add(candidate)
    return normalized


def _ensure_allowed_hosts(chain, allowed_hosts):
    if allowed_hosts is None:
        return
    for url in chain:
        if url_host(url) not in allowed_hosts:
            raise ValueError("page redirect host is not allowed")


def _content_type(response):
    value = response.headers.get("Content-Type", "")
    return value.split(";", 1)[0].strip().casefold()


def _decode_bounded(content, max_bytes):
    bounded = content[:max_bytes]
    encoding = "utf-8"
    try:
        text = bounded.decode(encoding, errors="ignore")
    except (LookupError, UnicodeError):
        text = bounded.decode("utf-8", errors="ignore")
    return text, len(bounded), len(content) > max_bytes


def fetch_html_page(url, *, http_client, allowed_hosts=None, resolver=None, max_bytes=2_000_000) -> dict:
    max_bytes = _positive_integer(max_bytes, "max bytes")
    requested_url = canonicalize_public_url(url)
    normalized_allowed_hosts = _normalized_allowed_hosts(allowed_hosts)
    try:
        response = http_client.request("GET", requested_url, browser=True)
    except httpx.ReadTimeout as exc:
        raise ValueError("page request timed out") from exc
    except httpx.HTTPError as exc:
        raise ValueError("page request failed") from exc

    chain = [str(item.url) for item in response.history] + [str(response.url)]
    try:
        normalized_chain = validate_redirect_chain(chain, resolver=resolver)
    except ValueError:
        raise
    _ensure_allowed_hosts(normalized_chain, normalized_allowed_hosts)
    final_url = normalized_chain[-1]
    content_type = _content_type(response)
    if content_type not in _HTML_CONTENT_TYPES:
        raise ValueError("page content type is not html")
    html, response_bytes, truncated = _decode_bounded(response.content, max_bytes)
    if not html.strip():
        raise ValueError("page html is empty")
    return {
        "requested_url": requested_url,
        "final_url": final_url,
        "content_type": content_type,
        "html": html,
        "response_bytes": response_bytes,
        "fetched_at": datetime.now(UTC).isoformat(),
        "truncated": truncated,
    }

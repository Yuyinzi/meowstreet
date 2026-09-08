from collections.abc import Iterable
from datetime import UTC, datetime
import ipaddress
import socket
from urllib.parse import urljoin

import httpx

from app.agents.catalyst_research.domain import (
    canonicalize_public_url,
    url_host,
    validate_redirect_chain,
)
from app.http_client import ResponseTooLargeError


_HTML_CONTENT_TYPES = {"text/html", "application/xhtml+xml"}
_DOH_URL = "https://dns.google/resolve"
_PROXY_FAKE_IP_NETWORK = ipaddress.ip_network("198.18.0.0/15")


def _resolve_with_doh(host, http_client):
    addresses = []
    try:
        for record_type, answer_type in (("A", 1), ("AAAA", 28)):
            response = http_client.request(
                "GET",
                _DOH_URL,
                params={"name": host, "type": record_type},
                headers={"Accept": "application/dns-json"},
                max_response_bytes=65_536,
            )
            payload = response.json()
            if payload.get("Status") != 0:
                continue
            addresses.extend(
                answer.get("data")
                for answer in payload.get("Answer", [])
                if isinstance(answer, dict) and answer.get("type") == answer_type and isinstance(answer.get("data"), str)
            )
    except (AttributeError, TypeError, ValueError, httpx.HTTPError) as exc:
        raise ValueError("url host could not be resolved") from exc
    if not addresses:
        raise ValueError("url host could not be resolved")
    return addresses


def _resolve_host(host, http_client):
    try:
        entries = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except OSError:
        return _resolve_with_doh(host, http_client)
    addresses = [entry[4][0] for entry in entries if entry and entry[4]]
    if not addresses:
        return _resolve_with_doh(host, http_client)
    try:
        parsed = [ipaddress.ip_address(address) for address in addresses]
    except ValueError:
        return addresses
    if parsed and all(address in _PROXY_FAKE_IP_NETWORK for address in parsed):
        return _resolve_with_doh(host, http_client)
    return addresses


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
    effective_resolver = resolver if resolver is not None else lambda host: _resolve_host(host, http_client)
    current_url = requested_url
    chain = []
    redirect_count = 0
    while True:
        normalized_current = validate_redirect_chain([current_url], resolver=effective_resolver)[0]
        _ensure_allowed_hosts([normalized_current], normalized_allowed_hosts)
        chain.append(normalized_current)
        try:
            response = http_client.request(
                "GET",
                normalized_current,
                browser=True,
                follow_redirects=False,
                max_response_bytes=max_bytes,
            )
        except httpx.TimeoutException as exc:
            raise ValueError("page request timed out") from exc
        except ResponseTooLargeError as exc:
            raise ValueError("page response exceeds maximum bytes") from exc
        except httpx.HTTPError as exc:
            raise ValueError("page request failed") from exc
        if not response.is_redirect:
            break
        if redirect_count >= 5:
            raise ValueError("page redirect limit exceeded")
        location = response.headers.get("Location")
        if not location:
            raise ValueError("page redirect location is missing")
        current_url = canonicalize_public_url(urljoin(normalized_current, location))
        redirect_count += 1

    final_url = chain[-1]
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
        "redirect_chain": chain,
    }

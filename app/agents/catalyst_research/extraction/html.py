import hashlib
import re
from collections.abc import Mapping
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Comment, NavigableString, Tag

from app.agents.catalyst_research.domain import canonicalize_public_url


SNAPSHOT_SCHEMA_VERSION = "catalyst_structural_snapshot_v1"
_UNSAFE_NODES = {"embed", "form", "iframe", "object", "script", "style", "template"}
_STABLE_ATTRIBUTES = {"aria-label", "class", "data-date", "datetime", "href", "id", "title"}
_WHITESPACE_RE = re.compile(r"\s+")


def _bounded(value, limit):
    return value[:limit]


def _validate_limit(value, name):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return value


def _clean_text(value):
    return _WHITESPACE_RE.sub(" ", value).strip()


def _canonical_href(value, base_url):
    if not isinstance(value, str) or not value.strip():
        return None
    absolute = urljoin(base_url, value.strip())
    try:
        return canonicalize_public_url(absolute)
    except ValueError:
        return None


def _remove_unsafe_nodes_and_attributes(soup, base_url):
    for node in list(soup.find_all(_UNSAFE_NODES)):
        node.decompose()
    for node in soup.find_all(string=lambda value: isinstance(value, Comment)):
        node.extract()
    for node in soup.find_all(True):
        attributes = {}
        for name, value in node.attrs.items():
            normalized_name = name.casefold()
            if normalized_name.startswith("on") or normalized_name not in _STABLE_ATTRIBUTES:
                continue
            if normalized_name == "href":
                href = _canonical_href(value, base_url)
                if href is None:
                    continue
                value = href
            elif isinstance(value, list):
                value = " ".join(str(item) for item in value)
            attributes[normalized_name] = str(value)
        node.attrs = {key: attributes[key] for key in sorted(attributes)}
        for child in list(node.children):
            if isinstance(child, NavigableString):
                normalized = _clean_text(str(child))
                if normalized:
                    child.replace_with(normalized)
                else:
                    child.extract()


def _normalized_text(soup):
    return _clean_text(soup.get_text(" ", strip=True))


def _heading_rows(soup):
    return [{"level": int(node.name[1]), "text": _clean_text(node.get_text(" ", strip=True))} for node in soup.find_all(re.compile(r"^h[1-6]$")) if _clean_text(node.get_text(" ", strip=True))]


def _link_rows(soup, max_links):
    rows = []
    for node in soup.find_all("a")[:max_links]:
        href = node.get("href")
        if not href:
            continue
        row = {"href": href, "text": _clean_text(node.get_text(" ", strip=True))}
        for name in ("aria-label", "class", "data-date", "datetime", "id", "title"):
            if node.get(name) is not None:
                row[name] = node.get(name)
        rows.append(row)
    return rows


def build_structural_snapshot(page, *, max_html_chars=120_000, max_text_chars=40_000, max_links=500) -> dict:
    if not isinstance(page, Mapping):
        raise ValueError("page is required")
    for name, value in (("max html chars", max_html_chars), ("max text chars", max_text_chars), ("max links", max_links)):
        _validate_limit(value, name)
    source_html = page.get("html")
    if not isinstance(source_html, str) or not source_html.strip():
        raise ValueError("page html is required")
    requested_url = page.get("requested_url")
    final_url = page.get("final_url")
    if not isinstance(requested_url, str) and not isinstance(final_url, str):
        raise ValueError("page url is required")
    requested_url = canonicalize_public_url(requested_url) if isinstance(requested_url, str) else None
    final_url = canonicalize_public_url(final_url) if isinstance(final_url, str) else requested_url
    base_url = final_url
    soup = BeautifulSoup(source_html, "html.parser")
    _remove_unsafe_nodes_and_attributes(soup, base_url)
    normalized_html = _bounded(str(soup), max_html_chars)
    normalized = {
        "title": _clean_text(soup.title.get_text(" ", strip=True)) if soup.title else "",
        "text": _bounded(_normalized_text(soup), max_text_chars),
        "headings": _heading_rows(soup),
        "links": _link_rows(soup, max_links),
    }
    return {
        "snapshot_schema_version": SNAPSHOT_SCHEMA_VERSION,
        "requested_url": requested_url,
        "final_url": final_url,
        "content_type": page.get("content_type"),
        "fetched_at": page.get("fetched_at"),
        "response_bytes": page.get("response_bytes"),
        "truncated": bool(page.get("truncated", False)),
        "structural_html": normalized_html,
        "normalized": normalized,
        "content_hash": hashlib.sha256(normalized_html.encode("utf-8")).hexdigest(),
    }

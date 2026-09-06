import hashlib
import re
from collections.abc import Mapping
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Comment, Doctype, NavigableString

from app.agents.catalyst_research.domain import canonicalize_public_url


SNAPSHOT_SCHEMA_VERSION = "catalyst_structural_snapshot_v1"
_UNSAFE_NODES = {"aside", "embed", "footer", "form", "iframe", "nav", "object", "script", "style", "template"}
_NOISE_HINTS = ("banner", "consent", "cookie")
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
    noise_nodes = []
    for node in soup.find_all(True):
        attributes = node.attrs or {}
        identity = " ".join(
            value
            for name in ("id", "class")
            for value in (attributes.get(name, []) if isinstance(attributes.get(name, []), list) else [attributes.get(name, "")])
        ).casefold()
        if any(hint in identity for hint in _NOISE_HINTS):
            noise_nodes.append(node)
    for node in noise_nodes:
        if node.parent is not None:
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


def _heading_rows(soup, max_text_chars, max_headings):
    return [
        {"level": int(node.name[1]), "text": _bounded(_clean_text(node.get_text(" ", strip=True)), max_text_chars)}
        for node in soup.find_all(re.compile(r"^h[1-6]$"))
        if _clean_text(node.get_text(" ", strip=True))
    ][:max_headings]


def _link_rows(soup, base_url, max_links):
    rows = []
    for node in soup.find_all("a"):
        href = _canonical_href(node.get("href"), base_url)
        if href is None:
            continue
        row = {"href": href, "text": _clean_text(node.get_text(" ", strip=True))}
        for name in ("aria-label", "class", "data-date", "datetime", "id", "title"):
            if node.get(name) is not None:
                row[name] = node.get(name)
        rows.append(row)
        if len(rows) >= max_links:
            break
    return rows


def _contains_protected(node, protected_nodes):
    return node in protected_nodes or any(item in protected_nodes for item in node.find_all(True))


def _remove_last_subtree(soup, protected_nodes):
    children = list(soup.children)
    meaningful = [
        child
        for child in children
        if not isinstance(child, (Doctype, NavigableString)) or str(child).strip()
    ]
    for child in reversed(meaningful):
        if isinstance(child, (Doctype, NavigableString)):
            if isinstance(child, Doctype):
                continue
            child.extract()
            return True
        if child in protected_nodes:
            if _remove_last_subtree(child, protected_nodes):
                return True
            continue
        if _contains_protected(child, protected_nodes):
            if _remove_last_subtree(child, protected_nodes):
                return True
            continue
        if len(meaningful) > 1 or child.name not in {"html", "body", "main"}:
            child.decompose()
            return True
        if _remove_last_subtree(child, protected_nodes):
            return True
        return False
    return False


def _protected_nodes(soup):
    protected = set()
    for name in ("html", "body", "main"):
        node = soup.find(name)
        if node is not None:
            protected.add(node)
    extraction_root = soup.find("main")
    if extraction_root is None:
        extraction_root = soup.find("body")
    if extraction_root is None:
        extraction_root = soup
    first_card = extraction_root.find(class_=lambda value: value and "event-card" in (value if isinstance(value, list) else [value]))
    if first_card is not None:
        protected.add(first_card)
    return protected


def _truncate_text_nodes(soup, max_html_chars, protected_nodes):
    nodes = [
        node
        for node in soup.find_all(string=True)
        if not isinstance(node, (Comment, Doctype)) and str(node)
    ]
    ordered = [
        node
        for node in reversed(nodes)
        if not any(node is descendant or node in descendant.descendants for descendant in protected_nodes)
    ]
    if len(ordered) < len(nodes):
        ordered.extend(node for node in reversed(nodes) if node not in ordered)
    for node in ordered:
        if len(str(soup)) <= max_html_chars:
            return True
        excess = len(str(soup)) - max_html_chars
        value = str(node)
        if excess >= len(value):
            node.extract()
        else:
            node.replace_with(value[:-excess])
    return len(str(soup)) <= max_html_chars


def _bounded_normalized_html(soup, max_html_chars):
    truncated = False
    protected_nodes = _protected_nodes(soup)
    while len(str(soup)) > max_html_chars and _remove_last_subtree(soup, protected_nodes):
        truncated = True
    if len(str(soup)) > max_html_chars:
        truncated = True
        if not _truncate_text_nodes(soup, max_html_chars, protected_nodes):
            raise ValueError("structural html budget is too small")
    return str(soup), truncated


def build_structural_snapshot(page, *, max_html_chars=120_000, max_text_chars=40_000, max_links=500, max_headings=100) -> dict:
    if not isinstance(page, Mapping):
        raise ValueError("page is required")
    for name, value in (("max html chars", max_html_chars), ("max text chars", max_text_chars), ("max links", max_links), ("max headings", max_headings)):
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
    normalized_html, structural_truncated = _bounded_normalized_html(soup, max_html_chars)
    normalized = {
        "title": _clean_text(soup.title.get_text(" ", strip=True)) if soup.title else "",
        "text": _bounded(_normalized_text(soup), max_text_chars),
        "headings": _heading_rows(soup, max_text_chars, max_headings),
        "links": _link_rows(soup, base_url, max_links),
    }
    return {
        "snapshot_schema_version": SNAPSHOT_SCHEMA_VERSION,
        "requested_url": requested_url,
        "final_url": final_url,
        "content_type": page.get("content_type"),
        "fetched_at": page.get("fetched_at"),
        "response_bytes": page.get("response_bytes"),
        "truncated": bool(page.get("truncated", False)) or structural_truncated,
        "structural_html": normalized_html,
        "normalized": normalized,
        "content_hash": hashlib.sha256(normalized_html.encode("utf-8")).hexdigest(),
    }

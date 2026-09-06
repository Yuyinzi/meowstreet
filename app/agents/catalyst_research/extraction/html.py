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
_CONTENT_HINTS = ("archive", "event", "investor", "ir", "news", "presentation", "press", "release")
_IRRELEVANT_CONTENT_HINTS = ("cookie", "consent", "legal", "privacy", "terms")
_ROOT_EXCLUDED_NODES = {"a", "h1", "h2", "h3", "h4", "h5", "h6", "time"}
_MAX_RELEVANCE_DATES = 6
_MAX_RELEVANCE_LINKS = 6
_MAX_RELEVANCE_REPEATED_ITEMS = 4
_WHITESPACE_RE = re.compile(r"\s+")
_WORD_RE = re.compile(r"[a-z0-9]+")


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
    return any(node is protected for protected in protected_nodes) or any(
        any(item is protected for protected in protected_nodes) for item in node.find_all(True)
    )


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
        if any(child is protected for protected in protected_nodes):
            if child.name in {"a", "h1", "h2", "h3", "h4", "h5", "h6", "time"}:
                continue
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


def _accepted_links(node, base_url):
    anchors = [node] if node.name == "a" else node.find_all("a")
    return [anchor for anchor in anchors if _canonical_href(anchor.get("href"), base_url)]


def _structural_identity(node):
    attributes = node.attrs or {}
    values = []
    for name in ("id", "class"):
        value = attributes.get(name)
        values.extend(value if isinstance(value, list) else [value])
    values.extend(heading.get_text(" ", strip=True) for heading in node.find_all(re.compile(r"^h[1-6]$"), limit=3))
    return _clean_text(" ".join(str(value) for value in values if value)).casefold()


def _date_evidence_count(node):
    date_nodes = node.find_all("time", limit=_MAX_RELEVANCE_DATES)
    dated_nodes = node.find_all(attrs={"data-date": True}, limit=_MAX_RELEVANCE_DATES)
    datetime_nodes = node.find_all(attrs={"datetime": True}, limit=_MAX_RELEVANCE_DATES)
    return min(_MAX_RELEVANCE_DATES, len(date_nodes) + len(dated_nodes) + len(datetime_nodes))


def _repeated_item_count(node):
    items = node.find_all({"article", "li"}, limit=_MAX_RELEVANCE_REPEATED_ITEMS)
    return min(_MAX_RELEVANCE_REPEATED_ITEMS, len(items))


def _content_root_score(node, base_url):
    identity = _structural_identity(node)
    identity_words = set(_WORD_RE.findall(identity))
    content_hint_count = sum(hint in identity_words for hint in _CONTENT_HINTS)
    irrelevant_hint_count = sum(hint in identity_words for hint in _IRRELEVANT_CONTENT_HINTS)
    date_count = _date_evidence_count(node)
    link_count = min(_MAX_RELEVANCE_LINKS, len(_accepted_links(node, base_url)))
    repeated_item_count = _repeated_item_count(node)
    heading_count = len(node.find_all(re.compile(r"^h[1-6]$"), limit=2))
    return (
        content_hint_count * 6
        - irrelevant_hint_count * 10
        + date_count * 3
        + link_count
        + max(repeated_item_count - 1, 0) * 4
        + heading_count
    )


def _generic_content_root(body, base_url):
    candidates = [
        node
        for node in body.find_all(True)
        if node.name not in _ROOT_EXCLUDED_NODES and _clean_text(node.get_text(" ", strip=True))
    ]
    candidates = [
        node
        for node in candidates
        if _accepted_links(node, base_url) or _date_evidence_count(node) or node.find(re.compile(r"^h[1-6]$"))
    ]
    return max(candidates, key=lambda node: _content_root_score(node, base_url), default=body)


def _protected_nodes(soup, base_url):
    protected = []
    for name in ("html", "body", "main"):
        node = soup.find(name)
        if node is not None:
            protected.append(node)
    extraction_root = soup.find("main")
    if extraction_root is None:
        body = soup.find("body")
        if body is not None:
            extraction_root = _generic_content_root(body, base_url)
    if extraction_root is None:
        extraction_root = soup
    if not any(extraction_root is node for node in protected):
        protected.append(extraction_root)
    first_card = extraction_root.find(class_=lambda value: value and "event-card" in (value if isinstance(value, list) else [value]))
    first_branch = first_card or extraction_root
    for name in ("h1", "h2", "h3", "h4", "h5", "h6", "time"):
        node = first_branch.find(name)
        if node is not None:
            protected.append(node)
            break
    first_link = _accepted_links(first_branch, base_url)
    if first_link:
        protected.append(first_link[0])
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
        if not any(
            node is protected or any(node is descendant for descendant in protected.descendants)
            for protected in protected_nodes
        )
    ]
    ordered.extend(
        node
        for node in reversed(nodes)
        if any(
            node is protected or any(node is descendant for descendant in protected.descendants)
            for protected in protected_nodes
        )
    )
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


def _bounded_normalized_html(soup, base_url, max_html_chars):
    truncated = False
    protected_nodes = _protected_nodes(soup, base_url)
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
    normalized_html, structural_truncated = _bounded_normalized_html(soup, base_url, max_html_chars)
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

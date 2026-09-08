import hashlib
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin
import xml.etree.ElementTree as ET

from app.agents.catalyst_research.domain import canonicalize_public_url, url_host
from app.agents.catalyst_research.extraction.pages import _fetch_redirected_document


_FEED_ENDPOINT_TYPES = {"rss", "atom"}
_FEED_CONTENT_TYPES = {"application/rss+xml", "application/atom+xml", "application/xml", "text/xml"}
_FEED_ACCEPT = "application/rss+xml, application/atom+xml, application/xml;q=0.9, text/xml;q=0.9, */*;q=0.1"
_DEFAULT_MAX_ITEMS = 500
_MAX_SUMMARY_CHARS = 500
_TAG_RE = re.compile(r"<[^>]+>")


def _local_name(tag):
    return tag.rsplit("}", 1)[-1].rsplit(":", 1)[-1].casefold()


def _child(element, *names):
    for node in element:
        if _local_name(node.tag) in names:
            return node
    return None


def _child_text(element, *names):
    node = _child(element, *names)
    if node is None:
        return None
    text = " ".join("".join(node.itertext()).split())
    return text or None


def _clean_summary(value):
    return " ".join(_TAG_RE.sub(" ", value or "").split())[:_MAX_SUMMARY_CHARS]


def _summary_text(element, *names):
    node = _child(element, *names)
    if node is None:
        return ""
    return _clean_summary("".join(node.itertext()))


def _parse_rss_datetime(value):
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def _parse_atom_datetime(value):
    if not value or not value.strip():
        return None
    cleaned = value.strip()
    try:
        parsed = datetime.fromisoformat(cleaned)
    except ValueError:
        try:
            parsed = datetime.fromisoformat(cleaned.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def _host_in_domains(host, domains):
    return any(host == domain or host.endswith(f".{domain}") for domain in domains)


def _entry_url(link, feed_url):
    if not link:
        return None
    try:
        return canonicalize_public_url(urljoin(feed_url, link))
    except ValueError:
        return None


def _rss_entry(item, feed_url, endpoint, approved_hosts):
    url = _entry_url(_child_text(item, "link"), feed_url)
    if url is None or not _host_in_domains(url_host(url), approved_hosts):
        return None
    published = _parse_rss_datetime(_child_text(item, "pubdate"))
    return {
        "external_guid": _child_text(item, "guid"),
        "title": _child_text(item, "title") or "",
        "url": url,
        "published_at": published,
        "summary": _summary_text(item, "description") or _summary_text(item, "encoded"),
        "discovery_method": endpoint["endpoint_type"],
        "endpoint_id": endpoint["endpoint_id"],
    }


def _atom_link(entry, feed_url):
    links = [node for node in entry if _local_name(node.tag) == "link"]
    alternates = [node for node in links if (node.get("rel") or "alternate").casefold() == "alternate"]
    for node in alternates or links:
        href = node.get("href")
        if href:
            return href
    return None


def _atom_entry(entry, feed_url, endpoint, approved_hosts):
    url = _entry_url(_atom_link(entry, feed_url), feed_url)
    if url is None or not _host_in_domains(url_host(url), approved_hosts):
        return None
    published = _parse_atom_datetime(_child_text(entry, "updated")) or _parse_atom_datetime(_child_text(entry, "published"))
    return {
        "external_guid": _child_text(entry, "id"),
        "title": _child_text(entry, "title") or "",
        "url": url,
        "published_at": published,
        "summary": _summary_text(entry, "summary") or _summary_text(entry, "content"),
        "discovery_method": endpoint["endpoint_type"],
        "endpoint_id": endpoint["endpoint_id"],
    }


def _descendants(element, name):
    matches = []
    for child in element:
        if _local_name(child.tag) == name:
            matches.append(child)
        matches.extend(_descendants(child, name))
    return matches


def _feed_format(root):
    name = _local_name(root.tag)
    if name == "rss":
        return "rss"
    if name == "feed":
        return "atom"
    raise ValueError("feed format is unsupported")


def _feed_items(root, feed_format, feed_url, endpoint, approved_hosts):
    entry_name = "item" if feed_format == "rss" else "entry"
    builder = _rss_entry if feed_format == "rss" else _atom_entry
    items = []
    for element in _descendants(root, entry_name):
        item = builder(element, feed_url, endpoint, approved_hosts)
        if item is not None:
            items.append(item)
    return items


def _dedupe_and_sort(items):
    ordered = sorted(
        items,
        key=lambda item: (
            -(item["published_at"].timestamp() if item["published_at"] is not None else 0.0),
            item["url"],
            item["title"],
        ),
    )
    unique = []
    seen = set()
    for item in ordered:
        keys = {("url", item["url"])}
        if item["external_guid"]:
            keys.add(("guid", item["external_guid"]))
        if keys & seen:
            continue
        seen |= keys
        unique.append(item)
    return unique


def _validate_endpoint(endpoint):
    if not isinstance(endpoint, Mapping):
        raise ValueError("endpoint is required")
    endpoint_id = endpoint.get("endpoint_id")
    if not isinstance(endpoint_id, str) or not endpoint_id.strip():
        raise ValueError("endpoint id is required")
    endpoint_type = endpoint.get("endpoint_type")
    if endpoint_type not in _FEED_ENDPOINT_TYPES:
        raise ValueError("endpoint type is invalid")
    raw_url = endpoint.get("url")
    raw_domain = endpoint.get("domain")
    if isinstance(raw_url, str) and raw_url.strip():
        feed_url = canonicalize_public_url(raw_url)
        domain = url_host(feed_url)
    elif isinstance(raw_domain, str) and raw_domain.strip():
        domain = raw_domain.strip().casefold()
        feed_url = canonicalize_public_url(f"https://{domain}/")
    else:
        raise ValueError("endpoint url is required")
    if isinstance(raw_domain, str) and raw_domain.strip():
        domain = raw_domain.strip().casefold()
    return {
        "endpoint_id": endpoint_id.strip(),
        "endpoint_type": endpoint_type,
        "url": feed_url,
        "domain": domain,
    }


def _approved_domains(approved_domains):
    if approved_domains is None:
        raise ValueError("approved domains are required")
    domains = set()
    for value in approved_domains:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("approved domain is invalid")
        domains.add(value.strip().casefold().rstrip("."))
    if not domains:
        raise ValueError("approved domains are required")
    return domains


def _public_item(item):
    published = item["published_at"]
    return {
        "external_guid": item["external_guid"],
        "title": item["title"],
        "url": item["url"],
        "published_at": published.isoformat() if published is not None else None,
        "summary": item["summary"],
        "discovery_method": item["discovery_method"],
        "endpoint_id": item["endpoint_id"],
    }


def parse_feed(xml_text, endpoint, *, max_items=_DEFAULT_MAX_ITEMS) -> dict:
    if not isinstance(xml_text, str) or not xml_text.strip():
        raise ValueError("feed xml is required")
    if isinstance(max_items, bool) or not isinstance(max_items, int) or max_items <= 0:
        raise ValueError("max items must be a positive integer")
    normalized_endpoint = _validate_endpoint(endpoint)
    try:
        root = ET.fromstring(xml_text.encode("utf-8"))
    except ET.ParseError as exc:
        raise ValueError("feed xml is invalid") from exc
    feed_format = _feed_format(root)
    approved_hosts = {normalized_endpoint["domain"], url_host(normalized_endpoint["url"])}
    items = _dedupe_and_sort(_feed_items(root, feed_format, normalized_endpoint["url"], normalized_endpoint, approved_hosts))
    bounded = items[:max_items]
    newest = next((item["published_at"] for item in bounded if item["published_at"] is not None), None)
    return {
        "format": feed_format,
        "items": [_public_item(item) for item in bounded],
        "item_count": len(bounded),
        "newest_item_at": newest.isoformat() if newest is not None else None,
        "content_hash": hashlib.sha256(xml_text.encode("utf-8")).hexdigest(),
        "final_url": normalized_endpoint["url"],
    }


def _content_type(response):
    value = response.headers.get("Content-Type", "")
    return value.split(";", 1)[0].strip().casefold()


def fetch_feed(endpoint, *, http_client, approved_domains, resolver=None, max_bytes=2_000_000) -> dict:
    normalized_endpoint = _validate_endpoint(endpoint)
    domains = _approved_domains(approved_domains)
    _requested_url, chain, response = _fetch_redirected_document(
        normalized_endpoint["url"],
        http_client=http_client,
        resolver=resolver,
        max_bytes=max_bytes,
        browser=False,
        headers={"Accept": _FEED_ACCEPT},
        error_prefix="feed",
    )
    for url in chain:
        if not _host_in_domains(url_host(url), domains):
            raise ValueError("feed redirect host is not allowed")
    content_type = _content_type(response)
    if content_type not in _FEED_CONTENT_TYPES:
        raise ValueError("feed content type is not xml")
    xml_text = response.content.decode("utf-8", errors="ignore")
    if not xml_text.strip():
        raise ValueError("feed body is empty")
    parsed = parse_feed(xml_text, endpoint, max_items=_DEFAULT_MAX_ITEMS)
    parsed["final_url"] = chain[-1]
    return parsed

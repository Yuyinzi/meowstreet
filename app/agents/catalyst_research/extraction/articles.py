import json
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

from bs4 import BeautifulSoup

from app.agents.catalyst_research.domain import _has_identity_evidence, _has_source_purpose, canonicalize_public_url, url_host
from app.agents.catalyst_research.extraction.pages import fetch_html_page


_VALID_CHANNELS = frozenset({"press_releases", "events_presentations", "earnings_results"})
_JSON_LD_ARTICLE_TYPES = frozenset({"article", "newsarticle", "blogposting", "report", "techarticle"})
_JSON_LD_DATE_KEYS = ("datepublished", "datecreated", "datemodified")
_MAX_JSON_LD_SCRIPTS = 8
_MAX_JSON_LD_CHARS = 100_000
_MAX_TITLE_CHARS = 500
_MAX_TEXT_CHARS = 20_000
_MAX_METADATA_HTML_CHARS = 2_000_000
_MIN_TEXT_CHARS = 20
_MAX_DATE_TEXT_CHARS = 60
_MAX_DATE_CONTAINERS = 12
_LIST_PAGE_DATE_MARKERS = 5
_HUMAN_DATE_FORMATS = ("%B %d, %Y", "%b %d, %Y", "%d %B %Y", "%d %b %Y")
_DATE_MARKER_TOKENS = ("date", "published", "pubdate")
_TITLE_PREFIX_SEPARATORS = (" - ", " | ", " — ", " – ")
_CORPORATE_TOKENS = frozenset(
    {"corp", "corporation", "inc", "incorporated", "ltd", "limited", "co", "company", "plc", "group", "holdings", "holding", "llc", "lp", "nv", "sa", "ag"}
)


def _name_anchor(value):
    tokens = re.sub(r"[^a-z0-9 ]", " ", str(value or "").casefold()).split()
    return " ".join(token for token in tokens if token not in _CORPORATE_TOKENS)


def strip_title_site_prefix(title, company):
    folded = _fold(title)
    if not folded or not isinstance(company, Mapping):
        return folded
    anchors = {
        anchor
        for anchor in (_name_anchor(company.get("company_name") or company.get("name")), _name_anchor(company.get("ticker")))
        if anchor
    }
    if not anchors:
        return folded
    split = None
    for separator in _TITLE_PREFIX_SEPARATORS:
        index = folded.find(separator)
        if index > 0 and (split is None or index < split[0]):
            split = (index, separator)
    if split is None:
        return folded
    index, separator = split
    if _name_anchor(folded[:index]) in anchors and folded[index + len(separator):].strip():
        return folded[index + len(separator):].strip()
    return folded


def _fold(value):
    return " ".join(str(value or "").split())


def _approved_domains(approved_domains):
    if approved_domains is None or isinstance(approved_domains, (str, bytes)):
        raise ValueError("approved domains are required")
    domains = set()
    for value in approved_domains:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("approved domain is invalid")
        domains.add(value.strip().casefold().rstrip("."))
    if not domains:
        raise ValueError("approved domains are required")
    return domains


def _host_in_domains(host, domains):
    return any(host == domain or host.endswith(f".{domain}") for domain in domains)


def _normalize_datetime(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        cleaned = _fold(value)
        if not cleaned:
            return None
        try:
            parsed = datetime.fromisoformat(cleaned.replace("Z", "+00:00"))
        except ValueError:
            parsed = None
        if parsed is None:
            try:
                parsed = parsedate_to_datetime(cleaned)
            except (TypeError, ValueError):
                parsed = None
        if parsed is None:
            for date_format in _HUMAN_DATE_FORMATS:
                try:
                    parsed = datetime.strptime(cleaned, date_format)
                    break
                except ValueError:
                    continue
            else:
                return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.isoformat()


def _flatten_json_ld(value):
    items = []
    if isinstance(value, Mapping):
        items.append(value)
        graph = value.get("@graph")
        if isinstance(graph, list):
            for entry in graph:
                items.extend(_flatten_json_ld(entry))
    elif isinstance(value, list):
        for entry in value:
            items.extend(_flatten_json_ld(entry))
    return items


def _json_ld_nodes(soup):
    nodes = []
    scripts = soup.find_all("script", attrs={"type": True})
    for script in scripts[:_MAX_JSON_LD_SCRIPTS]:
        type_value = script.get("type") or ""
        if "ld+json" not in type_value.casefold():
            continue
        text = script.string or script.get_text()
        if not text or len(text) > _MAX_JSON_LD_CHARS:
            continue
        try:
            payload = json.loads(text)
        except ValueError:
            continue
        nodes.extend(_flatten_json_ld(payload))
    return nodes


def _node_types(node):
    raw = node.get("@type")
    if isinstance(raw, str):
        return {raw.casefold()}
    if isinstance(raw, list):
        return {str(item).casefold() for item in raw if isinstance(item, str)}
    return set()


def _article_node(nodes):
    fallback = None
    for node in nodes:
        if _node_types(node) & _JSON_LD_ARTICLE_TYPES:
            return node
        if fallback is None and ("headline" in node or "datePublished" in node):
            fallback = node
    return fallback


def _node_value(node, *keys):
    lowered = {str(key).casefold(): value for key, value in node.items()}
    for key in keys:
        value = lowered.get(key)
        if isinstance(value, str) and value.strip():
            return _fold(value)
    return None


def _json_ld_url(node):
    raw = node.get("url")
    if isinstance(raw, Mapping):
        raw = raw.get("@id")
    if not isinstance(raw, str):
        raw = node.get("mainEntityOfPage")
        if isinstance(raw, Mapping):
            raw = raw.get("@id")
    if not isinstance(raw, str):
        return None
    return _fold(raw) or None


def _json_ld_metadata(soup):
    node = _article_node(_json_ld_nodes(soup))
    if node is None:
        return {"title": None, "published_at": None, "url": None}
    return {
        "title": _node_value(node, "headline", "name"),
        "published_at": _normalize_datetime(_node_value(node, *_JSON_LD_DATE_KEYS)),
        "url": _json_ld_url(node),
    }


def _meta_content(soup, *keys):
    wanted = {key.casefold() for key in keys}
    for meta in soup.find_all("meta"):
        key = meta.get("property") or meta.get("name") or ""
        if key.casefold() in wanted:
            content = meta.get("content")
            if isinstance(content, str) and content.strip():
                return _fold(content)
    return None


def _heading_title(soup):
    heading = soup.find("h1")
    if heading is None:
        return None
    return _fold(heading.get_text(" ")) or None


def _time_element_value(soup):
    tag = soup.find("time")
    if tag is None:
        return None
    value = tag.get("datetime") or tag.get_text(" ")
    return _fold(value) or None


def _date_container_marker(tag):
    itemprop = tag.get("itemprop")
    if itemprop and str(itemprop).casefold() in {"datepublished", "datecreated", "datemodified"}:
        return True
    markers = []
    for attribute in ("class", "id", "rel"):
        value = tag.get(attribute)
        if isinstance(value, list):
            markers.extend(str(part) for part in value)
        elif value:
            markers.append(str(value))
    joined = " ".join(markers).casefold()
    return any(token in joined for token in _DATE_MARKER_TOKENS)


def _date_container_value(soup):
    containers = soup.find_all(_date_container_marker, limit=_MAX_DATE_CONTAINERS)
    for tag in containers:
        value = tag.get("content") or tag.get("datetime") or tag.get_text(" ")
        folded = _fold(value)
        if not folded or len(folded) > _MAX_DATE_TEXT_CHARS:
            continue
        if _normalize_datetime(folded):
            return folded
    return None


def _visible_text(soup, max_chars):
    for element in soup(["script", "style", "noscript"]):
        element.decompose()
    return " ".join(soup.get_text(" ").split())[:max_chars]


def count_date_markers(soup):
    markers = len(soup.find_all("time"))
    markers += len(soup.find_all(_date_container_marker, limit=100))
    return markers


def is_list_page(soup):
    return count_date_markers(soup) >= _LIST_PAGE_DATE_MARKERS


def is_list_page_html(html):
    if not isinstance(html, str) or not html.strip():
        return False
    return is_list_page(BeautifulSoup(html[:_MAX_METADATA_HTML_CHARS], "html.parser"))


def _has_company_evidence(company, title, text):
    return _has_identity_evidence(company, {"title": title, "text": text})


def _has_channel_evidence(channel, title, text):
    return _has_source_purpose(channel, {"title": title, "text": text})


def parse_article_metadata(html):
    if not isinstance(html, str) or not html.strip():
        raise ValueError("html is required")
    soup = BeautifulSoup(html[:_MAX_METADATA_HTML_CHARS], "html.parser")
    json_ld = _json_ld_metadata(soup)
    title = json_ld["title"] or _meta_content(soup, "og:title") or _heading_title(soup) or None
    published_at = (
        json_ld["published_at"]
        or _normalize_datetime(_meta_content(soup, "article:published_time", "og:published_time", "article:modified_time"))
        or _normalize_datetime(_time_element_value(soup))
        or _normalize_datetime(_date_container_value(soup))
    )
    return {"title": title, "published_at": published_at, "json_ld_url": json_ld["url"]}


def extract_direct_article(url, *, http_client, approved_domains, candidate=None, company=None, channel=None, resolver=None, max_text_chars=_MAX_TEXT_CHARS) -> dict:
    if isinstance(max_text_chars, bool) or not isinstance(max_text_chars, int) or max_text_chars <= 0:
        raise ValueError("max text chars must be a positive integer")
    if candidate is not None and not isinstance(candidate, Mapping):
        raise ValueError("candidate is invalid")
    if company is not None and not isinstance(company, Mapping):
        raise ValueError("company is invalid")
    if channel is not None and channel not in _VALID_CHANNELS:
        raise ValueError("candidate channel is invalid")
    domains = _approved_domains(approved_domains)
    candidate = dict(candidate or {})
    try:
        page = fetch_html_page(url, http_client=http_client, resolver=resolver)
    except ValueError as exc:
        if str(exc) == "page html is empty":
            raise ValueError("empty_content") from None
        raise ValueError("request_failed") from None
    final_url = page["final_url"]
    if not _host_in_domains(url_host(final_url), domains):
        raise ValueError("redirect_not_allowed")
    soup = BeautifulSoup(page["html"], "html.parser")
    if is_list_page(soup):
        raise ValueError("list_page")
    metadata = parse_article_metadata(page["html"])
    if metadata["json_ld_url"]:
        try:
            canonicalize_public_url(metadata["json_ld_url"])
        except ValueError:
            raise ValueError("unsafe_metadata_url") from None
    title = metadata["title"] or _fold(candidate.get("title")) or None
    if title:
        title = strip_title_site_prefix(title, company)
    published_at = metadata["published_at"] or _normalize_datetime(candidate.get("published_at"))
    text = _visible_text(soup, max_text_chars)
    if len(text) < _MIN_TEXT_CHARS:
        raise ValueError("empty_content")
    if not title:
        raise ValueError("metadata_missing")
    if not published_at:
        raise ValueError("metadata_missing")
    if company is not None:
        if not _has_company_evidence(company, title, text):
            raise ValueError("identity_evidence_missing")
        if channel is not None and not _has_channel_evidence(channel, title, text):
            raise ValueError("channel_evidence_missing")
    return {
        "status": "extracted",
        "url": page["requested_url"],
        "final_url": final_url,
        "title": title[:_MAX_TITLE_CHARS],
        "published_at": published_at,
        "text": text,
        "provider": "direct_http",
    }

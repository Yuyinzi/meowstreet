import re
from datetime import date, datetime, timedelta
from urllib.parse import parse_qsl, urlsplit

from app.agents.catalyst_research.domain import canonicalize_public_url
from app.agents.catalyst_research.domain import url_host


_VALID_CHANNELS = frozenset({"press_releases", "events_presentations", "earnings_results"})
_CHANNEL_PHRASES = {
    "press_releases": "press release",
    "events_presentations": "events presentations",
    "earnings_results": "quarterly earnings financial results",
}
_DEFAULT_SLICE_DAYS = 92
_DEFAULT_MAX_QUERIES = 16
_DEFAULT_RESULT_LIMIT = 10
_DEFAULT_GAP_LOOKBACK_DAYS = 14
_DEFAULT_MAX_GAP_QUERIES = 2
_REJECTED_HOST_MARKERS = (
    "web.archive.org",
    "archive.today",
    "archive.ph",
    "archive.is",
    "archive.org",
    "archive.li",
    "wayback",
    "webcache",
    "cache.google",
    "google.",
    "bing.",
    "duckduckgo.",
    "search.brave",
    "yahoo.",
    "baidu.",
    "ecosia.",
    "facebook.",
    "linkedin.",
    "twitter.",
    "instagram.",
    "youtube.",
    "youtu.be",
    "reddit.",
    "tiktok.",
    "bloomberg.",
    "businesswire.",
    "globenewswire.",
    "marketwatch.",
    "prnewswire.",
    "reuters.",
    "seekingalpha.",
    "stockanalysis.",
    "feedly.",
    "news.google",
)
_LIST_ROOT_SEGMENTS = frozenset(
    {
        "articles",
        "blog",
        "events",
        "home",
        "investor-relations",
        "investors",
        "media",
        "news",
        "newsroom",
        "press",
        "press-release",
        "press-releases",
        "press-releases-and-events",
        "presentations",
        "presentations-and-events",
    }
)
_REJECTED_PATH_SEGMENTS = frozenset({"search", "searchresults", "tag", "tags", "category", "topics"})
_ARCHIVE_LABEL_SEGMENTS = frozenset(
    {
        "press-releases",
        "press-release",
        "news-releases",
        "news-events",
        "presentations",
        "events-presentations",
        "ir-calendar",
        "events-calendar",
        "calendar",
        "past-events",
        "past",
        "filings-reports",
        "sec-filings",
        "filings",
        "financial-results",
        "quarterly-reports",
        "annual-reports",
    }
)
_SEARCH_QUERY_KEYS = frozenset({"q", "query", "s", "search", "keyword"})
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
_RANK_FALLBACK = 10_000


def _coerce_date(value, label):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return date.fromisoformat(value.strip())
        except ValueError:
            raise ValueError(f"{label} is invalid") from None
    raise ValueError(f"{label} is required")


def _positive_integer(value, label):
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{label} must be a positive integer")
    return value


def _config_int(config, key, default):
    if not isinstance(config, dict):
        raise ValueError("collection config is required")
    value = config.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"collection config {key} is invalid")
    return value


def _validate_channel(channel):
    if channel not in _CHANNEL_PHRASES:
        raise ValueError(f"channel {channel!r} is not supported")
    return channel


def _normalize_domains(domains):
    if isinstance(domains, (str, bytes)) or not isinstance(domains, (list, tuple, set, frozenset)):
        raise ValueError("approved domains are required")
    normalized = []
    for domain in domains:
        if not isinstance(domain, str) or not domain.strip():
            raise ValueError("approved domains must be non-empty strings")
        value = domain.strip().casefold()
        if value not in normalized:
            normalized.append(value)
    if not normalized:
        raise ValueError("approved domains are required")
    return normalized


def _company_identity(company):
    if not isinstance(company, dict):
        raise ValueError("company identity is required")
    raw_name = " ".join(str(company.get("company_name") or company.get("name") or "").split())
    name = re.sub(r"[^A-Za-z0-9 .&-]", " ", raw_name)
    name = " ".join(name.split())[:120]
    ticker = re.sub(r"[^A-Za-z0-9.-]", "", str(company.get("ticker") or "").upper())[:24]
    identity = name or ticker
    if not identity:
        raise ValueError("company identity is required")
    return identity


def _identity_tokens(company):
    if not isinstance(company, dict):
        raise ValueError("company identity is required")
    name = " ".join(str(company.get("company_name") or company.get("name") or "").split())
    ticker = " ".join(str(company.get("ticker") or "").split()).casefold()
    tokens = {
        token.casefold()
        for token in re.findall(r"[A-Za-z0-9]+", name)
        if token.casefold() not in _COMMON_IDENTITY_WORDS and len(token) >= 3
    }
    if ticker:
        tokens.add(ticker)
    return tokens


def _build_query(company, channel, domain, window_start, window_end, purpose, result_limit):
    identity = _company_identity(company)
    after = window_start - timedelta(days=1)
    before = window_end + timedelta(days=1)
    query = f"site:{domain} {identity} {_CHANNEL_PHRASES[channel]} after:{after.isoformat()} before:{before.isoformat()}"
    return {
        "query": query,
        "domain": domain,
        "channel": channel,
        "purpose": purpose,
        "window": {"start": window_start.isoformat(), "end": window_end.isoformat()},
        "result_limit": result_limit,
    }


def historical_slices(start: date, end: date, *, slice_days: int, max_queries: int) -> dict:
    window_start = _coerce_date(start, "window start")
    window_end = _coerce_date(end, "window end")
    if window_start > window_end:
        raise ValueError("date window is invalid")
    slice_size = _positive_integer(slice_days, "slice days")
    cap = _positive_integer(max_queries, "max queries")
    total_days = (window_end - window_start).days + 1
    required = (total_days + slice_size - 1) // slice_size
    count = min(required, cap)
    slices = []
    for index in range(count):
        slice_start = window_start + timedelta(days=index * slice_size)
        slice_end = min(slice_start + timedelta(days=slice_size - 1), window_end)
        slices.append({"index": index, "start": slice_start.isoformat(), "end": slice_end.isoformat()})
    truncated = required > cap
    return {
        "slices": slices,
        "truncated": truncated,
        "truncation_reason": "historical_query_limit" if truncated else None,
    }


def historical_queries(company: dict, channel: str, domains: list, window: dict, config: dict) -> dict:
    _validate_channel(channel)
    domain_list = _normalize_domains(domains)
    if not isinstance(window, dict):
        raise ValueError("date window is required")
    window_start = _coerce_date(window.get("start"), "window start")
    window_end = _coerce_date(window.get("end"), "window end")
    if window_start > window_end:
        raise ValueError("date window is invalid")
    max_queries = _config_int(config, "max_historical_queries_per_channel", _DEFAULT_MAX_QUERIES)
    result_limit = _config_int(config, "search_result_limit", _DEFAULT_RESULT_LIMIT)
    slice_days = _config_int(config, "historical_slice_days", _DEFAULT_SLICE_DAYS)
    slices = historical_slices(window_start, window_end, slice_days=slice_days, max_queries=max_queries)
    queries = [
        _build_query(
            company,
            channel,
            domain,
            date.fromisoformat(time_slice["start"]),
            date.fromisoformat(time_slice["end"]),
            "historical_backfill",
            result_limit,
        )
        for time_slice in slices["slices"]
        for domain in domain_list
    ]
    truncated = slices["truncated"] or len(queries) > max_queries
    return {
        "channel": channel,
        "window": {"start": window_start.isoformat(), "end": window_end.isoformat()},
        "queries": queries[:max_queries],
        "truncated": truncated,
        "truncation_reason": "historical_query_limit" if truncated else None,
    }


def gap_queries(company: dict, channel: str, domains: list, as_of: date, config: dict) -> list:
    _validate_channel(channel)
    domain_list = _normalize_domains(domains)
    as_of_date = _coerce_date(as_of, "as of date")
    lookback_days = _config_int(config, "gap_lookback_days", _DEFAULT_GAP_LOOKBACK_DAYS)
    max_queries = _config_int(config, "max_gap_queries_per_channel", _DEFAULT_MAX_GAP_QUERIES)
    result_limit = _config_int(config, "search_result_limit", _DEFAULT_RESULT_LIMIT)
    window_start = as_of_date - timedelta(days=lookback_days - 1)
    queries = [
        _build_query(company, channel, domain, window_start, as_of_date, "incremental_gap_check", result_limit)
        for domain in domain_list[:max_queries]
    ]
    return queries


def _is_approved_host(host, approved_domains):
    return any(host == domain or host.endswith(f".{domain}") for domain in approved_domains)


def _is_rejected_host(host):
    return any(marker in host for marker in _REJECTED_HOST_MARKERS)


def _is_list_root(canonical):
    parsed = urlsplit(canonical)
    segments = [segment for segment in parsed.path.split("/") if segment]
    if not segments:
        return True
    if len(segments) == 1 and segments[0].casefold() in _LIST_ROOT_SEGMENTS:
        return True
    if len(segments) <= 3 and segments[-1].casefold() in _ARCHIVE_LABEL_SEGMENTS:
        return True
    if any(segment.casefold() in _REJECTED_PATH_SEGMENTS for segment in segments):
        return True
    if any(key.casefold() in _SEARCH_QUERY_KEYS for key, _ in parse_qsl(parsed.query, keep_blank_values=True)):
        return True
    return False


def _has_identity_evidence(tokens, row, canonical):
    if not tokens:
        return False
    haystack = " ".join(
        str(row.get(key) or "") for key in ("title", "snippet", "text", "description")
    )
    haystack = f"{haystack} {urlsplit(canonical).path}".casefold()
    return any(re.search(rf"\b{re.escape(token)}\b", haystack) for token in tokens)


def _candidate_sort_key(row):
    published = str(row.get("published_date") or "9999-12-31")
    rank = row.get("provider_rank")
    if not isinstance(rank, int) or isinstance(rank, bool):
        rank = _RANK_FALLBACK
    return (published, rank, str(row.get("url") or ""))


def filter_official_candidates(rows: list, *, company: dict, channel: str, approved_domains) -> list:
    _validate_channel(channel)
    if not isinstance(rows, list):
        raise ValueError("candidate rows are required")
    approved = _normalize_domains(approved_domains)
    tokens = _identity_tokens(company)
    accepted = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("candidate row is invalid")
        try:
            canonical = canonicalize_public_url(str(row.get("url") or ""))
        except ValueError:
            continue
        host = url_host(canonical)
        if not _is_approved_host(host, approved):
            continue
        if _is_rejected_host(host):
            continue
        if _is_list_root(canonical):
            continue
        if not _has_identity_evidence(tokens, row, canonical):
            continue
        candidate = dict(row)
        candidate["url"] = canonical
        candidate["canonical_url"] = canonical
        accepted.append(candidate)
    accepted.sort(key=_candidate_sort_key)
    return accepted

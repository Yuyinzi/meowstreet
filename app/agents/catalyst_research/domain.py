import calendar
import ipaddress
import re
import socket
from collections.abc import Mapping
from datetime import UTC, date, datetime
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit


_SOURCE_TYPES = {"press_releases", "events_presentations"}
_URL_SCHEMES = {"http", "https"}
_TRACKING_NAMES = {
    "_hsenc",
    "_hsmi",
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "ref",
    "referrer",
}
_EARNINGS_PATTERNS = (
    re.compile(r"\b(?:financial|quarterly|annual|full[ -]year|fiscal)\s+(?:financial\s+)?results?\b", re.IGNORECASE),
    re.compile(r"\b(?:q[1-4]|first|second|third|fourth)\s+(?:fiscal\s+)?quarter\s+(?:financial\s+)?results?\b", re.IGNORECASE),
    re.compile(r"\b(?:q[1-4]|fy\s*\d{2,4})\b.{0,24}\b(?:financial\s+)?results?\b", re.IGNORECASE),
    re.compile(r"\b(?:q[1-4]|fy\s*\d{2,4}|quarterly|annual)\b.{0,24}\bearnings?\s+(?:release|conference\s+call|call|webcast)\b", re.IGNORECASE),
    re.compile(r"\b(?:earnings?|financial\s+results?|results?)\s+(?:release|presentation|webcast)\b", re.IGNORECASE),
    re.compile(r"\bearnings?\s+(?:conference\s+)?call\b", re.IGNORECASE),
    re.compile(r"\bresults?\s+(?:conference\s+)?call\b", re.IGNORECASE),
    re.compile(r"\b(?:quarterly|annual)\s+(?:financial\s+)?results?\b", re.IGNORECASE),
)
_EXPLICIT_FINANCIAL_RESULTS = re.compile(r"\bfinancial\s+results?\b", re.IGNORECASE)
_NON_EARNINGS_RESULT_CONTEXT = (
    re.compile(r"\b(?:product|customer|clinical|operational)\b.{0,40}\bresults?\b", re.IGNORECASE),
    re.compile(r"\bresults?\s+update\b", re.IGNORECASE),
)


def _fold_whitespace(value):
    if value is None:
        return ""
    return " ".join(str(value).split())


def _parse_date(value, label):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} is required")
    cleaned = value.strip()
    try:
        return date.fromisoformat(cleaned)
    except ValueError:
        try:
            return datetime.fromisoformat(cleaned.replace("Z", "+00:00")).date()
        except ValueError as exc:
            raise ValueError(f"{label} is invalid") from exc


def _subtract_years(value, years):
    day = min(value.day, calendar.monthrange(value.year - years, value.month)[1])
    return value.replace(year=value.year - years, day=day)


def normalize_request(ticker, years=4, as_of=None) -> dict:
    normalized = str(ticker or "").strip().upper()
    if not normalized:
        raise ValueError("ticker is required")
    if isinstance(years, bool) or not isinstance(years, int) or not 1 <= years <= 4:
        raise ValueError("years must be between 1 and 4")
    end = datetime.now(UTC).date() if as_of is None else _parse_date(as_of, "as of date")
    start = _subtract_years(end, years)
    return {
        "ticker": normalized,
        "years": years,
        "as_of": end.isoformat(),
        "start": start.isoformat(),
        "end": end.isoformat(),
    }


def _parse_url(url):
    if not isinstance(url, str) or not url.strip():
        raise ValueError("url is required")
    value = url.strip()
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ValueError("url is invalid")
    try:
        parsed = urlsplit(value)
        scheme = parsed.scheme.casefold()
        host = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise ValueError("url is invalid") from exc
    if scheme not in _URL_SCHEMES:
        raise ValueError("url scheme is not allowed")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("url credentials are not allowed")
    if not host:
        raise ValueError("url host is required")
    try:
        normalized_host = host.encode("idna").decode("ascii").casefold().rstrip(".")
    except UnicodeError as exc:
        raise ValueError("url host is invalid") from exc
    if not normalized_host or normalized_host == "localhost" or normalized_host.endswith((".localhost", ".internal")):
        raise ValueError("url host is not public")
    try:
        address = ipaddress.ip_address(normalized_host)
    except ValueError:
        address = None
        if re.fullmatch(r"[0-9a-fA-FxX.]+", normalized_host):
            try:
                address = ipaddress.ip_address(socket.inet_aton(normalized_host))
            except OSError as exc:
                raise ValueError("url host is invalid") from exc
    if address is not None and (not address.is_global or address.is_multicast):
        raise ValueError("url host is not public")
    return parsed, scheme, normalized_host, port


def _canonical_query(query):
    pairs = []
    for key, value in parse_qsl(query, keep_blank_values=True):
        normalized_key = key.casefold()
        if normalized_key.startswith("utm_") or normalized_key.startswith("mc_") or normalized_key in _TRACKING_NAMES:
            continue
        pairs.append((key, value))
    pairs.sort(key=lambda item: (item[0].casefold(), item[1]))
    return urlencode(pairs, doseq=True, quote_via=quote)


def canonicalize_public_url(url: str) -> str:
    parsed, scheme, host, port = _parse_url(url)
    if ":" in host:
        netloc_host = f"[{host}]"
    else:
        netloc_host = host
    if port is not None and port != (80 if scheme == "http" else 443):
        netloc_host = f"{netloc_host}:{port}"
    return urlunsplit((scheme, netloc_host, parsed.path, _canonical_query(parsed.query), ""))


def url_host(url: str) -> str:
    return _parse_url(url)[2]


def _resolved_addresses(host, resolver):
    try:
        if callable(resolver):
            values = resolver(host)
        elif hasattr(resolver, "resolve"):
            values = resolver.resolve(host)
        elif isinstance(resolver, Mapping):
            values = resolver.get(host, ())
        else:
            raise ValueError("url resolver is invalid")
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("url host could not be resolved") from exc
    if isinstance(values, str):
        values = [values]
    addresses = []
    for value in values or ():
        if isinstance(value, str) or isinstance(value, ipaddress.IPv4Address | ipaddress.IPv6Address):
            addresses.append(value)
        elif isinstance(value, tuple):
            candidate = value[-1] if value and isinstance(value[-1], str) else value[-1][0] if value and isinstance(value[-1], tuple) else None
            if candidate:
                addresses.append(candidate)
    return addresses


def validate_redirect_chain(urls: list[str], *, resolver=None) -> list[str]:
    if not isinstance(urls, list) or not urls:
        raise ValueError("redirect chain is required")
    normalized = []
    for url in urls:
        canonical = canonicalize_public_url(url)
        host = url_host(canonical)
        if resolver is not None:
            addresses = _resolved_addresses(host, resolver)
            if not addresses:
                raise ValueError("url host could not be resolved")
            try:
                parsed_addresses = [ipaddress.ip_address(address) for address in addresses]
            except ValueError as exc:
                raise ValueError("url host resolution is invalid") from exc
            if any(not address.is_global for address in parsed_addresses):
                raise ValueError("url host is not public")
        normalized.append(canonical)
    return normalized


def _source_type(source_type):
    if source_type not in _SOURCE_TYPES:
        raise ValueError("event source type is invalid")
    return source_type


def normalize_observations(ticker, source_type, events, requested_start, requested_end) -> dict:
    normalized_ticker = str(ticker or "").strip().upper()
    if not normalized_ticker:
        raise ValueError("ticker is required")
    source_type = _source_type(source_type)
    if not isinstance(events, list):
        raise ValueError("events are required")
    start = _parse_date(requested_start, "requested start")
    end = _parse_date(requested_end, "requested end")
    if start > end:
        raise ValueError("requested date range is invalid")
    result = []
    seen = set()
    for event in events:
        if not isinstance(event, Mapping):
            raise ValueError("event is invalid")
        event_ticker = event.get("ticker")
        if event_ticker is not None and str(event_ticker).strip().upper() != normalized_ticker:
            raise ValueError("event ticker does not match ticker")
        title = _fold_whitespace(event.get("title", ""))
        if not title:
            raise ValueError("event title is required")
        published_value = event.get("published_date") if event.get("published_date") is not None else event.get("date") if source_type == "press_releases" else None
        event_value = event.get("event_date") if event.get("event_date") is not None else event.get("date") if source_type == "events_presentations" else None
        published = _parse_date(published_value, "event published date") if published_value is not None else None
        event_date = _parse_date(event_value, "event date") if event_value is not None else None
        if source_type == "press_releases":
            count_date = published
            if count_date is None:
                raise ValueError("event published date is required")
            if count_date > end:
                raise ValueError("future press release date is invalid")
        else:
            count_date = event_date or published
            if count_date is None:
                raise ValueError("event date is required")
        supplied_url = event.get("canonical_url") or event.get("url")
        if source_type == "press_releases" and not supplied_url:
            raise ValueError("event url is required")
        canonical_url = canonicalize_public_url(supplied_url) if supplied_url else None
        if count_date < start or count_date > end:
            continue
        normalized_title = title.casefold()
        key = (normalized_ticker, source_type, count_date.isoformat(), normalized_title, canonical_url or "")
        if key in seen:
            continue
        seen.add(key)
        normalized_event = dict(event)
        normalized_event.update(
            {
                "ticker": normalized_ticker,
                "source_type": source_type,
                "published_date": published.isoformat() if published else None,
                "event_date": event_date.isoformat() if event_date else None,
                "count_date": count_date.isoformat(),
                "title": title,
                "normalized_title": normalized_title,
                "canonical_url": canonical_url,
                "url": canonical_url,
            }
        )
        result.append(normalized_event)
    return {
        "ticker": normalized_ticker,
        "source_type": source_type,
        "requested_start": start.isoformat(),
        "requested_end": end.isoformat(),
        "events": result,
    }


def classify_title_by_rule(title, source_type) -> str | None:
    _source_type(source_type)
    normalized = _fold_whitespace(title)
    if not normalized:
        return None
    if not _EXPLICIT_FINANCIAL_RESULTS.search(normalized) and any(
        pattern.search(normalized) for pattern in _NON_EARNINGS_RESULT_CONTEXT
    ):
        return None
    if any(pattern.search(normalized) for pattern in _EARNINGS_PATTERNS):
        return "earnings"
    return None


def _payload_classifications(model_payload):
    if model_payload is None:
        return [], False
    if hasattr(model_payload, "model_dump"):
        model_payload = model_payload.model_dump()
    if isinstance(model_payload, Mapping):
        rows = model_payload.get("classifications")
    elif isinstance(model_payload, list):
        rows = model_payload
    else:
        return [], True
    return rows if isinstance(rows, list) else [], True


def merge_classifications(events, model_payload=None) -> list[dict]:
    if not isinstance(events, list):
        raise ValueError("events are required")
    rows, model_attempted = _payload_classifications(model_payload)
    by_id = {}
    duplicate_ids = set()
    malformed = False
    for row in rows:
        if not isinstance(row, Mapping):
            malformed = True
            continue
        identifier = row.get("id")
        if isinstance(identifier, bool) or not isinstance(identifier, int) or identifier < 1:
            malformed = True
            continue
        if identifier in by_id:
            duplicate_ids.add(identifier)
        by_id.setdefault(identifier, []).append(row)
    event_ids = set()
    identifiers = []
    for position, event in enumerate(events, 1):
        if not isinstance(event, Mapping):
            raise ValueError("event is invalid")
        identifier = event.get("id", position)
        try:
            hash(identifier)
        except TypeError:
            identifiers.append(None)
            continue
        event_ids.add(identifier)
        identifiers.append(identifier)
    unknown_model_id = any(identifier not in event_ids for identifier in by_id)
    output = []
    for position, event in enumerate(events, 1):
        if not isinstance(event, Mapping):
            raise ValueError("event is invalid")
        item = dict(event)
        identifier = identifiers[position - 1]
        rule_state = classify_title_by_rule(event.get("title", ""), event.get("source_type"))
        matched = by_id.get(identifier, []) if identifier is not None else []
        state = rule_state
        method = "rule_v1" if rule_state else None
        reason = None
        if len(matched) != 1 or identifier in duplicate_ids:
            state = rule_state or "ambiguous"
            if matched and rule_state:
                state = "ambiguous"
            method = "llm_v1" if model_attempted and matched else method
        elif (malformed or unknown_model_id) and not rule_state:
            state = "ambiguous"
            method = "llm_v1"
        else:
            model_state = matched[0].get("earnings_state")
            if model_state not in {"earnings", "non_earnings", "ambiguous"}:
                state = "ambiguous"
                method = "llm_v1"
            elif rule_state and model_state != rule_state:
                state = "ambiguous"
                method = "llm_v1"
            elif rule_state:
                state = rule_state
                method = "rule_v1"
            else:
                state = model_state
                method = "llm_v1"
            reason = matched[0].get("reason")
        if state is None:
            state = "ambiguous"
            method = "manual" if not model_attempted else "llm_v1"
        item["earnings_state"] = state
        item["classification_method"] = method
        if reason:
            item["classification_reason"] = _fold_whitespace(reason)
        output.append(item)
    return output

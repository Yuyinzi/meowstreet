import calendar
import hashlib
import ipaddress
import json
import re
import socket
from collections import Counter
from collections.abc import Mapping
from datetime import UTC, date, datetime
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

from app.agents.catalyst_research.providers.base import SearchProviderError
from app.agents.catalyst_research.providers.base import VALID_REASON_CODES
from app.agents.catalyst_research.config import PROMPT_VERSIONS
from app.agents.catalyst_research.prompts import classification_prompt
from app.agents.catalyst_research.prompts import source_selection_prompt
from app.agents.catalyst_research.schemas import EventClassificationResponse
from app.agents.catalyst_research.schemas import SourceSelectionResponse


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
    re.compile(r"\bresults?\b.{0,40}\b(?:program|pilot|customer)\b", re.IGNORECASE),
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
    identifier_counts = Counter(identifier for identifier in identifiers if identifier is not None)
    duplicate_event_ids = {identifier for identifier, count in identifier_counts.items() if count > 1}
    integer_event_ids = all(isinstance(identifier, int) and not isinstance(identifier, bool) for identifier in identifiers)
    rule_ids = {
        identifier
        for identifier, event in zip(identifiers, events)
        if identifier is not None and classify_title_by_rule(event.get("title", ""), event.get("source_type"))
    }
    if integer_event_ids:
        expected_model_ids = event_ids - rule_ids
    else:
        rule_positions = {
            position
            for position, (identifier, event) in enumerate(zip(identifiers, events), 1)
            if identifier is not None and classify_title_by_rule(event.get("title", ""), event.get("source_type"))
        }
        expected_model_ids = set(range(1, len(events) + 1)) - rule_positions
    unknown_model_id = any(identifier not in expected_model_ids for identifier in by_id)
    model_ids = set(by_id)
    incomplete_model_output = model_attempted and (
        malformed or unknown_model_id or duplicate_ids or model_ids != expected_model_ids
    )
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
        if identifier in duplicate_event_ids and not rule_state:
            state = "ambiguous"
            method = "llm_v1" if model_attempted else "manual"
        elif incomplete_model_output and not rule_state:
            state = "ambiguous"
            method = "llm_v1"
        elif len(matched) != 1 or identifier in duplicate_ids:
            state = rule_state or "ambiguous"
            if matched and rule_state:
                state = "ambiguous"
            method = "llm_v1" if model_attempted and matched else method
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


def _classification_event_key(event):
    return (
        str(event.get("source_type") or ""),
        str(event.get("count_date") or event.get("event_date") or event.get("published_date") or ""),
        _fold_whitespace(event.get("title", "")).casefold(),
        str(event.get("canonical_url") or event.get("url") or ""),
        str(event.get("published_date") or ""),
        str(event.get("event_date") or ""),
    )


def _classification_tie_key(event):
    try:
        return json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    except (TypeError, ValueError):
        return repr(sorted((str(key), repr(value)) for key, value in event.items()))


def _classification_output_key(event):
    identifier = event.get("id")
    if isinstance(identifier, int) and not isinstance(identifier, bool) and identifier >= 1:
        return (0, identifier, _classification_event_key(event), _classification_tie_key(event))
    return (1, 0, _classification_event_key(event), _classification_tie_key(event))


def _classification_input(events):
    return [
        {"id": event["id"], "source_type": event["source_type"], "title": event["title"]}
        for event in events
    ]


def _hash_payload(value):
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _response_payload(response):
    parsed = getattr(response, "output_parsed", None)
    if parsed is None:
        payload = None
    else:
        candidate = parsed.model_dump(mode="json") if hasattr(parsed, "model_dump") else parsed
        payload = EventClassificationResponse.model_validate(candidate).model_dump(mode="json")
    output_text = getattr(response, "output_text", None)
    return payload, output_text


async def classify_observations(events, *, llm_client=None, model=None, batch_size=50) -> dict:
    if not isinstance(events, list):
        raise ValueError("events are required")
    if isinstance(batch_size, bool) or not isinstance(batch_size, int) or not 1 <= batch_size <= 50:
        raise ValueError("batch size must be between 1 and 50")
    prepared = []
    for event in events:
        if not isinstance(event, Mapping):
            raise ValueError("event is invalid")
        item = dict(event)
        if not _fold_whitespace(item.get("title")):
            raise ValueError("event title is required")
        _source_type(item.get("source_type"))
        prepared.append(item)
    prepared.sort(key=lambda item: (_classification_event_key(item), _classification_tie_key(item)))
    explicit_ids = [item.get("id") for item in prepared]
    valid_ids = [identifier for identifier in explicit_ids if isinstance(identifier, int) and not isinstance(identifier, bool) and identifier >= 1]
    duplicate_valid_ids = {identifier for identifier, count in Counter(valid_ids).items() if count > 1}
    used_ids = set(valid_ids)
    next_id = 1
    for item in prepared:
        if "id" not in item:
            while next_id in used_ids:
                next_id += 1
            item["id"] = next_id
            used_ids.add(next_id)
            next_id += 1
    for input_id, item in enumerate(prepared, 1):
        identifier = item.get("id")
        if not isinstance(identifier, int) or isinstance(identifier, bool) or identifier < 1 or identifier in duplicate_valid_ids:
            item["classification_input_id"] = input_id
    classified = []
    unresolved = []
    for item in prepared:
        rule_state = classify_title_by_rule(item["title"], item["source_type"])
        identifier = item.get("id")
        invalid_id = not isinstance(identifier, int) or isinstance(identifier, bool) or identifier < 1
        if invalid_id or identifier in duplicate_valid_ids:
            item["earnings_state"] = "ambiguous"
            item["classification_method"] = "manual"
            item.update({"model": None, "prompt_schema_version": None, "input_hash": None, "output_hash": None})
            classified.append(item)
        elif rule_state:
            item["earnings_state"] = rule_state
            item["classification_method"] = "rule_v1"
            item.update({"model": None, "prompt_schema_version": None, "input_hash": None, "output_hash": None})
            classified.append(item)
        else:
            unresolved.append(item)

    llm_call_count = 0
    provenance = []
    for start in range(0, len(unresolved), batch_size):
        batch = unresolved[start : start + batch_size]
        batch_index = start // batch_size
        bounded = _classification_input(batch)
        prompt = classification_prompt(bounded)
        input_hash = _hash_payload(prompt)
        payload = None
        output_hash = None
        attempted = llm_client is not None and bool(model)
        if attempted:
            llm_call_count += 1
            try:
                response = await llm_client.responses.parse(
                    model=model,
                    input=prompt,
                    text_format=EventClassificationResponse,
                )
                payload, output_text = _response_payload(response)
                output_hash = _hash_payload(payload) if payload is not None else None
            except Exception:
                payload = None
            provenance.append(
                {
                    "batch_index": batch_index,
                    "event_ids": [item["id"] for item in batch],
                    "method": "llm_v1",
                    "model": model,
                    "prompt_schema_version": PROMPT_VERSIONS["classification"],
                    "input_hash": input_hash,
                    "output_hash": output_hash,
                }
            )
        merge_payload = payload if payload is not None else {"classifications": []} if attempted else None
        merged = merge_classifications(batch, merge_payload)
        batch_provenance = provenance[-1] if attempted else None
        for item in merged:
            item.update(
                {
                    "model": batch_provenance["model"] if batch_provenance else None,
                    "prompt_schema_version": batch_provenance["prompt_schema_version"] if batch_provenance else None,
                    "input_hash": batch_provenance["input_hash"] if batch_provenance else None,
                    "output_hash": batch_provenance["output_hash"] if batch_provenance else None,
                }
            )
        classified.extend(merged)
    classified.sort(key=_classification_output_key)
    return {"events": classified, "llm_call_count": llm_call_count, "provenance": provenance}


_DISCOVERY_SOURCE_TYPES = ("ir_home", "press_releases", "events_presentations", "earnings_results")
MAX_ALTERNATE_SOURCES_PER_TYPE = 2
DEFERRED_DISCOVERY_CAPABILITIES = ("same_site_traversal_from_trusted_snapshot",)
_DISCOVERY_QUERY_LABELS = {
    "ir_home": "investor relations",
    "press_releases": "investor relations press releases news",
    "events_presentations": "investor relations events presentations",
    "earnings_results": "investor relations quarterly earnings financial results",
}
_THIRD_PARTY_HOST_MARKERS = (
    "bloomberg.",
    "businesswire.",
    "facebook.",
    "globenewswire.",
    "linkedin.",
    "marketwatch.",
    "prnewswire.",
    "reuters.",
    "seekingalpha.",
    "stockanalysis.",
    "yahoo.",
)
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


def _discovery_queries(company: Mapping, source_types: set[str] | None = None) -> list[dict]:
    name = re.sub(r"[^A-Za-z0-9 .&-]", " ", _fold_whitespace(company.get("company_name") or company.get("name") or ""))
    name = " ".join(name.split())[:120]
    ticker = re.sub(r"[^A-Za-z0-9.-]", "", _fold_whitespace(company.get("ticker") or "").upper())[:24]
    identity = name or ticker
    if not identity:
        raise ValueError("company identity is required")
    requested = set(source_types or _DISCOVERY_SOURCE_TYPES)
    return [
        {
            "source_type": source_type,
            "query": f"{identity} {ticker} {_DISCOVERY_QUERY_LABELS[source_type]}".strip()[:240],
        }
        for source_type in _DISCOVERY_SOURCE_TYPES
        if source_type in requested
    ]


def _repository_call(repository, method_name, *args, connection=None, **kwargs):
    method = getattr(repository, method_name, None)
    if method is None:
        raise ValueError(f"repository method {method_name} is unavailable")
    try:
        import inspect

        parameters = list(inspect.signature(method).parameters.values())
    except (TypeError, ValueError):
        parameters = []
    first = parameters[0].name if parameters else ""
    if first in {"con", "connection"}:
        if connection is None:
            raise ValueError("repository connection is required")
        return method(connection, *args, **kwargs)
    return method(*args, **kwargs)


def _identity_tokens(company: Mapping) -> set[str]:
    name = _fold_whitespace(company.get("company_name") or company.get("name") or "")
    ticker = _fold_whitespace(company.get("ticker") or "").casefold()
    words = {
        token.casefold()
        for token in re.findall(r"[A-Za-z0-9]+", name)
        if token.casefold() not in _COMMON_IDENTITY_WORDS and len(token) >= 3
    }
    if ticker:
        words.add(ticker)
    return words


def _has_identity_evidence(company: Mapping, result: Mapping) -> bool:
    haystack = " ".join(
        str(result.get(key) or "") for key in ("title", "snippet", "text", "description")
    ).casefold()
    tokens = _identity_tokens(company)
    return bool(tokens and any(re.search(rf"\b{re.escape(token)}\b", haystack) for token in tokens))


def _has_source_purpose(source_type: str, result: Mapping) -> bool:
    haystack = " ".join(
        str(result.get(key) or "") for key in ("title", "snippet", "text", "description")
    ).casefold()
    terms = {
        "ir_home": ("investor relations", "investors", "shareholders"),
        "press_releases": ("press release", "press releases", "news release", "news"),
        "events_presentations": ("events", "presentations", "webcast", "conference"),
        "earnings_results": ("earnings", "financial results", "quarterly results", "annual results"),
    }[source_type]
    return any(term in haystack for term in terms)


def _is_third_party(host: str) -> bool:
    return any(marker in host for marker in _THIRD_PARTY_HOST_MARKERS)


def _candidate_rows(results: list[Mapping]) -> dict[int, Mapping]:
    return {
        int(result["result_id"]): result
        for result in results
        if isinstance(result.get("result_id"), int) and not isinstance(result.get("result_id"), bool)
    }


def _selection_result(selection, rows: dict[int, Mapping], company: Mapping) -> dict:
    try:
        selected_url = canonicalize_public_url(selection.url)
    except ValueError:
        return {
            **selection.model_dump(mode="json"),
            "status": "rejected",
            "reason": "selected url is unsafe",
        }
    evidence_rows = [rows[item] for item in selection.evidence_result_ids if item in rows]
    if len(evidence_rows) != len(selection.evidence_result_ids):
        return {
            **selection.model_dump(mode="json"),
            "url": selected_url,
            "status": "rejected",
            "reason": "selection references unavailable evidence",
        }
    evidence = None
    for row in evidence_rows:
        try:
            if canonicalize_public_url(row.get("url")) == selected_url:
                evidence = row
                break
        except ValueError:
            continue
    if evidence is None:
        return {
            **selection.model_dump(mode="json"),
            "url": selected_url,
            "status": "rejected",
            "reason": "selected url is not in current evidence",
        }
    try:
        host = url_host(selected_url)
    except ValueError:
        return {
            **selection.model_dump(mode="json"),
            "url": selected_url,
            "status": "rejected",
            "reason": "selected url is unsafe",
        }
    if _is_third_party(host):
        status = "rejected"
        reason = "third-party source is not an official IR archive"
    elif not _has_identity_evidence(company, evidence):
        status = "ambiguous"
        reason = "company identity is not established by page evidence"
    elif not _has_source_purpose(selection.source_type, evidence):
        status = "ambiguous"
        reason = "IR archive purpose is not established by page evidence"
    else:
        status = "ambiguous"
        reason = "candidate requires fetched company identity and IR-purpose verification"
    result = {
        **selection.model_dump(mode="json"),
        "url": selected_url,
        "status": status,
        "reason": reason,
    }
    result["provider_rank"] = evidence.get("provider_rank") if isinstance(evidence.get("provider_rank"), int) else 10_000
    return result


async def _select_discovery_sources(company, results, *, llm_client, model):
    if llm_client is None or not model or not results:
        return [], None
    try:
        response = await llm_client.responses.parse(
            model=model,
            input=source_selection_prompt(company, results),
            text_format=SourceSelectionResponse,
        )
        payload = response.output_parsed
        if not isinstance(payload, SourceSelectionResponse):
            payload = SourceSelectionResponse.model_validate(
                payload.model_dump(mode="json") if hasattr(payload, "model_dump") else payload
            )
        rows = _candidate_rows(results)
        return [_selection_result(selection, rows, company) for selection in payload.selections], None
    except Exception:
        return [], "source selection failed"


def _manual_override_sources(overrides: Mapping) -> tuple[list[dict], list[str]]:
    if not isinstance(overrides, Mapping):
        raise ValueError("overrides are invalid")
    sources = []
    warnings = []
    for source_type, url in (overrides or {}).items():
        if source_type not in _DISCOVERY_SOURCE_TYPES:
            warnings.append("manual override source type was ignored")
            continue
        try:
            canonical = canonicalize_public_url(url)
        except ValueError:
            sources.append(
                {
                    "source_type": source_type,
                    "url": str(url or ""),
                    "status": "rejected",
                    "acceptance_status": "rejected",
                    "discovery_provider": "manual_override",
                    "evidence_result_ids": [],
                    "reason": "manual override url is unsafe",
                }
            )
            continue
        if _is_third_party(url_host(canonical)):
            sources.append(
                {
                    "source_type": source_type,
                    "url": canonical,
                    "status": "rejected",
                    "acceptance_status": "rejected",
                    "discovery_provider": "manual_override",
                    "evidence_result_ids": [],
                    "reason": "third-party source is not an official IR archive",
                }
            )
            continue
        sources.append(
            {
                "source_type": source_type,
                "url": canonical,
                "status": "ambiguous",
                "acceptance_status": "ambiguous",
                "discovery_provider": "manual_override",
                "evidence_result_ids": [],
                "reason": "manual override requires later fetch and identity validation",
            }
        )
    return sources, warnings


def _bounded_request_id(value) -> str | None:
    if value is None:
        return None
    normalized = " ".join(str(value).split())
    return normalized[:200] or None


def _bounded_metadata(value) -> dict:
    if not isinstance(value, Mapping):
        return {}
    output = {}
    for key, item in list(value.items())[:8]:
        if not isinstance(key, str) or not key or len(key) > 64:
            continue
        if isinstance(item, bool) or isinstance(item, (int, float)):
            output[key] = item
        elif isinstance(item, str):
            output[key] = " ".join(item.split())[:200]
    return output


def _bounded_search_result(row: Mapping) -> dict:
    return {
        "title": " ".join(str(row.get("title") or "").split())[:500],
        "url": " ".join(str(row.get("url") or "").split())[:2000],
        "snippet": " ".join(str(row.get("snippet") or "").split())[:1000],
        "provider_rank": row.get("provider_rank") if isinstance(row.get("provider_rank"), int) else None,
        "provider_metadata": _bounded_metadata(row.get("provider_metadata")),
    }


def _merge_source_candidates(existing: dict, incoming: dict) -> dict:
    evidence_ids = list(dict.fromkeys(existing.get("evidence_result_ids", []) + incoming.get("evidence_result_ids", [])))[:20]
    provenance = list(existing.get("provider_provenance", []))
    for item in incoming.get("provider_provenance", []):
        if item not in provenance and len(provenance) < 8:
            provenance.append(item)
    merged = dict(existing)
    merged["evidence_result_ids"] = evidence_ids
    merged["provider_provenance"] = provenance
    return merged


def _alternate_sources_truncated(candidates: list[dict]) -> dict[str, int]:
    urls_by_type = {}
    for candidate in candidates:
        source_type = candidate.get("source_type")
        url = candidate.get("url")
        if source_type not in _DISCOVERY_SOURCE_TYPES or not url:
            continue
        urls_by_type.setdefault(source_type, set()).add(url)
    return {
        source_type: max(0, len(urls) - MAX_ALTERNATE_SOURCES_PER_TYPE - 1)
        for source_type, urls in urls_by_type.items()
        if len(urls) > MAX_ALTERNATE_SOURCES_PER_TYPE + 1
    }


def _shape_source_candidates(candidates: list[dict], router) -> tuple[list[dict], list[dict]]:
    names = router.provider_order() if hasattr(router, "provider_order") else ("tavily", "native_search", "ddgs")
    provider_order = {name: index for index, name in enumerate(names)}
    deduped = {}
    for candidate in candidates:
        key = (candidate.get("source_type"), candidate.get("url"))
        if key in deduped:
            deduped[key].update(_merge_source_candidates(deduped[key], candidate))
        else:
            deduped[key] = dict(candidate)
    grouped = {}
    for index, candidate in enumerate(deduped.values()):
        source_type = candidate.get("source_type")
        grouped.setdefault(source_type, []).append((index, candidate))
    primaries = []
    alternates = []
    for source_type in _DISCOVERY_SOURCE_TYPES:
        rows = grouped.get(source_type, [])
        rows.sort(
            key=lambda item: (
                -1 if item[1].get("discovery_provider") == "manual_override" else provider_order.get(item[1].get("discovery_provider"), 99),
                item[1].get("provider_rank") if isinstance(item[1].get("provider_rank"), int) else 10_000,
                item[0],
            )
        )
        if rows:
            primaries.append(rows[0][1])
            alternates.extend(item[1] for item in rows[1 : MAX_ALTERNATE_SOURCES_PER_TYPE + 1])
    return primaries, alternates


async def _discover_sources_impl(
    company,
    *,
    router,
    llm_client,
    model,
    repository,
    job_id,
    overrides=None,
    connection=None,
    result_limit=10,
)-> dict:
    if not isinstance(company, Mapping):
        raise ValueError("company identity is required")
    if isinstance(result_limit, bool) or not isinstance(result_limit, int) or not 1 <= result_limit <= 50:
        raise ValueError("result limit is invalid")
    if overrides is not None and not isinstance(overrides, Mapping):
        raise ValueError("overrides are invalid")
    discovered, warnings = _manual_override_sources(overrides or {})
    if hasattr(router, "unavailable"):
        for provider_name in router.unavailable():
            warnings.append(f"{provider_name} is not configured or capability-ready")
    selected_types = {item["source_type"] for item in discovered if item["status"] != "rejected"}
    result_counter = 0
    provider_provenance = []
    query_specs = _discovery_queries(company, set(_DISCOVERY_SOURCE_TYPES) - selected_types)
    for query_spec in query_specs:
        if query_spec["source_type"] in selected_types:
            continue
        accepted_for_query = False
        for provider in router.provider_chain():
            started_at = datetime.now(UTC).isoformat()
            outcome = "provider_error"
            diagnostics = {}
            rows = []
            selections = []
            selection_warning = None
            unsafe_result_count = 0
            try:
                rows = await provider.search(query_spec["query"], limit=result_limit)
                if not isinstance(rows, list):
                    raise SearchProviderError("malformed_response", "search provider returned malformed results")
                normalized_rows = []
                for row in rows:
                    if not isinstance(row, Mapping) or not row.get("url"):
                        raise SearchProviderError("malformed_response", "search provider returned malformed results")
                    normalized = _bounded_search_result(row)
                    try:
                        normalized["url"] = canonicalize_public_url(normalized["url"])
                    except ValueError:
                        unsafe_result_count += 1
                        continue
                    result_counter += 1
                    normalized.update(
                        {
                            "result_id": result_counter,
                            "query": query_spec["query"],
                            "provider": provider.name,
                            "metadata": normalized.get("provider_metadata", {}),
                        }
                    )
                    normalized_rows.append(normalized)
                rows = normalized_rows
                diagnostics["result_ids"] = [row["result_id"] for row in rows]
                if unsafe_result_count:
                    diagnostics["rejected_unsafe_count"] = min(unsafe_result_count, result_limit)
                if not rows:
                    outcome = "rejected" if unsafe_result_count else "empty_results"
                else:
                    outcome = "candidate_results"
            except SearchProviderError as exc:
                outcome = exc.reason_code if exc.reason_code in VALID_REASON_CODES else "provider_error"
                diagnostics = {"reason": outcome}
                if exc.disable_provider:
                    router.disable(provider.name)
                    warnings.append(f"{provider.name} was disabled for this process run")
            except Exception:
                outcome = "provider_error"
                diagnostics = {"reason": "search provider request failed"}
            completed_at = datetime.now(UTC).isoformat()
            attempt = {
                "job_id": job_id,
                "provider": provider.name,
                "query": query_spec["query"],
                "requested_limit": result_limit,
                "started_at": started_at,
                "completed_at": completed_at,
                "outcome": outcome,
                "diagnostics": diagnostics,
                "provider_request_id": _bounded_request_id(getattr(provider, "last_request_id", None)),
            }
            try:
                attempt_id = _repository_call(repository, "record_search_attempt", attempt, connection=connection)
                if not isinstance(attempt_id, str) or not attempt_id:
                    raise ValueError("repository did not return search attempt id")
                if rows:
                    _repository_call(
                        repository,
                        "record_search_results",
                        job_id,
                        attempt_id,
                        rows,
                        connection=connection,
                    )
            except Exception:
                raise ValueError("search evidence persistence failed") from None
            if rows:
                selections, selection_warning = await _select_discovery_sources(
                    company, rows, llm_client=llm_client, model=model
                )
                if selection_warning:
                    warnings.append(selection_warning)
                target_candidates = [
                    item
                    for item in selections
                    if item["source_type"] == query_spec["source_type"]
                    and item["status"] == "ambiguous"
                ]
                outcome = "ambiguous" if target_candidates else "rejected"
            if hasattr(repository, "update_search_attempt"):
                try:
                    _repository_call(
                        repository,
                        "update_search_attempt",
                        attempt_id,
                        outcome=outcome,
                        diagnostics=diagnostics,
                        completed_at=completed_at,
                        provider_request_id=_bounded_request_id(getattr(provider, "last_request_id", None)),
                        connection=connection,
                    )
                except Exception:
                    raise ValueError("search evidence persistence failed") from None
            provider_provenance.append(
                {
                    "provider": provider.name,
                    "query": query_spec["query"],
                    "outcome": outcome,
                    "provider_request_id": _bounded_request_id(getattr(provider, "last_request_id", None)),
                    "result_ids": diagnostics.get("result_ids", []),
                }
            )
            if selections:
                for selection in selections:
                    selection["discovery_provider"] = provider.name
                    selection["provider_request_id"] = _bounded_request_id(getattr(provider, "last_request_id", None))
                    selection["acceptance_status"] = selection["status"]
                    selection["provider_provenance"] = [{
                        "provider": provider.name,
                        "provider_request_id": selection["provider_request_id"],
                    }]
                    existing = next(
                        (
                            item
                            for item in discovered
                            if item["source_type"] == selection["source_type"]
                            and item["url"] == selection["url"]
                        ),
                        None,
                    )
                    if existing:
                        if existing["status"] == "rejected" and selection["status"] == "ambiguous":
                            discovered.remove(existing)
                        else:
                            existing.update(_merge_source_candidates(existing, selection))
                            continue
                    discovered = [
                        item
                        for item in discovered
                        if not (
                            item["source_type"] == selection["source_type"]
                            and item["url"] == selection["url"]
                        )
                    ]
                    discovered.append(selection)
                accepted = [
                    item
                    for item in selections
                    if item["source_type"] == query_spec["source_type"]
                    and item["status"] == "ambiguous"
                ]
                if accepted:
                    accepted_for_query = True
                    selected_types.update(item["source_type"] for item in accepted)
        if not accepted_for_query and not router.provider_chain():
            warnings.append("search provider chain is unavailable")
            break
    accepted_count = sum(item["status"] == "accepted" for item in discovered)
    ambiguous_count = sum(item["status"] == "ambiguous" for item in discovered)
    rejected_count = sum(item["status"] == "rejected" for item in discovered)
    transport_outcomes = {"authentication_failed", "rate_limited", "timeout", "provider_error", "empty_results", "malformed_response", "not_configured"}
    only_transport_failures = bool(provider_provenance) and all(item["outcome"] in transport_outcomes for item in provider_provenance)
    if accepted_count:
        status = "accepted"
    elif ambiguous_count:
        status = "ambiguous"
    elif rejected_count or any(item["outcome"] == "rejected" for item in provider_provenance):
        status = "rejected"
    elif only_transport_failures:
        status = "search_unavailable"
    else:
        status = "search_unavailable"
    next_actions = []
    if status != "accepted":
        next_actions.append("provide a verified Investor Relations source override")
    if warnings:
        next_actions.append("review search provider and source evidence warnings")
    normalized_ticker = _fold_whitespace(company.get("ticker") or "").upper()
    for source in discovered:
        source.setdefault("ticker", normalized_ticker)
        source.setdefault("job_id", job_id)
    primary_sources, alternate_sources = _shape_source_candidates(discovered, router)
    alternate_sources_truncated = _alternate_sources_truncated(discovered)
    for provenance in provider_provenance:
        provenance["alternate_sources_truncated"] = dict(alternate_sources_truncated)
    result = {
        "status": status,
        "sources": primary_sources,
        "alternate_sources": alternate_sources,
        "alternate_sources_truncated": alternate_sources_truncated,
        "diagnostics": {"alternate_sources_truncated": alternate_sources_truncated},
        "deferred_capabilities": list(DEFERRED_DISCOVERY_CAPABILITIES),
        "provider_provenance": provider_provenance,
        "warnings": list(dict.fromkeys(warnings)),
        "next_actions": list(dict.fromkeys(next_actions)),
    }
    return result


async def discover_sources(
    company,
    *,
    router,
    llm_client,
    model,
    repository,
    job_id,
    overrides=None,
    connection=None,
    result_limit=10,
) -> dict:
    owned_connection = None
    if connection is None and callable(getattr(repository, "connect", None)):
        owned_connection = repository.connect()
        connection = owned_connection
    try:
        return await _discover_sources_impl(
            company,
            router=router,
            llm_client=llm_client,
            model=model,
            repository=repository,
            job_id=job_id,
            overrides=overrides,
            connection=connection,
            result_limit=result_limit,
        )
    finally:
        if owned_connection is not None:
            owned_connection.close()

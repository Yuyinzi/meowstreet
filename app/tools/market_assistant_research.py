import hashlib
import json
import math
import re
import unicodedata
from datetime import date
from typing import Literal
from typing import NoReturn
from urllib.parse import urlunsplit
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.tools.market_assistant_artifacts import build_object_index
from app.tools.market_assistant_artifacts import validate_artifact

RESEARCH_SCHEMA_VERSION = "market_assistant_research_result_v1"

_TIER_LIMITS = {
    "focused": {"max_queries": 2, "max_sources": 3},
    "standard": {"max_queries": 4, "max_sources": 6},
    "deep": {"max_queries": 8, "max_sources": 12},
}

_APPROVED_SCHEMES = frozenset({"http", "https"})

_DOMAIN_RE = re.compile(
    r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)*$"
)

_QUERY_FORBIDDEN_RE = re.compile(
    r"https?://|api_key|password|token|secret|;|\$\(|`|&&|\|\||[|><\n]",
    re.IGNORECASE,
)

_PRIVATE_HOST_RE = re.compile(
    r"(^|\.)localhost$|^127\.|^10\.|^192\.168\.|^172\.(1[6-9]|2\d|3[01])\."
    r"|\.internal$|^0\.0\.0\.0$|^169\.254\.|^::1$|^fe80:"
)


class _TimeWindow(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    start: str
    end: str


class _ResearchTask(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    purpose: Literal[
        "external_context",
        "current_events",
        "historical_context",
        "source_verification",
        "document_summary",
    ]
    depth_tier: Literal["focused", "standard", "deep"]
    queries: list[str]
    approved_domains: list[str] | None = None
    time_window: _TimeWindow | None = None
    expected_source_class: Literal[
        "official_publication",
        "news",
        "market_data",
        "financial_media",
        "academic",
    ]


class _ProviderMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    provider_id: str = Field(min_length=1)
    model: str | None = None
    request_id: str | None = None


class _SearchCall(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    search_call_id: str | None = None
    query: str
    occurred_at: str | None = None


class _ProviderSource(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    url: str
    title: str | None = None
    publisher: str | None = None
    publication_date: str | None = None
    event_date: str | None = None
    retrieved_at: str | None = None
    cited_spans: list[str]


class _FindingCitation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    url: str
    span: str | None = None


class _ProviderFinding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    statement: str
    purpose: Literal[
        "external_context",
        "current_events",
        "historical_context",
        "source_verification",
        "document_summary",
    ]
    framing: Literal["reported", "fact"]
    citations: list[_FindingCitation]


class _ProviderPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    provider_metadata: _ProviderMetadata
    search_calls: list[_SearchCall]
    sources: list[_ProviderSource]
    findings: list[_ProviderFinding]


def research_limits(tier):
    limits = _TIER_LIMITS.get(tier)
    if limits is None:
        raise ValueError("research tier is unknown")
    return dict(limits)


def validate_research_task(payload, *, explicit_deep):
    if not isinstance(payload, dict):
        raise ValueError("research task is required")
    try:
        validated = _ResearchTask.model_validate(payload)
    except ValidationError as exc:
        _raise_task_validation_error(exc)
    task = validated.model_dump()
    if task["depth_tier"] == "deep" and not explicit_deep:
        raise ValueError("deep research requires explicit user intent")
    _validate_queries(task["queries"], task["depth_tier"])
    task["approved_domains"] = _validate_domains(task["approved_domains"])
    task["time_window"] = _validate_time_window(task["time_window"])
    return task


def _validate_queries(queries, tier):
    if not queries:
        raise ValueError("research task queries are required")
    for query in queries:
        if not query.strip():
            raise ValueError("research task query is empty")
        if _QUERY_FORBIDDEN_RE.search(query):
            raise ValueError("research task query contains forbidden content")
    maximum = research_limits(tier)["max_queries"]
    if len(queries) > maximum:
        raise ValueError(f"research task exceeds maximum queries for {tier}")


def _validate_domains(domains):
    if domains is None:
        return None
    normalized = []
    for domain in domains:
        if not isinstance(domain, str):
            raise ValueError("research task domain filter is invalid")
        candidate = domain.strip().lower()
        if _DOMAIN_RE.fullmatch(candidate) is None:
            raise ValueError("research task domain filter is invalid")
        normalized.append(candidate)
    return normalized


def _validate_time_window(time_window):
    if time_window is None:
        return None
    start = time_window.get("start")
    end = time_window.get("end")
    start_date = _parse_iso_date(start, "research task time window start")
    end_date = _parse_iso_date(end, "research task time window end")
    if start_date > end_date:
        raise ValueError("research task time window start is after end")
    return time_window


def _parse_iso_date(value, label):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} is invalid") from exc


def _raise_task_validation_error(exc) -> NoReturn:
    errors = exc.errors()
    for error in errors:
        if error["type"] == "extra_forbidden":
            raise ValueError("extra inputs are not permitted")
    for error in errors:
        loc = error.get("loc", ())
        field = str(loc[0]) if loc else ""
        if field == "purpose":
            raise ValueError("research task purpose is unknown")
        if field == "depth_tier":
            raise ValueError("research tier is unknown")
        if field == "expected_source_class":
            raise ValueError("research task expected source class is unknown")
        if field == "approved_domains":
            raise ValueError("research task domain filter is invalid")
        if field == "time_window":
            raise ValueError("research task time window is invalid")
        if field == "queries":
            raise ValueError("research task queries are invalid")
    missing = sorted(
        {str(error["loc"][0]) for error in errors if error["type"] == "missing"}
    )
    if missing:
        raise ValueError(f"research task is missing required field: {missing[0]}")
    raise ValueError("research task is invalid")


def build_research_result(*, task, provider_payload, result_id, searched_at):
    if not isinstance(result_id, str) or not result_id:
        raise ValueError("research result id is required")
    if not isinstance(searched_at, str) or not searched_at:
        raise ValueError("research searched_at is required")
    validated_task = validate_research_task(task, explicit_deep=True)
    provider = _validate_provider_payload(provider_payload)
    sources = _normalize_sources(provider["sources"], searched_at)
    source_by_canonical = {source["canonical_url"]: source for source in sources}
    findings = _normalize_findings(provider["findings"], source_by_canonical)
    search_calls = _normalize_search_calls(provider["search_calls"])
    result = {
        "research_result_id": result_id,
        "artifact_schema_version": RESEARCH_SCHEMA_VERSION,
        "authority": "external_research",
        "market_setup_relation": "non_decision",
        "task": validated_task,
        "provider_metadata": provider["provider_metadata"],
        "searched_at": searched_at,
        "search_calls": search_calls,
        "sources": sources,
        "findings": findings,
        "object_index": _build_research_objects(sources, findings),
    }
    result["result_hash"] = compute_result_hash(result)
    envelope = _build_envelope(result, result_id)
    validate_artifact(envelope)
    return result


def _validate_provider_payload(payload):
    if not isinstance(payload, dict):
        raise ValueError("provider payload is required")
    try:
        validated = _ProviderPayload.model_validate(payload)
    except ValidationError as exc:
        _raise_provider_validation_error(exc)
    return validated.model_dump()


def _raise_provider_validation_error(exc) -> NoReturn:
    errors = exc.errors()
    for error in errors:
        if error["type"] == "extra_forbidden":
            raise ValueError("extra inputs are not permitted")
    for error in errors:
        loc = error.get("loc", ())
        field = str(loc[0]) if loc else ""
        if field == "provider_metadata":
            raise ValueError("provider metadata is invalid")
        if field == "search_calls":
            raise ValueError("provider search calls are invalid")
        if field == "sources":
            raise ValueError("provider source is invalid")
        if field == "findings":
            raise ValueError("provider finding is invalid")
    missing = sorted(
        {str(error["loc"][0]) for error in errors if error["type"] == "missing"}
    )
    if missing:
        raise ValueError(f"provider payload is missing required field: {missing[0]}")
    raise ValueError("provider payload is invalid")


def _normalize_sources(provider_sources, searched_at):
    by_canonical = {}
    for source in provider_sources:
        canonical_url = _canonical_url(source["url"])
        title = source.get("title") or ""
        publisher = source.get("publisher") or _url_host(canonical_url)
        if not title.strip() and not publisher:
            raise ValueError("research source title or domain is required")
        spans = _non_empty_strings(
            source.get("cited_spans"), "research source cited spans are required"
        )
        record = by_canonical.get(canonical_url)
        if record is None:
            record = {
                "source_id": None,
                "canonical_url": canonical_url,
                "title": title,
                "publisher": publisher,
                "publication_date": _optional_iso_date(
                    source.get("publication_date"),
                    "research source publication date",
                ),
                "event_date": _optional_iso_date(
                    source.get("event_date"), "research source event date"
                ),
                "retrieved_at": source.get("retrieved_at") or searched_at,
                "cited_spans": list(spans),
            }
            by_canonical[canonical_url] = record
        else:
            record["cited_spans"] = _merge_spans(record["cited_spans"], spans)
    ordered = [by_canonical[url] for url in sorted(by_canonical)]
    for index, record in enumerate(ordered, start=1):
        record["source_id"] = f"src_{index}"
    return ordered


def _normalize_findings(provider_findings, source_by_canonical):
    findings = []
    for index, finding in enumerate(provider_findings, start=1):
        statement = finding["statement"]
        if not statement.strip():
            raise ValueError("research finding statement is required")
        citations = finding["citations"]
        if not citations:
            raise ValueError("research finding requires at least one citation")
        source_refs = []
        spans = []
        for citation in citations:
            url = citation.get("url")
            if not isinstance(url, str) or not url:
                raise ValueError("research finding citation url is required")
            canonical_url = _canonical_url(url)
            source = source_by_canonical.get(canonical_url)
            if source is None:
                raise ValueError("research finding cites an unknown source")
            source_ref = source["source_id"]
            if source_ref not in source_refs:
                source_refs.append(source_ref)
            span = citation.get("span")
            if not isinstance(span, str) or not span.strip():
                raise ValueError("research finding citation is missing a cited span")
            spans.append(span.strip())
        findings.append(
            {
                "finding_id": f"fnd_{index}",
                "statement": statement.strip(),
                "purpose": finding["purpose"],
                "framing": finding["framing"],
                "source_refs": source_refs,
                "cited_spans": spans,
            }
        )
    return findings


def _normalize_search_calls(search_calls):
    normalized = []
    for call in search_calls:
        query = call.get("query")
        if not isinstance(query, str) or not query.strip():
            raise ValueError("research search call query is required")
        if _QUERY_FORBIDDEN_RE.search(query):
            raise ValueError("research search call query contains forbidden content")
        record = {"query": query.strip()}
        if call.get("search_call_id"):
            record["search_call_id"] = call["search_call_id"]
        if call.get("occurred_at"):
            record["occurred_at"] = call["occurred_at"]
        normalized.append(record)
    return normalized


def _non_empty_strings(value, message):
    if not isinstance(value, list) or not value:
        raise ValueError(message)
    normalized = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(message)
        normalized.append(item.strip())
    return normalized


def _merge_spans(existing, incoming):
    merged = list(existing)
    for span in incoming:
        if span not in merged:
            merged.append(span)
    return merged


def _optional_iso_date(value, label):
    if not value:
        return None
    _parse_iso_date(value, label)
    return value


def _canonical_url(url):
    if not isinstance(url, str) or not url:
        raise ValueError("research source url is required")
    try:
        parsed = urlsplit(url)
    except ValueError as exc:
        raise ValueError("research source url is invalid") from exc
    scheme = parsed.scheme.lower()
    if scheme not in _APPROVED_SCHEMES:
        raise ValueError("research source url scheme is not approved")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("research source url contains credentials")
    host = parsed.hostname
    if not host:
        raise ValueError("research source url is invalid")
    host = host.lower().rstrip(".")
    if _is_private_host(host):
        raise ValueError("research source url is private")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("research source url is invalid") from exc
    netloc = host
    if port is not None and not _is_default_port(scheme, port):
        netloc = f"{host}:{port}"
    path = parsed.path
    if path != "/":
        path = path.rstrip("/")
    return urlunsplit((scheme, netloc, path, parsed.query, ""))


def _url_host(url):
    try:
        parsed = urlsplit(url)
    except ValueError as exc:
        raise ValueError("research source url is invalid") from exc
    host = parsed.hostname
    if not host:
        raise ValueError("research source url is invalid")
    return host.lower().rstrip(".")


def _is_private_host(host):
    return _PRIVATE_HOST_RE.search(host) is not None


def _is_default_port(scheme, port):
    return (scheme == "http" and port == 80) or (scheme == "https" and port == 443)


def _build_research_objects(sources, findings):
    objects = []
    for source in sources:
        objects.append(
            {
                "object_type": "research_source",
                "object_id": source["source_id"],
                "authority": "external_research",
                "payload": source,
            }
        )
    for finding in findings:
        objects.append(
            {
                "object_type": "research_finding",
                "object_id": finding["finding_id"],
                "authority": "external_research",
                "payload": finding,
            }
        )
    return build_object_index(objects)


def _build_envelope(result, result_id):
    envelope = {
        "artifact_id": result_id,
        "artifact_kind": "research_result",
        "schema_version": RESEARCH_SCHEMA_VERSION,
        "primary_authority": "external_research",
        "market_setup_relation": "non_decision",
        "payload": result,
        "object_index": result["object_index"],
    }
    envelope["integrity_hash"] = _hash_excluding(envelope, "integrity_hash")
    return envelope


def _hash_excluding(payload, excluded_key):
    projection = {key: value for key, value in payload.items() if key != excluded_key}
    return _sha256(projection)


def canonical_json(payload):
    if not isinstance(payload, dict):
        raise ValueError("canonical payload must be a dictionary")
    return json.dumps(
        _canonicalize(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _canonicalize(value):
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("canonical payload contains a non-finite number")
        if isinstance(value, float) and value == 0.0:
            return 0.0
        return value
    if isinstance(value, (list, tuple)):
        return [_canonicalize(item) for item in value]
    if isinstance(value, dict):
        return {
            unicodedata.normalize("NFC", str(key)): _canonicalize(item)
            for key, item in value.items()
        }
    if value is None:
        return None
    raise ValueError("canonical payload contains an unsupported value type")


def _sha256(payload):
    return hashlib.sha256(canonical_json(payload)).hexdigest()


def compute_result_hash(result):
    if not isinstance(result, dict):
        raise ValueError("research result is required")
    projection = {key: value for key, value in result.items() if key != "result_hash"}
    return _sha256(projection)

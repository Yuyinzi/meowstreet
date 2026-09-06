import hashlib
import json
from collections.abc import Mapping
import re

from app.agents.catalyst_research.adapters.schema import IRSourceAdapter, validate_adapter_payload
from app.agents.catalyst_research.config import ADAPTER_SCHEMA_VERSION, PROMPT_VERSIONS
from app.agents.catalyst_research.prompts import adapter_generation_prompt


_MAX_HTML_CHARS = 120_000
_MAX_TEXT_CHARS = 8_000
_MAX_LINKS = 40
_MAX_HEADINGS = 20
_MAX_ITEM_TEXT_CHARS = 240
_MAX_PROMPT_CHARS = 120_000
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _canonical_json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(value):
    return hashlib.sha256(_canonical_json(value).encode()).hexdigest()


def _bounded_text(value, limit=_MAX_ITEM_TEXT_CHARS):
    return value[:limit] if isinstance(value, str) else ""


def _bounded_company(company):
    if not isinstance(company, Mapping):
        raise ValueError("company is required")
    return {
        "ticker": _bounded_text(company.get("ticker") or company.get("symbol"), 32),
        "company_name": _bounded_text(company.get("company_name") or company.get("name"), 240),
    }


def _bounded_source(source):
    if not isinstance(source, Mapping):
        raise ValueError("source is required")
    return {
        "source_type": _bounded_text(source.get("source_type"), 64),
        "url": _bounded_text(source.get("url") or source.get("source_url"), 500),
        "allowed_hosts": [_bounded_text(host, 253) for host in source.get("allowed_hosts", [])[:4] if isinstance(host, str)],
    }


def _bounded_normalized(normalized_input):
    if not isinstance(normalized_input, Mapping):
        return {}
    normalized = {}
    if isinstance(normalized_input.get("title"), str):
        normalized["title"] = _bounded_text(normalized_input["title"], 500)
    if isinstance(normalized_input.get("text"), str):
        normalized["text"] = normalized_input["text"][:_MAX_TEXT_CHARS]
    headings = normalized_input.get("headings")
    if isinstance(headings, list):
        normalized["headings"] = [
            {"level": item.get("level"), "text": _bounded_text(item.get("text"))}
            for item in headings[:_MAX_HEADINGS]
            if isinstance(item, Mapping) and isinstance(item.get("level"), int) and isinstance(item.get("text"), str)
        ]
    links = normalized_input.get("links")
    if isinstance(links, list):
        bounded_links = []
        for item in links[:_MAX_LINKS]:
            if not isinstance(item, Mapping) or not isinstance(item.get("href"), str) or not isinstance(item.get("text", ""), str):
                continue
            bounded_item = {
                "href": _bounded_text(item["href"], 500),
                "text": _bounded_text(item.get("text", "")),
            }
            for name in ("aria-label", "class", "data-date", "datetime", "id", "title"):
                if isinstance(item.get(name), str):
                    bounded_item[name] = _bounded_text(item[name])
            bounded_links.append(bounded_item)
        normalized["links"] = bounded_links
    return normalized


def _bounded_snapshot(snapshot):
    if not isinstance(snapshot, Mapping):
        raise ValueError("snapshot is required")
    structural_html = snapshot.get("structural_html")
    if not isinstance(structural_html, str) or not structural_html.strip():
        raise ValueError("bounded structural snapshot is required")
    normalized = _bounded_normalized(snapshot.get("normalized"))
    bounded = {
        "snapshot_schema_version": snapshot.get("snapshot_schema_version"),
        "requested_url": snapshot.get("requested_url"),
        "final_url": snapshot.get("final_url"),
        "content_type": snapshot.get("content_type"),
        "fetched_at": snapshot.get("fetched_at"),
        "response_bytes": snapshot.get("response_bytes"),
        "truncated": bool(snapshot.get("truncated", False)),
        "structural_html": structural_html[:_MAX_HTML_CHARS],
        "normalized": normalized,
        "content_hash": snapshot.get("content_hash"),
    }
    return bounded


def _trusted_fields(company, source):
    if not isinstance(company, Mapping) or not isinstance(source, Mapping):
        raise ValueError("company and source are required")
    ticker = company.get("ticker") or company.get("symbol")
    source_url = source.get("url") or source.get("source_url")
    allowed_hosts = source.get("allowed_hosts")
    source_type = source.get("source_type")
    if not ticker or not source_url or not source_type or not isinstance(allowed_hosts, list):
        raise ValueError("trusted adapter fields are incomplete")
    return {
        "schema_version": ADAPTER_SCHEMA_VERSION,
        "ticker": ticker,
        "source_type": source_type,
        "source_url": source_url,
        "allowed_hosts": allowed_hosts,
    }


def _snapshot_hash(snapshot):
    computed = hashlib.sha256(snapshot["structural_html"].encode()).hexdigest()
    supplied = snapshot.get("content_hash")
    if isinstance(supplied, str) and _SHA256_RE.fullmatch(supplied) and supplied == computed:
        return supplied
    return computed


def _bounded_prompt_inputs(company, source, snapshot):
    bounded_company = _bounded_company(company)
    bounded_source = _bounded_source(source)
    bounded_snapshot = _bounded_snapshot(snapshot)
    for html_limit in (50_000, 30_000, 10_000, 0):
        bounded_snapshot["structural_html"] = bounded_snapshot["structural_html"][:html_limit]
        prompt = adapter_generation_prompt(bounded_company, bounded_source, bounded_snapshot)
        if len(_canonical_json(prompt)) <= _MAX_PROMPT_CHARS:
            return bounded_company, bounded_source, bounded_snapshot, prompt
    raise ValueError("adapter generation input exceeds bound")


async def generate_adapter(company: dict, source: dict, snapshot: dict, *, llm_client, model: str) -> dict:
    if not isinstance(model, str) or not model.strip():
        raise ValueError("model is required")
    provenance_snapshot = _bounded_snapshot(snapshot)
    source_snapshot_hash = _snapshot_hash(provenance_snapshot)
    bounded_company, bounded_source, bounded_snapshot, prompt = _bounded_prompt_inputs(company, source, snapshot)
    trusted = _trusted_fields(company, source)
    response = await llm_client.responses.parse(model=model, input=prompt, text_format=IRSourceAdapter)
    parsed = getattr(response, "output_parsed", None)
    if parsed is None:
        raise ValueError("adapter generation response is missing")
    if hasattr(parsed, "model_dump"):
        payload = parsed.model_dump(mode="json")
    elif isinstance(parsed, Mapping):
        payload = dict(parsed)
    else:
        raise ValueError("adapter generation response is invalid")
    adapter_payload = validate_adapter_payload(payload, trusted)
    input_hash = _hash({"company": bounded_company, "source": bounded_source, "snapshot": bounded_snapshot})
    output_hash = _hash(adapter_payload)
    result = {
        "status": "candidate",
        "adapter": adapter_payload,
        "adapter_json": adapter_payload,
        "generation_model": model,
        "prompt_schema_version": PROMPT_VERSIONS["adapter_generation"],
        "source_snapshot_hash": source_snapshot_hash,
        "input_hash": input_hash,
        "output_hash": output_hash,
    }
    result.update(adapter_payload)
    return result

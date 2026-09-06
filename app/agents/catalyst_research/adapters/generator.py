import hashlib
import json
from collections.abc import Mapping

from app.agents.catalyst_research.adapters.schema import IRSourceAdapter, validate_adapter_payload
from app.agents.catalyst_research.config import ADAPTER_SCHEMA_VERSION, PROMPT_VERSIONS
from app.agents.catalyst_research.prompts import adapter_generation_prompt


_MAX_HTML_CHARS = 120_000
_MAX_TEXT_CHARS = 40_000
_MAX_LINKS = 500
_MAX_HEADINGS = 100


def _canonical_json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(value):
    return hashlib.sha256(_canonical_json(value).encode()).hexdigest()


def _bounded_snapshot(snapshot):
    if not isinstance(snapshot, Mapping):
        raise ValueError("snapshot is required")
    structural_html = snapshot.get("structural_html")
    if not isinstance(structural_html, str) or not structural_html.strip():
        raise ValueError("bounded structural snapshot is required")
    normalized_input = snapshot.get("normalized")
    normalized = {}
    if isinstance(normalized_input, Mapping):
        for key in ("title", "text", "headings", "links"):
            value = normalized_input.get(key)
            if key == "text" and isinstance(value, str):
                normalized[key] = value[:_MAX_TEXT_CHARS]
            elif key == "title" and isinstance(value, str):
                normalized[key] = value[:2_000]
            elif key == "headings" and isinstance(value, list):
                normalized[key] = value[:_MAX_HEADINGS]
            elif key == "links" and isinstance(value, list):
                normalized[key] = value[:_MAX_LINKS]
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


async def generate_adapter(company: dict, source: dict, snapshot: dict, *, llm_client, model: str) -> dict:
    if not isinstance(model, str) or not model.strip():
        raise ValueError("model is required")
    bounded_snapshot = _bounded_snapshot(snapshot)
    trusted = _trusted_fields(company, source)
    prompt = adapter_generation_prompt(company, source, bounded_snapshot)
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
    input_hash = _hash({"company": company, "source": source, "snapshot": bounded_snapshot})
    output_hash = _hash(adapter_payload)
    result = {
        "status": "candidate",
        "adapter": adapter_payload,
        "adapter_json": adapter_payload,
        "generation_model": model,
        "prompt_schema_version": PROMPT_VERSIONS["adapter_generation"],
        "source_snapshot_hash": bounded_snapshot.get("content_hash") or _hash(bounded_snapshot),
        "input_hash": input_hash,
        "output_hash": output_hash,
    }
    result.update(adapter_payload)
    return result

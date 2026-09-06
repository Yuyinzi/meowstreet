from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.agents.catalyst_research.adapters.schema import (
    IRSourceAdapter,
    validate_adapter_payload,
)


def adapter_payload():
    return {
        "schema_version": "ir_source_adapter_v1",
        "ticker": "NVDA",
        "source_type": "press_releases",
        "source_url": "https://investor.example.com/news",
        "allowed_hosts": ["investor.example.com"],
        "access_mode": "html",
        "extraction": {
            "item_selector": ".news-item",
            "date": {
                "selector": "time",
                "value_source": "text",
                "attribute": None,
                "formats": ["%B %d, %Y"],
            },
            "title": {
                "selector": ".news-title",
                "value_source": "text",
                "attribute": None,
            },
            "url": {
                "selector": ".news-title",
                "value_source": "attribute",
                "attribute": "href",
            },
        },
        "pagination": {"type": "next_link", "selector": "a.next", "parameter": None, "start": None},
    }


@pytest.mark.parametrize(
    "mutation",
    [
        lambda payload: payload.update(extra=True),
        lambda payload: payload.update(access_mode="json"),
        lambda payload: payload["extraction"].update(item_selector="*"),
        lambda payload: payload["extraction"]["date"].update(value_source="regex"),
        lambda payload: payload["extraction"]["date"].update(attribute="onclick"),
        lambda payload: payload["extraction"]["date"].update(formats=["%Q"]),
        lambda payload: payload.update(allowed_hosts=["localhost"]),
        lambda payload: payload["pagination"].update(type="cursor"),
        lambda payload: payload["pagination"].update(selector=None),
    ],
)
def test_adapter_schema_rejects_unsafe_or_unsupported_payloads(mutation):
    payload = deepcopy(adapter_payload())
    mutation(payload)

    with pytest.raises((ValidationError, ValueError)):
        IRSourceAdapter.model_validate(payload)


def test_adapter_schema_overwrites_identity_with_trusted_fields():
    payload = adapter_payload()
    payload["ticker"] = "OTHER"
    payload["source_type"] = "events_presentations"
    payload["source_url"] = "https://other.example.com/archive"
    payload["allowed_hosts"] = ["other.example.com"]
    payload["schema_version"] = "wrong"

    trusted = {
        "ticker": "NVDA",
        "source_type": "press_releases",
        "source_url": "https://investor.example.com/news",
        "allowed_hosts": ["investor.example.com"],
        "schema_version": "ir_source_adapter_v1",
    }
    result = validate_adapter_payload(payload, trusted)

    assert result["ticker"] == "NVDA"
    assert result["source_type"] == "press_releases"
    assert result["source_url"] == trusted["source_url"]
    assert result["allowed_hosts"] == trusted["allowed_hosts"]
    assert result["schema_version"] == "ir_source_adapter_v1"


def test_events_adapter_allows_missing_url_and_machine_date_attribute():
    payload = adapter_payload()
    payload["source_type"] = "events_presentations"
    payload["extraction"]["date"] = {
        "selector": "[data-date]",
        "value_source": "attribute",
        "attribute": "data-date",
        "formats": ["%Y-%m-%d"],
    }
    payload["extraction"]["url"] = None
    payload["pagination"] = {"type": "none", "selector": None, "parameter": None, "start": None}

    adapter = IRSourceAdapter.model_validate(payload)

    assert adapter.extraction.url is None

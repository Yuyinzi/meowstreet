import json
from pathlib import Path

import pytest

from app.agents.catalyst_research.domain import classify_observations
from app.agents.catalyst_research.statistics import calculate_statistics


FIXTURE = Path(__file__).parent / "fixtures" / "classified_titles.json"


class FakeResponses:
    def __init__(self, rows):
        self.rows = rows
        self.inputs = []

    async def parse(self, *, model, input, text_format):
        self.inputs.append(input)
        requested = json.loads(input[-1]["content"].split("Events to classify:\n", 1)[1])
        selected = [row for row in self.rows if row["id"] in {item["id"] for item in requested}]
        return type("Response", (), {"output_parsed": {"classifications": selected}, "output_text": json.dumps(selected)})()


class FakeClient:
    def __init__(self, rows):
        self.responses = FakeResponses(rows)


class FixedResponseClient:
    def __init__(self, payload):
        self.payload = payload
        self.responses = self
        self.calls = 0

    async def parse(self, **kwargs):
        self.calls += 1
        return type("Response", (), {"output_parsed": self.payload, "output_text": "fixed"})()


def _events():
    return [
        {
            "id": row["id"],
            "title": row["title"],
            "source_type": row["source_type"],
            "count_date": f"2025-{((row['id'] - 1) % 12) + 1:02d}-15",
        }
        for row in json.loads(FIXTURE.read_text())
    ]


@pytest.mark.asyncio
async def test_fixture_classification_uses_narrow_rules_and_bounded_batches():
    labels = json.loads(FIXTURE.read_text())
    llm_rows = [
        {"id": row["id"], "earnings_state": row["expected"], "reason": "fixture label"}
        for row in labels
    ]
    client = FakeClient(llm_rows)

    result = await classify_observations(_events(), llm_client=client, model="test-model", batch_size=50)

    assert result["llm_call_count"] <= 2
    assert all(len(json.loads(call[-1]["content"].split("Events to classify:\n", 1)[1])) <= 50 for call in client.responses.inputs)
    observed = {item["id"]: item["earnings_state"] for item in result["events"]}
    agreement = sum(observed[item["id"]] == item["expected"] for item in labels) / len(labels)
    assert agreement >= 0.95
    assert result["events"] == sorted(result["events"], key=lambda item: item["id"])


@pytest.mark.asyncio
async def test_classification_without_llm_keeps_unresolved_titles_ambiguous():
    result = await classify_observations(
        [{"id": 1, "title": "New product launch", "source_type": "press_releases"}],
    )

    assert result["llm_call_count"] == 0
    assert result["events"][0]["earnings_state"] == "ambiguous"


@pytest.mark.asyncio
async def test_invalid_llm_ids_make_batch_ambiguous():
    client = FakeClient([{"id": 999, "earnings_state": "non_earnings", "reason": "unknown"}])

    result = await classify_observations(
        [
            {"id": 1, "title": "New product launch", "source_type": "press_releases"},
            {"id": 2, "title": "Business update", "source_type": "press_releases"},
        ],
        llm_client=client,
        model="test-model",
    )

    assert [item["earnings_state"] for item in result["events"]] == ["ambiguous", "ambiguous"]


@pytest.mark.asyncio
async def test_missing_or_unknown_id_makes_every_unresolved_event_ambiguous():
    client = FixedResponseClient({"classifications": [{"id": 1, "earnings_state": "non_earnings", "reason": "one"}, {"id": 99, "earnings_state": "non_earnings", "reason": "unknown"}]})

    result = await classify_observations(
        [
            {"id": 1, "title": "Business update", "source_type": "press_releases"},
            {"id": 2, "title": "Product update", "source_type": "press_releases"},
        ],
        llm_client=client,
        model="test-model",
    )

    assert [item["earnings_state"] for item in result["events"]] == ["ambiguous", "ambiguous"]
    assert all(item["classification_method"] == "llm_v1" for item in result["events"])


@pytest.mark.asyncio
async def test_extra_llm_fields_fail_pydantic_validation_and_remain_ambiguous():
    client = FixedResponseClient({"classifications": [{"id": 1, "earnings_state": "non_earnings", "reason": "one", "unexpected": True}]})

    result = await classify_observations(
        [{"id": 1, "title": "Business update", "source_type": "press_releases"}],
        llm_client=client,
        model="test-model",
    )

    assert result["events"][0]["earnings_state"] == "ambiguous"
    assert result["events"][0]["classification_method"] == "llm_v1"


def test_statistics_keep_channels_separate_and_round_rates():
    events = [
        {"source_type": "press_releases", "earnings_state": "earnings"},
        {"source_type": "press_releases", "earnings_state": "non_earnings"},
        {"source_type": "press_releases", "earnings_state": "ambiguous"},
        {"source_type": "events_presentations", "earnings_state": "non_earnings"},
    ]
    sources = [
        {"source_type": "press_releases", "extraction_status": "complete"},
        {"source_type": "events_presentations", "extraction_status": "complete"},
    ]

    result = calculate_statistics(events, sources, {"start": "2024-01-01", "end": "2024-12-31"})

    assert result["press_releases"]["total"] == 3
    assert result["press_releases"]["total"] == sum(result["press_releases"][key] for key in ("earnings", "non_earnings", "ambiguous"))
    assert result["press_releases"]["non_earnings_per_month"] is None
    assert result["events_presentations"]["total"] == 1
    assert result["events_presentations"]["earnings"] == 0
    assert result["events_presentations"]["per_month"] == 0.08


def test_partial_unknown_continuity_keeps_rates_null():
    result = calculate_statistics(
        [{"source_type": "press_releases", "earnings_state": "earnings"}],
        [{"source_type": "press_releases", "extraction_status": "partial", "coverage_start": "2024-01-01", "coverage_end": "2024-06-30"}],
        {"start": "2024-01-01", "end": "2024-12-31"},
    )

    assert result["press_releases"]["status"] == "partial"
    assert result["press_releases"]["per_month"] is None


def test_partial_known_continuity_uses_observed_calendar_window():
    result = calculate_statistics(
        [{"source_type": "press_releases", "earnings_state": "earnings"}],
        [{"source_type": "press_releases", "extraction_status": "partial", "coverage_start": "2024-01-01", "coverage_end": "2024-06-30", "coverage_continuous": True}],
        {"start": "2024-01-01", "end": "2024-12-31"},
    )

    assert result["press_releases"]["window_months"] == 5.95
    assert result["press_releases"]["per_month"] == 0.17


def test_missing_source_is_not_a_zero_archive():
    result = calculate_statistics([], [], {"start": "2024-01-01", "end": "2024-12-31"})

    assert result["press_releases"]["status"] == "missing"
    assert result["press_releases"]["total"] == 0
    assert result["press_releases"]["per_month"] is None


def test_exhausted_zero_archive_reports_zero_rates():
    result = calculate_statistics(
        [],
        [{"source_type": "press_releases", "extraction_status": "complete"}],
        {"start": "2024-01-01", "end": "2024-12-31"},
    )

    assert result["press_releases"]["status"] == "complete"
    assert result["press_releases"]["total"] == 0
    assert result["press_releases"]["per_month"] == 0.0


def test_statistics_are_order_independent():
    events = [
        {"source_type": "press_releases", "earnings_state": state}
        for state in ("earnings", "non_earnings", "ambiguous")
    ]
    source = [{"source_type": "press_releases", "extraction_status": "complete"}]
    requested = {"start": "2024-01-01", "end": "2024-12-31"}

    assert json.dumps(calculate_statistics(events, source, requested), sort_keys=True) == json.dumps(calculate_statistics(list(reversed(events)), source, requested), sort_keys=True)

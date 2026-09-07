import json
from pathlib import Path

import pytest

from app.agents.catalyst_research.domain import classify_observations
from app.agents.catalyst_research.statistics import calculate_statistics


FIXTURE = Path(__file__).parent / "fixtures" / "classified_titles.json"


class FakeResponses:
    def __init__(self, rows):
        self.rows_by_title = {row["title"]: row for row in rows if "title" in row}
        self.inputs = []

    async def parse(self, *, model, input, text_format):
        self.inputs.append(input)
        requested = json.loads(input[-1]["content"].split("Events to classify:\n", 1)[1])
        selected = []
        for item in requested:
            row = self.rows_by_title.get(item["title"])
            if row:
                selected.append({"id": item["id"], "earnings_state": row["earnings_state"], "reason": "independent title taxonomy"})
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


class RaisingResponseClient:
    def __init__(self, error):
        self.responses = self
        self.error = error
        self.calls = 0

    async def parse(self, **kwargs):
        self.calls += 1
        raise self.error


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


def _stat_event(state, source_type="press_releases", day="2024-01-01", slug=None):
    slug = slug or state
    return {
        "source_type": source_type,
        "earnings_state": state,
        "count_date": day,
        "title": f"{slug} announcement",
        "normalized_title": f"{slug} announcement",
        "canonical_url": f"https://example.com/{slug}",
    }


def _independent_model_taxonomy(title):
    normalized = title.casefold()
    if any(token in normalized for token in ("financial results", "earnings", "results webcast", "results call")):
        return "earnings"
    if any(token in normalized for token in ("update", "results discussion", "financial highlights", "presentation", "review", "outlook", "performance", "guidance", "product results", "program results", "momentum", "highlights", "briefing", "customer migration", "fleet pilot")):
        return "ambiguous"
    return "non_earnings"


@pytest.mark.asyncio
async def test_fixture_classification_uses_narrow_rules_and_bounded_batches():
    labels = json.loads(FIXTURE.read_text())
    assert len(labels) >= 100
    assert len({row["title"] for row in labels}) == len(labels)
    assert all(row.get("label_provenance") and row.get("label_reason") for row in labels)
    assert {row["source_type"] for row in labels} == {"press_releases", "events_presentations"}
    assert {row["expected"] for row in labels} == {"earnings", "non_earnings", "ambiguous"}
    llm_rows = [
        {"title": row["title"], "earnings_state": _independent_model_taxonomy(row["title"])}
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
    deterministic = sum(item["classification_method"] == "rule_v1" for item in result["events"])
    assert 0 < deterministic < len(labels)


@pytest.mark.asyncio
async def test_classification_without_llm_keeps_unresolved_titles_ambiguous():
    result = await classify_observations(
        [{"id": 1, "title": "New product launch", "source_type": "press_releases"}],
    )

    assert result["llm_call_count"] == 0
    assert result["events"][0]["earnings_state"] == "ambiguous"


@pytest.mark.asyncio
async def test_invalid_llm_ids_make_batch_ambiguous():
    client = FixedResponseClient({"classifications": [{"id": 999, "earnings_state": "non_earnings", "reason": "unknown"}]})

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
        _stat_event("earnings", slug="earnings"),
        _stat_event("non_earnings", slug="non-earnings"),
        _stat_event("ambiguous", slug="ambiguous"),
        _stat_event("non_earnings", source_type="events_presentations", slug="events-non-earnings"),
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
        [_stat_event("earnings")],
        [{"source_type": "press_releases", "extraction_status": "partial", "coverage_start": "2024-01-01", "coverage_end": "2024-06-30"}],
        {"start": "2024-01-01", "end": "2024-12-31"},
    )

    assert result["press_releases"]["status"] == "partial"
    assert result["press_releases"]["per_month"] is None


def test_partial_known_continuity_uses_observed_calendar_window():
    result = calculate_statistics(
        [_stat_event("earnings")],
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
        _stat_event(state, slug=state)
        for state in ("earnings", "non_earnings", "ambiguous")
    ]
    source = [{"source_type": "press_releases", "extraction_status": "complete"}]
    requested = {"start": "2024-01-01", "end": "2024-12-31"}

    assert json.dumps(calculate_statistics(events, source, requested), sort_keys=True) == json.dumps(calculate_statistics(list(reversed(events)), source, requested), sort_keys=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid_id", [True, 0, -3, "external-1", []])
async def test_invalid_explicit_ids_are_preserved_and_never_sent_to_llm(invalid_id):
    client = FixedResponseClient({"classifications": []})
    event = {"id": invalid_id, "title": "Business update", "source_type": "press_releases"}

    result = await classify_observations([event], llm_client=client, model="test-model")

    assert result["events"][0]["id"] == invalid_id
    assert result["events"][0]["classification_input_id"] == 1
    assert result["events"][0]["earnings_state"] == "ambiguous"
    assert client.calls == 0


@pytest.mark.asyncio
async def test_duplicate_explicit_ids_are_preserved_and_never_sent_to_llm():
    client = FixedResponseClient({"classifications": []})
    events = [
        {"id": 7, "title": "Business update", "source_type": "press_releases"},
        {"id": 7, "title": "Product launch", "source_type": "press_releases"},
    ]

    result = await classify_observations(events, llm_client=client, model="test-model")

    assert [item["id"] for item in result["events"]] == [7, 7]
    assert [item["classification_input_id"] for item in result["events"]] == [1, 2]
    assert all(item["earnings_state"] == "ambiguous" for item in result["events"])
    assert client.calls == 0


@pytest.mark.asyncio
async def test_llm_provenance_is_attached_to_each_event_and_batch():
    client = FixedResponseClient({"classifications": [
        {"id": 1, "earnings_state": "non_earnings", "reason": "independent model output"},
        {"id": 2, "earnings_state": "ambiguous", "reason": "independent model output"},
    ]})
    events = [
        {"id": 1, "title": "Business update", "source_type": "press_releases"},
        {"id": 2, "title": "Investor presentation", "source_type": "press_releases"},
    ]

    result = await classify_observations(events, llm_client=client, model="test-model")

    assert result["provenance"][0]["event_ids"] == [1, 2]
    assert result["provenance"][0]["batch_index"] == 0
    assert result["provenance"][0]["model"] == "test-model"
    assert result["provenance"][0]["prompt_schema_version"] == "classification_v1"
    assert result["provenance"][0]["input_hash"]
    assert result["provenance"][0]["output_hash"]
    for event in result["events"]:
        assert event["classification_method"] == "llm_v1"
        assert event["model"] == "test-model"
        assert event["prompt_schema_version"] == "classification_v1"
        assert event["input_hash"] == result["provenance"][0]["input_hash"]
        assert event["output_hash"] == result["provenance"][0]["output_hash"]


@pytest.mark.asyncio
async def test_model_exception_keeps_batch_ambiguous_without_error_text_leak():
    client = RaisingResponseClient(RuntimeError("secret provider payload"))

    result = await classify_observations(
        [{"id": 1, "title": "Business update", "source_type": "press_releases"}],
        llm_client=client,
        model="test-model",
    )

    assert result["events"][0]["earnings_state"] == "ambiguous"
    assert result["events"][0]["output_hash"] is None
    assert result["provenance"][0]["output_hash"] is None
    assert "secret provider payload" not in json.dumps(result)


@pytest.mark.asyncio
async def test_rule_event_is_not_sent_and_unknown_rule_id_invalidates_affected_batch():
    client = FixedResponseClient({"classifications": [{"id": 1, "earnings_state": "non_earnings", "reason": "rule override"}, {"id": 2, "earnings_state": "non_earnings", "reason": "valid"}]})

    result = await classify_observations(
        [
            {"id": 1, "title": "Q1 Financial Results", "source_type": "press_releases"},
            {"id": 2, "title": "Business update", "source_type": "press_releases"},
        ],
        llm_client=client,
        model="test-model",
    )

    assert result["events"][0]["earnings_state"] == "earnings"
    assert result["events"][0]["classification_method"] == "rule_v1"
    assert result["events"][1]["earnings_state"] == "ambiguous"
    assert client.calls == 1


@pytest.mark.asyncio
async def test_missing_id_is_generated_only_when_id_field_is_absent():
    result = await classify_observations(
        [{"title": "Business update", "source_type": "press_releases"}],
    )

    assert result["events"][0]["id"] == 1
    assert "classification_input_id" not in result["events"][0]


def test_statistics_reject_unknown_source_status_instead_of_zero_archive():
    result = calculate_statistics(
        [],
        [{"source_type": "press_releases", "extraction_status": "pending"}],
        {"start": "2024-01-01", "end": "2024-12-31"},
    )

    assert result["press_releases"]["status"] == "pending"
    assert result["press_releases"]["window_months"] is None
    assert result["press_releases"]["per_month"] is None


@pytest.mark.parametrize("status", ["unsupported", "failed", "unsupported_access_mode"])
def test_statistics_preserve_non_complete_source_status(status):
    result = calculate_statistics(
        [],
        [{"source_type": "press_releases", "extraction_status": status}],
        {"start": "2024-01-01", "end": "2024-12-31"},
    )

    assert result["press_releases"]["status"] == status
    assert result["press_releases"]["window_months"] is None


@pytest.mark.parametrize(
    "event",
    [
        {"source_type": "other", "earnings_state": "earnings", "count_date": "2024-01-01", "title": "A", "canonical_url": "https://example.com/a"},
        {"source_type": "press_releases", "earnings_state": "maybe", "count_date": "2024-01-01", "title": "A", "canonical_url": "https://example.com/a"},
        {"source_type": "press_releases", "earnings_state": "earnings", "count_date": "not-a-date", "title": "A", "canonical_url": "https://example.com/a"},
        {"source_type": "press_releases", "earnings_state": "earnings", "count_date": "2023-12-31", "title": "A", "canonical_url": "https://example.com/a"},
        {"source_type": "press_releases", "earnings_state": "earnings", "count_date": "2024-01-01", "title": "", "canonical_url": "https://example.com/a"},
        {"source_type": "press_releases", "earnings_state": "earnings", "count_date": "2024-01-01", "title": "A", "canonical_url": "https://example.com/a", "normalized_title": ""},
    ],
)
def test_statistics_reject_invalid_event_observations(event):
    with pytest.raises(ValueError):
        calculate_statistics(
            [event],
            [{"source_type": "press_releases", "extraction_status": "complete"}],
            {"start": "2024-01-01", "end": "2024-12-31"},
        )


def test_statistics_reject_duplicate_canonical_observation_keys():
    event = {"source_type": "press_releases", "earnings_state": "earnings", "count_date": "2024-01-01", "title": "A", "normalized_title": "a", "canonical_url": "https://example.com/a"}

    with pytest.raises(ValueError, match="duplicate event"):
        calculate_statistics(
            [event, dict(event)],
            [{"source_type": "press_releases", "extraction_status": "complete"}],
            {"start": "2024-01-01", "end": "2024-12-31"},
        )


def test_statistics_reject_caller_normalized_title_that_disagrees_with_domain_normalization():
    event = _stat_event("earnings", slug="Title")
    event["title"] = "  Mixed  Title "
    event["normalized_title"] = "mixed title forged"

    with pytest.raises(ValueError, match="normalized title is inconsistent"):
        calculate_statistics(
            [event],
            [{"source_type": "press_releases", "extraction_status": "complete"}],
            {"start": "2024-01-01", "end": "2024-12-31"},
        )


def test_statistics_reject_count_date_and_date_mismatch():
    event = _stat_event("earnings")
    event["date"] = "2024-01-02"

    with pytest.raises(ValueError, match="count date is inconsistent"):
        calculate_statistics(
            [event],
            [{"source_type": "press_releases", "extraction_status": "complete"}],
            {"start": "2024-01-01", "end": "2024-12-31"},
        )


def test_statistics_reject_invalid_source_rows():
    with pytest.raises(ValueError, match="source is invalid"):
        calculate_statistics([], ["not-a-source"], {"start": "2024-01-01", "end": "2024-12-31"})

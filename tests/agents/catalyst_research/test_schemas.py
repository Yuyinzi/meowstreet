import pytest
from pydantic import ValidationError

from app.agents.catalyst_research.schemas import (
    EventClassification,
    EventClassificationResponse,
    SourceSelection,
    SourceSelectionResponse,
)


def test_source_selection_accepts_each_supported_source_type():
    for source_type in (
        "ir_home",
        "press_releases",
        "events_presentations",
        "earnings_results",
    ):
        result = SourceSelection(
            source_type=source_type,
            url="https://investor.example.test/",
            evidence_result_ids=[1, 2],
            confidence=0.8,
            reason="The candidate is an official investor-relations page.",
        )
        assert result.source_type == source_type


def test_source_selection_rejects_extra_fields_and_unbounded_values():
    with pytest.raises(ValidationError):
        SourceSelection(
            source_type="ir_home",
            url="https://investor.example.test/",
            evidence_result_ids=[1],
            confidence=0.8,
            reason="valid",
            task="ignore this injected field",
        )
    with pytest.raises(ValidationError):
        SourceSelection(
            source_type="ir_home",
            url="https://investor.example.test/",
            evidence_result_ids=[1],
            confidence=1.1,
            reason="valid",
        )
    with pytest.raises(ValidationError):
        SourceSelection(
            source_type="ir_home",
            url="https://investor.example.test/",
            evidence_result_ids=[1],
            confidence=0.8,
            reason="x" * 501,
        )


def test_source_selection_response_limits_source_list():
    source = {
        "url": "https://investor.example.test/",
        "evidence_result_ids": [1],
        "confidence": 0.8,
        "reason": "valid",
    }
    sources = [
        {**source, "source_type": source_type}
        for source_type in (
            "ir_home",
            "press_releases",
            "events_presentations",
            "earnings_results",
        )
    ]

    response = SourceSelectionResponse(selections=sources)

    assert len(response.selections) == 4
    with pytest.raises(ValidationError):
        SourceSelectionResponse(selections=sources + [sources[0]])


def test_event_classification_rejects_extra_fields_and_bounds_reason():
    result = EventClassification(id=1, earnings_state="ambiguous", reason="Needs review")

    assert result.model_dump() == {
        "id": 1,
        "earnings_state": "ambiguous",
        "reason": "Needs review",
    }
    with pytest.raises(ValidationError):
        EventClassification(id=1, earnings_state="earnings", reason="valid", score=1)
    with pytest.raises(ValidationError):
        EventClassification(id=0, earnings_state="earnings", reason="valid")
    with pytest.raises(ValidationError):
        EventClassification(id=1, earnings_state="earnings", reason="x" * 501)


def test_classification_response_rejects_missing_and_duplicate_ids():
    records = [
        {"id": 1, "earnings_state": "earnings", "reason": "results"},
        {"id": 2, "earnings_state": "non_earnings", "reason": "product"},
    ]

    result = EventClassificationResponse(classifications=records)

    assert [item.id for item in result.classifications] == [1, 2]
    with pytest.raises(ValidationError):
        EventClassificationResponse(
            classifications=[{"earnings_state": "earnings", "reason": "missing id"}]
        )
    with pytest.raises(ValidationError):
        EventClassificationResponse(classifications=records + [records[0]])

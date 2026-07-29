import asyncio
import json

from app.db import us_rates_liquidity
from scripts import generate_fomc_minutes_structure


def test_target_events_only_include_events_with_statement_tone_and_minutes_doc():
    events = [
        {"event_id": "fomc_2026_06_16", "start_date": "2026-06-16"},
        {"event_id": "fomc_2026_07_28", "start_date": "2026-07-28"},
    ]
    minutes_docs = {"fomc_2026_06_16": {"source_hash": "minutes_hash"}}
    statement_tones = {"fomc_2026_06_16": {"marker_tone": "hawkish"}}

    result = generate_fomc_minutes_structure.target_events(
        events,
        minutes_docs,
        statement_tones,
    )

    assert result == [{"event_id": "fomc_2026_06_16", "start_date": "2026-06-16"}]


def test_should_skip_approved_minutes_extraction_when_hash_matches():
    existing = {
        "event_id": "fomc_2026_06_16",
        "source_hash": "abc123",
        "extraction_status": "approved",
    }

    assert generate_fomc_minutes_structure.should_skip_existing_extraction(
        existing,
        "abc123",
        force=False,
    )


def test_should_not_skip_non_approved_minutes_extraction():
    existing = {
        "event_id": "fomc_2026_06_16",
        "source_hash": "abc123",
        "extraction_status": "rejected",
    }

    assert not generate_fomc_minutes_structure.should_skip_existing_extraction(
        existing,
        "abc123",
        force=False,
    )


def test_should_not_skip_approved_minutes_extraction_when_forced():
    existing = {
        "event_id": "fomc_2026_06_16",
        "source_hash": "abc123",
        "extraction_status": "approved",
    }

    assert not generate_fomc_minutes_structure.should_skip_existing_extraction(
        existing,
        "abc123",
        force=True,
    )


def test_pending_events_excludes_existing_minutes_extraction_when_not_forced():
    event = {"event_id": "fomc_2026_06_16", "start_date": "2026-06-16"}
    minutes_docs = {"fomc_2026_06_16": {"source_hash": "minutes_hash"}}
    statement_tones = {"fomc_2026_06_16": {"marker_tone": "hawkish"}}
    existing = {
        ("fomc_2026_06_16", "minutes", "minutes_hash"): {
            "event_id": "fomc_2026_06_16",
            "source_hash": "minutes_hash",
            "extraction_status": "approved",
        }
    }

    pending = generate_fomc_minutes_structure.pending_events(
        [event],
        minutes_docs,
        statement_tones,
        lambda event_id, document_type, source_hash: existing.get(
            (event_id, document_type, source_hash)
        ),
        force=False,
    )

    assert pending == []


def test_pending_events_keeps_approved_minutes_extraction_when_forced():
    event = {"event_id": "fomc_2026_06_16", "start_date": "2026-06-16"}
    minutes_docs = {"fomc_2026_06_16": {"source_hash": "minutes_hash"}}
    statement_tones = {"fomc_2026_06_16": {"marker_tone": "hawkish"}}
    existing = {
        ("fomc_2026_06_16", "minutes", "minutes_hash"): {
            "event_id": "fomc_2026_06_16",
            "source_hash": "minutes_hash",
            "extraction_status": "approved",
        }
    }

    pending = generate_fomc_minutes_structure.pending_events(
        [event],
        minutes_docs,
        statement_tones,
        lambda event_id, document_type, source_hash: existing.get(
            (event_id, document_type, source_hash)
        ),
        force=True,
    )

    assert pending == [
        (
            event,
            {"source_hash": "minutes_hash"},
            {"marker_tone": "hawkish"},
        )
    ]


def test_generate_event_minutes_structure_retries_after_schema_error(
    tmp_path, monkeypatch
):
    con = us_rates_liquidity.connect(tmp_path / "market.sqlite")
    event = {"event_id": "fomc_2026_06_16", "start_date": "2026-06-16"}
    minutes_document = {
        "event_id": "fomc_2026_06_16",
        "source_hash": "minutes_hash",
        "text": "Minutes of the Federal Open Market Committee",
    }
    statement_tone = {
        "policy_action": "hold",
        "guidance_bias": "neutral",
        "language_tone": "hawkish",
        "overall_bias": "mild_hawkish",
        "statement_tone": "hawkish",
        "marker_tone": "hawkish",
        "tone_score": 1,
        "tone_change": "more_hawkish",
    }
    calls = []
    valid_payload = {
        "statement_bias": "hawkish",
        "risk_focus": "inflation",
        "risk_bias": "hawkish",
        "divergence_level": "medium",
        "uncertainty_level": "high",
        "policy_conviction": "divided",
        "minutes_confirmation": "confirmed_but_divided",
        "confidence": "high",
        "participant_distribution": [],
        "facts": [],
        "comparison": {"statement_vs_minutes": {"conclusion": "confirmed_but_divided"}},
        "reason": "schema corrected",
    }

    async def fake_call_json(client, model, prompt):
        calls.append((model, prompt))
        if (
            model == "extractor"
            and len([call for call in calls if call[0] == "extractor"]) == 1
        ):
            return json.dumps(
                {
                    "statement_bias": "mild_hawkish",
                    "risk_focus": "upside inflation risk",
                    "risk_bias": "hawkish",
                    "divergence_level": "moderate",
                    "uncertainty_level": "high",
                    "policy_conviction": "divided",
                    "minutes_confirmation": "confirmed_but_divided",
                    "confidence": "high",
                    "participant_distribution": "many participants",
                    "facts": [],
                    "comparison": "confirmed with division",
                    "reason": "invalid shape",
                }
            )
        if model == "extractor":
            return json.dumps(valid_payload)
        return json.dumps({"approved": True, "feedback": []})

    monkeypatch.setattr(generate_fomc_minutes_structure, "call_json", fake_call_json)

    try:
        result = asyncio.run(
            generate_fomc_minutes_structure.generate_event_minutes_structure(
                con,
                event,
                minutes_document,
                statement_tone,
                client=object(),
                models={"extractor_model": "extractor", "reviewer_model": "reviewer"},
                max_rounds=3,
            )
        )
        row = us_rates_liquidity.load_macro_event_tone_extraction(
            con,
            "fomc_2026_06_16",
            "minutes",
            "minutes_hash",
        )
    finally:
        con.close()

    assert result == 1
    assert row["extraction_status"] == "approved"
    assert row["review_rounds"] == 2
    extractor_prompts = [call[1] for call in calls if call[0] == "extractor"]
    assert "Extractor output failed schema validation" in extractor_prompts[1]

import asyncio
import json

from app.db import us_rates_liquidity
from scripts import generate_fomc_minutes_structure


def test_classify_events_includes_missing_prerequisites_as_unavailable():
    events = [
        {"event_id": "pending"},
        {"event_id": "reused"},
        {"event_id": "no_minutes"},
        {"event_id": "no_statement_tone"},
    ]
    minutes_docs = {
        "pending": {"source_hash": "pending-hash"},
        "reused": {"source_hash": "reused-hash"},
        "no_statement_tone": {"source_hash": "tone-missing-hash"},
    }
    statement_tones = {
        "pending": {"marker_tone": "neutral"},
        "reused": {"marker_tone": "hawkish"},
        "no_minutes": {"marker_tone": "dovish"},
    }
    existing = {"source_hash": "reused-hash", "extraction_status": "approved"}

    classified = generate_fomc_minutes_structure.classify_events(
        events,
        minutes_docs,
        statement_tones,
        lambda event_id, document_type, source_hash: existing
        if event_id == "reused"
        else None,
        force=False,
    )

    assert [item[0]["event_id"] for item in classified["pending"]] == ["pending"]
    assert [item[0]["event_id"] for item in classified["reused"]] == ["reused"]
    assert [item[0]["event_id"] for item in classified["unavailable"]] == [
        "no_minutes",
        "no_statement_tone",
    ]
    assert classified["unavailable"][0][1] == {"reason": "no minutes document"}
    assert classified["unavailable"][1][1] == {
        "reason": "no approved statement tone"
    }


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


def test_classify_events_reuses_matching_approved_minutes_extraction():
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

    classified = generate_fomc_minutes_structure.classify_events(
        [event],
        minutes_docs,
        statement_tones,
        lambda event_id, document_type, source_hash: existing.get(
            (event_id, document_type, source_hash)
        ),
        force=False,
    )

    assert classified["pending"] == []
    assert classified["reused"] == [
        (
            event,
            {
                "minutes_document": minutes_docs[event["event_id"]],
                "existing": existing[("fomc_2026_06_16", "minutes", "minutes_hash")],
            },
        )
    ]


def test_classify_events_keeps_approved_minutes_extraction_when_forced():
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

    classified = generate_fomc_minutes_structure.classify_events(
        [event],
        minutes_docs,
        statement_tones,
        lambda event_id, document_type, source_hash: existing.get(
            (event_id, document_type, source_hash)
        ),
        force=True,
    )

    assert classified["pending"] == [
        (
            event,
            {"source_hash": "minutes_hash"},
            {"marker_tone": "hawkish"},
        )
    ]


def test_no_pending_events_prints_one_summary_without_constructing_client(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setattr(
        generate_fomc_minutes_structure.llm,
        "build_async_client_bundle",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("client must not be constructed")
        ),
    )
    monkeypatch.setattr(
        generate_fomc_minutes_structure,
        "classify_events",
        lambda events, minutes_docs, statement_tones, load_existing, force: {
            "pending": [],
            "reused": [
                (
                    {"event_id": "cached"},
                    {
                        "minutes_document": {},
                        "existing": {},
                    },
                )
            ],
            "unavailable": [({"event_id": "missing"}, {"reason": "no minutes document"})],
        },
    )

    exit_code = generate_fomc_minutes_structure.main(
        ["--all", "--db-path", str(tmp_path / "market.sqlite")]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert output == (
        "fomc_minutes_structure: generated=0 reused=1 unavailable=1 failed=0\n"
    )


def test_verbose_prints_reused_and_unavailable_details(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(
        generate_fomc_minutes_structure,
        "classify_events",
        lambda events, minutes_docs, statement_tones, load_existing, force: {
            "pending": [],
            "reused": [
                (
                    {"event_id": "cached"},
                    {
                        "minutes_document": {"source_hash": "cached-hash"},
                        "existing": {
                            "source_hash": "cached-hash",
                            "generated_at": "2026-02-02Z",
                        },
                    },
                )
            ],
            "unavailable": [
                ({"event_id": "missing"}, {"reason": "no approved statement tone"})
            ],
        },
    )

    exit_code = generate_fomc_minutes_structure.main(
        [
            "--all",
            "--verbose",
            "--db-path",
            str(tmp_path / "market.sqlite"),
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "event: cached" in output
    assert "source_hash: cached-hash" in output
    assert "event: missing" in output
    assert "reason: no approved statement tone" in output
    assert output.endswith(
        "fomc_minutes_structure: generated=0 reused=1 unavailable=1 failed=0\n"
    )


def test_generation_failure_is_visible_without_verbose(tmp_path, monkeypatch, capsys):
    event = {"event_id": "bad-event"}
    monkeypatch.setattr(
        generate_fomc_minutes_structure,
        "classify_events",
        lambda events, minutes_docs, statement_tones, load_existing, force: {
            "pending": [(event, {"source_hash": "bad-hash"}, {"marker_tone": "neutral"})],
            "reused": [],
            "unavailable": [],
        },
    )
    monkeypatch.setattr(
        generate_fomc_minutes_structure,
        "generate_event_minutes_structure",
        lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("bad extraction")),
    )
    monkeypatch.setattr(
        generate_fomc_minutes_structure.llm,
        "build_async_client_bundle",
        lambda *args, **kwargs: {"client": object(), "models": {}},
    )

    exit_code = generate_fomc_minutes_structure.main(
        ["--all", "--db-path", str(tmp_path / "market.sqlite")]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "bad-event" in captured.err
    assert "bad extraction" in captured.err
    assert captured.out.endswith(
        "fomc_minutes_structure: generated=0 reused=0 unavailable=0 failed=1\n"
    )


def test_generate_event_minutes_structure_retries_after_schema_error(
    tmp_path, monkeypatch, capsys
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
    assert capsys.readouterr().out == ""

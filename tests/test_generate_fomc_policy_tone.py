from scripts import generate_fomc_policy_tone


def test_classify_events_counts_pending_reused_and_unavailable(monkeypatch):
    events = [
        {"event_id": "pending", "start_date": "2026-01-01"},
        {"event_id": "reused", "start_date": "2026-02-01"},
        {"event_id": "unavailable", "start_date": "2026-03-01"},
    ]
    documents = {
        "pending": {"source_hash": "pending-hash"},
        "reused": {"source_hash": "reused-hash"},
    }
    existing = {"extraction_status": "approved", "generated_at": "2026-02-02Z"}
    monkeypatch.setattr(
        generate_fomc_policy_tone.us_rates_liquidity,
        "load_macro_event_document",
        lambda con, event_id, document_type: documents.get(event_id),
    )
    monkeypatch.setattr(
        generate_fomc_policy_tone.us_rates_liquidity,
        "load_macro_event_tone_extraction",
        lambda con, event_id, document_type, source_hash: existing
        if event_id == "reused"
        else None,
    )

    classified = generate_fomc_policy_tone.classify_events(None, events, False)

    assert [item[0]["event_id"] for item in classified["pending"]] == ["pending"]
    assert [item[0]["event_id"] for item in classified["reused"]] == ["reused"]
    assert [item[0]["event_id"] for item in classified["unavailable"]] == [
        "unavailable"
    ]


def test_classify_events_force_marks_approved_matching_extraction_pending(monkeypatch):
    event = {"event_id": "reused", "start_date": "2026-02-01"}
    document = {"source_hash": "reused-hash"}
    existing = {"extraction_status": "approved"}
    monkeypatch.setattr(
        generate_fomc_policy_tone.us_rates_liquidity,
        "load_macro_event_document",
        lambda con, event_id, document_type: document,
    )
    monkeypatch.setattr(
        generate_fomc_policy_tone.us_rates_liquidity,
        "load_macro_event_tone_extraction",
        lambda con, event_id, document_type, source_hash: existing,
    )

    classified = generate_fomc_policy_tone.classify_events(None, [event], True)

    assert classified["pending"] == [(event, document)]
    assert classified["reused"] == []


def test_no_pending_events_prints_one_summary_without_constructing_client(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setattr(
        generate_fomc_policy_tone.llm,
        "build_async_client_bundle",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("client must not be constructed")
        ),
    )
    monkeypatch.setattr(
        generate_fomc_policy_tone,
        "classify_events",
        lambda con, events, force: {
            "pending": [],
            "reused": [({"event_id": "cached"}, {})],
            "unavailable": [({"event_id": "missing"}, {})],
        },
    )

    exit_code = generate_fomc_policy_tone.main(
        ["--all", "--db-path", str(tmp_path / "market.sqlite")]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert output == "fomc_policy_tone: generated=0 reused=1 unavailable=1 failed=0\n"


def test_verbose_prints_reused_and_unavailable_details(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(
        generate_fomc_policy_tone,
        "classify_events",
        lambda con, events, force: {
            "pending": [],
            "reused": [
                (
                    {"event_id": "cached"},
                    {"source_hash": "cached-hash", "generated_at": "2026-02-02Z"},
                )
            ],
            "unavailable": [
                ({"event_id": "missing"}, {"reason": "no statement document"})
            ],
        },
    )

    exit_code = generate_fomc_policy_tone.main(
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
    assert "reason: no statement document" in output
    assert output.endswith(
        "fomc_policy_tone: generated=0 reused=1 unavailable=1 failed=0\n"
    )


def test_generation_failure_is_visible_without_verbose(
    tmp_path, monkeypatch, capsys
):
    event = {"event_id": "bad-event"}
    monkeypatch.setattr(
        generate_fomc_policy_tone,
        "classify_events",
        lambda con, events, force: {
            "pending": [(event, {"source_hash": "bad-hash"})],
            "reused": [],
            "unavailable": [],
        },
    )
    monkeypatch.setattr(
        generate_fomc_policy_tone,
        "generate_event_tone",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            ValueError("bad extraction")
        ),
    )
    monkeypatch.setattr(
        generate_fomc_policy_tone.llm,
        "build_async_client_bundle",
        lambda *args, **kwargs: {"client": object(), "models": {}},
    )

    exit_code = generate_fomc_policy_tone.main(
        ["--all", "--db-path", str(tmp_path / "market.sqlite")]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "bad-event" in captured.err
    assert "bad extraction" in captured.err
    assert captured.out.endswith(
        "fomc_policy_tone: generated=0 reused=0 unavailable=0 failed=1\n"
    )


def _patch_successful_event_generation(monkeypatch):
    extraction = {
        "statement_tone": "neutral",
        "minutes_tone": "unknown",
        "marker_tone": "neutral",
        "tone_score": 0,
        "tone_change": "unchanged",
        "confidence": "medium",
        "facts": [],
        "comparison": {},
        "reason": "test extraction",
    }
    async def fake_run_extract_review_loop(*args, **kwargs):
        return {
            "extraction": extraction,
            "reviewer_feedback": [],
            "final_reviewer_feedback": [],
            "extraction_status": "approved",
            "review_rounds": 1,
        }

    monkeypatch.setattr(
        generate_fomc_policy_tone,
        "run_extract_review_loop",
        fake_run_extract_review_loop,
    )
    row = {
        "policy_action": "hold",
        "guidance_bias": "neutral",
        "language_tone": "neutral",
        "overall_bias": "neutral",
        "statement_tone": "neutral",
        "marker_tone": "neutral",
        "tone_change": "unchanged",
        "confidence": "medium",
        "extraction_status": "approved",
        "review_rounds": 1,
    }
    monkeypatch.setattr(
        generate_fomc_policy_tone.fomc_policy_tone,
        "tone_extraction_row",
        lambda **kwargs: row,
    )
    monkeypatch.setattr(
        generate_fomc_policy_tone.us_rates_liquidity,
        "replace_macro_event_tone_extraction",
        lambda con, row: None,
    )


def test_successful_generation_is_compact_by_default(monkeypatch, capsys):
    _patch_successful_event_generation(monkeypatch)

    generate_fomc_policy_tone.asyncio.run(
        generate_fomc_policy_tone.generate_event_tone(
            None,
            [{"event_id": "fomc_2026_07_28", "start_date": "2026-07-28"}],
            {"event_id": "fomc_2026_07_28", "start_date": "2026-07-28"},
            {"source_hash": "current-hash", "url": "https://example.test"},
            object(),
            {"extractor_model": "extractor", "reviewer_model": "reviewer"},
            1,
        )
    )

    assert capsys.readouterr().out == ""


def test_verbose_successful_generation_retains_details(monkeypatch, capsys):
    _patch_successful_event_generation(monkeypatch)

    generate_fomc_policy_tone.asyncio.run(
        generate_fomc_policy_tone.generate_event_tone(
            None,
            [{"event_id": "fomc_2026_07_28", "start_date": "2026-07-28"}],
            {"event_id": "fomc_2026_07_28", "start_date": "2026-07-28"},
            {"source_hash": "current-hash", "url": "https://example.test"},
            object(),
            {"extractor_model": "extractor", "reviewer_model": "reviewer"},
            1,
            verbose=True,
        )
    )

    output = capsys.readouterr().out
    assert "fomc policy tone generation:" in output
    assert "fomc policy tone saved:" in output


def test_run_extract_review_loop_revises_until_approved():
    calls = []

    async def fake_extract(prompt):
        calls.append(("extract", prompt))
        if len([call for call in calls if call[0] == "extract"]) == 1:
            return {
                "statement_tone": "hawkish",
                "minutes_tone": "unknown",
                "marker_tone": "unknown",
                "tone_score": 1,
                "tone_change": "more_hawkish",
                "confidence": "medium",
                "facts": [],
                "comparison": {},
                "reason": "first attempt",
            }
        return {
            "statement_tone": "neutral",
            "minutes_tone": "unknown",
            "marker_tone": "unknown",
            "tone_score": 0,
            "tone_change": "unchanged",
            "confidence": "medium",
            "facts": [],
            "comparison": {},
            "reason": "revised",
        }

    async def fake_review(prompt):
        calls.append(("review", prompt))
        if len([call for call in calls if call[0] == "review"]) == 1:
            return {"approved": False, "feedback": ["Tone change is unsupported."]}
        return {"approved": True, "feedback": []}

    result = generate_fomc_policy_tone.run_extract_review_loop_sync(
        event={"event_id": "fomc_2026_07_28"},
        current_document={"text": "current", "source_hash": "hash2"},
        previous_event={"event_id": "fomc_2026_06_16"},
        previous_document={"text": "previous"},
        extract=fake_extract,
        review=fake_review,
        max_rounds=3,
    )

    assert result["extraction_status"] == "approved"
    assert result["review_rounds"] == 2
    assert result["extraction"]["statement_tone"] == "neutral"
    assert result["reviewer_feedback"] == ["Tone change is unsupported."]
    assert result["final_reviewer_feedback"] == []


def test_run_extract_review_loop_tracks_final_reviewer_feedback_separately():
    async def fake_extract(prompt):
        return {
            "statement_tone": "neutral",
            "minutes_tone": "unknown",
            "marker_tone": "unknown",
            "tone_score": 0,
            "tone_change": "more_hawkish",
            "confidence": "medium",
            "facts": [],
            "comparison": {},
            "reason": "test",
        }

    review_count = 0

    async def fake_review(prompt):
        nonlocal review_count
        review_count += 1
        if review_count == 1:
            return {"approved": False, "feedback": ["Fix voting count."]}
        return {"approved": True, "feedback": ["Approved after correction."]}

    result = generate_fomc_policy_tone.run_extract_review_loop_sync(
        event={"event_id": "fomc_2026_06_16"},
        current_document={"text": "current", "source_hash": "hash2"},
        previous_event={"event_id": "fomc_2026_04_28"},
        previous_document={"text": "previous"},
        extract=fake_extract,
        review=fake_review,
        max_rounds=3,
    )

    assert result["reviewer_feedback"] == [
        "Fix voting count.",
        "Approved after correction.",
    ]
    assert result["final_reviewer_feedback"] == ["Approved after correction."]


def test_run_extract_review_loop_retries_after_schema_error():
    calls = []

    async def fake_extract(prompt):
        calls.append(("extract", prompt))
        if len([call for call in calls if call[0] == "extract"]) == 1:
            raise ValueError("facts must be a JSON array")
        return {
            "statement_tone": "neutral",
            "minutes_tone": "unknown",
            "marker_tone": "unknown",
            "tone_score": 0,
            "tone_change": "unchanged",
            "confidence": "medium",
            "facts": [{"dimension": "policy", "claim": "language was stable"}],
            "comparison": {"policy": {"change": "unchanged"}},
            "reason": "schema corrected",
        }

    async def fake_review(prompt):
        calls.append(("review", prompt))
        return {"approved": True, "feedback": []}

    result = generate_fomc_policy_tone.run_extract_review_loop_sync(
        event={"event_id": "fomc_2026_07_28"},
        current_document={"text": "current", "source_hash": "hash2"},
        previous_event={"event_id": "fomc_2026_06_16"},
        previous_document={"text": "previous"},
        extract=fake_extract,
        review=fake_review,
        max_rounds=3,
    )

    extract_prompts = [call[1] for call in calls if call[0] == "extract"]
    assert result["extraction_status"] == "approved"
    assert result["review_rounds"] == 2
    assert "Extractor output failed schema validation" in extract_prompts[1]


def test_run_extract_review_loop_raises_when_schema_never_valid():
    async def fake_extract(prompt):
        raise ValueError("comparison must be a JSON object")

    async def fake_review(prompt):
        return {"approved": True, "feedback": []}

    raised = False
    try:
        generate_fomc_policy_tone.run_extract_review_loop_sync(
            event={"event_id": "fomc_2026_07_28"},
            current_document={"text": "current", "source_hash": "hash2"},
            previous_event={"event_id": "fomc_2026_06_16"},
            previous_document={"text": "previous"},
            extract=fake_extract,
            review=fake_review,
            max_rounds=2,
        )
    except ValueError as exc:
        assert "valid FOMC tone JSON" in str(exc)
        raised = True
    assert raised


def test_run_extract_review_loop_returns_max_rounds_when_not_approved():
    calls = []

    async def fake_extract(prompt):
        calls.append(("extract", prompt))
        return {
            "statement_tone": "hawkish",
            "minutes_tone": "unknown",
            "marker_tone": "unknown",
            "tone_score": 1,
            "tone_change": "more_hawkish",
            "confidence": "medium",
            "facts": [],
            "comparison": {},
            "reason": "not approved",
        }

    async def fake_review(prompt):
        calls.append(("review", prompt))
        return {"approved": False, "feedback": ["Still unsupported."]}

    result = generate_fomc_policy_tone.run_extract_review_loop_sync(
        event={"event_id": "fomc_2026_07_28"},
        current_document={"text": "current", "source_hash": "hash2"},
        previous_event={"event_id": "fomc_2026_06_16"},
        previous_document={"text": "previous"},
        extract=fake_extract,
        review=fake_review,
        max_rounds=3,
    )

    assert result["extraction_status"] == "max_rounds_reached"
    assert result["review_rounds"] == 3


def test_load_previous_event_and_statement_uses_prior_date():
    events = [
        {"event_id": "fomc_2026_06_16", "start_date": "2026-06-16"},
        {"event_id": "fomc_2026_07_28", "start_date": "2026-07-28"},
    ]
    docs = {"fomc_2026_06_16": {"event_id": "fomc_2026_06_16", "text": "previous"}}

    previous_event, previous_doc = (
        generate_fomc_policy_tone.previous_event_and_document(
            events,
            "fomc_2026_07_28",
            lambda event_id: docs.get(event_id),
        )
    )

    assert previous_event["event_id"] == "fomc_2026_06_16"
    assert previous_doc["text"] == "previous"


def test_previous_event_and_document_returns_none_when_no_previous():
    events = [
        {"event_id": "fomc_2026_07_28", "start_date": "2026-07-28"},
    ]
    previous_event, previous_doc = (
        generate_fomc_policy_tone.previous_event_and_document(
            events,
            "fomc_2026_07_28",
            lambda event_id: None,
        )
    )

    assert previous_event is None
    assert previous_doc is None


def test_target_events_returns_all_events_for_all_mode():
    events = [
        {"event_id": "fomc_2026_06_16"},
        {"event_id": "fomc_2026_07_28"},
    ]

    selected = generate_fomc_policy_tone.target_events(events, generate_all=True)

    assert selected == events


def test_target_events_returns_single_event():
    events = [
        {"event_id": "fomc_2026_06_16"},
        {"event_id": "fomc_2026_07_28"},
    ]

    selected = generate_fomc_policy_tone.target_events(
        events,
        event_id="fomc_2026_07_28",
    )

    assert selected == [{"event_id": "fomc_2026_07_28"}]


def test_target_events_rejects_unknown_event():
    try:
        generate_fomc_policy_tone.target_events(
            [{"event_id": "fomc_2026_06_16"}],
            event_id="missing",
        )
    except ValueError as exc:
        assert str(exc) == "fomc event is unknown: missing"
    else:
        raise AssertionError("expected ValueError")


def test_log_generation_context_prints_meeting_and_comparison(capsys):
    generate_fomc_policy_tone.log_generation_context(
        event={
            "event_id": "fomc_2026_06_16",
            "start_date": "2026-06-16",
            "end_date": "2026-06-17",
        },
        current_document={
            "url": "https://www.federalreserve.gov/newsevents/pressreleases/monetary20260617a.htm",
            "source_hash": "abcdef1234567890",
        },
        previous_event={
            "event_id": "fomc_2026_04_28",
            "start_date": "2026-04-28",
            "end_date": "2026-04-29",
        },
        previous_document={"source_hash": "123456abcdef"},
        models={
            "extractor_model": "extractor",
            "reviewer_model": "reviewer",
        },
    )

    output = capsys.readouterr().out

    assert "current: fomc_2026_06_16 (2026-06-16 to 2026-06-17)" in output
    assert "previous: fomc_2026_04_28 (2026-04-28 to 2026-04-29)" in output
    assert "extractor_model: extractor" in output
    assert "reviewer_model: reviewer" in output
    assert "source_hash: abcdef123456" in output


def test_should_skip_approved_extraction_when_not_forced():
    existing = {
        "event_id": "fomc_2026_06_16",
        "source_hash": "abc123",
        "extraction_status": "approved",
    }

    assert generate_fomc_policy_tone.should_skip_existing_extraction(
        existing,
        force=False,
    )


def test_should_not_skip_non_approved_extraction_when_not_forced():
    existing = {
        "event_id": "fomc_2026_06_16",
        "source_hash": "abc123",
        "extraction_status": "max_rounds_reached",
    }

    assert not generate_fomc_policy_tone.should_skip_existing_extraction(
        existing,
        force=False,
    )


def test_should_not_skip_approved_extraction_when_forced():
    existing = {
        "event_id": "fomc_2026_06_16",
        "source_hash": "abc123",
        "extraction_status": "approved",
    }

    assert not generate_fomc_policy_tone.should_skip_existing_extraction(
        existing,
        force=True,
    )


def test_should_not_skip_when_no_existing_extraction():
    assert not generate_fomc_policy_tone.should_skip_existing_extraction(
        None,
        force=False,
    )


def test_call_json_uses_deterministic_generation_options():
    calls = []

    class FakeCompletions:
        async def create(self, **kwargs):
            calls.append(kwargs)

            class Choice:
                message = type(
                    "Message", (), {"content": '{"approved": true, "feedback": []}'}
                )()

            return type("Response", (), {"choices": [Choice()]})()

    class FakeClient:
        chat = type(
            "Chat",
            (),
            {"completions": FakeCompletions()},
        )()

    async def run():
        return await generate_fomc_policy_tone._call_json(
            FakeClient(),
            "model",
            "prompt",
            lambda content: {"parsed": content},
        )

    result = generate_fomc_policy_tone.asyncio.run(run())

    assert result["parsed"] == '{"approved": true, "feedback": []}'
    assert calls[0]["temperature"] == 0


def test_log_generation_result_prints_saved_tone_summary(capsys):
    generate_fomc_policy_tone.log_generation_result(
        {
            "policy_action": "hold",
            "guidance_bias": "neutral",
            "language_tone": "hawkish",
            "overall_bias": "mild_hawkish",
            "statement_tone": "hawkish",
            "marker_tone": "hawkish",
            "tone_change": "more_hawkish",
            "confidence": "medium",
            "extraction_status": "approved",
            "review_rounds": 1,
        }
    )

    output = capsys.readouterr().out

    assert "policy_action: hold" in output
    assert "overall_bias: mild_hawkish" in output
    assert "statement_tone: hawkish" in output
    assert "tone_change: more_hawkish" in output
    assert "review_rounds: 1" in output

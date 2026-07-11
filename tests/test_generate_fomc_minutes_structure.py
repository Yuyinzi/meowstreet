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


def test_should_skip_existing_minutes_extraction_when_hash_matches():
    existing = {"event_id": "fomc_2026_06_16", "source_hash": "abc123"}

    assert generate_fomc_minutes_structure.should_skip_existing_extraction(
        existing,
        "abc123",
        force=False,
    )


def test_should_not_skip_existing_minutes_extraction_when_forced():
    existing = {"event_id": "fomc_2026_06_16", "source_hash": "abc123"}

    assert not generate_fomc_minutes_structure.should_skip_existing_extraction(
        existing,
        "abc123",
        force=True,
    )

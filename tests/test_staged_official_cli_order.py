def test_building_permits_main_uses_fetch_then_persist(monkeypatch, tmp_path):
    from scripts import import_us_building_permits

    calls = []
    monkeypatch.setattr(
        import_us_building_permits.macro_indicators,
        "connect",
        lambda *_args: (_ for _ in ()).throw(
            AssertionError("CLI fetch/prepare must not open SQLite")
        ),
    )
    monkeypatch.setattr(
        import_us_building_permits,
        "fetch_building_permits",
        lambda artifacts, **kwargs: calls.append(("fetch", artifacts)) or {"observations": 2},
    )
    monkeypatch.setattr(
        import_us_building_permits,
        "persist_building_permits",
        lambda db_path, artifacts, **kwargs: calls.append(("persist", db_path, artifacts))
        or {"observations": 2},
    )

    assert import_us_building_permits.main(
        ["--db-path", str(tmp_path / "market.sqlite"), "--census-cache-path", str(tmp_path / "permits.xlsx")]
    ) == 0
    assert [call[0] for call in calls] == ["fetch", "persist"]
    assert calls[0][1] is calls[1][2]


def test_nfib_main_uses_fetch_then_persist_for_source_url(monkeypatch, tmp_path):
    from scripts import import_nfib_sbet

    calls = []
    monkeypatch.setattr(
        import_nfib_sbet.macro_indicators,
        "connect",
        lambda *_args: (_ for _ in ()).throw(
            AssertionError("CLI fetch/prepare must not open SQLite")
        ),
    )
    monkeypatch.setattr(
        import_nfib_sbet,
        "fetch_nfib",
        lambda artifacts, **kwargs: calls.append(("fetch", artifacts)) or {"observations": 2},
    )
    monkeypatch.setattr(
        import_nfib_sbet,
        "persist_nfib",
        lambda db_path, artifacts, **kwargs: calls.append(("persist", db_path, artifacts))
        or {"observations": 2},
    )

    assert import_nfib_sbet.main(
        ["--source-url", "https://example.test/report", "--db-path", str(tmp_path / "market.sqlite")]
    ) == 0
    assert [call[0] for call in calls] == ["fetch", "persist"]
    assert calls[0][1] is calls[1][2]


def test_nfib_regional_main_uses_fetch_then_persist(monkeypatch, tmp_path):
    from scripts import import_nfib_sbet_regional

    calls = []
    monkeypatch.setattr(
        import_nfib_sbet_regional.macro_indicators,
        "connect",
        lambda *_args: (_ for _ in ()).throw(
            AssertionError("CLI fetch/prepare must not open SQLite")
        ),
    )
    monkeypatch.setattr(
        import_nfib_sbet_regional,
        "fetch_nfib_regional",
        lambda artifacts, *args, **kwargs: calls.append(("fetch", artifacts))
        or {"observations": 2},
    )
    monkeypatch.setattr(
        import_nfib_sbet_regional,
        "persist_nfib_regional",
        lambda db_path, artifacts: calls.append(("persist", db_path, artifacts))
        or {"observations": 2},
    )

    assert import_nfib_sbet_regional.main(
        ["--db-path", str(tmp_path / "market.sqlite")]
    ) == 0
    assert [call[0] for call in calls] == ["fetch", "persist"]
    assert calls[0][1] is calls[1][2]


def test_fomc_document_main_uses_fetch_then_persist(monkeypatch, tmp_path):
    from scripts import fetch_fomc_documents

    calls = []
    class Connection:
        closed = False

        def close(self):
            self.closed = True

    connection = Connection()
    monkeypatch.setattr(
        fetch_fomc_documents.us_rates_liquidity,
        "connect",
        lambda *_args: connection,
    )
    monkeypatch.setattr(
        fetch_fomc_documents,
        "fetch_documents",
        lambda artifacts, events, document_type, **kwargs: (
            calls.append(("fetch", artifacts, events, document_type))
            or (assert_closed(connection) and {"fetched": 1, "failed": 0, "unavailable": 0})
        )
        or {"fetched": 1, "failed": 0, "unavailable": 0},
    )
    monkeypatch.setattr(
        fetch_fomc_documents,
        "persist_documents",
        lambda db_path, artifacts, document_type: calls.append(
            ("persist", db_path, artifacts, document_type)
        )
        or {"documents": 1},
    )
    monkeypatch.setattr(
        fetch_fomc_documents.us_rates_liquidity,
        "load_macro_events",
        lambda con, event_type: [
            {
                "event_id": "event",
                "start_date": "2026-07-28",
                "end_date": "2026-07-29",
            }
        ],
    )
    monkeypatch.setattr(
        fetch_fomc_documents.us_rates_liquidity,
        "load_macro_event_document",
        lambda *args: None,
    )

    assert fetch_fomc_documents.main(
        ["--db-path", str(tmp_path / "market.sqlite")]
    ) == 0
    assert [call[0] for call in calls] == ["fetch", "persist"]
    assert calls[0][1] is calls[1][2]


def assert_closed(connection):
    assert connection.closed
    return True


def test_fomc_policy_tone_main_uses_prepare_then_persist(monkeypatch, tmp_path):
    from scripts import generate_fomc_policy_tone

    event = {"event_id": "event", "start_date": "2026-07-28"}
    prepared = {"status": "ok", "event_id": "event", "row": {}}
    calls = []
    class Connection:
        closed = False

        def close(self):
            self.closed = True

    connection = Connection()
    monkeypatch.setattr(
        generate_fomc_policy_tone.us_rates_liquidity,
        "connect",
        lambda *_args: connection,
    )
    monkeypatch.setattr(
        generate_fomc_policy_tone.us_rates_liquidity,
        "load_macro_events",
        lambda con, event_type: [event],
    )
    monkeypatch.setattr(
        generate_fomc_policy_tone,
        "classify_events",
        lambda con, events, force: {
            "pending": [(event, {"source_hash": "hash"})],
            "reused": [],
            "unavailable": [],
        },
    )
    monkeypatch.setattr(
        generate_fomc_policy_tone,
        "prepare_fomc_policy_tone",
        lambda *args, **kwargs: (
            calls.append(("prepare", args))
            or (assert_closed(connection) and prepared)
        ),
    )
    monkeypatch.setattr(
        generate_fomc_policy_tone,
        "persist_fomc_policy_tone",
        lambda *args, **kwargs: calls.append(("persist", args)) or {"status": "ok"},
    )
    monkeypatch.setattr(
        generate_fomc_policy_tone.llm,
        "build_async_client_bundle",
        lambda *args, **kwargs: {
            "client": object(),
            "models": {"extractor_model": "extractor", "reviewer_model": "reviewer"},
        },
    )

    assert generate_fomc_policy_tone.main(
        ["--event-id", "event", "--db-path", str(tmp_path / "market.sqlite")]
    ) == 0
    assert [call[0] for call in calls] == ["prepare", "persist"]
    assert calls[1][1][1] is prepared


def test_fomc_minutes_main_uses_prepare_then_persist(monkeypatch, tmp_path):
    from scripts import generate_fomc_minutes_structure

    event = {"event_id": "event", "start_date": "2026-07-28"}
    prepared = {"status": "ok", "event_id": "event", "row": {}}
    calls = []
    class Connection:
        closed = False

        def close(self):
            self.closed = True

    connection = Connection()
    monkeypatch.setattr(
        generate_fomc_minutes_structure.us_rates_liquidity,
        "connect",
        lambda *_args: connection,
    )
    monkeypatch.setattr(
        generate_fomc_minutes_structure.us_rates_liquidity,
        "load_macro_events",
        lambda con, event_type: [event],
    )
    monkeypatch.setattr(
        generate_fomc_minutes_structure,
        "load_event_maps",
        lambda con, events: ({"event": {"source_hash": "hash"}}, {"event": {"marker_tone": "neutral"}}),
    )
    monkeypatch.setattr(
        generate_fomc_minutes_structure,
        "classify_events",
        lambda *args, **kwargs: {
            "pending": [(event, {"source_hash": "hash"}, {"marker_tone": "neutral"})],
            "reused": [],
            "unavailable": [],
        },
    )
    monkeypatch.setattr(
        generate_fomc_minutes_structure,
        "prepare_fomc_minutes_structure",
        lambda *args, **kwargs: (
            calls.append(("prepare", args))
            or (assert_closed(connection) and prepared)
        ),
    )
    monkeypatch.setattr(
        generate_fomc_minutes_structure,
        "persist_fomc_minutes_structure",
        lambda *args, **kwargs: calls.append(("persist", args)) or {"status": "ok"},
    )
    monkeypatch.setattr(
        generate_fomc_minutes_structure.llm,
        "build_async_client_bundle",
        lambda *args, **kwargs: {
            "client": object(),
            "models": {"extractor_model": "extractor", "reviewer_model": "reviewer"},
        },
    )

    assert generate_fomc_minutes_structure.main(
        ["--event-id", "event", "--db-path", str(tmp_path / "market.sqlite")]
    ) == 0
    assert [call[0] for call in calls] == ["prepare", "persist"]
    assert calls[1][1][1] is prepared


def test_fomc_document_cli_prints_only_compact_summary(monkeypatch, tmp_path, capsys):
    from scripts import fetch_fomc_documents

    event = {
        "event_id": "event",
        "start_date": "2026-07-28",
        "end_date": "2026-07-29",
    }
    monkeypatch.setattr(
        fetch_fomc_documents.us_rates_liquidity,
        "load_macro_events",
        lambda con, event_type: [event],
    )
    monkeypatch.setattr(
        fetch_fomc_documents.us_rates_liquidity,
        "load_macro_event_document",
        lambda *args: None,
    )
    monkeypatch.setattr(
        fetch_fomc_documents,
        "fetch_documents",
        lambda artifacts, events, document_type: {
            "artifact_key": "fomc.documents.statement",
            "rows": [
                {
                    "event_id": "event",
                    "document_type": "statement",
                    "text": "RAW DOCUMENT BODY MUST NOT PRINT",
                }
            ],
            "document_type": "statement",
            "fetched": 1,
            "unavailable": 0,
            "failed": 0,
        },
    )
    monkeypatch.setattr(
        fetch_fomc_documents,
        "persist_documents",
        lambda *args: {"status": "ok"},
    )

    assert fetch_fomc_documents.main(
        ["--db-path", str(tmp_path / "market.sqlite")]
    ) == 0
    output = capsys.readouterr().out
    assert output == "  {'document_type': 'statement', 'fetched': 1, 'unavailable': 0, 'failed': 0}\n"
    assert "RAW DOCUMENT BODY" not in output
    assert "rows" not in output


def test_staged_fomc_fetch_retains_structured_failure_details():
    from app.services import macro_refresh_official

    event = {
        "event_id": "event",
        "start_date": "2026-07-28",
        "end_date": "2026-07-29",
    }
    result = macro_refresh_official.fetch_fomc_documents(
        {},
        [event],
        "statement",
        fetcher=lambda current_event, document_type: (_ for _ in ()).throw(
            ValueError("source unavailable")
        ),
    )

    assert result["failed"] == 1
    assert result["failures"] == [
        {
            "event_id": "event",
            "document_type": "statement",
            "reason": "source unavailable",
        }
    ]


def test_fomc_document_cli_prints_structured_failures_without_skip_spam(
    monkeypatch, tmp_path, capsys
):
    from scripts import fetch_fomc_documents

    event = {
        "event_id": "event",
        "start_date": "2026-07-28",
        "end_date": "2026-07-29",
    }
    monkeypatch.setattr(
        fetch_fomc_documents.us_rates_liquidity,
        "load_macro_events",
        lambda con, event_type: [event],
    )
    monkeypatch.setattr(
        fetch_fomc_documents.us_rates_liquidity,
        "load_macro_event_document",
        lambda *args: None,
    )
    monkeypatch.setattr(
        fetch_fomc_documents,
        "fetch_documents",
        lambda *args: {
            "document_type": "statement",
            "fetched": 0,
            "unavailable": 1,
            "failed": 1,
            "failures": [
                {
                    "event_id": "event",
                    "document_type": "statement",
                    "reason": "invalid published document",
                }
            ],
        },
    )
    monkeypatch.setattr(
        fetch_fomc_documents,
        "persist_documents",
        lambda *args: {"status": "ok"},
    )

    assert fetch_fomc_documents.main(
        ["--db-path", str(tmp_path / "market.sqlite")]
    ) == 1
    captured = capsys.readouterr()
    assert "FAIL event statement: invalid published document" in captured.err
    assert "SKIP" not in captured.out
    assert captured.out == (
        "  {'document_type': 'statement', 'fetched': 0, "
        "'unavailable': 1, 'failed': 1}\n"
    )

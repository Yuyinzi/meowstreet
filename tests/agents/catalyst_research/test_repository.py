import sqlite3
from datetime import UTC, datetime

import pytest

from app.agents.catalyst_research.persistence import repository


EXPECTED_TABLES = {
    "catalyst_research_jobs",
    "catalyst_search_attempts",
    "catalyst_search_results",
    "catalyst_ir_sources",
    "catalyst_source_snapshots",
    "catalyst_source_adapters",
    "catalyst_adapter_validations",
    "catalyst_ir_events",
    "catalyst_ir_classifications",
}


def test_connect_creates_exact_catalyst_tables(tmp_path):
    con = repository.connect(tmp_path / "market_data.sqlite")
    try:
        tables = {
            row[0]
            for row in con.execute(
                "select name from sqlite_master where type = 'table' and name like 'catalyst_%'"
            )
        }
        assert tables == EXPECTED_TABLES
        assert con.row_factory is sqlite3.Row
        assert con.execute("pragma foreign_keys").fetchone()[0] == 1
    finally:
        con.close()


def _job(con, ticker="NVDA", status=None):
    result = repository.create_job(
        con,
        {"ticker": ticker, "years": 2},
        {"name": "NVIDIA Corporation", "cik": "1045810"},
        datetime(2026, 9, 4, tzinfo=UTC),
    )
    if status == "running":
        repository.start_job(con, result["job_id"], "2026-09-04T00:01:00+00:00")
    return result


def test_job_transition_and_terminal_immutability(tmp_path):
    con = repository.connect(tmp_path / "db.sqlite")
    job = _job(con)
    repository.start_job(con, job["job_id"], "2026-09-04T00:01:00+00:00")
    repository.finalize_job(con, job["job_id"], {"status": "completed", "statistics": {"total": 2}})
    with pytest.raises(ValueError, match="terminal"):
        repository.finalize_job(con, job["job_id"], {"status": "failed"})
    assert con.execute("select status, statistics_json from catalyst_research_jobs where job_id = ?", (job["job_id"],)).fetchone()[0] == "completed"


def test_snapshot_hash_deduplication_and_reference_safe_pruning(tmp_path):
    con = repository.connect(tmp_path / "db.sqlite")
    job = _job(con, status="running")
    snapshot = {"requested_url": "https://ir.example.test/news", "raw_html": "<html>same</html>"}
    first = repository.save_snapshot(con, snapshot)
    second = repository.save_snapshot(con, {**snapshot, "raw_html": "<html>same</html>", "final_url": "https://other"})
    assert first == second
    assert con.execute("select count(*) from catalyst_source_snapshots").fetchone()[0] == 1
    source = repository.save_source(con, {"job_id": job["job_id"], "ticker": "NVDA", "source_type": "press_releases", "url": snapshot["requested_url"], "snapshot_hash": first})
    assert repository.prune_unreferenced_snapshots(con) == 0
    orphan = repository.save_snapshot(con, {"requested_url": "https://ir.example.test/orphan", "raw_html": "orphan"})
    assert orphan != first
    assert repository.prune_unreferenced_snapshots(con) == 1
    assert con.execute("select 1 from catalyst_source_snapshots where content_hash = ?", (first,)).fetchone()
    assert not con.execute("select 1 from catalyst_source_snapshots where content_hash = ?", (orphan,)).fetchone()
    assert source["source_id"].startswith("cis_")


def test_adapter_versions_activation_supersession_and_failed_candidate(tmp_path):
    con = repository.connect(tmp_path / "db.sqlite")
    job = _job(con, status="running")
    base = {"ticker": "NVDA", "source_type": "press_releases", "source_url": "https://ir.example.test/news", "adapter": {"item_selector": ".item"}}
    first = repository.create_adapter_candidate(con, base)
    repository.record_adapter_validation(con, {"adapter_id": first["adapter_id"], "job_id": job["job_id"], "status": "passed", "report": {"ok": True}})
    repository.activate_adapter(con, first["adapter_id"], "2026-09-04T01:00:00+00:00")
    failed = repository.create_adapter_candidate(con, base)
    assert failed["version"] == 2
    repository.record_adapter_validation(con, {"adapter_id": failed["adapter_id"], "job_id": job["job_id"], "status": "failed", "report": {"ok": False}})
    with pytest.raises(ValueError, match="passing validation"):
        repository.activate_adapter(con, failed["adapter_id"], "2026-09-04T02:00:00+00:00")
    assert repository.load_active_adapter(con, "nvda", "press_releases")["adapter_id"] == first["adapter_id"]
    second = repository.create_adapter_candidate(con, base)
    repository.record_adapter_validation(con, {"adapter_id": second["adapter_id"], "job_id": job["job_id"], "status": "passed", "report": {"ok": True}})
    repository.activate_adapter(con, second["adapter_id"], "2026-09-04T03:00:00+00:00")
    states = dict(con.execute("select adapter_id, state from catalyst_source_adapters").fetchall())
    assert states[first["adapter_id"]] == "superseded"
    assert states[second["adapter_id"]] == "active"
    repository.mark_adapter_stale(con, second["adapter_id"], "2026-09-04T04:00:00+00:00")
    assert con.execute("select state from catalyst_source_adapters where adapter_id = ?", (second["adapter_id"],)).fetchone()[0] == "stale"


def test_event_and_classification_atomic_write_and_latest_usable_result(tmp_path):
    con = repository.connect(tmp_path / "db.sqlite")
    job = _job(con, status="running")
    source = repository.save_source(con, {"job_id": job["job_id"], "ticker": "NVDA", "source_type": "press_releases", "url": "https://ir.example.test/news"})
    events = [{"event_id": "ire_event1", "source_id": source["source_id"], "ticker": "NVDA", "source_type": "press_releases", "published_date": "2026-01-01", "count_date": "2026-01-01", "title": "Results", "url": "https://ir.example.test/1"}]
    repository.save_finalized_observations(con, job["job_id"], events, [{"event_id": "ire_event1", "earnings_state": "earnings", "classification_method": "rule_v1"}])
    repository.finalize_job(con, job["job_id"], {"status": "completed", "statistics": {"press_releases": {"total": 1}}})
    failed = _job(con, status="running")
    repository.finalize_job(con, failed["job_id"], {"status": "failed", "error": "network details" * 200})
    result = repository.load_latest_result(con, "NVDA")
    assert result["job_id"] == job["job_id"]
    assert result["statistics"]["press_releases"]["total"] == 1
    assert len(result["error_summary"] or "") == 0
    with pytest.raises(ValueError, match="terminal"):
        repository.save_finalized_observations(con, job["job_id"], events, [])


def test_batch_local_classification_ids_generate_global_event_ids_across_jobs(tmp_path):
    con = repository.connect(tmp_path / "db.sqlite")
    first_job = _job(con, status="running")
    first_source = repository.save_source(con, {"job_id": first_job["job_id"], "ticker": "NVDA", "source_type": "press_releases", "url": "https://ir.example.test/first"})
    second_job = _job(con, status="running")
    second_source = repository.save_source(con, {"job_id": second_job["job_id"], "ticker": "NVDA", "source_type": "press_releases", "url": "https://ir.example.test/second"})

    for job_id, source_id, title in ((first_job["job_id"], first_source["source_id"], "First job event"), (second_job["job_id"], second_source["source_id"], "Second job event")):
        repository.save_finalized_observations(
            con,
            job_id,
            [{"id": 1, "source_id": source_id, "ticker": "NVDA", "source_type": "press_releases", "count_date": "2026-01-01", "title": title, "url": f"https://ir.example.test/{title.replace(' ', '-')}"}],
            [{"id": 1, "earnings_state": "ambiguous", "classification_method": "manual"}],
        )

    rows = con.execute("select event_id, job_id from catalyst_ir_events order by job_id").fetchall()
    assert len(rows) == 2
    assert len({row["event_id"] for row in rows}) == 2
    assert all(row["event_id"].startswith("ire_") for row in rows)


def test_duplicate_classification_input_ids_save_as_distinct_ambiguous_events(tmp_path):
    con = repository.connect(tmp_path / "db.sqlite")
    job = _job(con, status="running")
    source = repository.save_source(con, {"job_id": job["job_id"], "ticker": "NVDA", "source_type": "press_releases", "url": "https://ir.example.test/news"})
    events = [
        {"id": 1, "source_id": source["source_id"], "ticker": "NVDA", "source_type": "press_releases", "count_date": "2026-01-01", "title": "Duplicate one", "url": "https://ir.example.test/one"},
        {"id": 1, "source_id": source["source_id"], "ticker": "NVDA", "source_type": "press_releases", "count_date": "2026-01-02", "title": "Duplicate two", "url": "https://ir.example.test/two"},
    ]

    repository.save_finalized_observations(
        con,
        job["job_id"],
        events,
        [{"id": 1, "earnings_state": "non_earnings", "classification_method": "llm_v1"}, {"id": 1, "earnings_state": "earnings", "classification_method": "llm_v1"}],
    )

    states = [row[0] for row in con.execute("select earnings_state from catalyst_ir_events order by count_date").fetchall()]
    assert states == ["ambiguous", "ambiguous"]


@pytest.mark.parametrize("invalid_id", [False, 0, -1, "external-id", []])
def test_invalid_classification_input_id_cannot_assign_state(tmp_path, invalid_id):
    con = repository.connect(tmp_path / "db.sqlite")
    job = _job(con, status="running")
    source = repository.save_source(con, {"job_id": job["job_id"], "ticker": "NVDA", "source_type": "press_releases", "url": "https://ir.example.test/news"})

    repository.save_finalized_observations(
        con,
        job["job_id"],
        [{"id": invalid_id, "source_id": source["source_id"], "ticker": "NVDA", "source_type": "press_releases", "count_date": "2026-01-01", "title": "Business update", "url": "https://ir.example.test/invalid-id"}],
        [{"id": invalid_id, "earnings_state": "non_earnings", "classification_method": "llm_v1"}],
    )

    assert con.execute("select earnings_state from catalyst_ir_events").fetchone()[0] == "ambiguous"


def test_duplicate_explicit_event_ids_raise_value_error_and_roll_back(tmp_path):
    con = repository.connect(tmp_path / "db.sqlite")
    job = _job(con, status="running")
    source = repository.save_source(con, {"job_id": job["job_id"], "ticker": "NVDA", "source_type": "press_releases", "url": "https://ir.example.test/news"})
    event = {"event_id": "ire_duplicate", "source_id": source["source_id"], "ticker": "NVDA", "source_type": "press_releases", "count_date": "2026-01-01", "title": "Duplicate", "url": "https://ir.example.test/duplicate"}

    with pytest.raises(ValueError, match="duplicate event id"):
        repository.save_finalized_observations(con, job["job_id"], [event, {**event, "count_date": "2026-01-02"}], [])

    assert con.execute("select count(*) from catalyst_ir_events where job_id = ?", (job["job_id"],)).fetchone()[0] == 0


def test_explicit_event_id_conflict_across_jobs_is_value_error(tmp_path):
    con = repository.connect(tmp_path / "db.sqlite")
    first_job = _job(con, status="running")
    first_source = repository.save_source(con, {"job_id": first_job["job_id"], "ticker": "NVDA", "source_type": "press_releases", "url": "https://ir.example.test/first"})
    event = {"event_id": "ire_cross_job", "source_id": first_source["source_id"], "ticker": "NVDA", "source_type": "press_releases", "count_date": "2026-01-01", "title": "First", "url": "https://ir.example.test/first-event"}
    repository.save_finalized_observations(con, first_job["job_id"], [event], [])
    second_job = _job(con, status="running")
    second_source = repository.save_source(con, {"job_id": second_job["job_id"], "ticker": "NVDA", "source_type": "press_releases", "url": "https://ir.example.test/second"})

    with pytest.raises(ValueError, match="event id conflicts"):
        repository.save_finalized_observations(con, second_job["job_id"], [{**event, "source_id": second_source["source_id"], "title": "Second"}], [])


def test_classification_provenance_round_trips_for_llm_and_rule_events(tmp_path):
    con = repository.connect(tmp_path / "db.sqlite")
    job = _job(con, status="running")
    source = repository.save_source(con, {"job_id": job["job_id"], "ticker": "NVDA", "source_type": "press_releases", "url": "https://ir.example.test/news"})
    events = [
        {"id": 1, "source_id": source["source_id"], "ticker": "NVDA", "source_type": "press_releases", "count_date": "2026-01-01", "title": "Business update", "url": "https://ir.example.test/one"},
        {"id": 2, "source_id": source["source_id"], "ticker": "NVDA", "source_type": "press_releases", "count_date": "2026-01-02", "title": "Q1 Financial Results", "url": "https://ir.example.test/two"},
    ]
    classifications = [
        {"id": 1, "earnings_state": "non_earnings", "classification_method": "llm_v1", "model": "test-model", "prompt_schema_version": "classification_v1", "input_hash": "input-hash", "output_hash": "output-hash"},
        {"id": 2, "earnings_state": "earnings", "classification_method": "rule_v1", "model": None, "prompt_schema_version": None, "input_hash": None, "output_hash": None},
    ]

    repository.save_finalized_observations(con, job["job_id"], events, classifications)

    rows = con.execute("select c.earnings_state, c.classification_method, c.model, c.prompt_schema_version, c.input_hash, c.output_hash from catalyst_ir_classifications c join catalyst_ir_events e on e.event_id = c.event_id order by e.count_date").fetchall()
    assert rows[0][0:6] == ("non_earnings", "llm_v1", "test-model", "classification_v1", "input-hash", "output-hash")
    assert rows[1][0:6] == ("earnings", "rule_v1", None, None, None, None)


def test_events_cursor_rejects_ticker_or_job_boundary(tmp_path):
    con = repository.connect(tmp_path / "db.sqlite")
    job = _job(con, status="running")
    source = repository.save_source(con, {"job_id": job["job_id"], "ticker": "NVDA", "source_type": "press_releases", "url": "https://ir.example.test/news"})
    for number in range(3):
        repository.save_finalized_observations(con, job["job_id"], [{"source_id": source["source_id"], "ticker": "NVDA", "source_type": "press_releases", "count_date": f"2026-01-0{number + 1}", "title": f"News {number}", "url": f"https://ir.example.test/{number}"}], [])
    page = repository.load_events_page(con, "NVDA", job["job_id"], 2, None)
    assert len(page["events"]) == 2 and page["next_cursor"]
    with pytest.raises(ValueError, match="ticker or job"):
        repository.load_events_page(con, "AAPL", job["job_id"], 2, page["next_cursor"])


def test_rejects_cross_ticker_source_and_event_provenance(tmp_path):
    con = repository.connect(tmp_path / "db.sqlite")
    job = _job(con, status="running")
    with pytest.raises(ValueError, match="source ticker"):
        repository.save_source(con, {"job_id": job["job_id"], "ticker": "AAPL", "source_type": "press_releases", "url": "https://ir.example.test/news"})
    source = repository.save_source(con, {"job_id": job["job_id"], "ticker": "NVDA", "source_type": "press_releases", "url": "https://ir.example.test/news"})
    with pytest.raises(ValueError, match="event ticker"):
        repository.save_finalized_observations(con, job["job_id"], [{"source_id": source["source_id"], "ticker": "AAPL", "source_type": "press_releases", "count_date": "2026-01-01", "title": "News", "url": "https://ir.example.test/1"}], [])


def test_queued_job_cannot_finalize(tmp_path):
    con = repository.connect(tmp_path / "db.sqlite")
    job = _job(con)
    with pytest.raises(ValueError, match="running"):
        repository.finalize_job(con, job["job_id"], {"status": "failed"})


def test_failed_validation_is_terminal_candidate_state_and_cannot_activate(tmp_path):
    con = repository.connect(tmp_path / "db.sqlite")
    job = _job(con, status="running")
    candidate = repository.create_adapter_candidate(con, {"job_id": job["job_id"], "ticker": "NVDA", "source_type": "press_releases", "source_url": "https://ir.example.test/news", "adapter": {}})
    repository.record_adapter_validation(con, {"adapter_id": candidate["adapter_id"], "job_id": job["job_id"], "status": "failed", "report": {}})
    assert con.execute("select state from catalyst_source_adapters where adapter_id = ?", (candidate["adapter_id"],)).fetchone()[0] == "failed_validation"
    with pytest.raises(ValueError, match="candidate"):
        repository.activate_adapter(con, candidate["adapter_id"], "2026-09-04T01:00:00+00:00")


def test_snapshot_hashes_structural_content_and_rejects_mismatch(tmp_path):
    con = repository.connect(tmp_path / "db.sqlite")
    first = repository.save_snapshot(con, {"requested_url": "https://ir.example.test/news", "structural_html": "<main>one</main>", "normalized": {"text": "one"}})
    second = repository.save_snapshot(con, {"requested_url": "https://ir.example.test/news", "structural_html": "<main>two</main>", "normalized": {"text": "two"}})
    assert first != second
    with pytest.raises(ValueError, match="content hash"):
        repository.save_snapshot(con, {"requested_url": "https://ir.example.test/news", "raw_html": "<main>three</main>", "content_hash": "not-the-content-hash"})


def test_cursor_rejects_non_scalar_payload_values(tmp_path):
    con = repository.connect(tmp_path / "db.sqlite")
    cursor = repository._encode_cursor({"ticker": ["NVDA"], "job_id": "cr_x", "count_date": {"date": "2026-01-01"}, "event_id": ["ire_x"]})
    with pytest.raises(ValueError, match="cursor is invalid"):
        repository.load_events_page(con, "NVDA", "cr_x", 1, cursor)


def test_invalid_date_and_integer_inputs_have_controlled_errors(tmp_path):
    con = repository.connect(tmp_path / "db.sqlite")
    with pytest.raises(ValueError, match="as of date is invalid"):
        repository.create_job(con, {"ticker": "NVDA", "years": 2, "as_of": "not-a-date"})
    job = _job(con, status="running")
    attempt = {"job_id": job["job_id"], "provider": "ddgs", "query": "NVDA IR"}
    repository.record_search_attempt(con, attempt)
    attempt_id = con.execute("select attempt_id from catalyst_search_attempts where job_id = ?", (job["job_id"],)).fetchone()[0]
    with pytest.raises(ValueError, match="result id is invalid"):
        repository.record_search_results(con, job["job_id"], attempt_id, [{"result_id": "not-an-int", "url": "https://ir.example.test"}])


def test_record_search_attempt_returns_repository_owned_id(tmp_path):
    con = repository.connect(tmp_path / "db.sqlite")
    job = _job(con, status="running")
    attempt_id = repository.record_search_attempt(con, {"job_id": job["job_id"], "provider": "ddgs", "query": "NVDA IR"})
    assert isinstance(attempt_id, str)
    assert con.execute("select attempt_id from catalyst_search_attempts where job_id = ?", (job["job_id"],)).fetchone()[0] == attempt_id


def test_terminal_mutation_is_rejected_after_other_connection_finalizes(tmp_path):
    db_path = tmp_path / "db.sqlite"
    con = repository.connect(db_path)
    other = repository.connect(db_path)
    job = _job(con)
    repository.start_job(con, job["job_id"], "2026-09-04T00:01:00+00:00")
    repository.finalize_job(other, job["job_id"], {"status": "failed", "error": "done"})
    with pytest.raises(ValueError, match="terminal"):
        repository.record_search_attempt(con, {"job_id": job["job_id"], "provider": "ddgs", "query": "NVDA IR"})
    assert con.execute("select count(*) from catalyst_search_attempts").fetchone()[0] == 0


def test_adapter_validation_cannot_write_after_other_connection_finalizes(tmp_path, monkeypatch):
    db_path = tmp_path / "db.sqlite"
    con = repository.connect(db_path)
    other = repository.connect(db_path)
    job = _job(con, status="running")
    candidate = repository.create_adapter_candidate(con, {"job_id": job["job_id"], "ticker": "NVDA", "source_type": "press_releases", "source_url": "https://ir.example.test/news", "adapter": {}})
    original_guard = repository._nonterminal_job

    def finalize_after_guard(connection, job_id):
        result = original_guard(connection, job_id)
        repository.finalize_job(other, job_id, {"status": "failed", "error": "finished"})
        return result

    monkeypatch.setattr(repository, "_nonterminal_job", finalize_after_guard)
    with pytest.raises(ValueError, match="terminal"):
        repository.record_adapter_validation(con, {"adapter_id": candidate["adapter_id"], "job_id": job["job_id"], "status": "passed", "report": {}})
    assert con.execute("select count(*) from catalyst_adapter_validations").fetchone()[0] == 0
    assert con.execute("select state from catalyst_source_adapters where adapter_id = ?", (candidate["adapter_id"],)).fetchone()[0] == "candidate"


def test_update_search_attempt_is_immutable_after_other_connection_finalizes(tmp_path):
    db_path = tmp_path / "db.sqlite"
    con = repository.connect(db_path)
    other = repository.connect(db_path)
    job = _job(con, status="running")
    attempt_id = repository.record_search_attempt(con, {"job_id": job["job_id"], "provider": "ddgs", "query": "NVDA IR", "outcome": "candidate_results", "diagnostics": {"safe": True}})
    repository.finalize_job(other, job["job_id"], {"status": "failed", "error": "done"})
    with pytest.raises(ValueError, match="terminal"):
        repository.update_search_attempt(con, attempt_id, outcome="rejected", diagnostics={"changed": True})
    row = con.execute("select outcome, diagnostics_json from catalyst_search_attempts where attempt_id = ?", (attempt_id,)).fetchone()
    assert row[0] == "candidate_results"
    assert '"safe":true' in row[1]


def test_update_search_attempt_refuses_terminal_job_and_missing_attempt(tmp_path):
    con = repository.connect(tmp_path / "db.sqlite")
    job = _job(con, status="running")
    repository.record_search_attempt(
        con,
        {"attempt_id": "attempt_1", "job_id": job["job_id"], "provider": "ddgs", "query": "acme ir"},
    )
    repository.update_search_attempt(con, "attempt_1", outcome="empty_results")
    assert con.execute("select outcome from catalyst_search_attempts where attempt_id = 'attempt_1'").fetchone()[0] == "empty_results"
    with pytest.raises(ValueError, match="not found"):
        repository.update_search_attempt(con, "missing", outcome="empty_results")
    repository.finalize_job(con, job["job_id"], {"status": "failed"})
    with pytest.raises(ValueError, match="terminal"):
        repository.update_search_attempt(con, "attempt_1", outcome="rejected")

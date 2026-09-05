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

import base64
import json
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
    "catalyst_company_registry",
    "catalyst_source_endpoints",
    "catalyst_endpoint_checks",
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


def registry_payload(version=1, ticker="NVDA", **overrides):
    payload = {
        "ticker": ticker,
        "company_name": "NVIDIA Corporation",
        "cik": "1045810",
        "official_domains": ["nvidianews.nvidia.com"],
        "source_confidence": "high",
        "registry_version": version,
        "discovered_at": "2026-09-01T00:00:00+00:00",
        "updated_at": "2026-09-01T00:00:00+00:00",
    }
    payload.update(overrides)
    return payload


def endpoint_payload(ticker="NVDA", **overrides):
    payload = {
        "ticker": ticker,
        "channel": "press_releases",
        "endpoint_type": "rss",
        "url": "https://nvidianews.nvidia.com/rss",
        "domain": "nvidianews.nvidia.com",
        "status": "unverified",
        "confidence": "high",
        "discovered_at": "2026-09-01T00:00:00+00:00",
    }
    payload.update(overrides)
    return payload


def check_payload(endpoint_id, **overrides):
    payload = {
        "endpoint_id": endpoint_id,
        "checked_at": "2026-09-08T00:00:00+00:00",
        "outcome": "success",
        "item_count": 3,
        "new_item_count": 1,
        "newest_item_at": "2026-09-07T12:00:00+00:00",
    }
    payload.update(overrides)
    return payload


def test_job_transition_and_terminal_immutability(tmp_path):
    con = repository.connect(tmp_path / "db.sqlite")
    job = _job(con)
    repository.start_job(con, job["job_id"], "2026-09-04T00:01:00+00:00")
    repository.finalize_job(con, job["job_id"], {"status": "completed", "statistics": {"total": 2}})
    with pytest.raises(ValueError, match="terminal"):
        repository.finalize_job(con, job["job_id"], {"status": "failed"})
    assert con.execute("select status, statistics_json from catalyst_research_jobs where job_id = ?", (job["job_id"],)).fetchone()[0] == "completed"


def test_start_job_guard_does_not_overwrite_terminal_race(tmp_path, monkeypatch):
    db_path = tmp_path / "db.sqlite"
    con = repository.connect(db_path)
    job = _job(con)
    original_job = repository._job
    reads = 0

    def finalize_after_read(connection, job_id):
        nonlocal reads
        reads += 1
        row = original_job(connection, job_id)
        if reads == 1:
            connection.execute("update catalyst_research_jobs set status = 'failed' where job_id = ?", (job_id,))
            connection.commit()
        return row

    monkeypatch.setattr(repository, "_job", finalize_after_read)
    with pytest.raises(ValueError, match="terminal"):
        repository.start_job(con, job["job_id"], "2026-09-04T00:01:00+00:00")
    assert con.execute("select status from catalyst_research_jobs where job_id = ?", (job["job_id"],)).fetchone()[0] == "failed"


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


def test_runtime_validation_and_discovery_required_source_are_atomic(tmp_path):
    con = repository.connect(tmp_path / "db.sqlite")
    job = _job(con, status="running")
    candidate = repository.create_adapter_candidate(
        con,
        {"job_id": job["job_id"], "ticker": "NVDA", "source_type": "press_releases", "source_url": "https://ir.example.test/news", "adapter": {}},
    )
    repository.record_adapter_validation(con, {"adapter_id": candidate["adapter_id"], "job_id": job["job_id"], "status": "passed", "report": {}})
    repository.activate_adapter(con, candidate["adapter_id"], "2026-09-04T01:00:00+00:00")
    repository.record_runtime_adapter_validation(
        con,
        {"adapter_id": candidate["adapter_id"], "job_id": job["job_id"], "status": "failed", "report": {"errors": ["selector drift"], "html": "must not persist"}, "page_content_hashes": ["page-hash"], "validator_version": "validator-v1", "executor_version": "executor-v1"},
    )
    source = repository.mark_adapter_stale_with_source(
        con,
        candidate["adapter_id"],
        "2026-09-04T02:00:00+00:00",
        {"job_id": job["job_id"], "ticker": "NVDA", "source_type": "press_releases", "url": "https://ir.example.test/news", "active_adapter_id": candidate["adapter_id"], "adapter_version": 1, "verification_reason": "selector drift"},
    )

    assert source["extraction_status"] == "discovery_required"
    assert source["verification_reason"] == "selector drift"
    assert con.execute("select state from catalyst_source_adapters where adapter_id = ?", (candidate["adapter_id"],)).fetchone()[0] == "stale"
    validation = con.execute("select status, page_content_hashes_json, report_json from catalyst_adapter_validations where adapter_id = ? order by rowid desc", (candidate["adapter_id"],)).fetchone()
    assert validation[0] == "failed"
    assert "page-hash" in validation[1]
    assert "html" not in validation[2]


def test_stale_source_transition_rolls_back_when_source_is_invalid(tmp_path):
    con = repository.connect(tmp_path / "db.sqlite")
    job = _job(con, status="running")
    candidate = repository.create_adapter_candidate(con, {"job_id": job["job_id"], "ticker": "NVDA", "source_type": "press_releases", "source_url": "https://ir.example.test/news", "adapter": {}})
    repository.record_adapter_validation(con, {"adapter_id": candidate["adapter_id"], "job_id": job["job_id"], "status": "passed", "report": {}})
    repository.activate_adapter(con, candidate["adapter_id"], "2026-09-04T01:00:00+00:00")

    with pytest.raises(ValueError, match="source ticker"):
        repository.mark_adapter_stale_with_source(con, candidate["adapter_id"], "2026-09-04T02:00:00+00:00", {"job_id": job["job_id"], "ticker": "OTHER", "source_type": "press_releases", "url": "https://ir.example.test/news"})

    assert con.execute("select state from catalyst_source_adapters where adapter_id = ?", (candidate["adapter_id"],)).fetchone()[0] == "active"
    assert con.execute("select count(*) from catalyst_ir_sources where job_id = ?", (job["job_id"],)).fetchone()[0] == 0


def test_latest_result_uses_rowid_tiebreak_for_same_clock_jobs(tmp_path):
    con = repository.connect(tmp_path / "db.sqlite")
    first = _job(con, status="running")
    repository.finalize_job(con, first["job_id"], {"status": "completed", "statistics": {"version": 1}, "execution_paths": {"press_releases": "hot"}, "call_counts": {"discovery": 0}})
    second = _job(con, status="running")
    repository.finalize_job(con, second["job_id"], {"status": "failed", "error": "replacement failed", "execution_paths": {"press_releases": "cold"}, "call_counts": {"discovery": 1}})

    result = repository.load_latest_result(con, "NVDA")

    assert result["job_id"] == first["job_id"]
    assert result["latest_job_id"] == second["job_id"]
    assert result["latest_job_status"] == "failed"
    assert result["execution_paths"] == {"press_releases": "hot"}
    assert result["call_counts"] == {"discovery": 0}


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


def test_load_job_result_and_events_page_return_complete_persisted_event_list(tmp_path):
    con = repository.connect(tmp_path / "db.sqlite")
    job = _job(con, status="running")
    source = repository.save_source(con, {"job_id": job["job_id"], "ticker": "NVDA", "source_type": "press_releases", "url": "https://ir.example.test/news"})
    events = [
        {"id": 1, "source_id": source["source_id"], "ticker": "NVDA", "source_type": "press_releases", "count_date": "2026-01-01", "title": "Business update", "url": "https://ir.example.test/one"},
        {"id": 2, "source_id": source["source_id"], "ticker": "NVDA", "source_type": "press_releases", "count_date": "2026-01-02", "title": "Q1 Financial Results", "url": "https://ir.example.test/two"},
    ]
    classifications = [
        {"id": 1, "earnings_state": "ambiguous", "classification_method": "llm_v1", "model": "test-model", "prompt_schema_version": "classification_v1", "input_hash": "input-1", "output_hash": "output-1"},
        {"id": 2, "earnings_state": "earnings", "classification_method": "rule_v1"},
    ]
    repository.save_finalized_observations(con, job["job_id"], events, classifications)
    repository.finalize_job(con, job["job_id"], {"status": "completed", "statistics": {"press_releases": {"total": 2}}})

    result = repository.load_job_result(con, job["job_id"])
    page = repository.load_events_page(con, "NVDA", job["job_id"], 200, None)

    assert result["observation_count"] == 2
    assert len(result["sources"]) == 1
    assert [event["title"] for event in page["events"]] == ["Q1 Financial Results", "Business update"]
    assert [event["earnings_state"] for event in page["events"]] == ["earnings", "ambiguous"]
    assert page["next_cursor"] is None
    rows = con.execute("select event_id, model, prompt_schema_version, input_hash, output_hash from catalyst_ir_classifications").fetchall()
    rows_by_input_hash = {row[3]: row for row in rows}
    assert rows_by_input_hash["input-1"][1:] == ("test-model", "classification_v1", "input-1", "output-1")
    assert rows_by_input_hash[None][1:] == (None, None, None, None)


def test_activity_page_dedupes_across_jobs_keeping_newest_row(tmp_path):
    con = repository.connect(tmp_path / "db.sqlite")
    first_job = _job(con, status="running")
    first_source = repository.save_source(con, {"job_id": first_job["job_id"], "ticker": "NVDA", "source_type": "press_releases", "url": "https://ir.example.test/news"})
    repository.save_finalized_observations(
        con,
        first_job["job_id"],
        [{"id": 1, "source_id": first_source["source_id"], "ticker": "NVDA", "source_type": "press_releases", "count_date": "2026-01-05", "title": "Business update", "url": "https://ir.example.test/one", "content_hash": "old-hash"}],
        [{"id": 1, "earnings_state": "ambiguous", "classification_method": "llm_v1"}],
    )
    second_job = _job(con, status="running")
    second_source = repository.save_source(con, {"job_id": second_job["job_id"], "ticker": "NVDA", "source_type": "press_releases", "url": "https://ir.example.test/news"})
    repository.save_finalized_observations(
        con,
        second_job["job_id"],
        [
            {"id": 1, "source_id": second_source["source_id"], "ticker": "NVDA", "source_type": "press_releases", "count_date": "2026-01-05", "title": "Business update", "url": "https://ir.example.test/one", "content_hash": "new-hash"},
            {"id": 2, "source_id": second_source["source_id"], "ticker": "NVDA", "source_type": "press_releases", "count_date": "2026-01-03", "title": "Older news", "url": "https://ir.example.test/two"},
        ],
        [{"id": 1, "earnings_state": "non_earnings", "classification_method": "llm_v1"}],
    )

    page = repository.load_ticker_activity_page(con, "NVDA", 200, None)

    assert len(page["events"]) == 2
    assert [event["title"] for event in page["events"]] == ["Business update", "Older news"]
    newest = page["events"][0]
    assert newest["job_id"] == second_job["job_id"]
    assert newest["content_hash"] == "new-hash"
    assert newest["earnings_state"] == "non_earnings"
    assert page["next_cursor"] is None


def test_activity_page_cursor_round_trip_and_ticker_isolation(tmp_path):
    con = repository.connect(tmp_path / "db.sqlite")
    job = _job(con, status="running")
    source = repository.save_source(con, {"job_id": job["job_id"], "ticker": "NVDA", "source_type": "press_releases", "url": "https://ir.example.test/news"})
    for number in range(3):
        repository.save_finalized_observations(con, job["job_id"], [{"source_id": source["source_id"], "ticker": "NVDA", "source_type": "press_releases", "count_date": f"2026-01-0{number + 1}", "title": f"News {number}", "url": f"https://ir.example.test/{number}"}], [])
    other_job = _job(con, ticker="AAPL", status="running")
    other_source = repository.save_source(con, {"job_id": other_job["job_id"], "ticker": "AAPL", "source_type": "press_releases", "url": "https://ir.example.test/apple"})
    repository.save_finalized_observations(con, other_job["job_id"], [{"source_id": other_source["source_id"], "ticker": "AAPL", "source_type": "press_releases", "count_date": "2026-01-02", "title": "Apple news", "url": "https://ir.example.test/apple-1"}], [])

    first = repository.load_ticker_activity_page(con, "NVDA", 2, None)
    second = repository.load_ticker_activity_page(con, "NVDA", 2, first["next_cursor"])

    assert first["next_cursor"]
    assert [event["title"] for event in first["events"]] == ["News 2", "News 1"]
    assert [event["title"] for event in second["events"]] == ["News 0"]
    assert second["next_cursor"] is None
    assert {event["ticker"] for event in first["events"] + second["events"]} == {"NVDA"}
    decoded = json.loads(base64.urlsafe_b64decode(first["next_cursor"] + "=" * (-len(first["next_cursor"]) % 4)).decode())
    assert "job_id" not in decoded


@pytest.mark.parametrize("limit", [0, 201, True, "10"])
def test_activity_page_rejects_invalid_limits(tmp_path, limit):
    con = repository.connect(tmp_path / "db.sqlite")
    with pytest.raises(ValueError, match="activity limit must be between 1 and 200"):
        repository.load_ticker_activity_page(con, "NVDA", limit, None)


def test_activity_cursor_rejects_job_scoped_or_cross_ticker_cursors(tmp_path):
    con = repository.connect(tmp_path / "db.sqlite")
    job_cursor = repository._encode_cursor({"ticker": "NVDA", "job_id": "cr_1", "count_date": "2026-01-01", "event_id": "ire_1"})
    ticker_cursor = repository._encode_cursor({"ticker": "AAPL", "count_date": "2026-01-01", "event_id": "ire_1"})
    with pytest.raises(ValueError, match="activity cursor does not belong to ticker"):
        repository.load_ticker_activity_page(con, "NVDA", 10, job_cursor)
    with pytest.raises(ValueError, match="activity cursor does not belong to ticker"):
        repository.load_ticker_activity_page(con, "NVDA", 10, ticker_cursor)


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


def test_fail_job_can_terminally_close_queued_or_running_job(tmp_path):
    con = repository.connect(tmp_path / "db.sqlite")
    queued = _job(con)
    repository.fail_job(con, queued["job_id"], "Authorization: Bearer secret")
    assert con.execute("select status, error_summary from catalyst_research_jobs where job_id = ?", (queued["job_id"],)).fetchone()[0:2] == ("failed", "Authorization: Bearer [redacted]")
    running = _job(con, status="running")
    repository.fail_job(con, running["job_id"], "api_key=secret token:other")
    assert con.execute("select status from catalyst_research_jobs where job_id = ?", (running["job_id"],)).fetchone()[0] == "failed"


@pytest.mark.parametrize("message", [
    "Authorization: Basic abc123",
    "Authorization=Digest abc123",
    "Cookie: session=abc123",
    "Set-Cookie: session=abc123",
    "client_secret: abc123 password=abc123",
])
def test_fail_job_sanitizes_credentials_and_cookie_shapes(tmp_path, message):
    con = repository.connect(tmp_path / "db.sqlite")
    job = _job(con)
    repository.fail_job(con, job["job_id"], message)
    error = con.execute("select error_summary from catalyst_research_jobs where job_id = ?", (job["job_id"],)).fetchone()[0]
    assert "abc123" not in error


def test_source_ambiguity_and_verification_reason_round_trip(tmp_path):
    con = repository.connect(tmp_path / "db.sqlite")
    job = _job(con, status="running")
    source = repository.save_source(con, {"job_id": job["job_id"], "ticker": "NVDA", "source_type": "press_releases", "url": "https://ir.example.test/news", "acceptance_status": "ambiguous", "verification_reason": "company identity is ambiguous"})
    assert source["acceptance_status"] == "ambiguous"
    loaded = repository.load_job_result(con, job["job_id"])
    assert loaded["sources"][0]["acceptance_status"] == "ambiguous"
    assert loaded["sources"][0]["verification_reason"] == "company identity is ambiguous"


def test_old_source_schema_migrates_ambiguity_and_preserves_foreign_keys(tmp_path):
    db_path = tmp_path / "legacy.sqlite"
    con = repository.connect(db_path)
    job = _job(con, status="running")
    source = repository.save_source(con, {"job_id": job["job_id"], "ticker": "NVDA", "source_type": "press_releases", "url": "https://ir.example.test/news", "acceptance_status": "ambiguous"})
    repository.save_finalized_observations(con, job["job_id"], [{"source_id": source["source_id"], "ticker": "NVDA", "source_type": "press_releases", "published_date": "2026-01-01", "count_date": "2026-01-01", "title": "Results", "url": "https://ir.example.test/news/results"}], [{"id": 1, "earnings_state": "earnings", "classification_method": "manual"}])
    con.execute("pragma foreign_keys = off")
    con.execute("pragma legacy_alter_table = on")
    con.execute("alter table catalyst_ir_sources rename to catalyst_ir_sources_saved")
    con.execute("""create table catalyst_ir_sources (
        source_id text primary key, job_id text not null references catalyst_research_jobs(job_id), ticker text not null,
        source_type text not null, url text not null, final_url text,
        acceptance_status text not null default 'pending' check (acceptance_status in ('pending','accepted','rejected')),
        extraction_status text not null default 'pending', active_adapter_id text, evidence_result_ids_json text not null default '[]',
        requested_start text, requested_end text, coverage_start text, coverage_end text,
        page_count integer not null default 0, item_count integer not null default 0, content_hash text,
        snapshot_hash text, truncation_reason text, discovery_provider text, execution_path text, checked_at text
    )""")
    con.execute("""insert into catalyst_ir_sources select source_id,job_id,ticker,source_type,url,final_url,'pending',extraction_status,active_adapter_id,evidence_result_ids_json,requested_start,requested_end,coverage_start,coverage_end,page_count,item_count,content_hash,snapshot_hash,truncation_reason,discovery_provider,execution_path,checked_at from catalyst_ir_sources_saved""")
    con.execute("drop table catalyst_ir_sources_saved")
    con.execute("pragma foreign_keys = on")
    con.execute("pragma legacy_alter_table = off")
    con.commit()
    con.close()

    migrated = repository.connect(db_path)
    row = migrated.execute("select acceptance_status, verification_reason from catalyst_ir_sources where source_id = ?", (source["source_id"],)).fetchone()
    assert row[0:2] == ("pending", None)
    assert migrated.execute("select count(*) from catalyst_ir_events").fetchone()[0] == 1
    assert migrated.execute("select count(*) from catalyst_ir_classifications").fetchone()[0] == 1
    assert migrated.execute("pragma foreign_key_check").fetchall() == []


def test_resolved_company_is_stored_on_running_job(tmp_path):
    con = repository.connect(tmp_path / "db.sqlite")
    job = _job(con, status="running")
    updated = repository.update_resolved_company(con, job["job_id"], {"ticker": "NVDA", "company_name": "NVIDIA Corporation", "cik": 1045810})
    assert updated["company_name"] == "NVIDIA Corporation"
    assert con.execute("select company_name, cik from catalyst_research_jobs where job_id = ?", (job["job_id"],)).fetchone()[0:2] == ("NVIDIA Corporation", "1045810")
    repository.finalize_job(con, job["job_id"], {"status": "unsupported"})
    assert repository.load_job_result(con, job["job_id"])["cik"] == "1045810"


def test_atomic_finalize_rolls_back_events_on_insert_failure(tmp_path):
    con = repository.connect(tmp_path / "db.sqlite")
    job = _job(con, status="running")
    source = repository.save_source(con, {"job_id": job["job_id"], "ticker": "NVDA", "source_type": "events_presentations", "url": "https://ir.example.test/events"})
    events = [
        {"id": 1, "source_id": source["source_id"], "ticker": "NVDA", "source_type": "events_presentations", "event_date": "2026-01-01", "count_date": "2026-01-01", "title": "Investor event", "url": None},
        {"id": 2, "source_id": source["source_id"], "ticker": "NVDA", "source_type": "events_presentations", "event_date": "2026-01-02", "count_date": "2026-01-02", "title": "", "url": "https://ir.example.test/broken"},
    ]
    with pytest.raises(ValueError, match="event title"):
        repository.finalize_job_with_observations(con, job["job_id"], events, [], {"status": "completed", "statistics": {}})
    assert con.execute("select count(*) from catalyst_ir_events where job_id = ?", (job["job_id"],)).fetchone()[0] == 0
    assert con.execute("select status from catalyst_research_jobs where job_id = ?", (job["job_id"],)).fetchone()[0] == "running"


def test_atomic_finalize_accepts_null_events_url_and_coverage_flag(tmp_path):
    con = repository.connect(tmp_path / "db.sqlite")
    job = _job(con, status="running")
    source = repository.save_source(con, {"job_id": job["job_id"], "ticker": "NVDA", "source_type": "events_presentations", "url": "https://ir.example.test/events", "extraction_status": "partial", "coverage_start": "2025-01-01", "coverage_end": "2026-01-01", "coverage_continuous": False})
    event = {"id": 1, "source_id": source["source_id"], "ticker": "NVDA", "source_type": "events_presentations", "event_date": "2026-01-01", "count_date": "2026-01-01", "title": "Investor event", "url": None}
    repository.finalize_job_with_observations(con, job["job_id"], [event], [{"id": 1, "earnings_state": "non_earnings", "classification_method": "manual"}], {"status": "completed_partial", "statistics": {"events_presentations": {"status": "partial"}}})
    row = con.execute("select canonical_url from catalyst_ir_events").fetchone()
    assert row[0] is None
    loaded = repository.load_job_result(con, job["job_id"])
    assert loaded["sources"][0]["coverage_continuous"] is False


def test_source_execution_promotion_is_atomic_and_preserves_old_active(tmp_path):
    con = repository.connect(tmp_path / "db.sqlite")
    job = _job(con, status="running")
    first = repository.create_adapter_candidate(con, {"job_id": job["job_id"], "ticker": "NVDA", "source_type": "press_releases", "source_url": "https://ir.example.test/news", "adapter": {}})
    repository.record_adapter_validation(con, {"adapter_id": first["adapter_id"], "job_id": job["job_id"], "status": "passed", "report": {}})
    repository.activate_adapter(con, first["adapter_id"], "2026-09-07T00:00:00+00:00")
    second = repository.create_adapter_candidate(con, {"job_id": job["job_id"], "ticker": "NVDA", "source_type": "press_releases", "source_url": "https://ir.example.test/news", "adapter": {}})
    repository.record_adapter_validation(con, {"adapter_id": second["adapter_id"], "job_id": job["job_id"], "status": "passed", "report": {}})
    with pytest.raises(ValueError, match="source ticker"):
        repository.activate_adapter_with_source(con, second["adapter_id"], "2026-09-07T00:00:00+00:00", {"job_id": job["job_id"], "ticker": "OTHER", "source_type": "press_releases", "url": "https://ir.example.test/news"})
    states = dict(con.execute("select adapter_id, state from catalyst_source_adapters").fetchall())
    assert states[first["adapter_id"]] == "active"
    assert states[second["adapter_id"]] == "candidate"


def test_source_execution_promotion_updates_existing_source_row_atomically(tmp_path):
    con = repository.connect(tmp_path / "db.sqlite")
    job = _job(con, status="running")
    candidate = repository.create_adapter_candidate(con, {"job_id": job["job_id"], "ticker": "NVDA", "source_type": "press_releases", "source_url": "https://ir.example.test/news", "adapter": {}})
    repository.record_adapter_validation(con, {"adapter_id": candidate["adapter_id"], "job_id": job["job_id"], "status": "passed", "report": {}})
    source = repository.save_source(con, {"job_id": job["job_id"], "ticker": "NVDA", "source_type": "press_releases", "url": "https://ir.example.test/news", "acceptance_status": "pending"})
    updated = repository.activate_adapter_with_source(con, candidate["adapter_id"], "2026-09-07T00:00:00+00:00", {**source, "acceptance_status": "accepted", "active_adapter_id": candidate["adapter_id"], "extraction_status": "complete"})
    assert updated["source_id"] == source["source_id"]
    assert con.execute("select count(*) from catalyst_ir_sources where source_id = ?", (source["source_id"],)).fetchone()[0] == 1
    assert con.execute("select acceptance_status, extraction_status from catalyst_ir_sources where source_id = ?", (source["source_id"],)).fetchone()[0:2] == ("accepted", "complete")


def test_connect_adds_v1_1_registry_tables_and_columns(tmp_path):
    con = repository.connect(tmp_path / "market.sqlite")
    try:
        tables = {row[0] for row in con.execute("select name from sqlite_master where type='table'")}
        assert {
            "catalyst_company_registry",
            "catalyst_source_endpoints",
            "catalyst_endpoint_checks",
        } <= tables
        job_columns = {row[1] for row in con.execute("pragma table_info(catalyst_research_jobs)")}
        attempt_columns = {row[1] for row in con.execute("pragma table_info(catalyst_search_attempts)")}
        source_columns = {row[1] for row in con.execute("pragma table_info(catalyst_ir_sources)")}
        event_columns = {row[1] for row in con.execute("pragma table_info(catalyst_ir_events)")}
        assert "mode" in job_columns
        assert "search_purpose" in attempt_columns
        assert {"endpoint_id", "discovery_method", "extraction_provider", "attempts_json"} <= source_columns
        assert {"endpoint_id", "external_guid", "discovery_method", "extraction_provider"} <= event_columns
    finally:
        con.close()


def test_v1_database_migrates_additively_and_preserves_readable_rows(tmp_path):
    db_path = tmp_path / "v1.sqlite"
    con = repository.connect(db_path)
    job = _job(con, status="running")
    source = repository.save_source(con, {"job_id": job["job_id"], "ticker": "NVDA", "source_type": "press_releases", "url": "https://ir.example.test/news"})
    repository.save_finalized_observations(
        con,
        job["job_id"],
        [{"id": 1, "source_id": source["source_id"], "ticker": "NVDA", "source_type": "press_releases", "count_date": "2026-01-01", "title": "Results", "url": "https://ir.example.test/results"}],
        [{"id": 1, "earnings_state": "earnings", "classification_method": "manual"}],
    )
    repository.finalize_job(con, job["job_id"], {"status": "completed", "statistics": {"total": 1}})
    adapter_job = _job(con, status="running")
    candidate = repository.create_adapter_candidate(con, {"job_id": adapter_job["job_id"], "ticker": "NVDA", "source_type": "press_releases", "source_url": "https://ir.example.test/news", "adapter": {}})
    repository.record_adapter_validation(con, {"adapter_id": candidate["adapter_id"], "job_id": adapter_job["job_id"], "status": "passed", "report": {}})
    repository.activate_adapter(con, candidate["adapter_id"], "2026-09-04T01:00:00+00:00")
    before = repository.load_job_result(con, job["job_id"])
    con.close()

    raw = sqlite3.connect(db_path)
    raw.execute("drop table catalyst_company_registry")
    raw.execute("drop table catalyst_source_endpoints")
    raw.execute("drop table catalyst_endpoint_checks")
    raw.execute("alter table catalyst_research_jobs drop column mode")
    raw.execute("alter table catalyst_search_attempts drop column search_purpose")
    for column in ("endpoint_id", "discovery_method", "extraction_provider", "attempts_json"):
        raw.execute(f"alter table catalyst_ir_sources drop column {column}")
    for column in ("endpoint_id", "external_guid", "discovery_method", "extraction_provider"):
        raw.execute(f"alter table catalyst_ir_events drop column {column}")
    raw.commit()
    raw.close()

    migrated = repository.connect(db_path)
    tables = {row[0] for row in migrated.execute("select name from sqlite_master where type='table'")}
    assert {
        "catalyst_company_registry",
        "catalyst_source_endpoints",
        "catalyst_endpoint_checks",
    } <= tables
    assert "mode" in {row[1] for row in migrated.execute("pragma table_info(catalyst_research_jobs)")}
    assert "attempts_json" in {row[1] for row in migrated.execute("pragma table_info(catalyst_ir_sources)")}
    assert migrated.execute("pragma foreign_key_check").fetchall() == []
    assert repository.load_job_result(migrated, job["job_id"]) == before
    assert repository.load_active_adapter(migrated, "NVDA", "press_releases")["adapter_id"] == candidate["adapter_id"]
    migrated.close()


def test_save_source_persists_extraction_attempts(tmp_path):
    con = repository.connect(tmp_path / "market_data.sqlite")
    job = _job(con, status="running")
    attempts = [
        {"provider": "direct_http", "outcome": "request_failed"},
        {"provider": "firecrawl", "outcome": "metadata_missing"},
    ]
    source = repository.save_source(
        con,
        {
            "job_id": job["job_id"],
            "ticker": "NVDA",
            "source_type": "press_releases",
            "url": "https://ir.example.test/news",
            "extraction_status": "failed",
            "attempts": attempts,
        },
    )
    assert source["attempts"] == attempts
    stored = con.execute("select attempts_json from catalyst_ir_sources where source_id = ?", (source["source_id"],)).fetchone()[0]
    assert json.loads(stored) == attempts


def test_save_source_without_attempts_defaults_to_empty_list(tmp_path):
    con = repository.connect(tmp_path / "market_data.sqlite")
    job = _job(con, status="running")
    source = repository.save_source(
        con,
        {"job_id": job["job_id"], "ticker": "NVDA", "source_type": "press_releases", "url": "https://ir.example.test/news"},
    )
    assert source["attempts"] == []


def test_list_event_normalized_titles_returns_ticker_scoped_titles(tmp_path):
    con = repository.connect(tmp_path / "market_data.sqlite")
    job = _job(con, status="running")
    source = repository.save_source(con, {"job_id": job["job_id"], "ticker": "NVDA", "source_type": "press_releases", "url": "https://ir.example.test/news"})
    repository.save_finalized_observations(
        con,
        job["job_id"],
        [{"id": 1, "source_id": source["source_id"], "ticker": "NVDA", "source_type": "press_releases", "count_date": "2026-01-01", "title": "NVIDIA Announces Results", "url": "https://ir.example.test/results"}],
        [],
    )
    assert repository.list_event_normalized_titles(con, "NVDA") == ["nvidia announces results"]
    assert repository.list_event_normalized_titles(con, "AAPL") == []


def test_registry_version_increments_without_deleting_endpoint_history(tmp_path):
    con = repository.connect(tmp_path / "market.sqlite")
    first = repository.save_company_registry(con, registry_payload(version=1))
    endpoint = repository.upsert_source_endpoint(con, endpoint_payload(first["ticker"]))
    repository.record_endpoint_check(con, check_payload(endpoint["endpoint_id"]))
    second = repository.save_company_registry(con, registry_payload(version=2))
    assert second["registry_version"] == 2
    assert repository.load_source_endpoints(con, "NVDA")[0]["endpoint_id"] == endpoint["endpoint_id"]
    assert con.execute("select count(*) from catalyst_endpoint_checks").fetchone()[0] == 1


def test_registry_load_returns_none_and_round_trips_domains(tmp_path):
    con = repository.connect(tmp_path / "db.sqlite")
    assert repository.load_company_registry(con, "NVDA") is None
    saved = repository.save_company_registry(con, registry_payload())
    loaded = repository.load_company_registry(con, "nvda")
    assert loaded["registry_version"] == 1
    assert loaded["official_domains"] == saved["official_domains"]
    assert "official_domains_json" not in loaded


def test_registry_initial_version_must_be_one(tmp_path):
    con = repository.connect(tmp_path / "db.sqlite")
    with pytest.raises(ValueError, match="version"):
        repository.save_company_registry(con, registry_payload(version=2))


def test_registry_version_must_advance_by_one(tmp_path):
    con = repository.connect(tmp_path / "db.sqlite")
    repository.save_company_registry(con, registry_payload(version=1))
    with pytest.raises(ValueError, match="version"):
        repository.save_company_registry(con, registry_payload(version=3))
    with pytest.raises(ValueError, match="version"):
        repository.save_company_registry(con, registry_payload(version=1, company_name="Changed Name"))


def test_registry_idempotent_rewrite_keeps_version_and_single_row(tmp_path):
    con = repository.connect(tmp_path / "db.sqlite")
    repository.save_company_registry(con, registry_payload(version=1))
    again = repository.save_company_registry(con, registry_payload(version=1))
    assert again["registry_version"] == 1
    assert con.execute("select count(*) from catalyst_company_registry where ticker = 'NVDA'").fetchone()[0] == 1


@pytest.mark.parametrize("overrides,match", [
    ({"source_confidence": "certain"}, "confidence"),
    ({"official_domains": []}, "domains"),
    ({"official_domains": "nvidianews.nvidia.com"}, "domains"),
    ({"registry_version": 0}, "version"),
])
def test_registry_rejects_invalid_payloads(tmp_path, overrides, match):
    con = repository.connect(tmp_path / "db.sqlite")
    with pytest.raises(ValueError, match=match):
        repository.save_company_registry(con, registry_payload(**overrides))


@pytest.mark.parametrize("overrides,match", [
    ({"channel": "news"}, "channel"),
    ({"endpoint_type": "html"}, "type"),
    ({"status": "broken"}, "status"),
    ({"confidence": "certain"}, "confidence"),
    ({"domain": ""}, "domain"),
])
def test_endpoint_upsert_rejects_invalid_enums_and_missing_domain(tmp_path, overrides, match):
    con = repository.connect(tmp_path / "db.sqlite")
    with pytest.raises(ValueError, match=match):
        repository.upsert_source_endpoint(con, endpoint_payload(**overrides))


def test_duplicate_endpoint_upsert_reuses_identity_and_updates_fields(tmp_path):
    con = repository.connect(tmp_path / "db.sqlite")
    first = repository.upsert_source_endpoint(con, endpoint_payload())
    second = repository.upsert_source_endpoint(con, endpoint_payload(status="active", confidence="medium"))
    assert second["endpoint_id"] == first["endpoint_id"]
    assert second["status"] == "active"
    assert second["confidence"] == "medium"
    assert con.execute("select count(*) from catalyst_source_endpoints").fetchone()[0] == 1
    loaded = repository.load_source_endpoints(con, "NVDA", channel="press_releases")
    assert len(loaded) == 1
    assert loaded[0]["endpoint_id"] == first["endpoint_id"]


def test_load_source_endpoints_filters_by_channel_and_statuses(tmp_path):
    con = repository.connect(tmp_path / "db.sqlite")
    repository.upsert_source_endpoint(con, endpoint_payload(url="https://a.test/rss", domain="a.test"))
    repository.upsert_source_endpoint(con, endpoint_payload(channel="events_presentations", endpoint_type="atom", url="https://b.test/atom", domain="b.test", status="active"))
    assert len(repository.load_source_endpoints(con, "NVDA")) == 2
    assert len(repository.load_source_endpoints(con, "NVDA", channel="press_releases")) == 1
    assert [item["channel"] for item in repository.load_source_endpoints(con, "NVDA", statuses={"active"})] == ["events_presentations"]
    with pytest.raises(ValueError, match="statuses"):
        repository.load_source_endpoints(con, "NVDA", statuses={"broken"})


def test_endpoint_check_allows_null_job_id_and_rejects_negative_counts(tmp_path):
    con = repository.connect(tmp_path / "db.sqlite")
    endpoint = repository.upsert_source_endpoint(con, endpoint_payload())
    check = repository.record_endpoint_check(con, check_payload(endpoint["endpoint_id"]))
    assert check["job_id"] is None
    assert check["check_id"].startswith("cec_")
    assert con.execute("select count(*) from catalyst_endpoint_checks").fetchone()[0] == 1
    with pytest.raises(ValueError, match="check item count"):
        repository.record_endpoint_check(con, check_payload(endpoint["endpoint_id"], item_count=-1))
    with pytest.raises(ValueError, match="new item count"):
        repository.record_endpoint_check(con, check_payload(endpoint["endpoint_id"], new_item_count=-1))
    with pytest.raises(ValueError, match="not found"):
        repository.record_endpoint_check(con, check_payload("cse_missing"))


def test_update_endpoint_health_touches_only_health_and_watermark_columns(tmp_path):
    con = repository.connect(tmp_path / "db.sqlite")
    endpoint = repository.upsert_source_endpoint(con, endpoint_payload())
    updated = repository.update_endpoint_health(
        con,
        endpoint["endpoint_id"],
        {"status": "failing", "consecutive_failures": 3, "last_error_code": "timeout", "last_checked_at": "2026-09-08T01:00:00+00:00"},
    )
    assert updated["status"] == "failing"
    assert updated["consecutive_failures"] == 3
    assert updated["last_error_code"] == "timeout"
    assert updated["last_checked_at"] == "2026-09-08T01:00:00+00:00"
    assert updated["domain"] == endpoint["domain"]
    assert updated["discovered_at"] == endpoint["discovered_at"]
    with pytest.raises(ValueError, match="not updatable"):
        repository.update_endpoint_health(con, endpoint["endpoint_id"], {"domain": "evil.test"})
    with pytest.raises(ValueError, match="failures"):
        repository.update_endpoint_health(con, endpoint["endpoint_id"], {"consecutive_failures": -1})
    with pytest.raises(ValueError, match="not found"):
        repository.update_endpoint_health(con, "cse_missing", {"status": "active"})


def test_terminal_job_rejects_source_provenance_writes(tmp_path):
    con = repository.connect(tmp_path / "db.sqlite")
    job = _job(con, status="running")
    repository.finalize_job(con, job["job_id"], {"status": "completed"})
    with pytest.raises(ValueError, match="terminal"):
        repository.save_source(con, {"job_id": job["job_id"], "ticker": "NVDA", "source_type": "press_releases", "url": "https://ir.example.test/news", "endpoint_id": "cse_x", "discovery_method": "search", "extraction_provider": "direct_http"})


def test_invalid_discovery_method_and_extraction_provider_are_rejected(tmp_path):
    con = repository.connect(tmp_path / "db.sqlite")
    job = _job(con, status="running")
    with pytest.raises(ValueError, match="discovery method"):
        repository.save_source(con, {"job_id": job["job_id"], "ticker": "NVDA", "source_type": "press_releases", "url": "https://ir.example.test/news", "discovery_method": "crawl"})
    with pytest.raises(ValueError, match="extraction provider"):
        repository.save_source(con, {"job_id": job["job_id"], "ticker": "NVDA", "source_type": "press_releases", "url": "https://ir.example.test/news", "extraction_provider": "browser"})


def test_event_provenance_columns_round_trip(tmp_path):
    con = repository.connect(tmp_path / "db.sqlite")
    job = _job(con, status="running")
    endpoint = repository.upsert_source_endpoint(con, endpoint_payload())
    source = repository.save_source(con, {"job_id": job["job_id"], "ticker": "NVDA", "source_type": "press_releases", "url": "https://nvidianews.nvidia.com/rss", "endpoint_id": endpoint["endpoint_id"], "discovery_method": "rss", "extraction_provider": "feed_metadata"})
    assert source["endpoint_id"] == endpoint["endpoint_id"]
    assert source["discovery_method"] == "rss"
    repository.save_finalized_observations(
        con,
        job["job_id"],
        [{"id": 1, "source_id": source["source_id"], "ticker": "NVDA", "source_type": "press_releases", "count_date": "2026-09-01", "title": "Launch", "url": "https://nvidianews.nvidia.com/launch", "endpoint_id": endpoint["endpoint_id"], "external_guid": "guid-1", "discovery_method": "rss", "extraction_provider": "feed_metadata"}],
        [{"id": 1, "earnings_state": "non_earnings", "classification_method": "manual"}],
    )
    page = repository.load_events_page(con, "NVDA", job["job_id"], 10, None)
    event = page["events"][0]
    assert event["endpoint_id"] == endpoint["endpoint_id"]
    assert event["external_guid"] == "guid-1"
    assert event["discovery_method"] == "rss"
    assert event["extraction_provider"] == "feed_metadata"
    result = repository.load_job_result(con, job["job_id"])
    assert result["sources"][0]["endpoint_id"] == endpoint["endpoint_id"]


def test_event_url_seen_only_counts_successful_persisted_events(tmp_path):
    con = repository.connect(tmp_path / "db.sqlite")
    good = _job(con, status="running")
    good_source = repository.save_source(con, {"job_id": good["job_id"], "ticker": "NVDA", "source_type": "press_releases", "url": "https://ir.example.test/good"})
    repository.save_finalized_observations(con, good["job_id"], [{"source_id": good_source["source_id"], "ticker": "NVDA", "source_type": "press_releases", "count_date": "2026-01-01", "title": "Good", "url": "https://ir.example.test/good-item"}], [])
    repository.finalize_job(con, good["job_id"], {"status": "completed"})
    bad = _job(con, status="running")
    bad_source = repository.save_source(con, {"job_id": bad["job_id"], "ticker": "NVDA", "source_type": "press_releases", "url": "https://ir.example.test/bad"})
    repository.save_finalized_observations(con, bad["job_id"], [{"source_id": bad_source["source_id"], "ticker": "NVDA", "source_type": "press_releases", "count_date": "2026-01-02", "title": "Bad", "url": "https://ir.example.test/bad-item"}], [])
    repository.finalize_job(con, bad["job_id"], {"status": "failed"})
    assert repository.event_url_seen(con, "NVDA", "https://ir.example.test/good-item") is True
    assert repository.event_url_seen(con, "NVDA", "https://ir.example.test/bad-item") is False
    assert repository.event_url_seen(con, "NVDA", "https://ir.example.test/never") is False
    assert repository.event_url_seen(con, "AAPL", "https://ir.example.test/good-item") is False
    with pytest.raises(ValueError, match="url"):
        repository.event_url_seen(con, "NVDA", "")


def test_search_attempt_persists_purpose_and_latest_gap_search_at(tmp_path):
    con = repository.connect(tmp_path / "db.sqlite")
    job = _job(con, status="running")
    repository.record_search_attempt(con, {"job_id": job["job_id"], "provider": "ddgs", "query": "nvidia news"})
    assert con.execute("select search_purpose from catalyst_search_attempts where job_id = ?", (job["job_id"],)).fetchone()[0] == "source_discovery"
    repository.record_search_attempt(con, {"job_id": job["job_id"], "provider": "ddgs", "query": "nvidia gap", "search_purpose": "incremental_gap_check", "completed_at": "2026-09-01T00:00:00+00:00"})
    repository.record_search_attempt(con, {"job_id": job["job_id"], "provider": "ddgs", "query": "nvidia gap later", "search_purpose": "incremental_gap_check", "completed_at": "2026-09-05T00:00:00+00:00"})
    assert repository.load_latest_gap_search_at(con, "NVDA", "press_releases") == "2026-09-05T00:00:00+00:00"
    assert repository.load_latest_gap_search_at(con, "AAPL", "press_releases") is None
    with pytest.raises(ValueError, match="purpose"):
        repository.record_search_attempt(con, {"job_id": job["job_id"], "provider": "ddgs", "query": "x", "search_purpose": "crawl"})


def test_create_job_persists_mode_and_validates_value(tmp_path):
    con = repository.connect(tmp_path / "db.sqlite")
    job = repository.create_job(con, {"ticker": "NVDA", "years": 1, "mode": "update"})
    assert job["mode"] == "update"
    assert con.execute("select mode from catalyst_research_jobs where job_id = ?", (job["job_id"],)).fetchone()[0] == "update"
    assert _job(con)["mode"] == "research"
    with pytest.raises(ValueError, match="mode"):
        repository.create_job(con, {"ticker": "NVDA", "years": 1, "mode": "crawl"})


def test_source_external_guid_provenance_round_trip(tmp_path):
    con = repository.connect(tmp_path / "db.sqlite")
    columns = {row[1] for row in con.execute("pragma table_info(catalyst_ir_sources)")}
    assert "external_guid" in columns
    job = _job(con, status="running")
    endpoint = repository.upsert_source_endpoint(con, endpoint_payload())
    source = repository.save_source(
        con,
        {
            "job_id": job["job_id"],
            "ticker": "NVDA",
            "source_type": "press_releases",
            "url": "https://nvidianews.nvidia.com/rss",
            "endpoint_id": endpoint["endpoint_id"],
            "external_guid": "guid-9",
            "discovery_method": "rss",
            "extraction_provider": "feed_metadata",
        },
    )
    assert source["external_guid"] == "guid-9"
    result = repository.load_job_result(con, job["job_id"])
    assert result["sources"][0]["external_guid"] == "guid-9"


def test_source_url_seen_detects_persisted_source_urls_across_jobs(tmp_path):
    con = repository.connect(tmp_path / "db.sqlite")
    job = _job(con, status="running")
    repository.save_source(
        con,
        {
            "job_id": job["job_id"],
            "ticker": "NVDA",
            "source_type": "press_releases",
            "url": "https://nvidianews.nvidia.com/news/nvidia-announces-new-platform",
            "acceptance_status": "ambiguous",
            "extraction_status": "failed",
            "extraction_provider": "manual",
        },
    )
    assert repository.source_url_seen(con, "NVDA", "https://nvidianews.nvidia.com/news/nvidia-announces-new-platform") is True
    assert repository.source_url_seen(con, "NVDA", "https://nvidianews.nvidia.com/news/other") is False
    assert repository.source_url_seen(con, "AAPL", "https://nvidianews.nvidia.com/news/nvidia-announces-new-platform") is False
    with pytest.raises(ValueError, match="url"):
        repository.source_url_seen(con, "NVDA", "")


LEGACY_RESEARCH_VERSION = "catalyst_research_v1"
LEGACY_RESULT_SCHEMA_VERSION = "catalyst_research_result_v1"
V1_1_RESULT_SCHEMA_VERSION = "catalyst_research_result_v1_1"


def _mark_legacy_research_version(con, job_id):
    con.execute(
        "update catalyst_research_jobs set research_version = ? where job_id = ?",
        (LEGACY_RESEARCH_VERSION, job_id),
    )
    con.commit()


def test_load_job_result_selects_stored_legacy_schema_version(tmp_path):
    con = repository.connect(tmp_path / "db.sqlite")
    job = _job(con, status="running")
    _mark_legacy_research_version(con, job["job_id"])
    repository.finalize_job(
        con,
        job["job_id"],
        {"status": "completed", "statistics": {"press_releases": {"status": "complete", "total": 2, "per_month": 0.17}}},
    )

    result = repository.load_job_result(con, job["job_id"])

    assert result["schema_version"] == LEGACY_RESULT_SCHEMA_VERSION
    assert result["research_version"] == LEGACY_RESEARCH_VERSION
    assert result["mode"] == "research"
    assert result["statistics"]["press_releases"]["total"] == 2
    assert result["statistics"]["press_releases"]["per_month"] == 0.17
    assert "coverage_status" not in result["statistics"]["press_releases"]
    assert "observed_total" not in result["statistics"]["press_releases"]


def test_load_job_result_reports_v1_1_schema_version_and_stored_mode(tmp_path):
    con = repository.connect(tmp_path / "db.sqlite")
    job = repository.create_job(
        con,
        {"ticker": "NVDA", "years": 1, "mode": "update"},
        {"name": "NVIDIA Corporation", "cik": "1045810"},
        datetime(2026, 9, 4, tzinfo=UTC),
    )
    repository.start_job(con, job["job_id"], "2026-09-04T00:01:00+00:00")
    repository.finalize_job(
        con,
        job["job_id"],
        {
            "status": "completed_partial",
            "statistics": {"press_releases": {"coverage_status": "observed_partial", "observed_total": 3}},
        },
    )

    result = repository.load_job_result(con, job["job_id"])

    assert result["schema_version"] == V1_1_RESULT_SCHEMA_VERSION
    assert result["mode"] == "update"
    assert result["statistics"]["press_releases"]["observed_total"] == 3


def test_load_latest_result_falls_back_to_prior_usable_legacy_result(tmp_path):
    con = repository.connect(tmp_path / "db.sqlite")
    legacy = _job(con, status="running")
    _mark_legacy_research_version(con, legacy["job_id"])
    repository.finalize_job(
        con,
        legacy["job_id"],
        {"status": "completed", "statistics": {"press_releases": {"status": "complete", "total": 1}}, "completed_at": "2026-09-01T00:00:00+00:00"},
    )
    failed = _job(con)
    repository.fail_job(con, failed["job_id"], "provider exhausted", completed_at="2026-09-08T00:00:00+00:00")

    result = repository.load_latest_result(con, "NVDA")

    assert result["job_id"] == legacy["job_id"]
    assert result["schema_version"] == LEGACY_RESULT_SCHEMA_VERSION
    assert result["mode"] == "research"
    assert result["statistics"]["press_releases"]["total"] == 1
    assert result["latest_job_id"] == failed["job_id"]
    assert result["latest_job_status"] == "failed"


def _finalize_v1_1_job(con, mode, *, events=None, status="completed", completed_at="2026-09-08T00:00:00+00:00"):
    job = repository.create_job(
        con,
        {"ticker": "NVDA", "years": 1, "mode": mode},
        {"name": "NVIDIA Corporation", "cik": "1045810"},
        datetime(2026, 9, 8, tzinfo=UTC),
    )
    repository.start_job(con, job["job_id"], "2026-09-08T00:00:30+00:00")
    if events:
        source = repository.save_source(
            con,
            {"job_id": job["job_id"], "ticker": "NVDA", "source_type": "press_releases", "url": "https://nvidianews.nvidia.com/news"},
        )
        rows = [
            {
                "event_id": f"ire_{mode}_{index}",
                "source_id": source["source_id"],
                "ticker": "NVDA",
                "source_type": "press_releases",
                "published_date": "2026-09-07",
                "count_date": "2026-09-07",
                "title": f"NVIDIA update {index}",
                "url": f"https://nvidianews.nvidia.com/news/{index}",
            }
            for index, _ in enumerate(events, 1)
        ]
        repository.save_finalized_observations(
            con,
            job["job_id"],
            rows,
            [{"event_id": row["event_id"], "earnings_state": "non_earnings", "classification_method": "rule_v1"} for row in rows],
        )
    repository.finalize_job(
        con,
        job["job_id"],
        {"status": status, "statistics": {"press_releases": {"observed_total": len(events or [])}}, "completed_at": completed_at},
    )
    return job


def test_load_latest_result_excludes_zero_event_rediscover_job(tmp_path):
    con = repository.connect(tmp_path / "db.sqlite")
    prior = _finalize_v1_1_job(con, "research", events=[object()], completed_at="2026-09-01T00:00:00+00:00")
    rediscover = _finalize_v1_1_job(con, "rediscover", events=[], status="completed")

    result = repository.load_latest_result(con, "NVDA")

    assert result["job_id"] == prior["job_id"]
    assert result["latest_job_id"] == rediscover["job_id"]
    assert result["latest_job_status"] == "completed"


def test_load_latest_result_excludes_zero_event_update_job(tmp_path):
    con = repository.connect(tmp_path / "db.sqlite")
    prior = _finalize_v1_1_job(con, "research", events=[object()], completed_at="2026-09-01T00:00:00+00:00")
    update = _finalize_v1_1_job(con, "update", events=[], status="completed")

    result = repository.load_latest_result(con, "NVDA")

    assert result["job_id"] == prior["job_id"]
    assert result["latest_job_id"] == update["job_id"]


def test_load_latest_result_selects_update_job_with_new_events(tmp_path):
    con = repository.connect(tmp_path / "db.sqlite")
    prior = _finalize_v1_1_job(con, "research", events=[object()], status="completed_partial", completed_at="2026-09-01T00:00:00+00:00")
    update = _finalize_v1_1_job(con, "update", events=[object(), object()], status="completed")

    result = repository.load_latest_result(con, "NVDA")

    assert result["job_id"] == update["job_id"]
    assert result["mode"] == "update"
    assert result["observation_count"] == 2
    assert result["latest_job_id"] == update["job_id"]
    assert prior["job_id"] != update["job_id"]


def test_load_latest_result_keeps_zero_event_research_job_usable(tmp_path):
    con = repository.connect(tmp_path / "db.sqlite")
    research = _finalize_v1_1_job(con, "research", events=[], status="completed")

    result = repository.load_latest_result(con, "NVDA")

    assert result["job_id"] == research["job_id"]


def test_load_job_result_schema_version_tracks_research_version(tmp_path):
    con = repository.connect(tmp_path / "db.sqlite")
    v1_1_job = _job(con, status="running")
    assert repository.load_job_result_schema_version(con, v1_1_job["job_id"]) == V1_1_RESULT_SCHEMA_VERSION
    _mark_legacy_research_version(con, v1_1_job["job_id"])
    assert repository.load_job_result_schema_version(con, v1_1_job["job_id"]) == LEGACY_RESULT_SCHEMA_VERSION
    with pytest.raises(ValueError, match="was not found"):
        repository.load_job_result_schema_version(con, "cr_missing")


def test_accumulated_channel_events_dedupe_across_jobs_and_clip_to_window(tmp_path):
    con = repository.connect(tmp_path / "db.sqlite")
    first_job = _job(con, status="running")
    first_source = repository.save_source(con, {"job_id": first_job["job_id"], "ticker": "NVDA", "source_type": "press_releases", "url": "https://ir.example.test/first"})
    second_job = _job(con, status="running")
    second_source = repository.save_source(con, {"job_id": second_job["job_id"], "ticker": "NVDA", "source_type": "press_releases", "url": "https://ir.example.test/second"})
    shared = {"source_type": "press_releases", "count_date": "2026-01-05", "title": "Shared event", "url": "https://ir.example.test/shared"}
    repository.save_finalized_observations(con, first_job["job_id"], [{**shared, "source_id": first_source["source_id"], "ticker": "NVDA"}], [])
    repository.save_finalized_observations(
        con,
        second_job["job_id"],
        [
            {**shared, "source_id": second_source["source_id"], "ticker": "NVDA"},
            {"source_id": second_source["source_id"], "ticker": "NVDA", "source_type": "press_releases", "count_date": "2026-02-01", "title": "Second only", "url": "https://ir.example.test/second-only"},
            {"source_id": second_source["source_id"], "ticker": "NVDA", "source_type": "press_releases", "count_date": "2027-01-05", "title": "Outside window", "url": "https://ir.example.test/outside"},
        ],
        [],
    )

    rows = repository.load_accumulated_channel_events(con, "NVDA", "2026-01-01", "2026-12-31")

    assert [(row["count_date"], row["title"]) for row in rows] == [("2026-01-05", "Shared event"), ("2026-02-01", "Second only")]
    con.close()


@pytest.mark.parametrize("start,end", [(None, "2026-12-31"), ("2026-01-01", None), ("2026-12-31", "2026-01-01")])
def test_accumulated_channel_events_reject_invalid_window(tmp_path, start, end):
    con = repository.connect(tmp_path / "db.sqlite")

    with pytest.raises(ValueError, match="accumulated events window is invalid"):
        repository.load_accumulated_channel_events(con, "NVDA", start, end)
    con.close()

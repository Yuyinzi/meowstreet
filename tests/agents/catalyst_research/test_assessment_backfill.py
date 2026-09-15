import asyncio
from datetime import UTC, datetime

import pytest

from app.agents.catalyst_research.assessment_backfill import backfill_catalyst_assessments
from app.agents.catalyst_research.persistence import repository


def _setup_events(con, titles):
    job = repository.create_job(
        con,
        {"ticker": "NVDA", "years": 2},
        {"name": "NVIDIA Corporation", "cik": "1045810"},
        datetime(2026, 9, 15, tzinfo=UTC),
    )
    repository.start_job(con, job["job_id"], "2026-09-15T00:01:00+00:00")
    source = repository.save_source(con, {"job_id": job["job_id"], "ticker": "NVDA", "source_type": "press_releases", "url": "https://ir.example.test/news"})
    events = [
        {
            "source_id": source["source_id"],
            "ticker": "NVDA",
            "source_type": "press_releases",
            "count_date": f"2026-01-0{index + 1}",
            "title": title,
            "url": f"https://ir.example.test/{index}",
            "earnings_state": "earnings" if "Results" in title else "non_earnings",
        }
        for index, title in enumerate(titles)
    ]
    repository.save_finalized_observations(con, job["job_id"], events, [])
    return job


async def _fake_assess(events, *, llm_client=None, model=None, batch_size=50):
    assessed = []
    for event in events:
        if event.get("earnings_state") == "earnings":
            assessed.append({**event, "catalyst_type": "earnings_results", "meaningful_state": "meaningful", "catalyst_type_method": "rule_v1", "meaningful_method": "rule_v1"})
        else:
            assessed.append({**event, "catalyst_type": "pr_other", "meaningful_state": "non_meaningful", "catalyst_type_method": "catalyst_assessment_v1", "meaningful_method": "catalyst_assessment_v1"})
    return {"events": assessed, "llm_call_count": 1, "provenance": []}


def test_backfill_dry_run_reports_pending_without_writes(tmp_path):
    con = repository.connect(tmp_path / "db.sqlite")
    job = _setup_events(con, ["NVIDIA Reports Results", "NVIDIA news item"])

    result = asyncio.run(backfill_catalyst_assessments(con, ticker="NVDA", dry_run=True, dependencies={"assess_catalyst_events": _fake_assess}))

    assert result == {"ticker": "NVDA", "pending": 2, "assessed": 0, "llm_call_count": 0, "dry_run": True}
    assert len(repository.load_unassessed_events(con, ticker="NVDA")) == 2
    assert con.execute("select count(*) from catalyst_ir_catalyst_assessments").fetchone()[0] == 0
    con.close()


def test_backfill_applies_assessments_in_batches(tmp_path):
    con = repository.connect(tmp_path / "db.sqlite")
    _setup_events(con, ["NVIDIA Reports Results", "NVIDIA news item", "NVIDIA partnership"])

    result = asyncio.run(backfill_catalyst_assessments(con, ticker="NVDA", batch_size=2, dependencies={"assess_catalyst_events": _fake_assess}))

    assert result["assessed"] == 3
    assert result["dry_run"] is False
    rows = con.execute("select title, catalyst_type, meaningful_state from catalyst_ir_events order by count_date").fetchall()
    assert [(row["title"], row["catalyst_type"], row["meaningful_state"]) for row in rows] == [
        ("NVIDIA Reports Results", "earnings_results", "meaningful"),
        ("NVIDIA news item", "pr_other", "non_meaningful"),
        ("NVIDIA partnership", "pr_other", "non_meaningful"),
    ]
    assert con.execute("select count(*) from catalyst_ir_catalyst_assessments").fetchone()[0] == 3
    assert repository.load_unassessed_events(con, ticker="NVDA") == []
    con.close()


def test_backfill_rejects_invalid_batch_size(tmp_path):
    con = repository.connect(tmp_path / "db.sqlite")

    with pytest.raises(ValueError, match="batch size"):
        asyncio.run(backfill_catalyst_assessments(con, batch_size=0))
    con.close()

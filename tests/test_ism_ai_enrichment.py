from app.db import growth_cycle, us_rates_liquidity
from app.services import ism_ai_enrichment


def snapshot(url, survey_type, report_month, parse_status="ok", fetched_at=None):
    return {
        "source_url": url,
        "source_name": "prnewswire",
        "survey_type": survey_type,
        "source_hash": f"hash-{url}",
        "fetched_at": fetched_at or f"{report_month}T12:00:00Z",
        "raw_html": "<html>report</html>",
        "parse_status": parse_status,
        "parse_error": None,
        "report_id": f"ism_{survey_type}_{report_month[:7].replace('-', '_')}",
        "report_month": report_month,
    }


def test_load_source_snapshots_returns_only_successful_survey_rows(tmp_path):
    con = us_rates_liquidity.connect(tmp_path / "market.sqlite")
    growth_cycle.init_db(con)
    growth_cycle.replace_ism_report_source_snapshot(
        con, snapshot("https://example.test/mfg", "manufacturing", "2026-07-01")
    )
    growth_cycle.replace_ism_report_source_snapshot(
        con, snapshot("https://example.test/services", "services", "2026-07-01")
    )
    growth_cycle.replace_ism_report_source_snapshot(
        con,
        snapshot(
            "https://example.test/failed",
            "manufacturing",
            "2026-08-01",
            parse_status="failed",
        ),
    )

    rows = growth_cycle.load_ism_report_source_snapshots(con, "manufacturing")

    con.close()
    assert [row["source_url"] for row in rows] == ["https://example.test/mfg"]


def test_latest_month_selection_does_not_fall_back_to_stale_snapshot():
    rows = [snapshot("https://example.test/july", "services", "2026-07-01")]

    selected = ism_ai_enrichment.select_snapshots(
        rows,
        latest_month="2026-08-01",
    )

    assert selected == []


def test_non_url_selection_keeps_latest_snapshot_per_report_month():
    rows = [
        snapshot(
            "https://example.test/old",
            "services",
            "2026-07-01",
            fetched_at="2026-07-02T12:00:00Z",
        ),
        snapshot(
            "https://example.test/new",
            "services",
            "2026-07-01",
            fetched_at="2026-07-03T12:00:00Z",
        ),
        snapshot("https://example.test/june", "services", "2026-06-01"),
    ]

    selected = ism_ai_enrichment.select_snapshots(rows, backfill_since="2026")

    assert [row["source_url"] for row in selected] == [
        "https://example.test/june",
        "https://example.test/new",
    ]


def test_source_url_selection_preserves_requested_url_order_without_deduplication():
    rows = [
        snapshot("https://example.test/first", "services", "2026-06-01"),
        snapshot("https://example.test/second", "services", "2026-07-01"),
    ]

    selected = ism_ai_enrichment.select_snapshots(
        rows,
        source_urls=["https://example.test/second", "https://example.test/first"],
    )

    assert [row["source_url"] for row in selected] == [
        "https://example.test/second",
        "https://example.test/first",
    ]


def test_source_url_and_period_selection_returns_union_in_core_order():
    rows = [
        snapshot("https://example.test/repair", "services", "2026-06-01"),
        snapshot("https://example.test/july", "services", "2026-07-01"),
        snapshot("https://example.test/august", "services", "2026-08-01"),
    ]

    selected = ism_ai_enrichment.select_snapshots(
        rows,
        current_year=2026,
        source_urls=["https://example.test/repair"],
    )

    assert [row["source_url"] for row in selected] == [
        "https://example.test/repair",
        "https://example.test/july",
        "https://example.test/august",
    ]


def test_enrich_snapshots_returns_ordered_structured_failures():
    rows = [
        snapshot("https://example.test/first", "services", "2026-06-01"),
        snapshot("https://example.test/second", "services", "2026-07-01"),
    ]

    def enrich_one(row):
        if row["source_url"].endswith("second"):
            raise RuntimeError("enrichment failed")
        return {"report_id": row["report_id"]}

    results, failures = ism_ai_enrichment.enrich_snapshots(rows, enrich_one)

    assert results == [{"report_id": rows[0]["report_id"]}, None]
    assert failures == [
        {
            "survey_type": "services",
            "report_id": "ism_services_2026_07",
            "source_url": "https://example.test/second",
            "error": "enrichment failed",
        }
    ]


def test_enrich_snapshots_parallel_runner_keeps_input_order():
    rows = [
        snapshot("https://example.test/first", "services", "2026-06-01"),
        snapshot("https://example.test/second", "services", "2026-07-01"),
    ]

    results, failures = ism_ai_enrichment.enrich_snapshots(
        rows,
        lambda row: row["source_url"],
        report_concurrency=2,
    )

    assert results == [row["source_url"] for row in rows]
    assert failures == []


def test_enrich_snapshots_parallel_runner_orders_failures_by_snapshot_input():
    rows = [
        snapshot("https://example.test/first", "services", "2026-06-01"),
        snapshot("https://example.test/second", "services", "2026-07-01"),
    ]

    def enrich_one(row):
        raise RuntimeError(f"failed {row['report_month']}")

    results, failures = ism_ai_enrichment.enrich_snapshots(
        rows,
        enrich_one,
        report_concurrency=2,
    )

    assert results == [None, None]
    assert failures == [
        {
            "survey_type": "services",
            "report_id": "ism_services_2026_06",
            "source_url": "https://example.test/first",
            "error": "failed 2026-06-01",
        },
        {
            "survey_type": "services",
            "report_id": "ism_services_2026_07",
            "source_url": "https://example.test/second",
            "error": "failed 2026-07-01",
        },
    ]

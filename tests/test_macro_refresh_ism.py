import pytest

from app.db import growth_cycle
from app.db import us_rates_liquidity
from app.services import macro_refresh_ism


def test_prepare_ism_reports_fetches_and_parses_without_opening_sqlite(monkeypatch):
    target = {
        "survey_type": "manufacturing",
        "report_month": "2026-07-01",
        "report_id": "ism_manufacturing_2026_07",
        "source_name": "ismworld",
        "url": "https://example.test/ism",
    }
    parsed = {
        "survey_type": "manufacturing",
        "report": {
            "report_id": "ism_manufacturing_2026_07",
            "report_month": "2026-07-01",
            "source_name": "ismworld",
            "source_url": target["url"],
        },
        "metrics": {},
    }
    monkeypatch.setattr(
        "app.tools.ism_report_config.load_survey_config",
        lambda _survey: {
            "parse_report": lambda *args: parsed,
            "report_id_prefix": "ism_manufacturing_",
            "allowed_metric_series": set(),
        },
    )

    prepared = macro_refresh_ism.prepare_ism_reports(
        [target], fetcher=lambda _url: "<html>fixture</html>"
    )

    assert prepared[0]["parsed"] == {**parsed, "at_a_glance_rows": []}
    assert prepared[0]["snapshot"]["raw_html"] == "<html>fixture</html>"


def test_enrichment_preparation_does_not_open_sqlite(monkeypatch):
    snapshot = {
        "survey_type": "services",
        "source_url": "https://example.test/ism",
        "source_name": "ismworld",
        "source_hash": "hash",
        "fetched_at": "2026-08-24T00:00:00Z",
        "report_id": "ism_services_2026_07",
        "report_month": "2026-07-01",
        "raw_html": "fixture",
    }
    monkeypatch.setattr("app.services.macro_refresh_ism._prepare_services", lambda *a: {"report_id": "ism_services_2026_07"})
    monkeypatch.setattr("app.services.macro_refresh_ism._run_services_extraction", lambda *a: ({"report_id": "ism_services_2026_07"}, {}))
    monkeypatch.setattr("app.db.us_rates_liquidity.connect", lambda *_: pytest.fail("writer opened during enrichment"))

    prepared = macro_refresh_ism.prepare_ism_enrichment(
        snapshot, client=object(), model="test-model", survey_type="services"
    )

    assert prepared["extraction"]["report_id"] == "ism_services_2026_07"


def test_ism_report_promotions_remain_per_report_atomic(monkeypatch, tmp_path):
    def prepared(month):
        report_id = f"ism_manufacturing_{month[:4]}_{month[5:7]}"
        target = {
            "survey_type": "manufacturing",
            "report_month": month,
            "report_id": report_id,
            "source_name": "ismworld",
            "url": f"https://example.test/{month}",
        }
        snapshot = {
            "source_url": target["url"],
            "source_name": "ismworld",
            "survey_type": "manufacturing",
            "source_hash": month,
            "fetched_at": "2026-08-24T00:00:00Z",
            "raw_html": "fixture",
            "parse_status": "prepared",
            "parse_error": None,
            "report_id": report_id,
            "report_month": month,
        }
        parsed = {
            "survey_type": "manufacturing",
            "report": {
                "report_id": report_id,
                "report_month": month,
                "source_name": "ismworld",
            },
            "metrics": {},
        }
        return {"target": target, "snapshot": snapshot, "parsed": parsed}

    calls = []

    def promote(_con, _survey, parsed):
        calls.append(parsed["report"]["report_month"])
        if len(calls) == 2:
            raise ValueError("second promotion failed")
        return {"report_id": parsed["report"]["report_id"]}

    monkeypatch.setattr(
        macro_refresh_ism.ism_report_ingestion,
        "persist_parsed_report",
        promote,
    )
    db_path = tmp_path / "ism.sqlite"
    with pytest.raises(ValueError, match="second promotion failed"):
        macro_refresh_ism.persist_ism_reports(
            db_path, [prepared("2026-06-01"), prepared("2026-07-01")]
        )

    con = us_rates_liquidity.connect(db_path)
    try:
        rows = [
            growth_cycle.load_ism_report_source_snapshot(
                con, f"https://example.test/{month}"
            )
            for month in ("2026-06-01", "2026-07-01")
        ]
    finally:
        con.close()
    statuses = {row["report_month"]: row["parse_status"] for row in rows}
    assert statuses == {"2026-06-01": "ok", "2026-07-01": "failed"}

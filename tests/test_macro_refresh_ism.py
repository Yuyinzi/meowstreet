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
    monkeypatch.setattr("app.services.macro_refresh_ism._run_services_extraction", lambda *a: ({"report": {"report_id": "ism_services_2026_07", "report_month": "2026-07-01"}}, {}))
    monkeypatch.setattr("app.db.us_rates_liquidity.connect", lambda *_: pytest.fail("writer opened during enrichment"))

    prepared = macro_refresh_ism.prepare_ism_enrichment(
        snapshot, client=object(), model="test-model", survey_type="services"
    )

    assert prepared["extraction"]["report"]["report_id"] == "ism_services_2026_07"
    assert prepared["status"] == "ok"


def test_services_enrichment_rejects_wrong_report_identity_without_writer(monkeypatch):
    snapshot = {
        "survey_type": "services",
        "source_url": "https://example.test/services",
        "source_name": "ismworld",
        "source_hash": "hash",
        "fetched_at": "2026-08-24T00:00:00Z",
        "report_id": "ism_services_2026_07",
        "report_month": "2026-07-01",
        "raw_html": "fixture",
    }
    monkeypatch.setattr(
        "app.services.macro_refresh_ism._prepare_services",
        lambda _snapshot: {"report_id": "ism_services_2026_07"},
    )
    monkeypatch.setattr(
        "app.services.macro_refresh_ism._run_services_extraction",
        lambda *_args: (
            {
                "report": {
                    "report_id": "ism_services_2026_06",
                    "report_month": "2026-06-01",
                }
            },
            {},
        ),
    )

    prepared = macro_refresh_ism.prepare_ism_enrichment(
        snapshot, client=object(), model="test-model", survey_type="services"
    )

    assert prepared["status"] == "failed"
    assert "report_id mismatch" in prepared["error"]
    assert prepared["snapshot"]["report_id"] == "ism_services_2026_07"


def test_services_enrichment_rejects_wrong_report_month(monkeypatch):
    snapshot = {
        "survey_type": "services",
        "source_url": "https://example.test/services",
        "source_name": "ismworld",
        "source_hash": "hash",
        "fetched_at": "2026-08-24T00:00:00Z",
        "report_id": "ism_services_2026_07",
        "report_month": "2026-07-01",
        "raw_html": "fixture",
    }
    monkeypatch.setattr(
        "app.services.macro_refresh_ism._prepare_services",
        lambda _snapshot: {"report_id": "ism_services_2026_07"},
    )
    monkeypatch.setattr(
        "app.services.macro_refresh_ism._run_services_extraction",
        lambda *_args: (
            {
                "report": {
                    "report_id": "ism_services_2026_07",
                    "report_month": "2026-06-01",
                }
            },
            {},
        ),
    )

    prepared = macro_refresh_ism.prepare_ism_enrichment(
        snapshot, client=object(), model="test-model", survey_type="services"
    )

    assert prepared["status"] == "failed"
    assert "report_month mismatch" in prepared["error"]


def test_prepare_ism_reports_retains_failed_targets_in_order(monkeypatch):
    targets = [
        {
            "survey_type": "manufacturing",
            "report_month": "2026-06-01",
            "report_id": "ism_manufacturing_2026_06",
            "source_name": "ismworld",
            "url": "https://example.test/one",
        },
        {
            "survey_type": "manufacturing",
            "report_month": "2026-07-01",
            "report_id": "ism_manufacturing_2026_07",
            "source_name": "ismworld",
            "url": "https://example.test/two",
        },
    ]
    parsed = {
        "survey_type": "manufacturing",
        "report": {
            "report_id": "ism_manufacturing_2026_06",
            "report_month": "2026-06-01",
        },
        "metrics": {},
    }
    monkeypatch.setattr(
        "app.tools.ism_report_config.load_survey_config",
        lambda _survey: {
            "parse_report": lambda *_args: parsed,
            "report_id_prefix": "ism_manufacturing_",
            "allowed_metric_series": set(),
        },
    )

    def fetch(url):
        if url.endswith("two"):
            raise ValueError("second source unavailable")
        return "first html"

    prepared = macro_refresh_ism.prepare_ism_reports(targets, fetcher=fetch)

    assert [item["target"]["url"] for item in prepared] == [
        "https://example.test/one",
        "https://example.test/two",
    ]
    assert prepared[1]["status"] == "failed"
    assert prepared[1]["report_id"] == "ism_manufacturing_2026_07"
    assert prepared[1]["error"] == "second source unavailable"


def test_failed_ism_preparation_is_promoted_as_failure(tmp_path):
    target = {
        "survey_type": "services",
        "report_month": "2026-07-01",
        "report_id": "ism_services_2026_07",
        "source_name": "ismworld",
        "url": "https://example.test/failure",
    }
    prepared = macro_refresh_ism.prepare_ism_reports(
        [target], fetcher=lambda _url: (_ for _ in ()).throw(ValueError("offline"))
    )

    results = macro_refresh_ism.persist_ism_reports(
        tmp_path / "ism.sqlite", prepared
    )

    assert results == [
        {
            "status": "failed",
            "source_url": target["url"],
            "report_id": target["report_id"],
            "report_month": target["report_month"],
            "error": "offline",
        }
    ]


def test_failed_enrichment_is_promoted_without_model_calls(tmp_path, monkeypatch):
    snapshot = {
        "source_url": "https://example.test/services",
        "source_name": "ismworld",
        "survey_type": "services",
        "source_hash": "hash",
        "fetched_at": "2026-08-24T00:00:00Z",
        "raw_html": "fixture",
        "parse_status": "ok",
        "parse_error": None,
        "report_id": "ism_services_2026_07",
        "report_month": "2026-07-01",
    }
    prepared = {
        "status": "failed",
        "survey_type": "services",
        "snapshot": snapshot,
        "source_url": snapshot["source_url"],
        "report_id": snapshot["report_id"],
        "report_month": snapshot["report_month"],
        "error": "model unavailable",
        "model": "test-model",
        "extraction": None,
    }
    monkeypatch.setattr(
        "app.db.ism_services_ai.promote_services_extraction",
        lambda *_args: pytest.fail("model promotion adapter should not run"),
    )

    result = macro_refresh_ism.persist_ism_enrichment(
        tmp_path / "ism.sqlite", prepared
    )

    assert result["status"] == "failed"
    con = us_rates_liquidity.connect(tmp_path / "ism.sqlite")
    try:
        saved = growth_cycle.load_ism_report_source_snapshot(
            con, snapshot["source_url"]
        )
    finally:
        con.close()
    assert saved["parse_status"] == "ok"
    assert saved["parse_error"] == "model unavailable"


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
    results = macro_refresh_ism.persist_ism_reports(
        db_path, [prepared("2026-06-01"), prepared("2026-07-01")]
    )

    assert [result["status"] for result in results] == ["ok", "failed"]
    assert results[1]["error"] == "second promotion failed"

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

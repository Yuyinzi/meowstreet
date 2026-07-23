from app.db import growth_cycle, us_rates_liquidity
from app.db.ism_services_ai import (
    promote_services_extraction,
)


def _connect(db_path):
    con = us_rates_liquidity.connect(db_path)
    growth_cycle.init_db(con)
    return con


SERVICES_COMPONENTS = sorted(
    [
        "ism_services_pmi",
        "ism_services_business_activity",
        "ism_services_new_orders",
        "ism_services_employment",
        "ism_services_supplier_deliveries",
        "ism_services_inventories",
        "ism_services_inventory_sentiment",
        "ism_services_prices",
        "ism_services_order_backlog",
        "ism_services_new_export_orders",
        "ism_services_imports",
    ]
)


def _valid_extraction():
    return {
        "report": {
            "report_id": "ism_services_2026_06",
            "report_month": "2026-06-01",
            "title": "June 2026 ISM Services PMI Report",
            "source_name": "ismworld",
            "source_url": "https://example.test/services/",
        },
        "at_a_glance_rows": [
            {
                "series_id": sid,
                "label": sid.replace("ism_services_", "").replace("_", " ").title(),
                "current_value": 50.0 + i * 0.5,
                "previous_value": 49.0 + i * 0.5,
                "point_change": 1.0,
                "direction": "Growing",
                "rate_of_change": "Faster",
                "trend_months": 1,
            }
            for i, sid in enumerate(SERVICES_COMPONENTS)
        ],
        "industry_signals": [
            {
                "signal_type": "overall_growth",
                "direction": "growth",
                "industry": "Construction",
                "rank": 1,
                "source_excerpt": "Construction reported growth in June.",
            },
        ],
        "respondent_comments": [
            {
                "industry": "Construction",
                "comment_text": "Pipeline remains healthy.",
            },
        ],
        "commodities": [
            {
                "commodity": "Construction Labor",
                "signal_type": "up_in_price",
                "months": 2,
            },
        ],
        "narrative_facts": {
            "consecutive_expansion_months": 6,
            "services_economy_gdp_share_percent": None,
            "broad_based_expansion_mentioned": True,
            "inflationary_pressure_mentioned": True,
        },
    }


def _valid_source():
    return {
        "source_url": "https://example.test/services/",
        "source_hash": "abc123",
        "model": "test-model",
        "updated_at": "2026-07-03T14:00:00Z",
    }


def test_promote_services_extraction_replaces_metrics(tmp_path):
    con = _connect(tmp_path / "macro.db")
    extraction = _valid_extraction()
    source = _valid_source()

    result = promote_services_extraction(con, extraction, source)

    assert result["report_id"] == "ism_services_2026_06"
    assert result["metrics"] == 4
    assert result["at_a_glance_rows"] == 11

    pmi_points = us_rates_liquidity.load_macro_indicator_points(con, "ism_services_pmi")
    assert len(pmi_points) == 1
    assert pmi_points[0]["value"] == 54.0


def test_promote_services_extraction_stores_all_11_at_a_glance_rows(tmp_path):
    con = _connect(tmp_path / "macro.db")
    result = promote_services_extraction(con, _valid_extraction(), _valid_source())

    rows = growth_cycle.load_ism_at_a_glance_rows(con, "ism_services_2026_06")
    assert len(rows) == 11


def test_promote_services_extraction_stores_report_snapshot(tmp_path):
    con = _connect(tmp_path / "macro.db")
    promote_services_extraction(con, _valid_extraction(), _valid_source())

    snapshot = growth_cycle.load_latest_ism_report_snapshot(con, "services")
    assert snapshot is not None
    assert snapshot["report_id"] == "ism_services_2026_06"


def test_promote_services_extraction_stores_comments(tmp_path):
    con = _connect(tmp_path / "macro.db")
    promote_services_extraction(con, _valid_extraction(), _valid_source())

    comments = growth_cycle.load_ism_report_comments(con, "ism_services_2026_06")
    assert len(comments) == 1
    assert comments[0]["industry"] == "Construction"


def test_promote_services_extraction_stores_industry_signals(tmp_path):
    con = _connect(tmp_path / "macro.db")
    promote_services_extraction(con, _valid_extraction(), _valid_source())

    signals = growth_cycle.load_ism_report_industry_signals(con, "ism_services_2026_06")
    assert len(signals) == 1
    assert signals[0]["signal_type"] == "overall_growth"


def test_promote_services_extraction_uses_grouped_declared_counts_for_coverage(
    tmp_path,
):
    con = _connect(tmp_path / "macro.db")
    extraction = _valid_extraction()
    extraction.pop("industry_signals")
    extraction["industry_signal_lists"] = [
        {
            "signal_type": "overall_growth",
            "direction": "growth",
            "declared_count": 1,
            "industries": ["Construction"],
            "evidence_text": (
                "The one service industry reporting growth is: Construction."
            ),
        },
        {
            "signal_type": "prices",
            "direction": "decrease",
            "declared_count": 0,
            "industries": [],
            "evidence_text": "No industries reported a decrease in prices paid.",
        },
    ]

    result = promote_services_extraction(con, extraction, _valid_source())

    rows = con.execute(
        "select signal_type, direction, list_present, declared_count, "
        "extracted_count, validation_status "
        "from ism_report_industry_signal_coverage where report_id = ? "
        "order by signal_type, direction",
        ("ism_services_2026_06",),
    ).fetchall()
    assert len(rows) == 12
    growth = next(row for row in rows if row["signal_type"] == "overall_growth")
    assert tuple(growth) == ("overall_growth", "growth", 1, 1, 1, "complete")
    prices = next(row for row in rows if row["signal_type"] == "prices")
    assert tuple(prices) == ("prices", "decrease", 1, 0, 0, "complete")
    assert result["signal_coverage"] == 12


def test_promote_services_extraction_stores_commodities(tmp_path):
    con = _connect(tmp_path / "macro.db")
    promote_services_extraction(con, _valid_extraction(), _valid_source())

    rows = con.execute(
        "select * from ism_report_commodities where report_id = ?",
        ("ism_services_2026_06",),
    ).fetchall()
    assert len(rows) >= 1
    assert rows[0]["commodity"] == "Construction Labor"

def test_promote_services_extraction_collapses_exact_duplicate_commodities(tmp_path):
    con = _connect(tmp_path / "macro.db")
    extraction = _valid_extraction()
    extraction["commodities"] = [
        {
            "commodity": "Plastic Pipe Fittings",
            "signal_type": "short_supply",
            "months": None,
        },
        {
            "commodity": "Plastic Pipe Fittings",
            "signal_type": "short_supply",
            "months": None,
        },
    ]

    result = promote_services_extraction(con, extraction, _valid_source())

    rows = con.execute(
        "select commodity, signal_type, months from ism_report_commodities "
        "where report_id = ?",
        ("ism_services_2026_06",),
    ).fetchall()
    assert [dict(row) for row in rows] == [
        {
            "commodity": "Plastic Pipe Fittings",
            "signal_type": "short_supply",
            "months": None,
        }
    ]
    assert result["commodities"] == 1


def test_promote_services_extraction_stores_narrative_facts(tmp_path):
    con = _connect(tmp_path / "macro.db")
    promote_services_extraction(con, _valid_extraction(), _valid_source())

    rows = con.execute(
        "select * from ism_report_narrative_facts where report_id = ?",
        ("ism_services_2026_06",),
    ).fetchall()
    assert len(rows) == 1


def test_promote_services_extraction_replaces_previous_month(tmp_path):
    con = _connect(tmp_path / "macro.db")
    result1 = promote_services_extraction(con, _valid_extraction(), _valid_source())

    modified = _valid_extraction()
    pmi_idx = SERVICES_COMPONENTS.index("ism_services_pmi")
    modified["at_a_glance_rows"][pmi_idx]["current_value"] = 55.0
    result2 = promote_services_extraction(con, modified, _valid_source())

    assert result2["report_id"] == "ism_services_2026_06"
    pmi_points = us_rates_liquidity.load_macro_indicator_points(con, "ism_services_pmi")
    assert len(pmi_points) == 1
    assert pmi_points[0]["value"] == 55.0


def test_validation_error_before_promotion_leaves_old_data(tmp_path):
    con = _connect(tmp_path / "macro.db")
    promote_services_extraction(con, _valid_extraction(), _valid_source())

    invalid = _valid_extraction()
    invalid["at_a_glance_rows"] = invalid["at_a_glance_rows"][:3]
    try:
        promote_services_extraction(con, invalid, _valid_source())
    except ValueError:
        pass

    rows = growth_cycle.load_ism_at_a_glance_rows(con, "ism_services_2026_06")
    assert len(rows) == 11


def test_manufacturing_report_id_rejected(tmp_path):
    con = _connect(tmp_path / "macro.db")
    extraction = _valid_extraction()
    extraction["report"]["report_id"] = "ism_manufacturing_2026_06"
    import pytest

    with pytest.raises(ValueError, match="report_id must start with ism_services_"):
        promote_services_extraction(con, extraction, _valid_source())


def test_workbook_precedence_official_replaces_workbook(tmp_path):
    con = _connect(tmp_path / "macro.db")

    workbook_series = {
        "series_id": "ism_services_pmi",
        "title": "Services PMI",
        "units": "index",
        "source": "ISM workbook",
    }
    workbook_points = [
        {"date": "2026-06-01", "value": 49.0, "source": "ISM workbook"},
    ]
    us_rates_liquidity.merge_macro_indicator_points(
        con, workbook_series, workbook_points
    )

    promote_services_extraction(con, _valid_extraction(), _valid_source())

    pmi_points = us_rates_liquidity.load_macro_indicator_points(con, "ism_services_pmi")
    assert pmi_points[-1]["value"] == 54.0
    assert pmi_points[-1]["source"] == "ISM AI extraction"


def test_failed_extraction_leaves_workbook_unchanged(tmp_path):
    con = _connect(tmp_path / "macro.db")

    workbook_series = {
        "series_id": "ism_services_pmi",
        "title": "Services PMI",
        "units": "index",
        "source": "ISM workbook",
    }
    workbook_points = [
        {"date": "2026-06-01", "value": 49.0, "source": "ISM workbook"},
    ]
    us_rates_liquidity.merge_macro_indicator_points(
        con, workbook_series, workbook_points
    )

    invalid = _valid_extraction()
    invalid["at_a_glance_rows"] = invalid["at_a_glance_rows"][:3]
    try:
        promote_services_extraction(con, invalid, _valid_source())
    except ValueError:
        pass

    pmi_points = us_rates_liquidity.load_macro_indicator_points(con, "ism_services_pmi")
    assert pmi_points[-1]["value"] == 49.0
    assert pmi_points[-1]["source"] == "ISM workbook"

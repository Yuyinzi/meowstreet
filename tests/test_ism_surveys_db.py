import sqlite3

from app.db import ism_surveys


def test_rankings_are_isolated_by_survey_type():
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    ism_surveys.init_db(con)
    base = {
        "date": "2026-06-01",
        "industry": "Construction",
        "direction": "growth",
        "rank": 1,
        "source": "source.xlsx",
    }

    ism_surveys.replace_industry_rankings(con, "manufacturing", [base])
    ism_surveys.replace_industry_rankings(
        con, "services", [{**base, "direction": "contraction", "rank": -1}]
    )

    assert (
        ism_surveys.load_industry_rankings(con, "manufacturing")[0]["direction"]
        == "growth"
    )
    assert (
        ism_surveys.load_industry_rankings(con, "services")[0]["direction"]
        == "contraction"
    )


def test_load_industry_rankings_max_date_filters_future_rankings():
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    ism_surveys.init_db(con)
    base = {
        "direction": "growth",
        "rank": 1,
        "source": "source.xlsx",
    }
    rows = [
        {"date": f"2026-{m:02d}-01", "industry": "Construction", **base}
        for m in range(1, 13)
    ]
    ism_surveys.replace_industry_rankings(con, "services", rows)

    result = ism_surveys.load_industry_rankings(
        con, "services", limit_months=6, max_date="2026-06-01"
    )

    dates = {r["date"] for r in result}
    assert dates == {f"2026-{m:02d}-01" for m in range(1, 7)}


def test_load_industry_rankings_max_date_returns_empty_for_before_all():
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    ism_surveys.init_db(con)
    base = {
        "date": "2026-06-01",
        "industry": "Construction",
        "direction": "growth",
        "rank": 1,
        "source": "source.xlsx",
    }
    ism_surveys.replace_industry_rankings(con, "services", [base])

    result = ism_surveys.load_industry_rankings(
        con, "services", limit_months=6, max_date="2025-01-01"
    )
    assert result == []


def test_legacy_rankings_migrate_to_manufacturing():
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.execute(
        "create table ism_industry_rankings(date text, industry text, direction text, rank integer, source text, primary key(date, industry))"
    )
    con.execute(
        "insert into ism_industry_rankings values ('2026-05-01', 'Machinery', 'growth', 1, 'legacy.xlsx')"
    )

    ism_surveys.init_db(con)

    rows = ism_surveys.load_industry_rankings(con, "manufacturing")
    assert rows[0]["industry"] == "Machinery"

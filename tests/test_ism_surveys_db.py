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

from datetime import UTC, datetime, timedelta

import pytest

from app.db import ticker_context


def industry_tags():
    return [
        {
            "industry": "Semiconductors & Semi Conductor Equipment",
            "sector": "Information Technology",
            "industry_group": "Semiconductors & Semi Conductor Equipment",
            "official_industry": "Semiconductors & Semiconductor Equipment",
            "cycle_tag": "cyclical",
            "tag_source": "method_workbook",
            "source_vintage": "2021-gics",
        },
        {
            "industry": "Electric Utilities",
            "sector": "Utilities",
            "industry_group": "Utilities",
            "official_industry": "Electric Utilities",
            "cycle_tag": "defensive",
            "tag_source": "method_workbook",
            "source_vintage": "2021-gics",
        },
        {
            "industry": "Beverages",
            "sector": "Consumer Staples",
            "industry_group": "Food, Beverage & Tobacco",
            "official_industry": "Beverages",
            "cycle_tag": "both",
            "tag_source": "method_workbook",
            "source_vintage": "2021-gics",
        },
    ]


def industry_row(industry):
    return {
        "industry": industry,
        "sector": "Communication Services",
        "industry_group": "Media & Entertainment",
        "official_industry": industry,
        "cycle_tag": "cyclical",
        "tag_source": "method_workbook",
        "source_vintage": "2021-gics",
    }


def alias_row(source_industry, gics_industry):
    return {
        "source": "yahoo",
        "source_industry": source_industry,
        "gics_industry": gics_industry,
    }


def test_save_and_load_ticker_profile(tmp_path):
    con = ticker_context.connect(tmp_path / "ticker_context.sqlite")

    ticker_context.save_ticker_profile(
        con,
        {
            "symbol": " nvda ",
            "company_name": "NVIDIA Corporation",
            "provider": "yahoo",
            "provider_sector": "Technology",
            "provider_industry": "Semiconductors",
        },
    )

    profile = ticker_context.load_ticker_profile(con, "NVDA")
    assert profile["symbol"] == "NVDA"
    assert profile["company_name"] == "NVIDIA Corporation"
    assert profile["provider"] == "yahoo"
    assert profile["provider_industry"] == "Semiconductors"
    assert profile["fetched_at"]


def test_load_ticker_profile_returns_none_for_unknown_symbol(tmp_path):
    con = ticker_context.connect(tmp_path / "ticker_context.sqlite")

    assert ticker_context.load_ticker_profile(con, "NVDA") is None


def test_save_ticker_profile_requires_company_name(tmp_path):
    con = ticker_context.connect(tmp_path / "ticker_context.sqlite")

    with pytest.raises(ValueError, match="company name is required for NVDA"):
        ticker_context.save_ticker_profile(
            con, {"symbol": "NVDA", "provider": "yahoo"}
        )


def test_save_and_load_industry_tags(tmp_path):
    con = ticker_context.connect(tmp_path / "ticker_context.sqlite")

    saved = ticker_context.save_industry_tags(con, industry_tags())

    assert saved == 3
    tag = ticker_context.load_industry_tag(con, "Beverages")
    assert tag["cycle_tag"] == "both"
    assert tag["sector"] == "Consumer Staples"
    all_tags = ticker_context.load_industry_tags(con)
    assert [row["industry"] for row in all_tags] == [
        "Beverages",
        "Semiconductors & Semi Conductor Equipment",
        "Electric Utilities",
    ]


def test_save_industry_tags_replaces_existing_row(tmp_path):
    con = ticker_context.connect(tmp_path / "ticker_context.sqlite")
    ticker_context.save_industry_tags(con, industry_tags())

    replacement = dict(industry_tags()[0], cycle_tag="defensive")
    ticker_context.save_industry_tags(con, [replacement])

    tag = ticker_context.load_industry_tag(
        con, "Semiconductors & Semi Conductor Equipment"
    )
    assert tag["cycle_tag"] == "defensive"


def test_save_industry_tags_rejects_invalid_cycle_tag(tmp_path):
    con = ticker_context.connect(tmp_path / "ticker_context.sqlite")

    with pytest.raises(ValueError, match="cycle tag neutral is invalid"):
        ticker_context.save_industry_tags(
            con, [dict(industry_tags()[0], cycle_tag="neutral")]
        )


def test_save_and_load_industry_aliases(tmp_path):
    con = ticker_context.connect(tmp_path / "ticker_context.sqlite")

    saved = ticker_context.save_industry_aliases(
        con,
        [
            {
                "source": "yahoo",
                "source_industry": "Semiconductors",
                "gics_industry": "Semiconductors & Semi Conductor Equipment",
            }
        ],
    )

    assert saved == 1
    alias = ticker_context.load_industry_alias(con, "yahoo", "Semiconductors")
    assert alias["gics_industry"] == "Semiconductors & Semi Conductor Equipment"
    assert ticker_context.load_industry_alias(con, "yahoo", "Unknown") is None


def test_replace_industry_reference_data_is_atomic(tmp_path):
    con = ticker_context.connect(tmp_path / "market_data.sqlite")
    ticker_context.replace_industry_reference_data(
        con,
        [industry_row("Media")],
        [alias_row("Advertising Agencies", "Media")],
    )

    with pytest.raises(ValueError, match="alias industry Missing is unknown"):
        ticker_context.replace_industry_reference_data(
            con,
            [industry_row("Media")],
            [alias_row("Advertising Agencies", "Missing")],
        )

    assert ticker_context.load_industry_tags(con) == [industry_row("Media")]
    assert ticker_context.load_industry_alias(
        con, "yahoo", "Advertising Agencies"
    )["gics_industry"] == "Media"


def _consensus(symbol="NVDA", fiscal_year_end="2026-12-31", avg=1.5, captured_at=None):
    return {
        "symbol": symbol,
        "fiscal_year_end": fiscal_year_end,
        "avg": avg,
        "low": 1.0,
        "high": 2.0,
        "analyst_count": 25,
        "captured_at": captured_at or "2026-08-28T12:00:00+00:00",
    }


def test_save_estimate_consensus_snapshot_accumulates_only_on_change(tmp_path):
    con = ticker_context.connect(tmp_path / "market_data.sqlite")

    ticker_context.save_estimate_consensus_snapshot(con, "NVDA", _consensus(avg=1.5))
    ticker_context.save_estimate_consensus_snapshot(con, "NVDA", _consensus(avg=1.5))

    rows = con.execute(
        "select count(*) as n from estimate_consensus_snapshots where symbol = ?",
        ("NVDA",),
    ).fetchone()
    assert rows["n"] == 1

    ticker_context.save_estimate_consensus_snapshot(con, "NVDA", _consensus(avg=1.6))

    rows = con.execute(
        "select count(*) as n from estimate_consensus_snapshots where symbol = ?",
        ("NVDA",),
    ).fetchone()
    assert rows["n"] == 2


def test_load_latest_estimate_consensus_returns_latest_row(tmp_path):
    con = ticker_context.connect(tmp_path / "market_data.sqlite")

    ticker_context.save_estimate_consensus_snapshot(con, "NVDA", _consensus(avg=1.5, captured_at="2026-08-26T12:00:00+00:00"))
    ticker_context.save_estimate_consensus_snapshot(con, "NVDA", _consensus(avg=1.6, captured_at="2026-08-28T12:00:00+00:00"))

    latest = ticker_context.load_latest_estimate_consensus(con, "NVDA")

    assert latest["avg"] == pytest.approx(1.6)


def test_load_estimate_consensus_history_filters_by_since(tmp_path):
    con = ticker_context.connect(tmp_path / "market_data.sqlite")

    ticker_context.save_estimate_consensus_snapshot(con, "NVDA", _consensus(avg=1.3, captured_at="2026-07-01T12:00:00+00:00"))
    ticker_context.save_estimate_consensus_snapshot(con, "NVDA", _consensus(avg=1.4, captured_at="2026-08-27T12:00:00+00:00"))
    ticker_context.save_estimate_consensus_snapshot(con, "NVDA", _consensus(avg=1.5, captured_at="2026-08-28T12:00:00+00:00"))

    history = ticker_context.load_estimate_consensus_history(con, "NVDA", "2026-08-26T12:00:00+00:00")

    assert len(history) == 2
    assert history[0]["captured_at"] == "2026-08-27T12:00:00+00:00"


def test_estimate_consensus_fresh_honors_max_age(tmp_path):
    con = ticker_context.connect(tmp_path / "market_data.sqlite")
    stale = {
        "symbol": "NVDA",
        "fiscal_year_end": "2026-12-31",
        "avg": 1.5,
        "low": 1.0,
        "high": 2.0,
        "analyst_count": 25,
        "captured_at": (datetime.now(UTC) - timedelta(seconds=80000)).isoformat(),
    }

    assert ticker_context.estimate_consensus_fresh(stale, max_age_seconds=72000) is False
    assert ticker_context.estimate_consensus_fresh(stale, max_age_seconds=90000) is True


def test_estimate_consensus_fresh_treats_none_as_stale():
    assert ticker_context.estimate_consensus_fresh(None) is False

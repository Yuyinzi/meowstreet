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

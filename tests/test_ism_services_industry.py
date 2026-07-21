import pytest

from app.tools import ism_services_industry


def test_canonical_industries_contains_18_entries():
    assert len(ism_services_industry.CANONICAL_INDUSTRIES) == 18


def test_normalize_industry_accepts_exact_canonical_name():
    result = ism_services_industry.normalize_industry("Construction")
    assert result == "Construction"


def test_normalize_industry_rejects_manufacturing_name():
    with pytest.raises(ValueError, match="unknown services industry: Machinery"):
        ism_services_industry.normalize_industry("Machinery")


def test_normalize_industry_rejects_empty_string():
    with pytest.raises(ValueError, match="industry name is required"):
        ism_services_industry.normalize_industry("")


def test_normalize_industry_rejects_none():
    with pytest.raises(ValueError, match="industry name is required"):
        ism_services_industry.normalize_industry(None)


def test_normalize_industry_normalizes_whitespace():
    result = ism_services_industry.normalize_industry("  Construction  ")
    assert result == "Construction"


def test_normalize_industry_handles_all_18_canonical_names():
    for name in ism_services_industry.CANONICAL_INDUSTRIES:
        result = ism_services_industry.normalize_industry(name)
        assert result == name


def test_normalize_industry_rejects_random_string():
    with pytest.raises(ValueError, match="unknown services industry"):
        ism_services_industry.normalize_industry("NonExistent")


def test_build_industry_payload_tracks_direction_and_rank_change():
    rankings = [
        {
            "date": "2026-05-01",
            "industry": "Construction",
            "direction": "contraction",
            "rank": -2,
            "source": "test",
        },
        {
            "date": "2026-06-01",
            "industry": "Construction",
            "direction": "growth",
            "rank": 12,
            "source": "test",
        },
    ]

    result = ism_services_industry.build_industry_payload(rankings, [])
    construction = result["industries"][0]

    assert construction["direction_change"] == "contraction_to_growth"
    assert construction["rank_change"] == 14
    assert construction["positive_streak"] == 1


def test_build_industry_payload_groups_by_industry():
    rankings = [
        {
            "date": "2026-06-01",
            "industry": "Construction",
            "direction": "growth",
            "rank": 5,
            "source": "test",
        },
        {
            "date": "2026-06-01",
            "industry": "Retail Trade",
            "direction": "contraction",
            "rank": -3,
            "source": "test",
        },
    ]

    result = ism_services_industry.build_industry_payload(rankings, [])
    industries = {ind["industry"]: ind for ind in result["industries"]}

    assert "Construction" in industries
    assert "Retail Trade" in industries


def test_build_industry_payload_single_entry_no_change():
    rankings = [
        {
            "date": "2026-06-01",
            "industry": "Construction",
            "direction": "growth",
            "rank": 3,
            "source": "test",
        },
    ]

    result = ism_services_industry.build_industry_payload(rankings, [])
    construction = result["industries"][0]

    assert construction["direction_change"] is None
    assert construction["rank_change"] is None
    assert construction["positive_streak"] == 1
    assert construction["negative_streak"] == 0


def test_build_industry_payload_negative_streak():
    rankings = [
        {
            "date": "2026-05-01",
            "industry": "Construction",
            "direction": "contraction",
            "rank": -1,
            "source": "test",
        },
        {
            "date": "2026-06-01",
            "industry": "Construction",
            "direction": "contraction",
            "rank": -5,
            "source": "test",
        },
    ]

    result = ism_services_industry.build_industry_payload(rankings, [])
    construction = result["industries"][0]

    assert construction["direction_change"] is None
    assert construction["rank_change"] == -4
    assert construction["positive_streak"] == 0
    assert construction["negative_streak"] == 2


def test_build_industry_payload_streak_counted_from_latest():
    rankings = [
        {
            "date": "2026-04-01",
            "industry": "Construction",
            "direction": "contraction",
            "rank": -2,
            "source": "test",
        },
        {
            "date": "2026-05-01",
            "industry": "Construction",
            "direction": "growth",
            "rank": 5,
            "source": "test",
        },
        {
            "date": "2026-06-01",
            "industry": "Construction",
            "direction": "growth",
            "rank": 12,
            "source": "test",
        },
    ]

    result = ism_services_industry.build_industry_payload(rankings, [])
    construction = result["industries"][0]

    assert construction["direction_change"] == "contraction_to_growth"
    assert construction["rank_change"] == 7
    assert construction["positive_streak"] == 2


def test_build_industry_payload_matched_comments():
    rankings = [
        {
            "date": "2026-06-01",
            "industry": "Construction",
            "direction": "growth",
            "rank": 3,
            "source": "test",
        },
    ]
    comments = [
        {"industry": "Construction", "comment_text": "Strong housing demand"},
        {"industry": "Retail Trade", "comment_text": "Consumer spending slowing"},
    ]

    result = ism_services_industry.build_industry_payload(rankings, comments)
    construction = result["industries"][0]

    assert construction["comments"] == ["Strong housing demand"]


def test_build_industry_payload_normalizes_industry_in_rankings():
    rankings = [
        {
            "date": "2026-06-01",
            "industry": "  Construction  ",
            "direction": "growth",
            "rank": 3,
            "source": "test",
        },
    ]

    result = ism_services_industry.build_industry_payload(rankings, [])
    assert result["industries"][0]["industry"] == "Construction"


def test_build_industry_payload_skips_unknown_industry():
    rankings = [
        {
            "date": "2026-06-01",
            "industry": "Machinery",
            "direction": "growth",
            "rank": 3,
            "source": "test",
        },
        {
            "date": "2026-06-01",
            "industry": "Construction",
            "direction": "growth",
            "rank": 5,
            "source": "test",
        },
    ]

    result = ism_services_industry.build_industry_payload(rankings, [])
    industries = {ind["industry"] for ind in result["industries"]}

    assert "Construction" in industries
    assert "Machinery" not in industries


def test_build_breadth_returns_counts_and_status():
    rankings = [
        {
            "date": "2026-06-01",
            "industry": "Construction",
            "direction": "growth",
            "rank": 5,
            "source": "test",
        },
        {
            "date": "2026-06-01",
            "industry": "Retail Trade",
            "direction": "growth",
            "rank": 3,
            "source": "test",
        },
        {
            "date": "2026-06-01",
            "industry": "Mining",
            "direction": "contraction",
            "rank": -2,
            "source": "test",
        },
    ]

    result = ism_services_industry.build_breadth(rankings)

    assert result["growth_count"] == 2
    assert result["contraction_count"] == 1
    assert result["neutral_count"] == 0
    assert result["total_count"] == 3
    assert result["status"] == "supportive"


def test_build_breadth_warning_when_more_contraction():
    rankings = [
        {
            "date": "2026-06-01",
            "industry": "Construction",
            "direction": "contraction",
            "rank": -5,
            "source": "test",
        },
        {
            "date": "2026-06-01",
            "industry": "Retail Trade",
            "direction": "contraction",
            "rank": -3,
            "source": "test",
        },
        {
            "date": "2026-06-01",
            "industry": "Mining",
            "direction": "growth",
            "rank": 2,
            "source": "test",
        },
    ]

    result = ism_services_industry.build_breadth(rankings)

    assert result["growth_count"] == 1
    assert result["contraction_count"] == 2
    assert result["status"] == "warning"


def test_build_breadth_mixed_when_equal():
    rankings = [
        {
            "date": "2026-06-01",
            "industry": "Construction",
            "direction": "growth",
            "rank": 5,
            "source": "test",
        },
        {
            "date": "2026-06-01",
            "industry": "Retail Trade",
            "direction": "contraction",
            "rank": -3,
            "source": "test",
        },
    ]

    result = ism_services_industry.build_breadth(rankings)

    assert result["growth_count"] == 1
    assert result["contraction_count"] == 1
    assert result["neutral_count"] == 0
    assert result["status"] == "mixed"


def test_build_breadth_uses_latest_month_only():
    rankings = [
        {
            "date": "2026-05-01",
            "industry": "Construction",
            "direction": "growth",
            "rank": 10,
            "source": "test",
        },
        {
            "date": "2026-06-01",
            "industry": "Construction",
            "direction": "contraction",
            "rank": -5,
            "source": "test",
        },
        {
            "date": "2026-06-01",
            "industry": "Retail Trade",
            "direction": "growth",
            "rank": 3,
            "source": "test",
        },
    ]

    result = ism_services_industry.build_breadth(rankings)

    assert result["growth_count"] == 1
    assert result["contraction_count"] == 1


def test_build_breadth_empty_rankings():
    result = ism_services_industry.build_breadth([])

    assert result["growth_count"] == 0
    assert result["contraction_count"] == 0
    assert result["neutral_count"] == 0
    assert result["total_count"] == 0
    assert result["status"] is None


def test_build_industry_payload_sorts_industries_by_name():
    rankings = [
        {
            "date": "2026-06-01",
            "industry": "Mining",
            "direction": "growth",
            "rank": 1,
            "source": "test",
        },
        {
            "date": "2026-06-01",
            "industry": "Construction",
            "direction": "growth",
            "rank": 2,
            "source": "test",
        },
    ]

    result = ism_services_industry.build_industry_payload(rankings, [])
    assert result["industries"][0]["industry"] == "Construction"
    assert result["industries"][1]["industry"] == "Mining"


def test_build_breadth_all_growth():
    rankings = [
        {
            "date": "2026-06-01",
            "industry": "Construction",
            "direction": "growth",
            "rank": 5,
            "source": "test",
        },
        {
            "date": "2026-06-01",
            "industry": "Mining",
            "direction": "growth",
            "rank": 3,
            "source": "test",
        },
    ]
    result = ism_services_industry.build_breadth(rankings)
    assert result["status"] == "supportive"


def test_build_breadth_all_contraction():
    rankings = [
        {
            "date": "2026-06-01",
            "industry": "Construction",
            "direction": "contraction",
            "rank": -5,
            "source": "test",
        },
        {
            "date": "2026-06-01",
            "industry": "Mining",
            "direction": "contraction",
            "rank": -3,
            "source": "test",
        },
    ]
    result = ism_services_industry.build_breadth(rankings)
    assert result["status"] == "warning"


def test_build_breadth_skips_unknown_industry():
    rankings = [
        {
            "date": "2026-06-01",
            "industry": "Machinery",
            "direction": "growth",
            "rank": 5,
            "source": "test",
        },
        {
            "date": "2026-06-01",
            "industry": "Construction",
            "direction": "growth",
            "rank": 3,
            "source": "test",
        },
    ]
    result = ism_services_industry.build_breadth(rankings)
    assert result["total_count"] == 1
    assert result["growth_count"] == 1


def test_build_industry_payload_rankings_normalized_before_grouping():
    rankings = [
        {
            "date": "2026-06-01",
            "industry": "  Construction  ",
            "direction": "growth",
            "rank": 5,
            "source": "test",
        },
        {
            "date": "2026-05-01",
            "industry": "Construction",
            "direction": "contraction",
            "rank": -2,
            "source": "test",
        },
    ]
    result = ism_services_industry.build_industry_payload(rankings, [])
    assert len(result["industries"]) == 1
    assert result["industries"][0]["direction_change"] == "contraction_to_growth"

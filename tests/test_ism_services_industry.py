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

    assert construction["direction_change"] is None
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


def test_build_services_industry_analysis_groups_rank_history_and_components():
    rankings = [
        {
            "date": "2026-04-01",
            "industry": "Construction",
            "direction": "contraction",
            "rank": 2,
        },
        {
            "date": "2026-05-01",
            "industry": "Construction",
            "direction": "growth",
            "rank": 4,
        },
        {
            "date": "2026-06-01",
            "industry": "Construction",
            "direction": "growth",
            "rank": 1,
        },
        {
            "date": "2026-06-01",
            "industry": "Educational Services",
            "direction": "contraction",
            "rank": 1,
        },
    ]
    component_signals = [
        {
            "signal_type": "business_activity",
            "direction": "growth",
            "industry": "Construction",
            "rank": 3,
        },
        {
            "signal_type": "supplier_deliveries",
            "direction": "slower",
            "industry": "Construction",
            "rank": 5,
        },
        {
            "signal_type": "backlog",
            "direction": "lower",
            "industry": "Educational Services",
            "rank": 2,
        },
    ]
    coverage_rows = [
        {
            "signal_type": "business_activity",
            "direction": "growth",
            "list_present": True,
            "declared_count": 13,
            "extracted_count": 13,
            "validation_status": "complete",
        },
        {
            "signal_type": "supplier_deliveries",
            "direction": "slower",
            "list_present": True,
            "declared_count": 14,
            "extracted_count": 14,
            "validation_status": "complete",
        },
        {
            "signal_type": "backlog",
            "direction": "lower",
            "list_present": True,
            "declared_count": 7,
            "extracted_count": 7,
            "validation_status": "complete",
        },
    ]
    comments = [
        {"industry": "Construction", "comment_text": "Construction comment."},
        {"industry": "Educational Services", "comment_text": "Education comment."},
    ]

    result = ism_services_industry.build_services_industry_analysis(
        rankings,
        component_signals,
        coverage_rows,
        comments,
        period="2026-06-01",
        source_url="https://www.ismworld.org/services/june/",
    )

    assert result["status"] == "available"
    assert result["period"] == "2026-06-01"
    assert result["growing_industries"] == [{"industry": "Construction", "rank": 1}]
    assert result["contracting_industries"] == [
        {"industry": "Educational Services", "rank": 1}
    ]
    construction = next(
        row for row in result["industries"] if row["industry"] == "Construction"
    )
    assert construction["direction"] == "growth"
    assert construction["rank"] == 1
    assert construction["direction_change"] is None
    assert construction["rank_change"] == -3
    assert construction["streak"] == {"direction": "growth", "months": 2}
    assert construction["trend"] == [
        {"period": "2026-04-01", "direction": "contraction", "rank": 2},
        {"period": "2026-05-01", "direction": "growth", "rank": 4},
        {"period": "2026-06-01", "direction": "growth", "rank": 1},
    ]
    assert construction["component_signals"] == [
        {
            "signal_type": "business_activity",
            "label": "Business Activity",
            "direction": "growth",
            "direction_label": "Growth",
            "rank": 3,
            "list_size": 13,
        },
        {
            "signal_type": "supplier_deliveries",
            "label": "Supplier Deliveries",
            "direction": "slower",
            "direction_label": "Slower",
            "rank": 5,
            "list_size": 14,
        },
    ]
    assert construction["component_coverage"] == {
        "listed_components": 2,
        "available_components": 3,
        "coverage_status": "available",
    }
    assert construction["comments"] == ["Construction comment."]
    assert "score" not in construction
    assert "score_weights" not in result


def test_services_industry_analysis_does_not_compare_ranks_across_directions():
    result = ism_services_industry.build_services_industry_analysis(
        [
            {
                "date": "2026-05-01",
                "industry": "Construction",
                "direction": "contraction",
                "rank": 2,
            },
            {
                "date": "2026-06-01",
                "industry": "Construction",
                "direction": "growth",
                "rank": 12,
            },
        ],
        [],
        [],
        [],
        period="2026-06-01",
        source_url="https://example.com",
    )

    industry = result["industries"][0]
    assert industry["direction_change"] == "contraction_to_growth"
    assert industry["rank_change"] is None


def test_services_industry_analysis_does_not_forward_fill_missing_months():
    result = ism_services_industry.build_services_industry_analysis(
        [
            {
                "date": "2026-04-01",
                "industry": "Construction",
                "direction": "growth",
                "rank": 2,
            },
            {
                "date": "2026-06-01",
                "industry": "Construction",
                "direction": "growth",
                "rank": 1,
            },
        ],
        [],
        [],
        [],
        period="2026-06-01",
        source_url="https://example.com",
    )

    assert [row["period"] for row in result["industries"][0]["trend"]] == [
        "2026-04-01",
        "2026-06-01",
    ]
    assert result["industries"][0]["streak"] == {
        "direction": "growth",
        "months": 1,
    }


def test_services_industry_analysis_is_unavailable_without_current_rankings():
    result = ism_services_industry.build_services_industry_analysis(
        [], [], [], [], period="2026-06-01", source_url=None
    )

    assert result["status"] == "unavailable"
    assert result["industries"] == []
    assert "2026-06-01" in result["reason"]


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


def test_services_industry_analysis_excludes_rankings_older_than_six_months():
    rankings = [
        {
            "date": "2020-08-01",
            "industry": "Construction",
            "direction": "growth",
            "rank": 1,
        },
        {
            "date": "2020-09-01",
            "industry": "Construction",
            "direction": "growth",
            "rank": 2,
        },
        {
            "date": "2020-10-01",
            "industry": "Construction",
            "direction": "growth",
            "rank": 3,
        },
        {
            "date": "2020-11-01",
            "industry": "Construction",
            "direction": "growth",
            "rank": 4,
        },
        {
            "date": "2020-12-01",
            "industry": "Construction",
            "direction": "growth",
            "rank": 5,
        },
        {
            "date": "2026-05-01",
            "industry": "Construction",
            "direction": "contraction",
            "rank": 10,
        },
        {
            "date": "2026-06-01",
            "industry": "Construction",
            "direction": "contraction",
            "rank": 8,
        },
    ]
    result = ism_services_industry.build_services_industry_analysis(
        rankings,
        [],
        [],
        [],
        period="2026-06-01",
        source_url="https://example.com",
    )
    industry = result["industries"][0]
    assert [row["period"] for row in industry["trend"]] == [
        "2026-05-01",
        "2026-06-01",
    ]
    assert industry["rank_change"] == -2
    assert industry["direction_change"] is None


def test_services_industry_analysis_coverage_is_unavailable_when_no_coverage_rows():
    result = ism_services_industry.build_services_industry_analysis(
        [
            {
                "date": "2026-06-01",
                "industry": "Construction",
                "direction": "growth",
                "rank": 1,
            },
        ],
        [],
        [],
        [],
        period="2026-06-01",
        source_url="https://example.com",
    )
    industry = result["industries"][0]
    assert industry["component_coverage"] == {
        "listed_components": 0,
        "available_components": None,
        "coverage_status": "unavailable",
    }


def test_services_industry_analysis_coverage_is_unavailable_when_only_partial():
    result = ism_services_industry.build_services_industry_analysis(
        [
            {
                "date": "2026-06-01",
                "industry": "Construction",
                "direction": "growth",
                "rank": 1,
            },
        ],
        [],
        [
            {
                "signal_type": "business_activity",
                "direction": "growth",
                "list_present": True,
                "declared_count": 13,
                "extracted_count": 13,
                "validation_status": "partial",
            },
        ],
        [],
        period="2026-06-01",
        source_url="https://example.com",
    )
    industry = result["industries"][0]
    assert industry["component_coverage"]["coverage_status"] == "unavailable"
    assert industry["component_coverage"]["available_components"] is None


SERVICES_COMPONENT_KEYS = {
    "business_activity",
    "new_orders",
    "employment",
    "supplier_deliveries",
    "inventories",
    "inventory_sentiment",
    "prices",
    "backlog",
    "new_export_orders",
    "imports",
}


def test_services_direction_labels_preserve_reduction_wording():
    assert ism_services_industry.SERVICES_DIRECTION_LABELS["reduction"] == "Reduction"


def test_build_services_signal_trend_returns_one_point_per_report():
    reports = [
        {"report_id": "r1", "report_month": "2026-05-01"},
        {"report_id": "r2", "report_month": "2026-06-01"},
    ]
    signals = [
        {
            "report_id": "r2",
            "signal_type": "overall_growth",
            "direction": "growth",
            "industry": "Construction",
            "rank": 1,
            "source_excerpt": "growth",
        },
    ]
    coverage = [
        {
            "report_id": "r2",
            "signal_type": "overall_growth",
            "direction": "growth",
            "validation_status": "complete",
            "list_present": True,
            "declared_count": 14,
            "extracted_count": 14,
            "evidence_text": "",
            "source_url": "",
            "source_hash": "",
        },
    ]
    trend = ism_services_industry.build_services_signal_trend(
        reports, signals, coverage, "Construction"
    )
    assert len(trend) == 2
    assert trend[0]["period"] == "2026-05-01"
    assert trend[1]["period"] == "2026-06-01"


def test_signal_trend_point_has_all_component_keys():
    reports = [{"report_id": "r1", "report_month": "2026-06-01"}]
    trend = ism_services_industry.build_services_signal_trend(
        reports, [], [], "Construction"
    )
    point = trend[0]
    assert set(point["components"].keys()) == SERVICES_COMPONENT_KEYS


def test_signal_trend_listed_state_shows_direction_rank_and_list_size():
    reports = [{"report_id": "r1", "report_month": "2026-06-01"}]
    signals = [
        {
            "report_id": "r1",
            "signal_type": "overall_growth",
            "direction": "growth",
            "industry": "Construction",
            "rank": 1,
            "source_excerpt": "growth",
        },
        {
            "report_id": "r1",
            "signal_type": "business_activity",
            "direction": "increase",
            "industry": "Construction",
            "rank": 2,
            "source_excerpt": "increase",
        },
    ]
    coverage = [
        {
            "report_id": "r1",
            "signal_type": "overall_growth",
            "direction": "growth",
            "validation_status": "complete",
            "list_present": True,
            "declared_count": 14,
            "extracted_count": 14,
            "evidence_text": "",
            "source_url": "",
            "source_hash": "",
        },
        {
            "report_id": "r1",
            "signal_type": "business_activity",
            "direction": "increase",
            "validation_status": "complete",
            "list_present": True,
            "declared_count": 8,
            "extracted_count": 8,
            "evidence_text": "",
            "source_url": "",
            "source_hash": "",
        },
    ]
    trend = ism_services_industry.build_services_signal_trend(
        reports, signals, coverage, "Construction"
    )
    point = trend[0]
    assert point["overall"] == {
        "status": "listed",
        "direction": "growth",
        "direction_label": "Growth",
        "rank": 1,
        "list_size": 14,
    }
    assert point["components"]["business_activity"] == {
        "status": "listed",
        "direction": "increase",
        "direction_label": "Increase",
        "rank": 2,
        "list_size": 8,
    }


def test_signal_trend_not_listed_when_all_coverage_complete():
    reports = [{"report_id": "r1", "report_month": "2026-06-01"}]
    coverage = [
        {
            "report_id": "r1",
            "signal_type": "overall_growth",
            "direction": "growth",
            "validation_status": "complete",
            "list_present": True,
            "declared_count": 14,
            "extracted_count": 14,
            "evidence_text": "",
            "source_url": "",
            "source_hash": "",
        },
        {
            "report_id": "r1",
            "signal_type": "overall_contraction",
            "direction": "contraction",
            "validation_status": "complete",
            "list_present": True,
            "declared_count": 3,
            "extracted_count": 3,
            "evidence_text": "",
            "source_url": "",
            "source_hash": "",
        },
    ]
    trend = ism_services_industry.build_services_signal_trend(
        reports, [], coverage, "Construction"
    )
    assert trend[0]["overall"]["status"] == "not_listed"
    assert trend[0]["overall"]["direction"] is None
    assert trend[0]["overall"]["direction_label"] == "Not listed"


def test_signal_trend_unavailable_when_coverage_incomplete():
    reports = [{"report_id": "r1", "report_month": "2026-06-01"}]
    coverage = [
        {
            "report_id": "r1",
            "signal_type": "overall_growth",
            "direction": "growth",
            "validation_status": "partial",
            "list_present": True,
            "declared_count": None,
            "extracted_count": 5,
            "evidence_text": "",
            "source_url": "",
            "source_hash": "",
        },
    ]
    trend = ism_services_industry.build_services_signal_trend(
        reports, [], coverage, "Construction"
    )
    assert trend[0]["overall"]["status"] == "unavailable"
    assert trend[0]["overall"]["direction_label"] == "Unavailable"


def test_signal_trend_conflicting_when_industry_in_both_directions():
    reports = [{"report_id": "r1", "report_month": "2026-06-01"}]
    signals = [
        {
            "report_id": "r1",
            "signal_type": "business_activity",
            "direction": "increase",
            "industry": "Construction",
            "rank": 1,
            "source_excerpt": "increase",
        },
        {
            "report_id": "r1",
            "signal_type": "business_activity",
            "direction": "decrease",
            "industry": "Construction",
            "rank": 1,
            "source_excerpt": "decrease",
        },
    ]
    trend = ism_services_industry.build_services_signal_trend(
        reports, signals, [], "Construction"
    )
    assert trend[0]["components"]["business_activity"]["status"] == "conflicting"
    assert (
        trend[0]["components"]["business_activity"]["direction_label"] == "Conflicting"
    )


def test_signal_trend_no_score_or_composite_fields():
    reports = [{"report_id": "r1", "report_month": "2026-06-01"}]
    trend = ism_services_industry.build_services_signal_trend(
        reports, [], [], "Construction"
    )
    point = trend[0]
    assert "score" not in point
    assert "score_coverage" not in point
    assert "positive_confirmation_count" not in point


def test_signal_trend_point_with_no_data_uses_unavailable_for_all():
    reports = [{"report_id": "r1", "report_month": "2026-06-01"}]
    trend = ism_services_industry.build_services_signal_trend(
        reports, [], [], "Construction"
    )
    point = trend[0]
    assert point["overall"]["status"] == "unavailable"
    for key in SERVICES_COMPONENT_KEYS:
        assert point["components"][key]["status"] == "unavailable"


def test_signal_trend_missing_months_not_synthesized():
    reports = [
        {"report_id": "r1", "report_month": "2026-04-01"},
        {"report_id": "r3", "report_month": "2026-06-01"},
    ]
    trend = ism_services_industry.build_services_signal_trend(
        reports, [], [], "Construction"
    )
    assert len(trend) == 2
    assert trend[0]["period"] == "2026-04-01"
    assert trend[1]["period"] == "2026-06-01"


def test_signal_trend_chronological_order():
    reports = [
        {"report_id": "r3", "report_month": "2026-06-01"},
        {"report_id": "r1", "report_month": "2026-04-01"},
        {"report_id": "r2", "report_month": "2026-05-01"},
    ]
    trend = ism_services_industry.build_services_signal_trend(
        reports, [], [], "Construction"
    )
    assert [p["period"] for p in trend] == ["2026-04-01", "2026-05-01", "2026-06-01"]


def test_services_industry_analysis_coverage_is_absent_when_all_rows_absent():
    result = ism_services_industry.build_services_industry_analysis(
        [
            {
                "date": "2026-06-01",
                "industry": "Construction",
                "direction": "growth",
                "rank": 1,
            },
        ],
        [],
        [
            {
                "signal_type": "business_activity",
                "direction": "growth",
                "validation_status": "absent",
            },
            {
                "signal_type": "new_orders",
                "direction": "growth",
                "validation_status": "absent",
            },
        ],
        [],
        period="2026-06-01",
        source_url="https://example.com",
    )
    industry = result["industries"][0]
    assert industry["component_coverage"]["coverage_status"] == "absent"
    assert industry["component_coverage"]["available_components"] == 0

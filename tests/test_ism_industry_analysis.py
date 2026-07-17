import pytest

from app.tools import ism_industry_analysis


def test_canonical_industries_contains_18_entries():
    assert len(ism_industry_analysis.CANONICAL_INDUSTRIES) == 18


def test_normalize_industry_accepts_exact_canonical_name():
    result = ism_industry_analysis.normalize_industry(
        "Printing & Related Support Activities"
    )
    assert result == "Printing & Related Support Activities"


def test_normalize_industry_accepts_known_alias():
    result = ism_industry_analysis.normalize_industry(
        "Printing and Related Support Activities"
    )
    assert result == "Printing & Related Support Activities"


def test_normalize_industry_accepts_short_alias():
    result = ism_industry_analysis.normalize_industry("Primary Metal")
    assert result == "Primary Metals"


def test_normalize_industry_rejects_unknown_name():
    with pytest.raises(ValueError, match="unknown industry"):
        ism_industry_analysis.normalize_industry("NonExistent Industry")


def test_normalize_industry_rejects_empty_string():
    with pytest.raises(ValueError, match="industry name is required"):
        ism_industry_analysis.normalize_industry("")


def test_normalize_industry_rejects_none():
    with pytest.raises(ValueError, match="industry name is required"):
        ism_industry_analysis.normalize_industry(None)


def test_normalize_industry_normalizes_whitespace():
    result = ism_industry_analysis.normalize_industry("  Machinery  ")
    assert result == "Machinery"


def test_normalize_industry_handles_all_18_canonical_names():
    for name in ism_industry_analysis.CANONICAL_INDUSTRIES:
        result = ism_industry_analysis.normalize_industry(name)
        assert result == name


def test_normalize_industry_maps_known_aliases():
    canonical = ism_industry_analysis.normalize_industry(
        "Electrical Equipment, Appliances and Components"
    )
    assert canonical == "Electrical Equipment, Appliances & Components"


def test_validate_industry_name_returns_true_for_valid():
    assert ism_industry_analysis.validate_industry_name("Machinery") is True


def test_validate_industry_name_returns_false_for_invalid():
    assert ism_industry_analysis.validate_industry_name("Fake Industry") is False


def test_duplicate_canonical_normalization_returns_same_string():
    for name in ism_industry_analysis.CANONICAL_INDUSTRIES:
        first = ism_industry_analysis.normalize_industry(name)
        second = ism_industry_analysis.normalize_industry(first)
        assert first == second


def _june_2026_report():
    return {
        "report_id": "ism_manufacturing_2026_06",
        "report_month": "2026-06-01",
        "title": "June 2026 ISM Manufacturing PMI Report",
        "source_name": "prnewswire",
        "source_url": "https://example.com/june-2026.html",
    }


def _june_2026_signals():
    growth_industries = [
        "Printing & Related Support Activities",
        "Machinery",
        "Chemical Products",
        "Computer & Electronic Products",
        "Electrical Equipment, Appliances & Components",
        "Food, Beverage & Tobacco Products",
        "Fabricated Metal Products",
        "Primary Metals",
        "Paper Products",
        "Miscellaneous Manufacturing",
        "Furniture & Related Products",
        "Transportation Equipment",
        "Plastics & Rubber Products",
        "Wood Products",
    ]
    new_orders_growth = [
        "Chemical Products",
        "Computer & Electronic Products",
        "Printing & Related Support Activities",
        "Machinery",
        "Electrical Equipment, Appliances & Components",
        "Food, Beverage & Tobacco Products",
        "Fabricated Metal Products",
        "Primary Metals",
        "Paper Products",
        "Miscellaneous Manufacturing",
        "Furniture & Related Products",
    ]
    production_growth = [
        "Printing & Related Support Activities",
        "Chemical Products",
        "Computer & Electronic Products",
        "Machinery",
        "Electrical Equipment, Appliances & Components",
        "Food, Beverage & Tobacco Products",
        "Fabricated Metal Products",
        "Paper Products",
    ]
    backlog_higher = [
        "Machinery",
        "Computer & Electronic Products",
        "Chemical Products",
        "Electrical Equipment, Appliances & Components",
        "Food, Beverage & Tobacco Products",
    ]

    signals = []
    evidence = "The 14 manufacturing industries reporting growth in June."
    for rank, ind in enumerate(growth_industries, start=1):
        signals.append(
            {
                "signal_type": "overall_growth",
                "direction": "growth",
                "industry": ind,
                "rank": rank,
                "evidence_text": evidence,
            }
        )

    for ind in [
        "Nonmetallic Mineral Products",
        "Apparel, Leather & Allied Products",
        "Petroleum & Coal Products",
    ]:
        rank = [
            "Nonmetallic Mineral Products",
            "Apparel, Leather & Allied Products",
            "Petroleum & Coal Products",
        ].index(ind) + 1
        signals.append(
            {
                "signal_type": "overall_contraction",
                "direction": "contraction",
                "industry": ind,
                "rank": rank,
                "evidence_text": "The three industries reporting contraction in June.",
            }
        )

    evidence_no = "The 11 industries reporting growth in new orders in June."
    for rank, ind in enumerate(new_orders_growth, start=1):
        signals.append(
            {
                "signal_type": "new_orders",
                "direction": "growth",
                "industry": ind,
                "rank": rank,
                "evidence_text": evidence_no,
            }
        )

    for ind in ["Apparel, Leather & Allied Products", "Nonmetallic Mineral Products"]:
        rank = [
            "Apparel, Leather & Allied Products",
            "Nonmetallic Mineral Products",
        ].index(ind) + 1
        signals.append(
            {
                "signal_type": "new_orders",
                "direction": "decrease",
                "industry": ind,
                "rank": rank,
                "evidence_text": "The two industries reporting a decrease in new orders.",
            }
        )

    evidence_prod = "The eight industries reporting production growth in June."
    for rank, ind in enumerate(production_growth, start=1):
        signals.append(
            {
                "signal_type": "production",
                "direction": "growth",
                "industry": ind,
                "rank": rank,
                "evidence_text": evidence_prod,
            }
        )

    for ind in [
        "Apparel, Leather & Allied Products",
        "Nonmetallic Mineral Products",
        "Petroleum & Coal Products",
        "Plastics & Rubber Products",
    ]:
        rank = [
            "Apparel, Leather & Allied Products",
            "Nonmetallic Mineral Products",
            "Petroleum & Coal Products",
            "Plastics & Rubber Products",
        ].index(ind) + 1
        signals.append(
            {
                "signal_type": "production",
                "direction": "decrease",
                "industry": ind,
                "rank": rank,
                "evidence_text": "The four industries reporting a decrease in production.",
            }
        )

    evidence_bh = "The five industries reporting higher order backlogs."
    for rank, ind in enumerate(backlog_higher, start=1):
        signals.append(
            {
                "signal_type": "backlog",
                "direction": "higher",
                "industry": ind,
                "rank": rank,
                "evidence_text": evidence_bh,
            }
        )

    for ind in [
        "Nonmetallic Mineral Products",
        "Fabricated Metal Products",
        "Apparel, Leather & Allied Products",
        "Primary Metals",
    ]:
        rank = [
            "Nonmetallic Mineral Products",
            "Fabricated Metal Products",
            "Apparel, Leather & Allied Products",
            "Primary Metals",
        ].index(ind) + 1
        signals.append(
            {
                "signal_type": "backlog",
                "direction": "lower",
                "industry": ind,
                "rank": rank,
                "evidence_text": "The four industries reporting lower order backlogs.",
            }
        )

    return signals


def _june_2026_coverage():
    return [
        {
            "signal_type": "overall_growth",
            "direction": "growth",
            "list_present": True,
            "declared_count": 14,
            "extracted_count": 14,
            "validation_status": "complete",
            "evidence_text": "The 14 manufacturing industries reporting growth in June.",
        },
        {
            "signal_type": "overall_contraction",
            "direction": "contraction",
            "list_present": True,
            "declared_count": 3,
            "extracted_count": 3,
            "validation_status": "complete",
            "evidence_text": "The three industries reporting contraction in June.",
        },
        {
            "signal_type": "new_orders",
            "direction": "growth",
            "list_present": True,
            "declared_count": 11,
            "extracted_count": 11,
            "validation_status": "complete",
            "evidence_text": "The 11 industries reporting growth in new orders.",
        },
        {
            "signal_type": "new_orders",
            "direction": "decrease",
            "list_present": True,
            "declared_count": 2,
            "extracted_count": 2,
            "validation_status": "complete",
            "evidence_text": "The two industries reporting a decrease in new orders.",
        },
        {
            "signal_type": "production",
            "direction": "growth",
            "list_present": True,
            "declared_count": 8,
            "extracted_count": 8,
            "validation_status": "complete",
            "evidence_text": "The eight industries reporting production growth in June.",
        },
        {
            "signal_type": "production",
            "direction": "decrease",
            "list_present": True,
            "declared_count": 4,
            "extracted_count": 4,
            "validation_status": "complete",
            "evidence_text": "The four industries reporting a decrease in production.",
        },
        {
            "signal_type": "backlog",
            "direction": "higher",
            "list_present": True,
            "declared_count": 5,
            "extracted_count": 5,
            "validation_status": "complete",
            "evidence_text": "The five industries reporting higher order backlogs.",
        },
        {
            "signal_type": "backlog",
            "direction": "lower",
            "list_present": True,
            "declared_count": 4,
            "extracted_count": 4,
            "validation_status": "complete",
            "evidence_text": "The four industries reporting lower order backlogs.",
        },
    ]


def _june_2026_at_a_glance():
    return [
        {
            "series_id": "ism_manufacturing_new_orders",
            "current_value": 56.0,
            "direction": "Growing",
            "rate_of_change": "Slower",
            "point_change": -1.5,
            "trend_months": 8,
        },
        {
            "series_id": "ism_manufacturing_production",
            "current_value": 52.2,
            "direction": "Growing",
            "rate_of_change": "Slower",
            "point_change": -0.8,
            "trend_months": 6,
        },
        {
            "series_id": "ism_manufacturing_order_backlog",
            "current_value": 50.5,
            "direction": "Growing",
            "rate_of_change": "Slower",
            "point_change": -2.1,
            "trend_months": 4,
        },
        {
            "series_id": "ism_manufacturing_inventories",
            "current_value": 51.4,
            "direction": "Growing",
            "rate_of_change": "From Contracting",
            "point_change": 3.2,
            "trend_months": 2,
        },
        {
            "series_id": "ism_manufacturing_customer_inventories",
            "current_value": 42.3,
            "direction": "Too Low",
            "rate_of_change": "Faster",
            "point_change": -4.1,
            "trend_months": 5,
        },
    ]


def _june_2026_comments():
    return [
        {
            "industry": "Chemical Products",
            "comment_text": "Input costs remain elevated.",
        },
        {"industry": "Machinery", "comment_text": "Demand is steady."},
    ]


def test_build_analysis_printing_new_orders_positive_rank3():
    result = ism_industry_analysis.build_ism_industry_analysis(
        _june_2026_report(),
        _june_2026_signals(),
        _june_2026_coverage(),
        _june_2026_at_a_glance(),
        _june_2026_comments(),
    )

    industries = {i["industry"]: i for i in result["industries"]}
    printing = industries["Printing & Related Support Activities"]

    assert printing["overall_signal"]["rank"] == 1
    assert printing["overall_signal"]["direction"] == "growth"

    no = printing["core_signals"]["new_orders"]
    assert no["status"] == "positive"
    assert no["rank"] == 3

    prod = printing["core_signals"]["production"]
    assert prod["status"] == "positive"
    assert prod["rank"] == 1

    backlog = printing["core_signals"]["backlog"]
    assert backlog["status"] == "not_reported"
    assert backlog["rank"] is None


def test_build_analysis_printing_has_no_comments():
    result = ism_industry_analysis.build_ism_industry_analysis(
        _june_2026_report(),
        _june_2026_signals(),
        _june_2026_coverage(),
        _june_2026_at_a_glance(),
        _june_2026_comments(),
    )

    industries = {i["industry"]: i for i in result["industries"]}
    printing = industries["Printing & Related Support Activities"]

    assert printing["comments"] == []


def test_build_analysis_machinery_has_comment():
    result = ism_industry_analysis.build_ism_industry_analysis(
        _june_2026_report(),
        _june_2026_signals(),
        _june_2026_coverage(),
        _june_2026_at_a_glance(),
        _june_2026_comments(),
    )

    industries = {i["industry"]: i for i in result["industries"]}
    machinery = industries["Machinery"]

    assert machinery["comments"] == ["Demand is steady."]


def test_build_analysis_apparel_has_negative_new_orders():
    result = ism_industry_analysis.build_ism_industry_analysis(
        _june_2026_report(),
        _june_2026_signals(),
        _june_2026_coverage(),
        _june_2026_at_a_glance(),
        _june_2026_comments(),
    )

    industries = {i["industry"]: i for i in result["industries"]}
    apparel = industries["Apparel, Leather & Allied Products"]

    assert apparel["overall_signal"]["direction"] == "contraction"

    no = apparel["core_signals"]["new_orders"]
    assert no["status"] == "negative"
    assert no["direction"] == "decrease"

    prod = apparel["core_signals"]["production"]
    assert prod["status"] == "negative"

    backlog = apparel["core_signals"]["backlog"]
    assert backlog["status"] == "negative"


def test_build_analysis_status_available_when_all_core_coverage_complete():
    result = ism_industry_analysis.build_ism_industry_analysis(
        _june_2026_report(),
        _june_2026_signals(),
        _june_2026_coverage(),
        _june_2026_at_a_glance(),
        _june_2026_comments(),
    )

    assert result["status"] == "available"
    assert result["report_id"] == "ism_manufacturing_2026_06"


def test_build_analysis_status_partial_when_core_coverage_missing():
    coverage = _june_2026_coverage()
    for c in coverage:
        if c["signal_type"] == "backlog" and c["direction"] == "higher":
            c["validation_status"] = "partial"

    result = ism_industry_analysis.build_ism_industry_analysis(
        _june_2026_report(),
        _june_2026_signals(),
        coverage,
        _june_2026_at_a_glance(),
        _june_2026_comments(),
    )

    assert result["status"] == "partial"


def test_build_analysis_macro_context_has_expected_fields():
    result = ism_industry_analysis.build_ism_industry_analysis(
        _june_2026_report(),
        _june_2026_signals(),
        _june_2026_coverage(),
        _june_2026_at_a_glance(),
        _june_2026_comments(),
    )

    mc = result["macro_context"]
    assert mc["new_orders"]["value"] == 56.0
    assert mc["new_orders"]["direction"] == "Growing"
    assert mc["new_orders"]["point_change"] == -1.5
    assert mc["new_orders"]["trend_months"] == 8
    assert mc["new_orders"]["tone"] == "amber"
    assert mc["production"]["value"] == 52.2
    assert mc["production"]["point_change"] == -0.8
    assert mc["production"]["trend_months"] == 6
    assert mc["production"]["tone"] == "amber"
    assert mc["backlog"]["value"] == 50.5
    assert mc["backlog"]["point_change"] == -2.1
    assert mc["backlog"]["trend_months"] == 4
    assert mc["backlog"]["tone"] == "amber"
    assert mc["inventories"]["value"] == 51.4
    assert mc["inventories"]["point_change"] == 3.2
    assert mc["inventories"]["trend_months"] == 2
    assert mc["inventories"]["tone"] == "amber"
    assert mc["customer_inventories"]["value"] == 42.3
    assert mc["customer_inventories"]["direction"] == "Too Low"
    assert mc["customer_inventories"]["point_change"] == -4.1
    assert mc["customer_inventories"]["trend_months"] == 5
    assert mc["customer_inventories"]["tone"] == "amber"


def test_build_analysis_none_report_returns_unavailable():
    result = ism_industry_analysis.build_ism_industry_analysis(None, [], [], [], [])

    assert result["status"] == "unavailable"
    assert result["industries"] == []


def test_build_analysis_rejects_duplicate_industry_in_signal_list():
    signals = _june_2026_signals()
    signals.append(
        {
            "signal_type": "new_orders",
            "direction": "growth",
            "industry": "Chemical Products",
            "rank": 12,
            "evidence_text": "Duplicate signal",
        }
    )

    with pytest.raises(ValueError, match="duplicated"):
        ism_industry_analysis.build_ism_industry_analysis(
            _june_2026_report(),
            signals,
            _june_2026_coverage(),
            _june_2026_at_a_glance(),
            _june_2026_comments(),
        )


def test_build_analysis_rejects_duplicate_ranks():
    signals = _june_2026_signals()
    for s in signals:
        if s["signal_type"] == "overall_growth" and s["rank"] == 14:
            s["rank"] = 1

    with pytest.raises(ValueError, match="ranks are incomplete"):
        ism_industry_analysis.build_ism_industry_analysis(
            _june_2026_report(),
            signals,
            _june_2026_coverage(),
            _june_2026_at_a_glance(),
            _june_2026_comments(),
        )


def test_build_analysis_rejects_complete_coverage_with_mismatched_extracted_count():
    coverage = _june_2026_coverage()
    for c in coverage:
        if c["signal_type"] == "overall_growth":
            c["extracted_count"] = 13
            break

    with pytest.raises(ValueError, match="declared_count.*extracted_count"):
        ism_industry_analysis.build_ism_industry_analysis(
            _june_2026_report(),
            _june_2026_signals(),
            coverage,
            _june_2026_at_a_glance(),
            _june_2026_comments(),
        )


def test_build_analysis_rejects_complete_coverage_without_signal_group():
    coverage = _june_2026_coverage()
    coverage.append(
        {
            "signal_type": "new_export_orders",
            "direction": "growth",
            "list_present": True,
            "declared_count": 3,
            "extracted_count": 3,
            "validation_status": "complete",
            "evidence_text": "Three industries reported growth in new export orders.",
        }
    )

    with pytest.raises(ValueError, match="no signal rows exist"):
        ism_industry_analysis.build_ism_industry_analysis(
            _june_2026_report(),
            _june_2026_signals(),
            coverage,
            _june_2026_at_a_glance(),
            _june_2026_comments(),
        )


def test_build_analysis_unavailable_when_coverage_missing():
    result = ism_industry_analysis.build_ism_industry_analysis(
        _june_2026_report(),
        _june_2026_signals(),
        [],
        _june_2026_at_a_glance(),
        _june_2026_comments(),
    )

    industries = {i["industry"]: i for i in result["industries"]}

    printing = industries["Printing & Related Support Activities"]
    assert printing["core_signals"]["new_orders"]["status"] == "positive"
    assert printing["core_signals"]["new_orders"]["rank"] is None
    assert printing["core_signals"]["production"]["status"] == "positive"
    assert printing["core_signals"]["production"]["rank"] is None
    assert printing["core_signals"]["backlog"]["status"] == "unavailable"


def test_build_analysis_puts_negative_backlog_as_negative():
    result = ism_industry_analysis.build_ism_industry_analysis(
        _june_2026_report(),
        _june_2026_signals(),
        _june_2026_coverage(),
        _june_2026_at_a_glance(),
        _june_2026_comments(),
    )

    industries = {i["industry"]: i for i in result["industries"]}
    apparel = industries["Apparel, Leather & Allied Products"]

    backlog = apparel["core_signals"]["backlog"]
    assert backlog["status"] == "negative"


def test_build_analysis_industry_list_includes_all_industries():
    result = ism_industry_analysis.build_ism_industry_analysis(
        _june_2026_report(),
        _june_2026_signals(),
        _june_2026_coverage(),
        _june_2026_at_a_glance(),
        _june_2026_comments(),
    )

    industry_names = {i["industry"] for i in result["industries"]}
    assert "Printing & Related Support Activities" in industry_names
    assert "Machinery" in industry_names
    assert "Apparel, Leather & Allied Products" in industry_names
    assert "Nonmetallic Mineral Products" in industry_names
    assert "Chemical Products" in industry_names


# ── Step 7.2: scoring helpers ──────────────────────────────────────────────────


def test_positive_score_first_rank():
    score = ism_industry_analysis._positive_score(1, 14)
    assert score == pytest.approx(100.0)


def test_positive_score_mid_rank():
    score = ism_industry_analysis._positive_score(3, 11)
    assert score == pytest.approx(90.9090909)


def test_positive_score_last_rank():
    score = ism_industry_analysis._positive_score(14, 14)
    assert score == pytest.approx(53.5714286)


def test_positive_score_raises_for_out_of_range_rank():
    with pytest.raises(ValueError, match="rank.*out of range"):
        ism_industry_analysis._positive_score(0, 14)
    with pytest.raises(ValueError, match="rank.*out of range"):
        ism_industry_analysis._positive_score(15, 14)


def test_negative_score_first_rank():
    score = ism_industry_analysis._negative_score(1, 3)
    assert score == pytest.approx(0.0)


def test_negative_score_last_rank():
    score = ism_industry_analysis._negative_score(3, 3)
    assert score == pytest.approx(33.3333333)


def test_negative_score_raises_for_out_of_range_rank():
    with pytest.raises(ValueError, match="rank.*out of range"):
        ism_industry_analysis._negative_score(0, 5)
    with pytest.raises(ValueError, match="rank.*out of range"):
        ism_industry_analysis._negative_score(6, 5)


def test_signal_component_score_positive():
    signal = {"status": "positive", "rank": 3, "list_size": 11}
    score = ism_industry_analysis._signal_component_score(signal)
    assert score == pytest.approx(90.9090909)


def test_signal_component_score_negative():
    signal = {"status": "negative", "rank": 1, "list_size": 4}
    score = ism_industry_analysis._signal_component_score(signal)
    assert score == pytest.approx(0.0)


def test_signal_component_score_not_reported():
    signal = {"status": "not_reported"}
    score = ism_industry_analysis._signal_component_score(signal)
    assert score == pytest.approx(50.0)


def test_signal_component_score_unavailable():
    signal = {"status": "unavailable"}
    score = ism_industry_analysis._signal_component_score(signal)
    assert score is None


def test_signal_component_score_positive_no_rank():
    signal = {"status": "positive", "rank": None, "list_size": None}
    score = ism_industry_analysis._signal_component_score(signal)
    assert score is None


def test_score_label_strong():
    assert ism_industry_analysis._score_label(80.0) == "strong"


def test_score_label_improving():
    assert ism_industry_analysis._score_label(70.0) == "improving"


def test_score_label_mixed():
    assert ism_industry_analysis._score_label(50.0) == "mixed"


def test_score_label_weakening():
    assert ism_industry_analysis._score_label(30.0) == "weakening"


def test_score_label_weak():
    assert ism_industry_analysis._score_label(15.0) == "weak"


def test_score_label_boundary_strong():
    assert ism_industry_analysis._score_label(75.0) == "strong"


def test_score_label_boundary_improving():
    assert ism_industry_analysis._score_label(60.0) == "improving"


def test_score_label_boundary_mixed():
    assert ism_industry_analysis._score_label(40.0) == "mixed"


def test_score_label_boundary_weakening():
    assert ism_industry_analysis._score_label(25.0) == "weakening"


def test_score_label_none():
    assert ism_industry_analysis._score_label(None) == "unavailable"


def test_build_industry_scores_all_four_components():
    overall = {"status": "positive", "rank": 1, "list_size": 14}
    core = {
        "new_orders": {"status": "positive", "rank": 3, "list_size": 11},
        "production": {"status": "positive", "rank": 1, "list_size": 8},
        "backlog": {"status": "not_reported"},
    }
    score, coverage, label, component_scores = (
        ism_industry_analysis._build_industry_scores(overall, core)
    )
    assert score == pytest.approx(86.36363636)
    assert coverage == pytest.approx(100.0)
    assert label == "strong"
    assert component_scores["new_orders"] == pytest.approx(90.9090909)
    assert component_scores["production"] == pytest.approx(100.0)
    assert component_scores["backlog"] == pytest.approx(50.0)
    assert component_scores["overall"] == pytest.approx(100.0)


def test_build_industry_scores_with_unavailable_weights_adjusted():
    overall = {"status": "unavailable"}
    core = {
        "new_orders": {"status": "positive", "rank": 3, "list_size": 11},
        "production": {"status": "unavailable"},
        "backlog": {"status": "not_reported"},
    }
    score, coverage, label, _ = ism_industry_analysis._build_industry_scores(
        overall, core
    )
    # Only new_orders (0.40) + backlog (0.20) available → effective weight 0.60
    # score = (90.909... * 0.40 + 50 * 0.20) / 0.60
    assert score == pytest.approx(77.27272727)
    assert coverage == pytest.approx(60.0)


def test_build_industry_scores_no_components_returns_none():
    overall = {"status": "unavailable"}
    core = {
        "new_orders": {"status": "unavailable"},
        "production": {"status": "unavailable"},
        "backlog": {"status": "unavailable"},
    }
    score, coverage, label, _ = ism_industry_analysis._build_industry_scores(
        overall, core
    )
    assert score is None
    assert coverage == 0.0
    assert label == "unavailable"


def test_industry_sort_key_orders_correctly():
    industries = [
        {
            "industry": "Low Score",
            "score": 30.0,
            "score_coverage": 100.0,
            "overall_signal": {"rank": 5},
        },
        {
            "industry": "High Score",
            "score": 90.0,
            "score_coverage": 100.0,
            "overall_signal": {"rank": 1},
        },
        {
            "industry": "Mid Score",
            "score": 60.0,
            "score_coverage": 100.0,
            "overall_signal": {"rank": 3},
        },
    ]
    sorted_inds = sorted(industries, key=ism_industry_analysis._industry_sort_key)
    assert sorted_inds[0]["industry"] == "High Score"
    assert sorted_inds[1]["industry"] == "Mid Score"
    assert sorted_inds[2]["industry"] == "Low Score"


def test_industry_sort_key_none_score_last():
    industries = [
        {
            "industry": "Known",
            "score": 50.0,
            "score_coverage": 100.0,
            "overall_signal": {"rank": 2},
        },
        {
            "industry": "Unknown",
            "score": None,
            "score_coverage": 0.0,
            "overall_signal": {"rank": None},
        },
    ]
    sorted_inds = sorted(industries, key=ism_industry_analysis._industry_sort_key)
    assert sorted_inds[0]["industry"] == "Known"
    assert sorted_inds[1]["industry"] == "Unknown"


def test_industry_sort_key_tiebreaks_by_coverage():
    industries = [
        {
            "industry": "A",
            "score": 50.0,
            "score_coverage": 80.0,
            "overall_signal": {"rank": 1},
        },
        {
            "industry": "B",
            "score": 50.0,
            "score_coverage": 100.0,
            "overall_signal": {"rank": 1},
        },
    ]
    sorted_inds = sorted(industries, key=ism_industry_analysis._industry_sort_key)
    assert sorted_inds[0]["industry"] == "B"  # higher coverage first


# ── Step 7.2: score components in build output ─────────────────────────────────


def test_build_analysis_core_signals_have_component_score():
    result = ism_industry_analysis.build_ism_industry_analysis(
        _june_2026_report(),
        _june_2026_signals(),
        _june_2026_coverage(),
        _june_2026_at_a_glance(),
        _june_2026_comments(),
    )
    printing = next(
        i
        for i in result["industries"]
        if i["industry"] == "Printing & Related Support Activities"
    )
    assert printing["core_signals"]["new_orders"]["component_score"] == pytest.approx(
        90.9, rel=0.01
    )
    assert printing["core_signals"]["production"]["component_score"] == pytest.approx(
        100.0
    )
    assert printing["core_signals"]["backlog"]["component_score"] == pytest.approx(
        50.0
    )  # not_reported
    os_ = printing["overall_signal"]
    assert os_["status"] == "positive"
    assert os_["rank"] == 1
    assert os_["direction"] == "growth"
    assert os_["list_size"] == 14
    assert os_["component_score"] == pytest.approx(100.0)


def test_build_analysis_printing_score():
    result = ism_industry_analysis.build_ism_industry_analysis(
        _june_2026_report(),
        _june_2026_signals(),
        _june_2026_coverage(),
        _june_2026_at_a_glance(),
        _june_2026_comments(),
    )
    printing = next(
        i
        for i in result["industries"]
        if i["industry"] == "Printing & Related Support Activities"
    )
    assert printing["score"] == pytest.approx(86.4, rel=0.01)
    assert printing["score_coverage"] == 100.0
    assert printing["score_label"] == "strong"


def test_build_analysis_apparel_score():
    result = ism_industry_analysis.build_ism_industry_analysis(
        _june_2026_report(),
        _june_2026_signals(),
        _june_2026_coverage(),
        _june_2026_at_a_glance(),
        _june_2026_comments(),
    )
    apparel = next(
        i
        for i in result["industries"]
        if i["industry"] == "Apparel, Leather & Allied Products"
    )
    assert apparel["score"] == pytest.approx(6.7, rel=0.01)
    assert apparel["score_label"] == "weak"


def test_build_analysis_has_score_version_and_weights():
    result = ism_industry_analysis.build_ism_industry_analysis(
        _june_2026_report(),
        _june_2026_signals(),
        _june_2026_coverage(),
        _june_2026_at_a_glance(),
        _june_2026_comments(),
    )
    assert result["score_version"] == "ism_industry_signal_v1"
    assert result["score_weights"] == {
        "new_orders": 0.40,
        "production": 0.30,
        "backlog": 0.20,
        "overall": 0.10,
    }


def test_build_analysis_industries_sorted_by_score():
    result = ism_industry_analysis.build_ism_industry_analysis(
        _june_2026_report(),
        _june_2026_signals(),
        _june_2026_coverage(),
        _june_2026_at_a_glance(),
        _june_2026_comments(),
    )
    scores = [i["score"] for i in result["industries"] if i["score"] is not None]
    assert scores == sorted(scores, reverse=True)


def test_build_analysis_industries_with_none_score_at_end():
    result = ism_industry_analysis.build_ism_industry_analysis(
        _june_2026_report(),
        _june_2026_signals(),
        _june_2026_coverage(),
        _june_2026_at_a_glance(),
        _june_2026_comments(),
    )
    none_scores = [i for i in result["industries"] if i["score"] is None]
    scored = [i for i in result["industries"] if i["score"] is not None]
    if none_scores:
        last_scored_idx = result["industries"].index(scored[-1])
        first_none_idx = result["industries"].index(none_scores[0])
        assert last_scored_idx < first_none_idx


def test_build_analysis_coverage_summary():
    result = ism_industry_analysis.build_ism_industry_analysis(
        _june_2026_report(),
        _june_2026_signals(),
        _june_2026_coverage(),
        _june_2026_at_a_glance(),
        _june_2026_comments(),
    )
    cs = result["coverage_summary"]
    assert cs["complete_components"] > 0
    assert cs["unavailable_components"] >= 0
    assert cs["complete_components"] + cs["unavailable_components"] == 17 * 4


def test_build_analysis_no_unavailable_coverage_yields_full_coverage_summary():
    result = ism_industry_analysis.build_ism_industry_analysis(
        _june_2026_report(),
        _june_2026_signals(),
        _june_2026_coverage(),
        _june_2026_at_a_glance(),
        _june_2026_comments(),
    )
    cs = result["coverage_summary"]
    assert cs["complete_components"] == 17 * 4
    assert cs["unavailable_components"] == 0


def test_build_analysis_idempotent():
    import json

    args = (
        _june_2026_report(),
        _june_2026_signals(),
        _june_2026_coverage(),
        _june_2026_at_a_glance(),
        _june_2026_comments(),
    )
    first = json.dumps(
        ism_industry_analysis.build_ism_industry_analysis(*args), sort_keys=True
    )
    second = json.dumps(
        ism_industry_analysis.build_ism_industry_analysis(*args), sort_keys=True
    )
    assert first == second

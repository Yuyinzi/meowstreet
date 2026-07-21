import pytest

from app.tools.ism_macro_signal import (
    ISM_MACRO_SIGNAL_VERSION,
    _combined_pressure,
    _confidence_signal,
    _cycle_state,
    _growth_impulse,
    _growth_pressure,
    _industry_breadth_status,
    _inflation_pressure,
    _level_state,
    _make_evidence,
    _metric_confirmation,
    _momentum,
    _phase,
    _supply_pressure,
    build_ism_macro_signal,
)


def _snapshot(report_id="ism_manufacturing_2026_06", report_month="2026-06-01", **kw):
    return {
        "report_id": report_id,
        "report_month": report_month,
        "title": "ISM Manufacturing Report June 2026",
        "source_url": "https://example.com/ism/2026-06",
        "source_hash": "abc123",
        **kw,
    }


def _aag_row(
    report_id="ism_manufacturing_2026_06",
    report_month="2026-06-01",
    series_id="ism_manufacturing_pmi",
    label="PMI",
    current_value=53.3,
    previous_value=52.8,
    point_change=0.5,
    direction="rising",
    rate_of_change="moderate",
    trend_months=3,
    source_url="https://example.com/ism/2026-06",
    source_hash="abc123",
):
    return {
        "report_id": report_id,
        "report_month": report_month,
        "series_id": series_id,
        "label": label,
        "current_value": current_value,
        "previous_value": previous_value,
        "point_change": point_change,
        "direction": direction,
        "rate_of_change": rate_of_change,
        "trend_months": trend_months,
        "source_url": source_url,
        "source_hash": source_hash,
    }


def _row_helper(series_id, label, defaults):
    def inner(**kw):
        d = dict(series_id=series_id, label=label)
        d.update(defaults)
        d.update(kw)
        return _aag_row(**d)

    return inner


_pmi_row = _row_helper(
    "ism_manufacturing_pmi",
    "PMI",
    {
        "current_value": 53.3,
        "previous_value": 52.8,
        "point_change": 0.5,
        "direction": "rising",
        "rate_of_change": "moderate",
        "trend_months": 3,
    },
)

_no_row = _row_helper(
    "ism_manufacturing_new_orders",
    "New Orders",
    {
        "current_value": 56.0,
        "previous_value": 54.0,
        "point_change": 2.0,
        "direction": "rising",
        "rate_of_change": "moderate",
        "trend_months": 3,
    },
)

_production_row = _row_helper(
    "ism_manufacturing_production",
    "Production",
    {
        "current_value": 54.0,
        "previous_value": 53.0,
        "point_change": 1.0,
        "direction": "rising",
        "rate_of_change": "moderate",
        "trend_months": 3,
    },
)

_inventories_row = _row_helper(
    "ism_manufacturing_inventories",
    "Inventories",
    {
        "current_value": 48.0,
        "previous_value": 49.0,
        "point_change": -1.0,
        "direction": "falling",
        "rate_of_change": "moderate",
        "trend_months": 2,
    },
)

_prices_row = _row_helper(
    "ism_manufacturing_prices",
    "Prices",
    {
        "current_value": 55.0,
        "previous_value": 54.0,
        "point_change": 1.0,
        "direction": "rising",
        "rate_of_change": "moderate",
        "trend_months": 3,
    },
)

_sd_row = _row_helper(
    "ism_manufacturing_supplier_deliveries",
    "Supplier Deliveries",
    {
        "current_value": 52.0,
        "previous_value": 51.0,
        "point_change": 1.0,
        "direction": "rising",
        "rate_of_change": "moderate",
        "trend_months": 3,
    },
)


def _all_rows(**kw):
    return [
        _pmi_row(**kw),
        _no_row(**kw),
        _production_row(**kw),
        _inventories_row(**kw),
        _prices_row(**kw),
        _sd_row(**kw),
    ]


def _two_month_scenario(
    pmi_current,
    pmi_previous,
    no_current,
    no_previous,
    pmi_pc=None,
    no_pc=None,
    prices_current=55.0,
    prices_previous=54.0,
    prices_pc=None,
    sd_current=52.0,
    sd_previous=51.0,
    sd_pc=None,
):
    if pmi_pc is None:
        pmi_pc = round(pmi_current - pmi_previous, 1)
    if no_pc is None:
        no_pc = round(no_current - no_previous, 1)
    if prices_pc is None:
        prices_pc = round(prices_current - prices_previous, 1)
    if sd_pc is None:
        sd_pc = round(sd_current - sd_previous, 1)
    reports = [
        _snapshot("ism_manufacturing_2026_05", "2026-05-01"),
        _snapshot("ism_manufacturing_2026_06", "2026-06-01"),
    ]
    rows = [
        _pmi_row(
            report_id="ism_manufacturing_2026_05",
            report_month="2026-05-01",
            current_value=pmi_previous,
            previous_value=pmi_previous - 1,
            point_change=round(pmi_previous - (pmi_previous - 1), 1),
        ),
        _pmi_row(
            report_id="ism_manufacturing_2026_06",
            report_month="2026-06-01",
            current_value=pmi_current,
            previous_value=pmi_previous,
            point_change=pmi_pc,
        ),
        _no_row(
            report_id="ism_manufacturing_2026_05",
            report_month="2026-05-01",
            current_value=no_previous,
            previous_value=no_previous - 1,
            point_change=round(no_previous - (no_previous - 1), 1),
        ),
        _no_row(
            report_id="ism_manufacturing_2026_06",
            report_month="2026-06-01",
            current_value=no_current,
            previous_value=no_previous,
            point_change=no_pc,
        ),
        _production_row(
            report_id="ism_manufacturing_2026_06", report_month="2026-06-01"
        ),
        _inventories_row(
            report_id="ism_manufacturing_2026_06", report_month="2026-06-01"
        ),
        _prices_row(
            report_id="ism_manufacturing_2026_06",
            report_month="2026-06-01",
            current_value=prices_current,
            previous_value=prices_previous,
            point_change=prices_pc,
        ),
        _sd_row(
            report_id="ism_manufacturing_2026_06",
            report_month="2026-06-01",
            current_value=sd_current,
            previous_value=sd_previous,
            point_change=sd_pc,
        ),
    ]
    return reports, rows


def _quick_signal(
    pmi_current,
    pmi_previous,
    no_current,
    no_previous,
    pmi_pc=None,
    no_pc=None,
    prices_current=55.0,
    prices_previous=54.0,
    prices_pc=None,
    sd_current=52.0,
    sd_previous=51.0,
    sd_pc=None,
    breadth=None,
):
    reports, rows = _two_month_scenario(
        pmi_current,
        pmi_previous,
        no_current,
        no_previous,
        pmi_pc=pmi_pc,
        no_pc=no_pc,
        prices_current=prices_current,
        prices_previous=prices_previous,
        prices_pc=prices_pc,
        sd_current=sd_current,
        sd_previous=sd_previous,
        sd_pc=sd_pc,
    )
    return build_ism_macro_signal(reports, rows, industry_breadth=breadth)


def _three_month_trend(pmi_vals, no_vals):
    reports = [
        _snapshot("ism_manufacturing_2026_04", "2026-04-01"),
        _snapshot("ism_manufacturing_2026_05", "2026-05-01"),
        _snapshot("ism_manufacturing_2026_06", "2026-06-01"),
    ]
    rows = []
    for i, (rid, rm) in enumerate(
        [
            ("ism_manufacturing_2026_04", "2026-04-01"),
            ("ism_manufacturing_2026_05", "2026-05-01"),
            ("ism_manufacturing_2026_06", "2026-06-01"),
        ]
    ):
        pmi_c, pmi_p = pmi_vals[i]
        no_c, no_p = no_vals[i]
        pmi_pc = round(pmi_c - pmi_p, 1)
        no_pc = round(no_c - no_p, 1)
        rows.append(
            _pmi_row(
                report_id=rid,
                report_month=rm,
                current_value=pmi_c,
                previous_value=pmi_p,
                point_change=pmi_pc,
            )
        )
        rows.append(
            _no_row(
                report_id=rid,
                report_month=rm,
                current_value=no_c,
                previous_value=no_p,
                point_change=no_pc,
            )
        )
    rows += [
        _production_row(
            report_id="ism_manufacturing_2026_06", report_month="2026-06-01"
        ),
        _inventories_row(
            report_id="ism_manufacturing_2026_06", report_month="2026-06-01"
        ),
        _prices_row(report_id="ism_manufacturing_2026_06", report_month="2026-06-01"),
        _sd_row(report_id="ism_manufacturing_2026_06", report_month="2026-06-01"),
    ]
    return reports, rows


# ============================================================
# _phase tests
# ============================================================


@pytest.mark.parametrize(
    "pmi,expected",
    [
        (None, "unavailable"),
        (40, "contraction"),
        (44.9, "contraction"),
        (45, "slowdown"),
        (50, "slowdown"),
        (50.1, "expansion"),
        (59.9, "expansion"),
        (60, "late_expansion"),
        (70, "late_expansion"),
    ],
)
def test_phase_boundaries(pmi, expected):
    assert _phase(pmi) == expected


# ============================================================
# _momentum tests
# ============================================================


@pytest.mark.parametrize(
    "pc,expected",
    [
        (None, "unavailable"),
        (0.1, "rising"),
        (1.0, "rising"),
        (-0.1, "falling"),
        (-5.0, "falling"),
        (0.0, "flat"),
    ],
)
def test_momentum(pc, expected):
    assert _momentum(pc) == expected


# ============================================================
# _level_state tests
# ============================================================


@pytest.mark.parametrize(
    "value,expected",
    [
        (None, "unavailable"),
        (50.1, "expanding"),
        (60, "expanding"),
        (49.9, "contracting"),
        (50, "neutral"),
    ],
)
def test_level_state(value, expected):
    assert _level_state(value) == expected


# ============================================================
# _metric_confirmation tests
# ============================================================


def test_metric_confirmation_positive_when_above_50_and_not_falling():
    assert _metric_confirmation(55.0, 53.0) == "positive"
    assert _metric_confirmation(55.0, 55.0) == "positive"


def test_metric_confirmation_negative_when_below_50_and_not_rising():
    assert _metric_confirmation(45.0, 47.0) == "negative"
    assert _metric_confirmation(45.0, 45.0) == "negative"


def test_metric_confirmation_mixed_when_level_and_momentum_disagree():
    assert _metric_confirmation(55.0, 57.0) == "mixed"


def test_metric_confirmation_unavailable_when_missing():
    assert _metric_confirmation(None, 55.0) == "unavailable"
    assert _metric_confirmation(55.0, None) == "unavailable"


# ============================================================
# _industry_breadth_status tests
# ============================================================


def test_breadth_positive_when_growth_exceeds_contraction():
    assert _industry_breadth_status(10, 5) == "positive"


def test_breadth_negative_when_contraction_exceeds_growth():
    assert _industry_breadth_status(5, 10) == "negative"


def test_breadth_mixed_when_equal():
    assert _industry_breadth_status(9, 9) == "mixed"


def test_breadth_unavailable_when_counts_missing():
    assert _industry_breadth_status(None, 5) == "unavailable"
    assert _industry_breadth_status(5, None) == "unavailable"


# ============================================================
# _cycle_state tests
# ============================================================


def test_cycle_state_peaking():
    assert _cycle_state(60, "falling", "rising") == "peaking"
    assert _cycle_state(65, "falling", "falling") == "peaking"


def test_cycle_state_troughing():
    assert _cycle_state(43, "rising", "rising") == "troughing"
    assert _cycle_state(40, "flat", "rising") == "troughing"
    assert _cycle_state(45, "flat", "rising") == "troughing"


def test_cycle_state_troughing_requires_new_orders_rising():
    assert _cycle_state(43, "rising", "falling") == "contraction_improving"


def test_cycle_state_expansion_rising():
    assert _cycle_state(55, "rising", "rising") == "expansion_rising"


def test_cycle_state_expansion_slowing():
    assert _cycle_state(55, "falling", "falling") == "expansion_slowing"


def test_cycle_state_contraction_improving():
    assert _cycle_state(48, "rising", "rising") == "contraction_improving"


def test_cycle_state_contraction_deepening():
    assert _cycle_state(48, "falling", "falling") == "contraction_deepening"


def test_cycle_state_stable():
    assert _cycle_state(55, "flat", "rising") == "stable"
    assert _cycle_state(48, "flat", "falling") == "stable"
    assert _cycle_state(50, "flat", "flat") == "stable"


def test_cycle_state_unavailable():
    assert _cycle_state(None, "rising", "rising") == "unavailable"
    assert _cycle_state(55, None, "rising") == "unavailable"


# ============================================================
# _growth_impulse tests
# ============================================================


def test_growth_impulse_turning_supportive():
    assert (
        _growth_impulse("troughing", 43, "rising", 46, "rising") == "turning_supportive"
    )


def test_growth_impulse_supports_growth():
    assert (
        _growth_impulse("expansion_rising", 54, "rising", 56, "rising")
        == "supports_growth"
    )


def test_growth_impulse_new_orders_below_50_prevents_supports_growth():
    assert (
        _growth_impulse("expansion_rising", 52, "rising", 48, "falling")
        == "growth_caution"
    )


def test_growth_impulse_supports_contraction():
    assert (
        _growth_impulse("contraction_deepening", 49, "falling", 47, "falling")
        == "supports_contraction"
    )


def test_growth_impulse_contraction_easing():
    assert (
        _growth_impulse("contraction_improving", 49, "rising", 51, "rising")
        == "contraction_easing"
    )


def test_growth_impulse_mixed():
    assert _growth_impulse("expansion_slowing", 52, "falling", 56, "rising") == "mixed"


def test_growth_impulse_unavailable():
    assert _growth_impulse("unavailable", None, None, None, None) == "unavailable"


# ============================================================
# _confidence_signal tests
# ============================================================


def test_confidence_high_when_all_optional_available():
    assert _confidence_signal("available", "positive", "positive", "positive") == "high"
    assert _confidence_signal("available", "negative", "mixed", "positive") == "high"


def test_confidence_medium_when_some_optional_available():
    assert (
        _confidence_signal("available", "positive", "unavailable", "unavailable")
        == "medium"
    )


def test_confidence_low_when_primary_partial():
    assert _confidence_signal("partial", "positive", "positive", "positive") == "low"


def test_confidence_low_when_no_optional_available():
    assert (
        _confidence_signal("available", "unavailable", "unavailable", "unavailable")
        == "low"
    )


def test_confidence_unavailable_when_signal_unavailable():
    assert (
        _confidence_signal("unavailable", "positive", "positive", "positive")
        == "unavailable"
    )


# ============================================================
# Policy context tests
# ============================================================


def test_growth_pressure_mapping():
    assert _growth_pressure("supports_growth") == "less_easing_pressure"
    assert _growth_pressure("supports_contraction") == "more_easing_pressure"
    assert _growth_pressure("turning_supportive") == "early_recovery"
    assert _growth_pressure("contraction_easing") == "early_recovery"
    assert _growth_pressure("mixed") == "mixed"
    assert _growth_pressure("growth_caution") == "mixed"


@pytest.mark.parametrize(
    "current,previous,expected",
    [
        (60, 58, "elevated"),
        (70, 65, "elevated"),
        (49.9, 50, "disinflationary"),
        (55, 54, "moderate"),
        (50.1, 49, "moderate"),
        (None, 55, "unavailable"),
        (55, None, "unavailable"),
    ],
)
def test_inflation_pressure(current, previous, expected):
    assert _inflation_pressure(current, previous) == expected


@pytest.mark.parametrize(
    "current,previous,expected",
    [
        (55, 54, "elevated"),
        (60, 58, "elevated"),
        (54.9, 53, "normal"),
        (None, 54, "unavailable"),
        (55, None, "unavailable"),
    ],
)
def test_supply_pressure(current, previous, expected):
    assert _supply_pressure(current, previous) == expected


def test_combined_stagflationary_tension_takes_precedence():
    assert (
        _combined_pressure("supports_contraction", "elevated", "normal")
        == "stagflationary_tension"
    )
    assert (
        _combined_pressure("supports_contraction", "moderate", "elevated")
        == "stagflationary_tension"
    )


def test_combined_inflation_caution():
    assert (
        _combined_pressure("supports_growth", "elevated", "normal")
        == "inflation_caution"
    )
    assert (
        _combined_pressure("supports_growth", "moderate", "elevated")
        == "inflation_caution"
    )


def test_combined_more_easing_pressure():
    assert (
        _combined_pressure("supports_contraction", "disinflationary", "normal")
        == "more_easing_pressure"
    )


def test_combined_less_easing_pressure():
    assert (
        _combined_pressure("supports_growth", "moderate", "normal")
        == "less_easing_pressure"
    )
    assert (
        _combined_pressure("supports_growth", "disinflationary", "normal")
        == "less_easing_pressure"
    )


def test_combined_mixed_pressure():
    assert _combined_pressure("mixed", "moderate", "normal") == "mixed_pressure"
    assert (
        _combined_pressure("growth_caution", "elevated", "normal") == "mixed_pressure"
    )


def test_combined_unavailable():
    assert _combined_pressure("unavailable", "moderate", "normal") == "unavailable"
    assert _combined_pressure(None, "moderate", "normal") == "unavailable"


# ============================================================
# Evidence tests
# ============================================================


def test_evidence_for_expansion_rising():
    ev = _make_evidence(54, "rising", 56, "rising", "supports_growth")
    assert ev[0] == "PMI is above 50 and rising month over month"
    assert ev[1] == "New Orders are above 50 and rising month over month"
    assert "supports continued expansion" in ev[2]


def test_evidence_for_peaking():
    ev = _make_evidence(61, "falling", 55, "falling", "growth_caution")
    assert "above 50 but falling" in ev[0]
    assert "above 50 but falling" in ev[1]
    assert "caution" in ev[2]


def test_evidence_for_missing_pmi():
    ev = _make_evidence(None, "unavailable", 55, "rising", "unavailable")
    assert ev[0] == "PMI is missing or unavailable"
    assert ev[1] == "New Orders are above 50 and rising month over month"


# ============================================================
# Full builder: test matrix
# ============================================================


def test_matrix_row1_expansion_rising():
    result = _quick_signal(54, 53, 56, 55)
    assert result["phase"] == "expansion"
    assert result["momentum"] == "rising"
    assert result["cycle_state"] == "expansion_rising"
    assert result["growth_impulse"] == "supports_growth"


def test_matrix_row2_peaking():
    result = _quick_signal(61, 62, 55, 56, prices_current=63, prices_previous=60)
    assert result["cycle_state"] == "peaking"
    assert result["growth_impulse"] == "growth_caution"
    assert result["policy_context"]["inflation_pressure"] == "elevated"
    assert result["policy_context"]["combined_pressure"] == "mixed_pressure"


def test_matrix_row3_contraction_deepening():
    result = _quick_signal(49, 50, 47, 48, prices_current=45, prices_previous=46)
    assert result["cycle_state"] == "contraction_deepening"
    assert result["growth_impulse"] == "supports_contraction"
    assert result["policy_context"]["inflation_pressure"] == "disinflationary"


def test_matrix_row4_troughing():
    result = _quick_signal(43, 43, 46, 45, pmi_pc=0)
    assert result["cycle_state"] == "troughing"
    assert result["growth_impulse"] == "turning_supportive"


def test_matrix_row5_contraction_improving_with_stagflation():
    result = _quick_signal(49, 48, 51, 50, prices_current=62, prices_previous=60)
    assert result["cycle_state"] == "contraction_improving"
    assert result["growth_impulse"] == "contraction_easing"
    assert result["policy_context"]["inflation_pressure"] == "elevated"
    assert result["policy_context"]["combined_pressure"] == "mixed_pressure"


def test_matrix_row6_new_orders_below_50():
    result = _quick_signal(52, 51, 48, 49)
    assert result["growth_impulse"] == "growth_caution"
    assert result["cycle_state"] == "expansion_rising"


def test_matrix_row7_missing_pmi():
    reports = [_snapshot("ism_manufacturing_2026_06", "2026-06-01")]
    rows = [
        _no_row(
            report_id="ism_manufacturing_2026_06",
            report_month="2026-06-01",
            current_value=55,
            previous_value=54,
            point_change=1,
        )
    ]
    result = build_ism_macro_signal(reports, rows)
    assert result["status"] == "unavailable"
    assert result["phase"] == "unavailable"
    assert result["confidence"] == "unavailable"


# ============================================================
# Validation tests
# ============================================================


def test_duplicate_series_id_raises():
    reports = [_snapshot()]
    rows = [_pmi_row(), _pmi_row()]
    with pytest.raises(ValueError, match="duplicate at-a-glance row"):
        build_ism_macro_signal(reports, rows)


def test_unknown_report_id_raises():
    reports = [_snapshot()]
    rows = [_pmi_row(report_id="ism_manufacturing_2026_05")]
    with pytest.raises(ValueError, match="unknown report_id"):
        build_ism_macro_signal(reports, rows)


def test_report_month_mismatch_raises():
    reports = [_snapshot(report_month="2026-06-01")]
    rows = [_pmi_row(report_month="2026-05-01")]
    with pytest.raises(ValueError, match="report_month mismatch"):
        build_ism_macro_signal(reports, rows)


def test_non_numeric_current_value_raises():
    reports = [_snapshot()]
    rows = [_pmi_row(current_value="abc")]
    with pytest.raises(ValueError, match="non-numeric"):
        build_ism_macro_signal(reports, rows)


def test_non_numeric_previous_value_raises():
    reports = [_snapshot()]
    rows = [_pmi_row(previous_value="abc")]
    with pytest.raises(ValueError, match="non-numeric"):
        build_ism_macro_signal(reports, rows)


def test_point_change_mismatch_raises():
    reports = [_snapshot()]
    rows = [_pmi_row(current_value=53.3, previous_value=52.8, point_change=999)]
    with pytest.raises(ValueError, match="point_change mismatch"):
        build_ism_macro_signal(reports, rows)


def test_point_change_derived_when_stored_absent():
    reports = [_snapshot()]
    rows = [_pmi_row(current_value=53.3, previous_value=52.8, point_change=None)]
    result = build_ism_macro_signal(reports, rows)
    assert result["metrics"]["pmi"]["point_change"] == 0.5


# ============================================================
# Coverage tests
# ============================================================


def test_coverage_all_required_available():
    reports, rows = _two_month_scenario(54, 53, 56, 55)
    result = build_ism_macro_signal(reports, rows)
    assert result["status"] == "available"
    assert "pmi" in result["coverage"]["available_required_metrics"]
    assert "new_orders" in result["coverage"]["available_required_metrics"]


def test_coverage_missing_pmi():
    reports = [_snapshot()]
    rows = [_no_row()]
    result = build_ism_macro_signal(reports, rows)
    assert result["status"] == "unavailable"
    assert "pmi" not in result["coverage"]["available_required_metrics"]
    assert "new_orders" in result["coverage"]["available_required_metrics"]


def test_coverage_partial_new_orders_missing():
    reports = [_snapshot()]
    rows = [_pmi_row()]
    result = build_ism_macro_signal(reports, rows)
    assert result["status"] == "partial"


def test_missing_optional_metrics():
    reports = [_snapshot()]
    rows = [_pmi_row(), _no_row()]
    result = build_ism_macro_signal(reports, rows)
    assert result["coverage"]["missing_metrics"] == [
        "production",
        "inventories",
        "prices",
        "supplier_deliveries",
    ]
    assert result["metrics"]["production"] == {}
    assert result["confirmations"]["production"] == "unavailable"
    assert result["confirmations"]["inventories"] == "unavailable"
    assert result["policy_context"]["inflation_pressure"] == "unavailable"
    assert result["policy_context"]["supply_pressure"] == "unavailable"


# ============================================================
# Breadth tests
# ============================================================


def test_missing_breadth():
    result = _quick_signal(54, 53, 56, 55, breadth=None)
    assert result["confirmations"]["industry_breadth"] == "unavailable"


def test_zero_growing_industries():
    result = _quick_signal(
        54, 53, 56, 55, breadth={"growth_count": 0, "contraction_count": 10}
    )
    assert result["confirmations"]["industry_breadth"] == "negative"


def test_breadth_does_not_require_sum_18():
    result = _quick_signal(
        54, 53, 56, 55, breadth={"growth_count": 3, "contraction_count": 1}
    )
    assert result["confirmations"]["industry_breadth"] == "positive"


# ============================================================
# Trend and continuity tests
# ============================================================


def test_trend_includes_both_reports():
    reports, rows = _two_month_scenario(54, 53, 56, 55)
    result = build_ism_macro_signal(reports, rows)
    assert len(result["trend"]) == 2
    assert result["trend"][0]["period"] == "2026-05-01"
    assert result["trend"][1]["pmi"] == 54


def test_trend_three_reports():
    reports, rows = _three_month_trend(
        [(51, 50), (52, 51), (53, 52)],
        [(53, 52), (54, 53), (55, 54)],
    )
    result = build_ism_macro_signal(reports, rows)
    assert len(result["trend"]) == 3
    assert result["trend"][0]["pmi"] == 51
    assert result["trend"][2]["pmi"] == 53


def test_continuity_adjacent_months():
    reports, rows = _two_month_scenario(54, 53, 56, 55)
    result = build_ism_macro_signal(reports, rows)
    assert result["continuity"]["months_loaded"] == 2
    assert result["continuity"]["adjacent_months"] == 1
    assert result["continuity"]["has_gap"] is False


def test_continuity_gap_detected():
    reports = [
        _snapshot("ism_manufacturing_2026_04", "2026-04-01"),
        _snapshot("ism_manufacturing_2026_06", "2026-06-01"),
    ]
    rows = [
        _pmi_row(report_id="ism_manufacturing_2026_04", report_month="2026-04-01"),
        _no_row(report_id="ism_manufacturing_2026_04", report_month="2026-04-01"),
        _pmi_row(report_id="ism_manufacturing_2026_06", report_month="2026-06-01"),
        _no_row(report_id="ism_manufacturing_2026_06", report_month="2026-06-01"),
        _production_row(
            report_id="ism_manufacturing_2026_06", report_month="2026-06-01"
        ),
        _inventories_row(
            report_id="ism_manufacturing_2026_06", report_month="2026-06-01"
        ),
        _prices_row(report_id="ism_manufacturing_2026_06", report_month="2026-06-01"),
        _sd_row(report_id="ism_manufacturing_2026_06", report_month="2026-06-01"),
    ]
    result = build_ism_macro_signal(reports, rows)
    assert result["continuity"]["has_gap"] is True
    assert result["continuity"]["adjacent_months"] == 0


def test_momentum_streak_breaks_at_gap():
    reports = [
        _snapshot("ism_manufacturing_2026_04", "2026-04-01"),
        _snapshot("ism_manufacturing_2026_06", "2026-06-01"),
    ]
    rows = [
        _pmi_row(
            report_id="ism_manufacturing_2026_04",
            report_month="2026-04-01",
            current_value=52,
            previous_value=51,
            point_change=1,
        ),
        _pmi_row(
            report_id="ism_manufacturing_2026_06",
            report_month="2026-06-01",
            current_value=54,
            previous_value=52,
            point_change=2,
        ),
    ]
    result = build_ism_macro_signal(reports, rows)
    assert result["continuity"]["latest_momentum_streak"] == 1


def test_momentum_streak_consecutive():
    reports = [
        _snapshot("ism_manufacturing_2026_04", "2026-04-01"),
        _snapshot("ism_manufacturing_2026_05", "2026-05-01"),
        _snapshot("ism_manufacturing_2026_06", "2026-06-01"),
    ]
    rows = [
        _pmi_row(
            report_id="ism_manufacturing_2026_04",
            report_month="2026-04-01",
            current_value=50,
            previous_value=51,
            point_change=-1,
        ),
        _pmi_row(
            report_id="ism_manufacturing_2026_05",
            report_month="2026-05-01",
            current_value=51,
            previous_value=50,
            point_change=1,
        ),
        _pmi_row(
            report_id="ism_manufacturing_2026_06",
            report_month="2026-06-01",
            current_value=53,
            previous_value=51,
            point_change=2,
        ),
    ]
    result = build_ism_macro_signal(reports, rows)
    assert result["continuity"]["latest_momentum_streak"] == 2


# ============================================================
# Determinism and source propagation
# ============================================================


def test_deterministic_idempotent_output():
    reports, rows = _two_month_scenario(54, 53, 56, 55)
    r1 = build_ism_macro_signal(reports, rows)
    r2 = build_ism_macro_signal(reports, rows)
    assert r1 == r2


def test_source_hash_propagated():
    reports = [_snapshot(source_hash="xyz789")]
    rows = [_pmi_row(source_hash="xyz789"), _no_row(source_hash="xyz789")]
    result = build_ism_macro_signal(reports, rows)
    assert result["source_hash"] == "xyz789"


# ============================================================
# Constants / enums
# ============================================================


def test_no_output_enum_is_hike_hold_cut():
    policy_enums = {"hike", "hold", "cut"}
    result = _quick_signal(54, 53, 56, 55)
    for key in (
        "growth_pressure",
        "inflation_pressure",
        "supply_pressure",
        "combined_pressure",
    ):
        assert result["policy_context"][key] not in policy_enums


def test_industry_scores_not_accepted_as_input():
    kw = dict(pmi_current=54, pmi_previous=53, no_current=56, no_previous=55)
    result = _quick_signal(**kw)
    assert "industry_scores" not in result


# ============================================================
# Latest report with no previous snapshot but valid aag values
# ============================================================


def test_single_report_latest_only():
    reports = [_snapshot()]
    rows = _all_rows()
    result = build_ism_macro_signal(reports, rows)
    assert result["report_id"] == "ism_manufacturing_2026_06"
    assert result["continuity"]["months_loaded"] == 1
    assert result["continuity"]["adjacent_months"] == 0
    assert result["continuity"]["has_gap"] is False


def test_persisted_report_month_mismatch_caught_after_db_roundtrip():
    import sqlite3
    from app.db import growth_cycle

    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    growth_cycle.init_db(con)
    growth_cycle.replace_ism_report_snapshot(
        con,
        _snapshot(
            report_month="2026-06-01",
            fetched_at="2026-06-15T12:00:00",
            parse_status="ok",
            next_report_period="2026-07-01",
            next_release_at="2026-07-15T10:00:00",
            next_release_label="July 2026",
        ),
        [],
        survey_type="manufacturing",
    )
    growth_cycle.replace_ism_at_a_glance_rows(
        con,
        [
            _pmi_row(report_month="2026-05-01"),
            _no_row(report_month="2026-05-01"),
        ],
    )
    con.commit()

    reports = growth_cycle.load_recent_ism_report_snapshots(
        con, limit=6, survey_type="manufacturing"
    )
    report_ids = [r["report_id"] for r in reports]
    aag_rows = growth_cycle.load_ism_at_a_glance_rows_for_reports(con, report_ids)

    with pytest.raises(ValueError, match="report_month mismatch"):
        build_ism_macro_signal(reports, aag_rows)
    con.close()

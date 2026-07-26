import pytest

from app.tools import consumer_sentiment


def _points(values, start_date="2026-01-01"):
    return [
        {"date": _shift_date(start_date, i), "value": v, "source": "test"}
        for i, v in enumerate(values)
    ]


def _shift_date(start, offset):
    year, month, day = start.split("-")
    m = int(month) + offset
    y = int(year) + (m - 1) // 12
    m = ((m - 1) % 12) + 1
    return f"{y:04d}-{m:02d}-{day}"


def _capacity_point(value):
    return {"date": "2026-06-01", "value": value, "source": "test"}


def _full_points(
    agg_values=(75.0, 78.0),
    exp_values=(80.0, 85.0),
    cur_values=(70.0, 72.0),
    start_date="2026-05-01",
):
    pts = {}
    pts["umcsi_aggregate"] = _points(agg_values, start_date)
    pts["umcsi_expectations"] = _points(exp_values, start_date)
    pts["umcsi_current_conditions"] = _points(cur_values, start_date)
    pts["household_debt_to_gdp"] = [_capacity_point(80.0)]
    pts["household_debt_service_ratio"] = [_capacity_point(9.8)]
    pts["personal_saving_rate"] = [_capacity_point(7.5)]
    pts["one_to_four_family_mortgage_liabilities"] = [_capacity_point(12000000.0)]
    return pts


def _sentiment_only_points():
    pts = _full_points()
    for sid in consumer_sentiment.CAPACITY_SERIES_IDS:
        pts[sid] = []
    return pts


def _monthly_values(count, start_date="2006-06-01"):
    return _points(tuple(float(value) for value in range(count)), start_date)


def _v2_points(
    aggregate_offset=0.0,
    expectations_offset=0.0,
    current_offset=0.0,
):
    points = _full_points()
    points["umcsi_aggregate"] = [
        {**point, "value": point["value"] + aggregate_offset}
        for point in _monthly_values(240)
    ]
    points["umcsi_expectations"] = [
        {**point, "value": point["value"] + expectations_offset}
        for point in _monthly_values(240)
    ]
    points["umcsi_current_conditions"] = [
        {**point, "value": point["value"] + current_offset}
        for point in _monthly_values(240)
    ]
    return points


def test_rolling_percentile_uses_exactly_240_months():
    points = [
        {"date": "2006-05-01", "value": 10000.0, "source": "test"},
        *_monthly_values(240),
    ]

    result = consumer_sentiment._rolling_percentile(points, "2026-05-01")

    assert result["available"] is True
    assert result["window_start"] == "2006-06-01"
    assert result["window_end"] == "2026-05-01"
    assert result["observation_count"] == 240
    assert result["rank"] == 99.79


def test_rolling_percentile_does_not_read_future_values():
    points = _monthly_values(241)

    before_future = consumer_sentiment._rolling_percentile(points[:240], "2026-05-01")
    with_future = consumer_sentiment._rolling_percentile(points, "2026-05-01")

    assert with_future == before_future


def test_rolling_percentile_uses_midrank_for_ties():
    points = [{**point, "value": 50.0} for point in _monthly_values(240)]

    result = consumer_sentiment._rolling_percentile(points, "2026-05-01")

    assert result["rank"] == 50.0


def test_rolling_percentile_requires_consecutive_months():
    points = _monthly_values(240)
    del points[120]

    result = consumer_sentiment._rolling_percentile(points, "2026-05-01")

    assert result == {
        "available": False,
        "rank": None,
        "window_start": None,
        "window_end": "2026-05-01",
        "observation_count": 239,
    }


@pytest.mark.parametrize(
    ("rank", "expected"),
    [
        (0.0, "depressed"),
        (15.0, "depressed"),
        (15.0001, "typical"),
        (84.9999, "typical"),
        (85.0, "elevated"),
        (100.0, "elevated"),
    ],
)
def test_percentile_zone_boundaries(rank, expected):
    assert consumer_sentiment._percentile_zone(rank) == expected


@pytest.mark.parametrize(
    ("rank", "expected"),
    [
        (1.0, "1st percentile"),
        (2.0, "2nd percentile"),
        (3.0, "3rd percentile"),
        (4.0, "4th percentile"),
        (8.12, "8th percentile"),
        (11.0, "11th percentile"),
        (12.0, "12th percentile"),
        (13.0, "13th percentile"),
        (21.0, "21st percentile"),
        (22.0, "22nd percentile"),
        (23.0, "23rd percentile"),
    ],
)
def test_ordinal_percentile_uses_round_half_up(rank, expected):
    assert consumer_sentiment._ordinal_percentile(rank) == expected


def test_summary_returns_v2_percentiles_for_all_three_series():
    summary = consumer_sentiment.build_summary(_v2_points())

    assert summary["method_version"] == 2
    assert summary["percentile_method"] == {
        "version": 2,
        "window_months": 240,
        "lower_boundary": 15,
        "upper_boundary": 85,
        "rank_method": "midrank",
    }
    for key in ("aggregate", "expectations", "current_conditions"):
        metric = summary[key]
        assert metric["percentile_rank"] == 99.79
        assert metric["percentile_label"] == "100th percentile"
        assert metric["percentile_zone"] == "elevated"
        assert metric["point_change_unit"] == "index_points"
    assert summary["expectations"]["role"] == "primary"
    assert summary["aggregate"]["role"] == "confirmation"
    assert summary["current_conditions"]["role"] == "confirmation"


def test_summary_does_not_return_legacy_fixed_zone_contract():
    summary = consumer_sentiment.build_summary(_v2_points())

    for key in (
        "version",
        "evidence_state",
        "evidence_explanation",
        "willingness_read",
        "component_comparison",
    ):
        assert key not in summary
    for key in ("aggregate", "expectations", "current_conditions"):
        assert "zone" not in summary[key]


def test_summary_marks_percentile_unavailable_with_short_history():
    summary = consumer_sentiment.build_summary(_full_points())

    for key in ("aggregate", "expectations", "current_conditions"):
        assert summary[key]["percentile_rank"] is None
        assert summary[key]["percentile_label"] == "Unavailable"
        assert summary[key]["percentile_zone"] == "percentile_unavailable"
    assert summary["primary_signal"]["headline"] == (
        "Primary sentiment percentile is unavailable."
    )
    assert summary["confirmation"]["state"] == "unavailable"


@pytest.mark.parametrize(
    (
        "aggregate_zone",
        "expectations_zone",
        "current_zone",
        "state",
        "aggregate_confirms",
        "current_confirms",
    ),
    [
        ("depressed", "depressed", "depressed", "broadly_confirmed", True, True),
        ("depressed", "depressed", "typical", "aggregate_confirms", True, False),
        (
            "typical",
            "depressed",
            "depressed",
            "current_conditions_confirms",
            False,
            True,
        ),
        ("typical", "depressed", "elevated", "divergent", False, False),
    ],
)
def test_confirmation_requires_exact_primary_zone(
    aggregate_zone,
    expectations_zone,
    current_zone,
    state,
    aggregate_confirms,
    current_confirms,
):
    aggregate = {"percentile_zone": aggregate_zone}
    expectations = {"percentile_zone": expectations_zone}
    current = {"percentile_zone": current_zone}

    result = consumer_sentiment._confirmation(aggregate, expectations, current, True)

    assert result == {
        "state": state,
        "aggregate_confirms": aggregate_confirms,
        "current_conditions_confirms": current_confirms,
    }


def test_confirmation_is_unavailable_for_mixed_periods():
    metric = {"percentile_zone": "depressed"}

    result = consumer_sentiment._confirmation(metric, metric, metric, False)

    assert result == {
        "state": "unavailable",
        "aggregate_confirms": None,
        "current_conditions_confirms": None,
    }


def test_primary_signal_uses_expectations_zone_and_momentum():
    expectations = {
        "percentile_zone": "depressed",
        "percentile_label": "8th percentile",
        "momentum": "weakening",
        "point_change": -4.0,
    }

    result = consumer_sentiment._primary_signal(expectations)

    assert result == {
        "series_id": "umcsi_expectations",
        "percentile_zone": "depressed",
        "momentum": "weakening",
        "headline": "Depressed \u00b7 Weakening",
    }


@pytest.mark.parametrize(
    ("debt_service", "real_rate", "expected"),
    [
        ("falling", "falling", "easing"),
        ("rising", "rising", "tightening"),
        ("unchanged", "unchanged", "unchanged"),
        ("falling", "rising", "mixed"),
        ("unchanged", "falling", "mixed"),
        ("unavailable", "falling", "unavailable"),
    ],
)
def test_ability_financing_requires_matching_available_states(
    debt_service, real_rate, expected
):
    interpretations = [
        {
            "series_id": "household_debt_service_ratio",
            "direction": debt_service,
            "available": debt_service != "unavailable",
        },
        {
            "series_id": "real_10y_rate",
            "direction": real_rate,
            "available": real_rate != "unavailable",
        },
        {
            "series_id": "household_debt_to_gdp",
            "direction": "rising",
            "available": True,
        },
        {
            "series_id": "personal_saving_rate",
            "direction": "unchanged",
            "available": True,
        },
    ]

    result = consumer_sentiment._ability_read(interpretations)

    assert result["financing"]["state"] == expected
    assert result["leverage"]["state"] == "rising"
    assert result["saving"]["state"] == "unchanged"
    assert "mortgage" not in str(result).lower()


def test_point_change():
    pts = _full_points(agg_values=(75.0, 78.0))
    summary = consumer_sentiment.build_summary(pts)
    assert summary["aggregate"]["point_change"] == 3.0


def test_point_change_missing_prior():
    pts = _full_points(agg_values=(78.0,))
    summary = consumer_sentiment.build_summary(pts)
    assert summary["aggregate"]["point_change"] is None


def test_large_expectations_decline_true():
    pts = _full_points(exp_values=(85.0, 70.0))
    summary = consumer_sentiment.build_summary(pts)
    assert summary["large_expectations_decline"] is True


def test_large_expectations_decline_false_at_minus_10():
    pts = _full_points(exp_values=(85.0, 75.0))
    summary = consumer_sentiment.build_summary(pts)
    assert summary["large_expectations_decline"] is False


def test_large_expectations_decline_false_positive_change():
    pts = _full_points(exp_values=(75.0, 85.0))
    summary = consumer_sentiment.build_summary(pts)
    assert summary["large_expectations_decline"] is False


def test_data_status_aligned_period():
    pts = _full_points()
    summary = consumer_sentiment.build_summary(pts)
    assert summary["data_status"] == "aligned_period"


def test_data_status_mixed_periods():
    pts = _full_points()
    pts["umcsi_aggregate"] = _points((75.0, 78.0), "2026-05-01")
    pts["umcsi_expectations"] = _points((80.0, 85.0), "2026-04-01")
    pts["umcsi_current_conditions"] = _points((70.0, 72.0), "2026-05-01")
    summary = consumer_sentiment.build_summary(pts)
    assert summary["data_status"] == "mixed_periods"


def test_data_status_missing():
    pts = _full_points()
    pts["umcsi_aggregate"] = []
    summary = consumer_sentiment.build_summary(pts)
    assert summary["data_status"] == "missing"


def test_data_status_missing_when_current_conditions_missing():
    pts = _full_points()
    pts["umcsi_current_conditions"] = []
    summary = consumer_sentiment.build_summary(pts)
    assert summary["data_status"] == "missing"


def test_capacity_completeness_complete():
    pts = _full_points()
    summary = consumer_sentiment.build_summary(pts)
    assert summary["capacity_completeness"] == "complete"


def test_capacity_completeness_partial():
    pts = _full_points()
    pts["household_debt_to_gdp"] = []
    summary = consumer_sentiment.build_summary(pts)
    assert summary["capacity_completeness"] == "partial"


def test_capacity_completeness_missing():
    pts = _full_points()
    for sid in consumer_sentiment.CAPACITY_SERIES_IDS:
        pts[sid] = []
    summary = consumer_sentiment.build_summary(pts)
    assert summary["capacity_completeness"] == "missing"


def test_summary_includes_provenance():
    pts = _full_points()
    summary = consumer_sentiment.build_summary(pts)
    assert summary["aggregate"]["source"] == "test"
    assert summary["expectations"]["source"] == "test"


def test_summary_has_required_fields():
    pts = _full_points()
    summary = consumer_sentiment.build_summary(pts)
    assert summary["method_version"] == 2
    assert "as_of" in summary
    assert "data_status" in summary
    assert "primary_signal" in summary
    assert "confirmation" in summary
    assert "aggregate" in summary
    assert "expectations" in summary
    assert "current_conditions" in summary
    assert "large_expectations_decline" in summary
    assert "capacity_completeness" in summary
    assert "capacity_as_of" in summary
    assert "ability_read" in summary
    assert "reasons" in summary
    assert "source_latest_final_month" in summary
    assert "method_version" not in summary.get("version", "")
    assert "evidence_state" not in summary


def test_detail_includes_history():
    pts = _full_points()
    detail = consumer_sentiment.build_detail(pts)
    assert "history" in detail
    assert "umcsi_aggregate" in detail["history"]
    assert "umcsi_expectations" in detail["history"]
    assert "umcsi_current_conditions" in detail["history"]


def test_detail_includes_point_changes():
    pts = _full_points(agg_values=(75.0, 78.0, 80.0))
    detail = consumer_sentiment.build_detail(pts)
    assert "point_changes" in detail
    assert len(detail["point_changes"]["umcsi_aggregate"]) == 2
    assert detail["point_changes"]["umcsi_aggregate"][0]["point_change"] == 3.0


def test_detail_includes_capacity():
    pts = _full_points()
    detail = consumer_sentiment.build_detail(pts)
    assert "capacity" in detail
    for sid in consumer_sentiment.CAPACITY_SERIES_IDS:
        assert sid in detail["capacity"]


def test_detail_no_gdp_forecast_or_sp_fields():
    pts = _full_points()
    detail = consumer_sentiment.build_detail(pts)
    detail_str = str(detail)
    assert "gdp_forecast" not in detail_str.lower()
    assert "sp500" not in detail_str.lower()
    assert "s&p" not in detail_str.lower()


def test_capacity_values_report_raw_context():
    pts = _full_points()
    detail = consumer_sentiment.build_detail(pts)
    cap = detail["capacity"]["household_debt_to_gdp"]
    assert len(cap) == 1
    assert cap[0]["value"] == 80.0


def test_aligned_month_in_summary():
    pts = _full_points()
    summary = consumer_sentiment.build_summary(pts)
    assert summary["aligned_month"] == "2026-06-01"


def test_aligned_month_none_when_mixed():
    pts = _full_points()
    pts["umcsi_expectations"] = _points((80.0, 85.0), "2026-04-01")
    summary = consumer_sentiment.build_summary(pts)
    assert summary["aligned_month"] is None


def test_reasons_for_missing_data():
    pts = _full_points()
    pts["umcsi_aggregate"] = []
    summary = consumer_sentiment.build_summary(pts)
    assert any("sentiment data is missing" in r for r in summary["reasons"])


def test_detail_includes_percentile_windows():
    pts = _full_points()
    detail = consumer_sentiment.build_detail(pts)
    assert "percentile_windows" in detail
    for key in ("aggregate", "expectations", "current_conditions"):
        win = detail["percentile_windows"][key]
        assert "start" in win
        assert "end" in win
        assert "observation_count" in win


def test_capacity_read_is_factual_prose_without_mortgage_conclusion():
    points = _full_points()
    points["household_debt_to_gdp"] = [
        {"date": "2025-01-01", "value": 79.0, "source": "test"},
        {"date": "2025-04-01", "value": 80.0, "source": "test"},
    ]
    points["household_debt_service_ratio"] = [
        {"date": "2025-12-01", "value": 10.0, "source": "test"},
        {"date": "2026-03-01", "value": 9.8, "source": "test"},
    ]
    points["personal_saving_rate"] = [
        {"date": "2026-05-01", "value": 7.5, "source": "test"},
        {"date": "2026-06-01", "value": 7.5, "source": "test"},
    ]
    real_rate = [
        {"date": "2026-05-01", "value": 1.5},
        {"date": "2026-06-01", "value": 1.2},
    ]

    read = consumer_sentiment.build_summary(points, real_rate_points=real_rate)[
        "capacity_evidence"
    ]

    assert read["headline"] == "Capacity evidence points in different directions."
    assert read["explanation"] == (
        "Debt-service burden and real financing conditions eased, while "
        "household leverage rose; saving was unchanged."
    )
    combined = f"{read['headline']} {read['explanation']}".lower()
    assert "mortgage" not in combined
    for unsupported in ("score", "supportive", "constraining", "manageable"):
        assert unsupported not in combined


def test_capacity_read_partial_names_incomplete_inputs():
    points = _sentiment_only_points()
    points["personal_saving_rate"] = [
        {"date": "2026-05-01", "value": 7.0, "source": "test"},
        {"date": "2026-06-01", "value": 7.5, "source": "test"},
    ]

    read = consumer_sentiment.build_summary(points)["capacity_evidence"]

    assert read["headline"] == "Capacity evidence is incomplete."
    assert read["explanation"] == (
        "Greater saving indicates near-term spending caution with a larger "
        "financial buffer. Some capacity inputs are unavailable."
    )


def test_capacity_read_missing_cannot_assess_ability():
    read = consumer_sentiment.build_summary(_sentiment_only_points())[
        "capacity_evidence"
    ]

    assert read["headline"] == (
        "Ability to spend cannot be assessed from the available capacity data."
    )
    assert read["explanation"] == ""


def test_capacity_read_with_only_directional_real_rate_is_incomplete():
    read = consumer_sentiment.build_summary(
        _sentiment_only_points(),
        real_rate_points=[
            {"date": "2026-05-01", "value": 1.5},
            {"date": "2026-06-01", "value": 1.2},
        ],
    )["capacity_evidence"]

    assert read["headline"] == "Capacity evidence is incomplete."
    assert read["explanation"] == (
        "Real financing conditions eased. Some capacity inputs are unavailable."
    )


def test_capacity_read_with_single_real_rate_preserves_direction_warning():
    read = consumer_sentiment.build_summary(
        _sentiment_only_points(),
        real_rate_points=[{"date": "2026-06-01", "value": 1.2}],
    )["capacity_evidence"]

    assert read["headline"] == "Capacity evidence is incomplete."
    assert "direction cannot be determined" in read["explanation"]
    assert "Some capacity inputs are unavailable." in read["explanation"]


def test_capacity_evidence_in_summary():
    pts = _full_points()
    summary = consumer_sentiment.build_summary(pts)
    assert "capacity_evidence" in summary
    assert "headline" in summary["capacity_evidence"]
    assert "explanation" in summary["capacity_evidence"]
    assert "drivers" in summary["capacity_evidence"]


def test_capacity_read_includes_real_rate_when_capacity_missing():
    pts = _full_points()
    for sid in consumer_sentiment.CAPACITY_SERIES_IDS:
        pts[sid] = []
    real_rate = [
        {"date": "2026-05-01", "value": 1.5, "treasury_10y": 4.5, "cpi_yoy": 3.0},
        {"date": "2026-06-01", "value": 1.2, "treasury_10y": 4.2, "cpi_yoy": 3.0},
    ]
    read = consumer_sentiment.build_summary(pts, real_rate_points=real_rate)[
        "capacity_evidence"
    ]
    assert read["explanation"] == (
        "Real financing conditions eased. Some capacity inputs are unavailable."
    )
    assert "unavailable" not in read["headline"].lower()
    assert "eased" in read["explanation"]


def test_capacity_driver_labels_are_stable():
    summary = consumer_sentiment.build_summary(_full_points())
    labels_by_id = {
        driver["series_id"]: driver["label"]
        for driver in summary["capacity_evidence"]["drivers"]
    }
    assert labels_by_id == {
        "household_debt_to_gdp": "Household Debt/GDP",
        "household_debt_service_ratio": "Debt Service Ratio",
        "personal_saving_rate": "Personal Saving Rate",
        "one_to_four_family_mortgage_liabilities": "Mortgage Liabilities",
        "real_10y_rate": "Real 10Y Rate",
    }


@pytest.mark.parametrize(
    ("dsr_points", "real_rate_points", "dsr_state", "real_rate_state"),
    [
        (
            [_capacity_point(9.0), _capacity_point(10.0)],
            [
                {"date": "2026-05-01", "value": 1.0},
                {"date": "2026-06-01", "value": 1.5},
            ],
            "rising",
            "rising",
        ),
        (
            [_capacity_point(10.0), _capacity_point(9.0)],
            [
                {"date": "2026-05-01", "value": 1.5},
                {"date": "2026-06-01", "value": 1.0},
            ],
            "falling",
            "falling",
        ),
        (
            [_capacity_point(9.0), _capacity_point(9.0)],
            [
                {"date": "2026-05-01", "value": 1.0},
                {"date": "2026-06-01", "value": 1.0},
            ],
            "unchanged",
            "unchanged",
        ),
        (
            [_capacity_point(9.0)],
            [{"date": "2026-06-01", "value": 1.0}],
            "direction unavailable",
            "direction unavailable",
        ),
        ([], [], "data unavailable", "data unavailable"),
    ],
)
def test_mortgage_context_reports_dsr_and_real_rate_states_without_health_judgment(
    dsr_points, real_rate_points, dsr_state, real_rate_state
):
    pts = _full_points()
    pts["household_debt_service_ratio"] = dsr_points
    pts["one_to_four_family_mortgage_liabilities"] = [
        _capacity_point(11000000.0),
        _capacity_point(12000000.0),
    ]
    summary = consumer_sentiment.build_summary(pts, real_rate_points=real_rate_points)
    mortgage = next(
        driver
        for driver in summary["capacity_evidence"]["drivers"]
        if driver["series_id"] == "one_to_four_family_mortgage_liabilities"
    )
    assert mortgage["label"] == "Mortgage Liabilities"
    assert mortgage["interpretation"].startswith("Rising mortgage liabilities.")
    assert "Scale context only" in mortgage["interpretation"]
    assert f"Debt Service Ratio: {dsr_state}" in mortgage["context_interpretation"]
    assert f"Real 10Y Rate: {real_rate_state}" in mortgage["context_interpretation"]
    context = mortgage["context_interpretation"].lower()
    assert "supportive" not in context
    assert "constraining" not in context
    assert "manageable" not in context
    assert "offset" not in context


def test_capacity_interpretations_in_detail():
    pts = _full_points()
    detail = consumer_sentiment.build_detail(pts)
    assert "capacity_interpretations" in detail
    interpretations = detail["capacity_interpretations"]
    assert len(interpretations) == len(consumer_sentiment.CAPACITY_SERIES_IDS) + 1


def test_capacity_interpretation_household_debt_rising():
    pts = _full_points()
    pts["household_debt_to_gdp"] = [
        {"date": "2026-03-01", "value": 78.0, "source": "test"},
        {"date": "2026-06-01", "value": 80.0, "source": "test"},
    ]
    interpretations = consumer_sentiment._capacity_interpretations(pts, [])
    hd = next(i for i in interpretations if i["series_id"] == "household_debt_to_gdp")
    assert "increasing leverage" in hd["interpretation"].lower()


def test_capacity_interpretation_household_debt_falling():
    pts = _full_points()
    pts["household_debt_to_gdp"] = [
        {"date": "2026-03-01", "value": 80.0, "source": "test"},
        {"date": "2026-06-01", "value": 78.0, "source": "test"},
    ]
    interpretations = consumer_sentiment._capacity_interpretations(pts, [])
    hd = next(i for i in interpretations if i["series_id"] == "household_debt_to_gdp")
    assert "declining leverage" in hd["interpretation"].lower()


def test_capacity_interpretation_saving_rate_rising():
    pts = _full_points()
    pts["personal_saving_rate"] = [
        {"date": "2026-03-01", "value": 6.0, "source": "test"},
        {"date": "2026-06-01", "value": 7.5, "source": "test"},
    ]
    interpretations = consumer_sentiment._capacity_interpretations(pts, [])
    sr = next(i for i in interpretations if i["series_id"] == "personal_saving_rate")
    assert "greater thrift" in sr["interpretation"].lower()
    assert "spending caution" in sr["interpretation"].lower()
    assert "larger financial buffer" in sr["interpretation"].lower()


def test_capacity_interpretation_saving_rate_falling():
    pts = _full_points()
    pts["personal_saving_rate"] = [
        {"date": "2026-03-01", "value": 7.5, "source": "test"},
        {"date": "2026-06-01", "value": 6.0, "source": "test"},
    ]
    interpretations = consumer_sentiment._capacity_interpretations(pts, [])
    sr = next(i for i in interpretations if i["series_id"] == "personal_saving_rate")
    assert "less thrift" in sr["interpretation"].lower()
    assert "spending support" in sr["interpretation"].lower()
    assert "smaller financial buffer" in sr["interpretation"].lower()


def test_capacity_interpretation_mortgage_liabilities_no_standalone_conclusion():
    pts = _full_points()
    pts["one_to_four_family_mortgage_liabilities"] = [
        {"date": "2026-03-01", "value": 11000000.0, "source": "test"},
        {"date": "2026-06-01", "value": 12000000.0, "source": "test"},
    ]
    interpretations = consumer_sentiment._capacity_interpretations(pts, [])
    ml = next(
        i
        for i in interpretations
        if i["series_id"] == "one_to_four_family_mortgage_liabilities"
    )
    assert "scale context" in ml["interpretation"].lower()
    assert "supportive" not in ml["interpretation"].lower()
    assert "constraining" not in ml["interpretation"].lower()
    assert (
        "rising" in ml["interpretation"].lower()
        or "declining" in ml["interpretation"].lower()
    )


def test_capacity_interpretation_real_rate_easing():
    real_rate = [
        {"date": "2026-05-01", "value": 1.5, "treasury_10y": 4.5, "cpi_yoy": 3.0},
        {"date": "2026-06-01", "value": 1.2, "treasury_10y": 4.2, "cpi_yoy": 3.0},
    ]
    interpretations = consumer_sentiment._capacity_interpretations({}, real_rate)
    rr = next(i for i in interpretations if i["series_id"] == "real_10y_rate")
    assert "easing" in rr["interpretation"].lower()


def test_capacity_interpretation_real_rate_tightening():
    real_rate = [
        {"date": "2026-05-01", "value": 1.2, "treasury_10y": 4.2, "cpi_yoy": 3.0},
        {"date": "2026-06-01", "value": 1.5, "treasury_10y": 4.5, "cpi_yoy": 3.0},
    ]
    interpretations = consumer_sentiment._capacity_interpretations({}, real_rate)
    rr = next(i for i in interpretations if i["series_id"] == "real_10y_rate")
    assert "tightening" in rr["interpretation"].lower()


def test_real_rate_single_observation_available_no_direction():
    pts = _full_points()
    real_rate = [
        {"date": "2026-06-01", "value": 1.2, "treasury_10y": 4.2, "cpi_yoy": 3.0}
    ]
    interpretations = consumer_sentiment._capacity_interpretations(pts, real_rate)
    rr = next(i for i in interpretations if i["series_id"] == "real_10y_rate")
    assert rr["available"] is True
    assert rr["has_direction"] is False
    assert "direction cannot be determined" in rr["interpretation"].lower()


def test_real_rate_zero_observations_unavailable():
    pts = _full_points()
    interpretations = consumer_sentiment._capacity_interpretations(pts, [])
    rr = next(i for i in interpretations if i["series_id"] == "real_10y_rate")
    assert rr["available"] is False
    assert rr["has_direction"] is False
    assert "unavailable" in rr["interpretation"].lower()
    assert "unchanged" not in rr["interpretation"].lower()


def test_capacity_completeness_independent_from_dates():
    pts = _full_points()
    summary = consumer_sentiment.build_summary(pts)
    assert summary["capacity_completeness"] == "complete"


def test_household_debt_gdp_quarter_note():
    note = consumer_sentiment._household_debt_gdp_quarter_note(
        [{"date": "2025-04-01", "value": 80.0, "source": "test"}]
    )
    assert note is not None
    assert "Q2 2025" in note
    assert "does not represent the current quarter" in note


def test_household_debt_gdp_quarter_note_advances_automatically():
    note = consumer_sentiment._household_debt_gdp_quarter_note(
        [{"date": "2025-10-01", "value": 80.0, "source": "test"}]
    )
    assert note is not None
    assert "Q4 2025" in note
    assert "does not represent the current quarter" in note


def test_household_debt_gdp_quarter_note_none_when_missing():
    assert consumer_sentiment._household_debt_gdp_quarter_note([]) is None


def test_household_debt_gdp_explicitly_lagged():
    pts = _full_points()
    detail = consumer_sentiment.build_detail(pts)
    note = detail["household_debt_gdp_quarter_note"]
    assert note is not None
    assert "lag" in note.lower()
    assert "does not represent the current quarter" in note.lower()


def test_data_status_mixed_periods_not_aligned():
    pts = _full_points()
    pts["umcsi_aggregate"] = _points((75.0, 78.0), "2026-05-01")
    pts["umcsi_expectations"] = _points((80.0, 85.0), "2026-04-01")
    pts["umcsi_current_conditions"] = _points((70.0, 72.0), "2026-05-01")
    summary = consumer_sentiment.build_summary(pts)
    assert summary["data_status"] == "mixed_periods"
    assert summary["aligned_month"] is None


def test_ability_read_in_summary():
    pts = _full_points()
    summary = consumer_sentiment.build_summary(pts)
    assert "ability_read" in summary
    assert "financing" in summary["ability_read"]
    assert "leverage" in summary["ability_read"]
    assert "saving" in summary["ability_read"]


def test_ability_read_financing_state_when_data_available():
    pts = _full_points()
    pts["household_debt_service_ratio"] = [
        {"date": "2026-05-01", "value": 10.0, "source": "test"},
        {"date": "2026-06-01", "value": 9.8, "source": "test"},
    ]
    real_rate = [
        {"date": "2026-05-01", "value": 1.5},
        {"date": "2026-06-01", "value": 1.2},
    ]
    summary = consumer_sentiment.build_summary(pts, real_rate_points=real_rate)
    assert summary["ability_read"]["financing"]["state"] in (
        "easing",
        "tightening",
        "mixed",
        "unavailable",
    )

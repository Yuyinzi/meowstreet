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


def test_aggregate_zone_bullish():
    pts = _full_points(agg_values=(85.0, 82.0))
    summary = consumer_sentiment.build_summary(pts)
    assert summary["aggregate"]["zone"] == "bullish"
    assert summary["aggregate"]["value"] == 82.0


def test_aggregate_zone_benign():
    pts = _full_points(agg_values=(72.0, 75.5))
    summary = consumer_sentiment.build_summary(pts)
    assert summary["aggregate"]["zone"] == "benign"


def test_aggregate_zone_bearish():
    pts = _full_points(agg_values=(60.0, 65.0))
    summary = consumer_sentiment.build_summary(pts)
    assert summary["aggregate"]["zone"] == "bearish"


def test_aggregate_zone_ambiguous_at_70():
    pts = _full_points(agg_values=(70.0, 70.0))
    summary = consumer_sentiment.build_summary(pts)
    assert summary["aggregate"]["zone"] == "ambiguous"


def test_aggregate_zone_ambiguous_below_55():
    pts = _full_points(agg_values=(54.0, 50.0))
    summary = consumer_sentiment.build_summary(pts)
    assert summary["aggregate"]["zone"] == "ambiguous"


def test_expectations_zone_peak():
    pts = _full_points(exp_values=(100.0, 105.0))
    summary = consumer_sentiment.build_summary(pts)
    assert summary["expectations"]["zone"] == "peak"


def test_expectations_zone_steady_growth():
    pts = _full_points(exp_values=(75.0, 80.0))
    summary = consumer_sentiment.build_summary(pts)
    assert summary["expectations"]["zone"] == "steady_growth"


def test_expectations_zone_trough():
    pts = _full_points(exp_values=(60.0, 65.0))
    summary = consumer_sentiment.build_summary(pts)
    assert summary["expectations"]["zone"] == "trough"


def test_expectations_zone_ambiguous_at_70():
    pts = _full_points(exp_values=(70.0, 70.0))
    summary = consumer_sentiment.build_summary(pts)
    assert summary["expectations"]["zone"] == "ambiguous"


def test_expectations_zone_ambiguous_between_90_and_95():
    pts = _full_points(exp_values=(92.0, 93.0))
    summary = consumer_sentiment.build_summary(pts)
    assert summary["expectations"]["zone"] == "ambiguous"


def test_expectations_zone_ambiguous_above_110():
    pts = _full_points(exp_values=(112.0, 115.0))
    summary = consumer_sentiment.build_summary(pts)
    assert summary["expectations"]["zone"] == "ambiguous"


def test_evidence_state_supportive():
    pts = _full_points(agg_values=(75.0, 82.0), exp_values=(80.0, 85.0))
    summary = consumer_sentiment.build_summary(pts)
    assert summary["evidence_state"] == "supportive"


def test_evidence_state_adverse():
    pts = _full_points(agg_values=(60.0, 65.0), exp_values=(58.0, 62.0))
    summary = consumer_sentiment.build_summary(pts)
    assert summary["evidence_state"] == "adverse"


def test_evidence_state_conflicting_bullish_aggregate_trough_expectations():
    pts = _full_points(agg_values=(85.0, 82.0), exp_values=(60.0, 65.0))
    summary = consumer_sentiment.build_summary(pts)
    assert summary["evidence_state"] == "conflicting"


def test_evidence_state_conflicting_bearish_aggregate_peak_expectations():
    pts = _full_points(agg_values=(60.0, 58.0), exp_values=(100.0, 105.0))
    summary = consumer_sentiment.build_summary(pts)
    assert summary["evidence_state"] == "conflicting"


def test_evidence_state_ambiguous():
    pts = _full_points(agg_values=(70.0, 70.0), exp_values=(80.0, 85.0))
    summary = consumer_sentiment.build_summary(pts)
    assert summary["evidence_state"] == "ambiguous"


def test_evidence_state_insufficient_data_missing_aggregate():
    pts = _full_points()
    pts["umcsi_aggregate"] = []
    summary = consumer_sentiment.build_summary(pts)
    assert summary["evidence_state"] == "insufficient_data"


def test_evidence_state_insufficient_data_missing_expectations():
    pts = _full_points()
    pts["umcsi_expectations"] = []
    summary = consumer_sentiment.build_summary(pts)
    assert summary["evidence_state"] == "insufficient_data"


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


def test_data_status_current():
    pts = _full_points()
    summary = consumer_sentiment.build_summary(pts)
    assert summary["data_status"] == "current"


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


def test_current_conditions_no_zone():
    pts = _full_points()
    summary = consumer_sentiment.build_summary(pts)
    assert "zone" not in summary["current_conditions"]


def test_summary_includes_provenance():
    pts = _full_points()
    summary = consumer_sentiment.build_summary(pts)
    assert summary["aggregate"]["source"] == "University of Michigan Table 1"
    assert summary["expectations"]["source"] == "University of Michigan Table 5"


def test_summary_has_required_fields():
    pts = _full_points()
    summary = consumer_sentiment.build_summary(pts)
    assert "version" in summary
    assert "as_of" in summary
    assert "data_status" in summary
    assert "evidence_state" in summary
    assert "aggregate" in summary
    assert "expectations" in summary
    assert "current_conditions" in summary
    assert "large_expectations_decline" in summary
    assert "capacity_completeness" in summary
    assert "capacity_as_of" in summary
    assert "reasons" in summary
    assert "source_latest_final_month" in summary


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


def test_evidence_state_insufficient_when_mixed_periods():
    pts = _full_points()
    pts["umcsi_expectations"] = _points((80.0,), "2026-04-01")
    summary = consumer_sentiment.build_summary(pts)
    assert summary["evidence_state"] == "insufficient_data"


def test_reasons_for_missing_data():
    pts = _full_points()
    pts["umcsi_aggregate"] = []
    summary = consumer_sentiment.build_summary(pts)
    assert any("aggregate sentiment is missing" in r for r in summary["reasons"])

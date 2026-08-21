from datetime import date, timedelta

import pytest

from app.tools import cot_historical_extremes as extremes

ACTIVE_ENTRY = {
    "commodity_id": "crude_oil_wti",
    "market_name": "CRUDE OIL, LIGHT SWEET-WTI - ICE FUTURES EUROPE",
    "contract_code": "067411",
    "active": True,
    "reason": None,
}

INACTIVE_ENTRY = {
    "commodity_id": "crude_oil_wti",
    "market_name": "CRUDE OIL, LIGHT SWEET-WTI - ICE FUTURES EUROPE",
    "contract_code": None,
    "active": False,
    "reason": "unsupported_contract",
}


def _observation(report_date, longs, shorts, **overrides):
    row = {
        "commodity_id": "crude_oil_wti",
        "report_date": report_date,
        "cftc_contract_market_code": "067411",
        "report_type": "disaggregated_futures_only",
        "position_category": "managed_money",
        "manager_longs": longs,
        "manager_shorts": shorts,
        "open_interest": longs + shorts,
    }
    row.update(overrides)
    return row


def _weekly_history(count=300, net_fn=None, start="2021-01-05"):
    rows = []
    day = date.fromisoformat(start)
    for index in range(count):
        net = net_fn(index) if net_fn else 200000 - index
        shorts = 20000
        longs = shorts + net
        rows.append(_observation(day.isoformat(), longs, shorts))
        day += timedelta(days=7)
    return rows


def _latest_date(rows):
    return max(row["report_date"] for row in rows)


def _weekly_history_with_publication(count=300, net_fn=None):
    rows = _weekly_history(count=count, net_fn=net_fn)
    for row in rows:
        row["publication_date"] = (
            date.fromisoformat(row["report_date"]) + timedelta(days=3)
        ).isoformat()
    return rows


def _after_latest(rows, days):
    return (date.fromisoformat(_latest_date(rows)) + timedelta(days=days)).isoformat()


def test_historical_high_when_latest_is_maximum():
    rows = _weekly_history(net_fn=lambda index: 100000 + index)
    result = extremes.evaluate(
        "crude_oil_wti", ACTIVE_ENTRY, rows, _after_latest(rows, 3)
    )

    assert result["status"] == "historical_high"
    assert result["latest_net_position"] == max(
        int(r["manager_longs"]) - int(r["manager_shorts"]) for r in rows
    )
    assert result["valid_observation_count"] == 300
    assert result["history_has_gaps"] is False


def test_recurring_historical_high_reports_tie_without_changing_status():
    rows = _weekly_history(net_fn=lambda index: 100000 + min(index, 298))
    result = extremes.evaluate(
        "crude_oil_wti", ACTIVE_ENTRY, rows, _after_latest(rows, 3)
    )

    assert result["status"] == "historical_high"
    assert result["latest_net_tie_count"] == 2


def test_historical_low_when_latest_is_minimum():
    rows = _weekly_history(net_fn=lambda index: 100000 - index)
    result = extremes.evaluate(
        "crude_oil_wti", ACTIVE_ENTRY, rows, _after_latest(rows, 3)
    )

    assert result["status"] == "historical_low"
    assert result["latest_net_position"] == min(
        int(r["manager_longs"]) - int(r["manager_shorts"]) for r in rows
    )


def test_not_extreme_when_latest_is_mid_range():
    rows = _weekly_history(net_fn=lambda index: 100000 + (index % 40))
    result = extremes.evaluate(
        "crude_oil_wti", ACTIVE_ENTRY, rows, _after_latest(rows, 3)
    )

    assert result["status"] == "not_extreme"


def test_zero_range_history_is_unavailable():
    rows = _weekly_history(net_fn=lambda index: 100000)
    result = extremes.evaluate(
        "crude_oil_wti", ACTIVE_ENTRY, rows, _after_latest(rows, 3)
    )

    assert result["status"] == "unavailable"
    assert result["reason_code"] == "zero_range_history"


def test_insufficient_history_below_260_reports():
    rows = _weekly_history(count=259)
    result = extremes.evaluate(
        "crude_oil_wti", ACTIVE_ENTRY, rows, _after_latest(rows, 3)
    )

    assert result["status"] == "unavailable"
    assert result["reason_code"] == "insufficient_history"


def test_insufficient_history_under_five_calendar_year_span():
    rows = _weekly_history(count=260)
    result = extremes.evaluate(
        "crude_oil_wti", ACTIVE_ENTRY, rows, _after_latest(rows, 3)
    )

    assert result["status"] == "unavailable"
    assert result["reason_code"] == "insufficient_history"


def test_stale_latest_report_at_15_days():
    rows = _weekly_history(count=300)
    result = extremes.evaluate(
        "crude_oil_wti", ACTIVE_ENTRY, rows, _after_latest(rows, 15)
    )

    assert result["status"] == "unavailable"
    assert result["reason_code"] == "stale_latest_report"


def test_skipped_week_within_14_days_is_missing_latest_report():
    rows = _weekly_history(net_fn=lambda index: 100000 + index)
    result = extremes.evaluate(
        "crude_oil_wti", ACTIVE_ENTRY, rows, _after_latest(rows, 14)
    )

    assert result["status"] == "unavailable"
    assert result["reason_code"] == "missing_latest_report"


def test_missing_expected_latest_report_is_unavailable():
    rows = _weekly_history(net_fn=lambda index: 100000 + index)
    del rows[-1]
    latest_date = date.fromisoformat(max(row["report_date"] for row in rows))
    observation_date = (latest_date + timedelta(days=10)).isoformat()

    result = extremes.evaluate("crude_oil_wti", ACTIVE_ENTRY, rows, observation_date)

    assert result["status"] == "unavailable"
    assert result["reason_code"] == "missing_latest_report"
    assert result["valid_observation_count"] == 299


def test_report_type_missing_is_unavailable():
    rows = _weekly_history(net_fn=lambda index: 100000 + index)
    rows.append(_observation("2024-06-04", 50000, 40000, report_type=""))

    result = extremes.evaluate(
        "crude_oil_wti", ACTIVE_ENTRY, rows, _after_latest(rows, 3)
    )

    assert result["status"] == "unavailable"
    assert result["reason_code"] == "report_definition_changed"


def test_position_category_missing_is_unavailable():
    rows = _weekly_history(net_fn=lambda index: 100000 + index)
    rows.append(_observation("2024-06-04", 50000, 40000, position_category=None))

    result = extremes.evaluate(
        "crude_oil_wti", ACTIVE_ENTRY, rows, _after_latest(rows, 3)
    )

    assert result["status"] == "unavailable"
    assert result["reason_code"] == "report_definition_changed"


def test_net_position_uses_raw_longs_minus_shorts_without_rounding():
    rows = _weekly_history(net_fn=lambda index: 100000 + index)
    rows[-1]["manager_longs"] = 120299.5
    rows[-1]["manager_shorts"] = 20000.25

    result = extremes.evaluate(
        "crude_oil_wti", ACTIVE_ENTRY, rows, _after_latest(rows, 3)
    )

    assert result["status"] == "historical_high"
    assert result["latest_net_position"] == 100299.25


def test_publication_lag_keeps_latest_report_usable_across_weekday():
    rows = _weekly_history_with_publication(net_fn=lambda index: 100000 + index)
    latest_date = date.fromisoformat(rows[-1]["report_date"])
    observation_date = (latest_date + timedelta(days=9)).isoformat()

    result = extremes.evaluate("crude_oil_wti", ACTIVE_ENTRY, rows, observation_date)

    assert result["status"] == "historical_high"


def test_publication_due_date_without_report_is_missing_latest_report():
    rows = _weekly_history_with_publication(net_fn=lambda index: 100000 + index)
    del rows[-1]
    latest_date = date.fromisoformat(max(row["report_date"] for row in rows))
    observation_date = (latest_date + timedelta(days=10)).isoformat()

    result = extremes.evaluate("crude_oil_wti", ACTIVE_ENTRY, rows, observation_date)

    assert result["status"] == "unavailable"
    assert result["reason_code"] == "missing_latest_report"


def test_future_conflicting_row_does_not_affect_current_result():
    rows = _weekly_history(net_fn=lambda index: 100000 + index)
    observation_date = _after_latest(rows, 3)
    future_date = (
        date.fromisoformat(rows[-1]["report_date"]) + timedelta(days=7)
    ).isoformat()
    rows.append(
        _observation(future_date, 50000, 40000, cftc_contract_market_code="999999")
    )

    result = extremes.evaluate("crude_oil_wti", ACTIVE_ENTRY, rows, observation_date)

    assert result["status"] == "historical_high"
    assert result["valid_observation_count"] == 300


def test_absent_latest_report_is_unavailable():
    result = extremes.evaluate("crude_oil_wti", ACTIVE_ENTRY, [], "2026-08-03")

    assert result["status"] == "unavailable"
    assert result["reason_code"] == "missing_latest_report"


def test_no_report_on_or_before_observation_date_is_unavailable():
    rows = _weekly_history(count=300)
    result = extremes.evaluate("crude_oil_wti", ACTIVE_ENTRY, rows, "2020-01-01")

    assert result["status"] == "unavailable"
    assert result["reason_code"] == "missing_latest_report"


def test_intermediate_gap_sets_history_has_gaps():
    rows = _weekly_history(net_fn=lambda index: 100000 + index)
    del rows[150]
    result = extremes.evaluate(
        "crude_oil_wti", ACTIVE_ENTRY, rows, _after_latest(rows, 3)
    )

    assert result["status"] == "historical_high"
    assert result["history_has_gaps"] is True
    assert result["valid_observation_count"] == 299


def test_null_identity_legacy_row_is_excluded():
    rows = _weekly_history(net_fn=lambda index: 100000 + index)
    legacy = _observation(
        "2024-06-04",
        50000,
        40000,
        cftc_contract_market_code=None,
        position_category=None,
    )
    rows.append(legacy)
    result = extremes.evaluate(
        "crude_oil_wti", ACTIVE_ENTRY, rows, _after_latest(rows, 3)
    )

    assert result["status"] == "historical_high"
    assert result["valid_observation_count"] == 300


def test_contract_code_discontinuity_is_unavailable():
    rows = _weekly_history(net_fn=lambda index: 100000 + index)
    rows.append(
        _observation("2024-06-04", 50000, 40000, cftc_contract_market_code="999999")
    )
    result = extremes.evaluate(
        "crude_oil_wti", ACTIVE_ENTRY, rows, _after_latest(rows, 3)
    )

    assert result["status"] == "unavailable"
    assert result["reason_code"] == "contract_discontinuity"


def test_report_definition_changed_is_unavailable():
    rows = _weekly_history(net_fn=lambda index: 100000 + index)
    rows.append(
        _observation("2024-06-04", 50000, 40000, position_category="commercial")
    )
    result = extremes.evaluate(
        "crude_oil_wti", ACTIVE_ENTRY, rows, _after_latest(rows, 3)
    )

    assert result["status"] == "unavailable"
    assert result["reason_code"] == "report_definition_changed"


def test_missing_manager_positions_on_latest_report():
    rows = _weekly_history(net_fn=lambda index: 100000 + index)
    rows[-1]["manager_shorts"] = None
    result = extremes.evaluate(
        "crude_oil_wti", ACTIVE_ENTRY, rows, _after_latest(rows, 3)
    )

    assert result["status"] == "unavailable"
    assert result["reason_code"] == "missing_manager_positions"


def test_middle_missing_positions_are_excluded_without_filling():
    rows = _weekly_history(net_fn=lambda index: 100000 + index)
    rows[150]["manager_longs"] = None
    rows[150]["manager_shorts"] = None
    result = extremes.evaluate(
        "crude_oil_wti", ACTIVE_ENTRY, rows, _after_latest(rows, 3)
    )

    assert result["status"] == "historical_high"
    assert result["valid_observation_count"] == 299


def test_unsupported_contract_for_missing_entry():
    result = extremes.evaluate("crude_oil_wti", None, [], "2026-08-03")

    assert result["status"] == "unavailable"
    assert result["reason_code"] == "unsupported_contract"


def test_unsupported_contract_for_inactive_entry():
    rows = _weekly_history(net_fn=lambda index: 100000 + index)
    result = extremes.evaluate(
        "crude_oil_wti", INACTIVE_ENTRY, rows, _after_latest(rows, 3)
    )

    assert result["status"] == "unavailable"
    assert result["reason_code"] == "unsupported_contract"


def test_available_result_includes_provenance_fields():
    rows = _weekly_history(net_fn=lambda index: 100000 + index)
    result = extremes.evaluate(
        "crude_oil_wti", ACTIVE_ENTRY, rows, _after_latest(rows, 3)
    )

    assert result["method_version"] == extremes.METHOD_VERSION
    assert result["cftc_contract_market_code"] == "067411"
    assert result["report_type"] == "disaggregated_futures_only"
    assert result["position_category"] == "managed_money"
    assert result["history_start_date"] == "2021-01-05"
    assert result["history_end_date"] == _latest_date(rows)
    assert result["latest_report_date"] == _latest_date(rows)
    assert result["latest_net_position"] is not None


def test_same_inputs_produce_identical_output():
    rows = _weekly_history(net_fn=lambda index: 100000 + index)
    observation_date = _after_latest(rows, 3)

    first = extremes.evaluate("crude_oil_wti", ACTIVE_ENTRY, rows, observation_date)
    second = extremes.evaluate("crude_oil_wti", ACTIVE_ENTRY, rows, observation_date)

    assert first == second


def test_invalid_report_date_is_rejected_strictly():
    rows = _weekly_history(net_fn=lambda index: 100000 + index)
    observation_date = _after_latest(rows, 3)
    rows.append(_observation("not-a-date", 50000, 40000))
    with pytest.raises(ValueError, match="commodities cot report date is invalid"):
        extremes.evaluate("crude_oil_wti", ACTIVE_ENTRY, rows, observation_date)

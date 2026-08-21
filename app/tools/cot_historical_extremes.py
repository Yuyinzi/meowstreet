from datetime import date, timedelta

METHOD_VERSION = "cot_historical_extremes_v1"
DATA_VERSION = "cftc_cot_disaggregated_futures_only_v1"
REPORT_TYPE = "disaggregated_futures_only"
POSITION_CATEGORY = "managed_money"
MIN_VALID_OBSERVATIONS = 260
MIN_SPAN_YEARS = 5
MAX_STALE_DAYS = 14
_WEEKLY_CADENCE_DAYS = 7
_GAP_THRESHOLD_DAYS = 10

_REASON_TEXT = {
    "unsupported_contract": ("contract is not supported by the versioned allowlist"),
    "insufficient_history": (
        "insufficient history: fewer than 260 valid weekly reports spanning "
        "five calendar years"
    ),
    "missing_latest_report": "the latest expected weekly report is missing",
    "missing_manager_positions": "the latest report lacks manager positions",
    "stale_latest_report": "the latest report is more than 14 days old",
    "contract_discontinuity": "contract identity is discontinuous",
    "report_definition_changed": "report definition changed",
    "zero_range_history": "net position has zero range across the history",
}


def evaluate(commodity_id, catalog_entry, observations, observation_date):
    if catalog_entry is None or catalog_entry.get("active") is not True:
        return _unavailable("unsupported_contract", commodity_id, None)
    contract_code = catalog_entry["contract_code"]
    observation_date_parsed = date.fromisoformat(observation_date)

    parsed = []
    for row in observations:
        if row.get("commodity_id") != commodity_id:
            continue
        try:
            report_date = date.fromisoformat(str(row["report_date"]))
        except ValueError as exc:
            raise ValueError(
                f"commodities cot report date is invalid for {commodity_id}"
            ) from exc
        parsed.append((report_date, row))
    parsed.sort(key=lambda item: item[0])

    history = [
        (d, row)
        for d, row in parsed
        if _availability_date(row, d) <= observation_date_parsed
    ]
    if not history:
        return _unavailable("missing_latest_report", commodity_id, contract_code)

    eligible = []
    for d, row in history:
        row_code = str(row.get("cftc_contract_market_code") or "").strip()
        if not row_code:
            continue
        if row_code != contract_code:
            return _unavailable("contract_discontinuity", commodity_id, contract_code)
        row_report = str(row.get("report_type") or "").strip()
        if row_report != REPORT_TYPE:
            return _unavailable(
                "report_definition_changed", commodity_id, contract_code
            )
        row_category = str(row.get("position_category") or "").strip()
        if row_category != POSITION_CATEGORY:
            return _unavailable(
                "report_definition_changed", commodity_id, contract_code
            )
        eligible.append((d, row))

    if not eligible:
        return _unavailable("missing_latest_report", commodity_id, contract_code)

    latest_date, latest_row = eligible[-1]
    if (
        latest_row.get("manager_longs") is None
        or latest_row.get("manager_shorts") is None
    ):
        return _unavailable(
            "missing_manager_positions",
            commodity_id,
            contract_code,
            latest_report_date=latest_date.isoformat(),
        )

    valid = []
    for d, row in eligible:
        if row.get("manager_longs") is None or row.get("manager_shorts") is None:
            continue
        valid.append((d, row))

    if not valid:
        return _unavailable("missing_manager_positions", commodity_id, contract_code)

    latest_date, latest_row = valid[-1]
    if (observation_date_parsed - latest_date).days > MAX_STALE_DAYS:
        return _unavailable(
            "stale_latest_report",
            commodity_id,
            contract_code,
            latest_report_date=latest_date.isoformat(),
            valid_count=len(valid),
        )
    latest_publication_date = _publication_date(latest_row, latest_date)
    next_expected_publication_date = latest_publication_date + timedelta(
        days=_WEEKLY_CADENCE_DAYS
    )
    if next_expected_publication_date <= observation_date_parsed:
        return _unavailable(
            "missing_latest_report",
            commodity_id,
            contract_code,
            latest_report_date=latest_date.isoformat(),
            valid_count=len(valid),
        )

    first_date = valid[0][0]
    if (
        len(valid) < MIN_VALID_OBSERVATIONS
        or _add_years(first_date, MIN_SPAN_YEARS) > latest_date
    ):
        return _unavailable(
            "insufficient_history",
            commodity_id,
            contract_code,
            latest_report_date=latest_date.isoformat(),
            history_start=first_date.isoformat(),
            history_end=latest_date.isoformat(),
            valid_count=len(valid),
        )

    nets = [row["manager_longs"] - row["manager_shorts"] for _, row in valid]
    latest_net = nets[-1]
    history_has_gaps = _has_gaps([d for d, _ in valid])

    if max(nets) == min(nets):
        return _unavailable(
            "zero_range_history",
            commodity_id,
            contract_code,
            latest_report_date=latest_date.isoformat(),
            history_start=first_date.isoformat(),
            history_end=latest_date.isoformat(),
            valid_count=len(valid),
            history_has_gaps=history_has_gaps,
        )
    if latest_net == max(nets):
        status = "historical_high"
    elif latest_net == min(nets):
        status = "historical_low"
    else:
        status = "not_extreme"

    return {
        "method_version": METHOD_VERSION,
        "data_version": DATA_VERSION,
        "commodity_id": commodity_id,
        "status": status,
        "reason_code": None,
        "reason": None,
        "cftc_contract_market_code": contract_code,
        "report_type": REPORT_TYPE,
        "position_category": POSITION_CATEGORY,
        "latest_report_date": latest_date.isoformat(),
        "latest_net_position": latest_net,
        "history_start_date": first_date.isoformat(),
        "history_end_date": latest_date.isoformat(),
        "valid_observation_count": len(valid),
        "history_has_gaps": history_has_gaps,
        "latest_net_tie_count": sum(1 for net in nets if net == latest_net),
    }


def invalid_input_unavailable(commodity_id, catalog_entry, message):
    contract_code = catalog_entry["contract_code"] if catalog_entry else None
    return _unavailable_with_text(commodity_id, contract_code, message)


def _unavailable_with_text(commodity_id, contract_code, message):
    return {
        "method_version": METHOD_VERSION,
        "data_version": DATA_VERSION,
        "commodity_id": commodity_id,
        "status": "unavailable",
        "reason_code": None,
        "reason": message,
        "cftc_contract_market_code": contract_code,
        "report_type": REPORT_TYPE,
        "position_category": POSITION_CATEGORY,
        "latest_report_date": None,
        "latest_net_position": None,
        "history_start_date": None,
        "history_end_date": None,
        "valid_observation_count": None,
        "history_has_gaps": None,
        "latest_net_tie_count": None,
    }


def _add_years(value, years):
    try:
        return value.replace(year=value.year + years)
    except ValueError:
        return value.replace(year=value.year + years, day=28)


def _publication_date(row, report_date):
    raw = str(row.get("publication_date") or "").strip()
    if raw:
        try:
            return date.fromisoformat(raw)
        except ValueError:
            pass
    return report_date


def _availability_date(row, report_date):
    return _publication_date(row, report_date)


def _has_gaps(dates):
    for prior, current in zip(dates, dates[1:]):
        if (current - prior).days > _GAP_THRESHOLD_DAYS:
            return True
    return False


def _unavailable(
    reason_code,
    commodity_id,
    contract_code,
    latest_report_date=None,
    valid_count=None,
    history_start=None,
    history_end=None,
    history_has_gaps=None,
):
    return {
        "method_version": METHOD_VERSION,
        "data_version": DATA_VERSION,
        "commodity_id": commodity_id,
        "status": "unavailable",
        "reason_code": reason_code,
        "reason": _REASON_TEXT[reason_code],
        "cftc_contract_market_code": contract_code,
        "report_type": REPORT_TYPE,
        "position_category": POSITION_CATEGORY,
        "latest_report_date": latest_report_date,
        "latest_net_position": None,
        "history_start_date": history_start,
        "history_end_date": history_end,
        "valid_observation_count": valid_count,
        "history_has_gaps": history_has_gaps,
        "latest_net_tie_count": None,
    }

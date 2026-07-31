import re
from collections import defaultdict
from datetime import date
from math import isfinite

_CU_CONTRACT_RE = re.compile(r"^CU(\d{2})(\d{2})$")

SELECTION_RULE_VERSION = "shfe_cu_main_oi_v1"
PRICE_SERIES_VERSION = "shfe_cu_oi_main_unadjusted_v1"
RETURN_METHOD_VERSION = "shfe_cu_oi_main_return_v1"


def _parse_cu_contract(contract):
    match = _CU_CONTRACT_RE.fullmatch(str(contract or "").strip().upper())
    if match is None:
        return None
    year = int(match.group(1))
    month = int(match.group(2))
    if month < 1 or month > 12:
        return None
    return (2000 + year, month)


def _parse_trade_date(value):
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def _is_eligible(row, expiry, trade_date_obj):
    if not isfinite(float(row["close"])):
        return False
    open_interest = row.get("open_interest")
    if open_interest is None or not isfinite(float(open_interest)):
        return False
    if float(open_interest) <= 0:
        return False
    return (expiry[0], expiry[1]) > (trade_date_obj.year, trade_date_obj.month)


def _has_valid_price(row):
    if not isfinite(float(row["close"])):
        return False
    open_interest = row.get("open_interest")
    if open_interest is None or not isfinite(float(open_interest)):
        return False
    return float(open_interest) > 0


def _candidate_key(candidate):
    return (
        -float(candidate["open_interest"]),
        candidate["expiry"][0],
        candidate["expiry"][1],
        candidate["contract"],
    )


def _select_for_date(candidates, prior_expiry):
    eligible = [
        c for c in candidates if prior_expiry is None or c["expiry"] >= prior_expiry
    ]
    if not eligible:
        return None
    eligible.sort(key=_candidate_key)
    return eligible[0]


def _prior_trading_day_close(close_by_contract_date, all_trade_dates, contract, idx):
    if idx == 0:
        return None
    prior_day = all_trade_dates[idx - 1]
    return close_by_contract_date.get(contract, {}).get(prior_day)


def build_shfe_cu_main_series(
    raw_rows, initial_selected_contract=None, initial_close=None
):
    by_date = defaultdict(list)
    close_by_contract_date = defaultdict(dict)
    for row in sorted(raw_rows, key=lambda r: r["trade_date"]):
        trade_date_obj = _parse_trade_date(row["trade_date"])
        if trade_date_obj is None:
            continue
        expiry = _parse_cu_contract(row["contract"])
        if expiry is None:
            continue
        by_date[trade_date_obj].append({**row, "expiry": expiry})
        if _has_valid_price(row):
            close_by_contract_date[row["contract"]][trade_date_obj] = float(
                row["close"]
            )

    all_trade_dates = sorted(by_date)
    result = []
    prior_selected = initial_selected_contract
    prior_selected_expiry = (
        _parse_cu_contract(initial_selected_contract)
        if initial_selected_contract
        else None
    )
    prior_selected_close = initial_close
    for idx, trade_date_obj in enumerate(all_trade_dates):
        candidates = [
            c
            for c in by_date[trade_date_obj]
            if _is_eligible(c, c["expiry"], trade_date_obj)
        ]
        selected = _select_for_date(candidates, prior_selected_expiry)
        if selected is None:
            result.append(
                {
                    "date": trade_date_obj.isoformat(),
                    "status": "unavailable",
                }
            )
            continue
        contract = selected["contract"]
        expiry = selected["expiry"]
        contract_roll = prior_selected is not None and contract != prior_selected
        same_contract_return = None
        prior_same_close = _prior_trading_day_close(
            close_by_contract_date, all_trade_dates, contract, idx
        )
        if prior_same_close is not None:
            same_contract_return = float(selected["close"]) / prior_same_close - 1
        unadjusted_continuous_return = None
        roll_gap = None
        if prior_selected_close is not None:
            unadjusted_continuous_return = (
                float(selected["close"]) / prior_selected_close - 1
            )
        if contract_roll and prior_selected_close is not None:
            roll_gap = float(selected["close"]) - prior_selected_close
        result.append(
            {
                "date": trade_date_obj.isoformat(),
                "selected_contract": contract,
                "previous_selected_contract": prior_selected,
                "close": float(selected["close"]),
                "settlement": (
                    float(selected["settlement"])
                    if selected.get("settlement") is not None
                    else None
                ),
                "volume": (
                    float(selected["volume"])
                    if selected.get("volume") is not None
                    else None
                ),
                "open_interest": float(selected["open_interest"]),
                "contract_roll": contract_roll,
                "roll_from": prior_selected if contract_roll else None,
                "roll_to": contract if contract_roll else None,
                "roll_gap": roll_gap,
                "unadjusted_continuous_return": unadjusted_continuous_return,
                "same_contract_return": same_contract_return,
                "roll_affected": contract_roll,
                "selection_rule_version": SELECTION_RULE_VERSION,
                "price_series_version": PRICE_SERIES_VERSION,
                "return_method_version": RETURN_METHOD_VERSION,
            }
        )
        prior_selected = contract
        prior_selected_expiry = expiry
        prior_selected_close = float(selected["close"])
    return result


def _iso_year_week(date_obj):
    return date_obj.isocalendar()[:2]


def build_shfe_cu_weekly_returns(main_rows):
    by_week = defaultdict(list)
    for row in main_rows:
        if row.get("status") == "unavailable":
            continue
        daily_return = row.get("same_contract_return")
        if daily_return is None:
            continue
        trade_date_obj = _parse_trade_date(row["date"])
        if trade_date_obj is None:
            continue
        by_week[_iso_year_week(trade_date_obj)].append(row)

    result = []
    for year, week in sorted(by_week):
        rows = by_week[(year, week)]
        compounded = 1.0
        for row in rows:
            compounded *= 1.0 + row["same_contract_return"]
        result.append(
            {
                "year": year,
                "week": week,
                "return": compounded - 1,
                "roll_in_week": any(row.get("contract_roll") for row in rows),
            }
        )
    return result

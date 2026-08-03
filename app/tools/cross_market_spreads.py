import math
from datetime import date

METHOD_VERSION = "cross_market_spreads_v1"

_SPREAD_ID_BRENT_WTI = "brent_wti_spot"
_SPREAD_ID_LME_COMEX = "lme_comex_copper"
_SPREAD_ID_SHFE_LME = "shfe_lme_copper"
_SPREAD_ID_SHFE_COMEX = "shfe_comex_copper"

_UNIT_ALIASES = {"USD/BBL", "$/BBL", "USD_per_barrel"}
_PRICE_TYPE_SPOT = "spot"

_BRENT_WTI_SPREAD = {
    "spread_id": _SPREAD_ID_BRENT_WTI,
    "label": "Date-aligned daily price spread",
    "formula": "Brent spot price - WTI spot price",
    "expression": "brent_price - wti_price",
    "unit": "USD/BBL",
    "legs": {
        "brent": {
            "source_series": "oil_brent_spot",
            "instrument": "Brent",
            "price_type": _PRICE_TYPE_SPOT,
            "unit": "USD/BBL",
        },
        "wti": {
            "source_series": "oil_wti_spot",
            "instrument": "WTI",
            "price_type": _PRICE_TYPE_SPOT,
            "unit": "USD/BBL",
        },
    },
}

_COPPER_UNAVAILABLE_CATALOG = [
    {
        "spread_id": _SPREAD_ID_LME_COMEX,
        "reason": "incomparable_price_basis",
        "label": "LME Copper - COMEX Copper",
        "legs": [
            {"side": "lme", "source_series": "copper_lme"},
            {"side": "comex", "source_series": "copper_comex"},
        ],
    },
    {
        "spread_id": _SPREAD_ID_SHFE_LME,
        "reason": "fx_source_not_approved",
        "label": "SHFE Copper - LME Copper",
        "legs": [
            {"side": "shfe", "source_series": "copper_shanghai"},
            {"side": "lme", "source_series": "copper_lme"},
        ],
    },
    {
        "spread_id": _SPREAD_ID_SHFE_COMEX,
        "reason": "fx_source_not_approved",
        "label": "SHFE Copper - COMEX Copper",
        "legs": [
            {"side": "shfe", "source_series": "copper_shanghai"},
            {"side": "comex", "source_series": "copper_comex"},
        ],
    },
]


def _date_key(value):
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _parsed_as_of(as_of_date):
    if not as_of_date:
        return None
    parsed = _date_key(as_of_date)
    if parsed is None:
        raise ValueError(f"invalid as-of date {as_of_date!r} for cross market spreads")
    return parsed


def _numeric_value(value):
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _eligible_rows(rows, as_of_date):
    as_of = _parsed_as_of(as_of_date)
    if as_of is None:
        return []
    eligible = []
    for row in rows or []:
        row_date = _date_key(row.get("date"))
        if row_date is None:
            continue
        if _numeric_value(row.get("value")) is None:
            continue
        if row_date > as_of:
            continue
        eligible.append(row)
    return eligible


def _leg_contract_mismatch(rows):
    for row in rows:
        if row.get("units") is not None and row.get("units") not in _UNIT_ALIASES:
            return "unit_mismatch"
        if (
            row.get("price_type") is not None
            and row.get("price_type") != _PRICE_TYPE_SPOT
        ):
            return "price_type_mismatch"
    return None


def _date_indexed(rows):
    by_date = {}
    for row in rows:
        by_date[_date_key(row["date"]).isoformat()] = row
    return by_date


def _oil_leg_payload(side, row):
    leg = dict(_BRENT_WTI_SPREAD["legs"][side])
    if row:
        leg["value"] = _numeric_value(row["value"])
        if row.get("source_identifier"):
            leg["source_identifier"] = row["source_identifier"]
        if row.get("source_url"):
            leg["source_url"] = row["source_url"]
    return leg


def _copper_leg_context(
    leg_spec, copper_market_metadata, copper_market_rows, as_of_date
):
    series_id = leg_spec["source_series"]
    meta = (copper_market_metadata or {}).get(series_id, {})
    leg = {"side": leg_spec["side"], "source_series": series_id}
    if meta.get("instrument"):
        leg["instrument"] = meta["instrument"]
    if meta.get("units"):
        leg["unit"] = meta["units"]
    as_of = _parsed_as_of(as_of_date)
    if as_of is not None:
        dates = []
        for row in (copper_market_rows or {}).get(series_id, []) or []:
            row_date = _date_key(row.get("date"))
            if row_date is None or row_date > as_of:
                continue
            dates.append((row_date, row))
        if dates:
            leg["latest_date"] = sorted(dates)[-1][1].get("date")
    return leg


def _build_copper_unavailable_entry(
    entry, copper_market_metadata, copper_market_rows, as_of_date
):
    return {
        "spread_id": entry["spread_id"],
        "status": "unavailable",
        "reason": entry["reason"],
        "label": entry["label"],
        "legs": [
            _copper_leg_context(
                leg, copper_market_metadata, copper_market_rows, as_of_date
            )
            for leg in entry["legs"]
        ],
    }


def _build_brent_wti_entry(wti_rows, brent_rows, as_of_date):
    brent_eligible = _eligible_rows(brent_rows, as_of_date)
    wti_eligible = _eligible_rows(wti_rows, as_of_date)
    brent_mismatch = _leg_contract_mismatch(brent_eligible)
    wti_mismatch = _leg_contract_mismatch(wti_eligible)
    if brent_mismatch:
        reason = brent_mismatch
    elif wti_mismatch:
        reason = wti_mismatch
    elif not brent_eligible:
        reason = "missing_brent_price"
    elif not wti_eligible:
        reason = "missing_wti_price"
    else:
        brent_by_date = _date_indexed(brent_eligible)
        wti_by_date = _date_indexed(wti_eligible)
        common_dates = sorted(set(brent_by_date) & set(wti_by_date))
        if not common_dates:
            reason = "no_common_observation_date"
        else:
            common_date = common_dates[-1]
            brent_row = brent_by_date[common_date]
            wti_row = wti_by_date[common_date]
            spread_value = round(
                _numeric_value(brent_row["value"]) - _numeric_value(wti_row["value"]),
                4,
            )
            return {
                "spread_id": _SPREAD_ID_BRENT_WTI,
                "status": "available",
                "label": _BRENT_WTI_SPREAD["label"],
                "formula": _BRENT_WTI_SPREAD["formula"],
                "expression": _BRENT_WTI_SPREAD["expression"],
                "unit": _BRENT_WTI_SPREAD["unit"],
                "value": spread_value,
                "common_observation_date": common_date,
                "legs": {
                    "brent": _oil_leg_payload("brent", brent_row),
                    "wti": _oil_leg_payload("wti", wti_row),
                },
            }
    return {
        "spread_id": _SPREAD_ID_BRENT_WTI,
        "status": "unavailable",
        "reason": reason,
        "label": _BRENT_WTI_SPREAD["label"],
        "expression": _BRENT_WTI_SPREAD["expression"],
        "unit": _BRENT_WTI_SPREAD["unit"],
        "legs": {
            "brent": _oil_leg_payload(
                "brent", brent_eligible[-1] if brent_eligible else None
            ),
            "wti": _oil_leg_payload("wti", wti_eligible[-1] if wti_eligible else None),
        },
    }


def build_cross_market_spreads(
    wti_rows=None,
    brent_rows=None,
    copper_market_metadata=None,
    copper_market_rows=None,
    as_of_date=None,
):
    brent_wti = _build_brent_wti_entry(wti_rows, brent_rows, as_of_date)
    copper_entries = [
        _build_copper_unavailable_entry(
            entry, copper_market_metadata, copper_market_rows, as_of_date
        )
        for entry in _COPPER_UNAVAILABLE_CATALOG
    ]
    return {
        "method_version": METHOD_VERSION,
        "spreads": [brent_wti, *copper_entries],
    }

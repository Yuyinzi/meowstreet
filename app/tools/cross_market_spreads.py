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

_COPPER_LME_COMEX_METHOD_VERSION = "copper_lme_comex_differential_v1"
_COPPER_LME_COMEX_EVIDENCE_TYPE = "date_aligned_continuous_price_differential"
_COPPER_LME_COMEX_LABEL = "LME-COMEX Date-aligned Continuous-price Differential"
_COPPER_LME_COMEX_FORMULA = (
    "LME Copper Grade A close - (COMEX HG close × 2204.62262185)"
)
_COPPER_LME_COMEX_EXPRESSION = "lme_close - comex_close_converted"
_COPPER_LME_COMEX_LIMITATIONS = [
    "contract_tenor_not_confirmed_comparable",
    "close_timing_not_synchronized",
    "continuous_roll_rules_undocumented",
]
_COPPER_LBS_PER_TONNE = 2204.62262185
_COPPER_SOURCE_VENDOR = "Investing.com rendered-history"
_COPPER_PRICE_BASIS = "vendor_continuous_series"
_COPPER_FIELD_CLOSE = "close"
_COPPER_LME_INSTRUMENT = "LME Copper Grade A"
_COPPER_COMEX_INSTRUMENT = "Copper High Grade futures (HG)"
_COPPER_LME_UNIT = "USD/tonne"
_COPPER_COMEX_UNIT = "USD/lb"
_COPPER_LME_COMEX_SERIES = {
    "lme": "copper_lme",
    "comex": "copper_comex",
}

_COPPER_UNAVAILABLE_CATALOG = [
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


def _frozen_source_contract(meta, instrument):
    return (
        meta.get("instrument") == instrument
        and meta.get("source_vendor") == _COPPER_SOURCE_VENDOR
        and meta.get("price_basis") == _COPPER_PRICE_BASIS
        and meta.get("roll_rule_documented") is False
    )


def _copper_leg_rows(rows, as_of):
    if as_of is None:
        return {"latest_eligible": None, "latest_date_valid": None, "by_date": {}}
    latest_eligible = None
    latest_date_valid = None
    by_date = {}
    for row in rows or []:
        row_date = _date_key(row.get("date"))
        if row_date is None or row_date > as_of:
            continue
        if latest_date_valid is None or row_date >= latest_date_valid[0]:
            latest_date_valid = (row_date, row)
        value = _numeric_value(row.get("value"))
        if value is None:
            continue
        by_date[row_date.isoformat()] = row
        if latest_eligible is None or row_date >= latest_eligible[0]:
            latest_eligible = (row_date, row)
    return {
        "latest_eligible": latest_eligible,
        "latest_date_valid": latest_date_valid,
        "by_date": by_date,
    }


def _copper_latest_invalid(leg):
    latest = leg["latest_date_valid"]
    return latest is not None and _numeric_value(latest[1].get("value")) is None


def _lme_comex_unavailable_leg(side, meta, latest):
    leg = {
        "side": side,
        "source_series": _COPPER_LME_COMEX_SERIES[side],
    }
    if meta.get("instrument"):
        leg["instrument"] = meta["instrument"]
    if meta.get("field"):
        leg["field"] = meta["field"]
    if side == "lme":
        value_key = "value"
        if meta.get("units"):
            leg["unit"] = meta["units"]
    else:
        value_key = "source_value"
        if meta.get("units"):
            leg["source_unit"] = meta["units"]
    if latest is not None:
        leg[value_key] = _numeric_value(latest[1]["value"])
        leg["date"] = latest[0].isoformat()
    return leg


def _unavailable_lme_comex_entry(
    reason, lme_meta, comex_meta, lme_latest, comex_latest
):
    return {
        "spread_id": _SPREAD_ID_LME_COMEX,
        "status": "unavailable",
        "reason": reason,
        "method_version": _COPPER_LME_COMEX_METHOD_VERSION,
        "label": _COPPER_LME_COMEX_LABEL,
        "legs": {
            "lme": _lme_comex_unavailable_leg("lme", lme_meta, lme_latest),
            "comex": _lme_comex_unavailable_leg("comex", comex_meta, comex_latest),
        },
    }


def _lme_comex_available_leg(side, meta, row):
    leg = {"source_series": _COPPER_LME_COMEX_SERIES[side]}
    if meta.get("instrument"):
        leg["instrument"] = meta["instrument"]
    value = _numeric_value(row["value"])
    if side == "lme":
        leg["value"] = value
        leg["unit"] = meta.get("units")
        leg["field"] = meta.get("field")
    else:
        leg["source_value"] = value
        leg["source_unit"] = meta.get("units")
        leg["normalized_value"] = round(value * _COPPER_LBS_PER_TONNE, 4)
        leg["normalized_unit"] = _COPPER_LME_UNIT
        leg["conversion_factor"] = _COPPER_LBS_PER_TONNE
        leg["field"] = meta.get("field")
    return leg


def _available_lme_comex_entry(lme_meta, comex_meta, lme_row, comex_row, common_date):
    lme_value = _numeric_value(lme_row["value"])
    comex_value = _numeric_value(comex_row["value"])
    differential = round(lme_value - comex_value * _COPPER_LBS_PER_TONNE, 4)
    return {
        "spread_id": _SPREAD_ID_LME_COMEX,
        "status": "available",
        "comparability": "limited",
        "evidence_type": _COPPER_LME_COMEX_EVIDENCE_TYPE,
        "method_version": _COPPER_LME_COMEX_METHOD_VERSION,
        "label": _COPPER_LME_COMEX_LABEL,
        "formula": _COPPER_LME_COMEX_FORMULA,
        "expression": _COPPER_LME_COMEX_EXPRESSION,
        "unit": _COPPER_LME_UNIT,
        "common_observation_date": common_date,
        "value": differential,
        "legs": {
            "lme": _lme_comex_available_leg("lme", lme_meta, lme_row),
            "comex": _lme_comex_available_leg("comex", comex_meta, comex_row),
        },
        "limitations": list(_COPPER_LME_COMEX_LIMITATIONS),
    }


def _build_lme_comex_entry(copper_market_metadata, copper_market_rows, as_of_date):
    metadata = copper_market_metadata or {}
    rows = copper_market_rows or {}
    lme_meta = metadata.get(_COPPER_LME_COMEX_SERIES["lme"], {})
    comex_meta = metadata.get(_COPPER_LME_COMEX_SERIES["comex"], {})
    as_of = _parsed_as_of(as_of_date)
    lme_leg = _copper_leg_rows(
        rows.get(_COPPER_LME_COMEX_SERIES["lme"], []) or [], as_of
    )
    comex_leg = _copper_leg_rows(
        rows.get(_COPPER_LME_COMEX_SERIES["comex"], []) or [], as_of
    )

    if not _frozen_source_contract(
        lme_meta, _COPPER_LME_INSTRUMENT
    ) or not _frozen_source_contract(comex_meta, _COPPER_COMEX_INSTRUMENT):
        reason = "source_series_changed"
    elif (
        lme_meta.get("field") != _COPPER_FIELD_CLOSE
        or comex_meta.get("field") != _COPPER_FIELD_CLOSE
    ):
        reason = "field_definition_changed"
    elif lme_meta.get("units") != _COPPER_LME_UNIT:
        reason = "ambiguous_lme_unit"
    elif comex_meta.get("units") != _COPPER_COMEX_UNIT:
        reason = "ambiguous_comex_unit"
    elif _copper_latest_invalid(lme_leg) or _copper_latest_invalid(comex_leg):
        reason = "invalid_or_non_numeric_price"
    elif not lme_leg["by_date"]:
        reason = "missing_lme_price"
    elif not comex_leg["by_date"]:
        reason = "missing_comex_price"
    else:
        common_dates = sorted(set(lme_leg["by_date"]) & set(comex_leg["by_date"]))
        if not common_dates:
            reason = "no_exact_common_trading_date"
        else:
            common_date = common_dates[-1]
            return _available_lme_comex_entry(
                lme_meta,
                comex_meta,
                lme_leg["by_date"][common_date],
                comex_leg["by_date"][common_date],
                common_date,
            )
    return _unavailable_lme_comex_entry(
        reason,
        lme_meta,
        comex_meta,
        lme_leg["latest_eligible"],
        comex_leg["latest_eligible"],
    )


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
    lme_comex = _build_lme_comex_entry(
        copper_market_metadata, copper_market_rows, as_of_date
    )
    copper_entries = [
        _build_copper_unavailable_entry(
            entry, copper_market_metadata, copper_market_rows, as_of_date
        )
        for entry in _COPPER_UNAVAILABLE_CATALOG
    ]
    return {
        "method_version": METHOD_VERSION,
        "spreads": [brent_wti, lme_comex, *copper_entries],
    }

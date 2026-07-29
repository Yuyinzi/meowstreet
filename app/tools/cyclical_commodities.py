_CYCLICAL_COMMODITIES_VERSION = "cyclical_commodities_v1"

_COMMODITY_DISPLAY = {
    "crude_oil_wti": "WTI Crude Oil",
    "crude_oil_brent": "Brent Crude Oil",
    "heating_oil": "Heating Oil",
    "natural_gas": "Natural Gas",
    "palladium": "Palladium",
    "platinum": "Platinum",
    "silver": "Silver",
    "gold": "Gold",
    "copper": "Copper",
    "aluminium": "Aluminium",
    "steel": "Steel",
}


def _normalized_manager_position(latest_row):
    longs = latest_row["manager_longs"]
    shorts = latest_row["manager_shorts"]
    oi = latest_row["open_interest"]
    if oi <= 0:
        return None
    return (longs - shorts) / oi


def _detect_flip(current, prior):
    if prior is None:
        return "insufficient_history"
    if current is None or prior is None:
        return None
    prior_neg = prior < 0
    current_neg = current < 0
    if prior_neg and not current_neg:
        return "positive"
    if not prior_neg and current_neg:
        return "negative"
    return "no_flip"


def _compute_cot_commodity(rows):
    sorted_rows = sorted(rows, key=lambda r: r["report_date"])
    if not sorted_rows:
        return None
    latest = sorted_rows[-1]
    prior = sorted_rows[-2] if len(sorted_rows) >= 2 else None
    current_norm = _normalized_manager_position(latest)
    prior_norm = _normalized_manager_position(prior) if prior else None
    return {
        "report_date": latest["report_date"],
        "manager_longs": latest["manager_longs"],
        "manager_shorts": latest["manager_shorts"],
        "open_interest": latest["open_interest"],
        "normalized_manager_net_position": current_norm,
        "flip": _detect_flip(current_norm, prior_norm),
        "source_url": latest.get("source_url", ""),
        "publication_date": latest.get("publication_date", ""),
        "extreme": "not_configured",
    }


def _compute_cot_payload(cot_rows):
    by_commodity = {}
    for row in cot_rows:
        cid = row["commodity_id"]
        by_commodity.setdefault(cid, []).append(row)
    result = {}
    for cid in sorted(_COMMODITY_DISPLAY):
        rows = by_commodity.get(cid, [])
        if not rows:
            result[cid] = {
                "commodity_id": cid,
                "display_name": _COMMODITY_DISPLAY[cid],
                "status": "unavailable",
            }
            continue
        result[cid] = {
            "commodity_id": cid,
            "display_name": _COMMODITY_DISPLAY[cid],
            "status": "available",
            **_compute_cot_commodity(rows),
        }
    return result


def _pct_change_ratio(latest_val, prior_val):
    if prior_val is None or prior_val == 0:
        return None
    return (latest_val / prior_val) - 1


def _compute_usd_series_payload(series_id, display_name, observations):
    if not observations:
        return {
            "series_id": series_id,
            "display_name": display_name,
            "status": "unavailable",
            "distribution_status": "not_configured",
        }
    sorted_obs = sorted(observations, key=lambda o: o["date"])
    latest = sorted_obs[-1]
    latest_val = latest["value"]
    prior = sorted_obs[-2] if len(sorted_obs) >= 2 else None
    prior_5 = sorted_obs[-6] if len(sorted_obs) >= 6 else None
    prior_val = prior["value"] if prior else None
    prior_5_val = prior_5["value"] if prior_5 else None
    return {
        "series_id": series_id,
        "display_name": display_name,
        "status": "available",
        "latest_date": latest["date"],
        "latest_value": latest_val,
        "daily_return": _pct_change_ratio(latest_val, prior_val) if prior else None,
        "weekly_return": _pct_change_ratio(latest_val, prior_5_val),
        "source": "fred",
        "source_identifier": observations[0].get("source_identifier", ""),
        "distribution_status": "not_configured",
    }


def _compute_inflation_series_payload(series_id, display_name, observations):
    if not observations:
        return {
            "series_id": series_id,
            "display_name": display_name,
            "status": "unavailable",
            "distribution_status": "not_configured",
        }
    sorted_obs = sorted(observations, key=lambda o: o["date"])
    latest = sorted_obs[-1]
    latest_val = latest["value"]
    prior_1 = sorted_obs[-2] if len(sorted_obs) >= 2 else None
    prior_12 = sorted_obs[-13] if len(sorted_obs) >= 13 else None
    mom = _pct_change_ratio(latest_val, prior_1["value"]) if prior_1 else None
    yoy = _pct_change_ratio(latest_val, prior_12["value"]) if prior_12 else None
    return {
        "series_id": series_id,
        "display_name": display_name,
        "status": "available",
        "latest_date": latest["date"],
        "latest_value": latest_val,
        "mom_pct": mom,
        "yoy_pct": yoy,
        "source": "fred",
        "source_identifier": observations[0].get("source_identifier", ""),
        "distribution_status": "not_configured",
    }


_USD_SERIES_DISPLAY = {
    "usd_broad": "Trade-Weighted USD Broad (DTWEXBGS)",
    "usd_afe": "Trade-Weighted USD AFE (DTWEXAFEGS)",
    "usd_eme": "Trade-Weighted USD EME (DTWEXEMEGS)",
}

_INFLATION_SERIES_DISPLAY = {
    "cpi_all_items": "CPI All Items (CPIAUCSL)",
    "core_cpi": "Core CPI (CPILFESL)",
    "ppi_all_commodities": "PPI All Commodities (PPIACO)",
}

_USD_SERIES_IDS = set(_USD_SERIES_DISPLAY)
_INFLATION_SERIES_IDS = set(_INFLATION_SERIES_DISPLAY)


def build_cyclical_commodities_payload(
    cot_rows, usd_observations_by_series, as_of_date
):
    cot_payload = _compute_cot_payload(cot_rows)

    usd_payload = {}
    inflation_payload = {}

    for sid, display_name in _USD_SERIES_DISPLAY.items():
        observations = usd_observations_by_series.get(sid, [])
        usd_payload[sid] = _compute_usd_series_payload(sid, display_name, observations)

    for sid, display_name in _INFLATION_SERIES_DISPLAY.items():
        observations = usd_observations_by_series.get(sid, [])
        inflation_payload[sid] = _compute_inflation_series_payload(
            sid, display_name, observations
        )

    return {
        "version": _CYCLICAL_COMMODITIES_VERSION,
        "as_of_date": as_of_date,
        "cot": cot_payload,
        "usd": usd_payload,
        "inflation": inflation_payload,
        "commodity_attribution": {
            "status": "unavailable",
            "reason": "commodity price, demand, supply, and inventory sources are not yet configured; COT and USD evidence cannot substitute for attribution",
        },
        "commodity_returns": {
            "status": "unavailable",
            "reason": "continuous commodity price histories and contract-roll methodology are not yet configured",
        },
        "card_status": "partial_official_evidence",
    }


def build_cyclical_commodities_headline(payload):
    card_status = payload.get("card_status", "partial_official_evidence")
    reasons = []
    if payload.get("commodity_attribution", {}).get("status") == "unavailable":
        reasons.append("commodity attribution is unavailable")
    if payload.get("commodity_returns", {}).get("status") == "unavailable":
        reasons.append("commodity prices are unavailable")
    cot_available = any(
        v.get("status") == "available" for v in payload.get("cot", {}).values()
    )
    if not cot_available:
        reasons.append("cftc cot data is unavailable")
    usd_available = any(
        v.get("status") == "available" for v in payload.get("usd", {}).values()
    )
    inflation_available = any(
        v.get("status") == "available" for v in payload.get("inflation", {}).values()
    )
    available = []
    if cot_available:
        available.append("CFTC")
    if usd_available:
        available.append("USD")
    if inflation_available:
        available.append("CPI/PPI")
    reason = "; ".join(reasons) if reasons else "official evidence is partial"
    return {
        "id": "cyclical_commodities",
        "title": "Cyclical Commodities & USD",
        "status": card_status,
        "reason": reason,
        "available_evidence": available,
        "observation_date": payload.get("as_of_date"),
    }


def build_cyclical_commodities_detail(payload):
    detail_steps = [
        {
            "step": 1,
            "title": "CFTC COT Positioning",
            "status": "available",
            "method": "Normalized Manager Net Position = (Manager Longs - Manager Shorts) / Open Interest",
            "note": "Extreme detection not configured",
            "commodities": list(payload.get("cot", {}).values()),
        },
        {
            "step": 2,
            "title": "Trade-Weighted USD",
            "status": "available",
            "note": "Distribution status not configured",
            "series": list(payload.get("usd", {}).values()),
        },
        {
            "step": 3,
            "title": "Commodity Returns",
            "status": "unavailable",
            "reason": payload.get("commodity_returns", {}).get(
                "reason", "not configured"
            ),
        },
        {
            "step": 4,
            "title": "Commodity Attribution",
            "status": "unavailable",
            "reason": payload.get("commodity_attribution", {}).get(
                "reason", "not configured"
            ),
        },
        {
            "step": 5,
            "title": "CPI/PPI Confirmation",
            "status": "available",
            "note": "Distribution status not configured. See Inflation Context for Core PCE context.",
            "series": list(payload.get("inflation", {}).values()),
        },
    ]
    return {
        "detail_id": "cyclical_commodities",
        "version": payload.get("version"),
        "as_of_date": payload.get("as_of_date"),
        "card_status": payload.get("card_status"),
        "commodity_attribution": payload.get("commodity_attribution"),
        "commodity_returns": payload.get("commodity_returns"),
        "steps": detail_steps,
    }

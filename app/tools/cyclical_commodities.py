_CYCLICAL_COMMODITIES_VERSION = "cyclical_commodities_v1"

_COMMODITY_DISPLAY = {
    "crude_oil_wti": "WTI Crude Oil (ICE Futures Europe)",
    "crude_oil_brent": "Brent Crude Oil (NYMEX)",
    "heating_oil": "NY Harbor ULSD Heating Oil (NYMEX)",
    "natural_gas": "Natural Gas (ICE EP San Juan Index)",
    "palladium": "Palladium (NYMEX)",
    "platinum": "Platinum (NYMEX)",
    "silver": "Silver (COMEX)",
    "gold": "Gold (COMEX)",
    "copper": "Copper (COMEX)",
    "aluminium": "Aluminum (COMEX)",
    "steel": "Steel HRC (COMEX)",
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

_CONTRACT_NOTE = {
    "natural_gas": "CFTC reports a Natural Gas index contract (ICE EP San Juan), not the standard NYMEX Henry Hub benchmark. Henry Hub positioning is not available through this source.",
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
    if current is None:
        return None
    prior_neg = prior < 0
    current_neg = current < 0
    if prior_neg and not current_neg:
        return "positive"
    if not prior_neg and current_neg:
        return "negative"
    return "no_flip"


def _compute_cot_commodity(rows, as_of_date):
    sorted_rows = sorted(rows, key=lambda r: r["report_date"])
    if not sorted_rows:
        return None
    latest = sorted_rows[-1]
    prior = sorted_rows[-2] if len(sorted_rows) >= 2 else None
    current_norm = _normalized_manager_position(latest)
    prior_norm = _normalized_manager_position(prior) if prior else None
    cid = latest.get("commodity_id", "")
    result = {
        "report_date": latest["report_date"],
        "manager_longs": latest["manager_longs"],
        "manager_shorts": latest["manager_shorts"],
        "open_interest": latest["open_interest"],
        "normalized_manager_net_position": current_norm,
        "flip": _detect_flip(current_norm, prior_norm),
        "source_url": latest.get("source_url", ""),
        "publication_date": latest.get("publication_date", ""),
        "extreme": "not_configured",
        "status": "available",
    }
    note = _CONTRACT_NOTE.get(cid)
    if note:
        result["contract_note"] = note
    return result


def _compute_cot_payload(cot_rows):
    by_commodity = {}
    for row in cot_rows:
        cid = row["commodity_id"]
        by_commodity.setdefault(cid, []).append(row)
    result = {}
    any_available = False
    for cid in sorted(_COMMODITY_DISPLAY):
        rows = by_commodity.get(cid, [])
        if not rows:
            result[cid] = {
                "commodity_id": cid,
                "display_name": _COMMODITY_DISPLAY[cid],
                "status": "unavailable",
            }
            continue
        computed = _compute_cot_commodity(rows, None)
        if computed is None:
            result[cid] = {
                "commodity_id": cid,
                "display_name": _COMMODITY_DISPLAY[cid],
                "status": "unavailable",
            }
            continue
        result[cid] = {
            "commodity_id": cid,
            "display_name": _COMMODITY_DISPLAY[cid],
            **computed,
        }
        if computed.get("status") == "available":
            any_available = True
    return result, any_available


def _pct_change_ratio(latest_val, prior_val):
    if prior_val is None or prior_val == 0:
        return None
    return (latest_val / prior_val) - 1


def _compute_usd_series_payload(series_id, display_name, observations, as_of_date):
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


def _compute_inflation_series_payload(
    series_id, display_name, observations, as_of_date
):
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


def build_cyclical_commodities_payload(
    cot_rows, usd_observations_by_series, as_of_date
):
    as_of = as_of_date or ""
    cot_payload, cot_available = _compute_cot_payload(cot_rows)
    usd_payload = {}
    inflation_payload = {}
    for sid, display_name in _USD_SERIES_DISPLAY.items():
        observations = usd_observations_by_series.get(sid, [])
        usd_payload[sid] = _compute_usd_series_payload(
            sid, display_name, observations, as_of
        )
    for sid, display_name in _INFLATION_SERIES_DISPLAY.items():
        observations = usd_observations_by_series.get(sid, [])
        inflation_payload[sid] = _compute_inflation_series_payload(
            sid, display_name, observations, as_of
        )
    return {
        "version": _CYCLICAL_COMMODITIES_VERSION,
        "as_of_date": as_of,
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
    reasons = []
    if payload.get("commodity_attribution", {}).get("status") == "unavailable":
        reasons.append("commodity attribution is unavailable")
    if payload.get("commodity_returns", {}).get("status") == "unavailable":
        reasons.append("commodity prices are unavailable")
    cot_available = any(
        v.get("status") == "available" for v in payload.get("cot", {}).values()
    )
    usd_available = any(
        v.get("status") == "available" for v in payload.get("usd", {}).values()
    )
    inflation_available = any(
        v.get("status") == "available" for v in payload.get("inflation", {}).values()
    )
    available = []
    freshness = {}
    if cot_available:
        available.append("CFTC")
        cot_dates = [
            v.get("report_date")
            for v in payload.get("cot", {}).values()
            if v.get("status") == "available" and v.get("report_date")
        ]
        if cot_dates:
            freshness["cftc_latest"] = max(cot_dates)
    if usd_available:
        available.append("USD")
        usd_dates = [
            v.get("latest_date")
            for v in payload.get("usd", {}).values()
            if v.get("status") == "available" and v.get("latest_date")
        ]
        if usd_dates:
            freshness["usd_latest"] = max(usd_dates)
    if inflation_available:
        available.append("CPI/PPI")
        inf_dates = [
            v.get("latest_date")
            for v in payload.get("inflation", {}).values()
            if v.get("status") == "available" and v.get("latest_date")
        ]
        if inf_dates:
            freshness["inflation_latest"] = max(inf_dates)
    if not available:
        return {
            "id": "cyclical_commodities",
            "title": "Cyclical Commodities & USD",
            "status": "partial_official_evidence",
            "reason": "no official  observations loaded; run import_cyclical_commodities to fetch CFTC, USD, and CPI/PPI data",
            "available_evidence": [],
            "observation_date": payload.get("as_of_date"),
            "freshness": {},
        }
    reason = "; ".join(reasons) if reasons else "official evidence is partial"
    return {
        "id": "cyclical_commodities",
        "title": "Cyclical Commodities & USD",
        "status": "partial_official_evidence",
        "reason": reason,
        "available_evidence": available,
        "observation_date": payload.get("as_of_date"),
        "freshness": freshness,
    }


def _build_step(step_num, title, status, detail=None):
    step = {"step": step_num, "title": title, "status": status}
    if detail:
        step.update(detail)
    return step


def build_cyclical_commodities_detail(payload):
    details = _collect_series_details(payload)
    return {
        "detail_id": "cyclical_commodities",
        "version": payload.get("version"),
        "as_of_date": payload.get("as_of_date"),
        "card_status": payload.get("card_status"),
        "commodity_attribution": payload.get("commodity_attribution"),
        "commodity_returns": payload.get("commodity_returns"),
        "steps": details,
        "freshness": _collect_freshness_metadata(payload),
    }


def _collect_series_details(payload):
    attr = payload.get("commodity_attribution", {})
    returns = payload.get("commodity_returns", {})
    cot = payload.get("cot", {})
    usd = payload.get("usd", {})
    inf = payload.get("inflation", {})

    def has_available(d):
        return any(v.get("status") == "available" for v in d.values())

    return [
        _build_step(
            1,
            "Commodity Returns",
            returns.get("status", "unavailable"),
            {
                "reason": returns.get("reason", "not configured"),
            },
        ),
        _build_step(
            2,
            "Commodity Attribution",
            attr.get("status", "unavailable"),
            {
                "reason": attr.get("reason", "not configured"),
            },
        ),
        _build_step(
            3,
            "CFTC COT Positioning",
            "available" if has_available(cot) else "unavailable",
            {
                "method": "Normalized Manager Net Position = (Manager Longs - Manager Shorts) / Open Interest",
                "note": "Extreme detection not configured",
                "commodities": list(cot.values()),
            },
        ),
        _build_step(
            4,
            "Trade-Weighted USD",
            "available" if has_available(usd) else "unavailable",
            {
                "note": "Distribution status not configured",
                "series": list(usd.values()),
            },
        ),
        _build_step(
            5,
            "CPI/PPI Confirmation",
            "available" if has_available(inf) else "unavailable",
            {
                "note": "Distribution status not configured. See Inflation Context for Core PCE context.",
                "series": list(inf.values()),
            },
        ),
    ]


def _collect_freshness_metadata(payload):
    freshness = {}
    cot_dates = [
        v.get("report_date")
        for v in payload.get("cot", {}).values()
        if v.get("status") == "available" and v.get("report_date")
    ]
    if cot_dates:
        freshness["cftc_latest_report_date"] = max(cot_dates)
    usd_dates = [
        v.get("latest_date")
        for v in payload.get("usd", {}).values()
        if v.get("status") == "available" and v.get("latest_date")
    ]
    if usd_dates:
        freshness["usd_latest_observation_date"] = max(usd_dates)
    inf_dates = [
        v.get("latest_date")
        for v in payload.get("inflation", {}).values()
        if v.get("status") == "available" and v.get("latest_date")
    ]
    if inf_dates:
        freshness["inflation_latest_observation_date"] = max(inf_dates)
    obs_date = payload.get("as_of_date")
    if obs_date:
        freshness["as_of_date"] = obs_date
    return freshness

from app.data_sources.tracked_commodities import ACTIVE_MARKET_SERIES
from app.data_sources.lumber import _LUMBER_SERIES
from app.tools import oil_distribution

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


_OIL_BENCHMARK_IDS = {"oil_wti_spot", "oil_brent_spot"}

_OIL_BENCHMARK_SUMMARY_NAMES = {
    "oil_wti_spot": "WTI",
    "oil_brent_spot": "Brent",
}

_DISTRIBUTION_LABELS = {
    "abnormal_1sigma": "1σ abnormal",
    "abnormal_2sigma": "2σ abnormal",
    "abnormal_3sigma": "3σ abnormal",
}

_OIL_ATTRIBUTION_IDS = {
    "oil_commercial_crude_stocks",
    "oil_commercial_crude_imports",
    "oil_crude_production",
    "oil_refinery_crude_input",
    "oil_petroleum_products_supplied",
}

_OIL_ATTRIBUTION_DISPLAY = {
    "oil_commercial_crude_stocks": "U.S. commercial crude stocks",
    "oil_commercial_crude_imports": "Commercial crude imports",
    "oil_crude_production": "U.S. crude production",
    "oil_refinery_crude_input": "Refinery crude input",
    "oil_petroleum_products_supplied": "Petroleum products supplied",
}

_OIL_ATTRIBUTION_ROLES = {
    "oil_commercial_crude_stocks": "inventory",
    "oil_commercial_crude_imports": "supply_context",
    "oil_crude_production": "supply_context",
    "oil_refinery_crude_input": "processing_activity",
    "oil_petroleum_products_supplied": "demand_proxy",
}


def _raw_change_state(value, role=None):
    if value is None:
        return "unavailable"
    if value == 0:
        return "flat"
    if role == "inventory":
        return "draw" if value < 0 else "build"
    return "up" if value > 0 else "down"


def _latest_as_of(observations, as_of_date):
    eligible = [row for row in observations if row["date"] <= as_of_date]
    return sorted(eligible, key=lambda row: row["date"])


def _oil_benchmark_payload(series_id, observations, as_of_date, metadata=None):
    rows = _latest_as_of(observations, as_of_date)
    meta = metadata or {}
    if not rows:
        return {
            "series_id": series_id,
            "status": "unavailable",
            "distribution_status": "not_configured",
            "source_identifier": None,
            "source_url": None,
            "daily_distribution": oil_distribution.build_distribution([], "daily"),
            "weekly_distribution": oil_distribution.build_distribution(
                [], "weekly"
            ),
        }
    latest = rows[-1]
    daily_return = (
        _pct_change_ratio(latest["value"], rows[-2]["value"])
        if len(rows) >= 2
        else None
    )
    weekly_return = (
        _pct_change_ratio(latest["value"], rows[-6]["value"])
        if len(rows) >= 6
        else None
    )
    return {
        "series_id": series_id,
        "status": "available",
        "latest_date": latest["date"],
        "latest_value": latest["value"],
        "daily_return": daily_return,
        "daily_return_state": _raw_change_state(daily_return),
        "weekly_return": weekly_return,
        "weekly_return_state": _raw_change_state(weekly_return),
        "units": meta.get("units", ""),
        "distribution_status": "not_configured",
        "source_identifier": latest.get("source_identifier"),
        "source_url": latest.get("source_url"),
        "daily_distribution": oil_distribution.build_distribution(rows, "daily"),
        "weekly_distribution": oil_distribution.build_distribution(rows, "weekly"),
    }


def _oil_observation_payload(
    oil_observations_by_series, as_of_date, oil_series_metadata_by_id=None
):
    oil = oil_observations_by_series or {}
    meta = oil_series_metadata_by_id or {}
    benchmarks = {}
    any_available = False
    missing = []
    for sid in sorted(_OIL_BENCHMARK_IDS):
        observations = oil.get(sid, [])
        bp = _oil_benchmark_payload(
            sid, observations, as_of_date, metadata=meta.get(sid)
        )
        benchmarks[sid] = bp
        if bp["status"] == "available":
            any_available = True
        else:
            missing.append(sid)
    if not any_available:
        return {
            "status": "unavailable",
            "benchmarks": benchmarks,
            "reason": "no oil benchmark observations are available",
        }
    if missing:
        return {
            "status": "available",
            "benchmarks": benchmarks,
            "reason": f"missing benchmarks: {', '.join(missing)}",
        }
    return {"status": "available", "benchmarks": benchmarks}


def _oil_attribution_payload(
    oil_observations_by_series, as_of_date, oil_series_metadata_by_id=None
):
    oil = oil_observations_by_series or {}
    meta = oil_series_metadata_by_id or {}
    metrics = []
    missing_ids = []
    for sid in sorted(_OIL_ATTRIBUTION_IDS):
        observations = oil.get(sid, [])
        rows = _latest_as_of(observations, as_of_date)
        sid_meta = meta.get(sid, {})
        role = _OIL_ATTRIBUTION_ROLES.get(sid, "")
        metric = {
            "series_id": sid,
            "display_name": _OIL_ATTRIBUTION_DISPLAY.get(sid, sid),
            "role": role,
        }
        if rows:
            latest = rows[-1]
            prior = rows[-2] if len(rows) >= 2 else None
            weekly_change = (
                latest["value"] - prior["value"] if prior is not None else None
            )
            metric["status"] = "available"
            metric["latest_date"] = latest["date"]
            metric["latest_value"] = latest["value"]
            metric["weekly_change"] = weekly_change
            metric["weekly_change_state"] = _raw_change_state(weekly_change, role)
            metric["units"] = sid_meta.get("units", "")
            metric["source_url"] = latest.get("source_url", "")
            metric["source_identifier"] = latest.get("source_identifier", "")
            metric["release_date"] = latest.get("release_date")
        else:
            metric["status"] = "unavailable"
            missing_ids.append(sid)
        metrics.append(metric)
    if missing_ids:
        return {
            "status": "unavailable",
            "metrics": metrics,
            "reason": f"missing oil attribution inputs: {', '.join(missing_ids)}",
            "missing_series": missing_ids,
        }
    return {
        "status": "attribution_pending_review",
        "metrics": metrics,
        "review_label": "Official attribution inputs loaded — review required before forming a narrative.",
    }


def _commodity_display_registry():
    registry = {}
    for sid, meta in ACTIVE_MARKET_SERIES.items():
        registry[sid] = {
            "display_name": meta["display_name"],
            "exchange_label": meta["exchange_label"],
            "source_label": "Method-specified market data \u00b7 Investing.com",
            "source_url": meta["price_page_url"],
            "source_class": "free_web",
        }
    registry[_LUMBER_SERIES["series_id"]] = {
        "display_name": _LUMBER_SERIES["title"],
        "exchange_label": "CME",
        "source_label": "Yahoo Finance LBR=F",
        "source_url": _LUMBER_SERIES["source_url"],
        "source_class": _LUMBER_SERIES["source_class"],
    }
    return registry


def _commodity_payload(observations_by_series, as_of_date):
    result = {}
    for sid, entry in _commodity_display_registry().items():
        rows = _latest_as_of(observations_by_series.get(sid, []), as_of_date)
        if not rows:
            result[sid] = {
                "series_id": sid,
                "display_name": entry["display_name"],
                "status": "unavailable",
                "exchange_label": entry["exchange_label"],
                "source_class": entry["source_class"],
            }
            continue
        latest = rows[-1]
        daily_return = (
            _pct_change_ratio(latest["value"], rows[-2]["value"])
            if len(rows) >= 2
            else None
        )
        weekly_return = (
            _pct_change_ratio(latest["value"], rows[-6]["value"])
            if len(rows) >= 6
            else None
        )
        result[sid] = {
            "series_id": sid,
            "display_name": entry["display_name"],
            "latest_date": latest["date"],
            "latest_value": latest["value"],
            "daily_return": daily_return,
            "daily_return_state": _raw_change_state(daily_return),
            "weekly_return": weekly_return,
            "weekly_return_state": _raw_change_state(weekly_return),
            "source_label": entry["source_label"],
            "source_url": latest.get("source_url") or entry["source_url"],
            "source_identifier": latest.get("source_identifier"),
            "status": "available",
            "exchange_label": entry["exchange_label"],
            "source_class": entry["source_class"],
        }
    return result


def build_cyclical_commodities_payload(
    cot_rows,
    usd_observations_by_series,
    oil_observations_by_series=None,
    as_of_date=None,
    oil_series_metadata_by_id=None,
    commodity_observations=None,
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
    oil_observation = _oil_observation_payload(
        oil_observations_by_series, as_of, oil_series_metadata_by_id
    )
    oil_attribution = _oil_attribution_payload(
        oil_observations_by_series, as_of, oil_series_metadata_by_id
    )
    commodity = _commodity_payload(
        commodity_observations or {}, as_of
    )
    return {
        "version": _CYCLICAL_COMMODITIES_VERSION,
        "as_of_date": as_of,
        "cot": cot_payload,
        "usd": usd_payload,
        "inflation": inflation_payload,
        "oil_observation": oil_observation,
        "commodity_attribution": oil_attribution,
        "commodity_returns": {
            "status": "unavailable",
            "reason": "continuous commodity price histories and contract-roll methodology are not yet configured",
        },
        "card_status": "partial_official_evidence",
        "commodity_observation": commodity,
    }


def build_cyclical_commodities_headline(payload):
    reasons = []
    attr_status = payload.get("commodity_attribution", {}).get("status")
    ret_status = payload.get("commodity_returns", {}).get("status")
    if attr_status in ("unavailable", None):
        reasons.append("commodity attribution is unavailable")
    if ret_status in ("unavailable", None):
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
    oil_obs = payload.get("oil_observation", {})
    oil_available = oil_obs.get("status") == "available"
    attr_review = attr_status == "attribution_pending_review"
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
    if oil_available:
        available.append("Oil price")
    if attr_review:
        available.append("Oil attribution inputs")
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


def _oil_attribution_review(payload):
    oil_observation = payload.get("oil_observation", {})
    oil_attribution = payload.get("commodity_attribution", {})
    if oil_observation.get("status") != "available":
        return None
    if oil_attribution.get("status") != "attribution_pending_review":
        return None
    return {
        "method_version": "oil_attribution_review_states_v1",
        "status": "review_required",
        "label": "Attribution inputs complete — review whether the price move is demand-, supply-, or inventory-driven.",
        "reason": "Price, inventory, supply-context, processing-activity, and demand-proxy observations are available. Read their labeled changes together; no automatic attribution is made.",
    }


def _incomplete_oil_distribution_summary():
    return {
        "status": "incomplete",
        "label": "Oil price distribution is incomplete; review the available benchmark evidence.",
        "detail": "This describes price distribution only; physical-market attribution remains required.",
        "abnormal_observations": [],
    }


def _oil_price_distribution_summary(payload):
    benchmarks = payload.get("oil_observation", {}).get("benchmarks", {})
    abnormal_observations = []
    for series_id, display_name in _OIL_BENCHMARK_SUMMARY_NAMES.items():
        benchmark = benchmarks.get(series_id, {})
        if benchmark.get("status") != "available":
            return _incomplete_oil_distribution_summary()
        for horizon, field in (
            ("daily", "daily_distribution"),
            ("weekly", "weekly_distribution"),
        ):
            classification = benchmark.get(field, {}).get("classification")
            if classification == "unavailable" or classification is None:
                return _incomplete_oil_distribution_summary()
            if classification != "normal":
                abnormal_observations.append(
                    f"{display_name} {horizon} ({_DISTRIBUTION_LABELS[classification]})"
                )
    if abnormal_observations:
        return {
            "status": "abnormal",
            "label": "Statistically abnormal oil-price movement requires review: "
            + "; ".join(abnormal_observations)
            + ".",
            "detail": "This describes price distribution only; physical-market attribution remains required.",
            "abnormal_observations": abnormal_observations,
        }
    return {
        "status": "normal",
        "label": "Oil price movement is within 1σ of their 2016-to-latest available distributions across WTI and Brent on both daily and weekly horizons.",
        "detail": "This describes price distribution only; physical-market attribution remains required.",
        "abnormal_observations": [],
    }


def build_cyclical_commodities_detail(payload):
    details = _collect_series_details(payload)
    return {
        "detail_id": "cyclical_commodities",
        "version": payload.get("version"),
        "as_of_date": payload.get("as_of_date"),
        "card_status": payload.get("card_status"),
        "oil_observation": payload.get("oil_observation"),
        "commodity_attribution": payload.get("commodity_attribution"),
        "commodity_returns": payload.get("commodity_returns"),
        "oil_attribution_review": _oil_attribution_review(payload),
        "oil_price_distribution_summary": _oil_price_distribution_summary(payload),
        "process_read": _process_read(payload),
        "corroboration": _corroboration_summary(payload),
        "steps": details,
        "freshness": _collect_freshness_metadata(payload),
        "non_oil_observation": payload.get("commodity_observation", {}),
    }


def _collect_series_details(payload):
    attr = payload.get("commodity_attribution", {})
    returns = payload.get("commodity_returns", {})
    cot = payload.get("cot", {})
    usd = payload.get("usd", {})
    inf = payload.get("inflation", {})
    oil_obs = payload.get("oil_observation", {})

    def has_available(d):
        return any(v.get("status") == "available" for v in d.values())

    steps = [
        _build_step(
            1,
            "Oil Observation",
            oil_obs.get("status", "unavailable"),
            {
                "benchmarks": list(oil_obs.get("benchmarks", {}).values()),
                "reason": oil_obs.get("reason", ""),
            },
        ),
        _build_step(
            2,
            "Oil Attribution",
            attr.get("status", "unavailable"),
            {
                "metrics": attr.get("metrics", []),
                "reason": attr.get("reason", "not configured"),
                "review_label": attr.get("review_label", ""),
            },
        ),
        _build_step(
            3,
            "Commodity Returns",
            returns.get("status", "unavailable"),
            {
                "reason": returns.get("reason", "not configured"),
            },
        ),
        _build_step(
            4,
            "Commodity Attribution",
            "unavailable",
            {
                "reason": "continuous commodity price attribution requires the Oil Attribution step; non-oil commodity attribution sources are not yet configured",
            },
        ),
        _build_step(
            5,
            "CFTC COT Positioning",
            "available" if has_available(cot) else "unavailable",
            {
                "method": "Normalized Manager Net Position = (Manager Longs - Manager Shorts) / Open Interest",
                "note": "Extreme detection not configured",
                "commodities": list(cot.values()),
            },
        ),
        _build_step(
            6,
            "Trade-Weighted USD",
            "available" if has_available(usd) else "unavailable",
            {
                "note": "Distribution status not configured",
                "series": list(usd.values()),
            },
        ),
        _build_step(
            7,
            "CPI/PPI Confirmation",
            "available" if has_available(inf) else "unavailable",
            {
                "note": "Distribution status not configured. See Inflation Context for Core PCE context.",
                "series": list(inf.values()),
            },
        ),
    ]
    return steps


def _process_read(payload):
    oil_observation = payload.get("oil_observation", {})
    oil_attribution = payload.get("commodity_attribution", {})
    if oil_observation.get("status") != "available":
        return {
            "status": "insufficient_for_commodity_narrative",
            "label": "Commodity narrative cannot be assessed",
            "reason": "commodity price observation and demand, supply, inventory attribution are unavailable",
            "next_action": "configure official commodity price and attribution sources",
        }
    if oil_attribution.get("status") != "attribution_pending_review":
        return {
            "status": "insufficient_for_commodity_narrative",
            "label": "Commodity narrative cannot be assessed",
            "reason": "oil price observations are present but attribution inputs are incomplete",
            "next_action": "load official oil attribution inputs",
        }
    return {
        "status": "review_required",
        "label": "Oil attribution is ready for review",
        "reason": "Official oil price, inventory, supply-context, processing-activity, and demand-proxy inputs are available; review their joint context before forming a macro narrative.",
        "next_action": "review oil attribution evidence; do not treat any individual metric as a trade signal",
    }


def _direction(values):
    signs = {
        1 if value > 0 else -1 if value < 0 else 0
        for value in values
        if value is not None
    }
    if not signs:
        return "unavailable"
    if signs == {1}:
        return "rising"
    if signs == {-1}:
        return "falling"
    return "mixed"


def _corroboration_summary(payload):
    cot = payload.get("cot", {})
    usd = payload.get("usd", {})
    inf = payload.get("inflation", {})

    available_contracts = [k for k, v in cot.items() if v.get("status") == "available"]
    positive_flips = sum(
        1 for k in available_contracts if cot[k].get("flip") == "positive"
    )
    negative_flips = sum(
        1 for k in available_contracts if cot[k].get("flip") == "negative"
    )

    usd_available = [k for k, v in usd.items() if v.get("status") == "available"]
    usd_daily_vals = [usd[k].get("daily_return") for k in usd_available]
    usd_weekly_vals = [usd[k].get("weekly_return") for k in usd_available]

    inf_available = [k for k, v in inf.items() if v.get("status") == "available"]

    result = {
        "cot": {
            "available_contract_count": len(available_contracts),
            "positive_flip_count": positive_flips,
            "negative_flip_count": negative_flips,
        },
        "usd": {
            "available_series_count": len(usd_available),
            "daily_direction": _direction(usd_daily_vals),
            "weekly_direction": _direction(usd_weekly_vals),
        },
        "inflation": {
            "available_series_count": len(inf_available),
            "role": "confirmation_context",
        },
    }
    return result


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
    oil_dates = [
        v.get("latest_date")
        for v in payload.get("oil_observation", {}).get("benchmarks", {}).values()
        if v.get("status") == "available" and v.get("latest_date")
    ]
    if oil_dates:
        freshness["oil_latest_observation_date"] = max(oil_dates)
    obs_date = payload.get("as_of_date")
    if obs_date:
        freshness["as_of_date"] = obs_date
    return freshness

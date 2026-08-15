import hashlib

from app.db import benchmark_market_data
from app.db import economic_confirmation
from app.db import macro_indicators
from app.db import us_rates_liquidity as us_rates_liquidity_db
from app.tools import market_assistant_exploration as exploration_tools
from app.tools import us_rates_liquidity as us_rates_liquidity_tool
from app.tools.market_assistant_artifacts import validate_artifact

EXPLORATION_SCHEMA_VERSION = "market_assistant_exploration_result_v1"


def execute_exploration(con, query, *, result_id, created_at):
    validated_query = exploration_tools.validate_exploration_query(query)
    catalog = exploration_tools.load_exploration_catalog()
    indicator = exploration_tools.get_catalog_indicator(
        catalog, validated_query["indicator_id"]
    )
    query_kind = validated_query["query_kind"]
    if query_kind == "indicator_current":
        result = _build_current_result(con, validated_query, indicator, result_id)
    elif query_kind == "indicator_history":
        result = _build_history_result(con, validated_query, indicator, result_id)
    elif query_kind == "period_comparison":
        result = _build_comparison_result(con, validated_query, indicator, result_id)
    else:
        result = _build_release_history_result(
            con, validated_query, indicator, result_id
        )
    envelope = _build_envelope(result, result_id)
    validate_artifact(envelope)
    return result


def _build_envelope(result, result_id):
    envelope = {
        "artifact_id": result_id,
        "artifact_kind": "exploration_result",
        "schema_version": EXPLORATION_SCHEMA_VERSION,
        "primary_authority": "local_observation",
        "market_setup_relation": "non_decision",
        "payload": result,
        "object_index": result["object_index"],
    }
    envelope["integrity_hash"] = _hash_excluding(envelope, "integrity_hash")
    return envelope


def _hash_excluding(payload, excluded_key):
    projection = {key: value for key, value in payload.items() if key != excluded_key}
    return hashlib.sha256(exploration_tools.canonical_json(projection)).hexdigest()


def _build_current_result(con, query, indicator, result_id):
    rows = _load_rows(con, indicator)
    latest = rows[-1] if rows else None
    if latest is None:
        observed_window = {"date": None}
        data_through = None
        window_rows = []
    else:
        observed_window = {"date": latest["date"]}
        data_through = latest["date"]
        window_rows = [latest]
    statistics = _compute_statistics(window_rows, query, indicator, lifecycle_rows=rows)
    return _finalize_result(
        window_rows,
        statistics,
        query,
        indicator,
        observed_window,
        data_through,
        result_id,
    )


def _build_history_result(con, query, indicator, result_id):
    all_rows = _load_rows(con, indicator)
    rows = _filter_window(all_rows, query["start"], query["end"])
    _check_row_limit(rows, indicator)
    observed_window = {"start": query["start"], "end": query["end"]}
    data_through = rows[-1]["date"] if rows else None
    lifecycle_rows = (
        _filter_window(all_rows, all_rows[0]["date"], query["end"]) if all_rows else []
    )
    statistics = _compute_statistics(
        rows,
        query,
        indicator,
        lifecycle_rows=lifecycle_rows,
        window_start=query["start"],
    )
    return _finalize_result(
        rows,
        statistics,
        query,
        indicator,
        observed_window,
        data_through,
        result_id,
    )


def _build_comparison_result(con, query, indicator, result_id):
    all_rows = _load_rows(con, indicator)
    period_a_rows = _filter_window(
        all_rows, query["period_a"]["start"], query["period_a"]["end"]
    )
    period_b_rows = _filter_window(
        all_rows, query["period_b"]["start"], query["period_b"]["end"]
    )
    _check_row_limit(period_a_rows, indicator)
    _check_row_limit(period_b_rows, indicator)
    statistics_a = _compute_statistics(period_a_rows, query, indicator)
    statistics_b = _compute_statistics(period_b_rows, query, indicator)
    snapshot_a = _comparison_snapshot(period_a_rows)
    snapshot_b = _comparison_snapshot(period_b_rows)
    combined_rows = period_a_rows + period_b_rows
    combined_rows.sort(key=lambda row: row["date"])
    observed_window = {
        "period_a": {
            "start": query["period_a"]["start"],
            "end": query["period_a"]["end"],
        },
        "period_b": {
            "start": query["period_b"]["start"],
            "end": query["period_b"]["end"],
        },
    }
    data_through = combined_rows[-1]["date"] if combined_rows else None
    result = {
        "exploration_result_id": result_id,
        "artifact_schema_version": EXPLORATION_SCHEMA_VERSION,
        "authority": "local_observation",
        "market_setup_relation": "non_decision",
        "query_contract": query,
        "observed_window": observed_window,
        "data_through": data_through,
        "rows": combined_rows,
        "deterministic_statistics": {
            "period_a": statistics_a,
            "period_b": statistics_b,
        },
        "comparison": {
            "first_value": {
                "period_a": snapshot_a["first_value"],
                "period_b": snapshot_b["first_value"],
            },
            "last_value": {
                "period_a": snapshot_a["last_value"],
                "period_b": snapshot_b["last_value"],
            },
            "absolute_change": {
                "period_a": snapshot_a["absolute_change"],
                "period_b": snapshot_b["absolute_change"],
            },
        },
        "gaps": None,
    }
    return _finalize_result_parts(result, query, indicator)


def _comparison_snapshot(rows):
    values = [row["value"] for row in rows]
    return {
        "first_value": values[0] if values else None,
        "last_value": values[-1] if values else None,
        "absolute_change": values[-1] - values[0] if len(values) >= 2 else None,
    }


def _build_release_history_result(con, query, indicator, result_id):
    rows = _filter_window(_load_rows(con, indicator), query["start"], query["end"])
    _check_row_limit(rows, indicator)
    release_history = _release_metadata(con, indicator, rows)
    observed_window = {"start": query["start"], "end": query["end"]}
    data_through = rows[-1]["date"] if rows else None
    statistics = _compute_statistics(rows, query, indicator)
    result = {
        "exploration_result_id": result_id,
        "artifact_schema_version": EXPLORATION_SCHEMA_VERSION,
        "authority": "local_observation",
        "market_setup_relation": "non_decision",
        "query_contract": query,
        "observed_window": observed_window,
        "data_through": data_through,
        "rows": rows,
        "deterministic_statistics": statistics,
        "gaps": statistics.get("gaps"),
        "release_history": release_history,
    }
    return _finalize_result_parts(result, query, indicator)


def _finalize_result(
    rows,
    statistics,
    query,
    indicator,
    observed_window,
    data_through,
    result_id,
):
    result = {
        "exploration_result_id": result_id,
        "artifact_schema_version": EXPLORATION_SCHEMA_VERSION,
        "authority": "local_observation",
        "market_setup_relation": "non_decision",
        "query_contract": query,
        "observed_window": observed_window,
        "data_through": data_through,
        "rows": rows,
        "deterministic_statistics": statistics,
        "gaps": statistics.get("gaps"),
    }
    return _finalize_result_parts(result, query, indicator)


def _finalize_result_parts(result, query, indicator):
    objects = _build_result_objects(result, query["indicator_id"])
    result["object_index"] = objects
    result["result_hash"] = exploration_tools.compute_result_hash(result)
    return result


def _build_result_objects(result, indicator_id):
    objects = []
    for row in result["rows"]:
        objects.append(
            {
                "object_type": "observation_row",
                "object_id": f"{indicator_id}:{row['date']}",
                "authority": "local_observation",
                "payload": row,
            }
        )
    statistics = result["deterministic_statistics"]
    if _query_kind_is_comparison(result["query_contract"]):
        for period, period_statistics in statistics.items():
            for statistic_id, statistic_value in period_statistics.items():
                objects.append(
                    {
                        "object_type": "deterministic_statistic",
                        "object_id": f"{period}:{statistic_id}",
                        "authority": "local_observation",
                        "payload": {
                            "period": period,
                            "statistic_id": statistic_id,
                            "value": statistic_value,
                        },
                    }
                )
    else:
        for statistic_id, statistic_value in statistics.items():
            objects.append(
                {
                    "object_type": "deterministic_statistic",
                    "object_id": statistic_id,
                    "authority": "local_observation",
                    "payload": {
                        "statistic_id": statistic_id,
                        "value": statistic_value,
                    },
                }
            )
    return objects


def _query_kind_is_comparison(query_contract):
    return query_contract.get("query_kind") == "period_comparison"


def _load_rows(con, indicator):
    loader = indicator["loader"]
    series = indicator["local_series"]
    if loader == "macro_indicator_points":
        rows = _load_macro_points(con, series)
    elif loader == "economic_confirmation_current":
        rows = _load_economic_confirmation(con, series)
    elif loader == "benchmark_prices":
        rows = _load_benchmark(con, series)
    elif loader == "credit_conditions_history":
        rows = _load_credit_conditions_history(con)
    else:
        raise ValueError(f"exploration loader is not registered: {loader}")
    return sorted(rows, key=lambda row: row["date"])


def _load_macro_points(con, series):
    loaded = macro_indicators.load_macro_indicator_points_for_series(con, [series])
    return [
        {"date": row["date"], "value": row["value"]} for row in loaded.get(series, [])
    ]


def _load_economic_confirmation(con, series):
    loaded = economic_confirmation.load_current_series(con, [series])
    return [
        {"date": row["reference_period"], "value": row["value"]}
        for row in loaded.get(series, [])
    ]


def _load_benchmark(con, series):
    rows = benchmark_market_data.load_price_rows(con, series)
    return [{"date": row["date"], "value": row["close"]} for row in rows]


def _load_credit_conditions_history(con):
    treasury = us_rates_liquidity_db.load_rate_points_for_series(con, ["treasury_10y"])
    corporate = macro_indicators.load_macro_indicator_points_for_series(
        con, ["bbb_corporate_yield", "ccc_corporate_yield"]
    )
    points_by_id = {}
    points_by_id.update(treasury)
    points_by_id.update(corporate)
    return us_rates_liquidity_tool.build_credit_conditions_history(points_by_id)


def _filter_window(rows, start, end):
    return [row for row in rows if start <= row["date"] <= end]


def _check_row_limit(rows, indicator):
    if len(rows) > indicator["maximum_rows"]:
        raise ValueError(
            f"exploration query exceeds maximum rows for {indicator['indicator_id']}"
        )


def _compute_statistics(
    rows, query, indicator, *, lifecycle_rows=None, window_start=None
):
    if indicator["value_type"] == "categorical":
        return exploration_tools.compute_categorical_statistics(
            rows,
            state_values=indicator["state_values"],
            method_version=indicator["method_version"],
            decision_method_version=indicator["decision_method_version"],
            lifecycle_rows=lifecycle_rows,
            window_start=window_start,
        )
    return exploration_tools.compute_statistics(
        rows,
        query["statistics"],
        frequency=indicator["frequency"],
        gap_policy=indicator["gap_policy"],
    )


def _release_metadata(con, indicator, rows):
    loader = indicator["loader"]
    series = indicator["local_series"]
    if loader == "macro_indicator_points":
        return _macro_release_metadata(con, series, rows)
    if loader == "economic_confirmation_current":
        return _claims_release_metadata(con, series, rows)
    return {
        "state": "unavailable",
        "reason": f"release metadata is not available for {indicator['indicator_id']}",
    }


def _macro_release_metadata(con, series, rows):
    observations = macro_indicators.load_macro_indicator_observations(con, series)
    by_date = {observation["date"]: observation for observation in observations}
    periods = []
    for row in rows:
        observation = by_date.get(row["date"])
        if observation is None or observation.get("revision_status") is None:
            return {
                "state": "unavailable",
                "reason": f"release metadata is not available for {series}",
            }
        periods.append(
            {
                "date": row["date"],
                "release_date": observation.get("release_date"),
                "revision_status": observation["revision_status"],
                "source_identifier": (
                    observation.get("source_identifier")
                    or observation.get("source_url")
                ),
            }
        )
    return {"state": "available", "periods": periods}


def _claims_release_metadata(con, series, rows):
    loaded = economic_confirmation.load_current_series(con, [series])
    by_period = {row["reference_period"]: row for row in loaded.get(series, [])}
    periods = []
    for row in rows:
        observation = by_period.get(row["date"])
        if observation is None:
            return {
                "state": "unavailable",
                "reason": f"release metadata is not available for {series}",
            }
        revision_number = observation.get("revision_number") or 0
        periods.append(
            {
                "date": row["date"],
                "release_date": observation.get("release_date"),
                "revision_status": ("original" if revision_number == 0 else "revised"),
                "source_identifier": observation.get("source_url"),
            }
        )
    return {"state": "available", "periods": periods}

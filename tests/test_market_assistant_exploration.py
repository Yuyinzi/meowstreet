import json

import pytest

from app.db import benchmark_market_data
from app.db import economic_confirmation
from app.db import macro_indicators
from app.services import market_assistant_exploration
from app.tools import market_assistant_exploration as exploration_tools
from app.tools.market_assistant_artifacts import validate_artifact
from app.tools.market_assistant_exploration import validate_exploration_query


def seeded_connection(tmp_path):
    con = macro_indicators.connect(tmp_path / "exploration.sqlite")
    macro_indicators.merge_macro_indicator_points(
        con,
        {
            "series_id": "vix",
            "title": "CBOE Volatility Index",
            "units": "index",
            "source": "fred_vixcls",
        },
        [
            {"date": "2026-05-01", "value": 18.4, "source": "fred_vixcls"},
            {"date": "2026-05-08", "value": 19.1, "source": "fred_vixcls"},
            {"date": "2026-06-01", "value": 18.9, "source": "fred_vixcls"},
            {"date": "2026-06-15", "value": 20.2, "source": "fred_vixcls"},
            {"date": "2026-08-10", "value": 20.9, "source": "fred_vixcls"},
        ],
    )
    return con


def claims_connection(tmp_path):
    con = economic_confirmation.connect(tmp_path / "claims.sqlite")
    economic_confirmation.record_vintage_batch(
        con,
        [
            {
                "series_id": "initial_claims_sa",
                "reference_period": "2026-07-26",
                "vintage_id": "v1",
                "as_of_timestamp": "2026-07-30T00:00:00Z",
                "value_at_release": 233000,
                "latest_revised_value": None,
                "revision_number": 0,
                "seasonal_adjustment": "seasonally_adjusted",
                "source_url": "https://oui.doleta.gov",
                "source_hash": "abc123",
            },
            {
                "series_id": "initial_claims_sa",
                "reference_period": "2026-08-02",
                "vintage_id": "v1",
                "as_of_timestamp": "2026-08-06T00:00:00Z",
                "value_at_release": 227000,
                "latest_revised_value": None,
                "revision_number": 0,
                "seasonal_adjustment": "seasonally_adjusted",
                "source_url": "https://oui.doleta.gov",
                "source_hash": "def456",
            },
        ],
    )
    return con


def benchmark_connection(tmp_path):
    con = benchmark_market_data.connect(tmp_path / "benchmark.sqlite")
    benchmark_market_data.upsert_benchmark_prices(
        con,
        "us_sp500",
        [
            {
                "date": "2026-08-06",
                "open": 5400.0,
                "high": 5450.0,
                "low": 5390.0,
                "close": 5440.0,
            },
            {
                "date": "2026-08-07",
                "open": 5440.0,
                "high": 5480.0,
                "low": 5430.0,
                "close": 5470.0,
            },
            {
                "date": "2026-08-10",
                "open": 5470.0,
                "high": 5500.0,
                "low": 5460.0,
                "close": 5495.0,
            },
        ],
        "yf_refresh",
    )
    return con


def valid_indicator(**overrides):
    indicator = {
        "indicator_id": "vix",
        "loader": "macro_indicator_points",
        "local_series": "vix",
        "frequency": "daily",
        "unit": "index",
        "query_kinds": [
            "indicator_current",
            "indicator_history",
            "period_comparison",
            "release_history",
        ],
        "maximum_rows": 5000,
        "date_requirements": {"start": True, "end": True},
        "gap_policy": "not_applicable",
    }
    indicator.update(overrides)
    return indicator


def valid_catalog(*indicators):
    return {
        "version": "market_assistant_exploration_catalog_v1",
        "indicators": list(indicators),
    }


def write_catalog(tmp_path, catalog):
    path = tmp_path / "market_assistant_exploration_catalog.v1.json"
    path.write_text(json.dumps(catalog), encoding="utf-8")
    return path


def test_history_query_returns_exact_rows_and_statistics(tmp_path):
    con = seeded_connection(tmp_path)
    result = market_assistant_exploration.execute_exploration(
        con,
        {
            "query_kind": "indicator_history",
            "indicator_id": "vix",
            "start": "2026-05-01",
            "end": "2026-08-10",
            "statistics": [
                "first_value",
                "last_value",
                "absolute_change",
                "percentage_change",
            ],
        },
        result_id="qry_1",
        created_at="2026-08-10T02:00:00Z",
    )
    assert result["authority"] == "local_observation"
    assert result["market_setup_relation"] == "non_decision"
    assert result["deterministic_statistics"]["absolute_change"] == 2.5


def test_query_rejects_arbitrary_table_name():
    with pytest.raises(ValueError, match="extra inputs are not permitted"):
        validate_exploration_query(
            {
                "query_kind": "indicator_history",
                "indicator_id": "vix",
                "table": "prices",
            }
        )


def test_catalog_registers_six_indicators():
    catalog = exploration_tools.load_exploration_catalog()
    assert [indicator["indicator_id"] for indicator in catalog["indicators"]] == [
        "ism_manufacturing_pmi",
        "vix",
        "m2_money_stock",
        "initial_claims_sa",
        "continuing_claims_sa",
        "sp500_close",
    ]


def test_catalog_rejects_unknown_loader(tmp_path):
    path = write_catalog(
        tmp_path, valid_catalog(valid_indicator(loader="unknown_loader"))
    )
    with pytest.raises(ValueError, match="unknown loader"):
        exploration_tools.load_exploration_catalog(path)


def test_catalog_rejects_unknown_frequency(tmp_path):
    path = write_catalog(tmp_path, valid_catalog(valid_indicator(frequency="hourly")))
    with pytest.raises(ValueError, match="unknown frequency"):
        exploration_tools.load_exploration_catalog(path)


def test_catalog_rejects_unknown_query_kind(tmp_path):
    path = write_catalog(
        tmp_path,
        valid_catalog(
            valid_indicator(query_kinds=["indicator_history", "correlation_join"])
        ),
    )
    with pytest.raises(ValueError, match="unknown query kind"):
        exploration_tools.load_exploration_catalog(path)


def test_catalog_rejects_non_positive_max_rows(tmp_path):
    path = write_catalog(tmp_path, valid_catalog(valid_indicator(maximum_rows=0)))
    with pytest.raises(ValueError, match="maximum rows must be positive"):
        exploration_tools.load_exploration_catalog(path)


def test_catalog_rejects_duplicate_indicator(tmp_path):
    path = write_catalog(tmp_path, valid_catalog(valid_indicator(), valid_indicator()))
    with pytest.raises(ValueError, match="is duplicated"):
        exploration_tools.load_exploration_catalog(path)


def test_catalog_rejects_unknown_gap_policy(tmp_path):
    path = write_catalog(
        tmp_path, valid_catalog(valid_indicator(gap_policy="interpolate"))
    )
    with pytest.raises(ValueError, match="unknown gap policy"):
        exploration_tools.load_exploration_catalog(path)


def test_query_rejects_unknown_indicator():
    with pytest.raises(ValueError, match="indicator is not registered"):
        validate_exploration_query(
            {
                "query_kind": "indicator_current",
                "indicator_id": "unknown_series",
                "statistics": [],
            }
        )


def test_query_rejects_unsupported_statistic():
    with pytest.raises(ValueError, match="statistic is not approved"):
        validate_exploration_query(
            {
                "query_kind": "indicator_current",
                "indicator_id": "vix",
                "statistics": ["momentum"],
            }
        )


def test_query_rejects_start_after_end():
    with pytest.raises(ValueError, match="start is after end"):
        validate_exploration_query(
            {
                "query_kind": "indicator_history",
                "indicator_id": "vix",
                "start": "2026-08-10",
                "end": "2026-05-01",
                "statistics": ["count"],
            }
        )


def test_query_rejects_missing_required_field():
    with pytest.raises(ValueError, match="missing required field"):
        validate_exploration_query(
            {"query_kind": "indicator_history", "indicator_id": "vix"}
        )


def test_query_rejects_release_history_for_benchmark():
    with pytest.raises(ValueError, match="not supported"):
        validate_exploration_query(
            {
                "query_kind": "release_history",
                "indicator_id": "sp500_close",
                "start": "2026-05-01",
                "end": "2026-08-10",
                "statistics": [],
            }
        )


def test_compute_statistics_exact_values():
    rows = [
        {"date": "2026-01-05", "value": 10.0},
        {"date": "2026-01-06", "value": 12.0},
        {"date": "2026-01-07", "value": 11.0},
        {"date": "2026-01-08", "value": 14.0},
    ]
    statistics = exploration_tools.compute_statistics(
        rows,
        [
            "first_value",
            "last_value",
            "absolute_change",
            "percentage_change",
            "min",
            "max",
            "count",
            "adjacent_increases",
            "adjacent_decreases",
            "mean",
            "median",
        ],
    )
    assert statistics["first_value"] == 10.0
    assert statistics["last_value"] == 14.0
    assert statistics["absolute_change"] == 4.0
    assert statistics["percentage_change"] == 40.0
    assert statistics["min"] == 10.0
    assert statistics["max"] == 14.0
    assert statistics["count"] == 4
    assert statistics["adjacent_increases"] == 2
    assert statistics["adjacent_decreases"] == 1
    assert statistics["mean"] == 11.75
    assert statistics["median"] == 11.5


def test_compute_statistics_percentage_change_zero_first_value():
    rows = [
        {"date": "2026-01-05", "value": 0.0},
        {"date": "2026-01-06", "value": 5.0},
    ]
    statistics = exploration_tools.compute_statistics(rows, ["percentage_change"])
    assert statistics["percentage_change"] == {
        "state": "unavailable",
        "reason_code": "zero_first_value",
    }


def test_compute_statistics_gaps_monthly():
    rows = [
        {"date": "2026-01-01", "value": 50.0},
        {"date": "2026-03-01", "value": 52.0},
    ]
    statistics = exploration_tools.compute_statistics(
        rows, ["gaps"], frequency="monthly", gap_policy="missing_periods_reported"
    )
    assert statistics["gaps"] == {
        "policy": "missing_periods_reported",
        "missing_periods": ["2026-02"],
    }


def test_compute_statistics_gaps_not_applicable_for_daily():
    rows = [
        {"date": "2026-01-01", "value": 1.0},
        {"date": "2026-01-03", "value": 2.0},
    ]
    statistics = exploration_tools.compute_statistics(
        rows, ["gaps"], frequency="daily", gap_policy="not_applicable"
    )
    assert statistics["gaps"]["missing_periods"] is None


def test_compute_statistics_rejects_non_finite_values():
    rows = [{"date": "2026-01-01", "value": float("nan")}]
    with pytest.raises(ValueError, match="not finite"):
        exploration_tools.compute_statistics(rows, ["count"])


def test_canonical_json_rejects_non_finite_numbers():
    with pytest.raises(ValueError, match="non-finite"):
        exploration_tools.canonical_json({"rows": [{"value": float("inf")}]})


def test_indicator_current_returns_latest_row(tmp_path):
    con = seeded_connection(tmp_path)
    result = market_assistant_exploration.execute_exploration(
        con,
        {
            "query_kind": "indicator_current",
            "indicator_id": "vix",
            "statistics": ["first_value", "last_value"],
        },
        result_id="qry_current",
        created_at="2026-08-10T02:00:00Z",
    )
    assert result["observed_window"] == {"date": "2026-08-10"}
    assert result["data_through"] == "2026-08-10"
    assert result["rows"] == [{"date": "2026-08-10", "value": 20.9}]
    assert result["deterministic_statistics"]["first_value"] == 20.9
    assert result["deterministic_statistics"]["last_value"] == 20.9


def test_history_filters_exact_dates(tmp_path):
    con = seeded_connection(tmp_path)
    result = market_assistant_exploration.execute_exploration(
        con,
        {
            "query_kind": "indicator_history",
            "indicator_id": "vix",
            "start": "2026-05-08",
            "end": "2026-06-15",
            "statistics": ["count"],
        },
        result_id="qry_dates",
        created_at="2026-08-10T02:00:00Z",
    )
    assert [row["date"] for row in result["rows"]] == [
        "2026-05-08",
        "2026-06-01",
        "2026-06-15",
    ]
    assert result["deterministic_statistics"]["count"] == 3


def test_period_comparison_result(tmp_path):
    con = seeded_connection(tmp_path)
    result = market_assistant_exploration.execute_exploration(
        con,
        {
            "query_kind": "period_comparison",
            "indicator_id": "vix",
            "period_a": {"start": "2026-05-01", "end": "2026-05-31"},
            "period_b": {"start": "2026-06-01", "end": "2026-08-10"},
            "statistics": ["first_value", "last_value", "absolute_change", "count"],
        },
        result_id="qry_periods",
        created_at="2026-08-10T02:00:00Z",
    )
    assert result["deterministic_statistics"]["period_a"]["count"] == 2
    assert result["deterministic_statistics"]["period_b"]["count"] == 3
    assert result["comparison"]["first_value"]["period_a"] == 18.4
    assert result["comparison"]["last_value"]["period_b"] == 20.9
    assert result["comparison"]["absolute_change"]["period_b"] == 2.0


def test_release_history_claims(tmp_path):
    con = claims_connection(tmp_path)
    result = market_assistant_exploration.execute_exploration(
        con,
        {
            "query_kind": "release_history",
            "indicator_id": "initial_claims_sa",
            "start": "2026-07-01",
            "end": "2026-08-10",
            "statistics": ["last_value"],
        },
        result_id="qry_releases",
        created_at="2026-08-10T02:00:00Z",
    )
    assert result["release_history"]["state"] == "available"
    assert result["release_history"]["periods"][1]["date"] == "2026-08-02"
    assert result["release_history"]["periods"][1]["revision_status"] == "original"
    assert result["deterministic_statistics"]["last_value"] == 227000.0


def test_release_history_unavailable_when_metadata_missing(tmp_path):
    con = seeded_connection(tmp_path)
    result = market_assistant_exploration.execute_exploration(
        con,
        {
            "query_kind": "release_history",
            "indicator_id": "vix",
            "start": "2026-05-01",
            "end": "2026-08-10",
            "statistics": ["count"],
        },
        result_id="qry_rel_vix",
        created_at="2026-08-10T02:00:00Z",
    )
    assert result["release_history"]["state"] == "unavailable"


def test_benchmark_close_value_extraction(tmp_path):
    con = benchmark_connection(tmp_path)
    result = market_assistant_exploration.execute_exploration(
        con,
        {
            "query_kind": "indicator_history",
            "indicator_id": "sp500_close",
            "start": "2026-08-01",
            "end": "2026-08-10",
            "statistics": ["first_value", "last_value", "absolute_change"],
        },
        result_id="qry_spx",
        created_at="2026-08-10T02:00:00Z",
    )
    assert result["rows"][0] == {"date": "2026-08-06", "value": 5440.0}
    assert result["rows"][-1] == {"date": "2026-08-10", "value": 5495.0}
    assert result["deterministic_statistics"]["absolute_change"] == 55.0


def test_result_hash_excludes_itself_and_responds_to_rows(tmp_path):
    con = seeded_connection(tmp_path)
    result = market_assistant_exploration.execute_exploration(
        con,
        {
            "query_kind": "indicator_history",
            "indicator_id": "vix",
            "start": "2026-05-01",
            "end": "2026-08-10",
            "statistics": ["count"],
        },
        result_id="qry_hash",
        created_at="2026-08-10T02:00:00Z",
    )
    original_hash = result["result_hash"]
    result["result_hash"] = "mutated"
    assert exploration_tools.compute_result_hash(result) == original_hash
    result["rows"][0]["value"] = 99.0
    assert exploration_tools.compute_result_hash(result) != original_hash


def test_result_validates_as_artifact(tmp_path):
    con = seeded_connection(tmp_path)
    result = market_assistant_exploration.execute_exploration(
        con,
        {
            "query_kind": "indicator_history",
            "indicator_id": "vix",
            "start": "2026-05-01",
            "end": "2026-08-10",
            "statistics": ["first_value", "last_value"],
        },
        result_id="qry_artifact",
        created_at="2026-08-10T02:00:00Z",
    )
    envelope = {
        "artifact_id": result["exploration_result_id"],
        "artifact_kind": "exploration_result",
        "schema_version": result["artifact_schema_version"],
        "primary_authority": result["authority"],
        "market_setup_relation": result["market_setup_relation"],
        "payload": result,
        "object_index": result["object_index"],
        "integrity_hash": "unverified",
    }
    validated = validate_artifact(envelope)
    assert validated["payload"]["result_hash"] == result["result_hash"]

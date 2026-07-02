from app.tools import market_phase


def test_compute_market_phase_series_marks_bear_and_bull_segments():
    rows = [
        {
            "date": "2020-01-01",
            "open": 100.0,
            "high": 100.0,
            "low": 100.0,
            "close": 100.0,
        },
        {"date": "2020-01-02", "open": 90.0, "high": 90.0, "low": 90.0, "close": 90.0},
        {"date": "2020-01-03", "open": 79.0, "high": 79.0, "low": 79.0, "close": 79.0},
        {"date": "2020-01-04", "open": 82.0, "high": 82.0, "low": 82.0, "close": 82.0},
    ]

    result = market_phase.compute_market_phase_series(rows)

    assert result[-1]["rolling_high"] == 100.0
    assert result[-1]["bear_market_level"] == 80.0
    assert result[2]["market_phase_status"] == "bear_market"
    assert result[2]["bear_market_index"] == 79.0
    assert result[2]["bull_market_index"] is None
    assert result[3]["market_phase_status"] == "bull_market"
    assert result[3]["bear_market_index"] is None
    assert result[3]["bull_market_index"] == 82.0


def test_build_market_phase_payload_returns_latest_and_chart_series():
    rows = [
        {
            "date": "2020-01-01",
            "open": 100.0,
            "high": 100.0,
            "low": 100.0,
            "close": 100.0,
        },
        {"date": "2020-01-02", "open": 79.0, "high": 79.0, "low": 79.0, "close": 79.0},
    ]

    payload = market_phase.build_market_phase_payload("us_sp500", rows)

    assert payload["benchmark_id"] == "us_sp500"
    assert payload["title"] == "S&P 500"
    assert payload["region"] == "US"
    assert payload["data_through"] == "2020-01-02"
    assert payload["latest"]["market_phase_status"] == "bear_market"
    assert payload["latest"]["drawdown_pct"] == -21.0
    assert len(payload["series"]) == 2


def test_build_market_phase_summary_payload_excludes_chart_series():
    rows = [
        {
            "date": "2020-01-01",
            "open": 100.0,
            "high": 100.0,
            "low": 100.0,
            "close": 100.0,
        },
        {"date": "2020-01-02", "open": 79.0, "high": 79.0, "low": 79.0, "close": 79.0},
    ]

    payload = market_phase.build_market_phase_summary_payload("us_sp500", rows)

    assert payload["benchmark_id"] == "us_sp500"
    assert payload["title"] == "S&P 500"
    assert payload["region"] == "US"
    assert payload["data_through"] == "2020-01-02"
    assert payload["latest"]["market_phase_status"] == "bear_market"
    assert "series" not in payload


def test_build_dashboard_payload_excludes_chart_series():
    rows_by_id = {
        "us_sp500": [
            {
                "date": "2020-01-01",
                "open": 100.0,
                "high": 100.0,
                "low": 100.0,
                "close": 100.0,
            },
            {
                "date": "2020-01-02",
                "open": 79.0,
                "high": 79.0,
                "low": 79.0,
                "close": 79.0,
            },
        ]
    }

    payload = market_phase.build_dashboard_payload(
        lambda benchmark_id: rows_by_id.get(benchmark_id, [])
    )

    assert payload["markets"][0]["benchmark_id"] == "us_sp500"
    assert payload["markets"][0]["latest"]["market_phase_status"] == "bear_market"
    assert "series" not in payload["markets"][0]


def test_market_phase_payload_computes_derived_fields_from_raw_price_rows():
    payload = market_phase.build_market_phase_payload(
        "us_sp500",
        [
            {
                "date": "2021-10-11",
                "open": 4300.0,
                "high": 4545.85,
                "low": 4300.0,
                "close": 4361.19,
            },
            {
                "date": "2021-10-12",
                "open": 4368.31,
                "high": 4374.89,
                "low": 4342.09,
                "close": 4350.65,
            },
        ],
    )

    latest = payload["latest"]

    assert latest["rolling_high"] == 4545.85
    assert latest["bear_market_level"] == 3636.68
    assert latest["drawdown_pct"] == -4.29
    assert latest["market_phase_status"] == "bull_market"
    assert latest["bull_market_index"] == 4350.65
    assert latest["bear_market_index"] is None

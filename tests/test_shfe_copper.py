import pytest

from app.data_sources import shfe_copper


def fixture_records():
    return [
        {
            "symbol": "CU2608",
            "date": "20260730",
            "open": 104650,
            "high": 105450,
            "low": 104550,
            "close": 104900.0,
            "volume": 27702,
            "open_interest": 62075,
            "turnover": 1454603.725,
            "settle": 105010,
            "pre_settle": 104950,
            "variety": "CU",
        },
        {
            "symbol": "cu2609",
            "date": "20260730",
            "open": 104500,
            "high": 105310,
            "low": 104320,
            "close": 104690.0,
            "volume": 89003,
            "open_interest": 196080,
            "turnover": 4662815.255,
            "settle": 104770,
            "pre_settle": 104790,
            "variety": "CU",
        },
        {
            "symbol": "BC2608",
            "date": "20260730",
            "open": 93000,
            "high": 93500,
            "low": 92900,
            "close": 93260.0,
            "volume": 500,
            "open_interest": 1000,
            "turnover": 123.0,
            "settle": 93250,
            "pre_settle": 93100,
            "variety": "BC",
        },
        {
            "symbol": "CU88",
            "date": "20260730",
            "open": 1.0,
            "high": 1.0,
            "low": 1.0,
            "close": 1.0,
            "volume": 1,
            "open_interest": 1,
            "turnover": 1.0,
            "settle": 1,
            "pre_settle": 1,
            "variety": "CU",
        },
        {
            "symbol": "CU2610",
            "date": "20260730",
            "open": 104390,
            "high": 105150,
            "low": 104130,
            "close": None,
            "volume": 30690,
            "open_interest": 112171,
            "turnover": 1605574.260,
            "settle": 104630,
            "pre_settle": 104640,
            "variety": "CU",
        },
        {
            "symbol": "CU2611",
            "date": "20260730",
            "open": 104180,
            "high": 104930,
            "low": 103940,
            "close": 104310.0,
            "volume": 6852,
            "open_interest": 0,
            "turnover": 357919.430,
            "settle": 104470,
            "pre_settle": 104440,
            "variety": "CU",
        },
        {
            "symbol": "CU2612",
            "date": "20260730",
            "open": 104070,
            "high": 104800,
            "low": 103820,
            "close": 104420.0,
            "volume": 6216,
            "open_interest": None,
            "turnover": 324080.320,
            "settle": 104270,
            "pre_settle": 104280,
            "variety": "CU",
        },
        {
            "symbol": "CU2701",
            "date": "20260730",
            "open": 103850,
            "high": 104620,
            "low": 103650,
            "close": 103880.0,
            "volume": 2655,
            "open_interest": 25915,
            "turnover": 138104.660,
            "settle": 104030,
            "pre_settle": 104100,
            "variety": "CU",
        },
    ]


def expected_cu2608():
    return {
        "trade_date": "2026-07-30",
        "product": "CU",
        "contract": "CU2608",
        "open": 104650.0,
        "high": 105450.0,
        "low": 104550.0,
        "close": 104900.0,
        "previous_settlement": 104950.0,
        "settlement": 105010.0,
        "volume": 27702.0,
        "open_interest": 62075.0,
        "open_interest_change": None,
        "turnover": 1454603.725,
        "source": "shfe",
        "source_class": "official_exchange",
        "access_adapter": "akshare",
        "access_adapter_version": "1.18.30",
        "source_identifier": "SHFE:CU",
        "source_url": "https://www.shfe.com.cn/reports/tradedata/dailyandweeklydata/?query_options=1&query_params=kx&query_product_code=cu_f",
        "source_hash": "e373e106ca8698790e44125b7e0c4a1a99a19f341aeab4fd6f29073cbb90b2ae",
        "retrieved_at": "2026-07-31T00:00:00+00:00",
    }


def test_source_hash_changes_when_official_correction_changes_a_value():
    base = expected_cu2608()
    corrected = dict(base, close=105000.0)

    assert shfe_copper._source_hash(base) != shfe_copper._source_hash(corrected)


class _FakeAkshare:
    __version__ = "1.18.81"

    def __init__(self, day_rows):
        self.day_rows = day_rows
        self.requested_days = []

    def get_shfe_daily(self, date=None):
        self.requested_days.append(date)
        rows = self.day_rows.get(date, [])
        import pandas as pd

        return pd.DataFrame(rows)


class _FakeCalendar:
    def __init__(self, days):
        import pandas as pd

        self._days = days
        self._frame = pd.DataFrame({"trade_date": days})

    def get_trade_dates(self):
        return self._frame["trade_date"].tolist()

    def __getitem__(self, key):
        return self._frame[key]


def _calendar_frame(days):
    import pandas as pd

    return pd.DataFrame({"trade_date": pd.Series(days)})


def test_akshare_daily_fetch_requests_only_trading_days():
    calendar = _calendar_frame(
        [
            __import__("datetime").date(2026, 7, 27),
            __import__("datetime").date(2026, 7, 28),
        ]
    )
    ak = _FakeAkshare(
        {
            "20260727": [
                {
                    "symbol": "CU2609",
                    "date": "20260727",
                    "close": 79000.0,
                    "open_interest": 200000.0,
                }
            ],
            "20260728": [
                {
                    "symbol": "CU2609",
                    "date": "20260728",
                    "close": 79500.0,
                    "open_interest": 200000.0,
                }
            ],
        }
    )

    records, version = shfe_copper._akshare_daily_fetch(
        "20260727", "20260729", ak_module=ak, calendar_frame=calendar
    )

    assert version == "1.18.81"
    assert ak.requested_days == ["20260727", "20260728"]
    assert len(records) == 2


def test_akshare_daily_fetch_retries_transient_failure_then_succeeds():
    calendar = _calendar_frame([__import__("datetime").date(2026, 7, 27)])

    class FlakyAkshare(_FakeAkshare):
        def __init__(self):
            super().__init__(
                {
                    "20260727": [
                        {
                            "symbol": "CU2609",
                            "date": "20260727",
                            "close": 79000.0,
                            "open_interest": 200000.0,
                        }
                    ]
                }
            )
            self.failures_left = 1

        def get_shfe_daily(self, date=None):
            self.requested_days.append(date)
            if self.failures_left > 0:
                self.failures_left -= 1
                raise RuntimeError("socket timeout")
            rows = self.day_rows.get(date, [])
            import pandas as pd

            return pd.DataFrame(rows)

    ak = FlakyAkshare()
    records, _ = shfe_copper._akshare_daily_fetch(
        "20260727", "20260727", ak_module=ak, calendar_frame=calendar
    )

    assert len(records) == 1
    assert len(ak.requested_days) == 2


def test_akshare_daily_fetch_raises_after_max_retries():
    calendar = _calendar_frame([__import__("datetime").date(2026, 7, 27)])

    class FailingAkshare(_FakeAkshare):
        def __init__(self):
            super().__init__({})
            self.requested_days = []

        def get_shfe_daily(self, date=None):
            self.requested_days.append(date)
            raise RuntimeError("persistent failure")

    ak = FailingAkshare()
    with pytest.raises(
        ValueError, match="akshare SHFE daily fetch failed for 2026-07-27"
    ):
        shfe_copper._akshare_daily_fetch(
            "20260727", "20260727", ak_module=ak, calendar_frame=calendar
        )


def test_normalize_shfe_copper_contract_rows_retains_valid_monthly_cu_contracts():
    rows = shfe_copper.normalize_shfe_copper_contract_rows(
        fixture_records(), "2026-07-31T00:00:00+00:00", "1.18.30"
    )

    assert rows == [
        expected_cu2608(),
        {
            **expected_cu2608(),
            "contract": "CU2609",
            "open": 104500.0,
            "high": 105310.0,
            "low": 104320.0,
            "close": 104690.0,
            "previous_settlement": 104790.0,
            "settlement": 104770.0,
            "volume": 89003.0,
            "open_interest": 196080.0,
            "turnover": 4662815.255,
            "source_hash": "5e30456897e8a8b36f0b0d36857394f77d696de8b73b0257eb92cf2e751fce4f",
        },
        {
            **expected_cu2608(),
            "contract": "CU2701",
            "open": 103850.0,
            "high": 104620.0,
            "low": 103650.0,
            "close": 103880.0,
            "previous_settlement": 104100.0,
            "settlement": 104030.0,
            "volume": 2655.0,
            "open_interest": 25915.0,
            "turnover": 138104.660,
            "source_hash": "bc3625621f6e060846ddbf64b8f3f8cdf5599635d5a6f8207369c948f053d296",
        },
    ]


def test_normalize_rejects_non_cu_and_malformed_and_missing_fields():
    rows = shfe_copper.normalize_shfe_copper_contract_rows(
        fixture_records(), "2026-07-31T00:00:00+00:00", "1.18.30"
    )

    contracts = [row["contract"] for row in rows]
    assert "BC2608" not in contracts
    assert "CU88" not in contracts
    assert "CU2610" not in contracts
    assert "CU2611" not in contracts
    assert "CU2612" not in contracts


def test_normalize_empty_valid_output_raises_descriptive_error():
    with pytest.raises(
        ValueError,
        match="akshare returned no valid SHFE CU contract observations",
    ):
        shfe_copper.normalize_shfe_copper_contract_rows(
            [], "2026-07-31T00:00:00+00:00", "1.18.30"
        )


def test_fetch_shfe_copper_contract_rows_raises_on_adapter_failure():
    def failing_adapter(start, end):
        raise RuntimeError("socket hang up")

    with pytest.raises(ValueError, match="akshare SHFE CU fetch failed for"):
        shfe_copper.fetch_shfe_copper_contract_rows(
            "2026-07-30", "2026-07-30", adapter=failing_adapter
        )


def test_fetch_shfe_copper_contract_rows_uses_injected_adapter():
    def fake_adapter(start, end):
        assert start == "20260730"
        assert end == "20260730"
        return fixture_records(), "1.18.30"

    rows = shfe_copper.fetch_shfe_copper_contract_rows(
        "2026-07-30", "2026-07-30", adapter=fake_adapter
    )

    assert [row["contract"] for row in rows] == ["CU2608", "CU2609", "CU2701"]


from app.tools import shfe_copper


def _raw_contract_row(trade_date, contract, close, open_interest, **overrides):
    return {
        "trade_date": trade_date,
        "contract": contract,
        "close": close,
        "open_interest": open_interest,
        "settlement": close,
        "volume": 100.0,
        **overrides,
    }


def raw_contract_rows():
    return [
        _raw_contract_row("2026-07-28", "CU2608", 79000.0, 100000.0),
        _raw_contract_row("2026-07-28", "CU2609", 79500.0, 200000.0),
        _raw_contract_row("2026-07-28", "CU2610", 80200.0, 150000.0),
        _raw_contract_row("2026-07-29", "CU2608", 79500.0, 90000.0),
        _raw_contract_row("2026-07-29", "CU2609", 80000.0, 120000.0),
        _raw_contract_row("2026-07-29", "CU2610", 80500.0, 220000.0),
        _raw_contract_row("2026-07-30", "CU2608", 80000.0, 80000.0),
        _raw_contract_row("2026-07-30", "CU2609", 81000.0, 250000.0),
        _raw_contract_row("2026-07-30", "CU2610", 81500.0, 180000.0),
    ]


def test_main_contract_selects_highest_oi_excludes_delivery_month_and_never_rolls_back():
    rows = shfe_copper.build_shfe_cu_main_series(raw_contract_rows())

    assert [row["selected_contract"] for row in rows] == ["CU2609", "CU2610", "CU2610"]
    assert rows[1]["contract_roll"] is True
    assert rows[1]["roll_from"] == "CU2609"
    assert rows[1]["roll_to"] == "CU2610"


def test_main_contract_equal_oi_breaks_to_nearest_expiry():
    rows = [
        _raw_contract_row("2026-07-28", "CU2609", 79000.0, 150000.0),
        _raw_contract_row("2026-07-28", "CU2610", 79500.0, 150000.0),
        _raw_contract_row("2026-07-29", "CU2609", 79000.0, 150000.0),
        _raw_contract_row("2026-07-29", "CU2610", 79500.0, 150000.0),
    ]

    rows = shfe_copper.build_shfe_cu_main_series(rows)

    assert [row["selected_contract"] for row in rows] == ["CU2609", "CU2609"]


def test_main_contract_never_selects_an_expiry_earlier_than_prior_selected():
    rows = [
        _raw_contract_row("2026-07-28", "CU2609", 79000.0, 100000.0),
        _raw_contract_row("2026-07-28", "CU2610", 79500.0, 200000.0),
        _raw_contract_row("2026-07-29", "CU2609", 79000.0, 250000.0),
        _raw_contract_row("2026-07-29", "CU2610", 79500.0, 150000.0),
    ]

    rows = shfe_copper.build_shfe_cu_main_series(rows)

    assert [row["selected_contract"] for row in rows] == ["CU2610", "CU2610"]


def test_main_contract_reports_unavailable_when_no_eligible_contract():
    rows = [
        _raw_contract_row("2026-07-28", "CU2607", 79000.0, 100000.0),
        _raw_contract_row("2026-07-29", "CU2607", 79000.0, 100000.0),
    ]

    rows = shfe_copper.build_shfe_cu_main_series(rows)

    assert rows[0]["status"] == "unavailable"
    assert rows[1]["status"] == "unavailable"


def test_main_contract_same_contract_return_is_none_on_first_day():
    rows = shfe_copper.build_shfe_cu_main_series(raw_contract_rows())

    assert rows[0]["same_contract_return"] is None


def switched_rows():
    return [
        _raw_contract_row("2026-07-28", "CU2608", 78000.0, 100000.0),
        _raw_contract_row("2026-07-28", "CU2609", 79000.0, 200000.0),
        _raw_contract_row("2026-07-28", "CU2610", 80200.0, 150000.0),
        _raw_contract_row("2026-07-29", "CU2608", 78500.0, 90000.0),
        _raw_contract_row("2026-07-29", "CU2609", 79500.0, 120000.0),
        _raw_contract_row("2026-07-29", "CU2610", 80500.0, 220000.0),
    ]


def test_separated_returns_keep_roll_gap_auditable_but_exclude_from_distribution():
    switched = shfe_copper.build_shfe_cu_main_series(switched_rows())

    assert switched[1]["selected_contract"] == "CU2610"
    assert switched[1]["unadjusted_continuous_return"] == pytest.approx(
        80500 / 79000 - 1
    )
    assert switched[1]["same_contract_return"] == pytest.approx(80500 / 80200 - 1)
    assert switched[1]["roll_gap"] == 1500.0
    assert switched[1]["roll_affected"] is True
    assert switched[0]["roll_affected"] is False
    assert switched[0]["roll_gap"] is None


def test_main_series_rows_include_method_versions_and_provenance():
    rows = shfe_copper.build_shfe_cu_main_series(raw_contract_rows())

    assert rows[0]["selection_rule_version"] == "shfe_cu_main_oi_v1"
    assert rows[0]["price_series_version"] == "shfe_cu_oi_main_unadjusted_v1"
    assert rows[0]["return_method_version"] == "shfe_cu_oi_main_return_v1"


def same_contract_week_rows():
    return [
        _raw_contract_row("2026-07-28", "CU2609", 79000.0, 200000.0),
        _raw_contract_row("2026-07-29", "CU2609", 79500.0, 200000.0),
        _raw_contract_row("2026-07-30", "CU2609", 80000.0, 200000.0),
    ]


def test_weekly_returns_compound_valid_same_contract_returns_by_iso_week():
    main_rows = shfe_copper.build_shfe_cu_main_series(same_contract_week_rows())

    weekly = shfe_copper.build_shfe_cu_weekly_returns(main_rows)

    assert weekly[0]["year"] == 2026
    assert weekly[0]["week"] == 31
    assert weekly[0]["return"] == pytest.approx(80000 / 79000 - 1)
    assert weekly[0]["roll_in_week"] is False


def test_weekly_returns_mark_week_with_contract_roll():
    main_rows = shfe_copper.build_shfe_cu_main_series(switched_rows())

    weekly = shfe_copper.build_shfe_cu_weekly_returns(main_rows)

    assert weekly[0]["return"] == pytest.approx(80500 / 80200 - 1)
    assert weekly[0]["roll_in_week"] is True


def test_weekly_returns_use_same_contract_returns_not_unadjusted():
    main_rows = shfe_copper.build_shfe_cu_main_series(switched_rows())

    weekly = shfe_copper.build_shfe_cu_weekly_returns(main_rows)

    assert weekly[0]["return"] != pytest.approx(80500 / 79000 - 1)
    assert "unadjusted_continuous_return" not in weekly[0]


def test_weekly_returns_is_empty_when_no_valid_same_contract_return():
    no_prior_close_rows = [
        _raw_contract_row("2026-07-28", "CU2609", 79000.0, 200000.0),
        _raw_contract_row("2026-07-29", "CU2609", 79500.0, 100000.0),
        _raw_contract_row("2026-07-29", "CU2610", 80500.0, 220000.0),
    ]
    main_rows = shfe_copper.build_shfe_cu_main_series(no_prior_close_rows)

    weekly = shfe_copper.build_shfe_cu_weekly_returns(main_rows)

    assert weekly == []


def test_same_contract_return_is_none_when_contract_misses_prior_trading_day():
    gap_rows = [
        _raw_contract_row("2026-07-27", "CU2609", 79000.0, 200000.0),
        _raw_contract_row("2026-07-27", "CU2610", 80200.0, 150000.0),
        _raw_contract_row("2026-07-28", "CU2609", 79500.0, 200000.0),
        _raw_contract_row("2026-07-28", "CU2610", 80400.0, 150000.0),
        _raw_contract_row("2026-07-29", "CU2609", 0.0, 0.0),
        _raw_contract_row("2026-07-30", "CU2609", 80500.0, 200000.0),
        _raw_contract_row("2026-07-30", "CU2610", 80800.0, 150000.0),
    ]
    main_rows = shfe_copper.build_shfe_cu_main_series(gap_rows)

    assert [row.get("selected_contract") for row in main_rows] == [
        "CU2609",
        "CU2609",
        None,
        "CU2609",
    ]
    assert main_rows[1]["same_contract_return"] == pytest.approx(79500 / 79000 - 1)
    assert main_rows[3]["date"] == "2026-07-30"
    assert main_rows[3]["same_contract_return"] is None


def test_rebuild_window_boundary_cannot_roll_back_to_earlier_expiry():
    window_rows = [
        _raw_contract_row("2026-07-30", "CU2609", 80500.0, 250000.0),
        _raw_contract_row("2026-07-30", "CU2610", 80800.0, 150000.0),
    ]
    main_rows = shfe_copper.build_shfe_cu_main_series(
        window_rows,
        initial_selected_contract="CU2610",
        initial_close=80200.0,
    )

    assert [row["selected_contract"] for row in main_rows] == ["CU2610"]
    assert main_rows[0]["previous_selected_contract"] == "CU2610"
    assert main_rows[0]["contract_roll"] is False
    assert main_rows[0]["unadjusted_continuous_return"] == pytest.approx(
        80800 / 80200 - 1
    )


def test_rebuild_window_boundary_first_day_same_contract_return_is_none():
    window_rows = [
        _raw_contract_row("2026-07-30", "CU2609", 80500.0, 250000.0),
        _raw_contract_row("2026-07-30", "CU2610", 80800.0, 150000.0),
    ]
    main_rows = shfe_copper.build_shfe_cu_main_series(
        window_rows,
        initial_selected_contract="CU2609",
        initial_close=80200.0,
    )

    assert main_rows[0]["selected_contract"] == "CU2609"
    assert main_rows[0]["same_contract_return"] is None
    assert main_rows[0]["unadjusted_continuous_return"] == pytest.approx(
        80500 / 80200 - 1
    )

import json
import sqlite3

import pytest

from app.db import macro_indicators


def _series():
    return {
        "series_id": "bbb_corporate_yield",
        "title": "BBB Corporate Yield",
        "units": "percent",
        "source": "test",
    }


def _points():
    return [
        {"date": "2021-01-06", "value": 2.20, "source": "test"},
        {"date": "2021-01-07", "value": 2.16, "source": "test"},
    ]


def test_replace_macro_indicator_points_loads_sorted_rows(tmp_path):
    con = macro_indicators.connect(tmp_path / "market_data.sqlite")
    saved = macro_indicators.replace_macro_indicator_points(con, _series(), _points())
    loaded_series = macro_indicators.load_macro_indicator_series(con)
    loaded_points = macro_indicators.load_macro_indicator_points(
        con, "bbb_corporate_yield"
    )

    assert saved == {"series": 1, "points": 2}
    assert loaded_series[0]["series_id"] == "bbb_corporate_yield"
    assert loaded_points[0]["date"] == "2021-01-06"
    assert loaded_points[-1]["value"] == 2.16


def test_replace_macro_indicator_points_deletes_old_points(tmp_path):
    con = macro_indicators.connect(tmp_path / "market_data.sqlite")
    macro_indicators.replace_macro_indicator_points(con, _series(), _points())
    saved = macro_indicators.replace_macro_indicator_points(
        con, _series(), [{"date": "2021-02-01", "value": 3.00, "source": "test"}]
    )
    loaded = macro_indicators.load_macro_indicator_points(con, "bbb_corporate_yield")

    assert saved == {"series": 1, "points": 1}
    assert len(loaded) == 1


def test_merge_macro_indicator_points_preserves_existing_points(tmp_path):
    con = macro_indicators.connect(tmp_path / "market_data.sqlite")
    workbook_points = [
        {"date": "2021-01-06", "value": 2.20, "source": "workbook"},
        {"date": "2021-01-07", "value": 2.16, "source": "workbook"},
    ]
    fred_points = [
        {"date": "2023-10-01", "value": 6.10, "source": "fred"},
        {"date": "2023-10-02", "value": 6.08, "source": "fred"},
    ]

    macro_indicators.replace_macro_indicator_points(con, _series(), workbook_points)
    saved = macro_indicators.merge_macro_indicator_points(
        con,
        {**_series(), "source": "merged"},
        fred_points,
    )
    loaded = macro_indicators.load_macro_indicator_points(con, "bbb_corporate_yield")
    loaded_series = [
        row
        for row in macro_indicators.load_macro_indicator_series(con)
        if row["series_id"] == "bbb_corporate_yield"
    ][0]

    assert saved == {"series": 1, "points": 2}
    assert [row["date"] for row in loaded] == [
        "2021-01-06",
        "2021-01-07",
        "2023-10-01",
        "2023-10-02",
    ]
    assert loaded[-1]["value"] == 6.08
    assert loaded_series["source"] == "merged"


def test_merge_macro_indicator_points_replaces_matching_dates(tmp_path):
    con = macro_indicators.connect(tmp_path / "market_data.sqlite")
    macro_indicators.replace_macro_indicator_points(
        con,
        _series(),
        [{"date": "2023-10-02", "value": 12.00, "source": "old"}],
    )
    saved = macro_indicators.merge_macro_indicator_points(
        con,
        {**_series(), "source": "merged"},
        [{"date": "2023-10-02", "value": 11.75, "source": "new"}],
    )
    loaded = macro_indicators.load_macro_indicator_points(con, "bbb_corporate_yield")

    assert saved == {"series": 1, "points": 1}
    assert loaded == [{"date": "2023-10-02", "value": 11.75, "source": "new"}]


def test_insert_macro_indicator_points_additive(tmp_path):
    con = macro_indicators.connect(tmp_path / "market_data.sqlite")
    macro_indicators.insert_macro_indicator_points(con, _series(), _points())
    saved = macro_indicators.insert_macro_indicator_points(
        con,
        _series(),
        [{"date": "2021-02-01", "value": 3.00, "source": "test"}],
    )
    loaded = macro_indicators.load_macro_indicator_points(con, "bbb_corporate_yield")

    assert saved == {"series": 1, "points": 1}
    assert len(loaded) == 3


def test_load_latest_macro_indicator_points(tmp_path):
    con = macro_indicators.connect(tmp_path / "market_data.sqlite")
    macro_indicators.replace_macro_indicator_points(con, _series(), _points())
    latest = macro_indicators.load_latest_macro_indicator_points(con)

    assert len(latest) >= 1
    bbb = [r for r in latest if r["series_id"] == "bbb_corporate_yield"]
    assert bbb[0]["date"] == "2021-01-07"
    assert bbb[0]["value"] == 2.16


def test_load_macro_indicator_points_for_series(tmp_path):
    con = macro_indicators.connect(tmp_path / "market_data.sqlite")
    macro_indicators.replace_macro_indicator_points(con, _series(), _points())
    grouped = macro_indicators.load_macro_indicator_points_for_series(
        con, ["bbb_corporate_yield"]
    )

    assert "bbb_corporate_yield" in grouped
    assert len(grouped["bbb_corporate_yield"]) == 2


def test_normalize_series_id_rejects_empty():
    with pytest.raises(ValueError, match="series id is required"):
        macro_indicators._normalize_series_id("")


def test_replace_macro_indicator_points_batch(tmp_path):
    con = macro_indicators.connect(tmp_path / "market_data.sqlite")
    macro_indicators.replace_macro_indicator_points_batch(
        con,
        [
            {"series": _series(), "points": _points()},
            {
                "series": {
                    "series_id": "aaa_corporate_yield",
                    "title": "AAA Corporate Yield",
                    "units": "percent",
                    "source": "test",
                },
                "points": [{"date": "2021-01-06", "value": 1.50, "source": "test"}],
            },
        ],
    )
    loaded = macro_indicators.load_macro_indicator_series(con)
    assert len(loaded) == 2


def test_replace_macro_indicator_points_batch_atomic_rollback_on_error(tmp_path):
    con = macro_indicators.connect(tmp_path / "market_data.sqlite")

    with pytest.raises(ValueError, match="series id is required"):
        macro_indicators.replace_macro_indicator_points_batch(
            con,
            [
                {"series": _series(), "points": _points()},
                {
                    "series": {
                        "series_id": "",
                        "title": "Bad Series",
                        "units": "percent",
                        "source": "test",
                    },
                    "points": [{"date": "2021-01-06", "value": 1.50, "source": "test"}],
                },
            ],
        )

    loaded = macro_indicators.load_macro_indicator_series(con)
    assert len(loaded) == 0


class TestMacroIndicatorObservationMetadata:
    def test_merge_macro_indicator_observations_replaces_a_revised_month(
        self, tmp_path
    ):
        con = macro_indicators.connect(tmp_path / "market.sqlite")
        series = {
            "series_id": "building_permits_saar",
            "title": "Building Permits",
            "units": "thousands_saar",
            "source": "Census",
        }
        macro_indicators.merge_macro_indicator_observations(
            con,
            series,
            [
                {
                    "date": "2026-05-01",
                    "value": 1413.0,
                    "source": "census.xlsx",
                    "release_date": "2026-06-16",
                    "revision_status": "initial",
                    "source_url": "https://www.census.gov/construction/nrc/index.html",
                    "source_identifier": "May 2026",
                }
            ],
        )
        macro_indicators.merge_macro_indicator_observations(
            con,
            series,
            [
                {
                    "date": "2026-05-01",
                    "value": 1418.0,
                    "source": "census.xlsx",
                    "release_date": "2026-07-17",
                    "revision_status": "revised",
                    "source_url": "https://www.census.gov/construction/nrc/index.html",
                    "source_identifier": "June 2026 release",
                }
            ],
        )
        result = macro_indicators.load_macro_indicator_observations(
            con, "building_permits_saar"
        )
        result = macro_indicators.load_macro_indicator_observations(
            con, "building_permits_saar"
        )
        assert len(result) == 1
        assert result[0]["date"] == "2026-05-01"
        assert result[0]["value"] == 1418.0
        assert result[0]["source"] == "census.xlsx"
        assert result[0]["release_date"] == "2026-07-17"
        assert result[0]["publication_date_basis"] is None
        assert result[0]["source_identifier"] == "June 2026 release"

    def test_merge_macro_indicator_observations_preserves_metadata_on_value_update(
        self, tmp_path
    ):
        con = macro_indicators.connect(tmp_path / "market.sqlite")
        series = {
            "series_id": "building_permits_saar",
            "title": "Building Permits",
            "units": "thousands_saar",
            "source": "Census",
        }
        macro_indicators.merge_macro_indicator_observations(
            con,
            series,
            [
                {
                    "date": "2026-05-01",
                    "value": 1413.0,
                    "source": "census.xlsx",
                    "release_date": "2026-06-16",
                    "revision_status": "initial",
                    "source_url": "https://www.census.gov/construction/nrc/index.html",
                    "source_identifier": "May 2026",
                },
                {
                    "date": "2026-04-01",
                    "value": 1420.0,
                    "source": "census.xlsx",
                    "release_date": "2026-06-16",
                    "revision_status": "initial",
                    "source_url": "https://www.census.gov/construction/nrc/index.html",
                    "source_identifier": "May 2026",
                },
            ],
        )
        result = macro_indicators.load_macro_indicator_observations(
            con, "building_permits_saar"
        )
        assert len(result) == 2
        assert result[0]["date"] == "2026-04-01"
        assert result[1]["date"] == "2026-05-01"
        assert all(r["release_date"] == "2026-06-16" for r in result)
        assert all(r["revision_status"] == "initial" for r in result)

    def test_load_macro_indicator_observations_returns_empty_for_unknown_series(
        self, tmp_path
    ):
        con = macro_indicators.connect(tmp_path / "market.sqlite")
        result = macro_indicators.load_macro_indicator_observations(
            con, "no_such_series"
        )
        assert result == []

    def test_merge_macro_indicator_observations_persists_access_adapter_version(
        self, tmp_path
    ):
        con = macro_indicators.connect(tmp_path / "market.sqlite")
        series = {
            "series_id": "copper_lme_sina_cad_v1",
            "title": "Copper (LME 3M)",
            "units": "USD/tonne",
            "source": "sina_finance",
        }
        macro_indicators.merge_macro_indicator_observations(
            con,
            series,
            [
                {
                    "date": "2026-07-31",
                    "value": 13803.0,
                    "source": "sina_finance",
                    "access_adapter_version": "1.18.81",
                }
            ],
        )
        result = macro_indicators.load_macro_indicator_observations(
            con, "copper_lme_sina_cad_v1"
        )
        assert result[0]["access_adapter_version"] == "1.18.81"


_COT_ROW = {
    "commodity_id": "crude_oil_wti",
    "report_date": "2026-07-21",
    "manager_longs": 200000.0,
    "manager_shorts": 150000.0,
    "open_interest": 1000000.0,
    "publication_date": "2026-07-24",
    "publication_date_basis": "estimated: report_date_plus_3_calendar_days",
    "report_type": "disaggregated_futures_only",
    "cftc_contract_market_code": "067411",
    "position_category": "managed_money",
    "source_url": "https://www.cftc.gov/files/dea/history/fut_disagg_txt_2026.zip",
    "source_hash": "abc123",
}


def test_load_macro_indicator_series_for_ids_returns_only_requested_series(tmp_path):
    con = macro_indicators.connect(tmp_path / "market_data.sqlite")
    macro_indicators.merge_macro_indicator_points(
        con,
        {
            "series_id": "oil_commercial_crude_stocks",
            "title": "Stocks",
            "units": "MBBL",
            "source": "eia",
        },
        [{"date": "2026-07-17", "value": 411675.0, "source": "eia"}],
    )

    assert macro_indicators.load_macro_indicator_series_for_ids(
        con, ["oil_commercial_crude_stocks", "missing"]
    ) == {
        "oil_commercial_crude_stocks": {
            "series_id": "oil_commercial_crude_stocks",
            "title": "Stocks",
            "units": "MBBL",
            "source": "eia",
        }
    }


def test_merge_cot_observations_updates_same_commodity_and_report_date(tmp_path):
    con = macro_indicators.connect(tmp_path / "commodities.sqlite")
    macro_indicators.merge_cot_observations(con, [_COT_ROW])
    macro_indicators.merge_cot_observations(
        con, [{**_COT_ROW, "manager_longs": 201000.0}]
    )

    assert macro_indicators.load_cot_observations(con) == [
        {**_COT_ROW, "manager_longs": 201000.0}
    ]


def test_merge_cot_observations_persists_contract_identity(tmp_path):
    con = macro_indicators.connect(tmp_path / "commodities.sqlite")
    macro_indicators.merge_cot_observations(con, [_COT_ROW])

    loaded = macro_indicators.load_cot_observations(con)[0]
    assert loaded["cftc_contract_market_code"] == "067411"
    assert loaded["position_category"] == "managed_money"
    assert loaded["report_type"] == "disaggregated_futures_only"


def test_merge_cot_observations_requires_contract_market_code(tmp_path):
    con = macro_indicators.connect(tmp_path / "commodities.sqlite")
    with pytest.raises(ValueError, match="commodities cot contract market code is required"):
        macro_indicators.merge_cot_observations(
            con, [{**_COT_ROW, "cftc_contract_market_code": None}]
        )


def test_merge_cot_observations_requires_fixed_report_type(tmp_path):
    con = macro_indicators.connect(tmp_path / "commodities.sqlite")
    with pytest.raises(ValueError, match="commodities cot report type must be"):
        macro_indicators.merge_cot_observations(
            con, [{**_COT_ROW, "report_type": "futures_and_options"}]
        )


def test_merge_cot_observations_requires_managed_money_category(tmp_path):
    con = macro_indicators.connect(tmp_path / "commodities.sqlite")
    with pytest.raises(ValueError, match="commodities cot position category must be"):
        macro_indicators.merge_cot_observations(
            con, [{**_COT_ROW, "position_category": "commercial"}]
        )


def test_merge_cot_observations_rejects_exact_key_with_different_code(tmp_path):
    con = macro_indicators.connect(tmp_path / "commodities.sqlite")
    macro_indicators.merge_cot_observations(con, [_COT_ROW])
    with pytest.raises(ValueError, match="different contract market code"):
        macro_indicators.merge_cot_observations(
            con, [{**_COT_ROW, "cftc_contract_market_code": "999999"}]
        )


def test_replace_cot_history_rebuilds_scope_and_leaves_others(tmp_path):
    con = macro_indicators.connect(tmp_path / "commodities.sqlite")
    copper_row = {
        **_COT_ROW,
        "commodity_id": "copper",
        "cftc_contract_market_code": "085692",
    }
    macro_indicators.merge_cot_observations(con, [_COT_ROW, copper_row])

    count = macro_indicators.replace_cot_history(
        con,
        [{**_COT_ROW, "manager_longs": 205000.0}],
        ["crude_oil_wti"],
    )

    assert count == 1
    loaded = macro_indicators.load_cot_observations(con)
    by_id = {row["commodity_id"]: row for row in loaded}
    assert by_id["crude_oil_wti"]["manager_longs"] == 205000.0
    assert by_id["copper"]["manager_longs"] == 200000.0


def test_replace_cot_history_rolls_back_on_invalid_row(tmp_path):
    con = macro_indicators.connect(tmp_path / "commodities.sqlite")
    macro_indicators.merge_cot_observations(con, [_COT_ROW])

    with pytest.raises(ValueError, match="commodities cot contract market code is required"):
        macro_indicators.replace_cot_history(
            con,
            [{**_COT_ROW, "cftc_contract_market_code": None}],
            ["crude_oil_wti"],
        )

    loaded = macro_indicators.load_cot_observations(con)
    assert [row["commodity_id"] for row in loaded] == ["crude_oil_wti"]


def test_connect_migrates_cot_identity_columns(tmp_path):
    con = sqlite3.connect(tmp_path / "old.sqlite")
    con.execute(
        """create table cot_observations (
            commodity_id text not null,
            report_date text not null,
            manager_longs real not null,
            manager_shorts real not null,
            open_interest real not null,
            publication_date text,
            report_type text,
            source_url text,
            source_hash text,
            primary key(commodity_id, report_date)
        )"""
    )
    con.commit()
    con.close()

    con = macro_indicators.connect(tmp_path / "old.sqlite")
    cols = {
        row["name"]
        for row in con.execute("pragma table_info(cot_observations)").fetchall()
    }
    assert "cftc_contract_market_code" in cols
    assert "position_category" in cols


def test_legacy_null_identity_cot_row_remains_loadable(tmp_path):
    con = macro_indicators.connect(tmp_path / "commodities.sqlite")
    con.execute(
        """insert into cot_observations(
            commodity_id, report_date, manager_longs, manager_shorts, open_interest,
            publication_date, report_type, source_url, source_hash,
            cftc_contract_market_code, position_category
        ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            "crude_oil_wti",
            "2026-07-21",
            200000.0,
            150000.0,
            1000000.0,
            "2026-07-24",
            "disaggregated_futures_only",
            "https://example.test",
            "abc",
            None,
            None,
        ),
    )
    con.commit()

    loaded = macro_indicators.load_cot_observations(con)[0]
    assert loaded["cftc_contract_market_code"] is None
    assert loaded["position_category"] is None


def test_merge_macro_indicator_observations_persists_series_source_contract(tmp_path):
    con = macro_indicators.connect(tmp_path / "market.sqlite")
    series = {
        "series_id": "lumber_cme_lbr_yahoo_v1",
        "title": "Lumber (CME LBR)",
        "units": "USD/1,000 board feet",
        "source": "yahoo_finance",
        "source_contract": {"product_code": "LBR", "roll_rule": "undocumented"},
    }
    macro_indicators.merge_macro_indicator_observations(con, series, [])
    assert macro_indicators.load_macro_indicator_series_contracts_for_ids(
        con, [series["series_id"]]
    ) == {series["series_id"]: series["source_contract"]}


def test_series_contract_is_unchanged_when_observation_merge_rolls_back(tmp_path):
    con = macro_indicators.connect(tmp_path / "market.sqlite")
    original = {
        "series_id": "lumber_cme_lbr_yahoo_v1",
        "title": "Lumber (CME LBR)",
        "units": "USD/1,000 board feet",
        "source": "yahoo_finance",
        "source_contract": {"product_code": "LBR", "roll_rule": "undocumented"},
    }
    macro_indicators.merge_macro_indicator_observations(con, original, [])
    replacement = dict(
        original, source_contract={"product_code": "LBR", "roll_rule": "claimed"}
    )
    macro_indicators.merge_macro_indicator_observations(
        con, replacement, [], commit=False
    )
    con.rollback()
    assert macro_indicators.load_macro_indicator_series_contracts_for_ids(
        con, [original["series_id"]]
    ) == {original["series_id"]: original["source_contract"]}


def test_series_source_contract_must_be_a_non_empty_dict(tmp_path):
    con = macro_indicators.connect(tmp_path / "market.sqlite")
    series = {
        "series_id": "lumber_cme_lbr_yahoo_v1",
        "title": "Lumber (CME LBR)",
        "units": "USD/1,000 board feet",
        "source": "yahoo_finance",
        "source_contract": {},
    }
    with pytest.raises(
        ValueError, match="series source contract is required to be a non-empty dict"
    ):
        macro_indicators.merge_macro_indicator_observations(con, series, [])


def test_vendor_overlap_audit_is_keyed_by_series_and_version(tmp_path):
    con = macro_indicators.connect(tmp_path / "market.sqlite")
    audit = {"overlap_test_version": "copper_comex_hg_overlap_v1", "passed": True}
    macro_indicators.merge_vendor_series_overlap_audit(
        con, "copper_comex_hg_yahoo_v1", audit
    )
    assert (
        macro_indicators.load_vendor_series_overlap_audit(
            con, "copper_comex_hg_yahoo_v1", "copper_comex_hg_overlap_v1"
        )
        == audit
    )


def test_vendor_overlap_audit_is_separate_across_series(tmp_path):
    con = macro_indicators.connect(tmp_path / "market.sqlite")
    lumber_audit = {"overlap_test_version": "lumber_overlap_v1", "passed": True}
    copper_audit = {
        "overlap_test_version": "copper_comex_hg_overlap_v1",
        "passed": True,
    }
    macro_indicators.merge_vendor_series_overlap_audit(
        con, "lumber_cme_lbr_yahoo_v1", lumber_audit
    )
    macro_indicators.merge_vendor_series_overlap_audit(
        con, "copper_comex_hg_yahoo_v1", copper_audit
    )
    assert (
        macro_indicators.load_vendor_series_overlap_audit(
            con, "lumber_cme_lbr_yahoo_v1", "lumber_overlap_v1"
        )
        == lumber_audit
    )
    assert (
        macro_indicators.load_vendor_series_overlap_audit(
            con, "copper_comex_hg_yahoo_v1", "copper_comex_hg_overlap_v1"
        )
        == copper_audit
    )


def test_ensure_schema_migrates_legacy_lumber_overlap_audits(tmp_path):
    con = macro_indicators.connect(tmp_path / "market.sqlite")
    legacy_audit = {"overlap_test_version": "lumber_overlap_v1", "shared_date_count": 3}
    con.execute(
        """insert into lumber_overlap_audits(overlap_test_version, audit_json)
           values (?, ?)""",
        ("lumber_overlap_v1", json.dumps(legacy_audit, sort_keys=True)),
    )
    con.commit()
    macro_indicators.ensure_schema(con)
    assert (
        macro_indicators.load_vendor_series_overlap_audit(
            con, "lumber_cme_lbr_yahoo_v1", "lumber_overlap_v1"
        )
        == legacy_audit
    )


def test_connect_migrates_legacy_lumber_overlap_audits_on_reopen(tmp_path):
    db_path = tmp_path / "market.sqlite"
    con = macro_indicators.connect(db_path)
    legacy_audit = {"overlap_test_version": "lumber_overlap_v1", "shared_date_count": 3}
    con.execute(
        """insert into lumber_overlap_audits(overlap_test_version, audit_json)
           values (?, ?)""",
        ("lumber_overlap_v1", json.dumps(legacy_audit, sort_keys=True)),
    )
    con.commit()
    con.close()

    reopened = macro_indicators.connect(db_path)
    assert (
        macro_indicators.load_vendor_series_overlap_audit(
            reopened, "lumber_cme_lbr_yahoo_v1", "lumber_overlap_v1"
        )
        == legacy_audit
    )


def global_fact():
    return {
        "method_version": "non_oil_attribution_evidence_v1",
        "commodity_id": "copper",
        "source_name": "International Wrought Copper Council",
        "source_url": "http://www.coppercouncil.org/iwcc-statistics-and-data",
        "factor_category": "supply",
        "metric_name": "Production",
        "geography": "Global",
        "observation_date": "2024-12-31",
        "publication_date": None,
        "value": 24100.0,
        "units": "t",
        "status": "available",
    }


def europe_fact():
    return {**global_fact(), "geography": "Europe"}


def test_merge_preserves_same_metric_for_two_geographies(tmp_path):
    con = macro_indicators.connect(tmp_path / "market_data.sqlite")
    macro_indicators.merge_non_oil_attribution_facts(
        con, [global_fact(), europe_fact()]
    )
    assert [
        row["geography"]
        for row in macro_indicators.load_non_oil_attribution_facts(con, "copper")
    ] == ["Europe", "Global"]


def test_merge_non_oil_attribution_facts_upserts_existing_key(tmp_path):
    con = macro_indicators.connect(tmp_path / "market_data.sqlite")
    macro_indicators.merge_non_oil_attribution_facts(con, [global_fact()])
    macro_indicators.merge_non_oil_attribution_facts(
        con, [{**global_fact(), "value": 25000.0}]
    )
    rows = macro_indicators.load_non_oil_attribution_facts(con, "copper")
    assert len(rows) == 1
    assert rows[0]["value"] == 25000.0


def test_load_non_oil_attribution_facts_filters_by_commodity(tmp_path):
    con = macro_indicators.connect(tmp_path / "market_data.sqlite")
    lumber_fact = {
        **global_fact(),
        "commodity_id": "lumber",
        "source_name": "Food and Agriculture Organization of the United Nations",
        "source_url": "https://www.fao.org/faostat/en/#data/FO",
        "factor_category": "trade",
        "geography": "World",
        "units": "m3",
    }
    macro_indicators.merge_non_oil_attribution_facts(
        con, [global_fact(), lumber_fact]
    )
    rows = macro_indicators.load_non_oil_attribution_facts(con, "lumber")
    assert len(rows) == 1
    assert rows[0]["commodity_id"] == "lumber"


def test_load_non_oil_attribution_facts_returns_empty_for_unknown_commodity(
    tmp_path,
):
    con = macro_indicators.connect(tmp_path / "market_data.sqlite")
    macro_indicators.merge_non_oil_attribution_facts(con, [global_fact()])
    assert macro_indicators.load_non_oil_attribution_facts(con, "iron_ore") == []


def test_merge_non_oil_attribution_refresh_status_upserts_same_source(tmp_path):
    con = macro_indicators.connect(tmp_path / "market_data.sqlite")
    macro_indicators.merge_non_oil_attribution_refresh_status(
        con,
        "copper",
        "http://www.coppercouncil.org/iwcc-statistics-and-data",
        "unavailable",
        "boom",
    )
    macro_indicators.merge_non_oil_attribution_refresh_status(
        con,
        "copper",
        "http://www.coppercouncil.org/iwcc-statistics-and-data",
        "available",
        None,
    )
    rows = macro_indicators.load_non_oil_attribution_refresh_status(con)
    assert len(rows) == 1
    assert rows[0]["status"] == "available"
    assert rows[0]["error_message"] is None

from json import dumps
from sqlite3 import connect

import pytest

from app.db import benchmark_market_data, economic_confirmation, gdp_market_relationships, growth_cycle, us_rates_liquidity
from app.db.macro_data_freshness import load_observations, load_task_history
from app.db.ism_services_ai import promote_services_extraction
from app.services.macro_data_freshness_catalog import load_catalog
from app.services.macro_data_freshness import get_overview
from app.db.macro_source_lineage import replace_lineage


def rows(*ids):
    return [r for r in load_catalog()["datasets"] if r["id"] in ids]


def database(path):
    for module in (us_rates_liquidity, benchmark_market_data, gdp_market_relationships, economic_confirmation):
        con = module.connect(path)
        con.close()
    con = us_rates_liquidity.connect(path)
    growth_cycle.init_db(con)
    return con


def test_absent_database_is_unavailable_and_is_not_created(tmp_path):
    path = tmp_path / "absent.sqlite"
    result = load_observations(rows("macro:m2_money_stock"), path)
    assert result["macro:m2_money_stock"]["availability"] == "unavailable"
    assert not path.exists()


def test_empty_readable_table_is_missing_but_missing_table_is_unavailable(tmp_path):
    path = tmp_path / "data.sqlite"
    con = connect(path)
    con.execute("create table macro_indicator_points(series_id text,date text,value real,source text)")
    con.close()
    selected = rows("macro:m2_money_stock", "rate:treasury_10y")
    result = load_observations(selected, path)
    assert result["macro:m2_money_stock"]["availability"] == "missing"
    assert result["rate:treasury_10y"]["availability"] == "unavailable"


@pytest.mark.parametrize("lineage_value,source_id,expected", [(3, "CPIAUCSL", "2026-10-01"), (4, "CPIAUCSL", None), (3, "OTHER", None)])
def test_resampled_lineage_requires_matching_current_value_and_source(tmp_path, lineage_value, source_id, expected):
    path = tmp_path / "data.sqlite"
    con = database(path)
    con.execute("insert into macro_indicator_points values(?,?,?,?)", ("cpi_yoy", "2026-11-15", 3, "source"))
    replace_lineage(con, "macro:cpi_yoy", [{"date": "2026-11-15", "value": lineage_value, "source_date": "2026-10-01", "source_series_id": source_id, "source_hash": "a" * 64}], "captured_at_import")
    con.close()
    result = load_observations(rows("macro:cpi_yoy"), path)["macro:cpi_yoy"]
    assert result.get("source_observation_date") == expected


def test_benchmark_reader_retains_a_completed_close_beneath_intraday_row(tmp_path):
    path = tmp_path / "data.sqlite"
    con = database(path)
    con.executemany("insert into benchmark_prices(benchmark_id,date,close,source) values(?,?,?,?)", [("us_sp500", "2026-11-16", 6000, "source"), ("us_sp500", "2026-11-17", 6001, "source")])
    con.commit()
    con.close()
    result = load_observations(rows("benchmark:us_sp500"), path)["benchmark:us_sp500"]
    assert {r["current_period"] for r in result["recent_observations"]} == {"2026-11-16", "2026-11-17"}


@pytest.mark.parametrize("id,sql,values,period", [
    ("macro:m2_money_stock", "insert into macro_indicator_points values(?,?,?,?)", ("m2_money_stock", "2026-09-01", 10, "source"), "2026-09-01"),
    ("rate:treasury_10y", "insert into us_rate_points values(?,?,?,?,?)", ("treasury_10y", "2026-11-08", 4, "file", "sheet"), "2026-11-08"),
    ("benchmark:us_sp500", "insert into benchmark_prices(benchmark_id,date,close,source) values(?,?,?,?)", ("us_sp500", "2026-11-12", 6000, "source"), "2026-11-12"),
    ("regional:pacific:nfib_sbo_optimism", "insert into macro_indicator_regional_observations values(?,?,?,?,?)", ("pacific", "nfib_sbo_optimism", "2026-09-30", 98, "available"), "2026-09-30"),
    ("gdp:lag", "insert into gdp_lag_rows values(?,?,?,?,?,?,?,?)", ("us_sp500_gdp", "2026-09-30", 3, 5, 3, .6, "file", "sheet"), "2026-09-30"),
])
def test_series_readers_load_actual_periods_without_writes(tmp_path, id, sql, values, period):
    path = tmp_path / "data.sqlite"
    con = database(path)
    con.execute(sql, values)
    con.commit()
    con.close()
    before = path.read_bytes()
    result = load_observations(rows(id), path)[id]
    assert result["availability"] == "available"
    assert result["current_period"] == period
    assert path.read_bytes() == before


def test_fomc_extraction_keeps_latest_document_version_separate(tmp_path):
    path = tmp_path / "data.sqlite"
    con = database(path)
    con.execute("insert into macro_events(event_id,event_type,start_date,display_month,title,source) values(?,?,?,?,?,?)", ("fomc_2026_10_27", "fomc_meeting", "2026-10-27", "2026-10-01", "FOMC", "Fed"))
    con.execute("insert into macro_event_documents values(?,?,?,?,?,?)", ("fomc_2026_10_27", "statement", "https://www.federalreserve.gov/", "text", "new-hash", "2026-10-28T18:05:00Z"))
    con.commit()
    con.close()
    result = load_observations(rows("fomc:policy_tone", "fomc:statement", "fomc:calendar"), path)
    assert result["fomc:policy_tone"]["availability"] == "missing"
    assert result["fomc:policy_tone"]["source"]["source_hash"] == "new-hash"
    assert result["fomc:statement"]["current_period"] == "2026-10-27"
    assert result["fomc:calendar"]["event_periods"] == ["2026-10-27"]


def test_regional_unavailable_latest_value_is_not_hidden_by_old_valid_row(tmp_path):
    path = tmp_path / "data.sqlite"
    con = database(path)
    con.executemany("insert into macro_indicator_regional_observations values(?,?,?,?,?)", [("pacific", "nfib_sbo_optimism", "2026-06-30", 98, "available"), ("pacific", "nfib_sbo_optimism", "2026-09-30", None, "unavailable")])
    con.commit()
    con.close()
    result = load_observations(rows("regional:pacific:nfib_sbo_optimism"), path)
    assert result["regional:pacific:nfib_sbo_optimism"]["availability"] == "invalid"


def test_cot_reader_never_substitutes_another_contract(tmp_path):
    path = tmp_path / "data.sqlite"
    con = connect(path)
    con.execute("create table cot_observations(commodity_id text,cftc_contract_market_code text,report_date text,open_interest real)")
    con.executemany("insert into cot_observations values(?,?,?,?)", [("aluminium", "191691", "2026-06-09", 2000), ("aluminium", "different", "2026-11-10", 5000)])
    con.commit()
    con.close()
    catalog = load_catalog()
    selected = [row for row in catalog["datasets"] if row["id"].startswith("cot:aluminium:")]
    evidence = load_observations(selected, path)[selected[0]["id"]]
    assert evidence["current_period"] == "2026-06-09"
    assert evidence["availability"] == "available"
    assert "release_date" not in evidence


def test_economic_and_shfe_readers_preserve_distinct_periods(tmp_path):
    path = tmp_path / "data.sqlite"
    con = connect(path)
    con.executescript("create table economic_confirmation_current_observations(series_id text,reference_period text,value real,release_date text,as_of_timestamp text,source_hash text,vintage_id text); create table shfe_cu_main_daily(date text,close real,retrieved_at text); create table shfe_cu_contract_daily(trade_date text,close real,retrieved_at text);")
    con.execute("insert into economic_confirmation_current_observations values(?,?,?,?,?,?,?)", ("initial_claims_sa", "2026-11-07", 200000, "2026-11-12", "2026-11-12T14:00:00Z", "hash", "v1"))
    con.execute("insert into shfe_cu_main_daily values(?,?,?)", ("2026-11-12", 80000, "2026-11-12T10:00:00Z"))
    con.execute("insert into shfe_cu_contract_daily values(?,?,?)", ("2026-11-11", 81000, "2026-11-11T10:00:00Z"))
    con.commit()
    con.close()
    result = load_observations(rows("economic:initial_claims_sa", "shfe:main", "shfe:contracts"), path)
    assert result["economic:initial_claims_sa"]["release_date"] == "2026-11-12"
    assert result["economic:initial_claims_sa"]["current_period"] == "2026-11-07"
    assert result["shfe:main"]["current_period"] == "2026-11-12"
    assert result["shfe:contracts"]["current_period"] == "2026-11-11"


def test_ism_rankings_only_take_hash_from_matching_promoted_signals(tmp_path):
    path = tmp_path / "data.sqlite"
    con = database(path)
    con.execute("insert into ism_report_snapshots(report_id,report_month,title,source_url,source_hash,fetched_at,parse_status,next_release_label,survey_type) values(?,?,?,?,?,?,?,?,?)", ("ism_services_2026_10", "2026-10-01", "Services", "https://www.ismworld.org/", "new", "2026-11-04T16:00:00Z", "ok", "", "services"))
    con.execute("insert into ism_industry_rankings values(?,?,?,?,?,?)", ("services", "2026-10-01", "Information", "growth", 1, "ISM AI extraction"))
    con.execute("insert into ism_report_industry_signals values(?,?,?,?,?,?,?,?,?)", ("ism_services_2026_10", "2026-10-01", "overall_growth", "growth", "Information", 1, "evidence", "https://www.ismworld.org/", "new"))
    con.commit()
    con.close()
    result = load_observations(rows("ism:services:industry_rankings"), path)
    assert result["ism:services:industry_rankings"]["source_hash"] == "new"
    con = connect(path)
    con.execute("update ism_industry_rankings set rank=2")
    con.commit()
    con.close()
    result = load_observations(rows("ism:services:industry_rankings"), path)
    assert result["ism:services:industry_rankings"].get("source_hash") is None


def services_extraction():
    from app.tools.ism_services_ai_extraction import SERVICES_SERIES_IDS
    return {
        "report": {"report_id": "ism_services_2026_10", "report_month": "2026-10-01", "title": "October 2026 Services ISM Report On Business", "source_name": "ismworld", "source_url": "https://www.ismworld.org/"},
        "at_a_glance_rows": [{"series_id": sid, "label": sid, "current_value": 52, "previous_value": 51, "point_change": 1, "direction": "growing", "rate_of_change": "faster", "trend_months": 2} for sid in sorted(SERVICES_SERIES_IDS)],
        "industry_signals": [], "respondent_comments": [], "commodities": [],
        "narrative_facts": {"consecutive_expansion_months": None, "services_economy_gdp_share_percent": None, "broad_based_expansion_mentioned": False, "inflationary_pressure_mentioned": False},
    }


@pytest.mark.parametrize("source_status,expected", [("prepared", "processing"), ("failed", "unknown")])
def test_newer_ism_source_version_is_independent_from_promoted_output(tmp_path, source_status, expected):
    from datetime import datetime
    path = tmp_path / "data.sqlite"
    con = database(path)
    con.execute("insert into ism_report_snapshots(report_id,report_month,title,source_url,source_hash,fetched_at,parse_status,next_release_label,survey_type) values(?,?,?,?,?,?,?,?,?)", ("ism_services_2026_10", "2026-10-01", "Services", "https://www.ismworld.org/", "old", "2026-11-04T16:00:00Z", "ok", "", "services"))
    con.execute("insert into ism_report_comments values(?,?,?,?,?,?,?)", ("ism_services_2026_10", 0, "2026-10-01", "Information", "comment", "https://www.ismworld.org/", "old"))
    con.execute("insert into macro_indicator_points values(?,?,?,?)", ("ism_services_pmi", "2026-10-01", 52, "ISM"))
    con.execute("insert into ism_at_a_glance_rows values(?,?,?,?,?,?,?,?,?,?,?,?)", ("ism_services_2026_10", "2026-10-01", "ism_services_pmi", "PMI", 52, 51, 1, "growing", "faster", 2, "https://www.ismworld.org/", "old"))
    con.execute("insert into ism_report_source_snapshots(source_url,source_name,survey_type,source_hash,fetched_at,raw_html,parse_status,report_id,report_month) values(?,?,?,?,?,?,?,?,?)", ("https://www.ismworld.org/", "ismworld", "services", "new", "2026-11-05T16:00:00Z", "new report", source_status, "ism_services_2026_10", "2026-10-01"))
    con.commit()
    con.close()
    result = get_overview(db_path=path, notification_db_path=tmp_path / "none.sqlite", as_of=datetime.fromisoformat("2026-11-13T12:00:00Z"))
    row = next(r for r in result["datasets"] if r["id"] == "ism:services:comments")
    assert row["status"] == expected
    assert next(r for r in result["datasets"] if r["id"] == "ism:services:core")["status"] == expected
    assert next(r for r in result["datasets"] if r["id"] == "macro:ism_services_pmi")["status"] == expected


@pytest.mark.parametrize("older_output", [False, True])
def test_real_services_promotion_with_empty_outputs_is_complete(tmp_path, older_output):
    from datetime import datetime
    path = tmp_path / "data.sqlite"
    con = database(path)
    source = {"source_url": "https://www.ismworld.org/", "source_hash": "new", "updated_at": "2026-11-04T16:00:00Z"}
    if older_output:
        con.execute("insert into ism_report_snapshots(report_id,report_month,title,source_url,source_hash,fetched_at,parse_status,next_release_label,survey_type) values(?,?,?,?,?,?,?,?,?)", ("ism_services_2026_09", "2026-09-01", "September Services", "https://www.ismworld.org/", "old", "2026-10-05T16:00:00Z", "ok", "", "services"))
        con.execute("insert into ism_report_commodities values(?,?,?,?,?,?)", ("ism_services_2026_09", "2026-09-01", "Copper", "up", 1, "old"))
        con.commit()
    promoted = promote_services_extraction(con, services_extraction(), source)
    assert promoted["commodities"] == 0
    con.close()
    result = get_overview(db_path=path, notification_db_path=tmp_path / "none.sqlite", as_of=datetime.fromisoformat("2026-11-13T12:00:00Z"))
    selected = [r for r in result["datasets"] if r["id"] in {"ism:services:commodities", "ism:services:comments", "ism:services:industry_signals", "ism:services:industry_rankings"}]
    assert len(selected) == 4
    assert all(row["status"] == "current" for row in selected)


def test_task_history_matches_stages_beyond_recent_25_and_ignores_parent_success(tmp_path):
    path = tmp_path / "tasks.sqlite"
    con = connect(path)
    con.executescript("create table job_notification_runs(sequence integer primary key,run_id text,job_id text,status text,payload text); create table job_notification_children(run_id text,name text,payload text);")
    for n in range(40):
        payload = {"run_id": f"run{n}", "origin": "command_line", "ended_at": f"2026-11-13T{n % 24:02d}:00:00Z", "status": "succeeded"}
        con.execute("insert into job_notification_runs values(?,?,?,?,?)", (n, f"run{n}", "macro_refresh", "succeeded", dumps(payload)))
    con.execute("insert into job_notification_children values(?,?,?)", ("run0", "m2_fred_fetch", dumps({"status": "ok", "updated_at": "2026-11-01T12:00:00Z"})))
    con.execute("insert into job_notification_children values(?,?,?)", ("run39", "m2_fred_fetch", dumps({"status": "failed", "updated_at": "2026-11-13T12:00:00Z", "summary": "secret raw error"})))
    con.execute("insert into job_notification_children values(?,?,?)", ("run0", "m2_fred_import", dumps({"status": "ok", "updated_at": "2026-11-01T12:01:00Z"})))
    con.commit()
    con.close()
    result = load_task_history(rows("macro:m2_money_stock", "macro:cpi_yoy", "benchmark:us_sp500"), path)
    item = result["macro:m2_money_stock"]
    assert item["last_successful_check"]["run_id"] == "run0"
    assert item["last_attempt"]["status"] == "failed"
    assert item["last_processing"]["at"] == "2026-11-01T12:01:00Z"
    assert result["macro:cpi_yoy"]["last_successful_check"] is None
    assert result["benchmark:us_sp500"]["last_successful_check"] is None
    assert "secret" not in dumps(result)
    assert item["last_attempt"]["href"] == "/notifications.html?run=run39"


def test_history_missing_file_is_not_created(tmp_path):
    path = tmp_path / "none.sqlite"
    result = load_task_history(rows("macro:m2_money_stock"), path)
    assert result["macro:m2_money_stock"]["availability"] == "unavailable"
    assert not path.exists()

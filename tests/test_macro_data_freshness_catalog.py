from copy import deepcopy
from json import dumps

import pytest

from app.data_sources.nfib_sbet_api import REGIONS, SERIES_TO_INDICATOR
from app.data_sources.nfib_sbet import SERIES_IDS
from app.resources import resource_path
from app.services.macro_data_freshness_catalog import load_catalog
from app.services.nfib_sbet_regional_import import NATIONAL_REGION_ID
from app.tools.benchmark_market_data import BENCHMARK_YAHOO_SYMBOLS
from app.tools.ism_services_ai_extraction import SERVICES_SERIES_IDS
from scripts.import_us_rates_liquidity import RATE_SERIES_CONFIG


def test_catalog_covers_configured_benchmarks_rates_surveys_regions_and_contracts():
    catalog = load_catalog()
    rows = catalog["datasets"]
    ids = {row["id"] for row in rows}
    assert len(ids) == len(rows)
    assert {f"benchmark:{x['benchmark_id']}" for x in BENCHMARK_YAHOO_SYMBOLS} <= ids
    assert {f"rate:{x['series_id']}" for x in RATE_SERIES_CONFIG.values()} <= ids
    assert {f"macro:{x}" for x in SERIES_IDS | SERVICES_SERIES_IDS} <= ids
    assert {f"regional:{region}:{indicator}" for region in {*REGIONS, NATIONAL_REGION_ID} for indicator in SERIES_TO_INDICATOR} <= ids
    assert {"fomc:calendar", "fomc:statement", "fomc:minutes", "fomc:policy_tone", "fomc:minutes_structure"} <= ids
    assert {"gdp:lag", "gdp:quad", "shfe:main", "shfe:contracts"} <= ids
    import json
    allowlist = json.loads(resource_path("cot_extreme_allowlist").read_text())
    assert {f"cot:{x['commodity_id']}:{x['contract_code']}" for x in allowlist["entries"] if x["active"]} <= ids
    assert not any(x in ids for x in ("macro:sp500_pe", "macro:lumber", "gdp:eu", "gdp:cn"))
    assert {row["lane"] for row in rows} == {"fred_macro", "credit", "yahoo", "ism_manufacturing", "ism_services", "consumer", "census", "nfib", "fomc", "tracked_commodities", "cftc", "eia", "shfe", "dce_sina", "dol", "bls", "federal_reserve"}
    assert {s["job_id"] for s in catalog["collection_schedules"]} == {"macro_refresh", "investing_refresh"}


def test_catalog_excludes_artifacts_not_promoted_by_the_current_cron_pipeline():
    ids = {row["id"] for row in load_catalog()["datasets"]}
    assert not ids & {"gdp:raw", "ism:manufacturing:summary", "ism:services:summary"}


def test_catalog_separates_storage_frequency_and_derived_outputs():
    rows = {r["id"]: r for r in load_catalog()["datasets"]}
    assert rows["rate:treasury_10y"]["storage_frequency"] == "Weekly (Sunday labels)"
    assert rows["macro:cpi_yoy"]["period_basis"] == "weekly_resample"
    assert rows["fomc:policy_tone"]["storage"]["kind"] == "fomc_extraction"
    assert len(rows["macro:copper_comex"]["tasks"]) == 2
    assert rows["regional:pacific:nfib_sbo_optimism"]["frequency"] == "Quarterly (3-month aggregate)"


@pytest.mark.parametrize("mutate, message", [
    (lambda p: p["datasets"].append(deepcopy(p["datasets"][0])), "dataset id is duplicated"),
    (lambda p: p["datasets"][0].update(schedule_id="absent"), "schedule is unknown"),
    (lambda p: p.update(version=""), "catalog version is required"),
])
def test_catalog_rejects_invalid_contract(tmp_path, mutate, message):
    payload = load_catalog()
    mutate(payload)
    path = tmp_path / "catalog.json"
    path.write_text(dumps(payload))
    with pytest.raises(ValueError, match=message):
        load_catalog(path)


def test_current_quarter_policy_only_covers_configured_nfib_api_datasets():
    rows = load_catalog()['datasets']
    selected = [row for row in rows if (row.get('freshness_policy') or {}).get('kind') == 'current_quarter']
    assert len(selected) == 44
    assert all(row['storage']['kind'] == 'regional' and row['period_basis'] == 'quarter' for row in selected)
    assert all(row['freshness_policy']['timezone'] == 'America/New_York' for row in selected)

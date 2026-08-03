import argparse
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.data_sources import bls_employment_situation
from app.data_sources import dol_ui_claims
from app.data_sources import federal_reserve_g17
from app.db import economic_confirmation
from app.http_client import HttpClient

DEFAULT_DB_PATH = economic_confirmation.DEFAULT_DB_PATH

DOL_NATIONAL_CLAIMS_URL = "https://oui.doleta.gov/unemploy/claims.asp"
DOL_RELEASE_URL = "https://www.dol.gov/ui/data.pdf"
BLS_ESR_OVERVIEW_URL = "https://www.bls.gov/news.release/empsit.htm"
BLS_ESR_HOUSEHOLD_URL = "https://www.bls.gov/news.release/empsit.a.htm"
BLS_ESR_ESTABLISHMENT_URL = "https://www.bls.gov/news.release/empsit.b.htm"
G17_PAGE_URL = "https://www.federalreserve.gov/releases/g17/Current/default.htm"
G17_DATA_URL = (
    "https://www.federalreserve.gov/datadownload/Output.aspx?rel=G17&series="
    "809009461b1cba2fd5b4cf5557d9d663&lastobs=&from=&to=&filetype=csv"
    "&label=include&layout=seriesrow&type=package"
)

CLAIMS_SOURCE_CONTRACTS = {
    "initial_claims_sa": {
        "metric_id": "initial_claims_trend",
        "source": "DOL",
        "seasonal_adjustment": "seasonally_adjusted",
        "raw_frequency": "weekly",
        "aggregation": "four_week_moving_average",
        "method_version": "claims_trend_v1",
    },
    "continuing_claims_sa": {
        "metric_id": "continuing_claims_trend",
        "source": "DOL",
        "seasonal_adjustment": "seasonally_adjusted",
        "raw_frequency": "weekly",
        "aggregation": "four_week_moving_average",
        "method_version": "claims_trend_v1",
    },
}

BLS_SOURCE_CONTRACTS = {
    "nonfarm_payrolls_change": {
        "metric_id": "nonfarm_payrolls_change",
        "source": "BLS Employment Situation Summary Table B",
        "seasonal_adjustment": "seasonally_adjusted",
        "raw_frequency": "monthly",
        "unit": "thousands, over-the-month change",
        "method_version": "bls_esr_html_v1",
    },
    "payrolls_3m_average_change": {
        "metric_id": "payrolls_3m_average_change",
        "source": "BLS Employment Situation Summary Table B",
        "seasonal_adjustment": "seasonally_adjusted",
        "raw_frequency": "monthly",
        "unit": "thousands, 3-month average over-the-month change",
        "method_version": "bls_esr_html_v1",
    },
}


def _fetch_bytes(client, url, label):
    try:
        response = client.request("GET", url, timeout=60)
    except httpx.HTTPError as exc:
        raise ValueError(f"failed to fetch {label} from {url}: {exc}") from exc
    return response.content


def _save_cache(cache_dir, name, content):
    if cache_dir is None:
        return None
    directory = Path(cache_dir)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / name
    target.write_bytes(content)
    return target


def _import_source(name, fetch, store):
    try:
        return store(fetch())
    except ValueError as exc:
        print(f"{name}: failed - {exc}", file=sys.stderr)
        return None


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Import economic confirmation source data"
    )
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--cache-dir", type=Path, default=None)
    parser.add_argument("--dol-national-claims-url", type=str, default=None)
    parser.add_argument("--dol-release-url", type=str, default=None)
    parser.add_argument("--bls-overview-url", type=str, default=None)
    parser.add_argument("--bls-household-url", type=str, default=None)
    parser.add_argument("--bls-establishment-url", type=str, default=None)
    parser.add_argument("--g17-page-url", type=str, default=None)
    parser.add_argument("--g17-data-url", type=str, default=None)
    args = parser.parse_args(argv)
    client = HttpClient()
    national_url = args.dol_national_claims_url or DOL_NATIONAL_CLAIMS_URL
    release_url = args.dol_release_url or DOL_RELEASE_URL
    esr_overview_url = args.bls_overview_url or BLS_ESR_OVERVIEW_URL
    esr_household_url = args.bls_household_url or BLS_ESR_HOUSEHOLD_URL
    esr_establishment_url = args.bls_establishment_url or BLS_ESR_ESTABLISHMENT_URL
    g17_page_url = args.g17_page_url or G17_PAGE_URL
    g17_data_url = args.g17_data_url or G17_DATA_URL
    con = economic_confirmation.connect(args.db_path)
    try:
        counts = {
            "claims_history": _import_source(
                "claims_history",
                lambda: dol_ui_claims.fetch_national_claims_history(
                    client, national_url
                ),
                lambda observations: (
                    economic_confirmation.replace_national_claims_history_batch(
                        con, observations
                    )
                ),
            ),
            "claims_release": _import_source(
                "claims_release",
                lambda: dol_ui_claims.fetch_claims_release(client, release_url),
                lambda observations: economic_confirmation.record_vintage_batch(
                    con, observations
                ),
            ),
            "esr": _import_source(
                "esr",
                lambda: _fetch_esr(
                    client,
                    esr_overview_url,
                    esr_household_url,
                    esr_establishment_url,
                    args.cache_dir,
                ),
                lambda result: _record_esr(con, result),
            ),
            "g17": _import_source(
                "g17",
                lambda: federal_reserve_g17.fetch_g17_release(
                    client, g17_page_url, g17_data_url
                ),
                lambda result: _record_g17(con, result, args.cache_dir),
            ),
        }
        if counts["claims_history"] is not None:
            _record_claims_contracts(con)
    finally:
        con.close()
    print(f"db: {args.db_path}")
    for key, value in counts.items():
        if value is not None:
            print(f"{key}: {value}")
    return 1 if any(value is None for value in counts.values()) else 0


def _record_claims_contracts(con):
    for series_id, contract in CLAIMS_SOURCE_CONTRACTS.items():
        economic_confirmation.record_source_contract(con, series_id, contract)


def _record_esr(con, result):
    count = economic_confirmation.record_vintage_batch(con, result["observations"])
    economic_confirmation.record_scheduled_events(con, result["scheduled_events"])
    for series_id, contract in BLS_SOURCE_CONTRACTS.items():
        economic_confirmation.record_source_contract(con, series_id, contract)
    return count


def _fetch_esr(client, overview_url, household_url, establishment_url, cache_dir):
    overview_html = _fetch_bytes(client, overview_url, "employment situation overview")
    household_html = _fetch_bytes(
        client, household_url, "employment situation household table"
    )
    establishment_html = _fetch_bytes(
        client, establishment_url, "employment situation establishment table"
    )
    _save_cache(cache_dir, "bls_esr_overview.html", overview_html)
    _save_cache(cache_dir, "bls_esr_household.html", household_html)
    _save_cache(cache_dir, "bls_esr_establishment.html", establishment_html)
    return bls_employment_situation.parse_employment_situation_html(
        overview_html,
        household_html,
        establishment_html,
        overview_url,
        household_url,
        establishment_url,
    )


def _record_g17(con, result, cache_dir):
    _save_cache(cache_dir, "g17_ip.csv", result["csv"])
    return economic_confirmation.record_vintage_batch(con, result["observations"])


if __name__ == "__main__":
    raise SystemExit(main())

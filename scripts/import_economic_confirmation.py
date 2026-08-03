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

DOL_INITIAL_CLAIMS_URL = "https://oui.doleta.gov/unemploy/Chartbook/a2.asp"
DOL_CONTINUING_CLAIMS_URL = "https://oui.doleta.gov/unemploy/Chartbook/a3.asp"
DOL_RELEASE_URL = "https://www.dol.gov/ui/data.pdf"
BLS_ESR_URL = "https://www.bls.gov/news.release/pdf/empsit.pdf"
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
    parser.add_argument("--dol-initial-url", type=str, default=None)
    parser.add_argument("--dol-continuing-url", type=str, default=None)
    parser.add_argument("--dol-release-url", type=str, default=None)
    parser.add_argument("--bls-esr-url", type=str, default=None)
    parser.add_argument("--g17-page-url", type=str, default=None)
    parser.add_argument("--g17-data-url", type=str, default=None)
    args = parser.parse_args(argv)
    client = HttpClient()
    initial_url = args.dol_initial_url or DOL_INITIAL_CLAIMS_URL
    continuing_url = args.dol_continuing_url or DOL_CONTINUING_CLAIMS_URL
    release_url = args.dol_release_url or DOL_RELEASE_URL
    esr_url = args.bls_esr_url or BLS_ESR_URL
    g17_page_url = args.g17_page_url or G17_PAGE_URL
    g17_data_url = args.g17_data_url or G17_DATA_URL
    con = economic_confirmation.connect(args.db_path)
    try:
        counts = {
            "claims_history": _import_source(
                "claims_history",
                lambda: dol_ui_claims.fetch_claims_history(
                    client, initial_url, continuing_url
                ),
                lambda observations: economic_confirmation.record_vintage_batch(
                    con, observations
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
                lambda: bls_employment_situation.parse_employment_situation_release(
                    _fetch_bytes(client, esr_url, "employment situation pdf"), esr_url
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
    return count


def _record_g17(con, result, cache_dir):
    _save_cache(cache_dir, "g17_ip.csv", result["csv"])
    return economic_confirmation.record_vintage_batch(con, result["observations"])


if __name__ == "__main__":
    raise SystemExit(main())

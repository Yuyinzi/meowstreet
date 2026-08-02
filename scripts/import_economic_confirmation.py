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
G17_URL = "https://www.federalreserve.gov/releases/g17/Current/default.htm"

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
    parser.add_argument("--g17-url", type=str, default=None)
    parser.add_argument("--g17-release-date", type=str, default=None)
    args = parser.parse_args(argv)
    try:
        client = HttpClient()
        initial_url = args.dol_initial_url or DOL_INITIAL_CLAIMS_URL
        continuing_url = args.dol_continuing_url or DOL_CONTINUING_CLAIMS_URL
        release_url = args.dol_release_url or DOL_RELEASE_URL
        esr_url = args.bls_esr_url or BLS_ESR_URL
        g17_url = args.g17_url or G17_URL

        claims_history = dol_ui_claims.fetch_claims_history(
            client, initial_url, continuing_url
        )
        claims_release = dol_ui_claims.fetch_claims_release(client, release_url)

        esr_pdf = _fetch_bytes(client, esr_url, "employment situation pdf")
        _save_cache(args.cache_dir, "employment_situation.pdf", esr_pdf)
        esr_result = bls_employment_situation.parse_employment_situation_release(
            esr_pdf, esr_url
        )

        counts = {}
        con = economic_confirmation.connect(args.db_path)
        try:
            counts["claims_history"] = economic_confirmation.record_vintage_batch(
                con, claims_history
            )
            counts["claims_release"] = economic_confirmation.record_vintage_batch(
                con, claims_release
            )
            counts["esr"] = economic_confirmation.record_vintage_batch(
                con, esr_result["observations"]
            )
            economic_confirmation.record_scheduled_events(
                con, esr_result["scheduled_events"]
            )
            for series_id, contract in CLAIMS_SOURCE_CONTRACTS.items():
                economic_confirmation.record_source_contract(con, series_id, contract)
            if args.g17_release_date:
                g17_csv = _fetch_bytes(client, g17_url, "g17 csv")
                _save_cache(args.cache_dir, "g17_ip.csv", g17_csv)
                g17_result = federal_reserve_g17.parse_g17_release(
                    {"release_date": args.g17_release_date, "csv": g17_csv},
                    g17_url,
                )
                counts["g17"] = economic_confirmation.record_vintage_batch(
                    con, g17_result["observations"]
                )
            else:
                print("g17: skipped (no --g17-release-date)")
        finally:
            con.close()
        print(f"db: {args.db_path}")
        for key, value in counts.items():
            print(f"{key}: {value}")
        return 0
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

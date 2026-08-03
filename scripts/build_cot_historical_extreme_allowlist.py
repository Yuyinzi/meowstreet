#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services import cot_historical_extremes_catalog as allowlist_service

DEFAULT_CACHE_DIR = ROOT / "data" / ""
DEFAULT_OUTPUT = allowlist_service.DEFAULT_ALLOWLIST_PATH

ALLOWLIST_RECORDS = [
    {
        "commodity_id": "crude_oil_wti",
        "market_name": "CRUDE OIL, LIGHT SWEET-WTI - ICE FUTURES EUROPE",
        "contract_code": "067411",
    },
    {
        "commodity_id": "crude_oil_brent",
        "market_name": "BRENT LAST DAY - NEW YORK MERCANTILE EXCHANGE",
        "contract_code": "06765T",
    },
    {
        "commodity_id": "heating_oil",
        "market_name": "NY HARBOR ULSD - NEW YORK MERCANTILE EXCHANGE",
        "contract_code": "022651",
    },
    {
        "commodity_id": "natural_gas",
        "market_name": "NATURAL GAS INDEX: EP SAN JUAN - ICE FUTURES ENERGY DIV",
        "contract_code": "0233AX",
        "active": False,
    },
    {
        "commodity_id": "us_natural_gas",
        "market_name": "NAT GAS NYME - NEW YORK MERCANTILE EXCHANGE",
        "contract_code": "023651",
    },
    {
        "commodity_id": "palladium",
        "market_name": "PALLADIUM - NEW YORK MERCANTILE EXCHANGE",
        "contract_code": "075651",
    },
    {
        "commodity_id": "platinum",
        "market_name": "PLATINUM - NEW YORK MERCANTILE EXCHANGE",
        "contract_code": "076651",
    },
    {
        "commodity_id": "silver",
        "market_name": "SILVER - COMMODITY EXCHANGE INC.",
        "contract_code": "084691",
    },
    {
        "commodity_id": "gold",
        "market_name": "GOLD - COMMODITY EXCHANGE INC.",
        "contract_code": "088691",
    },
    {
        "commodity_id": "copper",
        "market_name": "COPPER- #1 - COMMODITY EXCHANGE INC.",
        "contract_code": "085692",
    },
    {
        "commodity_id": "aluminium",
        "market_name": "ALUMINUM - COMMODITY EXCHANGE INC.",
        "contract_code": "191691",
    },
    {
        "commodity_id": "steel",
        "market_name": "STEEL-HRC - COMMODITY EXCHANGE INC.",
        "contract_code": "192651",
    },
]


def build_arg_parser():
    parser = argparse.ArgumentParser(
        description="Build the  cot historical extreme allowlist from cached CFTC archives."
    )
    parser.add_argument("--cache-dir", default=str(DEFAULT_CACHE_DIR))
    parser.add_argument("--output-path", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--years", default="2021,2022,2023,2024,2025,2026")
    return parser


def main(argv=None):
    args = build_arg_parser().parse_args(argv)
    years = [int(year.strip()) for year in args.years.split(",")]
    try:
        pairs = allowlist_service.scan_cftc_archive_contract_pairs(
            Path(args.cache_dir), years
        )
        records = allowlist_service.derive_allowlist_records(ALLOWLIST_RECORDS, pairs)
        payload = allowlist_service.write_cot_historical_extreme_allowlist(
            args.output_path, records
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    active = [record["commodity_id"] for record in records if record["active"]]
    inactive = [record["commodity_id"] for record in records if not record["active"]]
    print(
        json.dumps(
            {
                "output": str(Path(args.output_path)),
                "version": payload["version"],
                "active": active,
                "inactive": inactive,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

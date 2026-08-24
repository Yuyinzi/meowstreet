import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db import us_rates_liquidity
from scripts import generate_credit_ai_interpretation
from scripts import import_us_corporate_credit
from scripts import import_us_macro_indicators
from scripts import import_us_rates_liquidity


RATES_FRED_SERIES = tuple(sorted(import_us_rates_liquidity.FRED_RATE_SERIES_CONFIG))
MACRO_FRED_SERIES = tuple(sorted(import_us_macro_indicators.FRED_MACRO_SERIES_CONFIG))
CREDIT_FRED_SERIES = tuple(sorted(import_us_corporate_credit.FRED_SERIES_MAP))
FRED_SERIES_GROUPS = {
    "rates": RATES_FRED_SERIES,
    "macro": MACRO_FRED_SERIES,
    "credit": CREDIT_FRED_SERIES,
}


def _print_fetched(label, fetched):
    if fetched is None:
        print(f"{label} fetch skipped")
        return
    print(f"{label} fetched: {len(fetched)}")
    for series_id, path in fetched.items():
        print(f"  {series_id}: {path}")


def _print_imported(label, inserted):
    if inserted is None:
        print(f"{label} import skipped")
        return
    print(f"{label} imported:")
    for series_id, count in inserted.items():
        print(f"  {series_id}: {count}")


def _generate_credit_interpretation(db_path):
    return generate_credit_ai_interpretation.main(["--db-path", str(db_path)])


def _fetch_rates_grouped():
    return import_us_rates_liquidity.fetch_fred_csvs(
        fred_series_ids=RATES_FRED_SERIES
    )


def _fetch_macro_grouped():
    return import_us_macro_indicators.fetch_fred_csvs(
        fred_series_ids=MACRO_FRED_SERIES
    )


def _fetch_credit_grouped():
    return import_us_corporate_credit.fetch_fred_csvs(
        fred_series_ids=CREDIT_FRED_SERIES
    )


def _import_rates_grouped(con):
    return import_us_rates_liquidity.import_fred_csvs(
        con,
        fred_series_ids=RATES_FRED_SERIES,
    )


def _import_credit_grouped(con):
    return import_us_corporate_credit.import_fred_csvs(
        con,
        fred_series_ids=CREDIT_FRED_SERIES,
    )


def refresh(
    db_path,
    skip_fetch=False,
    connect=us_rates_liquidity.connect,
    fetch_rates=import_us_rates_liquidity.fetch_fred_csvs,
    fetch_macro=import_us_macro_indicators.fetch_fred_csvs,
    fetch_credit=import_us_corporate_credit.fetch_fred_csvs,
    import_rates=import_us_rates_liquidity.import_fred_csvs,
    import_macro=import_us_macro_indicators.import_fred_macro_csvs,
    import_credit_fred=import_us_corporate_credit.import_fred_csvs,
):
    con = connect(db_path)
    try:
        rates_fetched = None if skip_fetch else fetch_rates()
        macro_fetched = None if skip_fetch else fetch_macro()
        credit_fetched = None if skip_fetch else fetch_credit()
        rates_imported = import_rates(con)
        macro_imported = import_macro(con)
        credit_fred_imported = import_credit_fred(con)
        return {
            "rates_fetched": rates_fetched,
            "macro_fetched": macro_fetched,
            "credit_fetched": credit_fetched,
            "rates_imported": rates_imported,
            "macro_imported": macro_imported,
            "credit_fred_imported": credit_fred_imported,
        }
    finally:
        con.close()


def main(
    argv=None,
    connect=us_rates_liquidity.connect,
    fetch_rates=_fetch_rates_grouped,
    fetch_macro=_fetch_macro_grouped,
    fetch_credit=_fetch_credit_grouped,
    import_rates=_import_rates_grouped,
    import_macro=import_us_macro_indicators.import_fred_macro_csvs,
    import_credit_fred=_import_credit_grouped,
    generate_credit_interpretation=_generate_credit_interpretation,
):
    parser = argparse.ArgumentParser(
        description="Refresh US Rates / Liquidity dashboard data from FRED"
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=us_rates_liquidity.DEFAULT_DB_PATH,
    )
    parser.add_argument(
        "--skip-fetch",
        action="store_true",
        help="import from already downloaded FRED CSVs without network fetch",
    )
    parser.add_argument(
        "--generate-credit-interpretation",
        action="store_true",
        help="generate stored AI interpretation after data refresh",
    )
    args = parser.parse_args(argv)
    try:
        result = refresh(
            args.db_path,
            skip_fetch=args.skip_fetch,
            connect=connect,
            fetch_rates=fetch_rates,
            fetch_macro=fetch_macro,
            fetch_credit=fetch_credit,
            import_rates=import_rates,
            import_macro=import_macro,
            import_credit_fred=import_credit_fred,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    _print_fetched("rates", result["rates_fetched"])
    _print_fetched("macro", result["macro_fetched"])
    _print_fetched("credit", result["credit_fetched"])
    _print_imported("rates", result["rates_imported"])
    _print_imported("macro", result["macro_imported"])
    _print_imported("corporate credit fred", result["credit_fred_imported"])
    if args.generate_credit_interpretation:
        generated_exit = generate_credit_interpretation(args.db_path)
        if generated_exit != 0:
            return generated_exit
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

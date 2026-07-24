import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.data_sources.fred import FredClient, parse_fred_csv
from app.data_sources.michigan_consumer_sentiment import (
    MichiganConsumerSentimentClient,
    parse_aggregate_csv,
    parse_components_csv,
)
from app.db import consumer_sentiment


FRED_CAPACITY_SERIES = {
    "HDTGPDUSQ163N": {
        "series_id": "household_debt_to_gdp",
        "title": "Household Debt to GDP",
        "units": "percent",
        "source": "FRED HDTGPDUSQ163N",
    },
    "TDSP": {
        "series_id": "household_debt_service_ratio",
        "title": "Household Debt Service Payments as Percent of Disposable Personal Income",
        "units": "percent",
        "source": "FRED TDSP",
    },
    "PSAVERT": {
        "series_id": "personal_saving_rate",
        "title": "Personal Saving Rate",
        "units": "percent",
        "source": "FRED PSAVERT",
    },
    "HHMSDODNS": {
        "series_id": "one_to_four_family_mortgage_liabilities",
        "title": "One-to-Four-Family Residential Mortgage Liabilities",
        "units": "millions_usd",
        "source": "FRED HHMSDODNS",
    },
}


MICHIGAN_SOURCES = {
    "umcsi_aggregate": "University of Michigan Table 1",
    "umcsi_expectations": "University of Michigan Table 5",
    "umcsi_current_conditions": "University of Michigan Table 5",
}


def _michigan_series_payload(series_id, title, units):
    return {
        "series_id": series_id,
        "title": title,
        "units": units,
        "source": MICHIGAN_SOURCES[series_id],
    }


def _fred_series_payload(fred_series_id):
    info = FRED_CAPACITY_SERIES[fred_series_id]
    return {
        "series_id": info["series_id"],
        "title": info["title"],
        "units": info["units"],
        "source": info["source"],
    }


def import_michigan_csvs(table_1_path, table_5_path, db_path):
    aggregate_rows = parse_aggregate_csv(table_1_path)
    component_rows = parse_components_csv(table_5_path)
    series_points_list = []
    series_points_list.append(
        {
            "series": _michigan_series_payload(
                "umcsi_aggregate", "UMCSI Aggregate", "index_points"
            ),
            "points": [
                {
                    "date": r["date"],
                    "value": r["value"],
                    "source": MICHIGAN_SOURCES["umcsi_aggregate"],
                }
                for r in aggregate_rows
            ],
        }
    )
    series_points_list.append(
        {
            "series": _michigan_series_payload(
                "umcsi_expectations", "UMCSI Consumer Expectations", "index_points"
            ),
            "points": [
                {
                    "date": r["date"],
                    "value": r["expectations"],
                    "source": MICHIGAN_SOURCES["umcsi_expectations"],
                }
                for r in component_rows
            ],
        }
    )
    series_points_list.append(
        {
            "series": _michigan_series_payload(
                "umcsi_current_conditions", "UMCSI Current Conditions", "index_points"
            ),
            "points": [
                {
                    "date": r["date"],
                    "value": r["current_conditions"],
                    "source": MICHIGAN_SOURCES["umcsi_current_conditions"],
                }
                for r in component_rows
            ],
        }
    )
    con = consumer_sentiment.connect(db_path)
    try:
        consumer_sentiment.replace_michigan_series(con, series_points_list)
    finally:
        con.close()
    return series_points_list


def import_fred_csvs(csv_dir, db_path):
    csv_dir = Path(csv_dir)
    series_points_list = []
    for fred_id in FRED_CAPACITY_SERIES:
        csv_path = csv_dir / f"{fred_id}.csv"
        if not csv_path.exists():
            raise ValueError(f"fred csv does not exist: {csv_path}")
        parsed = parse_fred_csv(csv_path, fred_id)
        series_info = FRED_CAPACITY_SERIES[fred_id]
        points = [
            {"date": date_key, "value": value, "source": series_info["source"]}
            for date_key, value in parsed.items()
        ]
        series_points_list.append(
            {
                "series": _fred_series_payload(fred_id),
                "points": points,
            }
        )
    con = consumer_sentiment.connect(db_path)
    try:
        consumer_sentiment.replace_capacity_series(con, series_points_list)
    finally:
        con.close()
    return series_points_list


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Import consumer sentiment data from Michigan website and FRED"
    )
    parser.add_argument(
        "--db-path", type=Path, default=consumer_sentiment.DEFAULT_DB_PATH
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--fetch-michigan-csv", type=Path, metavar="DESTINATION_DIR")
    mode.add_argument(
        "--michigan-csv-import", nargs=2, metavar=("TABLE_1_PATH", "TABLE_5_PATH")
    )
    mode.add_argument("--fetch-fred-csv", type=Path, metavar="DESTINATION_DIR")
    mode.add_argument("--fred-csv-import", type=Path, metavar="DIRECTORY")
    args = parser.parse_args(argv)
    try:
        if args.fetch_michigan_csv:
            client = MichiganConsumerSentimentClient()
            paths = client.fetch_csvs(args.fetch_michigan_csv)
            for table_id, path in paths.items():
                print(f"table_{table_id}: {path}")
            return 0
        if args.michigan_csv_import:
            table_1_path = Path(args.michigan_csv_import[0])
            table_5_path = Path(args.michigan_csv_import[1])
            result = import_michigan_csvs(table_1_path, table_5_path, args.db_path)
            total = sum(len(item["points"]) for item in result)
            print(f"db: {args.db_path}")
            for item in result:
                print(f"{item['series']['series_id']}: {len(item['points'])}")
            print(f"total: {total}")
            return 0
        if args.fetch_fred_csv:
            client = FredClient(args.fetch_fred_csv)
            paths = client.fetch_csvs(list(FRED_CAPACITY_SERIES))
            for series_id, path in paths.items():
                print(f"{series_id}: {path}")
            return 0
        if args.fred_csv_import:
            result = import_fred_csvs(args.fred_csv_import, args.db_path)
            total = sum(len(item["points"]) for item in result)
            print(f"db: {args.db_path}")
            for item in result:
                print(f"{item['series']['series_id']}: {len(item['points'])}")
            print(f"total: {total}")
            return 0
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

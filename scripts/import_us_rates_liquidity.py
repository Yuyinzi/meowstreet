import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.data_sources.fred import FredClient
from app.data_sources.fred import parse_fred_csv
from app.data_sources.fred import resample_to_weekly_sundays
from app.db import us_rates_liquidity
from scripts import import_benchmark_market_data


DEFAULT_WORKBOOK_PATH = ROOT / "data" / "source_material" / "Video 04" / "Benchmark_Yields_US.xlsm"
DEFAULT_FRED_DIR = DEFAULT_WORKBOOK_PATH.parent / "fred"
FRED_SOURCE_SHEET = "FRED weekly Sunday resample"
DATA_SHEET_NAME = "Data"
DATA_HEADER_ROW = 1
DATA_FIRST_VALUE_ROW = 4
RATE_SERIES_CONFIG = {
    "Fed Funds": {
        "series_id": "fed_funds",
        "title": "Fed Funds",
        "instrument_type": "policy_rate",
        "maturity_months": None,
    },
    "1mo": {
        "series_id": "treasury_1m",
        "title": "1-Month Treasury",
        "instrument_type": "nominal_treasury",
        "maturity_months": 1,
    },
    "3mo": {
        "series_id": "treasury_3m",
        "title": "3-Month Treasury",
        "instrument_type": "nominal_treasury",
        "maturity_months": 3,
    },
    "6mo": {
        "series_id": "treasury_6m",
        "title": "6-Month Treasury",
        "instrument_type": "nominal_treasury",
        "maturity_months": 6,
    },
    "1yr": {
        "series_id": "treasury_1y",
        "title": "1-Year Treasury",
        "instrument_type": "nominal_treasury",
        "maturity_months": 12,
    },
    "2yr": {
        "series_id": "treasury_2y",
        "title": "2-Year Treasury",
        "instrument_type": "nominal_treasury",
        "maturity_months": 24,
    },
    "3yr": {
        "series_id": "treasury_3y",
        "title": "3-Year Treasury",
        "instrument_type": "nominal_treasury",
        "maturity_months": 36,
    },
    "5yr": {
        "series_id": "treasury_5y",
        "title": "5-Year Treasury",
        "instrument_type": "nominal_treasury",
        "maturity_months": 60,
    },
    "7yr": {
        "series_id": "treasury_7y",
        "title": "7-Year Treasury",
        "instrument_type": "nominal_treasury",
        "maturity_months": 84,
    },
    "10yr": {
        "series_id": "treasury_10y",
        "title": "10-Year Treasury",
        "instrument_type": "nominal_treasury",
        "maturity_months": 120,
    },
    "20yr": {
        "series_id": "treasury_20y",
        "title": "20-Year Treasury",
        "instrument_type": "nominal_treasury",
        "maturity_months": 240,
    },
    "30yr": {
        "series_id": "treasury_30y",
        "title": "30-Year Treasury",
        "instrument_type": "nominal_treasury",
        "maturity_months": 360,
    },
    "5yr TIPS": {
        "series_id": "tips_5y",
        "title": "5-Year TIPS",
        "instrument_type": "tips",
        "maturity_months": 60,
    },
    "7yr TIPS": {
        "series_id": "tips_7y",
        "title": "7-Year TIPS",
        "instrument_type": "tips",
        "maturity_months": 84,
    },
    "10yr TIPS": {
        "series_id": "tips_10y",
        "title": "10-Year TIPS",
        "instrument_type": "tips",
        "maturity_months": 120,
    },
    "20yr TIPS": {
        "series_id": "tips_20y",
        "title": "20-Year TIPS",
        "instrument_type": "tips",
        "maturity_months": 240,
    },
    "30yr TIPS": {
        "series_id": "tips_30y",
        "title": "30-Year TIPS",
        "instrument_type": "tips",
        "maturity_months": 360,
    },
}

FRED_RATE_SERIES_CONFIG = {
    "DFF": "Fed Funds",
    "DGS1MO": "1mo",
    "DGS3MO": "3mo",
    "DGS6MO": "6mo",
    "DGS1": "1yr",
    "DGS2": "2yr",
    "DGS3": "3yr",
    "DGS5": "5yr",
    "DGS7": "7yr",
    "DGS10": "10yr",
    "DGS20": "20yr",
    "DGS30": "30yr",
    "DFII5": "5yr TIPS",
    "DFII7": "7yr TIPS",
    "DFII10": "10yr TIPS",
    "DFII20": "20yr TIPS",
    "DFII30": "30yr TIPS",
}


def _series_payload(header, workbook_path):
    config = RATE_SERIES_CONFIG[header]
    return {
        "series_id": config["series_id"],
        "title": config["title"],
        "instrument_type": config["instrument_type"],
        "maturity_months": config["maturity_months"],
        "units": "percent",
        "source_workbook": Path(workbook_path).name,
        "source_sheet": DATA_SHEET_NAME,
    }


def _point_payload(date_iso, value, workbook_path):
    return {
        "date": date_iso,
        "value": value,
        "source_workbook": Path(workbook_path).name,
        "source_sheet": DATA_SHEET_NAME,
    }


def _fred_series_payload(fred_series_id, csv_path):
    header = FRED_RATE_SERIES_CONFIG[fred_series_id]
    config = RATE_SERIES_CONFIG[header]
    return {
        "series_id": config["series_id"],
        "title": config["title"],
        "instrument_type": config["instrument_type"],
        "maturity_months": config["maturity_months"],
        "units": "percent",
        "source_workbook": Path(csv_path).name,
        "source_sheet": FRED_SOURCE_SHEET,
    }


def _fred_point_payload(point, csv_path):
    return {
        "date": point["date"],
        "value": point["value"],
        "source_workbook": Path(csv_path).name,
        "source_sheet": FRED_SOURCE_SHEET,
    }


def build_fred_rate_payload(csv_path, fred_series_id):
    if fred_series_id not in FRED_RATE_SERIES_CONFIG:
        raise ValueError(f"fred rate series is unsupported: {fred_series_id}")
    rows = parse_fred_csv(csv_path, fred_series_id)
    points = [
        _fred_point_payload(point, csv_path)
        for point in resample_to_weekly_sundays(rows)
    ]
    return {
        "series": _fred_series_payload(fred_series_id, csv_path),
        "points": points,
    }


def fetch_fred_csvs(fred_dir=DEFAULT_FRED_DIR, fred_series_ids=None):
    series_ids = fred_series_ids or sorted(FRED_RATE_SERIES_CONFIG)
    for fred_series_id in series_ids:
        if fred_series_id not in FRED_RATE_SERIES_CONFIG:
            raise ValueError(f"fred rate series is unsupported: {fred_series_id}")
    client = FredClient(fred_dir)
    return client.fetch_csvs(series_ids)


def import_fred_csvs(con, fred_dir=DEFAULT_FRED_DIR, fred_series_ids=None):
    series_ids = fred_series_ids or sorted(FRED_RATE_SERIES_CONFIG)
    inserted = {}
    for fred_series_id in series_ids:
        csv_path = Path(fred_dir) / f"{fred_series_id}.csv"
        payload = build_fred_rate_payload(csv_path, fred_series_id)
        saved = us_rates_liquidity.replace_rate_series_points(
            con,
            payload["series"],
            payload["points"],
        )
        inserted[payload["series"]["series_id"]] = saved["points"]
    return inserted


def parse_data_sheet(workbook_path=DEFAULT_WORKBOOK_PATH):
    sheet = import_benchmark_market_data.load_workbook_sheet(
        workbook_path,
        DATA_SHEET_NAME,
        data_only=True,
    )
    headers = [cell.value for cell in sheet[DATA_HEADER_ROW]]
    parsed = {}
    for column_index, header in enumerate(headers[1:], start=2):
        if header not in RATE_SERIES_CONFIG:
            continue
        series_id = RATE_SERIES_CONFIG[header]["series_id"]
        parsed[series_id] = {
            "series": _series_payload(header, workbook_path),
            "points": [],
        }
        for row in sheet.iter_rows(
            min_row=DATA_FIRST_VALUE_ROW,
            min_col=1,
            max_col=column_index,
            values_only=True,
        ):
            date_value = row[0]
            rate_value = row[column_index - 1]
            value = import_benchmark_market_data.float_or_none(rate_value)
            if date_value is None or value is None:
                continue
            parsed[series_id]["points"].append(
                _point_payload(
                    import_benchmark_market_data.cell_date_iso(date_value),
                    value,
                    workbook_path,
                )
            )
        parsed[series_id]["points"] = sorted(
            parsed[series_id]["points"],
            key=lambda point: point["date"],
        )
    return parsed


def import_workbook(con, workbook_path=DEFAULT_WORKBOOK_PATH):
    parsed = parse_data_sheet(workbook_path)
    inserted = {}
    for series_id, payload in parsed.items():
        saved = us_rates_liquidity.replace_rate_series_points(
            con,
            payload["series"],
            payload["points"],
        )
        inserted[series_id] = saved["points"]
    return inserted


def main():
    args = set(sys.argv[1:])
    con = us_rates_liquidity.connect()
    try:
        if "--fetch-fred-csv" in args:
            fetched = fetch_fred_csvs()
            for series_id, path in fetched.items():
                print(f"{series_id}: {path}")
            return
        if "--fred-csv-merge" in args:
            inserted = import_fred_csvs(con)
        else:
            inserted = import_workbook(con)
        for series_id, count in inserted.items():
            print(f"{series_id}: {count}")
    finally:
        con.close()


if __name__ == "__main__":
    main()

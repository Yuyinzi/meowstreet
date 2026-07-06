import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db import us_rates_liquidity
from scripts import import_benchmark_market_data


DEFAULT_WORKBOOK_PATH = ROOT / "data" / "materials" / "Video 04" / "Benchmark_Yields_US.xlsm"
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
    con = us_rates_liquidity.connect()
    try:
        inserted = import_workbook(con)
        for series_id, count in inserted.items():
            print(f"{series_id}: {count}")
    finally:
        con.close()


if __name__ == "__main__":
    main()

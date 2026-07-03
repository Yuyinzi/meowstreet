import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db import gdp_market_relationships
from scripts import import_benchmark_market_data

DEFAULT_WORKBOOK_PATH = ROOT / "data" / "materials" / "Video 03" / "GDP_Correlations.xlsx"

GDP_RELATIONSHIP_SHEETS = [
    {
        "relationship_id": "us_sp500_gdp",
        "title": "S&P 500 vs US Real GDP",
        "region": "US",
        "economy": "US",
        "index_name": "S&P 500",
        "primary_lag_months": 6,
        "correlation_window_years": 10,
        "correlation_sheet": "S&P500_USGDP Correlation",
        "quadnomial_sheet": "S&P500_US_Quadnomial",
    },
    {
        "relationship_id": "us_nasdaq_gdp",
        "title": "Nasdaq Composite vs US Real GDP",
        "region": "US",
        "economy": "US",
        "index_name": "Nasdaq Composite",
        "primary_lag_months": 6,
        "correlation_window_years": 10,
        "correlation_sheet": "Nasdaq_USGDP Correlation",
        "quadnomial_sheet": "Nasdaq_US_Quadnomial",
    },
    {
        "relationship_id": "europe_stoxx50_gdp",
        "title": "Eurostoxx 50 vs EU Real GDP",
        "region": "Europe",
        "economy": "EU",
        "index_name": "Eurostoxx 50",
        "primary_lag_months": 6,
        "correlation_window_years": 10,
        "correlation_sheet": "Eurostoxx50_EUGDP Correlation",
        "quadnomial_sheet": "Eurostoxx50_EU_Quadnomial",
    },
    {
        "relationship_id": "japan_nikkei_gdp",
        "title": "Nikkei 225 vs Japan Real GDP",
        "region": "Japan",
        "economy": "Japan",
        "index_name": "Nikkei 225",
        "primary_lag_months": 6,
        "correlation_window_years": 10,
        "correlation_sheet": "Nikkei225_JPGDP Correlation",
        "quadnomial_sheet": "Nikkei225_JP_Quadnomial",
    },
]

_LAG_GROUPS = [
    {"lag_months": 0, "index_yoy_col": 4, "gdp_yoy_col": 5, "rolling_corr_col": 6},
    {"lag_months": 3, "index_yoy_col": 7, "gdp_yoy_col": 8, "rolling_corr_col": 9},
    {"lag_months": 6, "index_yoy_col": 10, "gdp_yoy_col": 11, "rolling_corr_col": 12},
]


def _source_name(workbook_path):
    return Path(workbook_path).name


def _quad_case(index_direction, gdp_direction):
    if index_direction is None or gdp_direction is None:
        return None
    return f"{int(index_direction)},{int(gdp_direction)}"


def _parse_correlation_sheet(workbook_path, sheet_name):
    sheet = import_benchmark_market_data.load_workbook_sheet(
        workbook_path, sheet_name, data_only=True
    )
    lag_rows = []
    for values in sheet.iter_rows(min_row=3, values_only=True):
        date_value = values[0]
        if date_value is None:
            continue
        date_iso = import_benchmark_market_data.cell_date_iso(date_value)
        has_data = False
        for group in _LAG_GROUPS:
            idx = group["index_yoy_col"] - 1
            gdp = group["gdp_yoy_col"] - 1
            corr = group["rolling_corr_col"] - 1
            if idx < len(values) and values[idx] is not None:
                has_data = True
            if gdp < len(values) and values[gdp] is not None:
                has_data = True
            if corr < len(values) and values[corr] is not None:
                has_data = True
        if not has_data:
            continue
        for group in _LAG_GROUPS:
            idx = group["index_yoy_col"] - 1
            gdp = group["gdp_yoy_col"] - 1
            corr = group["rolling_corr_col"] - 1
            lag_rows.append(
                {
                    "date": date_iso,
                    "lag_months": group["lag_months"],
                    "index_yoy": import_benchmark_market_data.float_or_none(
                        values[idx] if idx < len(values) else None
                    ),
                    "gdp_yoy": import_benchmark_market_data.float_or_none(
                        values[gdp] if gdp < len(values) else None
                    ),
                    "rolling_correlation": import_benchmark_market_data.float_or_none(
                        values[corr] if corr < len(values) else None
                    ),
                }
            )
    return lag_rows


def _parse_quadnomial_sheet(workbook_path, sheet_name):
    sheet = import_benchmark_market_data.load_workbook_sheet(
        workbook_path, sheet_name, data_only=True
    )
    quad_rows = []
    for values in sheet.iter_rows(min_row=2, values_only=True):
        date_value = values[0]
        if date_value is None:
            continue
        date_iso = import_benchmark_market_data.cell_date_iso(date_value)
        index_direction = import_benchmark_market_data.float_or_none(
            values[4] if len(values) > 4 else None
        )
        gdp_direction = import_benchmark_market_data.float_or_none(
            values[5] if len(values) > 5 else None
        )
        case = _quad_case(index_direction, gdp_direction)
        if case is None:
            continue
        quad_rows.append(
            {
                "date": date_iso,
                "primary_lag_months": 6,
                "index_level": import_benchmark_market_data.float_or_none(
                    values[1] if len(values) > 1 else None
                ),
                "period_label": str(values[2])
                if len(values) > 2 and values[2] is not None
                else None,
                "gdp_level": import_benchmark_market_data.float_or_none(
                    values[3] if len(values) > 3 else None
                ),
                "index_direction": int(index_direction)
                if index_direction is not None
                else None,
                "gdp_direction": int(gdp_direction)
                if gdp_direction is not None
                else None,
                "quad_case": case,
            }
        )
    return quad_rows


def parse_relationship(workbook_path, config):
    source = _source_name(workbook_path)
    relationship = {
        "relationship_id": config["relationship_id"],
        "title": config["title"],
        "region": config["region"],
        "economy": config["economy"],
        "index_name": config["index_name"],
        "primary_lag_months": config["primary_lag_months"],
        "correlation_window_years": config["correlation_window_years"],
        "source_workbook": source,
        "source_sheet": config["correlation_sheet"],
    }
    lag_rows = _parse_correlation_sheet(workbook_path, config["correlation_sheet"])
    for row in lag_rows:
        row["source_workbook"] = source
        row["source_sheet"] = config["correlation_sheet"]
    quad_rows = _parse_quadnomial_sheet(workbook_path, config["quadnomial_sheet"])
    for row in quad_rows:
        row["source_workbook"] = source
        row["source_sheet"] = config["quadnomial_sheet"]
    return relationship, lag_rows, quad_rows


def import_workbook(con, workbook_path=DEFAULT_WORKBOOK_PATH, configs=None):
    if configs is None:
        configs = GDP_RELATIONSHIP_SHEETS
    inserted = {}
    errors = {}
    for config in configs:
        try:
            relationship, lag_rows, quad_rows = parse_relationship(
                workbook_path, config
            )
            gdp_market_relationships.replace_relationship_data(
                con, relationship, lag_rows, quad_rows
            )
            inserted[config["relationship_id"]] = {
                "lag_rows": len(lag_rows),
                "quad_rows": len(quad_rows),
            }
        except ValueError as exc:
            errors[config["relationship_id"]] = str(exc)
    return inserted, errors


def main():
    con = gdp_market_relationships.connect()
    inserted, errors = import_workbook(con)
    for relationship_id, counts in inserted.items():
        print(
            f"{relationship_id}: {counts['lag_rows']} lag rows, {counts['quad_rows']} quad rows"
        )
    for relationship_id, message in errors.items():
        print(f"ERROR {relationship_id}: {message}", file=sys.stderr)


if __name__ == "__main__":
    main()

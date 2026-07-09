import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.data_sources.fred import FredClient
from app.data_sources.fred import parse_fred_csv
from app.data_sources.fred import quarter_end_for_date
from app.db import gdp_market_relationships
from app.tools import gdp_market_relationship
from app.tools import gdp_market_relationship_compute
from scripts import import_benchmark_market_data

US_GDP_RELATIONSHIP_ID = "us_sp500_gdp"

GDP_RELATIONSHIP_SHEETS = [
    {
        "relationship_id": "us_sp500_gdp",
        "title": "S&P 500 vs US GDP",
        "region": "US",
        "economy": "US GDP",
        "index_name": "S&P 500",
        "correlation_sheet": "S&P500_USGDP Correlation",
        "quadnomial_sheet": "S&P500_US_Quadnomial",
        "primary_lag_months": 6,
        "correlation_window_years": 10,
    },
    {
        "relationship_id": "europe_stoxx600_eu_gdp",
        "title": "Eurostoxx 600 vs EU GDP",
        "region": "Europe",
        "economy": "EU GDP",
        "index_name": "Eurostoxx 600",
        "correlation_sheet": "STOXX600_EUGDP Correlation",
        "quadnomial_sheet": "STOXX600_Quadnomial",
        "primary_lag_months": 6,
        "correlation_window_years": 5,
    },
    {
        "relationship_id": "europe_stoxx600_eurozone_gdp",
        "title": "Eurostoxx 600 vs Eurozone GDP",
        "region": "Europe",
        "economy": "Eurozone GDP",
        "index_name": "Eurostoxx 600",
        "correlation_sheet": "STOXX600_EZGDP Correlation",
        "quadnomial_sheet": "STOXX600_EZ_Quadnomial",
        "primary_lag_months": 6,
        "correlation_window_years": 5,
    },
    {
        "relationship_id": "china_szsc_gdp",
        "title": "Shenzhen Composite vs China GDP",
        "region": "China",
        "economy": "China GDP",
        "index_name": "Shenzhen Composite",
        "correlation_sheet": "SZSC_CNGDP Correlation",
        "quadnomial_sheet": "SZSC_CN_Quadnomial",
        "primary_lag_months": 6,
        "correlation_window_years": 5,
    },
]

_LAG_GROUPS = [
    {"lag_months": 0, "index_yoy_col": 4, "gdp_yoy_col": 5, "rolling_corr_col": 6},
    {"lag_months": 3, "index_yoy_col": 7, "gdp_yoy_col": 8, "rolling_corr_col": 9},
    {"lag_months": 6, "index_yoy_col": 10, "gdp_yoy_col": 11, "rolling_corr_col": 12},
    {"lag_months": 9, "index_yoy_col": 13, "gdp_yoy_col": 14, "rolling_corr_col": 15},
    {"lag_months": 12, "index_yoy_col": 16, "gdp_yoy_col": 17, "rolling_corr_col": 18},
]


def _default_materials_path(*parts):
    path = ROOT / "data" / "materials" / Path(*parts)
    if path.exists():
        return path
    if ROOT.parent.name == ".worktrees":
        fallback = ROOT.parents[1] / "data" / "materials" / Path(*parts)
        if fallback.exists():
            return fallback
    return path


DEFAULT_WORKBOOK_PATH = _default_materials_path("Video 03", "GDP_Correlations.xlsx")
DEFAULT_GDPC1_CSV_PATH = _default_materials_path("Video 03", "GDPC1.csv")
DEFAULT_SP500_CSV_PATH = _default_materials_path("Video 03", "SP500.csv")
DEFAULT_FRED_DIR = DEFAULT_GDPC1_CSV_PATH.parent


def _source_name(workbook_path):
    return Path(workbook_path).name


def _load_relationship(con, relationship_id):
    normalized = gdp_market_relationships.normalize_relationship_id(relationship_id)
    for relationship in gdp_market_relationships.load_relationships(con):
        if relationship["relationship_id"] == normalized:
            return relationship
    raise ValueError(f"relationship is not loaded: {normalized}")


def _raw_rows_from_csv_levels(gdp_levels, sp500_levels):
    return [
        {
            "date": date_iso,
            "gdp_level": gdp_levels[date_iso],
            "index_level": sp500_levels[date_iso],
        }
        for date_iso in sorted(set(gdp_levels) & set(sp500_levels))
    ]


def _merge_existing_and_computed_lag_rows(existing_rows, computed_rows):
    merged_rows = {(row["date"], row["lag_months"]): dict(row) for row in existing_rows}
    for row in computed_rows:
        key = (row["date"], row["lag_months"])
        existing_row = merged_rows.get(key)
        if existing_row is None:
            merged_rows[key] = dict(row)
            continue
        merged_row = dict(existing_row)
        for field, value in row.items():
            if field in {"date", "lag_months"} or value is not None:
                merged_row[field] = value
        merged_rows[key] = merged_row
    return [merged_rows[key] for key in sorted(merged_rows)]


def _affected_rolling_dates(computed_rows):
    return sorted(
        {
            row["date"]
            for row in computed_rows
            if row.get("index_yoy") is not None or row.get("gdp_yoy") is not None
        }
    )


def _build_relationship_summary(con, relationship_id):
    relationship = _load_relationship(con, relationship_id)
    return gdp_market_relationship.build_detail_payload(
        relationship,
        gdp_market_relationships.load_lag_rows(con, relationship_id),
        gdp_market_relationships.load_quad_rows(con, relationship_id),
    )


def _format_summary_value(value):
    return "None" if value is None else str(value)


def _print_relationship_summary_comparison(
    relationship_id,
    before_summary,
    after_summary,
):
    print(f"latest metric comparison for {relationship_id}")
    comparisons = [
        (
            "primary_lag_date",
            before_summary["latest"].get("primary_lag_date"),
            after_summary["latest"].get("primary_lag_date"),
        ),
        (
            "quadnomial_date",
            before_summary["latest"].get("quadnomial_date"),
            after_summary["latest"].get("quadnomial_date"),
        ),
        (
            "rolling_index_gdp_correlation",
            before_summary["latest"].get("rolling_index_gdp_correlation"),
            after_summary["latest"].get("rolling_index_gdp_correlation"),
        ),
        (
            "average_10y_correlation",
            before_summary["latest"].get("average_10y_correlation"),
            after_summary["latest"].get("average_10y_correlation"),
        ),
        (
            "index_yoy",
            before_summary["latest"].get("index_yoy"),
            after_summary["latest"].get("index_yoy"),
        ),
        (
            "gdp_yoy",
            before_summary["latest"].get("gdp_yoy"),
            after_summary["latest"].get("gdp_yoy"),
        ),
        (
            "quadnomial_current_case",
            before_summary["latest"].get("quadnomial_current_case"),
            after_summary["latest"].get("quadnomial_current_case"),
        ),
        (
            "same_direction_pct",
            before_summary.get("same_direction_pct"),
            after_summary.get("same_direction_pct"),
        ),
        (
            "method_explainable_pct",
            before_summary.get("method_explainable_pct"),
            after_summary.get("method_explainable_pct"),
        ),
        (
            "relationship_signal_usability",
            before_summary.get("relationship_signal_usability"),
            after_summary.get("relationship_signal_usability"),
        ),
        (
            "macro_relationship_confidence",
            before_summary.get("macro_relationship_confidence"),
            after_summary.get("macro_relationship_confidence"),
        ),
    ]
    for label, before_value, after_value in comparisons:
        print(
            f"{label}: {_format_summary_value(before_value)} -> "
            f"{_format_summary_value(after_value)}"
        )


def fetch_fred_csvs(fred_dir=DEFAULT_FRED_DIR):
    client = FredClient(fred_dir)
    gdp_csv_path = client.fetch_csv("GDPC1")
    sp500_csv_path = client.fetch_csv("SP500")
    return {"gdp_csv": str(gdp_csv_path), "sp500_csv": str(sp500_csv_path)}


def parse_fred_gdp_csv(csv_path):
    rows = parse_fred_csv(csv_path, "GDPC1")
    return {quarter_end_for_date(date_iso): value for date_iso, value in rows.items()}


def parse_fred_sp500_csv(csv_path):
    rows = parse_fred_csv(csv_path, "SP500")
    return {quarter_end_for_date(date_iso): value for date_iso, value in rows.items()}


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


def import_us_csv_merge(
    con,
    gdp_csv_path=DEFAULT_GDPC1_CSV_PATH,
    sp500_csv_path=DEFAULT_SP500_CSV_PATH,
):
    relationship = _load_relationship(con, US_GDP_RELATIONSHIP_ID)
    gdp_levels = parse_fred_gdp_csv(gdp_csv_path)
    sp500_levels = parse_fred_sp500_csv(sp500_csv_path)
    raw_rows = _raw_rows_from_csv_levels(gdp_levels, sp500_levels)
    source = f"{Path(gdp_csv_path).name}+{Path(sp500_csv_path).name}"
    computed_lag_rows = gdp_market_relationship_compute.compute_lag_rows(
        raw_rows,
        source,
        correlation_window_years=relationship["correlation_window_years"],
    )
    computed_quad_rows = gdp_market_relationship_compute.compute_quad_rows(
        raw_rows,
        source,
    )
    existing_lag_rows = gdp_market_relationships.load_lag_rows(
        con,
        US_GDP_RELATIONSHIP_ID,
    )
    merged_lag_rows = _merge_existing_and_computed_lag_rows(
        existing_lag_rows,
        computed_lag_rows,
    )
    recomputed_lag_rows = (
        gdp_market_relationship_compute.recompute_rolling_correlations(
            merged_lag_rows,
            _affected_rolling_dates(computed_lag_rows),
            source,
            correlation_window_years=relationship["correlation_window_years"],
        )
    )
    affected_dates = sorted(
        {row["date"] for row in recomputed_lag_rows}
        | {row["date"] for row in computed_quad_rows}
    )
    return gdp_market_relationships.replace_relationship_rows_for_dates(
        con,
        US_GDP_RELATIONSHIP_ID,
        affected_dates,
        recomputed_lag_rows,
        computed_quad_rows,
    )


def main(argv=None):
    con = gdp_market_relationships.connect()
    argv = sys.argv if argv is None else argv
    try:
        if "--fetch-fred-csv" in argv:
            result = fetch_fred_csvs()
            print(f"downloaded {result['gdp_csv']}")
            print(f"downloaded {result['sp500_csv']}")
            return
        if "--us-csv-merge" in argv:
            before_summary = _build_relationship_summary(con, US_GDP_RELATIONSHIP_ID)
            counts = import_us_csv_merge(con)
            after_summary = _build_relationship_summary(con, US_GDP_RELATIONSHIP_ID)
            print(
                f"us_sp500_gdp: {counts['lag_rows']} csv lag rows, "
                f"{counts['quad_rows']} csv quad rows merged"
            )
            _print_relationship_summary_comparison(
                US_GDP_RELATIONSHIP_ID,
                before_summary,
                after_summary,
            )
            return
        inserted, errors = import_workbook(con)
        for relationship_id, counts in inserted.items():
            print(
                f"{relationship_id}: {counts['lag_rows']} lag rows, {counts['quad_rows']} quad rows"
            )
        for relationship_id, message in errors.items():
            print(f"ERROR {relationship_id}: {message}", file=sys.stderr)
    finally:
        con.close()


if __name__ == "__main__":
    main()

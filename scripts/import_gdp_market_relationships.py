import argparse
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

US_GDP_RELATIONSHIP_ID = "us_sp500_gdp"

DEFAULT_FRED_DIR = ROOT / "data" / "downloads" / "fred"
DEFAULT_GDPC1_CSV_PATH = DEFAULT_FRED_DIR / "GDPC1.csv"
DEFAULT_SP500_CSV_PATH = DEFAULT_FRED_DIR / "SP500.csv"


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
    parser = argparse.ArgumentParser(
        description="Refresh the US S&P 500 vs GDP relationship from FRED CSVs"
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--fetch-fred-csv", action="store_true")
    mode.add_argument("--us-csv-merge", action="store_true")
    args = parser.parse_args(argv)
    if args.fetch_fred_csv:
        result = fetch_fred_csvs()
        print(f"downloaded {result['gdp_csv']}")
        print(f"downloaded {result['sp500_csv']}")
        return
    con = gdp_market_relationships.connect()
    try:
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
    finally:
        con.close()


if __name__ == "__main__":
    main()

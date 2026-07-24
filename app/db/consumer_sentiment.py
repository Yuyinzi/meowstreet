from pathlib import Path

from app.db import macro_indicators


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = ROOT / "data" / "local_system" / "market_data.sqlite"

MICHIGAN_SERIES_IDS = {
    "umcsi_aggregate",
    "umcsi_expectations",
    "umcsi_current_conditions",
}

CAPACITY_SERIES_IDS = {
    "household_debt_to_gdp",
    "household_debt_service_ratio",
    "personal_saving_rate",
    "one_to_four_family_mortgage_liabilities",
}

ALL_CONSUMER_SERIES_IDS = MICHIGAN_SERIES_IDS | CAPACITY_SERIES_IDS


def connect(db_path=DEFAULT_DB_PATH):
    return macro_indicators.connect(db_path)


def _validate_series_ids(series_points_list, allowed_ids, label):
    for item in series_points_list:
        sid = item["series"]["series_id"]
        if sid not in allowed_ids:
            raise ValueError(f"series {sid} is not a valid {label} series id")


def replace_michigan_series(con, series_points_list):
    _validate_series_ids(series_points_list, MICHIGAN_SERIES_IDS, "michigan")
    macro_indicators.replace_macro_indicator_points_batch(con, series_points_list)


def replace_capacity_series(con, series_points_list):
    _validate_series_ids(series_points_list, CAPACITY_SERIES_IDS, "capacity")
    macro_indicators.replace_macro_indicator_points_batch(con, series_points_list)


def load_overview_series(con):
    return macro_indicators.load_macro_indicator_points_for_series(
        con, list(ALL_CONSUMER_SERIES_IDS)
    )


def load_detail_series(con):
    return macro_indicators.load_macro_indicator_points_for_series(
        con, list(ALL_CONSUMER_SERIES_IDS)
    )

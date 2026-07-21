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


def replace_michigan_series(con, series_points_list):
    for item in series_points_list:
        sid = item["series"]["series_id"]
        if sid not in MICHIGAN_SERIES_IDS:
            raise ValueError(f"series {sid} is not a valid michigan series id")
    for item in series_points_list:
        macro_indicators.replace_macro_indicator_points(
            con, item["series"], item["points"]
        )


def replace_capacity_series(con, series_points_list):
    for item in series_points_list:
        sid = item["series"]["series_id"]
        if sid not in CAPACITY_SERIES_IDS:
            raise ValueError(f"series {sid} is not a valid capacity series id")
    for item in series_points_list:
        macro_indicators.replace_macro_indicator_points(
            con, item["series"], item["points"]
        )


def load_overview_series(con):
    return macro_indicators.load_macro_indicator_points_for_series(
        con, list(ALL_CONSUMER_SERIES_IDS)
    )


def load_detail_series(con):
    return macro_indicators.load_macro_indicator_points_for_series(
        con, list(ALL_CONSUMER_SERIES_IDS)
    )

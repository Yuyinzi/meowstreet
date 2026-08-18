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


def merge_michigan_points(con, series_id, points):
    normalized = str(series_id or "").strip().lower()
    if normalized not in MICHIGAN_SERIES_IDS:
        raise ValueError(f"series {normalized} is not a valid michigan series id")
    existing = con.execute(
        "select 1 from macro_indicator_series where series_id = ?", (normalized,)
    ).fetchone()
    if existing is None:
        raise ValueError(
            f"michigan series {normalized} is not defined; run the csv import first"
        )
    try:
        for point in points:
            con.execute(
                """
                insert into macro_indicator_points(series_id, date, value, source)
                values (?, ?, ?, ?)
                on conflict(series_id, date) do update set
                    value = excluded.value,
                    source = excluded.source
                """,
                (normalized, point["date"], point["value"], point["source"]),
            )
        con.commit()
    except Exception:
        con.rollback()
        raise
    return {"series_id": normalized, "points": len(points)}


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

from pathlib import Path
from sqlite3 import Error as SQLiteError

from app.data_sources.freshness_lineage import build_lineage
from app.db import macro_indicators
from app.db.macro_source_lineage import connect, load_stored_points, matching_lineage, merge_reconstructed_lineage
from app.services.macro_data_freshness_catalog import load_catalog


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CACHE_DIR = ROOT / "data" / "downloads" / "fred"


def backfill_cached_lineage(db_path=None, cache_dir=None):
    path = Path(db_path or macro_indicators.DEFAULT_DB_PATH)
    directory = Path(cache_dir or DEFAULT_CACHE_DIR)
    result = {"matched_rows": 0, "datasets": 0, "conflicting_rows": 0}
    if not path.exists() or not directory.exists():
        return result
    con = connect(path)
    try:
        for dataset in load_catalog()["datasets"]:
            source_id = dataset.get("lineage_source")
            if not source_id or not (directory / f"{source_id}.csv").exists():
                continue
            try:
                stored = load_stored_points(con, dataset["storage"])
            except SQLiteError:
                continue
            if not stored:
                continue
            reconstructed = build_lineage(directory / f"{source_id}.csv", source_id, transform=dataset["lineage_transform"], start_date=stored[0]["date"], end_date=stored[-1]["date"])
            matched = matching_lineage(stored, reconstructed)
            if matched:
                result["conflicting_rows"] += merge_reconstructed_lineage(con, dataset["id"], matched)
                result["matched_rows"] += len(matched)
                result["datasets"] += 1
    finally:
        con.close()
    return result

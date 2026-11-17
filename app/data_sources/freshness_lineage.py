from hashlib import sha256
from pathlib import Path

from app.data_sources.fred import compute_yoy, parse_fred_csv_text, resample_to_weekly_sundays


def build_lineage(csv_path, series_id, *, transform="identity", start_date=None, end_date=None):
    snapshot = read_fred_snapshot(csv_path, series_id)
    return lineage_from_snapshot(snapshot, transform=transform, start_date=start_date, end_date=end_date)


def read_fred_snapshot(csv_path, series_id):
    path = Path(csv_path)
    if not path.exists():
        raise ValueError(f"fred csv does not exist: {path}")
    content = path.read_bytes()
    return {"source_hash": sha256(content).hexdigest(), "source_series_id": series_id, "rows": parse_fred_csv_text(content.decode("utf-8"), series_id)}


def lineage_from_snapshot(snapshot, *, transform="identity", start_date=None, end_date=None):
    if transform not in {"identity", "yoy"}:
        raise ValueError(f"lineage transform is unsupported: {transform}")
    rows = snapshot["rows"]
    values = compute_yoy(rows) if transform == "yoy" else rows
    points = resample_to_weekly_sundays(values, start_date=start_date, end_date=end_date, include_source_date=True)
    return [{**point, "source_series_id": snapshot["source_series_id"], "source_hash": snapshot["source_hash"]} for point in points]

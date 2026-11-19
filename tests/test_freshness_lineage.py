from hashlib import sha256
from pathlib import Path

import pytest

from app.data_sources.fred import resample_to_weekly_sundays
from app.data_sources.freshness_lineage import build_lineage


def test_resampling_preserves_source_date_only_when_requested():
    rows = {"2026-10-01": 3.1}
    assert resample_to_weekly_sundays(rows, end_date="2026-11-15")[-1] == {"date": "2026-11-15", "value": 3.1}
    result = resample_to_weekly_sundays(rows, end_date="2026-11-15", include_source_date=True)
    assert result[-1] == {"date": "2026-11-15", "value": 3.1, "source_date": "2026-10-01"}


def test_missing_snapshot_preserves_the_existing_fred_validation_contract(tmp_path):
    with pytest.raises(ValueError, match="fred csv does not exist"):
        build_lineage(tmp_path / "missing.csv", "CPIAUCSL")


def test_yoy_lineage_uses_original_month_and_source_hash(tmp_path):
    path = tmp_path / "CPIAUCSL.csv"
    path.write_text("observation_date,CPIAUCSL\n2025-10-01,100\n2026-10-01,103\n")
    result = build_lineage(path, "CPIAUCSL", transform="yoy", end_date="2026-11-15")
    assert result[-1]["date"] == "2026-11-15"
    assert result[-1]["value"] == 3
    assert result[-1]["source_date"] == "2026-10-01"
    assert result[-1]["source_series_id"] == "CPIAUCSL"
    assert len(result[-1]["source_hash"]) == 64


def test_hash_and_values_share_one_immutable_csv_snapshot(tmp_path, monkeypatch):
    path = tmp_path / "DGS10.csv"
    first = b"observation_date,DGS10\n2026-10-30,4.1\n2026-11-09,4.2\n"
    later = "observation_date,DGS10\n2026-10-30,4.1\n2026-11-06,4.1\n2026-11-09,4.2\n"
    path.write_bytes(first)
    read = Path.read_bytes
    def swap_after_read(file):
        result = read(file)
        if file == path:
            file.write_text(later)
        return result
    monkeypatch.setattr(Path, "read_bytes", swap_after_read)
    result = build_lineage(path, "DGS10")
    assert result[-1]["source_hash"] == sha256(first).hexdigest()
    assert result[-1]["source_date"] == "2026-10-30"

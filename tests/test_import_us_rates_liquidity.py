from pathlib import Path

import pytest

from app.db import us_rates_liquidity
from scripts import import_us_rates_liquidity


def test_rate_import_captures_original_daily_date_without_changing_counts(tmp_path):
    path = tmp_path / "DGS10.csv"
    path.write_text("observation_date,DGS10\n2026-11-06,4.1\n2026-11-09,4.2\n")
    con = us_rates_liquidity.connect(tmp_path / "market.sqlite")
    result = import_us_rates_liquidity.import_fred_csvs(con, tmp_path, ["DGS10"])
    assert result == {"treasury_10y": 1}
    row = con.execute("select source_date,basis from macro_source_lineage where dataset_id='rate:treasury_10y'").fetchone()
    assert dict(row) == {"source_date": "2026-11-06", "basis": "captured_at_import"}
    con.close()


def test_rate_import_values_and_lineage_share_the_same_csv_snapshot(tmp_path, monkeypatch):
    path = tmp_path / "DGS10.csv"
    path.write_text("observation_date,DGS10\n2026-10-30,4.1\n2026-11-09,4.2\n")
    original = Path.read_bytes
    reads = []
    def swap_after_read(file):
        content = original(file)
        if file == path:
            reads.append(file)
            file.write_text("observation_date,DGS10\n2026-10-30,4.1\n2026-11-06,4.1\n2026-11-09,4.2\n")
        return content
    monkeypatch.setattr(Path, "read_bytes", swap_after_read)
    con = us_rates_liquidity.connect(tmp_path / "data.sqlite")
    import_us_rates_liquidity.import_fred_csvs(con, tmp_path, ["DGS10"])
    row = con.execute("select value,source_date from macro_source_lineage where observation_date='2026-11-08'").fetchone()
    assert tuple(row) == (4.1, "2026-10-30")
    assert len(reads) == 1
    con.close()


def test_failed_lineage_capture_does_not_commit_new_rate_values(tmp_path, monkeypatch):
    path = tmp_path / "DGS10.csv"
    path.write_text("observation_date,DGS10\n2026-11-06,4.1\n2026-11-09,4.2\n")
    db_path = tmp_path / "data.sqlite"
    con = us_rates_liquidity.connect(db_path)
    import_us_rates_liquidity.import_fred_csvs(con, tmp_path, ["DGS10"])
    path.write_text("observation_date,DGS10\n2026-11-06,4.9\n2026-11-09,5\n")
    def fail(*args):
        raise ValueError("lineage capture failed")
    monkeypatch.setattr(import_us_rates_liquidity, "replace_lineage", fail)
    with pytest.raises(ValueError, match="lineage capture failed"):
        import_us_rates_liquidity.import_fred_csvs(con, tmp_path, ["DGS10"])
    con.close()
    con = us_rates_liquidity.connect(db_path)
    assert con.execute("select value from us_rate_points").fetchone()[0] == 4.1
    con.close()


def test_build_fred_rate_payload_uses_shared_weekly_resample(tmp_path):
    csv_path = tmp_path / "DGS10.csv"
    csv_path.write_text(
        "observation_date,DGS10\n2020-12-24,0.94\n2020-12-31,0.93\n",
        encoding="utf-8",
    )

    payload = import_us_rates_liquidity.build_fred_rate_payload(csv_path, "DGS10")

    assert payload["series"] == {
        "series_id": "treasury_10y",
        "title": "10-Year Treasury",
        "instrument_type": "nominal_treasury",
        "maturity_months": 120,
        "units": "percent",
        "source_workbook": "DGS10.csv",
        "source_sheet": "FRED weekly Sunday resample",
    }
    assert payload["points"] == [
        {
            "date": "2020-12-27",
            "value": 0.94,
            "source_workbook": "DGS10.csv",
            "source_sheet": "FRED weekly Sunday resample",
        }
    ]


def test_import_fred_csvs_replaces_rate_series(tmp_path):
    con = us_rates_liquidity.connect(tmp_path / "market_data.sqlite")
    fred_dir = tmp_path / "fred"
    fred_dir.mkdir()
    (fred_dir / "DGS10.csv").write_text(
        "observation_date,DGS10\n2020-12-24,0.94\n2020-12-31,0.93\n",
        encoding="utf-8",
    )

    inserted = import_us_rates_liquidity.import_fred_csvs(
        con,
        fred_dir,
        fred_series_ids=["DGS10"],
    )

    assert inserted == {"treasury_10y": 1}
    assert us_rates_liquidity.load_rate_points(con, "treasury_10y") == [
        {
            "date": "2020-12-27",
            "value": 0.94,
            "source_workbook": "DGS10.csv",
            "source_sheet": "FRED weekly Sunday resample",
        }
    ]


def test_fetch_fred_csvs_uses_shared_fred_client(tmp_path, monkeypatch):
    fetched = []

    class FakeFredClient:
        def __init__(self, cache_dir):
            assert cache_dir == tmp_path

        def fetch_csv(self, series_id):
            fetched.append(series_id)
            return tmp_path / f"{series_id}.csv"

        def fetch_csvs(self, series_ids):
            return {sid: self.fetch_csv(sid) for sid in series_ids}

    monkeypatch.setattr(import_us_rates_liquidity, "FredClient", FakeFredClient)

    result = import_us_rates_liquidity.fetch_fred_csvs(
        fred_dir=tmp_path,
        fred_series_ids=["DGS10", "DFII10"],
    )

    assert fetched == ["DGS10", "DFII10"]
    assert result == {
        "DGS10": tmp_path / "DGS10.csv",
        "DFII10": tmp_path / "DFII10.csv",
    }

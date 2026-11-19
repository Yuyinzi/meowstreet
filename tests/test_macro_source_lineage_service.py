from sqlite3 import connect

from app.services.macro_source_lineage import backfill_cached_lineage
from app.db.macro_source_lineage import replace_lineage
from app.services.macro_data_freshness import get_overview


def test_backfill_matches_cached_results_and_never_replaces_indicator_values(tmp_path):
    db_path = tmp_path / "data.sqlite"
    con = connect(db_path)
    con.execute("create table macro_indicator_points(series_id text,date text,value real,source text)")
    con.executemany("insert into macro_indicator_points values(?,?,?,?)", [("cpi_yoy", "2026-11-08", 3, "source"), ("cpi_yoy", "2026-11-15", 99, "source")])
    con.commit()
    before = con.execute("select * from macro_indicator_points").fetchall()
    con.close()
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / "CPIAUCSL.csv").write_text("observation_date,CPIAUCSL\n2025-10-01,100\n2026-10-01,103\n")
    result = backfill_cached_lineage(db_path, cache)
    assert result["matched_rows"] == 1
    con = connect(db_path)
    assert con.execute("select * from macro_indicator_points").fetchall() == before
    assert con.execute("select observation_date,source_date,basis from macro_source_lineage").fetchall() == [("2026-11-08", "2026-10-01", "reconstructed_from_cached_source")]
    con.close()


def test_missing_cache_does_not_claim_source_dates(tmp_path):
    path = tmp_path / "data.sqlite"
    connect(path).close()
    result = backfill_cached_lineage(path, tmp_path / "absent")
    assert result["matched_rows"] == 0


def test_backfill_preserves_unmatched_records_and_flags_conflicting_dates(tmp_path):
    db = tmp_path / "data.sqlite"
    con = connect(db)
    con.execute("create table macro_indicator_points(series_id text,date text,value real,source text)")
    con.executemany("insert into macro_indicator_points values(?,?,?,?)", [("vix", "2026-11-01", 19, "source"), ("vix", "2026-11-08", 20, "source")])
    records = [{"date": "2026-11-01", "value": 19, "source_date": "2026-10-30", "source_series_id": "VIXCLS", "source_hash": "a" * 64}, {"date": "2026-11-08", "value": 20, "source_date": "2026-11-06", "source_series_id": "VIXCLS", "source_hash": "b" * 64}]
    replace_lineage(con, "macro:vix", records, "captured_at_import")
    con.close()
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / "VIXCLS.csv").write_text("observation_date,VIXCLS\n2026-10-30,20\n2026-11-09,21\n")
    result = backfill_cached_lineage(db, cache)
    con = connect(db)
    rows = con.execute("select observation_date,source_date,basis from macro_source_lineage order by observation_date").fetchall()
    assert rows[0] == ("2026-11-01", "2026-10-30", "captured_at_import")
    assert rows[1][2] == "conflicting"
    assert result["conflicting_rows"] == 1
    con.close()
    overview = get_overview(db_path=db, notification_db_path=tmp_path / "none.sqlite")
    row = next(r for r in overview["datasets"] if r["id"] == "macro:vix")
    assert row["status"] == "unknown"
    assert "Conflicting" in row["reason"]

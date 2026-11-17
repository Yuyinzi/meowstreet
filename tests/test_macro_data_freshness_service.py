from datetime import datetime
from sqlite3 import connect

from app.services.macro_data_freshness import get_overview


def test_service_reads_real_rows_and_keeps_other_sources_explicit(tmp_path):
    path = tmp_path / "market.sqlite"
    con = connect(path)
    con.execute("create table macro_indicator_points(series_id text,date text,value real,source text)")
    con.execute("insert into macro_indicator_points values('m2_money_stock','2026-09-01',10,'source')")
    con.commit()
    con.close()
    before = path.read_bytes()
    at = datetime.fromisoformat("2026-11-13T12:00:00+08:00")
    result = get_overview(db_path=path, notification_db_path=tmp_path / "none.sqlite", as_of=at)
    row = next(r for r in result["datasets"] if r["id"] == "macro:m2_money_stock")
    assert row["status"] == "current"
    assert row["current_period"] == "2026-09-01"
    assert result["availability"] == "partial"
    assert result["history_available"] is False
    assert sum(result["counts"].values()) == len(result["datasets"])
    assert result["unavailable_datasets"] > 0
    assert path.read_bytes() == before
    assert not (tmp_path / "none.sqlite").exists()


def test_service_does_not_create_absent_data_stores(tmp_path):
    result = get_overview(db_path=tmp_path / "market.sqlite", notification_db_path=tmp_path / "tasks.sqlite")
    assert result["counts"]["unknown"] == len(result["datasets"])
    assert list(tmp_path.iterdir()) == []

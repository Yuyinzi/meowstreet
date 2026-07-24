import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = ROOT / "data" / "local_system" / "market_data.sqlite"

_MACRO_TABLES_DDL = """
create table if not exists macro_indicator_series (
    series_id text primary key,
    title text not null,
    units text not null,
    source text not null
);
create table if not exists macro_indicator_points (
    series_id text not null,
    date text not null,
    value real not null,
    source text not null,
    primary key(series_id, date),
    foreign key(series_id) references macro_indicator_series(series_id)
);
create index if not exists idx_macro_indicator_points_series_date
on macro_indicator_points(series_id, date);
"""


def init_macro_tables(con):
    con.executescript(_MACRO_TABLES_DDL)


def connect(db_path=DEFAULT_DB_PATH):
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    init_macro_tables(con)
    return con


def _normalize_series_id(series_id):
    normalized = str(series_id or "").strip().lower()
    if not normalized:
        raise ValueError("series id is required")
    return normalized


def _replace_single(con, series, points):
    sid = _normalize_series_id(series["series_id"])
    con.execute("delete from macro_indicator_points where series_id = ?", (sid,))
    con.execute("delete from macro_indicator_series where series_id = ?", (sid,))
    con.execute(
        """
        insert into macro_indicator_series(series_id, title, units, source)
        values (?, ?, ?, ?)
        """,
        (sid, series["title"], series["units"], series["source"]),
    )
    for point in points:
        con.execute(
            """
            insert into macro_indicator_points(series_id, date, value, source)
            values (?, ?, ?, ?)
            """,
            (sid, point["date"], point["value"], point["source"]),
        )


def replace_macro_indicator_points(con, series, points):
    _replace_single(con, series, points)
    con.commit()
    return {"series": 1, "points": len(points)}


def merge_macro_indicator_points(con, series, points):
    sid = _normalize_series_id(series["series_id"])
    con.execute(
        """
        insert into macro_indicator_series(series_id, title, units, source)
        values (?, ?, ?, ?)
        on conflict(series_id) do update set
            title = excluded.title,
            units = excluded.units,
            source = excluded.source
        """,
        (sid, series["title"], series["units"], series["source"]),
    )
    for point in points:
        con.execute(
            """
            insert into macro_indicator_points(series_id, date, value, source)
            values (?, ?, ?, ?)
            on conflict(series_id, date) do update set
                value = excluded.value,
                source = excluded.source
            """,
            (sid, point["date"], point["value"], point["source"]),
        )
    con.commit()
    return {"series": 1, "points": len(points)}


def insert_macro_indicator_points(con, series, points):
    sid = _normalize_series_id(series["series_id"])
    con.execute(
        "insert or ignore into macro_indicator_series(series_id, title, units, source) values (?, ?, ?, ?)",
        (sid, series["title"], series["units"], series["source"]),
    )
    for point in points:
        con.execute(
            """
            insert or ignore into macro_indicator_points(series_id, date, value, source)
            values (?, ?, ?, ?)
            """,
            (sid, point["date"], point["value"], point["source"]),
        )
    con.commit()
    return {"series": 1, "points": len(points)}


def load_macro_indicator_series(con):
    rows = con.execute(
        """
        select series_id, title, units, source
        from macro_indicator_series
        order by series_id
        """
    ).fetchall()
    return [dict(row) for row in rows]


def load_macro_indicator_points(con, series_id):
    sid = _normalize_series_id(series_id)
    rows = con.execute(
        """
        select date, value, source
        from macro_indicator_points
        where series_id = ?
        order by date
        """,
        (sid,),
    ).fetchall()
    return [dict(row) for row in rows]


def load_latest_macro_indicator_points(con):
    rows = con.execute(
        """
        select p.series_id, p.date, p.value, p.source
        from macro_indicator_points p
        join (
            select series_id, max(date) as max_date
            from macro_indicator_points
            group by series_id
        ) latest
        on latest.series_id = p.series_id and latest.max_date = p.date
        order by p.series_id
        """
    ).fetchall()
    return [dict(row) for row in rows]


def load_macro_indicator_points_for_series(con, series_ids):
    normalized_ids = [_normalize_series_id(sid) for sid in series_ids]
    return {sid: load_macro_indicator_points(con, sid) for sid in normalized_ids}


def replace_macro_indicator_points_batch(con, series_points_list):
    try:
        for item in series_points_list:
            _replace_single(con, item["series"], item["points"])
        con.commit()
    except Exception:
        con.rollback()
        raise

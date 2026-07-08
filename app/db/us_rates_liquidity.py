import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = ROOT / "data" / "local_system" / "market_data.sqlite"


def connect(db_path=DEFAULT_DB_PATH):
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.executescript(
        """
        pragma journal_mode = wal;
        create table if not exists us_rate_series (
            series_id text primary key,
            title text not null,
            instrument_type text not null,
            maturity_months integer,
            units text not null,
            source_workbook text not null,
            source_sheet text not null
        );
        create table if not exists us_rate_points (
            series_id text not null,
            date text not null,
            value real not null,
            source_workbook text not null,
            source_sheet text not null,
            primary key(series_id, date),
            foreign key(series_id) references us_rate_series(series_id)
        );
        create index if not exists idx_us_rate_points_series_date
        on us_rate_points(series_id, date);
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
        create table if not exists macro_ai_interpretations (
            scope text not null,
            snapshot_hash text not null,
            as_of text,
            prompt_version text not null,
            model text not null,
            tone text not null,
            status text not null,
            text_en text not null,
            text_zh text not null,
            metrics_json text not null,
            generated_at text not null,
            primary key(scope, snapshot_hash)
        );
        create index if not exists idx_macro_ai_interpretations_scope_generated
        on macro_ai_interpretations(scope, generated_at);
        """
    )
    return con


def normalize_series_id(series_id):
    normalized = str(series_id or "").strip().lower()
    if not normalized:
        raise ValueError("rate series id is required")
    return normalized


def replace_rate_series_points(con, series, points):
    sid = normalize_series_id(series["series_id"])
    con.execute("delete from us_rate_points where series_id = ?", (sid,))
    con.execute("delete from us_rate_series where series_id = ?", (sid,))
    con.execute(
        """
        insert into us_rate_series(
            series_id, title, instrument_type, maturity_months,
            units, source_workbook, source_sheet
        ) values (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            sid,
            series["title"],
            series["instrument_type"],
            series.get("maturity_months"),
            series["units"],
            series["source_workbook"],
            series["source_sheet"],
        ),
    )
    for point in points:
        con.execute(
            """
            insert into us_rate_points(
                series_id, date, value, source_workbook, source_sheet
            ) values (?, ?, ?, ?, ?)
            """,
            (
                sid,
                point["date"],
                point["value"],
                point["source_workbook"],
                point["source_sheet"],
            ),
        )
    con.commit()
    return {"series": 1, "points": len(points)}


def load_rate_series(con):
    rows = con.execute(
        """
        select series_id, title, instrument_type, maturity_months,
               units, source_workbook, source_sheet
        from us_rate_series
        order by instrument_type, maturity_months, series_id
        """
    ).fetchall()
    return [dict(row) for row in rows]


def load_rate_points(con, series_id):
    sid = normalize_series_id(series_id)
    rows = con.execute(
        """
        select date, value, source_workbook, source_sheet
        from us_rate_points
        where series_id = ?
        order by date
        """,
        (sid,),
    ).fetchall()
    return [dict(row) for row in rows]


def load_latest_points(con):
    rows = con.execute(
        """
        select p.series_id, p.date, p.value, p.source_workbook, p.source_sheet
        from us_rate_points p
        join (
            select series_id, max(date) as max_date
            from us_rate_points
            group by series_id
        ) latest
        on latest.series_id = p.series_id and latest.max_date = p.date
        order by p.series_id
        """
    ).fetchall()
    return [dict(row) for row in rows]


def load_rate_points_for_series(con, series_ids):
    normalized_ids = [normalize_series_id(series_id) for series_id in series_ids]
    grouped = {series_id: [] for series_id in normalized_ids}
    for series_id in normalized_ids:
        grouped[series_id] = load_rate_points(con, series_id)
    return grouped


def replace_macro_indicator_points(con, series, points):
    sid = normalize_series_id(series["series_id"])
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
    con.commit()
    return {"series": 1, "points": len(points)}


def merge_macro_indicator_points(con, series, points):
    sid = normalize_series_id(series["series_id"])
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
    sid = normalize_series_id(series_id)
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
    normalized_ids = [normalize_series_id(series_id) for series_id in series_ids]
    return {
        series_id: load_macro_indicator_points(con, series_id)
        for series_id in normalized_ids
    }


def replace_ai_interpretation(con, row):
    con.execute(
        """
        insert into macro_ai_interpretations(
            scope, snapshot_hash, as_of, prompt_version, model, tone, status,
            text_en, text_zh, metrics_json, generated_at
        ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        on conflict(scope, snapshot_hash) do update set
            as_of = excluded.as_of,
            prompt_version = excluded.prompt_version,
            model = excluded.model,
            tone = excluded.tone,
            status = excluded.status,
            text_en = excluded.text_en,
            text_zh = excluded.text_zh,
            metrics_json = excluded.metrics_json,
            generated_at = excluded.generated_at
        """,
        (
            row["scope"],
            row["snapshot_hash"],
            row.get("as_of"),
            row["prompt_version"],
            row["model"],
            row["tone"],
            row["status"],
            row["text_en"],
            row["text_zh"],
            row["metrics_json"],
            row["generated_at"],
        ),
    )
    con.commit()
    return {"interpretations": 1}


def load_ai_interpretation(con, scope, snapshot_hash):
    rows = con.execute(
        """
        select scope, as_of, snapshot_hash, prompt_version, model, tone, status,
               text_en, text_zh, metrics_json, generated_at
        from macro_ai_interpretations
        where scope = ? and snapshot_hash = ?
        """,
        (scope, snapshot_hash),
    ).fetchall()
    return dict(rows[0]) if rows else None

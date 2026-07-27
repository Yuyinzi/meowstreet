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
create table if not exists macro_indicator_observation_metadata (
    series_id text not null,
    date text not null,
    release_date text,
    revision_status text,
    source_url text,
    source_identifier text,
    source_hash text,
    primary key(series_id, date),
    foreign key(series_id) references macro_indicator_series(series_id)
);
"""


def init_macro_tables(con):
    con.executescript(_MACRO_TABLES_DDL)
    try:
        con.execute(
            "alter table macro_indicator_observation_metadata add column source_hash text"
        )
    except sqlite3.OperationalError:
        pass


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


def merge_macro_indicator_points(con, series, points, commit=True):
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
    if commit:
        con.commit()
    return {"series": 1, "points": len(points)}


def insert_macro_indicator_points(con, series, points, commit=True):
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
    if commit:
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


def merge_macro_indicator_observations(con, series, observations):
    merge_macro_indicator_points(con, series, observations, commit=False)
    for observation in observations:
        con.execute(
            """insert into macro_indicator_observation_metadata(
                series_id, date, release_date, revision_status, source_url, source_identifier
            ) values (?, ?, ?, ?, ?, ?)
            on conflict(series_id, date) do update set
                release_date = excluded.release_date,
                revision_status = excluded.revision_status,
                source_url = excluded.source_url,
                source_identifier = excluded.source_identifier""",
            (
                series["series_id"],
                observation["date"],
                observation.get("release_date"),
                observation.get("revision_status"),
                observation.get("source_url"),
                observation.get("source_identifier"),
            ),
        )
    con.commit()


def load_macro_indicator_observations(con, series_id):
    sid = _normalize_series_id(series_id)
    rows = con.execute(
        """select p.date, p.value, p.source,
                  m.release_date, m.revision_status, m.source_url, m.source_identifier, m.source_hash
           from macro_indicator_points p
           left join macro_indicator_observation_metadata m
             on m.series_id = p.series_id and m.date = p.date
           where p.series_id = ?
           order by p.date""",
        (sid,),
    ).fetchall()
    return [dict(row) for row in rows]


def load_macro_indicator_observations_for_series(con, series_ids):
    normalized_ids = [_normalize_series_id(sid) for sid in series_ids]
    return {sid: load_macro_indicator_observations(con, sid) for sid in normalized_ids}


_NFIB_SERIES_METADATA = {
    "nfib_sbo_optimism": {
        "title": "Small Business Optimism Index",
        "units": "index",
        "source": "nfib_sbet_pdf",
    },
    "nfib_sbo_employment_plans": {
        "title": "Plans to Increase Employment",
        "units": "net_pct",
        "source": "nfib_sbet_pdf",
    },
    "nfib_sbo_expansion_outlook": {
        "title": "Good Time to Expand",
        "units": "net_pct",
        "source": "nfib_sbet_pdf",
    },
    "nfib_sbo_inventory_plans": {
        "title": "Plans to Increase Inventories",
        "units": "net_pct",
        "source": "nfib_sbet_pdf",
    },
    "nfib_sbo_economic_expectations": {
        "title": "Expect Economy to Improve",
        "units": "net_pct",
        "source": "nfib_sbet_pdf",
    },
    "nfib_sbo_real_sales_expectations": {
        "title": "Expect Real Sales Higher",
        "units": "net_pct",
        "source": "nfib_sbet_pdf",
    },
}


def merge_macro_indicator_observations_batch(con, observations):
    try:
        by_series = {}
        for obs in observations:
            sid = _normalize_series_id(obs["series_id"])
            by_series.setdefault(sid, []).append(obs)

        for sid, series_observations in by_series.items():
            meta = _NFIB_SERIES_METADATA.get(sid, {})
            series = {
                "series_id": sid,
                "title": meta.get("title", sid),
                "units": meta.get("units", "index"),
                "source": meta.get("source", "nfib_sbet_pdf"),
            }
            merge_macro_indicator_points(con, series, series_observations, commit=False)
            for obs in series_observations:
                con.execute(
                    """insert into macro_indicator_observation_metadata(
                        series_id, date, release_date, revision_status, source_url, source_identifier, source_hash
                    ) values (?, ?, ?, ?, ?, ?, ?)
                    on conflict(series_id, date) do update set
                        release_date = excluded.release_date,
                        revision_status = excluded.revision_status,
                        source_url = excluded.source_url,
                        source_identifier = excluded.source_identifier,
                        source_hash = excluded.source_hash""",
                    (
                        sid,
                        obs["date"],
                        obs.get("release_date"),
                        obs.get("revision_status"),
                        obs.get("source_url"),
                        obs.get("source_identifier"),
                        obs.get("source_hash"),
                    ),
                )

        con.commit()
        return {"series": len(by_series), "observations": len(observations)}
    except Exception:
        con.rollback()
        raise

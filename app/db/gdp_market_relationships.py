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
        create table if not exists gdp_relationships (
            relationship_id text primary key,
            title text not null,
            region text,
            economy text,
            index_name text,
            primary_lag_months integer,
            correlation_window_years integer,
            source_workbook text,
            source_sheet text
        );
        create table if not exists gdp_lag_rows (
            relationship_id text not null,
            date text not null,
            lag_months integer not null,
            index_yoy real,
            gdp_yoy real,
            rolling_correlation real,
            source_workbook text,
            source_sheet text,
            primary key(relationship_id, date, lag_months),
            foreign key(relationship_id) references gdp_relationships(relationship_id)
        );
        create index if not exists idx_gdp_lag_rows_relationship_date
        on gdp_lag_rows(relationship_id, date, lag_months);
        create table if not exists gdp_quad_rows (
            relationship_id text not null,
            date text not null,
            period_label text,
            primary_lag_months integer,
            index_level real,
            gdp_level real,
            index_direction integer,
            gdp_direction integer,
            quad_case text,
            source_workbook text,
            source_sheet text,
            primary key(relationship_id, date),
            foreign key(relationship_id) references gdp_relationships(relationship_id)
        );
        create index if not exists idx_gdp_quad_rows_relationship_date
        on gdp_quad_rows(relationship_id, date);
        create table if not exists gdp_raw_source_rows (
            relationship_id text not null,
            date text not null,
            gdp_level real,
            index_level real,
            gdp_source text,
            index_source text,
            primary key(relationship_id, date)
        );
        create index if not exists idx_gdp_raw_source_rows_relationship_date
        on gdp_raw_source_rows(relationship_id, date);
        """
    )
    return con


def normalize_relationship_id(relationship_id):
    normalized = str(relationship_id or "").strip().lower()
    if not normalized:
        raise ValueError("relationship id is required")
    return normalized


def replace_relationship_data(con, relationship, lag_rows, quad_rows):
    rid = normalize_relationship_id(relationship["relationship_id"])
    con.execute(
        "delete from gdp_lag_rows where relationship_id = ?",
        (rid,),
    )
    con.execute(
        "delete from gdp_quad_rows where relationship_id = ?",
        (rid,),
    )
    con.execute(
        "delete from gdp_relationships where relationship_id = ?",
        (rid,),
    )
    con.execute(
        """
        insert into gdp_relationships(
            relationship_id, title, region, economy, index_name,
            primary_lag_months, correlation_window_years,
            source_workbook, source_sheet
        ) values (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            rid,
            relationship.get("title"),
            relationship.get("region"),
            relationship.get("economy"),
            relationship.get("index_name"),
            relationship.get("primary_lag_months"),
            relationship.get("correlation_window_years"),
            relationship.get("source_workbook"),
            relationship.get("source_sheet"),
        ),
    )
    for row in lag_rows:
        con.execute(
            """
            insert into gdp_lag_rows(
                relationship_id, date, lag_months,
                index_yoy, gdp_yoy, rolling_correlation,
                source_workbook, source_sheet
            ) values (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                rid,
                row["date"],
                row["lag_months"],
                row.get("index_yoy"),
                row.get("gdp_yoy"),
                row.get("rolling_correlation"),
                row.get("source_workbook"),
                row.get("source_sheet"),
            ),
        )
    for row in quad_rows:
        con.execute(
            """
            insert into gdp_quad_rows(
                relationship_id, date, period_label,
                primary_lag_months, index_level, gdp_level,
                index_direction, gdp_direction, quad_case,
                source_workbook, source_sheet
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                rid,
                row["date"],
                row.get("period_label"),
                row.get("primary_lag_months"),
                row.get("index_level"),
                row.get("gdp_level"),
                row.get("index_direction"),
                row.get("gdp_direction"),
                row.get("quad_case"),
                row.get("source_workbook"),
                row.get("source_sheet"),
            ),
        )
    con.commit()
    return {
        "relationships": 1,
        "lag_rows": len(lag_rows),
        "quad_rows": len(quad_rows),
    }


def replace_raw_source_rows(con, relationship_id, raw_rows):
    rid = normalize_relationship_id(relationship_id)
    con.execute(
        "delete from gdp_raw_source_rows where relationship_id = ?",
        (rid,),
    )
    for row in raw_rows:
        con.execute(
            """
            insert into gdp_raw_source_rows(
                relationship_id, date, gdp_level, index_level,
                gdp_source, index_source
            ) values (?, ?, ?, ?, ?, ?)
            """,
            (
                rid,
                row["date"],
                row.get("gdp_level"),
                row.get("index_level"),
                row.get("gdp_source"),
                row.get("index_source"),
            ),
        )
    con.commit()
    return {"raw_rows": len(raw_rows)}


def replace_relationship_rows_for_dates(con, relationship_id, dates, lag_rows, quad_rows):
    rid = normalize_relationship_id(relationship_id)
    unique_dates = sorted({str(date_value) for date_value in dates})
    for date_iso in unique_dates:
        con.execute(
            "delete from gdp_lag_rows where relationship_id = ? and date = ?",
            (rid, date_iso),
        )
        con.execute(
            "delete from gdp_quad_rows where relationship_id = ? and date = ?",
            (rid, date_iso),
        )
    for row in lag_rows:
        con.execute(
            """
            insert into gdp_lag_rows(
                relationship_id, date, lag_months,
                index_yoy, gdp_yoy, rolling_correlation,
                source_workbook, source_sheet
            ) values (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                rid,
                row["date"],
                row["lag_months"],
                row.get("index_yoy"),
                row.get("gdp_yoy"),
                row.get("rolling_correlation"),
                row.get("source_workbook"),
                row.get("source_sheet"),
            ),
        )
    for row in quad_rows:
        con.execute(
            """
            insert into gdp_quad_rows(
                relationship_id, date, period_label,
                primary_lag_months, index_level, gdp_level,
                index_direction, gdp_direction, quad_case,
                source_workbook, source_sheet
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                rid,
                row["date"],
                row.get("period_label"),
                row.get("primary_lag_months"),
                row.get("index_level"),
                row.get("gdp_level"),
                row.get("index_direction"),
                row.get("gdp_direction"),
                row.get("quad_case"),
                row.get("source_workbook"),
                row.get("source_sheet"),
            ),
        )
    con.commit()
    return {"lag_rows": len(lag_rows), "quad_rows": len(quad_rows)}


def load_relationships(con):
    rows = con.execute(
        """
        select relationship_id, title, region, economy, index_name,
               primary_lag_months, correlation_window_years,
               source_workbook, source_sheet
        from gdp_relationships
        order by relationship_id
        """
    ).fetchall()
    return [dict(row) for row in rows]


def load_lag_rows(con, relationship_id):
    rid = normalize_relationship_id(relationship_id)
    rows = con.execute(
        """
        select relationship_id, date, lag_months,
               index_yoy, gdp_yoy, rolling_correlation,
               source_workbook, source_sheet
        from gdp_lag_rows
        where relationship_id = ?
        order by date, lag_months
        """,
        (rid,),
    ).fetchall()
    return [dict(row) for row in rows]


def load_quad_rows(con, relationship_id):
    rid = normalize_relationship_id(relationship_id)
    rows = con.execute(
        """
        select relationship_id, date, period_label,
               primary_lag_months, index_level, gdp_level,
               index_direction, gdp_direction, quad_case,
               source_workbook, source_sheet
        from gdp_quad_rows
        where relationship_id = ?
        order by date
        """,
        (rid,),
    ).fetchall()
    return [dict(row) for row in rows]


def load_raw_source_rows(con, relationship_id):
    rid = normalize_relationship_id(relationship_id)
    rows = con.execute(
        """
        select relationship_id, date, gdp_level, index_level,
               gdp_source, index_source
        from gdp_raw_source_rows
        where relationship_id = ?
        order by date
        """,
        (rid,),
    ).fetchall()
    return [dict(row) for row in rows]

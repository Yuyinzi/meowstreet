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
        create table if not exists benchmark_prices (
            benchmark_id text not null,
            date text not null,
            open real,
            high real,
            low real,
            close real not null,
            source text not null,
            source_updated_at text not null default current_timestamp,
            primary key(benchmark_id, date)
        );
        create index if not exists idx_benchmark_prices_benchmark_date
        on benchmark_prices(benchmark_id, date);
        """
    )
    return con


def normalize_benchmark_id(benchmark_id):
    normalized = str(benchmark_id or "").strip().lower()
    if not normalized:
        raise ValueError("benchmark id is required")
    return normalized


def save_benchmark_prices(con, benchmark_id, rows, source):
    normalized_id = normalize_benchmark_id(benchmark_id)
    con.execute(
        "delete from benchmark_prices where benchmark_id = ?",
        (normalized_id,),
    )
    inserted = 0
    for row in rows:
        con.execute(
            """
            insert into benchmark_prices(
                benchmark_id, date, open, high, low, close, source
            ) values (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                normalized_id,
                row["date"],
                row.get("open"),
                row.get("high"),
                row.get("low"),
                row["close"],
                source,
            ),
        )
        inserted += 1
    con.commit()
    return inserted


def latest_price_date(con, benchmark_id):
    normalized_id = normalize_benchmark_id(benchmark_id)
    row = con.execute(
        "select max(date) from benchmark_prices where benchmark_id = ?",
        (normalized_id,),
    ).fetchone()
    return row[0] if row else None


def load_price_rows(con, benchmark_id):
    normalized_id = normalize_benchmark_id(benchmark_id)
    rows = con.execute(
        """
        select date, open, high, low, close
        from benchmark_prices
        where benchmark_id = ?
        order by date
        """,
        (normalized_id,),
    ).fetchall()
    return [dict(row) for row in rows]

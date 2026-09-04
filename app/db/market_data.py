import sqlite3
from datetime import date, timedelta
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
        create table if not exists prices (
            symbol text not null,
            interval text not null,
            date text not null,
            open real,
            high real,
            low real,
            close real,
            adjusted_close real not null,
            volume integer,
            primary key(symbol, interval, date)
        );
        create index if not exists idx_prices_symbol_interval_date
        on prices(symbol, interval, date);
        """
    )
    return con


def connect_read_only(db_path=DEFAULT_DB_PATH):
    path = Path(db_path)
    if not path.exists():
        return None
    con = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def normalize_symbol(symbol):
    normalized = str(symbol or "").strip().upper()
    if not normalized:
        raise ValueError("symbol is required")
    return normalized


def save_price_rows(con, symbol, interval, rows):
    normalized_symbol = normalize_symbol(symbol)
    inserted = 0
    for row in rows:
        con.execute(
            """
            insert or replace into prices(
                symbol, interval, date, open, high, low, close, adjusted_close, volume
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                normalized_symbol,
                interval,
                row["date"],
                row.get("open"),
                row.get("high"),
                row.get("low"),
                row.get("close"),
                row["adjusted_close"],
                row.get("volume"),
            ),
        )
        inserted += 1
    con.commit()
    return inserted


def latest_price_date(con, symbol, interval):
    normalized_symbol = normalize_symbol(symbol)
    row = con.execute(
        "select max(date) from prices where symbol = ? and interval = ?",
        (normalized_symbol, interval),
    ).fetchone()
    return row[0] if row else None


def load_price_rows(con, symbol, interval, start_date=None):
    normalized_symbol = normalize_symbol(symbol)
    if start_date:
        rows = con.execute(
            """
            select date, open, high, low, close, adjusted_close, volume
            from prices
            where symbol = ? and interval = ? and date >= ?
            order by date
            """,
            (normalized_symbol, interval, start_date),
        ).fetchall()
    else:
        rows = con.execute(
            """
            select date, open, high, low, close, adjusted_close, volume
            from prices
            where symbol = ? and interval = ?
            order by date
            """,
            (normalized_symbol, interval),
        ).fetchall()
    return [dict(row) for row in rows]


def _parse_date(value):
    return date.fromisoformat(value)


def should_refresh_prices(latest_date, today_date, refresh_days=1):
    if latest_date is None:
        return True
    return (_parse_date(today_date) - _parse_date(latest_date)).days > refresh_days


def fetch_start_date(latest_date, today_date, overlap_days=5, days_back=420):
    if latest_date is None:
        return "1920-01-01"
    start = _parse_date(latest_date) - timedelta(days=overlap_days)
    return start.isoformat()


def load_recent_daily_volumes(con, symbol, limit=30):
    normalized_symbol = normalize_symbol(symbol)
    try:
        rows = con.execute(
            """
            select volume
            from prices
            where symbol = ? and interval = '1d' and volume is not null
            order by date desc
            limit ?
            """,
            (normalized_symbol, limit),
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    return [row["volume"] for row in rows]


def load_latest_daily_close(con, symbol):
    normalized_symbol = normalize_symbol(symbol)
    try:
        row = con.execute(
            """
            select close
            from prices
            where symbol = ? and interval = '1d' and close is not null
            order by date desc
            limit 1
            """,
            (normalized_symbol,),
        ).fetchone()
    except sqlite3.OperationalError:
        return None
    return row["close"] if row else None

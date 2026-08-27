import sqlite3
from datetime import UTC, datetime
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
        create table if not exists screener_universe (
            symbol text primary key,
            name text,
            market_cap real,
            price real,
            industry text,
            fetched_at text not null
        );
        create table if not exists screener_estimates (
            symbol text primary key,
            eps_fy0 real,
            eps_fy1 real,
            eps_fy2 real,
            provider text not null,
            fetched_at text not null
        );
        """
    )
    estimate_columns = {
        row[1] for row in con.execute("pragma table_info(screener_estimates)").fetchall()
    }
    if "error" not in estimate_columns:
        con.execute("alter table screener_estimates add column error text")
    return con


def normalize_symbol(symbol):
    normalized = str(symbol or "").strip().upper()
    if not normalized:
        raise ValueError("symbol is required")
    return normalized


def _now_iso():
    return datetime.now(UTC).isoformat()


def universe_fresh(rows_fetched_at_max, max_age_seconds=72000):
    if rows_fetched_at_max is None:
        return False
    fetched_at = rows_fetched_at_max.get("max_fetched_at")
    if not fetched_at:
        return False
    try:
        fetched = datetime.fromisoformat(fetched_at)
    except (ValueError, TypeError):
        return False
    if fetched.tzinfo is None:
        fetched = fetched.replace(tzinfo=UTC)
    return (datetime.now(UTC) - fetched).total_seconds() <= max_age_seconds


def save_universe(con, rows):
    fetched_at = _now_iso()
    con.executemany(
        """
        insert or replace into screener_universe(
            symbol, name, market_cap, price, industry, fetched_at
        ) values (?, ?, ?, ?, ?, ?)
        """,
        [
            (
                row["symbol"],
                row.get("name"),
                row.get("market_cap"),
                row.get("price"),
                row.get("industry"),
                fetched_at,
            )
            for row in rows
        ],
    )
    con.commit()


def load_universe(con):
    rows = con.execute(
        """
        select symbol, name, market_cap, price, industry, fetched_at
        from screener_universe
        order by symbol
        """
    ).fetchall()
    return [dict(row) for row in rows]


def estimate_fresh(row, max_age_seconds=72000):
    if row is None:
        return False
    fetched_at = row.get("fetched_at")
    if not fetched_at:
        return False
    try:
        fetched = datetime.fromisoformat(fetched_at)
    except (ValueError, TypeError):
        return False
    if fetched.tzinfo is None:
        fetched = fetched.replace(tzinfo=UTC)
    return (datetime.now(UTC) - fetched).total_seconds() <= max_age_seconds


def save_estimate(con, estimate):
    symbol = normalize_symbol(estimate.get("symbol"))
    provider = str(estimate.get("provider") or "").strip()
    if not provider:
        raise ValueError(f"provider is required for {symbol}")
    fetched_at = estimate.get("fetched_at") or _now_iso()
    con.execute(
        """
        insert or replace into screener_estimates(
            symbol, eps_fy0, eps_fy1, eps_fy2, provider, fetched_at
        ) values (?, ?, ?, ?, ?, ?)
        """,
        (
            symbol,
            estimate.get("eps_fy0"),
            estimate.get("eps_fy1"),
            estimate.get("eps_fy2"),
            provider,
            fetched_at,
        ),
    )
    con.commit()


def load_estimate(con, symbol):
    normalized = normalize_symbol(symbol)
    row = con.execute(
        """
        select symbol, eps_fy0, eps_fy1, eps_fy2, provider, fetched_at, error
        from screener_estimates
        where symbol = ?
        """,
        (normalized,),
    ).fetchone()
    return dict(row) if row else None


def save_estimate_error(con, symbol, reason, provider="stockanalysis"):
    normalized = normalize_symbol(symbol)
    reason_text = str(reason or "").strip()
    if not reason_text:
        raise ValueError(f"error reason is required for {normalized}")
    con.execute(
        """
        insert or replace into screener_estimates(
            symbol, eps_fy0, eps_fy1, eps_fy2, provider, fetched_at, error
        ) values (?, null, null, null, ?, ?, ?)
        """,
        (normalized, provider, _now_iso(), reason_text),
    )
    con.commit()


def list_industries(con):
    rows = con.execute(
        """
        select industry, count(*) as stock_count
        from screener_universe
        where industry is not null and trim(industry) != ''
        group by industry
        order by industry collate nocase
        """
    ).fetchall()
    return [dict(row) for row in rows]

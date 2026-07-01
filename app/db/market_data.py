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

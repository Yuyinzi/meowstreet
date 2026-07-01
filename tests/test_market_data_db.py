import sqlite3

from app.db import market_data


def test_connect_creates_prices_table(tmp_path):
    db_path = tmp_path / "market_data.sqlite"

    con = market_data.connect(db_path)
    columns = {
        row[1]
        for row in con.execute("pragma table_info(prices)").fetchall()
    }
    indexes = {
        row[1]
        for row in con.execute("pragma index_list(prices)").fetchall()
    }
    con.close()

    assert columns == {
        "symbol",
        "interval",
        "date",
        "open",
        "high",
        "low",
        "close",
        "adjusted_close",
        "volume",
    }
    assert "sqlite_autoindex_prices_1" in indexes
    assert sqlite3.connect(db_path).execute("select count(*) from prices").fetchone()[0] == 0


def price_rows():
    return [
        {
            "date": "2026-06-01",
            "open": 100.0,
            "high": 110.0,
            "low": 99.0,
            "close": 108.0,
            "adjusted_close": 108.0,
            "volume": 1000,
        },
        {
            "date": "2026-06-02",
            "open": 108.0,
            "high": 112.0,
            "low": 107.0,
            "close": 111.0,
            "adjusted_close": 111.0,
            "volume": 1200,
        },
    ]


def test_save_price_rows_upserts_rows_and_normalizes_symbol(tmp_path):
    con = market_data.connect(tmp_path / "market_data.sqlite")

    saved = market_data.save_price_rows(con, " aapl ", "1d", price_rows())
    replacement = [dict(price_rows()[0], close=109.0, adjusted_close=109.0)]
    updated = market_data.save_price_rows(con, "AAPL", "1d", replacement)
    rows = con.execute(
        "select symbol, interval, date, close, adjusted_close from prices order by date"
    ).fetchall()
    con.close()

    assert saved == 2
    assert updated == 1
    assert [dict(row) for row in rows] == [
        {
            "symbol": "AAPL",
            "interval": "1d",
            "date": "2026-06-01",
            "close": 109.0,
            "adjusted_close": 109.0,
        },
        {
            "symbol": "AAPL",
            "interval": "1d",
            "date": "2026-06-02",
            "close": 111.0,
            "adjusted_close": 111.0,
        },
    ]


def test_latest_price_date_and_load_price_rows(tmp_path):
    con = market_data.connect(tmp_path / "market_data.sqlite")
    market_data.save_price_rows(con, "AAPL", "1d", price_rows())

    latest = market_data.latest_price_date(con, "AAPL", "1d")
    rows = market_data.load_price_rows(con, "AAPL", "1d")
    rows_since = market_data.load_price_rows(con, "AAPL", "1d", start_date="2026-06-02")
    con.close()

    assert latest == "2026-06-02"
    assert [row["date"] for row in rows] == ["2026-06-01", "2026-06-02"]
    assert [row["date"] for row in rows_since] == ["2026-06-02"]

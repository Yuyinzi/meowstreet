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

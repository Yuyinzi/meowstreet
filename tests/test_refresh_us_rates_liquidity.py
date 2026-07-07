import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import refresh_us_rates_liquidity


class FakeConnection:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


def test_main_fetches_and_imports_fred_by_default(capsys):
    calls = []
    connection = FakeConnection()

    def fake_connect(db_path):
        calls.append(("connect", db_path))
        return connection

    def fake_fetch_rates():
        calls.append(("fetch_rates",))
        return {"DGS10": Path("fred/DGS10.csv"), "DFII10": Path("fred/DFII10.csv")}

    def fake_fetch_macro():
        calls.append(("fetch_macro",))
        return {
            "CPIAUCSL": Path("fred/CPIAUCSL.csv"),
            "VIXCLS": Path("fred/VIXCLS.csv"),
        }

    def fake_import_rates(con):
        assert con is connection
        calls.append(("import_rates",))
        return {"treasury_10y": 3079, "tips_10y": 1200}

    def fake_import_macro(con):
        assert con is connection
        calls.append(("import_macro",))
        return {"cpi_yoy": 2900, "vix": 1800}

    def fake_import_credit(con):
        assert con is connection
        calls.append(("import_credit",))
        return {"aaa_corporate_yield": 6269}

    exit_code = refresh_us_rates_liquidity.main(
        [],
        connect=fake_connect,
        fetch_rates=fake_fetch_rates,
        fetch_macro=fake_fetch_macro,
        import_rates=fake_import_rates,
        import_macro=fake_import_macro,
        import_credit=fake_import_credit,
    )

    captured = capsys.readouterr()

    assert exit_code == 0
    assert calls == [
        ("connect", refresh_us_rates_liquidity.us_rates_liquidity.DEFAULT_DB_PATH),
        ("fetch_rates",),
        ("fetch_macro",),
        ("import_rates",),
        ("import_macro",),
        ("import_credit",),
    ]
    assert connection.closed is True
    assert "rates fetched: 2" in captured.out
    assert "macro fetched: 2" in captured.out
    assert "treasury_10y: 3079" in captured.out
    assert "vix: 1800" in captured.out
    assert captured.err == ""


def test_main_skip_fetch_only_imports_existing_csvs(capsys):
    calls = []
    connection = FakeConnection()

    def fake_connect(db_path):
        calls.append(("connect", db_path))
        return connection

    def fake_fetch_rates():
        calls.append(("fetch_rates",))
        return {}

    def fake_fetch_macro():
        calls.append(("fetch_macro",))
        return {}

    def fake_import_rates(con):
        calls.append(("import_rates",))
        return {"treasury_10y": 3079}

    def fake_import_macro(con):
        calls.append(("import_macro",))
        return {"cpi_yoy": 2900}

    def fake_import_credit(con):
        calls.append(("import_credit",))
        return {"aaa_corporate_yield": 6269}

    exit_code = refresh_us_rates_liquidity.main(
        ["--skip-fetch"],
        connect=fake_connect,
        fetch_rates=fake_fetch_rates,
        fetch_macro=fake_fetch_macro,
        import_rates=fake_import_rates,
        import_macro=fake_import_macro,
        import_credit=fake_import_credit,
    )

    captured = capsys.readouterr()

    assert exit_code == 0
    assert calls == [
        ("connect", refresh_us_rates_liquidity.us_rates_liquidity.DEFAULT_DB_PATH),
        ("import_rates",),
        ("import_macro",),
        ("import_credit",),
    ]
    assert "fetch skipped" in captured.out
    assert captured.err == ""


def test_main_forwards_custom_db_path(capsys):
    calls = []
    connection = FakeConnection()

    def fake_connect(db_path):
        calls.append(db_path)
        return connection

    exit_code = refresh_us_rates_liquidity.main(
        ["--db-path", "tmp/market_data.sqlite", "--skip-fetch"],
        connect=fake_connect,
        fetch_rates=lambda: {},
        fetch_macro=lambda: {},
        import_rates=lambda con: {},
        import_macro=lambda con: {},
        import_credit=lambda con: {},
    )

    assert exit_code == 0
    assert calls == [Path("tmp/market_data.sqlite")]
    assert capsys.readouterr().err == ""


def test_main_reports_value_errors(capsys):
    def fake_connect(db_path):
        return FakeConnection()

    def fake_fetch_rates():
        raise ValueError("fred rate series is unsupported: BAD")

    exit_code = refresh_us_rates_liquidity.main(
        [],
        connect=fake_connect,
        fetch_rates=fake_fetch_rates,
        fetch_macro=lambda: {},
        import_rates=lambda con: {},
        import_macro=lambda con: {},
        import_credit=lambda con: {},
    )

    captured = capsys.readouterr()

    assert exit_code == 1
    assert captured.out == ""
    assert captured.err == "fred rate series is unsupported: BAD\n"


def test_main_imports_corporate_credit_after_rates_and_macro(capsys):
    calls = []
    connection = FakeConnection()

    def fake_connect(db_path):
        calls.append(("connect", db_path))
        return connection

    def fake_fetch_rates():
        calls.append(("fetch_rates",))
        return {}

    def fake_fetch_macro():
        calls.append(("fetch_macro",))
        return {}

    def fake_import_rates(con):
        calls.append(("import_rates",))
        return {"treasury_10y": 3079}

    def fake_import_macro(con):
        calls.append(("import_macro",))
        return {"cpi_yoy": 2900}

    def fake_import_credit(con):
        calls.append(("import_credit",))
        return {"aaa_corporate_yield": 6269, "bbb_corporate_yield": 6269}

    exit_code = refresh_us_rates_liquidity.main(
        ["--skip-fetch"],
        connect=fake_connect,
        fetch_rates=fake_fetch_rates,
        fetch_macro=fake_fetch_macro,
        import_rates=fake_import_rates,
        import_macro=fake_import_macro,
        import_credit=fake_import_credit,
    )

    captured = capsys.readouterr()

    assert exit_code == 0
    assert ("import_credit",) in calls
    assert calls.index(("import_rates",)) < calls.index(("import_credit",))
    assert calls.index(("import_macro",)) < calls.index(("import_credit",))
    assert "corporate credit imported:" in captured.out
    assert "aaa_corporate_yield: 6269" in captured.out

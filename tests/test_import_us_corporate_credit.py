from app.db import macro_indicators
from app.db import us_rates_liquidity
from scripts import import_us_corporate_credit


def test_build_fred_corporate_credit_payload_parses_csv(tmp_path):
    csv_path = tmp_path / "BAMLC0A4CBBBEY.csv"
    csv_path.write_text(
        "observation_date,BAMLC0A4CBBBEY\n"
        "2023-10-01,6.10\n"
        "2023-10-02,.\n"
        "2023-10-03,6.08\n",
        encoding="utf-8",
    )

    payload = import_us_corporate_credit.build_fred_corporate_credit_payload(
        csv_path,
        "BAMLC0A4CBBBEY",
    )

    assert payload["series"] == {
        "series_id": "bbb_corporate_yield",
        "title": "BBB Corporate Yield",
        "units": "percent",
        "source": "historical reference data + FRED",
    }
    assert payload["points"] == [
        {"date": "2023-10-01", "value": 6.10, "source": "BAMLC0A4CBBBEY.csv"},
        {"date": "2023-10-03", "value": 6.08, "source": "BAMLC0A4CBBBEY.csv"},
    ]


def test_import_fred_csvs_merges_with_existing_history(tmp_path):
    con = us_rates_liquidity.connect(tmp_path / "market_data.sqlite")
    fred_dir = tmp_path / "fred"
    fred_dir.mkdir()
    macro_indicators.replace_macro_indicator_points(
        con,
        {
            "series_id": "aaa_corporate_yield",
            "title": "AAA Corporate Yield",
            "units": "percent",
            "source": "historical reference data",
        },
        [
            {"date": "2021-01-04", "value": 1.56, "source": "history.csv"},
            {"date": "2021-01-05", "value": 1.58, "source": "history.csv"},
        ],
    )
    (fred_dir / "BAMLC0A1CAAAEY.csv").write_text(
        "observation_date,BAMLC0A1CAAAEY\n2023-10-01,5.20\n",
        encoding="utf-8",
    )

    inserted = import_us_corporate_credit.import_fred_csvs(
        con,
        fred_dir,
        ["BAMLC0A1CAAAEY"],
    )
    points = macro_indicators.load_macro_indicator_points(con, "aaa_corporate_yield")

    assert inserted == {"aaa_corporate_yield": 1}
    assert [row["date"] for row in points] == [
        "2021-01-04",
        "2021-01-05",
        "2023-10-01",
    ]
    assert points[-1] == {
        "date": "2023-10-01",
        "value": 5.20,
        "source": "BAMLC0A1CAAAEY.csv",
    }


def test_fetch_fred_csvs_rejects_unsupported_corporate_credit_series(tmp_path):
    try:
        import_us_corporate_credit.fetch_fred_csvs(tmp_path, ["BAD"])
    except ValueError as exc:
        assert str(exc) == "fred corporate credit series is unsupported: BAD"
    else:
        raise AssertionError("expected ValueError")

from pathlib import Path

import openpyxl

from app.db import us_rates_liquidity
from scripts import import_us_corporate_credit


def _sample_workbook(path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Data - US Corp Yields"
    ws.append(["BAMLC0A1CAAAEY", None, "BAMLC0A4CBBBEY", None, "BAMLH0A3HYCEY", None])
    ws.append(["lin", "Percent", "lin", "Percent", "lin", "Percent"])
    ws.append(["D", "Daily, Close", "D", "Daily, Close", "D", "Daily, Close"])
    ws.append([None, None, None, None, None, None])
    ws.append(["AAA title", None, "BBB title", None, "CCC title", None])
    ws.append(["Source A", None, "Source B", None, "Source C", None])
    ws.append(["date", "value", "date", "value", "date", "value"])
    ws.append(
        [
            "2021-01-04",
            1.56,
            "2021-01-04",
            2.30,
            "2021-01-04",
            8.10,
        ]
    )
    ws.append(
        [
            "2021-01-05",
            1.58,
            "2021-01-05",
            2.32,
            "2021-01-05",
            "#N/A",
        ]
    )
    wb.save(path)


def test_parse_workbook_extracts_three_corporate_yield_series(tmp_path):
    workbook_path = tmp_path / "Corporate_Bond_Indices.xlsm"
    _sample_workbook(workbook_path)

    parsed = import_us_corporate_credit.parse_workbook(workbook_path)

    assert sorted(parsed) == [
        "aaa_corporate_yield",
        "bbb_corporate_yield",
        "ccc_corporate_yield",
    ]
    assert parsed["aaa_corporate_yield"]["series"] == {
        "series_id": "aaa_corporate_yield",
        "title": "AAA Corporate Yield",
        "units": "percent",
        "source": "Corporate_Bond_Indices.xlsm",
    }
    assert parsed["aaa_corporate_yield"]["points"] == [
        {"date": "2021-01-04", "value": 1.56, "source": "Corporate_Bond_Indices.xlsm"},
        {"date": "2021-01-05", "value": 1.58, "source": "Corporate_Bond_Indices.xlsm"},
    ]
    assert parsed["bbb_corporate_yield"]["points"][-1]["value"] == 2.32
    assert len(parsed["ccc_corporate_yield"]["points"]) == 1
    assert parsed["ccc_corporate_yield"]["points"][0]["value"] == 8.10


def test_parse_workbook_skips_na_values(tmp_path):
    workbook_path = tmp_path / "Corporate_Bond_Indices.xlsm"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Data - US Corp Yields"
    ws.append(["BAMLC0A1CAAAEY", None])
    ws.append(["lin", "Percent"])
    ws.append(["D", "Daily, Close"])
    ws.append([None, None])
    ws.append(["AAA title", None])
    ws.append(["Source A", None])
    ws.append(["date", "value"])
    ws.append(["2021-01-04", "#N/A"])
    ws.append(["2021-01-05", 1.58])
    wb.save(workbook_path)

    parsed = import_us_corporate_credit.parse_workbook(workbook_path)

    assert len(parsed["aaa_corporate_yield"]["points"]) == 1
    assert parsed["aaa_corporate_yield"]["points"][0]["value"] == 1.58


def test_import_workbook_saves_to_macro_indicator_tables(tmp_path):
    workbook_path = tmp_path / "Corporate_Bond_Indices.xlsm"
    _sample_workbook(workbook_path)
    con = us_rates_liquidity.connect(tmp_path / "market_data.sqlite")

    inserted = import_us_corporate_credit.import_workbook(con, workbook_path)

    assert inserted["aaa_corporate_yield"] == 2
    assert inserted["bbb_corporate_yield"] == 2
    assert inserted["ccc_corporate_yield"] == 1
    points = us_rates_liquidity.load_macro_indicator_points(con, "aaa_corporate_yield")
    assert points[-1]["value"] == 1.58
    assert points[-1]["source"] == "Corporate_Bond_Indices.xlsm"
    series = us_rates_liquidity.load_macro_indicator_series(con)
    series_ids = [s["series_id"] for s in series]
    assert "aaa_corporate_yield" in series_ids
    assert "bbb_corporate_yield" in series_ids
    assert "ccc_corporate_yield" in series_ids


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
        "source": "P05 workbook + FRED",
    }
    assert payload["points"] == [
        {"date": "2023-10-01", "value": 6.10, "source": "BAMLC0A4CBBBEY.csv"},
        {"date": "2023-10-03", "value": 6.08, "source": "BAMLC0A4CBBBEY.csv"},
    ]


def test_import_fred_csvs_merges_with_existing_workbook_history(tmp_path):
    con = us_rates_liquidity.connect(tmp_path / "market_data.sqlite")
    workbook_path = tmp_path / "Corporate_Bond_Indices.xlsm"
    fred_dir = tmp_path / "fred"
    fred_dir.mkdir()
    _sample_workbook(workbook_path)
    (fred_dir / "BAMLC0A1CAAAEY.csv").write_text(
        "observation_date,BAMLC0A1CAAAEY\n2023-10-01,5.20\n",
        encoding="utf-8",
    )

    import_us_corporate_credit.import_workbook(con, workbook_path)
    inserted = import_us_corporate_credit.import_fred_csvs(
        con,
        fred_dir,
        ["BAMLC0A1CAAAEY"],
    )
    points = us_rates_liquidity.load_macro_indicator_points(con, "aaa_corporate_yield")

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

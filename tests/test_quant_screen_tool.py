import json
import math
from pathlib import Path

import pytest

from app.tools import quant_screen

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"
QUANT_ROWS_PATH = FIXTURE_DIR / "quant_screen_rows.json"
EG_PROFILES_PATH = FIXTURE_DIR / "eg_profiles.json"


@pytest.fixture
def quant_rows():
    return json.loads(QUANT_ROWS_PATH.read_text(encoding="utf-8"))["rows"]


@pytest.fixture
def eg_profiles():
    return json.loads(EG_PROFILES_PATH.read_text(encoding="utf-8"))


def _table_for_rows(rows):
    header = "Ticker\tPrice\tMarket Cap\teps0\teps1\teps2\teps3"
    lines = [header]
    for row in rows:
        price = row["expected"]["pe_fy1"] * row["eps_fy1"]
        line = "\t".join(
            str(value)
            for value in [
                row["symbol"],
                price,
                row["market_cap"],
                row.get("eps_fy0") if row.get("eps_fy0") is not None else "",
                row["eps_fy1"],
                row["eps_fy2"],
                row.get("eps_fy3") if row.get("eps_fy3") is not None else "",
            ]
        )
        lines.append(line)
    return "\n".join(lines)


def _find_row(rows, symbol):
    for row in rows:
        if row["symbol"] == symbol:
            return row
    raise ValueError(f"symbol {symbol} not found")


def _metrics_for_row(row):
    price = row["expected"]["pe_fy1"] * row["eps_fy1"]
    table = _table_for_rows([row])
    payload = quant_screen.build_screen_payload(*quant_screen.parse_screener_table(table))
    return payload["rows"][0]


@pytest.mark.parametrize("symbol", ["DELL", "MYRG"])
def test_fixture_parity_no_sign_override(quant_rows, symbol):
    source = _find_row(quant_rows, symbol)
    result = _metrics_for_row(source)
    expected = source["expected"]

    assert result["eg1"] == pytest.approx(expected["eg_f1"], abs=1e-9)
    assert result["eg2"] == pytest.approx(expected["eg_f2"], abs=1e-9)
    assert result["eg3"] == pytest.approx(expected["eg_f3"], abs=1e-9)
    assert result["pe1"] == pytest.approx(expected["pe_fy1"], abs=1e-9)
    assert result["pe2"] == pytest.approx(expected["pe_fy2"], abs=1e-9)
    assert result["pe3"] == pytest.approx(expected["pe_fy3"], abs=1e-9)
    assert result["peg1"] == pytest.approx(expected["peg_f1"], abs=1e-9)
    assert result["peg2"] == pytest.approx(expected["peg_f2"], abs=1e-9)
    assert result["peg3"] == pytest.approx(expected["peg_f3"], abs=1e-9)


def test_armk_eg1_parity_and_eg2_sign_override(quant_rows):
    source = _find_row(quant_rows, "ARMK")
    result = _metrics_for_row(source)
    expected = source["expected"]

    assert result["eg1"] == pytest.approx(expected["eg_f1"], abs=1e-9)
    assert result["eg2"] == 1.0
    assert "sign_change_override" in result["flags"]
    assert result["pe1"] == pytest.approx(expected["pe_fy1"], abs=1e-9)
    assert result["pe2"] == pytest.approx(expected["pe_fy2"], abs=1e-9)


def test_trgp_sign_change_overrides_workbook_raw_value(quant_rows):
    source = _find_row(quant_rows, "TRGP")
    result = _metrics_for_row(source)

    assert result["eg1"] == 1.0
    assert "sign_change_override" in result["flags"]
    assert source["expected"]["eg_f1"] == pytest.approx(1.25261671764918, abs=1e-9)


def test_xmtr_missing_eps_fy0_yields_none_eg1(quant_rows):
    source = _find_row(quant_rows, "XMTR")
    result = _metrics_for_row(source)

    assert result["eps_fy0"] is None
    assert result["eg1"] is None
    assert result["peg1"] is None
    assert result["eg2"] == pytest.approx(source["expected"]["eg_f2"], abs=1e-9)


@pytest.mark.parametrize("case", [str(i) for i in range(1, 11)])
def test_eg_case_longs_parity(eg_profiles, case):
    sheet = eg_profiles["longs"][case]
    s1, s2 = sheet["sector"]["v1"], sheet["sector"]["v2"]
    e1, e2 = sheet["stock"]["v1"], sheet["stock"]["v2"]
    eps_fy1, eps_fy2 = _eps_for_case(case, e1, e2)

    result, reason = quant_screen.classify_eg_case(e1, e2, s1, s2, eps_fy1, eps_fy2)

    assert result == int(case)
    assert reason is None


def _eps_for_case(case, eg1, eg2):
    if case in ("9",):
        return -1.0, 0.5
    if case in ("10",):
        return -1.0, -1.5
    if case in ("7", "8"):
        eps_fy1 = 1.0
        eps_fy2 = eps_fy1 * (1 + eg1)
        return eps_fy1, eps_fy2
    return 1.0, 1.0


def test_pe_ideal_long_filter_first_step_passes():
    metrics = {
        "pe1": 39.0,
        "pe2": 27.0,
        "eg1": 0.23,
        "eg2": 0.47,
        "peg1": 0.5,
        "market_cap": 5e9,
        "market_cap_tier": "mid",
    }
    sector_means = {"mean_pe1": 24.0, "mean_pe2": 21.0, "mean_eg1": 0.12, "mean_eg2": 0.16}
    result = quant_screen.long_filter_steps(metrics, sector_means)

    assert result["steps"][0]["passed"] is True
    assert result["steps"][0]["detail"]["pe1"] == 39.0
    assert result["steps"][0]["detail"]["mean_pe1"] == 24.0


@pytest.mark.parametrize(
    "market_cap,expected_tier",
    [
        (0.5e9, "micro"),
        (1e9, "small"),
        (2e9, "small"),
        (3e9, "mid"),
        (5e9, "mid"),
        (10e9, "large"),
        (2.5e10, "large"),
        (4e10, "mega"),
        (5e10, "mega"),
        (None, None),
    ],
)
def test_market_cap_tier_boundaries(market_cap, expected_tier):
    table = f"Ticker\tPrice\tMarket Cap\teps0\teps1\teps2\nA\t10\t{market_cap if market_cap is not None else ''}\t1\t1\t1"
    payload = quant_screen.build_screen_payload(*quant_screen.parse_screener_table(table))

    assert payload["rows"][0]["market_cap_tier"] == expected_tier


@pytest.mark.parametrize(
    "eps_prev,eps_next,expected_eg,expected_flag",
    [
        (-1.0, 1.0, 1.0, "sign_change_override"),
        (1.0, -1.0, -1.0, "sign_change_override"),
        (1.0, 1.5, 0.5, None),
        (-1.0, -1.5, -0.5, None),
        (1.0, 3.5, 2.5, "small_base_review"),
        (0.5, -2.0, -1.0, "sign_change_override"),
    ],
)
def test_eg_sign_override_and_small_base_flags(eps_prev, eps_next, expected_eg, expected_flag):
    row = {
        "symbol": "A",
        "price": 10.0,
        "market_cap": 5e9,
        "eps_fy0": eps_prev,
        "eps_fy1": eps_next,
        "eps_fy2": eps_next,
    }
    result = quant_screen.build_screen_payload([row])["rows"][0]

    assert result["eg1"] == pytest.approx(expected_eg, abs=1e-9)
    if expected_flag:
        assert expected_flag in result["flags"]


def test_parse_tsv_and_csv():
    tsv = "Ticker\tPrice\tMarket Cap\teps0\teps1\teps2\nA\t10\t5e9\t1\t1.2\t1.5"
    csv = "Ticker,Price,Market Cap,eps0,eps1,eps2\nA,10,5e9,1,1.2,1.5"

    tsv_payload = quant_screen.build_screen_payload(*quant_screen.parse_screener_table(tsv))
    csv_payload = quant_screen.build_screen_payload(*quant_screen.parse_screener_table(csv))

    assert tsv_payload["row_count"] == 1
    assert csv_payload["row_count"] == 1
    assert tsv_payload["rows"][0]["symbol"] == csv_payload["rows"][0]["symbol"] == "A"
    assert tsv_payload["rows"][0]["price"] == pytest.approx(10.0)


def test_parse_missing_required_column_raises():
    table = "Ticker\tPrice\tMarket Cap\teps1\teps2\nA\t10\t5e9\t1.2\t1.5"

    with pytest.raises(ValueError, match="missing required columns"):
        quant_screen.parse_screener_table(table)


def test_parse_bad_rows_collected_in_row_errors():
    table = (
        "Ticker\tPrice\tMarket Cap\teps0\teps1\teps2\n"
        "\t10\t5e9\t1\t1\t1\n"
        "B\t\t\t\t\t\n"
        "C\t10\t5e9\t1\t1.2\t1.5"
    )
    rows, errors = quant_screen.parse_screener_table(table)

    assert len(rows) == 1
    assert rows[0]["symbol"] == "C"
    assert len(errors) == 2
    assert errors[0]["line"] == 2
    assert "symbol" in errors[0]["reason"]
    assert errors[1]["line"] == 3
    assert "missing" in errors[1]["reason"]


def test_parse_value_cleaning():
    table = (
        "Ticker\tPrice\tMarket Cap\teps0\teps1\teps2\tSector\n"
        "A\t$1,500.50\t2,500,000,000\tNULL\tNaN\tN/A\tTech\n"
        "B\t10\t5e9\t1%\t1.2\t1.5\t"
    )
    rows, errors = quant_screen.parse_screener_table(table)

    assert len(rows) == 2
    assert rows[0]["price"] == pytest.approx(1500.50)
    assert rows[0]["market_cap"] == pytest.approx(2500000000.0)
    assert rows[0]["eps_fy0"] is None
    assert rows[0]["eps_fy1"] is None
    assert rows[0]["eps_fy2"] is None
    assert rows[0]["sector"] == "Tech"
    assert rows[1]["eps_fy0"] == pytest.approx(1.0)


def test_sector_means_and_leave_one_out():
    table = (
        "Ticker\tPrice\tMarket Cap\teps0\teps1\teps2\n"
        "A\t20\t5e9\t1\t1\t1\n"
        "B\t30\t5e9\t1\t1\t1\n"
        "C\t40\t5e9\t1\t1\t1"
    )
    payload = quant_screen.build_screen_payload(*quant_screen.parse_screener_table(table))

    assert payload["sector"]["mean_pe1"] == pytest.approx(30.0)
    assert payload["sector"]["mean_pe2"] == pytest.approx(30.0)
    assert payload["sector"]["mean_method"] == "arithmetic mean of valid values"
    contributions = payload["sector"]["leave_one_out"]
    assert len(contributions) == 3
    symbols = [item["symbol"] for item in contributions]
    assert "A" in symbols
    assert abs(contributions[0]["contribution"]) == pytest.approx(
        max(abs(item["contribution"]) for item in contributions), abs=1e-9
    )


def test_leave_one_out_sorted_by_absolute_contribution():
    table = (
        "Ticker\tPrice\tMarket Cap\teps0\teps1\teps2\n"
        "A\t10\t5e9\t1\t1\t1\n"
        "B\t20\t5e9\t1\t1\t1\n"
        "C\t100\t5e9\t1\t1\t1"
    )
    payload = quant_screen.build_screen_payload(*quant_screen.parse_screener_table(table))
    contributions = payload["sector"]["leave_one_out"]

    assert contributions[0]["symbol"] == "C"
    assert contributions[-1]["symbol"] == "B"
    for index in range(len(contributions) - 1):
        assert abs(contributions[index]["contribution"]) >= abs(
            contributions[index + 1]["contribution"]
        )


def test_unclassified_missing_eps():
    result, reason = quant_screen.classify_eg_case(0.2, 0.1, 0.12, 0.16)

    assert result == "unclassified"
    assert reason is not None


def test_unclassified_no_matching_pattern():
    result, reason = quant_screen.classify_eg_case(0.2, 0.1, 0.12, 0.16, 1.0, 1.0)

    assert result == "unclassified"
    assert "does not match" in reason


def test_empty_table_raises():
    with pytest.raises(ValueError, match="no usable rows"):
        quant_screen.build_screen_payload([])


def test_all_bad_rows_raises():
    table = "Ticker\tPrice\tMarket Cap\teps0\teps1\teps2\n\t\t\t\t\t\nB\t\t\t\t\t"
    rows, errors = quant_screen.parse_screener_table(table)

    assert len(rows) == 0
    assert len(errors) == 2
    with pytest.raises(ValueError, match="no usable rows"):
        quant_screen.build_screen_payload(rows, errors)


def test_full_payload_smoke():
    table = (
        "Ticker\tPrice\tMarket Cap\teps0\teps1\teps2\n"
        "Z\t20\t5e9\t1\t1.2\t1.5\n"
        "A\t30\t5e9\t1\t1.2\t1.5\n"
        "M\t40\t5e9\t1\t1.2\t1.5"
    )
    payload = quant_screen.build_screen_payload(*quant_screen.parse_screener_table(table))

    assert "disclaimer" in payload
    assert payload["row_count"] == 3
    pe_order = [row["pe1"] for row in payload["rows"]]
    assert pe_order == [40.0 / 1.2, 30.0 / 1.2, 20.0 / 1.2]
    for row in payload["rows"]:
        assert "long_filter" in row
        assert "short_filter" in row
        assert "steps" in row["long_filter"]
        assert "first_failed" in row["long_filter"]
        assert "passes" in row["long_filter"]
        assert "eg_case" in row


def test_pe_negative_allowed():
    row = {
        "symbol": "A",
        "price": 10.0,
        "market_cap": 5e9,
        "eps_fy0": 1.0,
        "eps_fy1": -1.0,
        "eps_fy2": 1.0,
    }
    result = quant_screen.build_screen_payload([row])["rows"][0]

    assert result["pe1"] == pytest.approx(-10.0)
    assert result["eg1"] == -1.0
    assert "sign_change_override" in result["flags"]
    assert result["peg1"] == pytest.approx(0.1)


def test_eps_zero_yields_none_pe_and_peg():
    row = {
        "symbol": "A",
        "price": 10.0,
        "market_cap": 5e9,
        "eps_fy0": 1.0,
        "eps_fy1": 0.0,
        "eps_fy2": 1.0,
    }
    result = quant_screen.build_screen_payload([row])["rows"][0]

    assert result["pe1"] is None
    assert result["peg1"] is None
    assert result["eg2"] is None
    assert result["pe2"] == pytest.approx(10.0)
    assert result["peg2"] is None


def test_filter_steps_report_null_when_inputs_missing():
    row = {
        "symbol": "B",
        "price": 10.0,
        "market_cap": None,
        "eps_fy0": None,
        "eps_fy1": None,
        "eps_fy2": None,
    }
    result = quant_screen.build_screen_payload([row])["rows"][0]

    long_passed = [step["passed"] for step in result["long_filter"]["steps"]]
    short_passed = [step["passed"] for step in result["short_filter"]["steps"]]
    assert long_passed == [None, None, None, None]
    assert short_passed == [None, None, None]
    assert result["long_filter"]["first_failed"] == "pe_premium_both_periods"
    assert result["long_filter"]["passes"] is False


def test_volatility_filter_check_passes_at_or_above_one_and_half_vix():
    result = quant_screen.volatility_filter_check(0.45, 20.0)

    assert result["passes"] is True
    assert result["stock_volatility"] == 0.45
    assert result["vix"] == 20.0
    assert result["required_volatility"] == pytest.approx(0.30)
    assert result["ratio"] == pytest.approx(2.25)


def test_volatility_filter_check_fails_below_threshold():
    result = quant_screen.volatility_filter_check(0.25, 20.0)

    assert result["passes"] is False
    assert result["required_volatility"] == pytest.approx(0.30)
    assert result["ratio"] == pytest.approx(1.25)


@pytest.mark.parametrize(
    ("annualized_volatility", "vix_level"),
    [
        (None, 20.0),
        (0.45, None),
        (None, None),
        (0.45, 0.0),
        (0.45, -5.0),
    ],
)
def test_volatility_filter_check_null_when_inputs_missing_or_invalid(
    annualized_volatility, vix_level
):
    result = quant_screen.volatility_filter_check(annualized_volatility, vix_level)

    assert result["passes"] is None
    assert result["required_volatility"] is None
    assert result["ratio"] is None
    assert result["stock_volatility"] == annualized_volatility
    assert result["vix"] == vix_level


def test_build_screen_payload_passes_through_volatility_filter():
    row = {
        "symbol": "A",
        "price": 10.0,
        "market_cap": 5e9,
        "eps_fy0": 1.0,
        "eps_fy1": 1.2,
        "eps_fy2": 1.5,
        "volatility_filter": quant_screen.volatility_filter_check(0.45, 20.0),
    }
    result = quant_screen.build_screen_payload([row])["rows"][0]

    assert result["volatility_filter"]["passes"] is True
    assert result["volatility_filter"]["ratio"] == pytest.approx(2.25)


def test_build_screen_payload_volatility_filter_defaults_to_none():
    row = {
        "symbol": "A",
        "price": 10.0,
        "market_cap": 5e9,
        "eps_fy0": 1.0,
        "eps_fy1": 1.2,
        "eps_fy2": 1.5,
    }
    result = quant_screen.build_screen_payload([row])["rows"][0]

    assert result["volatility_filter"] is None

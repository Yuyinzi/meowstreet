from pathlib import Path

import httpx
import pytest

from app.data_sources import cftc_cot
from app.http_client import HttpClient

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"
FIXTURE_PATH = FIXTURE_DIR / "cftc_disaggregated_futures_only_2026.txt"

BROKEN_TEXT = (
    '"Market_and_Exchange_Names","Report_Date_as_YYYY-MM-DD",'
    '"CFTC_Contract_Market_Code","Open_Interest_All",'
    '"Prod_Merc_Positions_Long_All","Prod_Merc_Positions_Short_All",'
    '"Swap_Positions_Long_All","Swap__Positions_Short_All","Swap__Positions_Spread_All",'
    '"M_Money_Positions_Long_All","M_Money_Positions_Short_All","M_Money_Positions_Spread_All",'
    '"Other_Rept_Positions_Long_All","Other_Rept_Positions_Short_All","Other_Rept_Positions_Spread_All",'
    '"Tot_Rept_Positions_Long_All","Tot_Rept_Positions_Short_All","NonRept_Positions_Long_All","NonRept_Positions_Short_All"\n'
    '"COPPER- #1 - COMMODITY EXCHANGE INC.",2026-07-21,001602,500000,120000,100000,'
    "80000,60000,20000,100000,,15000,30000,25000,5000,350000,290000,150000,210000\n"
)


def test_parse_disaggregated_futures_only_normalizes_wti_manager_fields():
    rows = cftc_cot.parse_disaggregated_futures_only(
        FIXTURE_PATH.read_text(),
        "https://www.cftc.gov/files/dea/history/fut_disagg_txt_2026.zip",
        "2026-07-24",
    )

    wti = [r for r in rows if r["commodity_id"] == "crude_oil_wti"]
    assert len(wti) == 1
    assert wti[0]["commodity_id"] == "crude_oil_wti"
    assert wti[0]["report_date"] == "2026-07-21"
    assert wti[0]["cftc_contract_market_code"] == "067411"
    assert wti[0]["market_name"] == ("CRUDE OIL, LIGHT SWEET-WTI - ICE FUTURES EUROPE")
    assert wti[0]["manager_longs"] == 200000.0
    assert wti[0]["manager_shorts"] == 150000.0
    assert wti[0]["open_interest"] == 1000000.0
    assert wti[0]["publication_date"] == "2026-07-24"
    assert wti[0]["report_type"] == "disaggregated_futures_only"
    assert wti[0]["source_url"] == (
        "https://www.cftc.gov/files/dea/history/fut_disagg_txt_2026.zip"
    )
    assert wti[0]["source_hash"] == cftc_cot._hash_text(FIXTURE_PATH.read_text())


def test_parse_disaggregated_futures_only_normalizes_natural_gas_contracts():
    rows = cftc_cot.parse_disaggregated_futures_only(
        FIXTURE_PATH.read_text(),
        "https://www.cftc.gov/files/dea/history/fut_disagg_txt_2026.zip",
        "2026-07-24",
    )

    henry_hub = [r for r in rows if r["commodity_id"] == "us_natural_gas"]
    assert len(henry_hub) == 1
    assert henry_hub[0]["market_name"] == "NAT GAS NYME - NEW YORK MERCANTILE EXCHANGE"
    assert henry_hub[0]["cftc_contract_market_code"] == "023651"
    assert henry_hub[0]["report_date"] == "2026-07-21"

    san_juan = [r for r in rows if r["commodity_id"] == "natural_gas"]
    assert len(san_juan) == 1
    assert san_juan[0]["market_name"] == (
        "NATURAL GAS INDEX: EP SAN JUAN - ICE FUTURES ENERGY DIV"
    )
    assert san_juan[0]["cftc_contract_market_code"] == "0233AX"
    assert san_juan[0]["report_date"] == "2026-03-03"


def test_parse_disaggregated_futures_only_rejects_missing_manager_field():
    with pytest.raises(ValueError, match="cftc row.*manager short"):
        cftc_cot.parse_disaggregated_futures_only(
            BROKEN_TEXT, "https://example.test", "2026-07-24"
        )


def test_parse_rejects_csv_with_missing_required_headers():
    bad = "A,B,C\n1,2,3\n"
    with pytest.raises(ValueError, match="cftc csv is missing required headers"):
        cftc_cot.parse_disaggregated_futures_only(
            bad, "https://example.test", "2026-07-24"
        )


def test_parse_rejects_csv_missing_contract_market_code_header():
    text = (
        '"Market_and_Exchange_Names","Report_Date_as_YYYY-MM-DD",'
        '"Open_Interest_All","M_Money_Positions_Long_All","M_Money_Positions_Short_All"\n'
        '"COPPER- #1 - COMMODITY EXCHANGE INC.",2026-07-21,500000,100000,90000\n'
    )
    with pytest.raises(ValueError, match="cftc csv is missing required headers"):
        cftc_cot.parse_disaggregated_futures_only(
            text, "https://example.test", "2026-07-24"
        )


def test_parse_rejects_row_with_empty_contract_market_code():
    text = (
        '"Market_and_Exchange_Names","Report_Date_as_YYYY-MM-DD",'
        '"CFTC_Contract_Market_Code","Open_Interest_All",'
        '"M_Money_Positions_Long_All","M_Money_Positions_Short_All"\n'
        '"COPPER- #1 - COMMODITY EXCHANGE INC.",2026-07-21,,500000,100000,90000\n'
    )
    with pytest.raises(ValueError, match="cftc row copper.*cftc contract market code"):
        cftc_cot.parse_disaggregated_futures_only(
            text, "https://example.test", "2026-07-24"
        )


def test_parse_matches_renamed_market_by_contract_code():
    text = (
        '"Market_and_Exchange_Names","Report_Date_as_YYYY-MM-DD",'
        '"CFTC_Contract_Market_Code","Open_Interest_All",'
        '"M_Money_Positions_Long_All","M_Money_Positions_Short_All"\n'
        '"COPPER-GRADE #1 - COMMODITY EXCHANGE INC.",2021-08-31,085692,500000,100000,90000\n'
    )
    code_registry = {"085692": "copper"}

    rows = cftc_cot.parse_disaggregated_futures_only(
        text,
        "https://example.test",
        "2026-07-24",
        code_registry=code_registry,
    )

    assert [row["commodity_id"] for row in rows] == ["copper"]
    assert rows[0]["cftc_contract_market_code"] == "085692"
    assert rows[0]["market_name"] == "COPPER-GRADE #1 - COMMODITY EXCHANGE INC."


def test_parse_skips_unrecognized_name_without_code_registry():
    text = (
        '"Market_and_Exchange_Names","Report_Date_as_YYYY-MM-DD",'
        '"CFTC_Contract_Market_Code","Open_Interest_All",'
        '"M_Money_Positions_Long_All","M_Money_Positions_Short_All"\n'
        '"COPPER-GRADE #1 - COMMODITY EXCHANGE INC.",2021-08-31,085692,500000,100000,90000\n'
    )

    rows = cftc_cot.parse_disaggregated_futures_only(
        text, "https://example.test", "2026-07-24"
    )

    assert rows == []


def test_cot_commodity_registry_preserves_the_video_12_energy_and_metals_universe():
    assert set(cftc_cot.COT_COMMODITY_REGISTRY.values()) == {
        "crude_oil_wti",
        "crude_oil_brent",
        "heating_oil",
        "natural_gas",
        "us_natural_gas",
        "palladium",
        "platinum",
        "silver",
        "gold",
        "copper",
        "aluminium",
        "steel",
    }


def test_fetch_historical_report_uses_identified_request_and_writes_archive(
    tmp_path,
):
    def handler(request):
        assert request.headers["User-Agent"] == "Meowstreet/1.0"
        return httpx.Response(200, content=b"official archive")

    destination = cftc_cot.fetch_historical_report(
        2026, tmp_path, http_client=HttpClient(transport=httpx.MockTransport(handler))
    )

    assert destination.read_bytes() == b"official archive"

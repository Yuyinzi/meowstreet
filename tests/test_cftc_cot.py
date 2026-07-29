from pathlib import Path

import pytest

from app.data_sources import cftc_cot

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"
FIXTURE_PATH = FIXTURE_DIR / "cftc_disaggregated_futures_only_2026.txt"

BROKEN_TEXT = (
    "Market and Exchange Names|As of Date in Form YYYY-MM-DD|Open Interest|"
    "Prod/Mercant/Processor/User Long|Prod/Mercant/Processor/User Short|"
    "Swap/Dealer Long|Swap/Dealer Short|Swap/Dealer Spread|"
    "Mkt/Money Mgr Long|Mkt/Money Mgr Short|Mkt/Money Mgr Spread|"
    "Other Reportable Long|Other Reportable Short|Other Reportable Spread|"
    "Total Reportable Long|Total Reportable Short|Non-Reptable Long|Non-Reptable Short\n"
    "COPPER - GRADE #1 - COMMODITY EXCHANGE INC.|2026-07-21|500000|120000|100000|"
    "80000|60000|20000|100000||15000|30000|25000|5000|350000|290000|150000|210000\n"
)


def test_parse_disaggregated_futures_only_normalizes_wti_manager_fields():
    rows = cftc_cot.parse_disaggregated_futures_only(
        FIXTURE_PATH.read_text(),
        "https://www.cftc.gov/files/dea/history/fut_disagg_txt_2026.zip",
        "2026-07-24",
    )

    wti = [r for r in rows if r["commodity_id"] == "crude_oil_wti"]
    assert len(wti) == 1
    assert wti[0] == {
        "commodity_id": "crude_oil_wti",
        "report_date": "2026-07-21",
        "manager_longs": 200000.0,
        "manager_shorts": 150000.0,
        "open_interest": 1000000.0,
        "publication_date": "2026-07-24",
        "report_type": "disaggregated_futures_only",
        "source_url": "https://www.cftc.gov/files/dea/history/fut_disagg_txt_2026.zip",
        "source_hash": cftc_cot._hash_text(FIXTURE_PATH.read_text()),
    }


def test_parse_disaggregated_futures_only_rejects_missing_manager_field():
    with pytest.raises(ValueError, match="cftc row.*manager short"):
        cftc_cot.parse_disaggregated_futures_only(
            BROKEN_TEXT, "https://example.test", "2026-07-24"
        )


def test_cot_commodity_registry_preserves_the_video_12_energy_and_metals_universe():
    assert set(cftc_cot.COT_COMMODITY_REGISTRY.values()) == {
        "crude_oil_wti",
        "crude_oil_brent",
        "heating_oil",
        "natural_gas",
        "palladium",
        "platinum",
        "silver",
        "gold",
        "copper",
        "aluminium",
        "steel",
    }

import io
import json
import zipfile
from pathlib import Path

import pytest

from app.data_sources import usd
from app.db import macro_indicators
from app.services import cyclical_commodities_import

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"
COT_FIXTURE = FIXTURE_DIR / "cftc_disaggregated_futures_only_2026.txt"


class FakeFredClient:
    def __init__(self, cache_dir):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def csv_path(self, series_id):
        return self.cache_dir / f"{series_id}.csv"

    def fetch_csvs(self, series_ids):
        for sid in series_ids:
            self.csv_path(sid).write_text(
                f"observation_date,{sid}\n2026-07-21,120.0\n2026-07-20,119.5\n"
            )


def _make_fake_cot_zip(target_path):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("fut_disagg_2026.txt", COT_FIXTURE.read_text())
    target_path.write_bytes(buf.getvalue())


def _write_allowlist(tmp_path, entries):
    payload = {
        "version": "cot_historical_extreme_allowlist_v1",
        "report_type": "disaggregated_futures_only",
        "position_category": "managed_money",
        "generated_at": "2026-08-03T00:00:00+00:00",
        "entries": entries,
    }
    dest = tmp_path / "allowlist.json"
    dest.write_text(json.dumps(payload), encoding="utf-8")
    return str(dest)


def _copper_and_wti_allowlist(tmp_path):
    return _write_allowlist(
        tmp_path,
        [
            {
                "commodity_id": "copper",
                "market_name": "COPPER- #1 - COMMODITY EXCHANGE INC.",
                "contract_code": "085692",
                "active": True,
            },
            {
                "commodity_id": "crude_oil_wti",
                "market_name": "CRUDE OIL, LIGHT SWEET-WTI - ICE FUTURES EUROPE",
                "contract_code": "067411",
                "active": True,
            },
        ],
    )


def test_refresh_official_fetches_cot_and_all_three_usd_series(tmp_path):
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    _make_fake_cot_zip(cache_dir / "cftc-disaggregated-futures-only-2026.zip")

    con = macro_indicators.connect(tmp_path / ".sqlite")

    usd_series = list(usd.USD_SERIES) + list(usd.INFLATION_SERIES)
    fake_fred = FakeFredClient(cache_dir)
    fake_fred.fetch_csvs(usd_series)

    result = cyclical_commodities_import.import_cached_official_(
        con, cache_dir, [2026]
    )

    assert result["cot_observations"] == 2
    assert result["usd_observations"] > 0
    loaded_cot = macro_indicators.load_cot_observations(con)
    assert len(loaded_cot) == 2


def test_replace_cot_history_rebuilds_scope_with_contract_identity(tmp_path):
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    _make_fake_cot_zip(cache_dir / "cftc-disaggregated-futures-only-2026.zip")
    allowlist_path = _copper_and_wti_allowlist(tmp_path)

    con = macro_indicators.connect(tmp_path / ".sqlite")
    result = cyclical_commodities_import.replace_cot_history(
        con, cache_dir, [2026], allowlist_path=allowlist_path
    )

    assert result["cot_observations"] == 2
    loaded = macro_indicators.load_cot_observations(con)
    by_id = {row["commodity_id"]: row for row in loaded}
    assert set(by_id) == {"copper", "crude_oil_wti"}
    assert by_id["copper"]["cftc_contract_market_code"] == "085692"
    assert by_id["crude_oil_wti"]["cftc_contract_market_code"] == "067411"
    for row in loaded:
        assert row["position_category"] == "managed_money"
        assert row["report_type"] == "disaggregated_futures_only"


def test_replace_cot_history_rolls_back_on_missing_archive(tmp_path):
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    allowlist_path = _copper_and_wti_allowlist(tmp_path)

    con = macro_indicators.connect(tmp_path / ".sqlite")
    _make_fake_cot_zip(cache_dir / "cftc-disaggregated-futures-only-2026.zip")
    cyclical_commodities_import.replace_cot_history(
        con, cache_dir, [2026], allowlist_path=allowlist_path
    )
    before = macro_indicators.load_cot_observations(con)

    with pytest.raises(ValueError, match="missing cached cftc archive"):
        cyclical_commodities_import.replace_cot_history(
            con, cache_dir, [2026, 2027], allowlist_path=allowlist_path
        )

    assert macro_indicators.load_cot_observations(con) == before


def test_replace_cot_history_rejects_allowlist_code_mismatch(tmp_path):
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    _make_fake_cot_zip(cache_dir / "cftc-disaggregated-futures-only-2026.zip")
    allowlist_path = _write_allowlist(
        tmp_path,
        [
            {
                "commodity_id": "copper",
                "market_name": "COPPER- #1 - COMMODITY EXCHANGE INC.",
                "contract_code": "999999",
                "active": True,
            },
        ],
    )

    con = macro_indicators.connect(tmp_path / ".sqlite")
    with pytest.raises(ValueError, match="does not match the allowlist"):
        cyclical_commodities_import.replace_cot_history(
            con, cache_dir, [2026], allowlist_path=allowlist_path
        )

    assert macro_indicators.load_cot_observations(con) == []


def test_replace_cot_history_skips_inactive_commodity_rows(tmp_path):
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    _make_fake_cot_zip(cache_dir / "cftc-disaggregated-futures-only-2026.zip")
    allowlist_path = _write_allowlist(
        tmp_path,
        [
            {
                "commodity_id": "copper",
                "market_name": "COPPER- #1 - COMMODITY EXCHANGE INC.",
                "contract_code": "085692",
                "active": True,
            },
            {
                "commodity_id": "crude_oil_wti",
                "market_name": "CRUDE OIL, LIGHT SWEET-WTI - ICE FUTURES EUROPE",
                "contract_code": None,
                "active": False,
                "reason": "unsupported_contract",
            },
        ],
    )

    con = macro_indicators.connect(tmp_path / ".sqlite")
    result = cyclical_commodities_import.replace_cot_history(
        con, cache_dir, [2026], allowlist_path=allowlist_path
    )

    assert result["cot_observations"] == 1
    loaded = macro_indicators.load_cot_observations(con)
    assert [row["commodity_id"] for row in loaded] == ["copper"]


def test_replace_cot_history_matches_renamed_market_by_code(tmp_path):
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    csv_text = (
        '"Market_and_Exchange_Names","Report_Date_as_YYYY-MM-DD",'
        '"CFTC_Contract_Market_Code","Open_Interest_All",'
        '"M_Money_Positions_Long_All","M_Money_Positions_Short_All"\n'
        '"COPPER-GRADE #1 - COMMODITY EXCHANGE INC.",2021-08-31,085692,500000,100000,90000\n'
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("fut_disagg_2021.txt", csv_text)
    cache_dir.joinpath("cftc-disaggregated-futures-only-2021.zip").write_bytes(
        buf.getvalue()
    )
    allowlist_path = _copper_and_wti_allowlist(tmp_path)

    con = macro_indicators.connect(tmp_path / ".sqlite")
    result = cyclical_commodities_import.replace_cot_history(
        con, cache_dir, [2021], allowlist_path=allowlist_path
    )

    assert result["cot_observations"] == 1
    loaded = macro_indicators.load_cot_observations(con)
    assert loaded[0]["commodity_id"] == "copper"
    assert loaded[0]["cftc_contract_market_code"] == "085692"
    assert loaded[0]["position_category"] == "managed_money"

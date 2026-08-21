import importlib.util
import io
import json
import zipfile
from pathlib import Path

import pytest

from app.resources import resource_path
from app.services import cot_historical_extremes_catalog as catalog

FIXTURE_PATH = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "cftc_disaggregated_futures_only_2026.txt"
)

ROOT = Path(__file__).resolve().parents[1]

VERIFIED_CODES = {
    "crude_oil_wti": "067411",
    "crude_oil_brent": "06765T",
    "heating_oil": "022651",
    "us_natural_gas": "023651",
    "palladium": "075651",
    "platinum": "076651",
    "silver": "084691",
    "gold": "088691",
    "copper": "085692",
    "aluminium": "191691",
    "steel": "192651",
}


def valid_records():
    records = []
    for commodity_id, code in VERIFIED_CODES.items():
        records.append(
            {
                "commodity_id": commodity_id,
                "market_name": _canonical_market_name(commodity_id),
                "contract_code": code,
                "active": True,
            }
        )
    return records


def _canonical_market_name(commodity_id):
    return next(
        name
        for name, cid in catalog.COT_COMMODITY_REGISTRY.items()
        if cid == commodity_id
    )


def _build_payload(**overrides):
    payload = catalog.build_cot_historical_extreme_allowlist(valid_records())
    payload.update(overrides)
    return payload


def _write_payload(tmp_path, payload):
    dest = tmp_path / "allowlist.v1.json"
    dest.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return dest


def test_load_accepts_the_checked_in_allowlist():
    path = resource_path("cot_extreme_allowlist")
    payload = catalog.load_cot_historical_extreme_allowlist(path)

    assert payload["version"] == catalog.VERSION
    assert payload["report_type"] == "disaggregated_futures_only"
    assert payload["position_category"] == "managed_money"
    entries = {entry["commodity_id"]: entry for entry in payload["entries"]}
    assert set(entries) == set(VERIFIED_CODES) | {"natural_gas"}
    for commodity_id, code in VERIFIED_CODES.items():
        entry = entries[commodity_id]
        assert entry["active"] is True
        assert entry["contract_code"] == code
    legacy = entries["natural_gas"]
    assert legacy["active"] is False
    assert legacy["contract_code"] is None
    assert legacy["reason"] == "unsupported_contract"


def test_active_entries_are_unambiguous():
    payload = catalog.load_cot_historical_extreme_allowlist(
        resource_path("cot_extreme_allowlist")
    )
    active = catalog.active_allowlist_entries(payload)

    assert set(active) == set(VERIFIED_CODES)
    assert "natural_gas" not in active
    for entry in active.values():
        assert entry["contract_code"] == VERIFIED_CODES[entry["commodity_id"]]


def test_build_sorts_entries_by_commodity_id():
    payload = catalog.build_cot_historical_extreme_allowlist(valid_records())

    assert [entry["commodity_id"] for entry in payload["entries"]] == sorted(
        VERIFIED_CODES
    )


def test_build_and_write_round_trip(tmp_path):
    dest = tmp_path / "allowlist.json"
    payload = catalog.write_cot_historical_extreme_allowlist(dest, valid_records())
    reloaded = catalog.load_cot_historical_extreme_allowlist(dest)

    assert reloaded == payload


def test_loader_rejects_duplicate_commodity_ids(tmp_path):
    payload = _build_payload()
    payload["entries"].append({**payload["entries"][0], "contract_code": "999999"})
    dest = _write_payload(tmp_path, payload)

    with pytest.raises(ValueError, match="duplicate commodities cot allowlist commodity"):
        catalog.load_cot_historical_extreme_allowlist(dest)


def test_loader_rejects_duplicate_identity_tuples(tmp_path):
    payload = _build_payload()
    entry = payload["entries"][0]
    payload["entries"].append({**entry, "market_name": entry["market_name"]})
    dest = _write_payload(tmp_path, payload)

    with pytest.raises(ValueError, match="duplicate commodities cot allowlist identity"):
        catalog.load_cot_historical_extreme_allowlist(dest)


def test_loader_rejects_active_entry_without_contract_code(tmp_path):
    payload = _build_payload()
    payload["entries"][0]["contract_code"] = None
    dest = _write_payload(tmp_path, payload)

    with pytest.raises(ValueError, match="commodities cot allowlist contract code is required"):
        catalog.load_cot_historical_extreme_allowlist(dest)


def test_loader_rejects_malformed_contract_code(tmp_path):
    payload = _build_payload()
    payload["entries"][0]["contract_code"] = "08x692"
    dest = _write_payload(tmp_path, payload)

    with pytest.raises(
        ValueError, match="commodities cot allowlist contract code is malformed"
    ):
        catalog.load_cot_historical_extreme_allowlist(dest)


def test_loader_rejects_unsupported_report_type(tmp_path):
    payload = _build_payload(report_type="futures_and_options")
    dest = _write_payload(tmp_path, payload)

    with pytest.raises(
        ValueError, match="commodities cot allowlist report type is unsupported"
    ):
        catalog.load_cot_historical_extreme_allowlist(dest)


def test_loader_rejects_unsupported_position_category(tmp_path):
    payload = _build_payload(position_category="commercial")
    dest = _write_payload(tmp_path, payload)

    with pytest.raises(
        ValueError, match="commodities cot allowlist position category is unsupported"
    ):
        catalog.load_cot_historical_extreme_allowlist(dest)


def test_loader_rejects_catalog_source_name_code_mismatch(tmp_path):
    payload = _build_payload()
    payload["entries"][0]["market_name"] = "GOLD - COMMODITY EXCHANGE INC."
    dest = _write_payload(tmp_path, payload)

    with pytest.raises(ValueError, match="commodities cot allowlist market name mismatch"):
        catalog.load_cot_historical_extreme_allowlist(dest)


def test_loader_rejects_inactive_entry_without_unsupported_reason(tmp_path):
    payload = _build_payload()
    payload["entries"][0]["active"] = False
    payload["entries"][0]["contract_code"] = None
    payload["entries"][0]["reason"] = "some_other_reason"
    dest = _write_payload(tmp_path, payload)

    with pytest.raises(ValueError, match="unsupported_contract"):
        catalog.load_cot_historical_extreme_allowlist(dest)


def test_inactive_entry_is_not_treated_as_eligible(tmp_path):
    payload = _build_payload()
    copper = next(
        entry for entry in payload["entries"] if entry["commodity_id"] == "copper"
    )
    copper["active"] = False
    copper["contract_code"] = None
    copper["reason"] = "unsupported_contract"
    dest = _write_payload(tmp_path, payload)

    reloaded = catalog.load_cot_historical_extreme_allowlist(dest)
    active = catalog.active_allowlist_entries(reloaded)

    assert "copper" not in active
    assert set(active) == set(VERIFIED_CODES) - {"copper"}


def _make_cached_zip(cache_dir, year):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        archive.writestr(f"fut_disagg_{year}.txt", FIXTURE_PATH.read_text())
    target = cache_dir / f"cftc-disaggregated-futures-only-{year}.zip"
    target.write_bytes(buf.getvalue())
    return target


def test_scan_cftc_archive_contract_pairs_reads_name_code_pairs(tmp_path):
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    _make_cached_zip(cache_dir, 2026)

    pairs = catalog.scan_cftc_archive_contract_pairs(cache_dir, [2026])

    assert ("COPPER- #1 - COMMODITY EXCHANGE INC.", "085692") in pairs["copper"]
    assert (
        "CRUDE OIL, LIGHT SWEET-WTI - ICE FUTURES EUROPE",
        "067411",
    ) in pairs["crude_oil_wti"]


def test_scan_cftc_archive_contract_pairs_requires_cached_archive(tmp_path):
    with pytest.raises(ValueError, match="missing cached cftc archive"):
        catalog.scan_cftc_archive_contract_pairs(tmp_path, [2021])


def test_derive_allowlist_records_marks_unmatched_pair_inactive():
    pairs = {"copper": {("COPPER- #1 - COMMODITY EXCHANGE INC.", "085692")}}
    seeds = [
        {
            "commodity_id": "copper",
            "market_name": "COPPER- #1 - COMMODITY EXCHANGE INC.",
            "contract_code": "085692",
        },
        {
            "commodity_id": "steel",
            "market_name": "STEEL-HRC - COMMODITY EXCHANGE INC.",
            "contract_code": "192651",
        },
    ]

    records = catalog.derive_allowlist_records(seeds, pairs)

    assert records[0]["active"] is True
    assert records[0]["contract_code"] == "085692"
    assert records[1]["active"] is False
    assert records[1]["contract_code"] is None
    assert records[1]["reason"] == "unsupported_contract"


def _load_build_script():
    path = ROOT / "scripts" / "build_cot_historical_extreme_allowlist.py"
    spec = importlib.util.spec_from_file_location(
        "build_cot_historical_extreme_allowlist", path
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_build_script_regeneration_keeps_legacy_series_inactive(tmp_path):
    module = _load_build_script()
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    _make_cached_zip(cache_dir, 2026)

    pairs = catalog.scan_cftc_archive_contract_pairs(cache_dir, [2026])
    records = catalog.derive_allowlist_records(module.ALLOWLIST_RECORDS, pairs)
    by_id = {record["commodity_id"]: record for record in records}

    assert by_id["us_natural_gas"]["active"] is True
    assert by_id["us_natural_gas"]["contract_code"] == "023651"
    assert by_id["natural_gas"]["active"] is False
    assert by_id["natural_gas"]["contract_code"] is None
    assert by_id["natural_gas"]["reason"] == "unsupported_contract"


def test_derive_allowlist_records_keeps_explicitly_inactive_seed_inactive():
    pairs = {
        "natural_gas": {
            ("NATURAL GAS INDEX: EP SAN JUAN - ICE FUTURES ENERGY DIV", "0233AX")
        }
    }
    seeds = [
        {
            "commodity_id": "natural_gas",
            "market_name": "NATURAL GAS INDEX: EP SAN JUAN - ICE FUTURES ENERGY DIV",
            "contract_code": "0233AX",
            "active": False,
            "reason": "unsupported_contract",
        },
    ]

    records = catalog.derive_allowlist_records(seeds, pairs)

    assert records[0]["active"] is False
    assert records[0]["contract_code"] is None
    assert records[0]["reason"] == "unsupported_contract"

import io
import json
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from app.data_sources import cftc_cot

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ALLOWLIST_PATH = (
    ROOT / "data" / "local_system" / "cot_historical_extreme_allowlist.v1.json"
)

VERSION = "cot_historical_extreme_allowlist_v1"
REPORT_TYPE = "disaggregated_futures_only"
POSITION_CATEGORY = "managed_money"

COT_COMMODITY_REGISTRY = cftc_cot.COT_COMMODITY_REGISTRY

_VALID_REPORT_TYPES = {"disaggregated_futures_only"}
_VALID_POSITION_CATEGORIES = {"managed_money"}
_CONTRACT_CODE_RE = re.compile(r"^[0-9A-Z]+$")
_UNSUPPORTED_REASON = "unsupported_contract"


def build_cot_historical_extreme_allowlist(records, generated_at=None):
    entries = [_normalize_entry(record) for record in records]
    _reject_duplicates(entries)
    return {
        "version": VERSION,
        "report_type": REPORT_TYPE,
        "position_category": POSITION_CATEGORY,
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
        "source_documents": ["cftc disaggregated futures-only historical archives"],
        "entries": sorted(entries, key=lambda entry: entry["commodity_id"]),
    }


def write_cot_historical_extreme_allowlist(destination, records, generated_at=None):
    payload = build_cot_historical_extreme_allowlist(
        records, generated_at=generated_at
    )
    dest = Path(destination)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return payload


def load_cot_historical_extreme_allowlist(path):
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    _validate_payload(payload)
    return payload


def active_allowlist_entries(payload):
    return {
        entry["commodity_id"]: entry
        for entry in payload.get("entries", [])
        if entry.get("active") is True
    }


def scan_cftc_archive_contract_pairs(cache_dir, years):
    pairs_by_commodity = {}
    for year in years:
        zip_path = Path(cache_dir) / f"cftc-disaggregated-futures-only-{year}.zip"
        if not zip_path.exists():
            raise ValueError(f"missing cached cftc archive for {year}")
        data = zip_path.read_bytes()
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            text_name = next(
                (name for name in archive.namelist() if name.endswith(".txt")),
                None,
            )
            if text_name is None:
                raise ValueError(f"no txt file in cftc zip for {year}")
            text = archive.read(text_name).decode("utf-8", errors="replace")
        source_url = cftc_cot.historical_report_url(year)
        rows = cftc_cot.parse_disaggregated_futures_only(text, source_url, "")
        for row in rows:
            pairs_by_commodity.setdefault(row["commodity_id"], set()).add(
                (row["market_name"], row["cftc_contract_market_code"])
            )
    return pairs_by_commodity


def derive_allowlist_records(seed_records, pairs_by_commodity):
    records = []
    for seed in seed_records:
        observed = pairs_by_commodity.get(seed["commodity_id"], set())
        if seed.get("active") is False:
            records.append(
                {
                    "commodity_id": seed["commodity_id"],
                    "market_name": seed["market_name"],
                    "contract_code": None,
                    "active": False,
                    "reason": _UNSUPPORTED_REASON,
                }
            )
        elif (seed["market_name"], seed["contract_code"]) in observed:
            records.append(
                {
                    "commodity_id": seed["commodity_id"],
                    "market_name": seed["market_name"],
                    "contract_code": seed["contract_code"],
                    "active": True,
                }
            )
        else:
            records.append(
                {
                    "commodity_id": seed["commodity_id"],
                    "market_name": seed["market_name"],
                    "contract_code": None,
                    "active": False,
                    "reason": _UNSUPPORTED_REASON,
                }
            )
    return records


def _normalize_entry(record):
    entry = {
        "commodity_id": str(record.get("commodity_id") or "").strip().lower(),
        "market_name": str(record.get("market_name") or "").strip(),
        "contract_code": str(record.get("contract_code") or "").strip() or None,
        "active": bool(record.get("active")),
        "reason": record.get("reason"),
    }
    _validate_entry(entry)
    return entry


def _validate_payload(payload):
    if payload.get("version") != VERSION:
        raise ValueError(
            f" cot historical extreme allowlist version is invalid: "
            f"{payload.get('version')}"
        )
    if payload.get("report_type") not in _VALID_REPORT_TYPES:
        raise ValueError(
            f" cot allowlist report type is unsupported: {payload.get('report_type')}"
        )
    if payload.get("position_category") not in _VALID_POSITION_CATEGORIES:
        raise ValueError(
            f" cot allowlist position category is unsupported: "
            f"{payload.get('position_category')}"
        )
    entries = payload.get("entries")
    if not isinstance(entries, list) or not entries:
        raise ValueError(" cot allowlist has no entries")
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError(" cot allowlist entry must be an object")
        _validate_entry(entry)
    _reject_duplicates(entries)


def _validate_entry(entry):
    commodity_id = entry.get("commodity_id")
    if not commodity_id:
        raise ValueError(" cot allowlist commodity id is required")
    if commodity_id not in COT_COMMODITY_REGISTRY.values():
        raise ValueError(
            f" cot allowlist commodity {commodity_id} is not a registry commodity"
        )
    market_name = entry.get("market_name")
    if not market_name:
        raise ValueError(" cot allowlist market name is required")
    if COT_COMMODITY_REGISTRY.get(market_name) != commodity_id:
        raise ValueError(f" cot allowlist market name mismatch for {commodity_id}")
    active = entry.get("active")
    if not isinstance(active, bool):
        raise ValueError(" cot allowlist active flag must be a boolean")
    contract_code = entry.get("contract_code")
    if active:
        if not contract_code:
            raise ValueError(
                " cot allowlist contract code is required for active entries"
            )
        if _CONTRACT_CODE_RE.fullmatch(str(contract_code)) is None:
            raise ValueError(" cot allowlist contract code is malformed")
        if entry.get("reason"):
            raise ValueError(" cot allowlist active entry must not carry a reason")
    elif entry.get("reason") != _UNSUPPORTED_REASON:
        raise ValueError(
            " cot allowlist inactive entry requires the unsupported_contract reason"
        )


def _reject_duplicates(entries):
    seen_identities = set()
    seen_commodities = set()
    for entry in entries:
        identity = (
            entry.get("commodity_id"),
            entry.get("contract_code"),
            REPORT_TYPE,
            POSITION_CATEGORY,
        )
        if identity in seen_identities:
            raise ValueError(
                f"duplicate  cot allowlist identity {identity[0]}:{identity[1]}"
            )
        seen_identities.add(identity)
        commodity_id = entry.get("commodity_id")
        if commodity_id in seen_commodities:
            raise ValueError(f"duplicate  cot allowlist commodity {commodity_id}")
        seen_commodities.add(commodity_id)

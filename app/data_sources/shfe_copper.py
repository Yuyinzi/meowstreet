import hashlib
import io
import json
import re
import time
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from math import isfinite

import pandas as pd

_SHFE_DAILY_REPORT_URL = (
    "https://www.shfe.com.cn/reports/tradedata/dailyandweeklydata/"
    "?query_options=1&query_params=kx&query_product_code=cu_f"
)

_SOURCE_IDENTIFIER = "SHFE:CU"

_CU_CONTRACT_RE = re.compile(r"^CU(\d{2})(\d{2})$")

_DATE_FORMAT = "%Y-%m-%d"

_REQUEST_INTERVAL_SECONDS = 0.5
_REQUEST_MAX_RETRIES = 3
_REQUEST_BACKOFF_SECONDS = 1.0

_HASH_FIELDS = [
    "trade_date",
    "contract",
    "product",
    "open",
    "high",
    "low",
    "close",
    "previous_settlement",
    "settlement",
    "volume",
    "open_interest",
    "open_interest_change",
    "turnover",
]


def _retrieved_at():
    return datetime.now(timezone.utc).isoformat()


def _compact_date(value):
    return str(value).replace("-", "")


def _iso_from_compact(value):
    return datetime.strptime(str(value), "%Y%m%d").strftime(_DATE_FORMAT)


def _trading_days(start, end, calendar_frame=None):
    import akshare as ak

    try:
        frame = calendar_frame
        if frame is None:
            frame = ak.tool_trade_date_hist_sina()
        dates = {str(d) for d in frame["trade_date"].tolist()}
    except Exception:
        dates = None
    first = datetime.strptime(_iso_from_compact(start), _DATE_FORMAT).date()
    last = datetime.strptime(_iso_from_compact(end), _DATE_FORMAT).date()
    current = first
    days = []
    while current <= last:
        day_text = current.isoformat()
        if dates is None or day_text in dates:
            days.append(day_text)
        current += timedelta(days=1)
    return days


def _fetch_day_with_retry(ak, day_text):
    last_exc = None
    for attempt in range(_REQUEST_MAX_RETRIES):
        try:
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                return ak.get_shfe_daily(date=_compact_date(day_text))
        except Exception as exc:
            last_exc = exc
            time.sleep(_REQUEST_BACKOFF_SECONDS * (attempt + 1))
    raise ValueError(
        f"akshare SHFE daily fetch failed for {day_text}: {last_exc}"
    ) from last_exc


def _akshare_daily_fetch(
    start, end, ak_module=None, calendar_frame=None, progress_callback=None
):
    if ak_module is None:
        import akshare as ak_module

    frames = []
    trading_days = _trading_days(start, end, calendar_frame)
    for completed, day_text in enumerate(trading_days, start=1):
        frame = _fetch_day_with_retry(ak_module, day_text)
        if frame is not None and not frame.empty:
            frames.append(frame)
        if progress_callback is not None:
            progress_callback(
                {
                    "date": day_text,
                    "contracts_received": 0 if frame is None else len(frame),
                    "completed": completed,
                    "total": len(trading_days),
                }
            )
        time.sleep(_REQUEST_INTERVAL_SECONDS)
    if not frames:
        return [], ak_module.__version__
    combined = pd.concat(frames, ignore_index=True)
    combined = combined.drop_duplicates(subset=["symbol", "date"]).reset_index(
        drop=True
    )
    return combined.to_dict("records"), ak_module.__version__


def _source_hash(row):
    payload = {field: row.get(field) for field in _HASH_FIELDS}
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    return digest.hexdigest()


def _normalize_date_range(start_date, end_date):
    start = _parse_request_date(start_date)
    end = _parse_request_date(end_date)
    if start > end:
        raise ValueError(f"shfe start date {start} is after end date {end}")
    return start.replace("-", ""), end.replace("-", "")


def _parse_request_date(value):
    text = str(value or "").strip()
    if not text:
        raise ValueError("shfe request date is required")
    return datetime.strptime(text, _DATE_FORMAT).strftime(_DATE_FORMAT)


def _normalize_trade_date(value):
    text = str(value or "").strip()
    for fmt in ("%Y%m%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).strftime(_DATE_FORMAT)
        except ValueError:
            continue
    return None


def _as_finite_float(value):
    if value is None or value == "":
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not isfinite(parsed):
        return None
    return parsed


def _normalize_cu_row(record, retrieved_at, adapter_version):
    raw_contract = str(record.get("symbol") or "").strip().upper()
    if not _CU_CONTRACT_RE.fullmatch(raw_contract):
        return None
    trade_date = _normalize_trade_date(record.get("date"))
    if trade_date is None:
        return None
    close = _as_finite_float(record.get("close"))
    if close is None:
        return None
    open_interest = _as_finite_float(record.get("open_interest"))
    if open_interest is None or open_interest <= 0:
        return None
    product = str(record.get("variety") or "").strip().upper() or "CU"
    normalized = {
        "trade_date": trade_date,
        "product": product,
        "contract": raw_contract,
        "open": _as_finite_float(record.get("open")),
        "high": _as_finite_float(record.get("high")),
        "low": _as_finite_float(record.get("low")),
        "close": close,
        "previous_settlement": _as_finite_float(record.get("pre_settle")),
        "settlement": _as_finite_float(record.get("settle")),
        "volume": _as_finite_float(record.get("volume")),
        "open_interest": open_interest,
        "open_interest_change": _as_finite_float(record.get("open_interest_change")),
        "turnover": _as_finite_float(record.get("turnover")),
        "source": "shfe",
        "source_class": "official_exchange",
        "access_adapter": "akshare",
        "access_adapter_version": str(adapter_version),
        "source_identifier": _SOURCE_IDENTIFIER,
        "source_url": _SHFE_DAILY_REPORT_URL,
        "retrieved_at": retrieved_at,
    }
    normalized["source_hash"] = _source_hash(normalized)
    return normalized


def normalize_shfe_copper_contract_rows(records, retrieved_at, adapter_version):
    normalized = []
    seen = set()
    for record in records or []:
        row = _normalize_cu_row(record, retrieved_at, adapter_version)
        if row is None:
            continue
        key = (row["trade_date"], row["contract"])
        if key in seen:
            continue
        seen.add(key)
        normalized.append(row)
    normalized.sort(key=lambda row: (row["trade_date"], row["contract"]))
    if not normalized:
        raise ValueError("akshare returned no valid SHFE CU contract observations")
    return normalized


def fetch_shfe_copper_contract_rows(start_date, end_date, adapter=None, progress_callback=None):
    start, end = _normalize_date_range(start_date, end_date)
    try:
        if adapter is None:
            records, adapter_version = _akshare_daily_fetch(
                start, end, progress_callback=progress_callback
            )
        else:
            records, adapter_version = adapter(start, end)
    except Exception as exc:
        raise ValueError(
            f"akshare SHFE CU fetch failed for {start} to {end}: {exc}"
        ) from exc
    return normalize_shfe_copper_contract_rows(
        records, _retrieved_at(), adapter_version
    )

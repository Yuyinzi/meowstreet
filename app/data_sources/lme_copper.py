from datetime import datetime, timezone
from math import isfinite


SINA_CAD_DAILY_URL = (
    "https://stock2.finance.sina.com.cn/futures/api/jsonp.php/"
    "var%20_S2026_8_1=/GlobalFuturesService.getGlobalFuturesDailyKLine"
)

_SOURCE_IDENTIFIER = "CAD"

_DATE_FORMAT = "%Y-%m-%d"


def _retrieved_at():
    return datetime.now(timezone.utc).isoformat()


def _normalize_sina_date(value):
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in (_DATE_FORMAT, "%Y%m%d"):
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


_LME_COPPER_SERIES_ID = "copper_lme_sina_cad_v1"
_LME_COPPER_CUTOVER_DATE = "2026-07-31"

_LME_COPPER_SERIES = {
    "series_id": _LME_COPPER_SERIES_ID,
    "title": "Copper (LME 3M)",
    "units": "USD/tonne",
    "source": "sina_finance",
    "source_class": "vendor_free_market_data",
    "access_adapter": "akshare",
    "source_identifier": _SOURCE_IDENTIFIER,
    "source_url": SINA_CAD_DAILY_URL,
    "source_contract": {
        "instrument": "LME Copper 3-month",
        "symbol": _SOURCE_IDENTIFIER,
        "source_publisher": "Sina Finance",
        "access_adapter": "akshare",
        "series_type": "vendor_continuous_3_month_quote",
        "roll_rule": "undocumented",
        "price_field": "close",
        "price_adjustment": "none",
        "official_settlement": False,
        "cutover_date": _LME_COPPER_CUTOVER_DATE,
    },
}


def normalize_lme_copper_cad_daily(frame, retrieved_at, adapter_version):
    if frame is None or frame.empty:
        raise ValueError("sina CAD frame has no rows")
    rows = []
    seen = set()
    for record in frame.to_dict("records"):
        date_text = _normalize_sina_date(record.get("date"))
        if date_text is None:
            raise ValueError("sina CAD row has an invalid date")
        close = _as_finite_float(record.get("close"))
        if close is None:
            raise ValueError("sina CAD row has an invalid close")
        if date_text in seen:
            raise ValueError(f"sina CAD row duplicates date {date_text}")
        seen.add(date_text)
        rows.append(
            {
                "date": date_text,
                "value": close,
                "source": "sina_finance",
                "source_url": SINA_CAD_DAILY_URL,
                "source_identifier": _SOURCE_IDENTIFIER,
                "source_class": "vendor_free_market_data",
                "retrieved_at": retrieved_at,
                "access_adapter_version": adapter_version,
            }
        )
    rows.sort(key=lambda row: row["date"])
    if not rows:
        raise ValueError("sina CAD returned no valid observations")
    return rows


def fetch_lme_copper_cad(adapter=None):
    try:
        if adapter is None:
            import akshare as ak

            adapter = ak.futures_foreign_hist
            adapter_version = ak.__version__
        else:
            adapter_version = "test-adapter"
        frame = adapter(symbol="CAD")
    except Exception as exc:
        raise ValueError(f"sina CAD fetch failed: {exc}") from exc
    return {
        "series": _LME_COPPER_SERIES,
        "observations": normalize_lme_copper_cad_daily(
            frame, _retrieved_at(), adapter_version
        ),
    }

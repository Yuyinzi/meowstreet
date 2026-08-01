from datetime import datetime, timezone
from math import isfinite


SINA_I0_DAILY_URL = (
    "https://stock2.finance.sina.com.cn/futures/api/jsonp.php/"
    "var%20_V21052021_4_12=/InnerFuturesNewService.getDailyKLine"
)

_SOURCE_IDENTIFIER = "I0"

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


_DCE_IRON_ORE_SINA_SERIES = {
    "series_id": "iron_ore_dce",
    "title": "Iron Ore (DCE)",
    "units": "CNY/tonne",
    "source": "sina_finance",
    "source_class": "vendor_free_market_data",
    "access_adapter": "akshare",
    "source_identifier": _SOURCE_IDENTIFIER,
    "source_url": SINA_I0_DAILY_URL,
    "source_contract": {
        "product": "I",
        "symbol": _SOURCE_IDENTIFIER,
        "roll_rule": "undocumented",
        "price_field": "close",
        "official_settlement": False,
        "price_series_version": "sina_i0_continuous_v1",
        "return_method_version": "raw_close_to_close",
    },
}


def normalize_dce_iron_ore_sina_daily(frame, retrieved_at):
    if frame is None or frame.empty:
        raise ValueError("sina I0 frame has no rows")
    rows = []
    seen = set()
    for record in frame.to_dict("records"):
        date_text = _normalize_sina_date(record.get("date"))
        if date_text is None:
            raise ValueError("sina I0 row has an invalid date")
        close = _as_finite_float(record.get("close"))
        if close is None:
            raise ValueError("sina I0 row has an invalid close")
        if date_text in seen:
            raise ValueError(f"sina I0 row duplicates date {date_text}")
        seen.add(date_text)
        rows.append(
            {
                "date": date_text,
                "value": close,
                "source": "sina_finance",
                "source_url": SINA_I0_DAILY_URL,
                "source_identifier": _SOURCE_IDENTIFIER,
                "source_class": "vendor_free_market_data",
                "retrieved_at": retrieved_at,
            }
        )
    rows.sort(key=lambda row: row["date"])
    if not rows:
        raise ValueError("sina I0 returned no valid observations")
    return rows


def fetch_dce_iron_ore_sina(adapter=None):
    try:
        if adapter is None:
            import akshare as ak

            adapter = ak.futures_zh_daily_sina
        frame = adapter(symbol="I0")
    except Exception as exc:
        raise ValueError(f"sina I0 fetch failed: {exc}") from exc
    return {
        "series": _DCE_IRON_ORE_SINA_SERIES,
        "observations": normalize_dce_iron_ore_sina_daily(frame, _retrieved_at()),
    }

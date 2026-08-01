import csv
import io
import re
from datetime import datetime, timezone

from app.http_client import HttpClient


INVESTING_BASE = "https://www.investing.com"

# instrument_id values must be confirmed from each market's actual
# Investing.com page request before claiming data matches the method
# market.  The cid parameters in the method URLs provide probable
# IDs (used below) but these should be verified against the XHR
# request the page makes to /api/financialdata/historical/<id>.

MARKET_SERIES = {
    "copper_comex": {
        "price_page_url": f"{INVESTING_BASE}/commodities/copper-historical-data",
        "display_name": "Copper (COMEX)",
        "exchange_label": "COMEX",
        "instrument": "Copper High Grade futures (HG)",
        "units": "USD/lb",
        "instrument_id": 8831,
    },
    "copper_lme": {
        "price_page_url": f"{INVESTING_BASE}/commodities/copper-historical-data?cid=959211",
        "display_name": "Copper (LME)",
        "exchange_label": "LME",
        "instrument": "LME Copper Grade A",
        "units": "USD/tonne",
        "instrument_id": 959211,
    },
    "copper_shanghai": {
        "display_name": "Copper (Shanghai)",
        "exchange_label": "SHFE",
        "instrument": "SHFE Copper main contract (OI-selected)",
        "units": "CNY/tonne",
        "source": "shfe",
        "source_class": "official_exchange",
        "access_adapter": "akshare",
        "source_url": "https://www.shfe.com.cn/reports/tradedata/dailyandweeklydata/?query_options=1&query_params=kx&query_product_code=cu_f",
        "source_identifier": "SHFE:CU",
    },
    "lumber": {
        "price_page_url": f"{INVESTING_BASE}/commodities/lumber-historical-data",
        "display_name": "Lumber",
        "exchange_label": "CME",
        "instrument": "Lumber futures (LBS)",
        "units": "USD/1,000 board feet",
        "instrument_id": 497,
    },
    "iron_ore_62_cfr_china": {
        "price_page_url": f"{INVESTING_BASE}/commodities/iron-ore-62-cfr-futures",
        "display_name": "Iron Ore 62% CFR China",
        "exchange_label": "S&P Global",
        "instrument": "Iron Ore 62% Fe CFR China index",
        "units": "USD/tonne",
        "instrument_id": 965515,
    },
    "iron_ore_dce": {
        "price_page_url": f"{INVESTING_BASE}/commodities/iron-ore-62-cfr-futures?cid=961741",
        "display_name": "Iron Ore (DCE)",
        "exchange_label": "DCE",
        "instrument": "DCE Iron Ore futures (I)",
        "units": "CNY/tonne",
        "instrument_id": 961741,
    },
}

ARCHIVED_MARKET_SERIES = {
    "copper_comex": MARKET_SERIES["copper_comex"],
    "lumber": MARKET_SERIES["lumber"],
}

ACTIVE_MARKET_SERIES = {
    series_id: meta
    for series_id, meta in MARKET_SERIES.items()
    if series_id not in ARCHIVED_MARKET_SERIES
}


def free_web_series():
    return {
        series_id: meta
        for series_id, meta in MARKET_SERIES.items()
        if series_id not in ARCHIVED_MARKET_SERIES
        and meta.get("source_class", "free_web") == "free_web"
    }


def validate_free_web_markets(series_ids):
    allowed = set(free_web_series())
    for series_id in series_ids:
        if series_id not in allowed:
            raise ValueError(
                f"method commodity market {series_id} is not an Investing method market"
            )


def _normalize_method_price(row, series_id, source_url, retrieved_at):
    return {
        "date": row["date"],
        "value": float(row["price"]),
        "source": "investing.com",
        "source_url": source_url,
        "source_identifier": series_id,
        "source_class": "free_web",
        "retrieved_at": retrieved_at,
    }


def parse_commodity_csv(csv_text, series_id, source_url=None, retrieved_at=None):
    reader = csv.DictReader(io.StringIO(csv_text.lstrip("\ufeff")))
    if "Date" not in reader.fieldnames or "Price" not in reader.fieldnames:
        raise ValueError(
            f"method commodity csv for {series_id} is missing required Date/Price columns"
        )
    rows = []
    for record in reader:
        date_text = (record.get("Date") or "").strip()
        price_text = (record.get("Price") or "").strip().replace(",", "")
        if not date_text or not price_text:
            continue
        parsed_date = _parse_date_cell(date_text)
        if parsed_date is None:
            continue
        try:
            price = float(price_text)
        except (ValueError, TypeError):
            continue
        rows.append({"date": parsed_date, "price": price})
    rows.sort(key=lambda r: r["date"])
    seen = set()
    deduped = []
    for row in rows:
        if row["date"] not in seen:
            seen.add(row["date"])
            deduped.append(row)
    meta = MARKET_SERIES.get(series_id, {})
    effective_source_url = source_url or meta.get("price_page_url", "")
    effective_retrieved_at = retrieved_at or datetime.now(timezone.utc).isoformat()
    return [
        _normalize_method_price(
            r, series_id, effective_source_url, effective_retrieved_at
        )
        for r in deduped
    ]


def parse_investing_history_payload(payload, series_id, retrieved_at=None):
    data = payload.get("data", [])
    meta = MARKET_SERIES.get(series_id, {})
    source_url = meta.get("price_page_url", "")
    effective_retrieved_at = retrieved_at or datetime.now(timezone.utc).isoformat()
    rows = []
    for entry in data:
        date_str = (entry.get("rowDate") or "").strip()
        if not date_str:
            continue
        parsed_date = _parse_date_cell(date_str)
        if parsed_date is None:
            continue
        raw_value = entry.get("last_close")
        if raw_value is None:
            raw_value = entry.get("last")
        if raw_value is None:
            continue
        try:
            price = float(raw_value)
        except (ValueError, TypeError):
            continue
        rows.append({"date": parsed_date, "price": price})
    rows.sort(key=lambda r: r["date"])
    seen = set()
    deduped = []
    for row in rows:
        if row["date"] not in seen:
            seen.add(row["date"])
            deduped.append(row)
    return [
        _normalize_method_price(r, series_id, source_url, effective_retrieved_at)
        for r in deduped
    ]


def build_commodity_series_payload(series_id, observations):
    meta = MARKET_SERIES[series_id]
    if meta.get("source_class", "free_web") != "free_web":
        raise ValueError(
            f"method commodity series {series_id} is not an Investing method market"
        )
    return {
        "series": {
            "series_id": series_id,
            "title": meta["display_name"],
            "units": meta["units"],
            "source": "investing.com",
            "source_class": "free_web",
            "source_url": meta["price_page_url"],
            "exchange_label": meta["exchange_label"],
            "instrument": meta["instrument"],
        },
        "observations": observations,
    }


_DATE_PATTERNS = [
    r"([A-Z][a-z]{2}\s+\d{1,2},\s+\d{4})",
    r"(\d{4}-\d{2}-\d{2})",
]


def _parse_cell_text(cell_html):
    return re.sub(r"<[^>]+>", "", cell_html).strip()


def _parse_date_cell(cell_text):
    cleaned = re.sub(r"[^\w\s,/-]", "", cell_text).strip()
    for fmt in ("%b %d, %Y", "%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(cleaned, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def _extract_table_rows(html):
    rows = []
    for table_match in re.finditer(
        r"<table[^>]*>(.*?)</table>", html, re.DOTALL | re.IGNORECASE
    ):
        table_html = table_match.group(1)
        for row_match in re.finditer(r"<tr[^>]*>(.*?)</tr>", table_html, re.DOTALL):
            cells = re.findall(r"<td[^>]*>(.*?)</td>", row_match.group(1), re.DOTALL)
            if len(cells) < 7:
                continue
            date_text = _parse_cell_text(cells[0])
            price_text = _parse_cell_text(cells[1]).replace(",", "")
            if not date_text or not price_text:
                continue
            parsed_date = _parse_date_cell(date_text)
            if parsed_date is None:
                continue
            try:
                price = float(price_text)
            except (ValueError, TypeError):
                continue
            rows.append({"date": parsed_date, "price": price})
    return rows


def _extract_any_tablerows(html):
    rows = []
    for row_match in re.finditer(r"<tr[^>]*>(.*?)</tr>", html, re.DOTALL):
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row_match.group(1), re.DOTALL)
        if len(cells) < 7:
            continue
        date_text = _parse_cell_text(cells[0])
        price_text = _parse_cell_text(cells[1]).replace(",", "")
        if not date_text or not price_text:
            continue
        parsed_date = _parse_date_cell(date_text)
        if parsed_date is None:
            continue
        try:
            price = float(price_text)
        except (ValueError, TypeError):
            continue
        rows.append({"date": parsed_date, "price": price})
    return rows


def _parse_investing_html(html, series_id, source_url, retrieved_at):
    table_rows = _extract_table_rows(html)
    if not table_rows:
        table_rows = _extract_any_tablerows(html)
    table_rows.sort(key=lambda r: r["date"])
    seen = set()
    deduped = []
    for row in table_rows:
        if row["date"] not in seen:
            seen.add(row["date"])
            deduped.append(row)
    return deduped


def _summarize_response(response):
    content = response.content
    if isinstance(content, bytes):
        content = content.decode("utf-8", errors="replace")
    preview = content[:2000]
    return {
        "status_code": response.status_code,
        "content_length": len(content),
        "content_type": response.headers.get("content-type", ""),
        "preview": preview,
    }


def fetch_commodity_observations(
    http_client=None,
    start_date=None,
    end_date=None,
    markets=None,
):
    client = http_client or HttpClient()
    result = {}
    if markets:
        validate_free_web_markets(markets)
        series_iter = [(sid, MARKET_SERIES[sid]) for sid in markets]
    else:
        series_iter = free_web_series().items()
    for series_id, meta in series_iter:
        source_url = meta["price_page_url"]
        retrieved_at = datetime.now(timezone.utc).isoformat()
        try:
            response = client.request("GET", source_url, timeout=30)
        except Exception as exc:
            result[series_id] = {
                "series": {
                    "series_id": series_id,
                    "title": meta["display_name"],
                    "units": meta["units"],
                    "source": "investing.com",
                    "source_class": "free_web",
                    "source_url": source_url,
                    "exchange_label": meta["exchange_label"],
                    "instrument": meta["instrument"],
                },
                "observations": [],
                "_fetch_diagnostic": {
                    "error": f"http request failed: {exc}",
                },
            }
            continue
        if response.status_code >= 400:
            result[series_id] = {
                "series": {
                    "series_id": series_id,
                    "title": meta["display_name"],
                    "units": meta["units"],
                    "source": "investing.com",
                    "source_class": "free_web",
                    "source_url": source_url,
                    "exchange_label": meta["exchange_label"],
                    "instrument": meta["instrument"],
                },
                "observations": [],
                "_fetch_diagnostic": {
                    "error": f"http {response.status_code}",
                },
            }
            continue
        html = response.content
        if isinstance(html, bytes):
            html = html.decode("utf-8", errors="replace")
        parsed = _parse_investing_html(html, series_id, source_url, retrieved_at)
        if not parsed:
            diag = _summarize_response(response)
            result[series_id] = {
                "series": {
                    "series_id": series_id,
                    "title": meta["display_name"],
                    "units": meta["units"],
                    "source": "investing.com",
                    "source_class": "free_web",
                    "source_url": source_url,
                    "exchange_label": meta["exchange_label"],
                    "instrument": meta["instrument"],
                },
                "observations": [],
                "_fetch_diagnostic": {
                    "error": "no table rows parsed from html response",
                    "content_length": diag["content_length"],
                    "content_type": diag["content_type"],
                    "preview": diag["preview"],
                },
            }
            continue
        if start_date:
            parsed = [r for r in parsed if r["date"] >= start_date]
        if end_date:
            parsed = [r for r in parsed if r["date"] <= end_date]
        observations = [
            _normalize_method_price(r, series_id, source_url, retrieved_at)
            for r in parsed
        ]
        result[series_id] = {
            "series": {
                "series_id": series_id,
                "title": meta["display_name"],
                "units": meta["units"],
                "source": "investing.com",
                "source_class": "free_web",
                "source_url": source_url,
                "exchange_label": meta["exchange_label"],
                "instrument": meta["instrument"],
            },
            "observations": observations,
        }
    return result

import sqlite3
from datetime import date, timedelta

from app.data_sources import sec_edgar
from app.db import edgar_filings as edgar_db
from app.runtime_logging import get_runtime_logger
from app.tools import catalyst_stats
from app.tools import market_data as market_data_tool


LOGGER = get_runtime_logger(__name__)

_WINDOW_DAYS = 4 * 365
_CALENDAR_WINDOW_DAYS = 400


def _resolve_cik(con, symbol, http_client):
    row = edgar_db.load_cik(con, symbol)
    if row is not None:
        return row["cik"]
    mapping = sec_edgar.fetch_cik_map(http_client=http_client)
    entry = mapping.get(symbol)
    if entry is None:
        raise ValueError(f"no edgar cik mapping for {symbol}")
    edgar_db.save_cik(con, symbol, entry["cik"], entry["title"])
    return entry["cik"]


def _refresh_filings(con, symbol, cik, since_iso, http_client):
    raw = sec_edgar.fetch_submissions(cik, http_client=http_client)
    parsed = sec_edgar.parse_submissions(raw, symbol)
    filings = parsed["filings"]
    oldest = min((filing["filing_date"] for filing in filings), default=None)
    if oldest is not None and oldest > since_iso and parsed["older_files"]:
        raw_older = sec_edgar.fetch_older_submissions(
            cik, parsed["older_files"][0], http_client=http_client
        )
        filings = filings + sec_edgar.parse_older_submissions(raw_older, symbol)
    for filing in filings:
        edgar_db.save_filing(con, symbol, filing)


def _backfill_items(con, symbol, cik, filings, http_client):
    for filing in filings:
        if filing.get("items") is not None:
            continue
        try:
            document = sec_edgar.fetch_filing_document(
                cik, filing["accession"], filing["primary_document"], http_client=http_client
            )
        except ValueError as exc:
            LOGGER.warning(
                "edgar filing items backfill skipped symbol=%s accession=%s reason=%s",
                symbol, filing["accession"], exc,
            )
            continue
        items = sec_edgar.parse_8k_items(document)
        edgar_db.save_filing(con, symbol, {
            **filing,
            "items": items,
            "is_earnings": 1 if sec_edgar.is_earnings_filing(items) else 0,
        })


def _load_price_window(symbol, since_iso, db_path, http_client):
    payload = market_data_tool.fetch_market_data(
        symbol, interval="1d", db_path=db_path, http_client=http_client
    )
    dates = payload["prices"]["dates"]
    closes = payload["prices"]["adjusted_close"]
    pairs = [
        (day, close) for day, close in zip(dates, closes)
        if day >= since_iso and close is not None
    ]
    return [close for _, close in pairs], [day for day, _ in pairs]


def get_catalyst_activity(symbol, db_path=None, http_client=None, today=None):
    normalized = edgar_db.normalize_symbol(symbol)
    effective_db_path = db_path or edgar_db.DEFAULT_DB_PATH
    today_date = date.fromisoformat(today) if isinstance(today, str) else (today or date.today())
    since_iso = (today_date - timedelta(days=_WINDOW_DAYS)).isoformat()
    con = edgar_db.connect(effective_db_path)
    try:
        cik = _resolve_cik(con, normalized, http_client)
        try:
            _refresh_filings(con, normalized, cik, since_iso, http_client)
        except ValueError as exc:
            LOGGER.warning("catalyst filings refresh skipped symbol=%s reason=%s", normalized, exc)
        filings = edgar_db.load_filings(con, normalized, since=since_iso)
        _backfill_items(con, normalized, cik, filings, http_client)
        filings = edgar_db.load_filings(con, normalized, since=since_iso)
        frequency = catalyst_stats.filing_frequency(filings, today_date)
        moves = {"status": "insufficient_data"}
        aligned_moves = []
        calendar = None
        try:
            closes, dates = _load_price_window(normalized, since_iso, effective_db_path, http_client)
            moves = catalyst_stats.large_move_days(closes, dates)
        except ValueError as exc:
            LOGGER.warning("catalyst price window unavailable symbol=%s reason=%s", normalized, exc)
        if moves.get("status") == "ok":
            calendar_start = (today_date - timedelta(days=_CALENDAR_WINDOW_DAYS)).isoformat()
            filing_dates = [filing["filing_date"] for filing in filings]
            aligned_moves = catalyst_stats.align_moves_with_filings(moves["moves"], filing_dates)
            calendar = {
                "days": [
                    day for day in catalyst_stats.daily_return_calendar(closes, dates)
                    if day["date"] >= calendar_start
                ],
                "filing_dates": [day for day in filing_dates if day >= calendar_start],
                "mean_return": moves.get("mean_return"),
                "stdev": moves.get("stdev"),
            }
        status = "ok" if frequency.get("status") == "ok" or moves.get("status") == "ok" else "insufficient_data"
        return {
            "status": status,
            "source": "sec_edgar",
            "cik": cik,
            "window_start": since_iso,
            "filing_frequency": frequency,
            "large_moves": {
                "status": moves.get("status"),
                "sample_days": moves.get("sample_days"),
                "mean_return": moves.get("mean_return"),
                "stdev": moves.get("stdev"),
                "moves": aligned_moves,
            },
            "calendar": calendar,
            "caveat": "8-K filings only; IR press releases are a superset of these events",
        }
    except (ValueError, sqlite3.Error) as exc:
        LOGGER.warning("catalyst activity unavailable symbol=%s reason=%s", normalized, exc)
        return {"status": "insufficient_data"}
    finally:
        con.close()

import sqlite3
import time
from datetime import date, timedelta

from app.data_sources import sec_edgar
from app.db import edgar_filings as edgar_db
from app.runtime_logging import get_runtime_logger
from app.services import catalyst_activity


LOGGER = get_runtime_logger(__name__)

_WINDOW_DAYS = 4 * 365
_BACKFILL_DELAY_SECONDS = 0.15


def _refresh_form4_filings(con, symbol, cik, since_iso, http_client):
    raw = sec_edgar.fetch_submissions(cik, http_client=http_client)
    parsed = sec_edgar.parse_submissions(raw, symbol, form="4")
    filings = parsed["filings"]
    oldest = min((filing["filing_date"] for filing in filings), default=None)
    if oldest is not None and oldest > since_iso and parsed["older_files"]:
        raw_older = sec_edgar.fetch_older_submissions(
            cik, parsed["older_files"][0], http_client=http_client
        )
        filings = filings + sec_edgar.parse_older_submissions(
            raw_older, symbol, form="4"
        )
    known = edgar_db.load_form4_accessions(con, symbol)
    for filing in filings:
        if filing["accession"] in known:
            continue
        time.sleep(_BACKFILL_DELAY_SECONDS)
        try:
            document = sec_edgar.fetch_filing_document(
                cik, filing["accession"], sec_edgar.form4_raw_document(filing["primary_document"]),
                http_client=http_client,
            )
        except ValueError as exc:
            LOGGER.warning(
                "form 4 document fetch skipped symbol=%s accession=%s reason=%s",
                symbol, filing["accession"], exc,
            )
            continue
        try:
            transactions = sec_edgar.parse_form4_document(document, symbol)
        except ValueError as exc:
            LOGGER.warning(
                "form 4 document parse failed symbol=%s accession=%s reason=%s",
                symbol, filing["accession"], exc,
            )
            transactions = []
        edgar_db.save_form4_filing(con, symbol, filing, transactions)


def _enrich_transaction(transaction):
    shares = transaction.get("shares")
    shares_after = transaction.get("shares_after")
    result = dict(transaction)
    if shares is not None and transaction.get("price") is not None:
        result["value"] = round(shares * transaction["price"], 2)
    else:
        result["value"] = None
    result["pct_of_holding"] = None
    if shares is not None and shares_after is not None:
        direction = transaction.get("acquired_disposed")
        if direction == "D" and shares_after + shares > 0:
            result["pct_of_holding"] = round(shares / (shares_after + shares), 4)
        elif direction == "A" and shares_after > 0:
            result["pct_of_holding"] = round(shares / shares_after, 4)
    return result


def get_insider_activity(symbol, db_path=None, http_client=None, today=None):
    normalized = edgar_db.normalize_symbol(symbol)
    effective_db_path = db_path or edgar_db.DEFAULT_DB_PATH
    today_date = date.fromisoformat(today) if isinstance(today, str) else (today or date.today())
    since_iso = (today_date - timedelta(days=_WINDOW_DAYS)).isoformat()
    con = edgar_db.connect(effective_db_path)
    try:
        cik = catalyst_activity._resolve_cik(con, normalized, http_client)
        try:
            _refresh_form4_filings(con, normalized, cik, since_iso, http_client)
        except ValueError as exc:
            LOGGER.warning(
                "insider filings refresh skipped symbol=%s reason=%s", normalized, exc
            )
        transactions = edgar_db.load_form4_transactions(con, normalized, since=since_iso)
        return {
            "status": "ok",
            "source": "sec_edgar",
            "cik": cik,
            "window_start": since_iso,
            "transactions": [_enrich_transaction(row) for row in transactions],
        }
    except (ValueError, sqlite3.Error) as exc:
        LOGGER.warning("insider activity unavailable symbol=%s reason=%s", normalized, exc)
        return {"status": "insufficient_data"}
    finally:
        con.close()

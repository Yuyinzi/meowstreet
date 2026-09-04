import sqlite3
from datetime import UTC, datetime, timedelta

from app.data_sources import sec_companyfacts
from app.data_sources import stockanalysis_screener
from app.data_sources import yahoo_asset_profile
from app.db import edgar_filings as edgar_db
from app.db import market_data as market_data_db
from app.db import ticker_context as ticker_context_db
from app.runtime_logging import get_runtime_logger
from app.services import catalyst_activity
from app.tools import quant_metrics


LOGGER = get_runtime_logger(__name__)

_FRESHNESS_SECONDS = 72000
_STATEMENT_FACTS_FRESHNESS_SECONDS = 604800


def _load_fundamentals(con, symbol, http_client, force_refresh=False):
    row = ticker_context_db.load_ticker_fundamentals(con, symbol)
    if (
        not force_refresh
        and row is not None
        and ticker_context_db.fundamentals_fresh(
            row, max_age_seconds=_FRESHNESS_SECONDS
        )
    ):
        return dict(row), "hit"
    fetched = yahoo_asset_profile.fetch_quote_fundamentals(
        symbol, http_client=http_client
    )
    fetched["symbol"] = symbol
    fetched["fetched_at"] = datetime.now(UTC).isoformat()
    ticker_context_db.save_ticker_fundamentals(con, fetched)
    return fetched, "refreshed"


def _load_peer_fundamentals(con, symbol, http_client):
    try:
        peer_row, _ = _load_fundamentals(con, symbol, http_client)
        return dict(peer_row)
    except ValueError as exc:
        return {"symbol": symbol, "error": str(exc)}


def _load_forecast_data(con, symbol, http_client):
    consensus_latest = ticker_context_db.load_latest_estimate_consensus(con, symbol)
    ratings_latest = ticker_context_db.load_latest_analyst_ratings(con, symbol)
    consensus_fresh = consensus_latest is not None and ticker_context_db.estimate_consensus_fresh(
        consensus_latest, max_age_seconds=_FRESHNESS_SECONDS
    )
    ratings_fresh = ratings_latest is not None and ticker_context_db.analyst_ratings_fresh(
        ratings_latest, max_age_seconds=_FRESHNESS_SECONDS
    )
    if consensus_fresh and ratings_fresh:
        return dict(consensus_latest), ratings_latest
    try:
        document = stockanalysis_screener.fetch_forecast_document(symbol, http_client=http_client)
    except ValueError:
        return (dict(consensus_latest) if consensus_latest is not None else None), ratings_latest
    consensus_row = dict(consensus_latest) if consensus_latest is not None else None
    ratings_row = ratings_latest
    captured_at = datetime.now(UTC).isoformat()
    if not consensus_fresh:
        try:
            parsed_consensus = stockanalysis_screener.parse_forecast_data(document, symbol)
        except ValueError:
            pass
        else:
            parsed_consensus["captured_at"] = captured_at
            ticker_context_db.save_estimate_consensus_snapshot(con, symbol, parsed_consensus)
            consensus_row = parsed_consensus
    if not ratings_fresh:
        try:
            parsed_ratings = stockanalysis_screener.parse_analyst_ratings(document, symbol)
        except ValueError:
            if ratings_latest is None:
                ticker_context_db.save_analyst_ratings_snapshot(
                    con, symbol, {"provider": "stockanalysis", "captured_at": captured_at}
                )
        else:
            parsed_ratings["captured_at"] = captured_at
            ticker_context_db.save_analyst_ratings_snapshot(con, symbol, parsed_ratings)
            ratings_row = ticker_context_db.load_latest_analyst_ratings(con, symbol)
    return consensus_row, ratings_row


def _load_statement_facts(symbol, db_path, http_client):
    con = edgar_db.connect(db_path)
    try:
        row = edgar_db.load_statement_facts(con, symbol)
        if row is not None and edgar_db.cik_map_fresh(
            row, max_age_seconds=_STATEMENT_FACTS_FRESHNESS_SECONDS
        ):
            return row["facts"]
        try:
            cik = catalyst_activity._resolve_cik(con, symbol, http_client)
            raw = sec_companyfacts.fetch_company_facts(cik, http_client=http_client)
            parsed = sec_companyfacts.parse_company_facts(raw, symbol)
        except ValueError as exc:
            LOGGER.warning("statement facts unavailable symbol=%s reason=%s", symbol, exc)
            edgar_db.save_statement_facts(con, symbol, None, None)
            return None
        edgar_db.save_statement_facts(con, symbol, cik, parsed["facts"])
        return parsed["facts"]
    except sqlite3.Error as exc:
        LOGGER.warning("statement facts storage failed symbol=%s reason=%s", symbol, exc)
        return None
    finally:
        con.close()


def get_ticker_quant_context(
    symbol, peer=None, db_path=None, http_client=None, force_refresh=False,
    include_catalyst=True,
):
    normalized = ticker_context_db.normalize_symbol(symbol)
    effective_db_path = db_path or ticker_context_db.DEFAULT_DB_PATH
    con = ticker_context_db.connect(effective_db_path)
    try:
        fundamentals, cache_state = _load_fundamentals(
            con, normalized, http_client, force_refresh=force_refresh
        )
        volumes = market_data_db.load_recent_daily_volumes(con, normalized, limit=30)
        consensus_row, ratings_row = _load_forecast_data(con, normalized, http_client)
        statement_facts = _load_statement_facts(normalized, effective_db_path, http_client)
        since = (datetime.now(UTC) - timedelta(days=30)).isoformat()
        history = ticker_context_db.load_estimate_consensus_history(con, normalized, since)
        latest_close = market_data_db.load_latest_daily_close(con, normalized)
        payload = {
            "symbol": normalized,
            "fetched_at": fundamentals.get("fetched_at"),
            "cache": cache_state,
            "provider": fundamentals.get("provider", "yahoo"),
            "valuation": {
                "forward_pe": fundamentals.get("forward_pe"),
                "forward_eps": fundamentals.get("forward_eps"),
                "trailing_eps": fundamentals.get("trailing_eps"),
                "market_cap": fundamentals.get("market_cap"),
            },
            "peer": None,
            "short_checks": quant_metrics.short_check_payload(fundamentals, volumes),
            "backward_ratios": quant_metrics.backward_ratios_payload(fundamentals, statement_facts),
            "estimate_consensus": quant_metrics.estimate_consensus_payload(consensus_row),
            "estimate_revision_trend": quant_metrics.estimate_revision_trend(history, datetime.now(UTC)),
            "analyst_ratings": quant_metrics.analyst_ratings_payload(ratings_row, latest_close),
        }

        if include_catalyst:
            payload["catalyst_activity"] = catalyst_activity.get_catalyst_activity(
                normalized, db_path=effective_db_path, http_client=http_client
            )

        if peer is not None:
            peer_symbol = ticker_context_db.normalize_symbol(peer)
            peer_payload = _load_peer_fundamentals(con, peer_symbol, http_client)
            if "error" not in peer_payload:
                peer_payload["pe_differential"] = quant_metrics.pe_differential(
                    fundamentals.get("forward_pe"),
                    peer_payload.get("forward_pe"),
                )
            payload["peer"] = peer_payload

        return payload
    finally:
        con.close()

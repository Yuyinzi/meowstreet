from datetime import UTC, datetime

from app.data_sources import yahoo_asset_profile
from app.db import market_data as market_data_db
from app.db import ticker_context as ticker_context_db
from app.tools import quant_metrics


_FRESHNESS_SECONDS = 72000


def _load_fundamentals(con, symbol, http_client):
    row = ticker_context_db.load_ticker_fundamentals(con, symbol)
    if row is not None and ticker_context_db.fundamentals_fresh(row, max_age_seconds=_FRESHNESS_SECONDS):
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
        return {
            "symbol": symbol,
            "forward_pe": peer_row.get("forward_pe"),
        }
    except ValueError as exc:
        return {"symbol": symbol, "error": str(exc)}


def get_ticker_quant_context(symbol, peer=None, db_path=None, http_client=None):
    normalized = ticker_context_db.normalize_symbol(symbol)
    con = ticker_context_db.connect(db_path or ticker_context_db.DEFAULT_DB_PATH)
    try:
        fundamentals, cache_state = _load_fundamentals(con, normalized, http_client)
        volumes = market_data_db.load_recent_daily_volumes(con, normalized, limit=30)
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
            "backward_ratios": quant_metrics.backward_ratios_payload(fundamentals),
        }

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

from app.data_sources import stockanalysis_screener
from app.db import quant_screen as quant_screen_db
from app.tools import quant_screen as quant_screen_tool


_MAX_INDUSTRY_STOCKS = 250


def run_quant_screen(table_text):
    if not isinstance(table_text, str):
        raise ValueError("table_text must be a string")
    rows, row_errors = quant_screen_tool.parse_screener_table(table_text)
    return quant_screen_tool.build_screen_payload(rows, row_errors)


def _ensure_universe(con, http_client=None):
    rows = quant_screen_db.load_universe(con)
    max_fetched = con.execute(
        "select max(fetched_at) as max_fetched_at from screener_universe"
    ).fetchone()
    if rows and quant_screen_db.universe_fresh(dict(max_fetched)):
        return rows
    rows = stockanalysis_screener.fetch_universe(http_client=http_client)
    quant_screen_db.save_universe(con, rows)
    return rows


def list_industries(db_path=None, http_client=None):
    con = quant_screen_db.connect(db_path or quant_screen_db.DEFAULT_DB_PATH)
    try:
        _ensure_universe(con, http_client=http_client)
        return quant_screen_db.list_industries(con)
    finally:
        con.close()


def run_industry_screen(industry, db_path=None, http_client=None):
    industry_input = str(industry or "").strip()
    if not industry_input:
        raise ValueError("industry is required")
    con = quant_screen_db.connect(db_path or quant_screen_db.DEFAULT_DB_PATH)
    try:
        return _run_industry_screen(con, industry_input, http_client)
    finally:
        con.close()


def _run_industry_screen(con, industry_input, http_client):
    universe = _ensure_universe(con, http_client=http_client)
    matching = [
        row for row in universe
        if row.get("industry") and row["industry"].lower() == industry_input.lower()
    ]
    if not matching:
        raise ValueError(f"industry {industry_input} not found in screener universe")
    if len(matching) > _MAX_INDUSTRY_STOCKS:
        raise ValueError(
            f"industry {industry_input} has {len(matching)} stocks; too large for automatic fetch, paste a screener table instead"
        )
    canonical_industry = matching[0]["industry"]
    rows = []
    row_errors = []
    for stock in matching:
        symbol = stock["symbol"]
        cached = quant_screen_db.load_estimate(con, symbol)
        if quant_screen_db.estimate_fresh(cached):
            if cached.get("error"):
                row_errors.append({"symbol": symbol, "reason": cached["error"]})
                continue
            estimate = {
                "symbol": cached["symbol"],
                "eps_fy0": cached["eps_fy0"],
                "eps_fy1": cached["eps_fy1"],
                "eps_fy2": cached["eps_fy2"],
                "provider": cached["provider"],
            }
        else:
            try:
                estimate = stockanalysis_screener.fetch_forecast_eps(
                    symbol, http_client=http_client
                )
                quant_screen_db.save_estimate(con, estimate)
            except ValueError as exc:
                quant_screen_db.save_estimate_error(con, symbol, str(exc))
                row_errors.append({"symbol": symbol, "reason": str(exc)})
                continue
        rows.append({
            "symbol": symbol,
            "price": stock["price"],
            "market_cap": stock["market_cap"],
            "eps_fy0": estimate.get("eps_fy0"),
            "eps_fy1": estimate.get("eps_fy1"),
            "eps_fy2": estimate.get("eps_fy2"),
        })
    if not rows:
        raise ValueError(f"no estimates available for industry {canonical_industry}")
    payload = quant_screen_tool.build_screen_payload(rows, row_errors)
    payload["source"] = {
        "mode": "auto",
        "provider": "stockanalysis",
        "industry": canonical_industry,
        "stock_count": len(matching),
        "estimate_failures": len(row_errors),
    }
    return payload

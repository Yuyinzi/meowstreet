from fastapi import APIRouter, HTTPException, Query

from app.agents.catalyst_research import config
from app.agents.catalyst_research.persistence import repository


router = APIRouter(prefix="/api/ticker-quant", tags=["catalyst-research"])

_SUMMARY_FIELDS = (
    "schema_version",
    "research_version",
    "job_id",
    "status",
    "ticker",
    "company_name",
    "as_of",
    "requested_window",
    "statistics",
    "observation_count",
    "warnings",
    "next_actions",
    "completed_at",
    "latest_job_id",
    "latest_job_status",
    "latest_job_completed_at",
)
_EVENT_FIELDS = (
    "published_date",
    "event_date",
    "count_date",
    "title",
    "source_type",
    "earnings_state",
    "classification_method",
    "first_seen_at",
)


def _normalize_symbol(symbol):
    normalized = str(symbol or "").strip().upper()
    if not normalized:
        raise ValueError("ticker is required")
    return normalized


def _not_researched(ticker):
    return {
        "schema_version": config.RESULT_SCHEMA_VERSION,
        "research_version": config.RESEARCH_VERSION,
        "ticker": ticker,
        "status": "not_researched",
        "sources": [],
        "statistics": {},
        "observation_count": 0,
        "warnings": [],
        "next_actions": [f"run .venv/bin/python -m app.agents.catalyst_research {ticker} --years 4"],
    }


def _source_summary(connection, source):
    summary = {
        "source_type": source.get("source_type"),
        "url": source.get("url"),
        "acceptance_status": source.get("acceptance_status"),
        "extraction_status": source.get("extraction_status"),
        "execution_path": source.get("execution_path"),
        "coverage_start": source.get("coverage_start"),
        "coverage_end": source.get("coverage_end"),
        "observation_count": source.get("item_count", 0),
        "truncation_reason": source.get("truncation_reason"),
    }
    if source.get("discovery_provider") and source.get("execution_path") == "cold":
        summary["discovery_provider"] = source["discovery_provider"]
    adapter_id = source.get("active_adapter_id")
    if adapter_id:
        adapter = repository.load_adapter_brief(connection, adapter_id)
        summary["adapter"] = adapter or {"adapter_id": adapter_id, "version": source.get("adapter_version"), "status": None, "access_mode": None}
    return summary


def _load_summary(symbol):
    ticker = _normalize_symbol(symbol)
    connection = repository.connect()
    try:
        result = repository.load_latest_result(connection, ticker)
        if result is None:
            return _not_researched(ticker)
        summary = {key: result.get(key) for key in _SUMMARY_FIELDS}
        summary["sources"] = [_source_summary(connection, source) for source in result.get("sources", [])]
        return summary
    finally:
        connection.close()


def _event_payload(row):
    event = {key: row.get(key) for key in _EVENT_FIELDS}
    event["url"] = row.get("canonical_url")
    return event


def _load_events(symbol, job_id, limit, cursor):
    ticker = _normalize_symbol(symbol)
    connection = repository.connect()
    try:
        if job_id is None:
            latest = repository.load_latest_result(connection, ticker)
            if latest is None:
                return {**_not_researched(ticker), "job_id": None, "events": [], "next_cursor": None}
            job_id = latest["job_id"]
        page = repository.load_events_page(connection, ticker, job_id, limit, cursor)
        return {
            "ticker": page["ticker"],
            "job_id": page["job_id"],
            "events": [_event_payload(row) for row in page["events"]],
            "next_cursor": page["next_cursor"],
        }
    finally:
        connection.close()


@router.get("/{symbol}/catalyst-research")
def catalyst_research_summary(symbol: str):
    try:
        return _load_summary(symbol)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{symbol}/catalyst-research/events")
def catalyst_research_events(
    symbol: str,
    job_id: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=200),
    cursor: str | None = Query(default=None),
):
    try:
        return _load_events(symbol, job_id, limit, cursor)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

from asyncio import CancelledError
from collections.abc import Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from re import fullmatch

from app.agents.catalyst_research.domain import normalize_request
from app.services.job_notifications import start_run


_ORIGIN = ContextVar("catalyst_notification_origin", default="command_line")
_BATCH = ContextVar("catalyst_notification_batch", default=None)
_OUTCOMES = {
    "completed": ("succeeded", "Announcement collection completed"),
    "completed_partial": ("completed_partial", "Collection completed with partial coverage; review the Catalyst result"),
    "unsupported": ("unsupported", "No supported collection path is available; review the Catalyst result"),
    "failed": ("failed", "Announcement collection did not complete; review the Catalyst result"),
    "interrupted": ("interrupted", "Announcement collection was interrupted"),
}
_STAGES = {
    "company_resolved": "Company identified", "discovery": "Finding announcement sources",
    "source_missing": "Reviewing unavailable sources", "adapter_generation": "Preparing source collection",
    "adapter_validated": "Checking source collection", "hot_validation": "Checking existing source",
    "hot_complete": "Source collection reported", "adapter_stale": "Reviewing changed source",
    "load_registry": "Loading registered sources", "discover_registry": "Finding official sources",
    "historical_backfill": "Collecting historical announcements", "daily_update": "Checking for new announcements",
    "feeds": "Checking announcement feeds", "gap_search": "Searching for missing announcements",
    "rediscover": "Rechecking source availability", "classification": "Organizing collected announcements",
    "finalizing": "Saving research result", "ingest_candidate": "Fetching an announcement",
    "ingest_complete": "Announcement collection progress reported",
}


def _outcome(result):
    status = result.get("status") if isinstance(result, Mapping) else None
    return _OUTCOMES.get(status, ("failed", "Collection did not report a terminal result"))


def _details(result, mode):
    details = {"research_mode": mode}
    if not isinstance(result, Mapping):
        return details
    job_id = result.get("job_id")
    if isinstance(job_id, str) and fullmatch(r"[a-zA-Z0-9_-]{1,128}", job_id):
        details["research_job_id"] = job_id
    count = result.get("observation_count")
    if type(count) is int and count >= 0:
        details["observation_count"] = count
    return details


def _child_status(status):
    return "ok" if status == "succeeded" else status


def _safe_ticker(ticker):
    value = str(ticker).strip().upper()
    return value if fullmatch(r"[A-Z0-9^$][A-Z0-9.^$=_-]{0,31}", value) else None


def _batch_child_name(batch, ticker):
    safe = _safe_ticker(ticker)
    if safe is not None:
        return safe
    return batch["unknown_tickers"].setdefault(ticker, f"Unrecognized ticker {len(batch['unknown_tickers']) + 1}")


@contextmanager
def background_origin():
    token = _ORIGIN.set("background")
    try:
        yield
    finally:
        _ORIGIN.reset(token)


async def run_with_notifications(operation, request, *, db_path=None, http_client=None, dependencies=None):
    if not isinstance(request, Mapping):
        raise ValueError("research request is required")
    normalized = normalize_request(request.get("ticker"), request.get("years", 4), request.get("as_of"), request.get("mode") or "research")
    ticker = normalized["ticker"]
    batch = _BATCH.get()
    handle = batch["handle"] if batch is not None else start_run("catalyst_research", target=_safe_ticker(ticker), origin=_ORIGIN.get())
    child_name = _batch_child_name(batch, ticker) if batch is not None else "Announcement collection"
    original_progress = (dependencies or {}).get("progress")

    def progress(stage, **details):
        label = _STAGES.get(stage)
        if label is not None:
            handle.report_child(child_name, "running", label)
        if callable(original_progress):
            try:
                original_progress(stage, **details)
            except Exception:
                pass

    def finish(result):
        status, summary = _outcome(result)
        handle.report_child(child_name, _child_status(status), summary)
        if batch is not None:
            batch["results"][ticker] = status
        else:
            handle.complete(status, summary, details=_details(result, normalized["mode"]))

    try:
        result = await operation(request, db_path=db_path, http_client=http_client,
                                 dependencies={**(dependencies or {}), "progress": progress})
    except (CancelledError, KeyboardInterrupt):
        finish({"status": "interrupted"})
        raise
    except Exception:
        finish({"status": "failed"})
        raise
    finish(result)
    return result


def record_feed_result(ticker, result):
    batch = _BATCH.get()
    if batch is None:
        return
    status, summary = _outcome(result)
    batch["results"][ticker] = status
    batch["handle"].report_child(_batch_child_name(batch, ticker), _child_status(status), summary)


def _finish_batch(batch, code):
    statuses = list(batch["results"].values())
    failed = statuses.count("failed")
    complete = sum(status in {"succeeded", "completed_partial"} for status in statuses)
    if code == 130 or "interrupted" in statuses:
        status = "interrupted"
    elif failed or code:
        status = "partially_failed" if complete else "failed"
    elif statuses and all(value == "unsupported" for value in statuses):
        status = "unsupported"
    elif any(value in {"completed_partial", "unsupported"} for value in statuses):
        status = "completed_partial"
    else:
        status = "succeeded"
    summary = f"{len(statuses)} tickers checked · {complete} completed · {statuses.count('unsupported')} unsupported · {failed} failed" if statuses else "No registered tickers to update"
    batch["handle"].complete(status, summary, exit_code=code)


def record_feed_batch(operation):
    @wraps(operation)
    def wrapped(*args, **kwargs):
        batch = {"handle": start_run("catalyst_feed_refresh"), "results": {}, "unknown_tickers": {}}
        token = _BATCH.set(batch)
        try:
            code = operation(*args, **kwargs)
        except (CancelledError, KeyboardInterrupt):
            _finish_batch(batch, 130)
            raise
        except SystemExit as exc:
            _finish_batch(batch, exc.code if isinstance(exc.code, int) else 1)
            raise
        except Exception:
            batch["handle"].complete("failed", "Feed refresh did not complete; check the command output", exit_code=1)
            raise
        else:
            _finish_batch(batch, code)
            return code
        finally:
            _BATCH.reset(token)
    return wrapped

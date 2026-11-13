import asyncio

from app.agents.catalyst_research.persistence import repository
from app.agents.catalyst_research.notifications import background_origin
from app.agents.catalyst_research.workflow import run_research
from app.runtime_logging import get_runtime_logger


LOGGER = get_runtime_logger(__name__)

_IN_FLIGHT = set()


def _normalize_ticker(value):
    normalized = str(value or "").strip().upper()
    if not normalized:
        raise ValueError("ticker is required")
    return normalized


def _log_progress(stage, **details):
    suffix = "".join(f" {key}={value}" for key, value in details.items() if value is not None)
    LOGGER.info("catalyst research stage=%s%s", stage, suffix)


def research_trigger_state(connection, ticker):
    normalized = _normalize_ticker(ticker)
    if repository.load_latest_result(connection, normalized) is not None:
        return {"ticker": normalized, "run_status": "already_researched"}
    active = repository.load_active_job(connection, normalized)
    if active is not None:
        return {"ticker": normalized, "run_status": "already_running", "job_id": active["job_id"]}
    return {"ticker": normalized, "run_status": "ready"}


async def _run_and_release(ticker, years, runner, dependencies):
    try:
        request = {"ticker": ticker, "years": years, "mode": "research"}
        with background_origin():
            if dependencies is None:
                await runner(request)
            else:
                await runner(request, dependencies=dependencies)
    except Exception:
        LOGGER.error("catalyst auto research failed ticker=%s", ticker, exc_info=True)
    finally:
        _IN_FLIGHT.discard(ticker)


async def launch_research(ticker, *, years=4, runner=None):
    normalized = _normalize_ticker(ticker)
    if isinstance(years, bool) or not isinstance(years, int) or not 1 <= years <= 4:
        raise ValueError("years must be between 1 and 4")
    if normalized in _IN_FLIGHT:
        return {"ticker": normalized, "run_status": "already_running"}
    connection = repository.connect()
    try:
        state = research_trigger_state(connection, normalized)
    finally:
        connection.close()
    if state["run_status"] != "ready":
        return state
    effective_runner = runner or run_research
    dependencies = None if runner is not None else {"progress": _log_progress}
    _IN_FLIGHT.add(normalized)
    asyncio.create_task(_run_and_release(normalized, years, effective_runner, dependencies))
    LOGGER.info("catalyst auto research launched ticker=%s years=%s", normalized, years)
    return {"ticker": normalized, "run_status": "started"}

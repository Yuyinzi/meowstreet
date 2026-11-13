from sqlite3 import Error as SQLiteError

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, StrictInt

from app.runtime_logging import get_runtime_logger
from app.services import job_notifications as service


router = APIRouter(prefix="/api/notifications", tags=["notifications"])
LOGGER = get_runtime_logger(__name__)


class ReadEvents(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_ids: list[StrictInt] = Field(max_length=200)


class NotificationCursor(BaseModel):
    model_config = ConfigDict(extra="forbid")
    through: StrictInt = Field(ge=0)


def _call(operation, *args, **kwargs):
    try:
        return operation(*args, **kwargs)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (OSError, SQLiteError) as exc:
        LOGGER.warning("job notifications unavailable")
        raise HTTPException(status_code=503, detail="Notification history is unavailable; please retry") from exc


@router.get("")
def snapshot():
    return _call(service.get_snapshot)


@router.get("/events")
def events(after: int = Query(default=0, ge=0), limit: int = Query(default=100, ge=1, le=100)):
    return _call(service.get_events, after, limit)


@router.get("/runs")
def history(job_id: str | None = None, status: str | None = None,
            before: int | None = Query(default=None, ge=1), limit: int = Query(default=25, ge=1, le=100)):
    return _call(service.get_history, job_id=job_id, status=status, before=before, limit=limit)


@router.get("/runs/{run_id}")
def detail(run_id: str):
    result = _call(service.get_run, run_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Notification run was not found")
    return result


@router.post("/read")
def read_events(body: ReadEvents):
    return _call(service.mark_read, body.event_ids)


@router.post("/read-all")
def read_all(body: NotificationCursor):
    return _call(service.mark_all_read, body.through)


@router.post("/clear")
def clear_notifications(body: NotificationCursor):
    return _call(service.clear_notifications, body.through)

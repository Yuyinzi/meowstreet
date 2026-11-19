from json import JSONDecodeError

from fastapi import APIRouter, HTTPException, Response

from app.runtime_logging import get_runtime_logger
from app.services import macro_data_freshness as service


router = APIRouter(prefix="/api/macro-data-freshness", tags=["macro-data-freshness"])
LOGGER = get_runtime_logger(__name__)


@router.get("")
def overview(response: Response):
    response.headers["Cache-Control"] = "no-store"
    try:
        return service.get_overview()
    except (OSError, ValueError, JSONDecodeError) as exc:
        LOGGER.warning("macro data freshness catalog unavailable")
        raise HTTPException(status_code=503, detail="Data freshness is unavailable; please retry") from exc

from fastapi import APIRouter, HTTPException, Query

from app.services import pair_analysis as pair_analysis_service

router = APIRouter(prefix="/api/pair-analysis", tags=["pair-analysis"])


@router.get("/{long_symbol}/{short_symbol}")
def pair_analysis_lookup(
    long_symbol: str,
    short_symbol: str,
    sessions: int = Query(default=60),
):
    try:
        return pair_analysis_service.get_pair_analysis(
            long_symbol, short_symbol, sessions=sessions
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

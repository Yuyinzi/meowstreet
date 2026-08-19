from fastapi import APIRouter, HTTPException, Query

from app.services import ticker_industry_context as ticker_context_service

router = APIRouter(prefix="/api/ticker-context", tags=["ticker-context"])


@router.get("/industries")
def ticker_context_industries():
    try:
        return {"industries": ticker_context_service.list_gics_industries()}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{symbol}")
def ticker_context_lookup(
    symbol: str, industry: str | None = Query(default=None)
):
    try:
        return ticker_context_service.get_ticker_industry_context(
            symbol, industry_override=industry
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

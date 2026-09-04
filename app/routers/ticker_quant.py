from fastapi import APIRouter, HTTPException, Query

from app.services import catalyst_activity as catalyst_activity_service
from app.services import ticker_quant_context as ticker_quant_context_service

router = APIRouter(prefix="/api/ticker-quant", tags=["ticker-quant"])


@router.get("/{symbol}/catalyst")
def ticker_quant_catalyst(symbol: str):
    try:
        return catalyst_activity_service.get_catalyst_activity(symbol)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{symbol}")
def ticker_quant_lookup(
    symbol: str,
    peer: str | None = Query(default=None),
    refresh: bool = Query(default=False),
):
    try:
        return ticker_quant_context_service.get_ticker_quant_context(
            symbol, peer=peer, force_refresh=refresh, include_catalyst=False
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

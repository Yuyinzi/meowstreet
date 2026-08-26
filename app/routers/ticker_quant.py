from fastapi import APIRouter, HTTPException, Query

from app.services import ticker_quant_context as ticker_quant_context_service

router = APIRouter(prefix="/api/ticker-quant", tags=["ticker-quant"])


@router.get("/{symbol}")
def ticker_quant_lookup(
    symbol: str,
    peer: str | None = Query(default=None),
):
    try:
        return ticker_quant_context_service.get_ticker_quant_context(symbol, peer=peer)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

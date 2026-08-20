from fastapi import APIRouter, Body, HTTPException

from app.services import portfolio_analysis as portfolio_analysis_service

router = APIRouter(prefix="/api", tags=["portfolio-analysis"])


@router.get("/ticker-risk/{symbol}")
def ticker_risk_profile(symbol: str):
    try:
        return portfolio_analysis_service.get_ticker_risk_profile(symbol)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/portfolio-analysis")
def portfolio_analysis_evaluate(body: dict = Body(default={})):
    try:
        return portfolio_analysis_service.get_portfolio_analysis(body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

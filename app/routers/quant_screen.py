from fastapi import APIRouter, Body, HTTPException

from app.services import quant_screen as quant_screen_service

router = APIRouter(prefix="/api/quant-screen", tags=["quant-screen"])


@router.post("")
def quant_screen_evaluate(body: dict = Body(default={})):
    table_text = body.get("table_text")
    if not isinstance(table_text, str):
        raise HTTPException(status_code=400, detail="table_text must be a string")
    try:
        return quant_screen_service.run_quant_screen(table_text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/industries")
def quant_screen_industries():
    try:
        return {"industries": quant_screen_service.list_industries()}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/auto")
def quant_screen_auto(body: dict = Body(default={})):
    industry = body.get("industry")
    if not isinstance(industry, str):
        raise HTTPException(status_code=400, detail="industry must be a string")
    try:
        return quant_screen_service.run_industry_screen(industry)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

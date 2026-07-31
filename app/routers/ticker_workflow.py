from fastapi import APIRouter, Body, HTTPException

from app import api, workflow_engine

router = APIRouter(prefix="/api/ticker-workflow", tags=["ticker-workflow"])


@router.get("/method")
def ticker_workflow_method():
    return api.load_workflow_method()


@router.post("/evaluate")
def ticker_workflow_evaluate(body: dict = Body(default={})):
    try:
        return workflow_engine.evaluate_workflow_method(
            api.load_workflow_method(),
            body,
            tool_runner=api.tool_runner.apply_tools,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

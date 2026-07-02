import json
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import tool_runner, workflow_engine
from app.db import benchmark_market_data
from app.tools import market_phase

ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = ROOT / "static"
METHOD_PATH = ROOT / "data" / "local_system" / "synthesis" / "method.v1.json"

app = FastAPI(title="Meowstreet")

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def load_workflow_method():
    if not METHOD_PATH.exists():
        raise HTTPException(
            status_code=500, detail=f"missing method artifact: {METHOD_PATH}"
        )
    return json.loads(METHOD_PATH.read_text(encoding="utf-8"))


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "method-system.html")


@app.get("/method-system.html")
def local_system_html():
    return FileResponse(STATIC_DIR / "method-system.html")


@app.get("/method-system.css")
def local_system_css():
    return FileResponse(STATIC_DIR / "method-system.css", media_type="text/css")


@app.get("/method-system.js")
def local_system_js():
    return FileResponse(
        STATIC_DIR / "method-system.js", media_type="application/javascript"
    )


@app.get("/api/method-system/method")
def method():
    return load_workflow_method()


@app.post("/api/method-system/workflow/evaluate")
def workflow_evaluate(body: dict = Body(default={})):
    try:
        return workflow_engine.evaluate_workflow_method(
            load_workflow_method(),
            body,
            tool_runner=tool_runner.apply_tools,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/macro-dashboard.html")
def macro_dashboard_html():
    return FileResponse(STATIC_DIR / "macro-dashboard.html")


@app.get("/macro-dashboard.css")
def macro_dashboard_css():
    return FileResponse(STATIC_DIR / "macro-dashboard.css", media_type="text/css")


@app.get("/macro-dashboard.js")
def macro_dashboard_js():
    return FileResponse(
        STATIC_DIR / "macro-dashboard.js", media_type="application/javascript"
    )


@app.get("/api/macro-dashboard/market-phase")
def macro_dashboard_market_phase():
    con = benchmark_market_data.connect()
    try:
        return market_phase.build_dashboard_payload(
            lambda benchmark_id: benchmark_market_data.load_price_rows(con, benchmark_id)
        )
    finally:
        con.close()

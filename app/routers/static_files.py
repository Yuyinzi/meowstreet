from fastapi import APIRouter
from fastapi.responses import FileResponse

from app import api

router = APIRouter(tags=["static"])


@router.get("/")
def index():
    return FileResponse(api.STATIC_DIR / "ticker-workflow.html")


@router.get("/ticker-workflow.html")
def ticker_workflow_html():
    return FileResponse(api.STATIC_DIR / "ticker-workflow.html")


@router.get("/ticker-workflow.css")
def ticker_workflow_css():
    return FileResponse(api.STATIC_DIR / "ticker-workflow.css", media_type="text/css")


@router.get("/ticker-workflow.js")
def ticker_workflow_js():
    return FileResponse(
        api.STATIC_DIR / "ticker-workflow.js", media_type="application/javascript"
    )


@router.get("/macro-dashboard.html")
def macro_dashboard_html():
    return FileResponse(api.STATIC_DIR / "macro-dashboard.html")


@router.get("/macro-dashboard.css")
def macro_dashboard_css():
    return FileResponse(api.STATIC_DIR / "macro-dashboard.css", media_type="text/css")


@router.get("/macro-dashboard.js")
def macro_dashboard_js():
    return FileResponse(
        api.STATIC_DIR / "macro-dashboard.js", media_type="application/javascript"
    )


@router.get("/consumer-sentiment.js")
def consumer_sentiment_js():
    return FileResponse(
        api.STATIC_DIR / "consumer-sentiment.js", media_type="application/javascript"
    )


@router.get("/consumer-sentiment.css")
def consumer_sentiment_css():
    return FileResponse(
        api.STATIC_DIR / "consumer-sentiment.css", media_type="text/css"
    )


@router.get("/ism-services.js")
def ism_services_js():
    return FileResponse(
        api.STATIC_DIR / "ism-services.js", media_type="application/javascript"
    )


@router.get("/ism-services.css")
def ism_services_css():
    return FileResponse(api.STATIC_DIR / "ism-services.css", media_type="text/css")


@router.get("/housing-permits-ui.js")
def housing_permits_ui_js():
    return FileResponse(
        api.STATIC_DIR / "housing-permits-ui.js", media_type="application/javascript"
    )


@router.get("/nfib-sbo-ui.js")
def nfib_sbo_ui_js():
    return FileResponse(
        api.STATIC_DIR / "nfib-sbo-ui.js", media_type="application/javascript"
    )


@router.get("/cyclical-commodities-ui.js")
def cyclical_commodities_ui_js():
    return FileResponse(
        api.STATIC_DIR / "cyclical-commodities-ui.js",
        media_type="application/javascript",
    )


@router.get("/claims-confirmation-ui.js")
def claims_confirmation_ui_js():
    return FileResponse(
        api.STATIC_DIR / "claims-confirmation-ui.js",
        media_type="application/javascript",
    )


@router.get("/claims-confirmation.css")
def claims_confirmation_css():
    return FileResponse(
        api.STATIC_DIR / "claims-confirmation.css", media_type="text/css"
    )

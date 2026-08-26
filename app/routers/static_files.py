from fastapi import APIRouter
from fastapi.responses import FileResponse

from app import api

router = APIRouter(tags=["static"])


@router.get("/")
def index():
    return FileResponse(api.STATIC_DIR / "macro-dashboard.html")


@router.get("/macro-dashboard.html")
def macro_dashboard_html():
    return FileResponse(api.STATIC_DIR / "macro-dashboard.html")


@router.get("/ticker-context.html")
def ticker_context_html():
    return FileResponse(api.STATIC_DIR / "ticker-context.html")


@router.get("/ticker-context.css")
def ticker_context_css():
    return FileResponse(api.STATIC_DIR / "ticker-context.css", media_type="text/css")


@router.get("/ticker-context.js")
def ticker_context_js():
    return FileResponse(
        api.STATIC_DIR / "ticker-context.js", media_type="application/javascript"
    )


@router.get("/portfolio.html")
def portfolio_html():
    return FileResponse(api.STATIC_DIR / "portfolio.html")


@router.get("/portfolio.css")
def portfolio_css():
    return FileResponse(api.STATIC_DIR / "portfolio.css", media_type="text/css")


@router.get("/portfolio.js")
def portfolio_js():
    return FileResponse(
        api.STATIC_DIR / "portfolio.js", media_type="application/javascript"
    )


@router.get("/quant-screen.html")
def quant_screen_html():
    return FileResponse(api.STATIC_DIR / "quant-screen.html")


@router.get("/quant-screen.css")
def quant_screen_css():
    return FileResponse(api.STATIC_DIR / "quant-screen.css", media_type="text/css")


@router.get("/quant-screen.js")
def quant_screen_js():
    return FileResponse(
        api.STATIC_DIR / "quant-screen.js", media_type="application/javascript"
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


@router.get("/market-assistant.js")
def market_assistant_js():
    return FileResponse(
        api.STATIC_DIR / "market-assistant.js", media_type="application/javascript"
    )


@router.get("/market-assistant.css")
def market_assistant_css():
    return FileResponse(api.STATIC_DIR / "market-assistant.css", media_type="text/css")

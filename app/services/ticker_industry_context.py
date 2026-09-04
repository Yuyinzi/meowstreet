import sqlite3

from app.data_sources import yahoo_asset_profile
from app.db import ticker_context as ticker_context_db
from app.services import survey_synthesis_current
from app.runtime_logging import get_runtime_logger
from app.tools import regime_bias as regime_bias_tool
from app.tools import ticker_industry_context as context_tool

LOGGER = get_runtime_logger(__name__)


def _resolve_industry_override(con, industry_override):
    normalized = str(industry_override or "").strip()
    if not normalized:
        return None
    tag_row = ticker_context_db.load_industry_tag(con, normalized)
    if tag_row is None:
        raise ValueError(f"gics industry {normalized} is unknown")
    return tag_row


def _load_regime_context(con):
    try:
        synthesis = survey_synthesis_current.load_survey_synthesis_inputs(con)[
            "survey_synthesis_result"
        ]
    except (sqlite3.Error, ValueError, TypeError, KeyError):
        LOGGER.warning(
            "survey synthesis unavailable for ticker industry context", exc_info=True
        )
        return "unknown", None
    if not synthesis:
        return "unknown", None
    bias = regime_bias_tool.regime_bias_from_gdp_direction(
        synthesis.get("expected_gdp_direction")
    )
    source = {
        "method_version": regime_bias_tool.REGIME_BIAS_VERSION,
        "source_method": synthesis.get("version"),
        "source_period": synthesis.get("period"),
    }
    return bias, source


def get_ticker_industry_context(
    symbol, industry_override=None, db_path=None, http_client=None
):
    normalized = ticker_context_db.normalize_symbol(symbol)
    con = ticker_context_db.connect(db_path or ticker_context_db.DEFAULT_DB_PATH)
    try:
        override_tag_row = _resolve_industry_override(con, industry_override)
        profile = ticker_context_db.load_ticker_profile(con, normalized)
        if profile is None:
            if override_tag_row is not None:
                profile = {
                    "symbol": normalized,
                    "company_name": normalized,
                    "provider": "manual",
                    "provider_sector": None,
                    "provider_industry": None,
                }
            else:
                profile = yahoo_asset_profile.fetch_asset_profile(
                    normalized, http_client=http_client
                )
                ticker_context_db.save_ticker_profile(con, profile)
        alias = None
        tag_row = override_tag_row
        if tag_row is None and profile.get("provider_industry"):
            alias = ticker_context_db.load_industry_alias(
                con, profile["provider"], profile["provider_industry"]
            )
            if alias is not None:
                tag_row = ticker_context_db.load_industry_tag(
                    con, alias["gics_industry"]
                )
        resolution = context_tool.resolve_cycle_tag(
            profile,
            alias,
            tag_row,
            industry_override=override_tag_row["industry"] if override_tag_row else None,
        )
        regime_bias, regime_source = _load_regime_context(con)
        return context_tool.build_industry_context_payload(
            profile,
            tag_row,
            resolution,
            regime_bias=regime_bias,
            regime_source=regime_source,
        )
    finally:
        con.close()


def list_gics_industries(db_path=None):
    con = ticker_context_db.connect(db_path or ticker_context_db.DEFAULT_DB_PATH)
    try:
        return ticker_context_db.load_industry_tags(con)
    finally:
        con.close()

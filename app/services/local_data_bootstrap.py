from pathlib import Path

from app.data_sources import gics_reference
from app.db import (
    benchmark_market_data,
    economic_confirmation,
    gdp_market_relationships,
    growth_cycle,
    macro_indicators,
    market_assistant,
    market_data,
    ticker_context,
    us_rates_liquidity,
)


SCHEMA_ADAPTERS = (
    benchmark_market_data,
    economic_confirmation,
    gdp_market_relationships,
    growth_cycle,
    macro_indicators,
    market_assistant,
    market_data,
    ticker_context,
    us_rates_liquidity,
)


def bootstrap_local_data(db_path, reference_path=None):
    path = Path(db_path)
    reference = gics_reference.load_gics_reference(
        reference_path or gics_reference.GICS_REFERENCE_PATH
    )
    for adapter in SCHEMA_ADAPTERS:
        con = adapter.connect(path)
        con.close()
    con = ticker_context.connect(path)
    try:
        counts = ticker_context.replace_industry_reference_data(
            con, reference["industries"], reference["aliases"]
        )
    finally:
        con.close()
    return {
        "db_path": str(path),
        "reference_version": reference["version"],
        "schemas_initialized": len(SCHEMA_ADAPTERS),
        "industries": counts["industries"],
        "aliases": counts["aliases"],
        "market_observations": 0,
    }

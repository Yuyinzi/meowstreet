from app.data_sources.non_oil_attribution_evidence import (
    fetch_faostat_lumber_facts,
    fetch_iwcc_copper_facts,
)
from app.db import macro_indicators

__NON_OIL_ATTRIBUTION_COMMODITIES = ["copper", "lumber"]


def refresh_non_oil_attribution_evidence(
    con,
    iwcc_fetcher=fetch_iwcc_copper_facts,
    faostat_fetcher=fetch_faostat_lumber_facts,
):
    try:
        facts = iwcc_fetcher() + faostat_fetcher()
        macro_indicators.merge_non_oil_attribution_facts(con, facts, commit=False)
        con.commit()
        return {
            "facts": len(facts),
            "commodities": list(__NON_OIL_ATTRIBUTION_COMMODITIES),
        }
    except Exception:
        con.rollback()
        raise

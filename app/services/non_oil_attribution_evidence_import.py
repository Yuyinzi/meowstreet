from app.data_sources.non_oil_attribution_evidence import (
    FAOSTAT_SOURCE_URL,
    IWCC_SOURCE_URL,
    fetch_faostat_lumber_facts,
    fetch_iwcc_copper_facts,
)
from app.db import macro_indicators

__NON_OIL_ATTRIBUTION_COMMODITIES = ["copper", "lumber"]
__NON_OIL_ATTRIBUTION_SOURCES = (
    ("copper", IWCC_SOURCE_URL),
    ("lumber", FAOSTAT_SOURCE_URL),
)


def refresh_non_oil_attribution_evidence(
    con,
    iwcc_fetcher=fetch_iwcc_copper_facts,
    faostat_fetcher=fetch_faostat_lumber_facts,
):
    fetchers = {
        "copper": iwcc_fetcher,
        "lumber": faostat_fetcher,
    }
    fetched = {}
    failures = {}
    for commodity_id, source_url in __NON_OIL_ATTRIBUTION_SOURCES:
        try:
            fetched[commodity_id] = fetchers[commodity_id]()
        except Exception as exc:
            failures[commodity_id] = exc
    if failures:
        con.rollback()
        for commodity_id, exc in failures.items():
            macro_indicators.merge_non_oil_attribution_refresh_status(
                con,
                commodity_id,
                _source_url(commodity_id),
                "unavailable",
                str(exc),
                commit=False,
            )
        con.commit()
        raise next(iter(failures.values()))
    facts = [fact for facts in fetched.values() for fact in facts]
    try:
        macro_indicators.merge_non_oil_attribution_facts(con, facts, commit=False)
        for commodity_id, source_url in __NON_OIL_ATTRIBUTION_SOURCES:
            macro_indicators.merge_non_oil_attribution_refresh_status(
                con, commodity_id, source_url, "available", None, commit=False
            )
        con.commit()
        return {
            "facts": len(facts),
            "commodities": list(__NON_OIL_ATTRIBUTION_COMMODITIES),
        }
    except Exception:
        con.rollback()
        for commodity_id, source_url in __NON_OIL_ATTRIBUTION_SOURCES:
            macro_indicators.merge_non_oil_attribution_refresh_status(
                con,
                commodity_id,
                source_url,
                "unavailable",
                "refresh merge failed",
                commit=False,
            )
        con.commit()
        raise


def _source_url(commodity_id):
    return dict(__NON_OIL_ATTRIBUTION_SOURCES)[commodity_id]

_VALID_CYCLE_TAGS = {"cyclical", "defensive", "both"}
_VALID_REGIME_BIAS = {"expansion", "contraction", "neutral", "unknown"}

_SIDE_SUPPORT_BY_TAG_AND_REGIME = {
    ("cyclical", "expansion"): "supports_long",
    ("cyclical", "contraction"): "supports_short",
    ("defensive", "expansion"): "supports_short",
    ("defensive", "contraction"): "supports_long",
    ("both", "expansion"): "neutral",
    ("both", "contraction"): "neutral",
}

_REGIME_UNKNOWN_NOTE = (
    "Side support is unavailable: the survey-based GDP growth direction "
    "is mixed, missing, or stale."
)


def resolve_cycle_tag(profile, alias, tag_row, industry_override=None):
    if industry_override is not None:
        if tag_row is None:
            raise ValueError(f"gics industry {industry_override} has no cycle tag")
        return {"status": "resolved", "resolution": "manual_override"}
    provider_industry = (profile or {}).get("provider_industry")
    if not provider_industry:
        return {"status": "unclassified", "resolution": "provider"}
    if alias is None or tag_row is None:
        return {"status": "unmapped_industry", "resolution": "provider"}
    return {"status": "resolved", "resolution": "provider"}


def side_support(cycle_tag, regime_bias):
    tag = str(cycle_tag or "").strip().lower()
    regime = str(regime_bias or "unknown").strip().lower()
    if tag not in _VALID_CYCLE_TAGS:
        return "unknown"
    if regime not in _VALID_REGIME_BIAS:
        raise ValueError(f"regime bias {regime} is invalid")
    return _SIDE_SUPPORT_BY_TAG_AND_REGIME.get((tag, regime), "unknown")


def build_industry_context_payload(
    profile, tag_row, resolution, regime_bias="unknown", regime_source=None
):
    status = resolution["status"]
    cycle_tag = tag_row["cycle_tag"] if status == "resolved" and tag_row else None
    support = side_support(cycle_tag, regime_bias) if cycle_tag else "unknown"
    return {
        "symbol": profile["symbol"],
        "company_name": profile["company_name"],
        "status": status,
        "resolution": resolution["resolution"],
        "sector": tag_row["sector"] if tag_row and status == "resolved" else None,
        "industry_group": (
            tag_row["industry_group"] if tag_row and status == "resolved" else None
        ),
        "industry": tag_row["industry"] if tag_row and status == "resolved" else None,
        "official_industry": (
            tag_row["official_industry"] if tag_row and status == "resolved" else None
        ),
        "cycle_tag": cycle_tag,
        "provider": profile.get("provider"),
        "provider_sector": profile.get("provider_sector"),
        "provider_industry": profile.get("provider_industry"),
        "regime_bias": regime_bias,
        "regime_source": regime_source,
        "side_support": support,
        "regime_note": _REGIME_UNKNOWN_NOTE if regime_bias == "unknown" else None,
        "tag_provenance": (
            {
                "tag_source": tag_row["tag_source"],
                "source_vintage": tag_row["source_vintage"],
            }
            if tag_row and status == "resolved"
            else None
        ),
    }

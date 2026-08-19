import pytest

from app.tools import ticker_industry_context as context_tool


def profile():
    return {
        "symbol": "NVDA",
        "company_name": "NVIDIA Corporation",
        "provider": "yahoo",
        "provider_sector": "Technology",
        "provider_industry": "Semiconductors",
    }


def tag_row():
    return {
        "industry": "Semiconductors & Semi Conductor Equipment",
        "sector": "Information Technology",
        "industry_group": "Semiconductors & Semi Conductor Equipment",
        "official_industry": "Semiconductors & Semiconductor Equipment",
        "cycle_tag": "cyclical",
        "tag_source": "method_workbook",
        "source_vintage": "2021-gics",
    }


def alias():
    return {
        "source": "yahoo",
        "source_industry": "Semiconductors",
        "gics_industry": "Semiconductors & Semi Conductor Equipment",
    }


def test_resolve_cycle_tag_resolves_via_provider_alias():
    resolution = context_tool.resolve_cycle_tag(profile(), alias(), tag_row())

    assert resolution == {"status": "resolved", "resolution": "provider"}


def test_resolve_cycle_tag_unmapped_when_alias_missing():
    resolution = context_tool.resolve_cycle_tag(profile(), None, None)

    assert resolution == {"status": "unmapped_industry", "resolution": "provider"}


def test_resolve_cycle_tag_unclassified_when_provider_industry_missing():
    unclassified = dict(profile(), provider_industry=None)

    resolution = context_tool.resolve_cycle_tag(unclassified, None, None)

    assert resolution == {"status": "unclassified", "resolution": "provider"}


def test_resolve_cycle_tag_manual_override_wins():
    resolution = context_tool.resolve_cycle_tag(
        profile(), None, tag_row(), industry_override=tag_row()["industry"]
    )

    assert resolution == {"status": "resolved", "resolution": "manual_override"}


def test_resolve_cycle_tag_override_requires_tag_row():
    with pytest.raises(ValueError, match="gics industry Unknown has no cycle tag"):
        context_tool.resolve_cycle_tag(profile(), None, None, industry_override="Unknown")


@pytest.mark.parametrize(
    "cycle_tag,regime_bias,expected",
    [
        ("cyclical", "expansion", "supports_long"),
        ("cyclical", "contraction", "supports_short"),
        ("defensive", "expansion", "supports_short"),
        ("defensive", "contraction", "supports_long"),
        ("both", "expansion", "neutral"),
        ("both", "contraction", "neutral"),
        ("cyclical", "neutral", "unknown"),
        ("defensive", "unknown", "unknown"),
        ("both", "neutral", "unknown"),
        (None, "expansion", "unknown"),
    ],
)
def test_side_support_matrix(cycle_tag, regime_bias, expected):
    assert context_tool.side_support(cycle_tag, regime_bias) == expected


def test_side_support_rejects_invalid_regime_bias():
    with pytest.raises(ValueError, match="regime bias sideways is invalid"):
        context_tool.side_support("cyclical", "sideways")


def test_build_payload_resolved_includes_tag_and_provenance():
    payload = context_tool.build_industry_context_payload(
        profile(), tag_row(), {"status": "resolved", "resolution": "provider"}
    )

    assert payload["symbol"] == "NVDA"
    assert payload["status"] == "resolved"
    assert payload["sector"] == "Information Technology"
    assert payload["industry"] == "Semiconductors & Semi Conductor Equipment"
    assert payload["official_industry"] == "Semiconductors & Semiconductor Equipment"
    assert payload["cycle_tag"] == "cyclical"
    assert payload["provider_industry"] == "Semiconductors"
    assert payload["regime_bias"] == "unknown"
    assert payload["side_support"] == "unknown"
    assert "GDP growth forecast" in payload["regime_note"]
    assert payload["tag_provenance"] == {
        "tag_source": "method_workbook",
        "source_vintage": "2021-gics",
    }


def test_build_payload_unmapped_keeps_provider_fields_only():
    payload = context_tool.build_industry_context_payload(
        profile(), None, {"status": "unmapped_industry", "resolution": "provider"}
    )

    assert payload["status"] == "unmapped_industry"
    assert payload["cycle_tag"] is None
    assert payload["sector"] is None
    assert payload["provider_industry"] == "Semiconductors"
    assert payload["side_support"] == "unknown"
    assert payload["tag_provenance"] is None

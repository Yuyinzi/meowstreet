import pytest

from app.tools import nfib_sbo
from app.data_sources import nfib_sbet_api


def _regional_obs(
    region_id, indicator_id, year, quarter, value, availability="available"
):
    month = quarter * 3
    return {
        "region_id": region_id,
        "indicator_id": indicator_id,
        "date": f"{year:04d}-{month:02d}-30",
        "value": value,
        "availability": availability,
        "display_label": nfib_sbet_api.REGIONS[region_id]["display_label"],
        "api_label": nfib_sbet_api.REGIONS[region_id]["display_label"],
        "states": nfib_sbet_api.REGIONS[region_id]["states"],
        "units": "net_pct",
        "title": "test",
        "source_url": "https://api.nfib-sbet.org/rest/sbetdb/_proc/getTotalsFullQuarter2",
        "procedure_name": "getTotalsFullQuarter2",
    }


def _regional_by_region(region_id, values_by_qi):
    by_indicator = {}
    for indicator_id in nfib_sbet_api.ALL_SERIES_IDS:
        by_indicator[indicator_id] = [
            _regional_obs(region_id, indicator_id, y, q, v)
            for (y, q), v in values_by_qi.items()
        ]
    return by_indicator


def _setup_regional_observations():
    return {
        "pacific": _regional_by_region(
            "pacific",
            {
                (2026, 1): 95.0,
                (2026, 2): 96.0,
            },
        ),
        "west_gulf": _regional_by_region(
            "west_gulf",
            {
                (2026, 1): 93.0,
                (2026, 2): 94.0,
            },
        ),
        "north_atlantic": _regional_by_region(
            "north_atlantic",
            {
                (2026, 1): 97.0,
                (2026, 2): 98.0,
            },
        ),
    }


def _national_observations(
    employment=11, expansion=8, inventory=-3, economy=13, sales=9, optimism=98.5
):
    base = {}
    for series_id, vals in [
        (
            "nfib_sbo_employment_plans",
            [
                (2026, 1, 8),
                (2026, 2, 7),
                (2026, 3, 9),
                (2026, 4, 10),
                (2026, 5, 9),
                (2026, 6, employment),
            ],
        ),
        (
            "nfib_sbo_expansion_outlook",
            [
                (2026, 1, 10),
                (2026, 2, 9),
                (2026, 3, 8),
                (2026, 4, 7),
                (2026, 5, 7),
                (2026, 6, expansion),
            ],
        ),
        (
            "nfib_sbo_inventory_plans",
            [
                (2026, 1, -1),
                (2026, 2, -2),
                (2026, 3, -3),
                (2026, 4, -2),
                (2026, 5, -2),
                (2026, 6, inventory),
            ],
        ),
        (
            "nfib_sbo_economic_expectations",
            [
                (2026, 1, 5),
                (2026, 2, 7),
                (2026, 3, 9),
                (2026, 4, 10),
                (2026, 5, 8),
                (2026, 6, economy),
            ],
        ),
        (
            "nfib_sbo_real_sales_expectations",
            [
                (2026, 1, 3),
                (2026, 2, 4),
                (2026, 3, 5),
                (2026, 4, 6),
                (2026, 5, 6),
                (2026, 6, sales),
            ],
        ),
        (
            "nfib_sbo_optimism",
            [
                (2026, 1, 94.0),
                (2026, 2, 94.5),
                (2026, 3, 95.0),
                (2026, 4, 95.5),
                (2026, 5, 96.2),
                (2026, 6, optimism),
            ],
        ),
    ]:
        base[series_id] = [
            {"date": f"{y:04d}-{m:02d}-30", "value": v, "series_id": series_id}
            for y, m, v in vals
        ]
    for sid in [
        "nfib_sbo_capital_outlay_plans",
        "nfib_sbo_current_inventory_low",
        "nfib_sbo_job_openings",
        "nfib_sbo_credit_conditions_expectations",
        "nfib_sbo_earnings_trends",
    ]:
        base[sid] = [
            {"date": f"2026-{m:02d}-30", "value": 0, "series_id": sid}
            for m in range(1, 7)
        ]
    return base


def test_regional_payload_does_not_change_national_signal():
    national = _national_observations()
    survey_synthesis = {
        "version": "ism_survey_synthesis_v1",
        "status": "available",
        "expected_gdp_direction": "rising",
    }
    signal_before = nfib_sbo.build_nfib_sbo_signal(
        national, survey_synthesis, "2026-07-27"
    )
    regional = _setup_regional_observations()
    payload = nfib_sbo.build_nfib_sbo_regional_payload(regional, national)
    signal_after = nfib_sbo.build_nfib_sbo_signal(
        national, survey_synthesis, "2026-07-27"
    )
    assert signal_after == signal_before
    assert payload["regions"][0].get("research_next_action") is not None


def test_regional_payload_includes_three_regions():
    regional = _setup_regional_observations()
    national = _national_observations()
    payload = nfib_sbo.build_nfib_sbo_regional_payload(regional, national)
    assert len(payload["regions"]) == 3
    assert [r["id"] for r in payload["regions"]] == [
        "pacific",
        "west_gulf",
        "north_atlantic",
    ]


def test_regional_payload_includes_display_labels():
    regional = _setup_regional_observations()
    national = _national_observations()
    payload = nfib_sbo.build_nfib_sbo_regional_payload(regional, national)
    pacific = next(r for r in payload["regions"] if r["id"] == "pacific")
    assert pacific["display_label"] == "Pacific"
    assert pacific["states"] == "AK, CA, HI, OR, WA"


def test_regional_payload_includes_optimism():
    regional = _setup_regional_observations()
    national = _national_observations()
    payload = nfib_sbo.build_nfib_sbo_regional_payload(regional, national)
    pacific = next(r for r in payload["regions"] if r["id"] == "pacific")
    assert pacific["optimism"]["latest"] == 96.0
    assert pacific["optimism"]["period"] == "2026-06-30"
    assert pacific["optimism"]["availability"] == "available"


def test_regional_payload_includes_leading_components():
    regional = _setup_regional_observations()
    national = _national_observations()
    payload = nfib_sbo.build_nfib_sbo_regional_payload(regional, national)
    pacific = next(r for r in payload["regions"] if r["id"] == "pacific")
    for cid in nfib_sbo._COMPONENT_SERIES:
        assert cid in pacific["leading_components"]
        assert pacific["leading_components"][cid]["latest"] is not None
    assert (
        pacific["leading_components"]["nfib_sbo_employment_plans"]["units"] == "net_pct"
    )


def test_regional_payload_includes_context_components():
    regional = _setup_regional_observations()
    national = _national_observations()
    payload = nfib_sbo.build_nfib_sbo_regional_payload(regional, national)
    pacific = next(r for r in payload["regions"] if r["id"] == "pacific")
    for cid in nfib_sbo._CONTEXT_SERIES:
        assert cid in pacific["context_components"]
        assert pacific["context_components"][cid]["latest"] is not None


def test_regional_payload_computes_quarter_over_quarter_change():
    regional = _setup_regional_observations()
    national = _national_observations()
    payload = nfib_sbo.build_nfib_sbo_regional_payload(regional, national)
    pacific = next(r for r in payload["regions"] if r["id"] == "pacific")
    optimism = pacific["optimism"]
    assert optimism["qoq_change"] == 1.0


def test_regional_payload_suppressed_latest_quarter_is_unavailable():
    regional = _setup_regional_observations()
    regional["pacific"]["nfib_sbo_optimism"] = [
        _regional_obs("pacific", "nfib_sbo_optimism", 2026, 1, 95.0),
        _regional_obs("pacific", "nfib_sbo_optimism", 2026, 2, None, "suppressed"),
    ]
    national = _national_observations()
    payload = nfib_sbo.build_nfib_sbo_regional_payload(regional, national)
    pacific = next(r for r in payload["regions"] if r["id"] == "pacific")
    assert pacific["optimism"]["availability"] == "suppressed"
    assert pacific["optimism"]["latest"] is None


def test_regional_payload_includes_national_differences():
    regional = _setup_regional_observations()
    national = _national_observations()
    national_quarterly = {
        "nfib_sbo_optimism": [
            {"date": "2026-06-30", "value": 98.5, "indicator_id": "nfib_sbo_optimism"},
        ],
    }
    payload = nfib_sbo.build_nfib_sbo_regional_payload(
        regional, national, national_quarterly_observations=national_quarterly
    )
    pacific = next(r for r in payload["regions"] if r["id"] == "pacific")
    optimism = pacific["optimism"]
    assert optimism["national_diff"] is not None
    assert optimism["national_diff"]["national_value"] == 98.5
    assert optimism["national_diff"]["difference"] == pytest.approx(96.0 - 98.5)


def test_regional_payload_adds_factual_research_read_from_qoq_and_national_comparison():
    regional = _setup_regional_observations()
    national = _national_observations()
    national_quarterly = {
        "nfib_sbo_optimism": [
            {"date": "2026-06-30", "value": 98.5, "indicator_id": "nfib_sbo_optimism"},
        ],
    }
    payload = nfib_sbo.build_nfib_sbo_regional_payload(
        regional, national, national_quarterly_observations=national_quarterly
    )
    pacific = next(region for region in payload["regions"] if region["id"] == "pacific")

    assert pacific["regional_read"] == {
        "en": "Optimism is 2.5 points below the national quarterly reading and rose 1.0 point from the prior quarter.",
        "zh": "乐观指数较全国季度读数低2.5点，较上季度上升1.0点。",
    }


def test_regional_payload_empty_observations_returns_all_three_unavailable():
    payload = nfib_sbo.build_nfib_sbo_regional_payload({}, {})
    assert len(payload["regions"]) == 3
    for region in payload["regions"]:
        assert region["availability"] == "unavailable"


def test_regional_payload_missing_data_returns_none():
    regional = {"pacific": {}}
    national = _national_observations()
    payload = nfib_sbo.build_nfib_sbo_regional_payload(regional, national)
    assert len(payload["regions"]) == 1
    assert payload["regions"][0]["availability"] == "unavailable"


def test_regional_payload_no_qoq_when_only_one_quarter():
    regional = {
        "pacific": {
            "nfib_sbo_optimism": [
                _regional_obs("pacific", "nfib_sbo_optimism", 2026, 2, 96.0),
            ]
        }
    }
    national = _national_observations()
    payload = nfib_sbo.build_nfib_sbo_regional_payload(regional, national)
    pacific = next(r for r in payload["regions"] if r["id"] == "pacific")
    assert pacific["optimism"]["qoq_change"] is None
    assert pacific["optimism"]["national_diff"] is None


def test_regional_payload_includes_provenance():
    regional = _setup_regional_observations()
    national = _national_observations()
    payload = nfib_sbo.build_nfib_sbo_regional_payload(regional, national)
    pacific = next(r for r in payload["regions"] if r["id"] == "pacific")
    assert "provenance" in pacific
    assert pacific["provenance"]["source_url"] is not None


def test_regional_payload_includes_raw_optimism_history_chart():
    regional = _setup_regional_observations()
    national = _national_observations()
    national_quarterly = {
        "nfib_sbo_optimism": [
            {"date": "2026-03-31", "value": 97.0},
            {"date": "2026-06-30", "value": 98.5},
        ]
    }

    payload = nfib_sbo.build_nfib_sbo_regional_payload(
        regional, {}, national_quarterly_observations=national_quarterly
    )
    chart = payload["optimism_history_chart"]

    assert chart["unit"] == "raw"
    assert chart["keys"] == ["pacific", "west_gulf", "north_atlantic", "national"]
    assert chart["series"][-1] == {
        "date": "2026-06-30",
        "pacific": 96.0,
        "west_gulf": 94.0,
        "north_atlantic": 98.0,
        "national": 98.5,
    }


def test_regional_payload_includes_research_next_action():
    regional = _setup_regional_observations()
    national = _national_observations()
    payload = nfib_sbo.build_nfib_sbo_regional_payload(regional, national)
    for region in payload["regions"]:
        assert region.get("research_next_action") is not None

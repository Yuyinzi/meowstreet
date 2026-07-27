import pytest

from app.tools import nfib_sbo


def _observations_by_series(
    employment=11,
    expansion=8,
    inventory=-3,
    economy=13,
    sales=9,
    optimism=98.5,
):
    def _obs(series_id, values):
        return [
            {"date": f"{m}-30", "value": v, "series_id": series_id} for m, v in values
        ]

    base = {}
    base["nfib_sbo_employment_plans"] = _obs(
        "nfib_sbo_employment_plans",
        [
            ("2026-01", 8),
            ("2026-02", 7),
            ("2026-03", 9),
            ("2026-04", 10),
            ("2026-05", 9),
            ("2026-06", employment),
        ],
    )
    base["nfib_sbo_expansion_outlook"] = _obs(
        "nfib_sbo_expansion_outlook",
        [
            ("2026-01", 10),
            ("2026-02", 9),
            ("2026-03", 8),
            ("2026-04", 7),
            ("2026-05", 7),
            ("2026-06", expansion),
        ],
    )
    base["nfib_sbo_inventory_plans"] = _obs(
        "nfib_sbo_inventory_plans",
        [
            ("2026-01", -1),
            ("2026-02", -2),
            ("2026-03", -3),
            ("2026-04", -2),
            ("2026-05", -2),
            ("2026-06", inventory),
        ],
    )
    base["nfib_sbo_economic_expectations"] = _obs(
        "nfib_sbo_economic_expectations",
        [
            ("2026-01", 5),
            ("2026-02", 7),
            ("2026-03", 9),
            ("2026-04", 10),
            ("2026-05", 8),
            ("2026-06", economy),
        ],
    )
    base["nfib_sbo_real_sales_expectations"] = _obs(
        "nfib_sbo_real_sales_expectations",
        [
            ("2026-01", 3),
            ("2026-02", 4),
            ("2026-03", 5),
            ("2026-04", 6),
            ("2026-05", 6),
            ("2026-06", sales),
        ],
    )
    base["nfib_sbo_optimism"] = _obs(
        "nfib_sbo_optimism",
        [
            ("2026-01", 94.0),
            ("2026-02", 94.5),
            ("2026-03", 95.0),
            ("2026-04", 95.5),
            ("2026-05", 96.2),
            ("2026-06", optimism),
        ],
    )
    return base


def _survey_synthesis(direction="rising"):
    return {
        "version": "ism_survey_synthesis_v1",
        "status": "available",
        "period": "2026-06",
        "expected_gdp_direction": direction,
        "economic_direction": "aligned_expansion",
    }


def test_build_nfib_sbo_signal_uses_equal_weight_average():
    result = nfib_sbo.build_nfib_sbo_signal(
        _observations_by_series(
            employment=11, expansion=8, inventory=-3, economy=13, sales=9
        ),
        _survey_synthesis("rising"),
        "2026-07-27",
    )
    assert result["latest"]["leading_index"] == 7.6


def test_build_nfib_sbo_signal_has_version():
    result = nfib_sbo.build_nfib_sbo_signal(
        _observations_by_series(), _survey_synthesis("rising"), "2026-07-27"
    )
    assert result["version"] == "nfib_sbo_signal_v1"


def test_build_nfib_sbo_signal_supports_rising_survey():
    result = nfib_sbo.build_nfib_sbo_signal(
        _observations_by_series(), _survey_synthesis("rising"), "2026-07-27"
    )
    assert result["status"] == "supports_growth_path"


def test_build_nfib_sbo_signal_challenges_rising_survey():
    result = nfib_sbo.build_nfib_sbo_signal(
        _observations_by_series(
            employment=6, expansion=5, inventory=-5, economy=3, sales=2
        ),
        _survey_synthesis("rising"),
        "2026-07-27",
    )
    assert result["status"] == "challenges_growth_path"


def test_build_nfib_sbo_signal_supports_slowing_survey():
    result = nfib_sbo.build_nfib_sbo_signal(
        _observations_by_series(
            employment=6, expansion=5, inventory=-5, economy=3, sales=2
        ),
        _survey_synthesis("slowing"),
        "2026-07-27",
    )
    assert result["status"] == "supports_growth_path"


def test_build_nfib_sbo_signal_challenges_slowing_survey():
    result = nfib_sbo.build_nfib_sbo_signal(
        _observations_by_series(), _survey_synthesis("slowing"), "2026-07-27"
    )
    assert result["status"] == "challenges_growth_path"


def test_build_nfib_sbo_signal_avoids_look_ahead():
    obs = _observations_by_series(
        employment=11, expansion=8, inventory=-3, economy=13, sales=9
    )
    for sid in nfib_sbo._COMPONENT_SERIES:
        obs[sid] = obs[sid][:-1]
    result = nfib_sbo.build_nfib_sbo_signal(
        obs, _survey_synthesis("rising"), "2026-07-27"
    )
    assert result["status"] == "unavailable"


def test_build_nfib_sbo_signal_less_than_5_months():
    obs = _observations_by_series(
        employment=11, expansion=8, inventory=-3, economy=13, sales=9
    )
    for sid in nfib_sbo._COMPONENT_SERIES:
        obs[sid] = obs[sid][:3]
    result = nfib_sbo.build_nfib_sbo_signal(
        obs, _survey_synthesis("rising"), "2026-04-01"
    )
    assert result["status"] == "awaiting_confirmation"


def test_build_nfib_sbo_signal_no_survey_is_awaiting():
    result = nfib_sbo.build_nfib_sbo_signal(
        _observations_by_series(), None, "2026-07-27"
    )
    assert result["status"] == "awaiting_confirmation"


def test_build_nfib_sbo_signal_is_deterministic():
    r1 = nfib_sbo.build_nfib_sbo_signal(
        _observations_by_series(), _survey_synthesis("rising"), "2026-07-27"
    )
    r2 = nfib_sbo.build_nfib_sbo_signal(
        _observations_by_series(), _survey_synthesis("rising"), "2026-07-27"
    )
    assert r1 == r2


def test_build_nfib_sbo_detail_payload_includes_components():
    obs = _observations_by_series()
    signal = nfib_sbo.build_nfib_sbo_signal(
        obs, _survey_synthesis("rising"), "2026-07-27"
    )
    detail = nfib_sbo.build_nfib_sbo_detail_payload(obs, signal)
    assert detail["detail_id"] == "nfib_sbo"
    for sid in nfib_sbo._COMPONENT_SERIES:
        assert detail["components"][sid] is not None
        assert detail["components"][sid]["latest"] is not None


def test_build_nfib_sbo_detail_payload_includes_optimism():
    obs = _observations_by_series()
    signal = nfib_sbo.build_nfib_sbo_signal(
        obs, _survey_synthesis("rising"), "2026-07-27"
    )
    detail = nfib_sbo.build_nfib_sbo_detail_payload(obs, signal)
    assert detail["optimism"]["latest"] == 98.5


def test_build_nfib_sbo_detail_payload_has_detail_series():
    obs = _observations_by_series()
    signal = nfib_sbo.build_nfib_sbo_signal(
        obs, _survey_synthesis("rising"), "2026-07-27"
    )
    detail = nfib_sbo.build_nfib_sbo_detail_payload(obs, signal)
    assert len(detail["detail_series"]) >= 6
    assert "leading_index" in detail["detail_series"][0]

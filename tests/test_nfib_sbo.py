import pytest

from app.tools import nfib_sbo


def _observations_by_series(
    employment=11,
    expansion=8,
    inventory=-3,
    economy=13,
    sales=9,
    optimism=98.5,
    job_openings_obs=None,
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
    job_val = job_openings_obs if job_openings_obs is not None else (33, 32)
    base["nfib_sbo_capital_outlay_plans"] = _obs(
        "nfib_sbo_capital_outlay_plans",
        [
            ("2026-01", 20),
            ("2026-02", 20),
            ("2026-03", 20),
            ("2026-04", 20),
            ("2026-05", 20),
            ("2026-06", 20),
        ],
    )
    base["nfib_sbo_current_inventory_low"] = _obs(
        "nfib_sbo_current_inventory_low",
        [
            ("2026-01", 0),
            ("2026-02", 0),
            ("2026-03", 0),
            ("2026-04", 0),
            ("2026-05", 0),
            ("2026-06", 0),
        ],
    )
    base["nfib_sbo_job_openings"] = _obs(
        "nfib_sbo_job_openings",
        [
            ("2026-01", 33),
            ("2026-02", 33),
            ("2026-03", 33),
            ("2026-04", 33),
            ("2026-05", job_val[0]),
            ("2026-06", job_val[1]),
        ],
    )
    base["nfib_sbo_credit_conditions_expectations"] = _obs(
        "nfib_sbo_credit_conditions_expectations",
        [
            ("2026-01", -5),
            ("2026-02", -5),
            ("2026-03", -5),
            ("2026-04", -5),
            ("2026-05", -5),
            ("2026-06", -5),
        ],
    )
    base["nfib_sbo_earnings_trends"] = _obs(
        "nfib_sbo_earnings_trends",
        [
            ("2026-01", -20),
            ("2026-02", -20),
            ("2026-03", -20),
            ("2026-04", -20),
            ("2026-05", -20),
            ("2026-06", -20),
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


def _observations_with_leading_indices(values):
    def _obs(series_id):
        return [
            {"date": f"{month}-28", "value": value, "series_id": series_id}
            for month, value in values
        ]

    return {series_id: _obs(series_id) for series_id in nfib_sbo._ALL_SERIES}


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
    assert result["reason"] == "nfib evidence supports the rising growth path"


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


def test_build_nfib_sbo_signal_explains_weaker_trend_and_latest_rebound():
    observations = _observations_with_leading_indices(
        [
            ("2026-01", 7),
            ("2026-02", 8),
            ("2026-03", 8),
            ("2026-04", 7),
            ("2026-05", 3),
            ("2026-06", 7.6),
        ]
    )

    result = nfib_sbo.build_nfib_sbo_signal(
        observations, _survey_synthesis("slowing"), "2026-07-27"
    )

    assert result["status"] == "awaiting_confirmation"
    assert result["latest"]["leading_index_1m_change"] == 4.6
    assert result["latest"]["previous_leading_index"] == 3.0
    assert result["reason"] == (
        "nfib's 4-month trend is weakening, but the latest leading index rose "
        "from 3.0 to 7.6, so it has not yet confirmed the ism-implied slowing "
        "growth path"
    )


def test_build_nfib_sbo_detail_payload_includes_components():
    obs = _observations_by_series()
    signal = nfib_sbo.build_nfib_sbo_signal(
        obs, _survey_synthesis("rising"), "2026-07-27"
    )
    detail = nfib_sbo.build_nfib_sbo_detail_payload(obs, signal)
    assert detail["detail_id"] == "nfib_sbo"
    for sid in nfib_sbo._COMPONENT_SERIES:
        assert detail["leading_components"][sid] is not None
        assert detail["leading_components"][sid]["latest"] is not None


def test_build_nfib_sbo_detail_payload_includes_optimism():
    obs = _observations_by_series()
    signal = nfib_sbo.build_nfib_sbo_signal(
        obs, _survey_synthesis("rising"), "2026-07-27"
    )
    detail = nfib_sbo.build_nfib_sbo_detail_payload(obs, signal)
    assert detail["optimism"]["latest"] == 98.5
    assert detail["optimism"]["basis"] == "1986=100"
    assert detail["optimism"]["role"] == "overall_context"


def test_build_nfib_sbo_detail_payload_has_detail_series():
    obs = _observations_by_series()
    signal = nfib_sbo.build_nfib_sbo_signal(
        obs, _survey_synthesis("rising"), "2026-07-27"
    )
    detail = nfib_sbo.build_nfib_sbo_detail_payload(obs, signal)
    assert len(detail["detail_series"]) >= 6
    assert "leading_index" in detail["detail_series"][0]


def test_build_nfib_sbo_detail_payload_includes_context_components():
    obs = _observations_by_series()
    signal = nfib_sbo.build_nfib_sbo_signal(
        obs, _survey_synthesis("rising"), "2026-07-27"
    )
    detail = nfib_sbo.build_nfib_sbo_detail_payload(obs, signal)
    for sid in nfib_sbo._CONTEXT_SERIES:
        assert detail["context_components"][sid] is not None
        assert detail["context_components"][sid]["latest"] is not None
        assert detail["context_components"][sid]["role"] == "context_only"
        assert detail["context_components"][sid]["units"] == "net_pct"
        assert detail["context_components"][sid]["title"] is not None


def test_build_nfib_sbo_detail_payload_context_change():
    obs = _observations_by_series(job_openings_obs=(34, 32))
    signal = nfib_sbo.build_nfib_sbo_signal(
        obs, _survey_synthesis("rising"), "2026-07-27"
    )
    detail = nfib_sbo.build_nfib_sbo_detail_payload(obs, signal)
    ctx = detail["context_components"]["nfib_sbo_job_openings"]
    assert ctx["previous"] == 34
    assert ctx["change"] == -2.0
    assert ctx["role"] == "context_only"

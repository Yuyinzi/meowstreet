import pytest

from app.tools import housing_permits


def _observation(date_str, value):
    return {
        "date": date_str,
        "value": value,
        "source": "census.xlsx",
        "release_date": "2026-06-16",
        "revision_status": "official_current_history",
        "source_url": "https://www.census.gov/construction/nrc/index.html",
        "source_identifier": "permits_cust.xlsx",
    }


def monthly_observations(
    count, start_value=1000, monthly_step=10, end_year=2026, end_month=6
):
    result = []
    start_total_months = end_year * 12 + end_month
    for i in range(count):
        total = start_total_months - count + 1 + i
        year = total // 12
        month = total % 12
        if month == 0:
            year -= 1
            month = 12
        value = start_value + i * monthly_step
        result.append(_observation(f"{year}-{month:02d}-01", float(value)))
    return result


def observations_with_latest_change(change_pct):
    obs = monthly_observations(24, 1000, 10)
    obs[-1]["value"] = obs[-2]["value"] * (1 + change_pct)
    return obs


def survey(direction="rising"):
    return {
        "version": "ism_survey_synthesis_v1",
        "status": "available",
        "economic_direction": "aligned_expansion",
        "expected_gdp_direction": direction,
        "survey_portfolio_implication": "long",
        "period": "2026-06",
    }


class TestBuildHousingPermitsSignal:
    def test_build_housing_permits_signal_calculates_method_metrics_without_lookahead(
        self,
    ):
        observations = monthly_observations(24, start_value=1000, monthly_step=10)
        result = housing_permits.build_housing_permits_signal(
            observations, survey("rising"), "2026-07-26"
        )
        assert result["latest"]["permits_saar"] == 1230.0
        assert result["latest"]["permits_mom_pct"] == pytest.approx(10 / 1220)
        assert result["latest"]["permits_yoy_pct"] == pytest.approx(120 / 1110)
        assert result["status"] == "supports_growth_path"

    def test_build_housing_permits_signal_marks_extreme_month_awaiting_confirmation(
        self,
    ):
        observations = observations_with_latest_change(0.21)
        result = housing_permits.build_housing_permits_signal(
            observations, survey("rising"), "2026-07-26"
        )
        assert result["status"] == "awaiting_confirmation"

    def test_build_housing_permits_signal_rejects_empty_observations(self):
        result = housing_permits.build_housing_permits_signal(
            [], survey("rising"), "2026-07-26"
        )
        assert result["status"] == "unavailable"

    def test_build_housing_permits_signal_rejects_missing_yoy_history(self):
        observations = monthly_observations(11, 1000, 10)
        result = housing_permits.build_housing_permits_signal(
            observations, survey("rising"), "2026-07-26"
        )
        assert result["status"] == "unavailable"

    def test_build_housing_permits_signal_rejects_stale_latest_observation(self):
        observations = monthly_observations(24, 1000, 10, end_year=2026, end_month=4)
        result = housing_permits.build_housing_permits_signal(
            observations, survey("rising"), "2026-07-26"
        )
        assert result["status"] == "unavailable"

    def test_build_housing_permits_signal_yoy_average_requires_12_yoy_values(self):
        observations = monthly_observations(23, 1000, 10)
        result = housing_permits.build_housing_permits_signal(
            observations, survey("rising"), "2026-07-26"
        )
        assert result["latest"]["permits_yoy_12m_average"] is None

    def test_build_housing_permits_signal_challenges_growth_path(self):
        observations = monthly_observations(24, 1000, -10)
        result = housing_permits.build_housing_permits_signal(
            observations, survey("rising"), "2026-07-26"
        )
        assert result["status"] == "challenges_growth_path"

    def test_build_housing_permits_signal_exact_zero_mom_is_awaiting_confirmation(
        self,
    ):
        observations = monthly_observations(24, 1000, 0)
        result = housing_permits.build_housing_permits_signal(
            observations, survey("rising"), "2026-07-26"
        )
        assert result["status"] == "awaiting_confirmation"

    def test_build_housing_permits_signal_returns_unavailable_for_incomplete_survey(
        self,
    ):
        observations = monthly_observations(24, 1000, 10)
        result = housing_permits.build_housing_permits_signal(
            observations, {"status": "partial"}, "2026-07-26"
        )
        assert result["status"] == "awaiting_confirmation"

    def test_build_housing_permits_signal_returns_yoy_average_for_full_history(self):
        observations = monthly_observations(36, 1000, 10)
        result = housing_permits.build_housing_permits_signal(
            observations, survey("rising"), "2026-07-26"
        )
        assert result["latest"]["permits_yoy_12m_average"] is not None

    def test_build_housing_permits_signal_freshness_before_day_20_allows_two_month_lag(
        self,
    ):
        observations = monthly_observations(24, 1000, 10, end_year=2026, end_month=5)
        result = housing_permits.build_housing_permits_signal(
            observations, survey("rising"), "2026-07-15"
        )
        assert result["status"] != "unavailable"

    def test_build_housing_permits_signal_freshness_on_day_20_allows_one_month_lag(
        self,
    ):
        observations = monthly_observations(24, 1000, 10, end_year=2026, end_month=6)
        result = housing_permits.build_housing_permits_signal(
            observations, survey("rising"), "2026-07-20"
        )
        assert result["status"] != "unavailable"


class TestBuildHousingPermitsCard:
    def test_build_housing_permits_card_contains_required_fields(self):
        obs = monthly_observations(24, 1000, 10)
        signal = housing_permits.build_housing_permits_signal(
            obs, survey("rising"), "2026-07-26"
        )
        card = housing_permits.build_housing_permits_card(signal)
        assert card["id"] == "housing_permits"
        assert "latest" in card
        assert card["latest"]["permits_saar"] == 1230.0

    def test_build_housing_permits_card_shows_unavailable_state(self):
        signal = {"status": "unavailable", "reason": "no observations loaded"}
        card = housing_permits.build_housing_permits_card(signal)
        assert card["status"] == "unavailable"


class TestBuildHousingPermitsDetail:
    def test_build_housing_permits_detail_payload_contains_two_charts(self):
        obs = monthly_observations(36, 1000, 10)
        signal = housing_permits.build_housing_permits_signal(
            obs, survey("rising"), "2026-07-26"
        )
        detail = housing_permits.build_housing_permits_detail_payload(obs, signal)
        assert detail["series_id"] == "building_permits_saar"
        assert len(detail["charts"]) == 2
        assert detail["charts"][0]["title"] == "Building Permits SAAR"
        assert detail["charts"][1]["title"] == "Building Permits YoY and 12M Average"

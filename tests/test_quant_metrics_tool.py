from datetime import datetime

import pytest

from app.tools import quant_metrics


class TestPeDifferential:
    def test_returns_forward_divided_by_peer(self):
        assert quant_metrics.pe_differential(20.0, 16.0) == pytest.approx(1.25)

    def test_returns_none_when_forward_pe_missing(self):
        assert quant_metrics.pe_differential(None, 16.0) is None

    def test_returns_none_when_peer_pe_missing(self):
        assert quant_metrics.pe_differential(20.0, None) is None

    def test_returns_none_when_peer_pe_is_zero(self):
        assert quant_metrics.pe_differential(20.0, 0.0) is None


class TestDaysToCover:
    def test_returns_within_when_exactly_15(self):
        volumes = [1.0] * 30
        result = quant_metrics.days_to_cover(15.0, volumes)
        assert result["value"] == pytest.approx(15.0)
        assert result["status"] == "within"
        assert result["sample_days"] == 30

    def test_returns_dangerous_when_greater_than_15(self):
        volumes = [1.0] * 30
        result = quant_metrics.days_to_cover(15.1, volumes)
        assert result["status"] == "dangerous"

    def test_returns_dangerous_when_exactly_30(self):
        volumes = [1.0] * 30
        result = quant_metrics.days_to_cover(30.0, volumes)
        assert result["value"] == pytest.approx(30.0)
        assert result["status"] == "dangerous"

    def test_returns_officially_dangerous_when_greater_than_30(self):
        volumes = [1.0] * 30
        result = quant_metrics.days_to_cover(31.0, volumes)
        assert result["value"] == pytest.approx(31.0)
        assert result["status"] == "officially_dangerous"

    def test_returns_insufficient_data_when_less_than_30_samples(self):
        volumes = [1.0] * 29
        result = quant_metrics.days_to_cover(15.0, volumes)
        assert result["value"] is None
        assert result["status"] == "insufficient_data"
        assert result["sample_days"] == 29

    def test_returns_insufficient_data_when_volumes_empty(self):
        result = quant_metrics.days_to_cover(15.0, [])
        assert result["value"] is None
        assert result["status"] == "insufficient_data"
        assert result["sample_days"] == 0

    def test_returns_insufficient_data_when_shares_short_missing(self):
        volumes = [1.0] * 30
        result = quant_metrics.days_to_cover(None, volumes)
        assert result["value"] is None
        assert result["status"] == "insufficient_data"
        assert result["sample_days"] == 0

    def test_returns_insufficient_data_when_average_volume_is_zero(self):
        volumes = [0.0] * 30
        result = quant_metrics.days_to_cover(15.0, volumes)
        assert result["value"] is None
        assert result["status"] == "insufficient_data"


class TestShortCheckPayload:
    def test_builds_full_payload(self):
        fundamentals = {
            "shares_short": 150.0,
            "short_percent_of_float": 0.0126,
            "dividend_yield": 0.0048,
        }
        volumes = [10.0] * 30
        payload = quant_metrics.short_check_payload(fundamentals, volumes)

        assert payload["short_percent_of_float"] == pytest.approx(0.0126)
        assert payload["days_to_cover"]["value"] == pytest.approx(15.0)
        assert payload["dividend"]["yield"] == pytest.approx(0.0048)
        assert len(payload["dividend"]["review_questions"]) == 3

    def test_tolerates_missing_fundamentals(self):
        payload = quant_metrics.short_check_payload(None, [1.0] * 30)
        assert payload["short_percent_of_float"] is None
        assert payload["days_to_cover"]["value"] is None
        assert payload["dividend"]["yield"] is None

    def test_tolerates_partial_fields(self):
        payload = quant_metrics.short_check_payload({}, [1.0] * 30)
        assert payload["short_percent_of_float"] is None
        assert payload["days_to_cover"]["status"] == "insufficient_data"
        assert payload["dividend"]["yield"] is None


class TestBackwardRatiosPayload:
    def test_debt_to_equity_converted_and_within(self):
        fundamentals = {"debt_to_equity": 150.0}
        payload = quant_metrics.backward_ratios_payload(fundamentals)
        ratio = next(r for r in payload["ratios"] if r["key"] == "debt_to_equity")
        assert ratio["value"] == pytest.approx(1.5)
        assert ratio["status"] == "within"
        assert "converted to ratio" in ratio["note"]

    def test_debt_to_equity_dangerous_when_ratio_exceeds_2(self):
        fundamentals = {"debt_to_equity": 250.0}
        payload = quant_metrics.backward_ratios_payload(fundamentals)
        ratio = next(r for r in payload["ratios"] if r["key"] == "debt_to_equity")
        assert ratio["value"] == pytest.approx(2.5)
        assert ratio["status"] == "dangerous"

    def test_current_ratio_warning_when_below_1(self):
        fundamentals = {"current_ratio": 0.95}
        payload = quant_metrics.backward_ratios_payload(fundamentals)
        ratio = next(r for r in payload["ratios"] if r["key"] == "current_ratio")
        assert ratio["value"] == pytest.approx(0.95)
        assert ratio["status"] == "warning"

    def test_current_ratio_within_when_at_least_1(self):
        fundamentals = {"current_ratio": 1.0}
        payload = quant_metrics.backward_ratios_payload(fundamentals)
        ratio = next(r for r in payload["ratios"] if r["key"] == "current_ratio")
        assert ratio["status"] == "within"

    def test_info_fields_pass_through(self):
        fundamentals = {
            "quick_ratio": 2.0,
            "return_on_equity": 0.12,
            "return_on_assets": 0.06,
            "book_value": 8.0,
        }
        payload = quant_metrics.backward_ratios_payload(fundamentals)
        keys = {r["key"]: r for r in payload["ratios"]}
        for key in ("quick_ratio", "return_on_equity", "return_on_assets", "book_value"):
            assert keys[key]["value"] == fundamentals[key]
            assert keys[key]["status"] == "info"

    def test_fcf_metrics_when_positive(self):
        fundamentals = {"market_cap": 1000.0, "free_cashflow": 100.0}
        payload = quant_metrics.backward_ratios_payload(fundamentals)
        keys = {r["key"]: r for r in payload["ratios"]}
        assert keys["fcf_yield"]["value"] == pytest.approx(0.1)
        assert keys["price_to_fcf"]["value"] == pytest.approx(10.0)
        assert "note" not in keys["price_to_fcf"]

    def test_price_to_fcf_none_when_free_cashflow_zero(self):
        fundamentals = {"market_cap": 1000.0, "free_cashflow": 0.0}
        payload = quant_metrics.backward_ratios_payload(fundamentals)
        keys = {r["key"]: r for r in payload["ratios"]}
        assert keys["price_to_fcf"]["value"] is None
        assert "negative" in keys["price_to_fcf"]["note"]

    def test_price_to_fcf_none_when_free_cashflow_negative(self):
        fundamentals = {"market_cap": 1000.0, "free_cashflow": -50.0}
        payload = quant_metrics.backward_ratios_payload(fundamentals)
        keys = {r["key"]: r for r in payload["ratios"]}
        assert keys["price_to_fcf"]["value"] is None

    def test_ev_to_ebitda_when_positive(self):
        fundamentals = {"enterprise_value": 1000.0, "ebitda": 200.0}
        payload = quant_metrics.backward_ratios_payload(fundamentals)
        ratio = next(r for r in payload["ratios"] if r["key"] == "ev_to_ebitda")
        assert ratio["value"] == pytest.approx(5.0)

    def test_ev_to_ebitda_none_when_ebitda_zero(self):
        fundamentals = {"enterprise_value": 1000.0, "ebitda": 0.0}
        payload = quant_metrics.backward_ratios_payload(fundamentals)
        ratio = next(r for r in payload["ratios"] if r["key"] == "ev_to_ebitda")
        assert ratio["value"] is None
        assert "negative" in ratio["note"]

    def test_ev_to_ebitda_none_when_ebitda_negative(self):
        fundamentals = {"enterprise_value": 1000.0, "ebitda": -10.0}
        payload = quant_metrics.backward_ratios_payload(fundamentals)
        ratio = next(r for r in payload["ratios"] if r["key"] == "ev_to_ebitda")
        assert ratio["value"] is None

    def test_missing_inputs_are_fixed_three(self):
        payload = quant_metrics.backward_ratios_payload({})
        assert payload["missing_inputs"] == [
            "interest_coverage",
            "working_capital_to_total_assets",
            "ev_to_ebit",
        ]

    def test_tolerates_none_fundamentals(self):
        payload = quant_metrics.backward_ratios_payload(None)
        assert payload["missing_inputs"] == [
            "interest_coverage",
            "working_capital_to_total_assets",
            "ev_to_ebit",
        ]
        for ratio in payload["ratios"]:
            assert ratio["value"] is None


class TestEstimateConsensusPayload:
    def test_positive_skew_when_avg_above_midpoint(self):
        payload = quant_metrics.estimate_consensus_payload(
            {"fiscal_year_end": "2026-12-31", "analyst_count": 38, "avg": 1.51, "low": 1.12, "high": 1.69}
        )

        assert payload["status"] == "ok"
        assert payload["midpoint"] == pytest.approx(1.405)
        assert payload["skew"] == "positive"

    def test_negative_skew_when_avg_below_midpoint(self):
        payload = quant_metrics.estimate_consensus_payload(
            {"fiscal_year_end": "2026-12-31", "analyst_count": 10, "avg": 1.3, "low": 1.2, "high": 1.6}
        )

        assert payload["skew"] == "negative"

    def test_neutral_skew_when_avg_equals_midpoint(self):
        payload = quant_metrics.estimate_consensus_payload(
            {"fiscal_year_end": "2026-12-31", "analyst_count": 10, "avg": 1.5, "low": 1.0, "high": 2.0}
        )

        assert payload["skew"] == "neutral"

    def test_missing_consensus_returns_insufficient_data(self):
        assert quant_metrics.estimate_consensus_payload(None) == {"status": "insufficient_data"}

    def test_missing_fields_return_insufficient_data(self):
        for consensus in (
            {"avg": 1.5, "low": 1.0},
            {"avg": 1.5, "low": 1.0, "high": None},
            {"avg": None, "low": 1.0, "high": 2.0},
        ):
            assert quant_metrics.estimate_consensus_payload(consensus) == {"status": "insufficient_data"}


class TestEstimateRevisionTrend:
    def test_accumulating_when_fewer_than_two_snapshots(self):
        now = datetime.fromisoformat("2026-08-28T12:00:00+00:00")
        snapshots = [
            {"avg": 1.5, "captured_at": "2026-08-27T12:00:00+00:00"},
        ]

        result = quant_metrics.estimate_revision_trend(snapshots, now)

        assert result["status"] == "accumulating"
        assert result["sample_snapshots"] == 1

    def test_filters_outside_30_day_window(self):
        now = datetime.fromisoformat("2026-08-28T12:00:00+00:00")
        snapshots = [
            {"avg": 1.0, "captured_at": "2026-07-01T12:00:00+00:00"},
            {"avg": 1.5, "captured_at": "2026-08-27T12:00:00+00:00"},
            {"avg": 1.6, "captured_at": "2026-08-28T12:00:00+00:00"},
        ]

        result = quant_metrics.estimate_revision_trend(snapshots, now)

        assert result["status"] == "ok"
        assert result["sample_snapshots"] == 2
        assert result["direction"] == "up"
        assert result["avg_first"] == 1.5
        assert result["avg_latest"] == 1.6

    def test_up_when_only_increases(self):
        now = datetime.fromisoformat("2026-08-28T12:00:00+00:00")
        snapshots = [
            {"avg": 1.0, "captured_at": "2026-08-26T12:00:00+00:00"},
            {"avg": 1.1, "captured_at": "2026-08-27T12:00:00+00:00"},
            {"avg": 1.2, "captured_at": "2026-08-28T12:00:00+00:00"},
        ]

        result = quant_metrics.estimate_revision_trend(snapshots, now)

        assert result["direction"] == "up"
        assert result["increases"] == 2
        assert result["decreases"] == 0

    def test_down_when_only_decreases(self):
        now = datetime.fromisoformat("2026-08-28T12:00:00+00:00")
        snapshots = [
            {"avg": 1.2, "captured_at": "2026-08-26T12:00:00+00:00"},
            {"avg": 1.1, "captured_at": "2026-08-27T12:00:00+00:00"},
            {"avg": 1.0, "captured_at": "2026-08-28T12:00:00+00:00"},
        ]

        result = quant_metrics.estimate_revision_trend(snapshots, now)

        assert result["direction"] == "down"
        assert result["increases"] == 0
        assert result["decreases"] == 2

    def test_mixed_when_both_increases_and_decreases(self):
        now = datetime.fromisoformat("2026-08-28T12:00:00+00:00")
        snapshots = [
            {"avg": 1.0, "captured_at": "2026-08-25T12:00:00+00:00"},
            {"avg": 1.1, "captured_at": "2026-08-26T12:00:00+00:00"},
            {"avg": 1.05, "captured_at": "2026-08-27T12:00:00+00:00"},
        ]

        result = quant_metrics.estimate_revision_trend(snapshots, now)

        assert result["direction"] == "mixed"
        assert result["increases"] == 1
        assert result["decreases"] == 1

    def test_flat_when_no_changes(self):
        now = datetime.fromisoformat("2026-08-28T12:00:00+00:00")
        snapshots = [
            {"avg": 1.0, "captured_at": "2026-08-26T12:00:00+00:00"},
            {"avg": 1.0, "captured_at": "2026-08-27T12:00:00+00:00"},
            {"avg": 1.0, "captured_at": "2026-08-28T12:00:00+00:00"},
        ]

        result = quant_metrics.estimate_revision_trend(snapshots, now)

        assert result["direction"] == "flat"
        assert result["increases"] == 0
        assert result["decreases"] == 0

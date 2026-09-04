from datetime import date, timedelta

import pytest

from app.tools import catalyst_stats


def _date_sequence(count, end=date(2026, 8, 26)):
    return [
        (end - timedelta(days=count - 1 - index)).isoformat()
        for index in range(count)
    ]


class TestFilingFrequency:
    def test_counts_and_averages(self):
        filings = [
            {"filing_date": "2025-09-01", "is_earnings": 1},
            {"filing_date": "2025-12-01", "is_earnings": 0},
            {"filing_date": "2026-03-01", "is_earnings": 1},
            {"filing_date": "2026-06-01", "is_earnings": None},
        ]
        result = catalyst_stats.filing_frequency(filings, "2026-09-01")
        assert result["status"] == "ok"
        assert result["total"] == 4
        assert result["earnings"] == 2
        assert result["non_earnings"] == 1
        assert result["unclassified"] == 1
        assert result["window_months"] == pytest.approx(12.0, abs=0.1)
        assert result["per_year"] == pytest.approx(4.0, abs=0.1)
        assert result["non_earnings_per_month"] is None

    def test_non_earnings_per_month_when_fully_classified(self):
        filings = [
            {"filing_date": "2025-09-01", "is_earnings": 1},
            {"filing_date": "2025-12-01", "is_earnings": 0},
            {"filing_date": "2026-03-01", "is_earnings": 0},
            {"filing_date": "2026-06-01", "is_earnings": 0},
        ]
        result = catalyst_stats.filing_frequency(filings, "2026-09-01")
        assert result["non_earnings_per_month"] == pytest.approx(0.25, abs=0.01)

    def test_empty_filings_insufficient(self):
        assert catalyst_stats.filing_frequency([], "2026-09-01") == {"status": "insufficient_data"}

    def test_undated_filings_skipped(self):
        filings = [{"filing_date": "not-a-date", "is_earnings": 1}, {"filing_date": None}]
        assert catalyst_stats.filing_frequency(filings, "2026-09-01") == {"status": "insufficient_data"}


class TestLargeMoveDays:
    def test_flags_hand_computable_outlier(self):
        closes = [100.0] * 40 + [110.0]
        dates = _date_sequence(41)
        result = catalyst_stats.large_move_days(closes, dates)
        assert result["status"] == "ok"
        assert result["sample_days"] == 40
        assert result["mean_return"] == pytest.approx(0.0025)
        assert result["stdev"] == pytest.approx(0.015811, abs=1e-6)
        assert len(result["moves"]) == 1
        move = result["moves"][0]
        assert move["date"] == "2026-08-26"
        assert move["return"] == pytest.approx(0.1)
        assert move["abs_sigma"] == pytest.approx(6.166, abs=0.01)
        assert move["beyond_2sigma"] is True

    def test_insufficient_samples(self):
        result = catalyst_stats.large_move_days([100.0] * 10, _date_sequence(10))
        assert result["status"] == "insufficient_data"
        assert result["sample_days"] == 9

    def test_length_mismatch_raises(self):
        with pytest.raises(ValueError, match="closes and dates length differ"):
            catalyst_stats.large_move_days([1.0, 2.0], ["2026-08-01"])

    def test_flat_series_zero_sigma_insufficient(self):
        result = catalyst_stats.large_move_days([100.0] * 40, _date_sequence(40))
        assert result["status"] == "insufficient_data"


class TestAlignMovesWithFilings:
    def test_matches_within_tolerance(self):
        moves = [
            {"date": "2026-08-26", "return": 0.1, "abs_sigma": 3.0},
            {"date": "2026-08-10", "return": -0.08, "abs_sigma": 2.5},
        ]
        aligned = catalyst_stats.align_moves_with_filings(moves, ["2026-08-27"])
        assert aligned[0]["filing_within_window"] is True
        assert aligned[1]["filing_within_window"] is False

    def test_unparseable_move_date_marked_unknown(self):
        aligned = catalyst_stats.align_moves_with_filings([{"date": "n/a"}], ["2026-08-27"])
        assert aligned[0]["filing_within_window"] is None


class TestDailyReturnCalendar:
    def test_pairs_each_return_with_following_date(self):
        closes = [100.0, 110.0, 99.0]
        dates = ["2026-08-24", "2026-08-25", "2026-08-26"]
        days = catalyst_stats.daily_return_calendar(closes, dates)
        assert days == [
            {"date": "2026-08-25", "return": pytest.approx(0.1)},
            {"date": "2026-08-26", "return": pytest.approx(-0.1)},
        ]

    def test_length_mismatch_raises(self):
        with pytest.raises(ValueError, match="closes and dates length differ"):
            catalyst_stats.daily_return_calendar([1.0, 2.0], ["2026-08-01"])

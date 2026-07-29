import pytest

from app.db import macro_indicators
from app.services import nfib_sbet_regional_import


def _db_observation(
    region_id, indicator_id, year, quarter, value, availability="available"
):
    month = quarter * 3
    return {
        "region_id": region_id,
        "indicator_id": indicator_id,
        "date": f"{year:04d}-{month:02d}-30",
        "value": value,
        "availability": availability,
        "title": "test",
        "units": "net_pct",
        "frequency": "quarterly_3_month_aggregate",
        "api_label": "Test",
        "display_label": "Test",
        "states": "XX",
        "procedure_name": "getTotalsFullQuarter2",
        "source_url": "https://api.nfib-sbet.org/rest/sbetdb/_proc/getTotalsFullQuarter2",
        "retrieval_time": "2026-07-27T00:00:00",
    }


def _all_regional_rows():
    rows = []
    for region_id in ["pacific", "west_gulf", "north_atlantic"]:
        for indicator_id in nfib_sbet_regional_import.ALL_SERIES_IDS:
            for year in range(2021, 2027):
                for quarter in range(1, 5):
                    if (year, quarter) > (2026, 2):
                        continue
                    value = (
                        hash(f"{region_id}:{indicator_id}:{year}:Q{quarter}") % 50 + 80
                    )
                    rows.append(
                        _db_observation(
                            region_id, indicator_id, year, quarter, float(value)
                        )
                    )
    return rows


def test_merge_nfib_regional_observations_batch_stores_all_regions_and_indicators(
    tmp_path,
):
    con = macro_indicators.connect(tmp_path / "market.sqlite")
    try:
        expected_regions = {"pacific", "west_gulf", "north_atlantic"}
        expected_indicators = nfib_sbet_regional_import.ALL_SERIES_IDS
        rows = _all_regional_rows()
        count = nfib_sbet_regional_import.merge_nfib_regional_observations_batch(
            con, rows
        )
        assert count == len(rows)

        stored = nfib_sbet_regional_import.load_nfib_regional_observations(
            con, "pacific", "nfib_sbo_optimism"
        )
        assert len(stored) > 0
        assert stored[-1]["availability"] == "available"

        all_stored = nfib_sbet_regional_import.load_all_nfib_regional_observations(con)
        stored_regions = {r["region_id"] for r in all_stored}
        stored_indicators = {r["indicator_id"] for r in all_stored}
        assert stored_regions == expected_regions
        assert stored_indicators == expected_indicators
    finally:
        con.close()


def test_merge_nfib_regional_observations_batch_is_idempotent(tmp_path):
    con = macro_indicators.connect(tmp_path / "market.sqlite")
    try:
        rows = _all_regional_rows()
        nfib_sbet_regional_import.merge_nfib_regional_observations_batch(con, rows)
        count2 = nfib_sbet_regional_import.merge_nfib_regional_observations_batch(
            con, rows
        )
        assert count2 == len(rows)
        stored = nfib_sbet_regional_import.load_nfib_regional_observations(
            con, "pacific", "nfib_sbo_optimism"
        )
        assert len(stored) == 22
    finally:
        con.close()


def test_merge_nfib_regional_observations_batch_stores_suppressed_values(tmp_path):
    con = macro_indicators.connect(tmp_path / "market.sqlite")
    try:
        rows = [
            _db_observation(
                "pacific", "nfib_sbo_employment_plans", 2026, 2, None, "suppressed"
            ),
        ]
        nfib_sbet_regional_import.merge_nfib_regional_observations_batch(con, rows)
        stored = nfib_sbet_regional_import.load_nfib_regional_observations(
            con, "pacific", "nfib_sbo_employment_plans"
        )
        assert stored[-1]["value"] is None
        assert stored[-1]["availability"] == "suppressed"
    finally:
        con.close()


def test_import_official_regional_sbet_coordinates_api_and_db(tmp_path):
    con = macro_indicators.connect(tmp_path / "market.sqlite")
    try:

        def fake_fetcher(region_id, start_year, end_year, opener=None):
            obs = {
                "date": "2026-06-30",
                "optimism": 95.0,
                "emp_count_change_expect": 10.0,
                "expand_good": 8.0,
                "inventory_expect": -3.0,
                "bus_cond_expect": 13.0,
                "sales_expect": 9.0,
                "cap_ex_expect": 20.0,
                "inventory_current": 0.0,
                "job_opening_unfilled": 32.0,
                "credit_access_expect": -5.0,
                "earn_change": -20.0,
                "_availability": "available",
            }
            return {
                "region_id": region_id,
                "start_year": start_year,
                "end_year": end_year,
                "frequency": "quarterly_3_month_aggregate",
                "retrieval_time": "2026-07-27T00:00:00",
                "request_hash": "abc123",
                "request_body": {"test": "body"},
                "provenance": {
                    "url": "https://api.example.com",
                    "procedure": "getTotalsFullQuarter2",
                    "retrieval_time": "2026-07-27T00:00:00",
                    "request_hash": "abc123",
                },
                "observations": [obs],
            }

        count = nfib_sbet_regional_import.import_official_regional_sbet(
            con, 2026, 2026, fetcher=fake_fetcher
        )
        assert count == 3 * 11

        stored = nfib_sbet_regional_import.load_nfib_regional_observations(
            con, "pacific", "nfib_sbo_optimism"
        )
        assert stored[-1]["value"] == 95.0
    finally:
        con.close()


def test_import_official_regional_sbet_rolls_back_on_invalid_response(tmp_path):
    con = macro_indicators.connect(tmp_path / "market.sqlite")
    try:
        call_count = 0

        def failing_fetcher(region_id, start_year, end_year, opener=None):
            nonlocal call_count
            call_count += 1
            if call_count >= 3:
                raise ValueError("nfib regional api: something went wrong")
            return {
                "region_id": region_id,
                "start_year": start_year,
                "end_year": end_year,
                "frequency": "quarterly_3_month_aggregate",
                "retrieval_time": "2026-07-27T00:00:00",
                "request_hash": "abc",
                "request_body": {"test": "body"},
                "provenance": {},
                "observations": [
                    {
                        "date": "2026-06-30",
                        "optimism": 50.0,
                        "_availability": "available",
                    }
                ],
            }

        with pytest.raises(ValueError, match="nfib regional"):
            nfib_sbet_regional_import.import_official_regional_sbet(
                con, 2026, 2026, fetcher=failing_fetcher
            )

        stored = nfib_sbet_regional_import.load_nfib_regional_observations(
            con, "pacific", "nfib_sbo_optimism"
        )
        assert stored == []
    finally:
        con.close()

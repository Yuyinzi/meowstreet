from pathlib import Path

import pytest

from app.db import macro_indicators
from app.services import nfib_sbet_import


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PDF = ROOT / "tests" / "fixtures" / "nfib_sbet_june_2026_real_layout.txt"
SOURCE_URL = "https://www.nfib.com/sbet/june-2026"


def test_import_cached_official_sbet_merges_provenance(tmp_path):
    con = macro_indicators.connect(tmp_path / "market.sqlite")
    try:
        count = nfib_sbet_import.import_cached_official_sbet(
            con, FIXTURE_PDF, SOURCE_URL, release_date="2026-07-14"
        )
        rows = macro_indicators.load_macro_indicator_observations_for_series(
            con, ["nfib_sbo_employment_plans", "nfib_sbo_optimism"]
        )
    finally:
        con.close()
    assert count > 0
    assert rows["nfib_sbo_employment_plans"][-1]["source_url"] == SOURCE_URL
    assert rows["nfib_sbo_optimism"][-1]["source_url"] == SOURCE_URL


def test_import_cached_official_sbet_stores_values(tmp_path):
    con = macro_indicators.connect(tmp_path / "market.sqlite")
    try:
        nfib_sbet_import.import_cached_official_sbet(
            con, FIXTURE_PDF, SOURCE_URL, release_date="2026-07-14"
        )
        employment = macro_indicators.load_macro_indicator_observations(
            con, "nfib_sbo_employment_plans"
        )
        optimism = macro_indicators.load_macro_indicator_observations(
            con, "nfib_sbo_optimism"
        )
    finally:
        con.close()
    assert employment[-1]["value"] == 11.0
    assert employment[-1]["date"] == "2026-06-30"
    assert optimism[-1]["value"] == 97.4
    assert optimism[-1]["date"] == "2026-06-30"


def test_import_cached_official_sbet_is_idempotent(tmp_path):
    con = macro_indicators.connect(tmp_path / "market.sqlite")
    try:
        nfib_sbet_import.import_cached_official_sbet(con, FIXTURE_PDF, SOURCE_URL)
        nfib_sbet_import.import_cached_official_sbet(con, FIXTURE_PDF, SOURCE_URL)
        optimism_rows = macro_indicators.load_macro_indicator_observations(
            con, "nfib_sbo_optimism"
        )
    finally:
        con.close()
    assert len(optimism_rows) == len({row["date"] for row in optimism_rows})


def test_import_cached_official_sbet_rejects_missing_path(tmp_path):
    import pytest

    con = macro_indicators.connect(tmp_path / "market.sqlite")
    try:
        with pytest.raises(ValueError, match="cache path does not exist"):
            nfib_sbet_import.import_cached_official_sbet(
                con, tmp_path / "nonexistent.pdf", SOURCE_URL
            )
    finally:
        con.close()


def test_import_stores_all_eleven_series(tmp_path):
    con = macro_indicators.connect(tmp_path / "market.sqlite")
    try:
        nfib_sbet_import.import_cached_official_sbet(con, FIXTURE_PDF, SOURCE_URL)
        all_series = macro_indicators.load_macro_indicator_series(con)
    finally:
        con.close()
    stored_ids = {s["series_id"] for s in all_series}
    assert stored_ids == macro_indicators._NFIB_SERIES_METADATA.keys()


def test_import_emits_all_context_series_observations(tmp_path):
    con = macro_indicators.connect(tmp_path / "market.sqlite")
    try:
        count = nfib_sbet_import.import_cached_official_sbet(
            con, FIXTURE_PDF, SOURCE_URL
        )
        job_openings = macro_indicators.load_macro_indicator_observations(
            con, "nfib_sbo_job_openings"
        )
    finally:
        con.close()
    assert len(job_openings) == 66
    assert job_openings[-1]["value"] == 32.0
    assert job_openings[-1]["date"] == "2026-06-30"


def test_import_rejects_conflicting_report_before_writing_observations(tmp_path):
    conflicting_path = tmp_path / "conflicting-report.txt"
    conflicting_path.write_text(
        FIXTURE_PDF.read_text().replace(
            "Plans to Increase Employment (net)   11%",
            "Plans to Increase Employment (net)   12%",
            1,
        )
    )
    con = macro_indicators.connect(tmp_path / "market.sqlite")
    try:
        with pytest.raises(ValueError, match="nfib report has conflicting values"):
            nfib_sbet_import.import_cached_official_sbet(
                con, conflicting_path, SOURCE_URL
            )
        employment = macro_indicators.load_macro_indicator_observations(
            con, "nfib_sbo_employment_plans"
        )
    finally:
        con.close()

    assert employment == []

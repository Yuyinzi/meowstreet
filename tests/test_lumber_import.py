import json

import pytest

from app.data_sources import lumber
from app.db import macro_indicators
from app.services import lumber_import

ARCHIVED_URL = "https://www.investing.com/commodities/lumber-historical-data"
ARCHIVED_RETRIEVED_AT = "2026-07-30T10:49:08.858071+00:00"
YAHOO_RETRIEVED_AT = "2026-07-31T00:00:00+00:00"


def archived_lumber_series():
    return {
        "series_id": "lumber",
        "title": "Lumber",
        "units": "USD/1,000 board feet",
        "source": "investing.com",
        "source_class": "free_web",
        "source_url": ARCHIVED_URL,
        "source_identifier": "lumber",
    }


def archived_observation(date_value, value):
    return {
        "date": date_value,
        "value": value,
        "source": "investing.com",
        "release_date": None,
        "publication_date_basis": None,
        "revision_status": None,
        "source_url": ARCHIVED_URL,
        "source_identifier": "lumber",
        "source_hash": None,
        "source_class": "free_web",
        "retrieved_at": ARCHIVED_RETRIEVED_AT,
    }


def archived_rows():
    return [
        archived_observation("2022-08-08", 621.0),
        archived_observation("2022-08-09", 625.0),
        archived_observation("2023-08-04", 500.0),
        archived_observation("2023-08-05", 505.0),
    ]


def yahoo_observation(date_value, value):
    return {
        "date": date_value,
        "value": value,
        "source": "yahoo_finance",
        "release_date": None,
        "publication_date_basis": None,
        "revision_status": None,
        "source_url": lumber.YAHOO_CHART_SOURCE_URL,
        "source_identifier": "LBR=F",
        "source_hash": None,
        "source_class": "vendor_free_market_data",
        "retrieved_at": YAHOO_RETRIEVED_AT,
    }


def yahoo_rows():
    return [
        yahoo_observation("2022-08-08", 621.0),
        yahoo_observation("2022-08-09", 625.0),
        yahoo_observation("2023-08-04", 500.0),
    ]


def expected_yahoo_rows():
    return yahoo_rows()


def changed_yahoo_rows():
    return [
        yahoo_observation("2022-08-08", 621.0),
        yahoo_observation("2022-08-09", 626.0),
        yahoo_observation("2023-08-04", 500.0),
    ]


def yahoo_payload(observations):
    return {"series": lumber._LUMBER_SERIES, "observations": observations}


def fake_yahoo_fetcher(start_date, end_date):
    return yahoo_payload(expected_yahoo_rows())


def test_initial_lbr_import_backfills_from_contract_start_and_preserves_archive(
    tmp_path,
):
    con = macro_indicators.connect(tmp_path / "market.sqlite")
    macro_indicators.merge_macro_indicator_observations(
        con, archived_lumber_series(), archived_rows()
    )
    audit_path = tmp_path / "lumber_overlap_v1.json"
    result = lumber_import.refresh_lumber(
        con,
        today_date="2026-07-31",
        fetcher=fake_yahoo_fetcher,
        audit_path=audit_path,
    )
    assert result["start_date"] == "2022-08-08"
    assert (
        macro_indicators.load_macro_indicator_observations(con, "lumber")
        == archived_rows()
    )
    assert (
        macro_indicators.load_macro_indicator_observations(
            con, "lumber_cme_lbr_yahoo_v1"
        )
        == expected_yahoo_rows()
    )
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    assert audit["overlap_test_version"] == "lumber_overlap_v1"
    assert audit["shared_date_count"] == 3
    assert audit["shared_price_difference_max"] == 0.0


def test_incremental_lbr_import_uses_fourteen_calendar_day_overlap(tmp_path):
    con = macro_indicators.connect(tmp_path / "market.sqlite")
    macro_indicators.merge_macro_indicator_observations(
        con, lumber._LUMBER_SERIES, [yahoo_observation("2026-07-29", 634.0)]
    )
    calls = []

    def fetcher(start_date, end_date):
        calls.append((start_date, end_date))
        return yahoo_payload([yahoo_observation("2026-07-30", 631.0)])

    lumber_import.refresh_lumber(con, today_date="2026-07-31", fetcher=fetcher)
    assert calls == [("2026-07-16", "2026-08-01")]


def test_failed_lbr_import_rolls_back_without_investing_fallback(tmp_path):
    con = macro_indicators.connect(tmp_path / "market.sqlite")
    macro_indicators.merge_macro_indicator_observations(
        con, archived_lumber_series(), archived_rows()
    )

    def raising_fetcher(start_date, end_date):
        raise ValueError("yahoo unavailable")

    with pytest.raises(ValueError, match="yahoo unavailable"):
        lumber_import.refresh_lumber(con, fetcher=raising_fetcher)
    assert (
        macro_indicators.load_macro_indicator_points(con, "lumber_cme_lbr_yahoo_v1")
        == []
    )


def test_failed_lbr_import_does_not_persist_overlap_audit(tmp_path):
    con = macro_indicators.connect(tmp_path / "market.sqlite")
    macro_indicators.merge_macro_indicator_observations(
        con, archived_lumber_series(), archived_rows()
    )
    audit_path = tmp_path / "lumber_overlap_v1.json"

    def raising_fetcher(start_date, end_date):
        raise ValueError("yahoo unavailable")

    with pytest.raises(ValueError, match="yahoo unavailable"):
        lumber_import.refresh_lumber(
            con, fetcher=raising_fetcher, audit_path=audit_path
        )
    assert not audit_path.exists()


def test_merge_failure_leaves_no_audit_or_active_rows(tmp_path):
    con = macro_indicators.connect(tmp_path / "market.sqlite")
    macro_indicators.merge_macro_indicator_observations(
        con, archived_lumber_series(), archived_rows()
    )
    audit_path = tmp_path / "lumber_overlap_v1.json"

    def bad_contract_fetcher(start_date, end_date):
        payload = yahoo_payload(expected_yahoo_rows())
        payload["series"] = dict(payload["series"], source_contract={})
        return payload

    with pytest.raises(
        ValueError, match="series source contract is required to be a non-empty dict"
    ):
        lumber_import.refresh_lumber(
            con,
            today_date="2026-07-31",
            fetcher=bad_contract_fetcher,
            audit_path=audit_path,
        )
    assert not audit_path.exists()
    assert (
        macro_indicators.load_macro_indicator_points(con, "lumber_cme_lbr_yahoo_v1")
        == []
    )


class _FailingCommitCon:
    def __init__(self, con):
        self._con = con

    def __getattr__(self, name):
        return getattr(self._con, name)

    def commit(self):
        raise ValueError("sqlite commit failed")


def test_commit_failure_leaves_no_audit_or_active_rows(tmp_path):
    con = macro_indicators.connect(tmp_path / "market.sqlite")
    macro_indicators.merge_macro_indicator_observations(
        con, archived_lumber_series(), archived_rows()
    )
    audit_path = tmp_path / "lumber_overlap_v1.json"

    with pytest.raises(ValueError, match="sqlite commit failed"):
        lumber_import.refresh_lumber(
            _FailingCommitCon(con),
            today_date="2026-07-31",
            fetcher=fake_yahoo_fetcher,
            audit_path=audit_path,
        )
    assert not audit_path.exists()
    assert (
        macro_indicators.load_macro_indicator_points(con, "lumber_cme_lbr_yahoo_v1")
        == []
    )


def test_overlap_audit_excludes_investing_only_saturday_and_detects_unequal_shared_close():
    audit = lumber_import.audit_lumber_overlap(archived_rows(), yahoo_rows())
    assert audit["archived_only_dates"] == ["2023-08-05"]
    with pytest.raises(ValueError, match="prices differ on 2022-08-09"):
        lumber_import.audit_lumber_overlap(archived_rows(), changed_yahoo_rows())


def test_overlap_audit_reports_shared_counts_and_difference_bounds():
    audit = lumber_import.audit_lumber_overlap(archived_rows(), yahoo_rows())
    assert audit["overlap_test_version"] == "lumber_overlap_v1"
    assert audit["shared_date_count"] == 3
    assert audit["archived_only_count"] == 1
    assert audit["yahoo_only_count"] == 0
    assert audit["shared_price_difference_min"] == 0.0
    assert audit["shared_price_difference_max"] == 0.0
    assert audit["shared_return_difference_min"] == 0.0
    assert audit["shared_return_difference_max"] == 0.0


def test_overlap_audit_raises_without_shared_dates():
    with pytest.raises(ValueError, match="no shared dates"):
        lumber_import.audit_lumber_overlap(
            [archived_observation("2022-08-08", 621.0)],
            [yahoo_observation("2023-08-04", 500.0)],
        )


def test_import_cli_prints_only_summary_fields(monkeypatch, capsys, tmp_path):
    from scripts import import_lumber

    monkeypatch.setattr(
        lumber_import,
        "refresh_lumber",
        lambda con, today_date=None, initial=False, audit_path=None: {
            "series": "lumber_cme_lbr_yahoo_v1",
            "observations": 3,
            "start_date": "2022-08-08",
            "end_date": "2026-08-01",
        },
    )
    exit_code = import_lumber.main(
        ["--db-path", str(tmp_path / "market.sqlite"), "--today-date", "2026-07-31"]
    )
    out = capsys.readouterr().out
    assert exit_code == 0
    assert out == (
        "series: lumber_cme_lbr_yahoo_v1, observations: 3, "
        "start_date: 2022-08-08, end_date: 2026-08-01\n"
    )


def test_import_cli_reports_errors_without_traceback(monkeypatch, capsys, tmp_path):
    from scripts import import_lumber

    def raising_refresh(con, today_date=None, initial=False, audit_path=None):
        raise ValueError("yahoo unavailable")

    monkeypatch.setattr(lumber_import, "refresh_lumber", raising_refresh)
    exit_code = import_lumber.main(
        ["--db-path", str(tmp_path / "market.sqlite"), "--today-date", "2026-07-31"]
    )
    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert captured.err == " lumber import error: yahoo unavailable\n"


def test_audit_cli_writes_no_audit_file_on_audit_failure(monkeypatch, capsys, tmp_path):
    from scripts import audit_lumber_overlap

    monkeypatch.setattr(
        macro_indicators,
        "load_macro_indicator_observations",
        lambda con, series_id: [],
    )

    def raising_fetch(start_date, end_date):
        raise ValueError("close data is missing for LBR=F")

    monkeypatch.setattr(
        audit_lumber_overlap, "fetch_lumber_series", raising_fetch
    )
    out_path = tmp_path / "lumber_overlap_v1.json"
    exit_code = audit_lumber_overlap.main(
        [
            "--db-path",
            str(tmp_path / "market.sqlite"),
            "--today-date",
            "2026-07-31",
            "--out-path",
            str(out_path),
        ]
    )
    captured = capsys.readouterr()
    assert exit_code == 1
    assert "audit failed" in captured.err
    assert not out_path.exists()

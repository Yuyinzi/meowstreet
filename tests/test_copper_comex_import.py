from datetime import date, timedelta

import pytest

from app.data_sources import copper_comex
from app.db import macro_indicators
from app.services import copper_comex_import

ARCHIVED_URL = "https://www.investing.com/commodities/copper-historical-data"
ARCHIVED_RETRIEVED_AT = "2026-07-30T10:49:08.858071+00:00"
YAHOO_RETRIEVED_AT = "2026-08-01T00:00:00+00:00"


def archived_copper_series():
    return {
        "series_id": "copper_comex",
        "title": "Copper (COMEX)",
        "units": "USD/lb",
        "source": "investing.com",
        "source_class": "free_web",
        "source_url": ARCHIVED_URL,
        "source_identifier": "copper_comex",
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
        "source_identifier": "copper_comex",
        "source_hash": None,
        "source_class": "free_web",
        "retrieved_at": ARCHIVED_RETRIEVED_AT,
    }


def yahoo_observation(date_value, value):
    return {
        "date": date_value,
        "value": value,
        "source": "yahoo_finance",
        "release_date": None,
        "publication_date_basis": None,
        "revision_status": None,
        "source_url": copper_comex.YAHOO_CHART_SOURCE_URL,
        "source_identifier": "HG=F",
        "source_hash": None,
        "source_class": "vendor_free_market_data",
        "retrieved_at": YAHOO_RETRIEVED_AT,
    }


def yahoo_payload(observations):
    return {
        "series": copper_comex._COPPER_COMEX_SERIES,
        "observations": observations,
    }


def _weekdays(start_date, count):
    days = []
    current = date.fromisoformat(start_date)
    while len(days) < count:
        if current.weekday() < 5:
            days.append(current.isoformat())
        current += timedelta(days=1)
    return days


def shared_dates():
    return _weekdays("2022-01-03", 62)


def archived_rows():
    rows = [
        archived_observation(day, 3.8 + index * 0.001)
        for index, day in enumerate(shared_dates())
    ]
    rows.append(archived_observation("2022-04-01", 3.9))
    return rows


def passing_yahoo_rows():
    rows = [
        yahoo_observation(day, 3.8 + index * 0.001)
        for index, day in enumerate(shared_dates())
    ]
    rows.append(yahoo_observation("2022-04-04", 3.9))
    return rows


def insufficient_shared_yahoo_rows():
    return [
        yahoo_observation(day, 3.8 + index * 0.001)
        for index, day in enumerate(shared_dates()[:10])
    ]


def zero_variance_yahoo_rows():
    return [yahoo_observation(day, 4.0) for day in shared_dates()]


def low_price_correlation_yahoo_rows():
    count = len(shared_dates())
    return [
        yahoo_observation(day, 3.8 + (count - 1 - index) * 0.001)
        for index, day in enumerate(shared_dates())
    ]


def low_return_correlation_yahoo_rows():
    return [
        yahoo_observation(day, 3.8 + index * 0.001 + (0.5 if index % 2 else -0.5))
        for index, day in enumerate(shared_dates())
    ]


def high_return_difference_yahoo_rows():
    rows = []
    for index, day in enumerate(shared_dates()):
        value = 3.8 + index * 0.001
        if index in (5, 15, 25, 35, 45):
            value += 0.2
        rows.append(yahoo_observation(day, value))
    return rows


def passing_yahoo_fetcher(start_date, end_date):
    return yahoo_payload(passing_yahoo_rows())


def test_initial_copper_import_audits_and_preserves_archive(tmp_path):
    con = macro_indicators.connect(tmp_path / "market.sqlite")
    macro_indicators.merge_macro_indicator_observations(
        con, archived_copper_series(), archived_rows()
    )
    result = copper_comex_import.refresh_copper_comex(
        con, today_date="2026-08-01", fetcher=passing_yahoo_fetcher, initial=True
    )
    assert result["start_date"] == "2000-08-30"
    assert (
        macro_indicators.load_macro_indicator_observations(con, "copper_comex")
        == archived_rows()
    )
    assert (
        macro_indicators.load_vendor_series_overlap_audit(
            con, "copper_comex_hg_yahoo_v1", "copper_comex_hg_overlap_v1"
        )["passed"]
        is True
    )


def test_initial_copper_import_persists_yahoo_rows(tmp_path):
    con = macro_indicators.connect(tmp_path / "market.sqlite")
    macro_indicators.merge_macro_indicator_observations(
        con, archived_copper_series(), archived_rows()
    )
    copper_comex_import.refresh_copper_comex(
        con, today_date="2026-08-01", fetcher=passing_yahoo_fetcher, initial=True
    )
    assert (
        macro_indicators.load_macro_indicator_observations(
            con, "copper_comex_hg_yahoo_v1"
        )
        == passing_yahoo_rows()
    )


def test_incremental_copper_import_uses_fourteen_calendar_day_overlap(tmp_path):
    con = macro_indicators.connect(tmp_path / "market.sqlite")
    macro_indicators.merge_macro_indicator_observations(
        con,
        copper_comex._COPPER_COMEX_SERIES,
        [yahoo_observation("2026-07-29", 3.9)],
    )
    calls = []

    def fetcher(start_date, end_date):
        calls.append((start_date, end_date))
        return yahoo_payload([yahoo_observation("2026-07-30", 3.91)])

    copper_comex_import.refresh_copper_comex(
        con, today_date="2026-07-31", fetcher=fetcher
    )
    assert calls == [("2026-07-16", "2026-08-01")]


def test_copper_overlap_audit_records_full_diagnostics():
    audit = copper_comex_import.audit_copper_comex_overlap(
        archived_rows(), passing_yahoo_rows()
    )
    assert audit["overlap_test_version"] == "copper_comex_hg_overlap_v1"
    assert audit["shared_date_count"] == 62
    assert audit["archived_only_dates"] == ["2022-04-01"]
    assert audit["yahoo_only_dates"] == ["2022-04-04"]
    assert audit["price_correlation"] >= 0.99
    assert audit["return_correlation"] >= 0.95
    assert audit["shared_return_difference_p95"] <= 0.01
    assert audit["passed"] is True


@pytest.mark.parametrize(
    "yahoo_rows_builder",
    [
        pytest.param(insufficient_shared_yahoo_rows, id="insufficient_shared_dates"),
        pytest.param(zero_variance_yahoo_rows, id="zero_variance"),
        pytest.param(low_price_correlation_yahoo_rows, id="low_price_correlation"),
        pytest.param(low_return_correlation_yahoo_rows, id="low_return_correlation"),
        pytest.param(high_return_difference_yahoo_rows, id="high_return_difference"),
    ],
)
def test_copper_overlap_audit_rejects_failing_thresholds(yahoo_rows_builder):
    with pytest.raises(ValueError, match="copper comex overlap audit failed"):
        copper_comex_import.audit_copper_comex_overlap(
            archived_rows(), yahoo_rows_builder()
        )


def test_failed_copper_import_rolls_back_without_writes(tmp_path):
    con = macro_indicators.connect(tmp_path / "market.sqlite")
    macro_indicators.merge_macro_indicator_observations(
        con, archived_copper_series(), archived_rows()
    )

    def raising_fetcher(start_date, end_date):
        raise ValueError("yahoo unavailable")

    with pytest.raises(ValueError, match="yahoo unavailable"):
        copper_comex_import.refresh_copper_comex(
            con,
            today_date="2026-08-01",
            fetcher=raising_fetcher,
            initial=True,
        )
    assert (
        macro_indicators.load_macro_indicator_points(
            con, "copper_comex_hg_yahoo_v1"
        )
        == []
    )
    assert (
        macro_indicators.load_vendor_series_overlap_audit(
            con, "copper_comex_hg_yahoo_v1", "copper_comex_hg_overlap_v1"
        )
        is None
    )


def test_failed_copper_audit_leaves_no_audit_or_active_rows(tmp_path):
    con = macro_indicators.connect(tmp_path / "market.sqlite")
    macro_indicators.merge_macro_indicator_observations(
        con, archived_copper_series(), archived_rows()
    )

    def failing_fetcher(start_date, end_date):
        return yahoo_payload(insufficient_shared_yahoo_rows())

    with pytest.raises(ValueError, match="copper comex overlap audit failed"):
        copper_comex_import.refresh_copper_comex(
            con,
            today_date="2026-08-01",
            fetcher=failing_fetcher,
            initial=True,
        )
    assert (
        macro_indicators.load_macro_indicator_points(
            con, "copper_comex_hg_yahoo_v1"
        )
        == []
    )
    assert (
        macro_indicators.load_vendor_series_overlap_audit(
            con, "copper_comex_hg_yahoo_v1", "copper_comex_hg_overlap_v1"
        )
        is None
    )


def test_initial_copper_import_rejects_overwriting_recorded_overlap_audit(tmp_path):
    con = macro_indicators.connect(tmp_path / "market.sqlite")
    macro_indicators.merge_macro_indicator_observations(
        con, archived_copper_series(), archived_rows()
    )
    copper_comex_import.refresh_copper_comex(
        con, today_date="2026-08-01", fetcher=passing_yahoo_fetcher, initial=True
    )

    with pytest.raises(
        ValueError, match="copper comex initial migration is already recorded"
    ):
        copper_comex_import.refresh_copper_comex(
            con,
            today_date="2026-08-01",
            fetcher=passing_yahoo_fetcher,
            initial=True,
        )


def test_import_cli_forwards_initial_flag(monkeypatch, tmp_path):
    from scripts import import_copper_comex

    captured = {}

    def fake_refresh(con, today_date=None, fetcher=None, initial=False):
        captured["today_date"] = today_date
        captured["initial"] = initial
        return {
            "series": "copper_comex_hg_yahoo_v1",
            "observations": 3,
            "start_date": "2000-08-30",
            "end_date": "2026-08-02",
        }

    monkeypatch.setattr(
        copper_comex_import, "refresh_copper_comex", fake_refresh
    )
    exit_code = import_copper_comex.main(
        [
            "--db-path",
            str(tmp_path / "market.sqlite"),
            "--today-date",
            "2026-08-01",
            "--initial",
        ]
    )
    assert exit_code == 0
    assert captured == {"today_date": "2026-08-01", "initial": True}


def test_import_cli_reports_errors_without_traceback(monkeypatch, capsys, tmp_path):
    from scripts import import_copper_comex

    def raising_refresh(con, today_date=None, fetcher=None, initial=False):
        raise ValueError("yahoo unavailable")

    monkeypatch.setattr(
        copper_comex_import, "refresh_copper_comex", raising_refresh
    )
    exit_code = import_copper_comex.main(
        ["--db-path", str(tmp_path / "market.sqlite"), "--today-date", "2026-08-01"]
    )
    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert captured.err == " copper comex import error: yahoo unavailable\n"


def test_audit_cli_writes_json_export_and_no_db_rows(monkeypatch, tmp_path):
    from scripts import audit_copper_comex_overlap

    monkeypatch.setattr(
        macro_indicators,
        "load_macro_indicator_observations",
        lambda con, series_id: archived_rows(),
    )
    monkeypatch.setattr(
        audit_copper_comex_overlap,
        "fetch_copper_comex_series",
        lambda start_date, end_date: yahoo_payload(passing_yahoo_rows()),
    )
    out_path = tmp_path / "copper_comex_hg_overlap_v1.json"
    exit_code = audit_copper_comex_overlap.main(
        [
            "--db-path",
            str(tmp_path / "market.sqlite"),
            "--today-date",
            "2026-08-01",
            "--out-path",
            str(out_path),
        ]
    )
    assert exit_code == 0
    import json

    export = json.loads(out_path.read_text())
    assert export["overlap_test_version"] == "copper_comex_hg_overlap_v1"
    assert export["passed"] is True


def test_audit_cli_writes_no_json_on_audit_failure(monkeypatch, capsys, tmp_path):
    from scripts import audit_copper_comex_overlap

    monkeypatch.setattr(
        macro_indicators,
        "load_macro_indicator_observations",
        lambda con, series_id: archived_rows(),
    )
    monkeypatch.setattr(
        audit_copper_comex_overlap,
        "fetch_copper_comex_series",
        lambda start_date, end_date: yahoo_payload(insufficient_shared_yahoo_rows()),
    )
    out_path = tmp_path / "copper_comex_hg_overlap_v1.json"
    exit_code = audit_copper_comex_overlap.main(
        [
            "--db-path",
            str(tmp_path / "market.sqlite"),
            "--today-date",
            "2026-08-01",
            "--out-path",
            str(out_path),
        ]
    )
    captured = capsys.readouterr()
    assert exit_code == 1
    assert "audit failed" in captured.err
    assert not out_path.exists()

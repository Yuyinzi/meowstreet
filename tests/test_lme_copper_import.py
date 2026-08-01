import pytest

from app.data_sources import lme_copper
from app.db import macro_indicators
from app.services import lme_copper_import

ARCHIVED_URL = "https://www.investing.com/commodities/copper-historical-data?cid=959211"
ARCHIVED_RETRIEVED_AT = "2026-07-30T10:49:08.858071+00:00"
CAD_RETRIEVED_AT = "2026-08-01T00:00:00+00:00"


def archived_lme_series():
    return {
        "series_id": "copper_lme",
        "title": "Copper (LME)",
        "units": "USD/tonne",
        "source": "investing.com",
        "source_class": "free_web",
        "source_url": ARCHIVED_URL,
        "source_identifier": "copper_lme",
    }


def archived_row(date_value, value):
    return {
        "date": date_value,
        "value": value,
        "source": "investing.com",
        "release_date": None,
        "publication_date_basis": None,
        "revision_status": None,
        "source_url": ARCHIVED_URL,
        "source_identifier": "copper_lme",
        "source_hash": None,
        "source_class": "free_web",
        "retrieved_at": ARCHIVED_RETRIEVED_AT,
        "access_adapter_version": None,
    }


def cad_series():
    return lme_copper._LME_COPPER_SERIES


def cad_row(date_value, value):
    return {
        "date": date_value,
        "value": value,
        "source": "sina_finance",
        "release_date": None,
        "publication_date_basis": None,
        "revision_status": None,
        "source_url": lme_copper.SINA_CAD_DAILY_URL,
        "source_identifier": "CAD",
        "source_hash": None,
        "source_class": "vendor_free_market_data",
        "retrieved_at": CAD_RETRIEVED_AT,
        "access_adapter_version": "1.18.81",
    }


def cad_payload(observations):
    return {"series": cad_series(), "observations": observations}


def cad_fetcher(start_date, end_date):
    return cad_payload([cad_row("2026-07-31", 13803.0), cad_row("2026-08-02", 13810.0)])


def test_initial_import_preserves_archive_and_persists_only_post_cutover_cad(tmp_path):
    con = macro_indicators.connect(tmp_path / "market.sqlite")
    macro_indicators.merge_macro_indicator_observations(
        con, archived_lme_series(), [archived_row("2026-07-30", 13745.72)]
    )
    result = lme_copper_import.refresh_lme_copper(
        con, today_date="2026-08-01", fetcher=cad_fetcher, initial=True
    )
    assert result == {
        "series": "copper_lme_sina_cad_v1",
        "observations": 1,
        "start_date": "2026-07-31",
        "end_date": "2026-08-02",
    }
    assert macro_indicators.load_macro_indicator_observations(
        con, "copper_lme"
    ) == [archived_row("2026-07-30", 13745.72)]
    assert [
        row["date"]
        for row in macro_indicators.load_macro_indicator_observations(
            con, "copper_lme_sina_cad_v1"
        )
    ] == ["2026-07-31"]


def test_incremental_import_uses_fourteen_calendar_day_overlap(tmp_path):
    con = macro_indicators.connect(tmp_path / "market.sqlite")
    macro_indicators.merge_macro_indicator_observations(
        con, cad_series(), [cad_row("2026-08-14", 13803.0)]
    )
    calls = []
    lme_copper_import.refresh_lme_copper(
        con,
        today_date="2026-08-15",
        fetcher=lambda start, end: (
            calls.append((start, end)) or cad_payload([cad_row("2026-08-15", 13810.0)])
        ),
    )
    assert calls == [("2026-07-31", "2026-08-16")]


def test_initial_import_cannot_run_twice(tmp_path):
    con = macro_indicators.connect(tmp_path / "market.sqlite")
    macro_indicators.merge_macro_indicator_observations(
        con, archived_lme_series(), [archived_row("2026-07-30", 13745.72)]
    )
    lme_copper_import.refresh_lme_copper(
        con, today_date="2026-08-01", fetcher=cad_fetcher, initial=True
    )
    with pytest.raises(
        ValueError, match="sina CAD initial migration is already recorded"
    ):
        lme_copper_import.refresh_lme_copper(
            con, today_date="2026-08-01", fetcher=cad_fetcher, initial=True
        )


def test_failed_fetch_leaves_no_active_or_audit_rows_and_keeps_archive(tmp_path):
    con = macro_indicators.connect(tmp_path / "market.sqlite")
    macro_indicators.merge_macro_indicator_observations(
        con, archived_lme_series(), [archived_row("2026-07-30", 13745.72)]
    )

    def raising_fetcher(start_date, end_date):
        raise ValueError("sina unavailable")

    with pytest.raises(ValueError, match="sina unavailable"):
        lme_copper_import.refresh_lme_copper(
            con, today_date="2026-08-01", fetcher=raising_fetcher, initial=True
        )
    assert (
        macro_indicators.load_macro_indicator_points(con, "copper_lme_sina_cad_v1")
        == []
    )
    assert (
        macro_indicators.load_vendor_series_overlap_audit(
            con, "copper_lme_sina_cad_v1", "lme_copper_cad_overlap_v1"
        )
        is None
    )
    assert macro_indicators.load_macro_indicator_observations(
        con, "copper_lme"
    ) == [archived_row("2026-07-30", 13745.72)]


def test_refresh_rolls_back_when_source_has_no_valid_observations(tmp_path):
    con = macro_indicators.connect(tmp_path / "market.sqlite")
    macro_indicators.merge_macro_indicator_observations(
        con, cad_series(), [cad_row("2026-08-14", 13803.0)]
    )
    with pytest.raises(ValueError, match="sina CAD returned no valid"):
        lme_copper_import.refresh_lme_copper(
            con,
            today_date="2026-08-15",
            fetcher=lambda start, end: cad_payload([]),
        )
    loaded = macro_indicators.load_macro_indicator_observations(
        con, "copper_lme_sina_cad_v1"
    )
    assert [row["date"] for row in loaded] == ["2026-08-14"]


def test_audit_reports_descriptive_overlap_without_requiring_parity():
    audit = lme_copper_import.audit_lme_copper_overlap(
        [
            archived_row("2026-07-28", 13700.0),
            archived_row("2026-07-29", 13730.0),
            archived_row("2026-07-30", 13745.72),
        ],
        [
            cad_row("2026-07-30", 13800.0),
            cad_row("2026-07-31", 13803.0),
        ],
    )
    assert audit["overlap_test_version"] == "lme_copper_cad_overlap_v1"
    assert audit["archived_count"] == 3
    assert audit["cad_count"] == 2
    assert audit["shared_date_count"] == 1
    assert audit["shared_dates"] == ["2026-07-30"]
    assert audit["archived_only_dates"] == ["2026-07-28", "2026-07-29"]
    assert audit["cad_only_dates"] == ["2026-07-31"]
    assert audit["mean_absolute_difference"] == pytest.approx(54.28)
    assert audit["max_absolute_difference"] == pytest.approx(54.28)
    assert audit["shared_price_percent_difference_max"] == pytest.approx(
        54.28 / 13745.72
    )
    assert audit["price_correlation"] is None
    assert audit["return_correlation"] is None
    assert audit["price_parity"] is False


def test_audit_computes_correlations_when_shared_history_exists():
    shared_days = ["2026-07-24", "2026-07-27", "2026-07-28", "2026-07-29", "2026-07-30"]
    archive = [
        archived_row(day, 13700.0 + index) for index, day in enumerate(shared_days)
    ]
    cad = [cad_row(day, 13701.0 + index) for index, day in enumerate(shared_days)]
    audit = lme_copper_import.audit_lme_copper_overlap(archive, cad)
    assert audit["shared_date_count"] == 5
    assert audit["price_correlation"] is not None
    assert audit["return_correlation"] is not None
    assert audit["price_parity"] is False


def test_audit_handles_single_shared_date_without_divide_by_zero():
    audit = lme_copper_import.audit_lme_copper_overlap(
        [archived_row("2026-07-30", 13745.72)],
        [cad_row("2026-07-30", 13803.0), cad_row("2026-07-31", 13810.0)],
    )
    assert audit["shared_date_count"] == 1
    assert audit["price_correlation"] is None
    assert audit["return_correlation"] is None


def test_audit_handles_no_shared_dates_without_divide_by_zero():
    audit = lme_copper_import.audit_lme_copper_overlap(
        [archived_row("2026-07-29", 13730.0)],
        [cad_row("2026-07-31", 13803.0)],
    )
    assert audit["shared_date_count"] == 0
    assert audit["mean_absolute_difference"] is None
    assert audit["price_correlation"] is None
    assert audit["return_correlation"] is None
    assert audit["price_parity"] is False


def test_import_cli_forwards_initial_flag_and_prints_result(
    monkeypatch, tmp_path, capsys
):
    from scripts import import_lme_copper

    captured = {}

    def fake_refresh(con, today_date=None, fetcher=None, initial=False):
        captured["today_date"] = today_date
        captured["initial"] = initial
        return {
            "series": "copper_lme_sina_cad_v1",
            "observations": 1,
            "start_date": "2026-07-31",
            "end_date": "2026-08-02",
        }

    monkeypatch.setattr(lme_copper_import, "refresh_lme_copper", fake_refresh)
    exit_code = import_lme_copper.main(
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
    out = capsys.readouterr().out
    assert "series: copper_lme_sina_cad_v1" in out
    assert "observations: 1" in out
    assert "start_date: 2026-07-31" in out
    assert "end_date: 2026-08-02" in out


def test_import_cli_reports_errors_without_traceback(monkeypatch, capsys, tmp_path):
    from scripts import import_lme_copper

    def raising_refresh(con, today_date=None, fetcher=None, initial=False):
        raise ValueError("sina unavailable")

    monkeypatch.setattr(
        lme_copper_import, "refresh_lme_copper", raising_refresh
    )
    exit_code = import_lme_copper.main(
        ["--db-path", str(tmp_path / "market.sqlite"), "--today-date", "2026-08-01"]
    )
    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert captured.err == " lme copper import error: sina unavailable\n"

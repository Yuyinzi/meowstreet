import sqlite3

import pytest

from app.db import economic_confirmation


def release_vintage():
    return {
        "series_id": "initial_claims_sa",
        "reference_period": "2026-06-01",
        "vintage_id": "initial_claims_sa:2026-06-01:2026-06-05",
        "release_date": "2026-06-05",
        "as_of_timestamp": "2026-06-05T08:30:00+00:00",
        "value_at_release": 180000,
        "latest_revised_value": None,
        "revision_number": 0,
        "seasonal_adjustment": "seasonally_adjusted",
        "source_url": "https://oui.doleta.gov/unemploy/pdf/claims.pdf",
        "source_hash": "hash-release",
    }


def revision_vintage():
    return {
        "series_id": "initial_claims_sa",
        "reference_period": "2026-06-01",
        "vintage_id": "initial_claims_sa:2026-06-01:2026-06-12",
        "release_date": "2026-06-12",
        "as_of_timestamp": "2026-06-12T08:30:00+00:00",
        "value_at_release": 175000,
        "latest_revised_value": 175000,
        "revision_number": 1,
        "seasonal_adjustment": "seasonally_adjusted",
        "source_url": "https://oui.doleta.gov/unemploy/pdf/claims.pdf",
        "source_hash": "hash-revision",
    }


def history_vintage():
    return {
        "series_id": "initial_claims_sa",
        "reference_period": "2026-07-25",
        "vintage_id": "history:initial_claims_sa:2026-07-25:2026-07-30",
        "release_date": None,
        "as_of_timestamp": "2026-07-30T12:00:00+00:00",
        "value_at_release": 197000,
        "latest_revised_value": None,
        "revision_number": 0,
        "seasonal_adjustment": "seasonally_adjusted",
        "source_url": "https://oui.doleta.gov/unemploy/Chartbook/createdf.php",
        "source_hash": "hash-history",
    }


def release_day_vintage():
    return {
        "series_id": "initial_claims_sa",
        "reference_period": "2026-07-25",
        "vintage_id": "release:initial_claims_sa:2026-07-25:2026-07-30",
        "release_date": "2026-07-30",
        "as_of_timestamp": "2026-07-30T08:30:00+00:00",
        "value_at_release": 197000,
        "latest_revised_value": None,
        "revision_number": 0,
        "seasonal_adjustment": "seasonally_adjusted",
        "source_url": "https://www.dol.gov/ui/data.pdf",
        "source_hash": "hash-release",
    }


def test_vintage_read_excludes_future_revision(tmp_path):
    con = economic_confirmation.connect(tmp_path / "market.sqlite")
    economic_confirmation.record_vintage_batch(
        con, [release_vintage(), revision_vintage()]
    )
    result = economic_confirmation.load_series_as_of(
        con, ["initial_claims_sa"], "2026-06-05T12:00:00Z"
    )
    assert result["initial_claims_sa"][0]["value"] == 180000
    assert result["initial_claims_sa"][0]["revision_number"] == 0


def test_record_vintage_batch_updates_current_series_to_latest_vintage(tmp_path):
    con = economic_confirmation.connect(tmp_path / "market.sqlite")
    economic_confirmation.record_vintage_batch(
        con, [release_vintage(), revision_vintage()]
    )
    result = economic_confirmation.load_current_series(con, ["initial_claims_sa"])
    assert result["initial_claims_sa"][0]["value"] == 175000
    assert result["initial_claims_sa"][0]["revision_number"] == 1
    assert result["initial_claims_sa"][0]["vintage_id"] == (
        "initial_claims_sa:2026-06-01:2026-06-12"
    )


def test_load_series_as_of_returns_latest_vintage_per_reference_period(tmp_path):
    con = economic_confirmation.connect(tmp_path / "market.sqlite")
    later_period = dict(release_vintage())
    later_period["reference_period"] = "2026-06-08"
    later_period["vintage_id"] = "initial_claims_sa:2026-06-08:2026-06-12"
    later_period["value_at_release"] = 170000
    later_period["source_hash"] = "hash-later"
    economic_confirmation.record_vintage_batch(
        con, [release_vintage(), revision_vintage(), later_period]
    )
    result = economic_confirmation.load_series_as_of(
        con, ["initial_claims_sa"], "2026-06-13T12:00:00Z"
    )
    assert [row["reference_period"] for row in result["initial_claims_sa"]] == [
        "2026-06-01",
        "2026-06-08",
    ]
    assert result["initial_claims_sa"][0]["value"] == 175000
    assert result["initial_claims_sa"][1]["value"] == 170000


def test_load_current_series_returns_empty_list_for_unknown_series(tmp_path):
    con = economic_confirmation.connect(tmp_path / "market.sqlite")
    result = economic_confirmation.load_current_series(con, ["initial_claims_sa"])
    assert result["initial_claims_sa"] == []


def test_load_series_as_of_returns_empty_list_for_unknown_series(tmp_path):
    con = economic_confirmation.connect(tmp_path / "market.sqlite")
    result = economic_confirmation.load_series_as_of(
        con, ["continuing_claims_sa"], "2026-06-05T12:00:00Z"
    )
    assert result["continuing_claims_sa"] == []


def test_record_vintage_batch_rejects_conflicting_duplicate_hash(tmp_path):
    con = economic_confirmation.connect(tmp_path / "market.sqlite")
    economic_confirmation.record_vintage_batch(con, [release_vintage()])
    conflicting = dict(release_vintage())
    conflicting["source_hash"] = "different-hash"
    with pytest.raises(ValueError, match="conflicting duplicate"):
        economic_confirmation.record_vintage_batch(con, [conflicting])


def test_record_vintage_batch_ignores_identical_duplicate(tmp_path):
    con = economic_confirmation.connect(tmp_path / "market.sqlite")
    count = economic_confirmation.record_vintage_batch(
        con, [release_vintage(), release_vintage()]
    )
    assert count == 1
    result = economic_confirmation.load_current_series(con, ["initial_claims_sa"])
    assert len(result["initial_claims_sa"]) == 1


def test_record_vintage_batch_accepts_history_and_release_on_same_day(tmp_path):
    con = economic_confirmation.connect(tmp_path / "market.sqlite")
    count = economic_confirmation.record_vintage_batch(
        con, [history_vintage(), release_day_vintage()]
    )
    assert count == 2
    vintage_ids = {
        row["vintage_id"]
        for row in con.execute(
            "select vintage_id from economic_confirmation_vintages "
            "where series_id = 'initial_claims_sa'"
        ).fetchall()
    }
    assert vintage_ids == {
        "history:initial_claims_sa:2026-07-25:2026-07-30",
        "release:initial_claims_sa:2026-07-25:2026-07-30",
    }


def test_record_vintage_batch_rejects_non_seasonally_adjusted_claims(tmp_path):
    con = economic_confirmation.connect(tmp_path / "market.sqlite")
    for series_id in ["initial_claims_sa", "continuing_claims_sa"]:
        observation = dict(release_vintage())
        observation["series_id"] = series_id
        observation["seasonal_adjustment"] = "not_seasonally_adjusted"
        with pytest.raises(ValueError, match="must be seasonally adjusted"):
            economic_confirmation.record_vintage_batch(con, [observation])


@pytest.mark.parametrize(
    "field",
    [
        "series_id",
        "reference_period",
        "vintage_id",
        "as_of_timestamp",
        "value_at_release",
        "seasonal_adjustment",
        "source_url",
        "source_hash",
    ],
)
def test_record_vintage_batch_rejects_missing_required_field(field, tmp_path):
    con = economic_confirmation.connect(tmp_path / "market.sqlite")
    observation = release_vintage()
    del observation[field]
    with pytest.raises(ValueError, match="required"):
        economic_confirmation.record_vintage_batch(con, [observation])


def test_record_vintage_batch_rejects_invalid_value(tmp_path):
    con = economic_confirmation.connect(tmp_path / "market.sqlite")
    observation = dict(release_vintage())
    observation["value_at_release"] = "not-a-number"
    with pytest.raises(ValueError, match="invalid value"):
        economic_confirmation.record_vintage_batch(con, [observation])


def test_connect_creates_feature_tables(tmp_path):
    con = economic_confirmation.connect(tmp_path / "market.sqlite")
    tables = {
        row["name"]
        for row in con.execute(
            "select name from sqlite_master where type = 'table'"
        ).fetchall()
    }
    assert {
        "economic_confirmation_vintages",
        "economic_confirmation_current_observations",
        "economic_confirmation_source_contracts",
        "economic_confirmation_scheduled_events",
    } <= tables


def test_record_scheduled_events_round_trip(tmp_path):
    con = economic_confirmation.connect(tmp_path / "market.sqlite")
    events = [
        {
            "event_id": "bls_employment_situation",
            "scheduled_at": "2026-08-07T08:30:00",
            "status": "upcoming",
            "timezone": "ET",
            "source_url": "https://www.bls.gov/news.release/pdf/empsit.pdf",
        }
    ]
    economic_confirmation.record_scheduled_events(con, events)
    loaded = economic_confirmation.load_scheduled_events(con)
    assert len(loaded) == 1
    assert loaded[0]["event_id"] == "bls_employment_situation"
    assert loaded[0]["status"] == "upcoming"
    assert loaded[0]["scheduled_at"] == "2026-08-07T08:30:00"


def test_load_scheduled_events_returns_empty_when_none(tmp_path):
    con = economic_confirmation.connect(tmp_path / "market.sqlite")
    assert economic_confirmation.load_scheduled_events(con) == []


def test_record_source_contract_round_trip(tmp_path):
    con = economic_confirmation.connect(tmp_path / "market.sqlite")
    contract = {
        "metric_id": "initial_claims_trend",
        "source": "DOL",
        "seasonal_adjustment": "seasonally_adjusted",
        "method_version": "claims_trend_v1",
    }
    economic_confirmation.record_source_contract(con, "initial_claims_sa", contract)
    loaded = economic_confirmation.load_source_contracts(con, ["initial_claims_sa"])
    assert loaded["initial_claims_sa"] == contract


def test_record_source_contract_rejects_empty_contract(tmp_path):
    con = economic_confirmation.connect(tmp_path / "market.sqlite")
    with pytest.raises(ValueError, match="non-empty dict"):
        economic_confirmation.record_source_contract(con, "initial_claims_sa", {})


def test_replace_national_claims_history_batch_removes_only_legacy_monthly_continuing_rows(
    tmp_path,
):
    con = economic_confirmation.connect(tmp_path / "market.sqlite")
    legacy = history_vintage()
    legacy.update(
        series_id="continuing_claims_sa",
        reference_period="2026-07",
        vintage_id="history:continuing_claims_sa:2026-07:2026-08-03",
        source_hash="legacy-monthly",
    )
    weekly = release_vintage()
    weekly.update(
        series_id="continuing_claims_sa",
        reference_period="2026-07-18",
        vintage_id="release:continuing_claims_sa:2026-07-18:2026-07-30",
    )
    initial = history_vintage()
    initial.update(
        series_id="initial_claims_sa",
        reference_period="2026-07-18",
        vintage_id="history:initial_claims_sa:2026-07-18:2026-08-03",
        source_hash="initial-history",
    )
    national_initial = history_vintage()
    national_initial.update(
        series_id="initial_claims_sa",
        reference_period="2026-07-04",
        vintage_id="history:initial_claims_sa:2026-07-04:2026-08-03",
        source_url="https://oui.doleta.gov/unemploy/wkclaims/report.asp",
        source_hash="national-history",
    )
    national_continuing = dict(national_initial)
    national_continuing.update(
        series_id="continuing_claims_sa",
        vintage_id="history:continuing_claims_sa:2026-07-04:2026-08-03",
    )
    economic_confirmation.record_vintage_batch(con, [legacy, weekly, initial])

    assert (
        economic_confirmation.replace_national_claims_history_batch(
            con, [national_initial, national_continuing]
        )
        == 2
    )

    rows = economic_confirmation.load_current_series(
        con, ["initial_claims_sa", "continuing_claims_sa"]
    )
    assert [row["reference_period"] for row in rows["continuing_claims_sa"]] == [
        "2026-07-04",
        "2026-07-18",
    ]
    assert [row["reference_period"] for row in rows["initial_claims_sa"]] == [
        "2026-07-04",
        "2026-07-18",
    ]


def test_replace_national_claims_history_batch_rolls_back_on_delete_failure(
    tmp_path, monkeypatch
):
    con = economic_confirmation.connect(tmp_path / "market.sqlite")
    legacy = history_vintage()
    legacy.update(
        series_id="continuing_claims_sa",
        reference_period="2026-07",
        vintage_id="history:continuing_claims_sa:2026-07:2026-08-03",
        source_hash="legacy-monthly",
    )
    economic_confirmation.record_vintage_batch(con, [legacy])
    national = history_vintage()
    national.update(
        series_id="continuing_claims_sa",
        reference_period="2026-07-04",
        vintage_id="history:continuing_claims_sa:2026-07-04:2026-08-03",
        source_hash="national-history",
    )

    def raiser(con):
        raise sqlite3.OperationalError("forced")

    monkeypatch.setattr(
        economic_confirmation, "_delete_legacy_monthly_continuing_claims", raiser
    )
    with pytest.raises(sqlite3.OperationalError, match="forced"):
        economic_confirmation.replace_national_claims_history_batch(con, [national])

    legacy_periods = [
        row["reference_period"]
        for row in con.execute(
            "select reference_period from economic_confirmation_vintages "
            "where series_id = 'continuing_claims_sa'"
        ).fetchall()
    ]
    assert legacy_periods == ["2026-07"]
    current_periods = [
        row["reference_period"]
        for row in con.execute(
            "select reference_period from economic_confirmation_current_observations "
            "where series_id = 'continuing_claims_sa'"
        ).fetchall()
    ]
    assert current_periods == ["2026-07"]

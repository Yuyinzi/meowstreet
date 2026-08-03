from scripts import import_economic_confirmation


def g17_observation():
    return {
        "series_id": "manufacturing_production",
        "reference_period": "2026-06-01",
        "vintage_id": "g17:manufacturing_production:2026-06-01:2026-08-03",
        "as_of_timestamp": "2026-08-03T00:00:00+00:00",
        "value_at_release": 100.0,
        "seasonal_adjustment": "seasonally_adjusted",
        "source_url": "https://www.federalreserve.gov/releases/g17/",
        "source_hash": "g17-source-hash",
    }


def test_main_imports_g17_when_claims_history_fails(monkeypatch, tmp_path, capsys):
    def failing_claims_history(*args):
        raise ValueError("claims chartbook is unavailable")

    monkeypatch.setattr(
        import_economic_confirmation.dol_ui_claims,
        "fetch_claims_history",
        failing_claims_history,
    )
    monkeypatch.setattr(
        import_economic_confirmation.dol_ui_claims,
        "fetch_claims_release",
        lambda *args: [],
    )
    monkeypatch.setattr(
        import_economic_confirmation,
        "_fetch_bytes",
        lambda *args: b"employment situation pdf",
    )
    monkeypatch.setattr(
        import_economic_confirmation.bls_employment_situation,
        "parse_employment_situation_release",
        lambda *args: {"observations": [], "scheduled_events": []},
    )
    monkeypatch.setattr(
        import_economic_confirmation.federal_reserve_g17,
        "fetch_g17_release",
        lambda *args: {"observations": [g17_observation()], "csv": b"g17 csv"},
    )

    db_path = tmp_path / "market.sqlite"
    exit_code = import_economic_confirmation.main(["--db-path", str(db_path)])

    con = import_economic_confirmation.economic_confirmation.connect(db_path)
    try:
        rows = import_economic_confirmation.economic_confirmation.load_current_series(
            con, ["manufacturing_production"]
        )
    finally:
        con.close()

    assert exit_code == 1
    assert rows["manufacturing_production"][0]["value"] == 100.0
    assert "claims_history: failed - claims chartbook is unavailable" in capsys.readouterr().err

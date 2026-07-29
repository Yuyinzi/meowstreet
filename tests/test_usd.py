from app.data_sources import usd


def _write_fred_csv(path, series_id, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"observation_date,{series_id}"]
    for date_val, value in rows:
        lines.append(f"{date_val},{value}")
    path.write_text("\n".join(lines))


def test_parse_usd_csvs_preserves_official_series_and_provenance(tmp_path):
    _write_fred_csv(tmp_path / "DTWEXBGS.csv", "DTWEXBGS", [("2026-07-21", "120.0")])
    payload = usd.parse_usd_csvs(tmp_path)

    assert (
        payload["usd_broad"]["observations"][0]["source_identifier"] == "DTWEXBGS"
    )


def test_parse_usd_csvs_includes_official_cpi_ppi_confirmation_series(tmp_path):
    _write_fred_csv(tmp_path / "CPIAUCSL.csv", "CPIAUCSL", [("2026-06-01", "332.568")])
    payload = usd.parse_usd_csvs(tmp_path)

    assert (
        payload["cpi_all_items"]["observations"][0]["source_identifier"]
        == "CPIAUCSL"
    )

import pytest

from app.db import macro_indicators
from app.services import non_oil_attribution_evidence_import as service


def global_fact():
    return {
        "method_version": "non_oil_attribution_evidence_v1",
        "commodity_id": "copper",
        "source_name": "International Wrought Copper Council",
        "source_url": "http://www.coppercouncil.org/iwcc-statistics-and-data",
        "factor_category": "supply",
        "metric_name": "Production",
        "geography": "Global",
        "observation_date": "2024-12-31",
        "publication_date": None,
        "value": 24100.0,
        "units": "t",
        "status": "available",
    }


def lumber_fact():
    return {
        **global_fact(),
        "commodity_id": "lumber",
        "source_name": "Food and Agriculture Organization of the United Nations",
        "source_url": "https://www.fao.org/faostat/en/#data/FO",
        "factor_category": "trade",
        "metric_name": "Production",
        "geography": "World",
        "observation_date": "2024-12-31",
        "value": 254000000.0,
        "units": "m3",
    }


def raising_faostat():
    raise ValueError("faostat fetch failed")


def test_refresh_rolls_back_iwcc_when_faostat_fails(tmp_path):
    con = macro_indicators.connect(tmp_path / "market_data.sqlite")
    with pytest.raises(ValueError, match="faostat"):
        service.refresh_non_oil_attribution_evidence(
            con,
            iwcc_fetcher=lambda: [global_fact()],
            faostat_fetcher=raising_faostat,
        )
    assert macro_indicators.load_non_oil_attribution_facts(con) == []


def test_refresh_records_unavailable_status_for_failed_source(tmp_path):
    con = macro_indicators.connect(tmp_path / "market_data.sqlite")
    with pytest.raises(ValueError, match="faostat"):
        service.refresh_non_oil_attribution_evidence(
            con,
            iwcc_fetcher=lambda: [global_fact()],
            faostat_fetcher=raising_faostat,
        )
    statuses = {
        row["commodity_id"]: row
        for row in macro_indicators.load_non_oil_attribution_refresh_status(con)
    }
    assert statuses["lumber"]["status"] == "unavailable"
    assert statuses["lumber"]["error_message"] == "faostat fetch failed"


def test_refresh_marks_succeeded_source_unavailable_when_sibling_fails(tmp_path):
    con = macro_indicators.connect(tmp_path / "market_data.sqlite")
    with pytest.raises(ValueError, match="faostat"):
        service.refresh_non_oil_attribution_evidence(
            con,
            iwcc_fetcher=lambda: [global_fact()],
            faostat_fetcher=raising_faostat,
        )
    statuses = {
        row["commodity_id"]: row
        for row in macro_indicators.load_non_oil_attribution_refresh_status(con)
    }
    assert statuses["copper"]["status"] == "unavailable"
    assert statuses["copper"]["error_message"]
    assert macro_indicators.load_non_oil_attribution_facts(con) == []


def test_refresh_records_available_status_for_successful_refresh(tmp_path):
    con = macro_indicators.connect(tmp_path / "market_data.sqlite")
    service.refresh_non_oil_attribution_evidence(
        con,
        iwcc_fetcher=lambda: [global_fact()],
        faostat_fetcher=lambda: [lumber_fact()],
    )
    statuses = {
        row["commodity_id"]: row
        for row in macro_indicators.load_non_oil_attribution_refresh_status(con)
    }
    assert statuses["copper"]["status"] == "available"
    assert statuses["lumber"]["status"] == "available"


def test_refresh_persists_facts_from_both_fetchers(tmp_path):
    con = macro_indicators.connect(tmp_path / "market_data.sqlite")
    result = service.refresh_non_oil_attribution_evidence(
        con,
        iwcc_fetcher=lambda: [global_fact()],
        faostat_fetcher=lambda: [lumber_fact()],
    )
    assert result == {"facts": 2, "commodities": ["copper", "lumber"]}
    rows = macro_indicators.load_non_oil_attribution_facts(con)
    assert len(rows) == 2


def test_refresh_rolls_back_all_facts_when_merge_fails_partway(tmp_path):
    con = macro_indicators.connect(tmp_path / "market_data.sqlite")

    def invalid_faostat():
        return [{"commodity_id": "lumber"}]

    with pytest.raises(ValueError, match=" non-oil attribution fact"):
        service.refresh_non_oil_attribution_evidence(
            con,
            iwcc_fetcher=lambda: [global_fact()],
            faostat_fetcher=invalid_faostat,
        )
    assert macro_indicators.load_non_oil_attribution_facts(con) == []


def test_import_cli_prints_result_on_success(monkeypatch, capsys, tmp_path):
    from scripts import import_non_oil_attribution_evidence

    monkeypatch.setattr(
        service,
        "refresh_non_oil_attribution_evidence",
        lambda con: {"facts": 2, "commodities": ["copper", "lumber"]},
    )
    exit_code = import_non_oil_attribution_evidence.main(
        ["--db-path", str(tmp_path / "market.sqlite")]
    )
    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out == "facts: 2, commodities: copper, lumber\n"


def test_import_cli_reports_errors_without_traceback(monkeypatch, capsys, tmp_path):
    from scripts import import_non_oil_attribution_evidence

    def raising_refresh(con):
        raise ValueError("faostat fetch failed")

    monkeypatch.setattr(
        service, "refresh_non_oil_attribution_evidence", raising_refresh
    )
    exit_code = import_non_oil_attribution_evidence.main(
        ["--db-path", str(tmp_path / "market.sqlite")]
    )
    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert (
        captured.err == " non-oil attribution import error: faostat fetch failed\n"
    )

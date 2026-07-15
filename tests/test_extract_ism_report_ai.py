from pathlib import Path

import pytest

from app.db import us_rates_liquidity
from app.tools import ism_ai_extraction
from scripts import extract_ism_report_ai


def test_extract_snapshot_with_client_saves_ai_payload(tmp_path):
    con = us_rates_liquidity.connect(tmp_path / "market_data.sqlite")
    us_rates_liquidity.replace_ism_report_source_snapshot(
        con,
        {
            "source_url": "https://example.com/report.html",
            "source_name": "prnewswire",
            "source_hash": "abc123",
            "fetched_at": "2026-07-15T10:00:00Z",
            "raw_html": "<html><article>June 2026 ISM report text</article></html>",
            "parse_status": "failed",
            "parse_error": "rankings missing",
            "report_id": None,
            "report_month": None,
        },
    )

    class FakeClient:
        def complete_json(self, prompt):
            payload = ism_ai_extraction_test_payload()
            return payload

    result = extract_ism_report_ai.extract_snapshot(
        con,
        "https://example.com/report.html",
        FakeClient(),
        model="fake-model",
    )

    assert result == {
        "report_id": "ism_manufacturing_2026_06",
        "industry_signals": 2,
    }


def test_extract_snapshot_rejects_llm_report_month_mismatch(tmp_path):
    con = us_rates_liquidity.connect(tmp_path / "market_data.sqlite")
    us_rates_liquidity.replace_ism_report_source_snapshot(
        con,
        {
            "source_url": "https://example.com/report.html",
            "source_name": "prnewswire",
            "source_hash": "abc123",
            "fetched_at": "2026-07-15T10:00:00Z",
            "raw_html": "<html><article>June 2026 ISM report text</article></html>",
            "parse_status": "failed",
            "parse_error": "rankings missing",
            "report_id": None,
            "report_month": None,
        },
    )

    class FakeClient:
        def complete_json(self, prompt):
            payload = ism_ai_extraction_test_payload()
            payload["report"]["report_month"] = "2026-01-01"
            return payload

    with pytest.raises(ValueError, match="llm report_month mismatch"):
        extract_ism_report_ai.extract_snapshot(
            con,
            "https://example.com/report.html",
            FakeClient(),
            model="fake-model",
        )


def test_extract_snapshot_saves_ai_summary(tmp_path):
    con = us_rates_liquidity.connect(tmp_path / "market_data.sqlite")
    us_rates_liquidity.replace_ism_report_source_snapshot(
        con,
        {
            "source_url": "https://example.com/report.html",
            "source_name": "prnewswire",
            "source_hash": "abc123",
            "fetched_at": "2026-07-15T10:00:00Z",
            "raw_html": "<html><article>June 2026 ISM report text</article></html>",
            "parse_status": "failed",
            "parse_error": "rankings missing",
            "report_id": None,
            "report_month": None,
        },
    )

    class FakeClient:
        def complete_json(self, prompt):
            return ism_ai_extraction_test_payload()

    extract_ism_report_ai.extract_snapshot(
        con,
        "https://example.com/report.html",
        FakeClient(),
        model="fake-model",
    )

    summary = us_rates_liquidity.load_ism_report_ai_summary(
        con,
        "ism_manufacturing_2026_06",
    )
    assert summary["summary_text"]


def test_main_extracts_source_url_with_injected_client(tmp_path, capsys):
    db_path = tmp_path / "market_data.sqlite"
    con = us_rates_liquidity.connect(db_path)
    us_rates_liquidity.replace_ism_report_source_snapshot(
        con,
        {
            "source_url": "https://example.com/report.html",
            "source_name": "prnewswire",
            "source_hash": "abc123",
            "fetched_at": "2026-07-15T10:00:00Z",
            "raw_html": "<html><article>June 2026 ISM report text</article></html>",
            "parse_status": "failed",
            "parse_error": "rankings missing",
            "report_id": None,
            "report_month": None,
        },
    )
    con.close()

    class FakeClient:
        def complete_json(self, prompt):
            return ism_ai_extraction_test_payload()

    exit_code = extract_ism_report_ai.main(
        [
            "--db-path",
            str(db_path),
            "--source-url",
            "https://example.com/report.html",
            "--model",
            "fake-model",
        ],
        client_factory=lambda config: FakeClient(),
    )

    assert exit_code == 0
    assert "ism_manufacturing_2026_06: industry_signals=2" in capsys.readouterr().out


def ism_ai_extraction_test_payload():
    from tests.test_ism_ai_extraction import valid_extraction

    return valid_extraction()

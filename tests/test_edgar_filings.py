import pytest

from app.db import edgar_filings as edgar_db


def _filing(accession, filing_date, items=None, is_earnings=None):
    return {
        "accession": accession,
        "filing_date": filing_date,
        "primary_document": f"doc-{accession}.htm",
        "items": items,
        "is_earnings": is_earnings,
    }


class TestCikMap:
    def test_save_and_load_roundtrip(self, tmp_path):
        con = edgar_db.connect(tmp_path / "market_data.sqlite")
        try:
            edgar_db.save_cik(con, "nvda", 1045810, "NVIDIA CORP")
            row = edgar_db.load_cik(con, "NVDA")
            assert row["cik"] == 1045810
            assert row["title"] == "NVIDIA CORP"
            assert edgar_db.cik_map_fresh(row)
        finally:
            con.close()

    def test_load_missing_returns_none(self, tmp_path):
        con = edgar_db.connect(tmp_path / "market_data.sqlite")
        try:
            assert edgar_db.load_cik(con, "NVDA") is None
        finally:
            con.close()

    def test_stale_row_not_fresh(self, tmp_path):
        assert not edgar_db.cik_map_fresh({"fetched_at": "2020-01-01T00:00:00+00:00"})
        assert not edgar_db.cik_map_fresh(None)


class TestFilings:
    def test_save_and_load_with_items(self, tmp_path):
        con = edgar_db.connect(tmp_path / "market_data.sqlite")
        try:
            edgar_db.save_filing(con, "NVDA", _filing("0001-26-000073", "2026-08-26"))
            edgar_db.save_filing(con, "NVDA", _filing("0001-25-000023", "2025-02-26"))
            filings = edgar_db.load_filings(con, "NVDA")
            assert [f["accession"] for f in filings] == ["0001-25-000023", "0001-26-000073"]
            assert filings[0]["items"] is None
            assert filings[0]["is_earnings"] is None
        finally:
            con.close()

    def test_upsert_preserves_existing_items(self, tmp_path):
        con = edgar_db.connect(tmp_path / "market_data.sqlite")
        try:
            edgar_db.save_filing(con, "NVDA", _filing("0001-26-000073", "2026-08-26", items=["2.02"], is_earnings=1))
            edgar_db.save_filing(con, "NVDA", _filing("0001-26-000073", "2026-08-26"))
            filings = edgar_db.load_filings(con, "NVDA")
            assert filings[0]["items"] == ["2.02"]
            assert filings[0]["is_earnings"] == 1
        finally:
            con.close()

    def test_since_filter(self, tmp_path):
        con = edgar_db.connect(tmp_path / "market_data.sqlite")
        try:
            edgar_db.save_filing(con, "NVDA", _filing("0001-26-000073", "2026-08-26"))
            edgar_db.save_filing(con, "NVDA", _filing("0001-25-000023", "2025-02-26"))
            filings = edgar_db.load_filings(con, "NVDA", since="2026-01-01")
            assert [f["accession"] for f in filings] == ["0001-26-000073"]
        finally:
            con.close()

    def test_load_missing_items_only(self, tmp_path):
        con = edgar_db.connect(tmp_path / "market_data.sqlite")
        try:
            edgar_db.save_filing(con, "NVDA", _filing("0001-26-000073", "2026-08-26"))
            edgar_db.save_filing(con, "NVDA", _filing("0001-25-000023", "2025-02-26", items=["2.02"], is_earnings=1))
            missing = edgar_db.load_filings_missing_items(con, "NVDA")
            assert [f["accession"] for f in missing] == ["0001-26-000073"]
        finally:
            con.close()


class TestStatementFacts:
    def test_save_and_load_roundtrip(self, tmp_path):
        con = edgar_db.connect(tmp_path / "market_data.sqlite")
        try:
            facts = {"ebit": {"tag": "OperatingIncomeLoss", "quarterly": [{"end": "2026-07-31", "val": 120.0, "filed": "2026-08-20", "form": "10-Q"}], "annual": [], "instant": []}}
            edgar_db.save_statement_facts(con, "nvda", 1045810, facts)
            row = edgar_db.load_statement_facts(con, "NVDA")
            assert row["cik"] == 1045810
            assert row["facts"] == facts
            assert edgar_db.cik_map_fresh(row)
        finally:
            con.close()

    def test_negative_cache_row_has_none_facts(self, tmp_path):
        con = edgar_db.connect(tmp_path / "market_data.sqlite")
        try:
            edgar_db.save_statement_facts(con, "BABA", None, None)
            row = edgar_db.load_statement_facts(con, "BABA")
            assert row["facts"] is None
            assert row["cik"] is None
            assert edgar_db.cik_map_fresh(row)
        finally:
            con.close()

    def test_load_missing_returns_none(self, tmp_path):
        con = edgar_db.connect(tmp_path / "market_data.sqlite")
        try:
            assert edgar_db.load_statement_facts(con, "NVDA") is None
        finally:
            con.close()

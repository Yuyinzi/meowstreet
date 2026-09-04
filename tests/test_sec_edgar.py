import json

import httpx
import pytest

from app.data_sources import sec_edgar
from app.http_client import HttpClient


def _mock_client(handler):
    return HttpClient(transport=httpx.MockTransport(handler), sleep=lambda _: None)


def _company_tickers_json():
    return json.dumps({
        "0": {"cik_str": 1045810, "ticker": "NVDA", "title": "NVIDIA CORP"},
        "1": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
    })


def _submissions_json(older_files=None):
    return json.dumps({
        "filings": {
            "recent": {
                "form": ["8-K", "4", "8-K", "10-Q"],
                "filingDate": ["2026-08-26", "2026-08-20", "2025-02-26", "2025-02-20"],
                "accessionNumber": ["0001045810-26-000073", "0001045810-26-000070", "0001045810-25-000023", "0001045810-25-000020"],
                "primaryDocument": ["nvda-20260826.htm", "form4.htm", "nvda-20250226.htm", "nvda-10q.htm"],
            },
            "files": older_files or [],
        }
    })


class TestParseCompanyTickers:
    def test_parses_ticker_entries(self):
        result = sec_edgar.parse_company_tickers(_company_tickers_json())
        assert result["NVDA"] == {"cik": 1045810, "title": "NVIDIA CORP"}
        assert result["AAPL"] == {"cik": 320193, "title": "Apple Inc."}

    def test_malformed_payload_raises(self):
        with pytest.raises(ValueError, match="company tickers payload is malformed"):
            sec_edgar.parse_company_tickers(json.dumps({}))


class TestParseSubmissions:
    def test_filters_8k_rows(self):
        result = sec_edgar.parse_submissions(_submissions_json(), "NVDA")
        assert result["older_files"] == []
        assert [row["filing_date"] for row in result["filings"]] == ["2026-08-26", "2025-02-26"]
        assert result["filings"][0]["accession"] == "0001045810-26-000073"
        assert result["filings"][0]["primary_document"] == "nvda-20260826.htm"

    def test_since_filters_older_rows(self):
        result = sec_edgar.parse_submissions(_submissions_json(), "NVDA", since="2026-01-01")
        assert [row["filing_date"] for row in result["filings"]] == ["2026-08-26"]

    def test_older_files_listed(self):
        payload = _submissions_json(older_files=[{"name": "CIK0001045810-submissions-001.json"}])
        result = sec_edgar.parse_submissions(payload, "NVDA")
        assert result["older_files"] == ["CIK0001045810-submissions-001.json"]

    def test_malformed_payload_raises(self):
        with pytest.raises(ValueError, match="submissions payload malformed for NVDA"):
            sec_edgar.parse_submissions(json.dumps({"filings": {}}), "NVDA")


class TestParseOlderSubmissions:
    def test_parses_paged_rows(self):
        payload = json.dumps({
            "form": ["8-K", "S-8"],
            "filingDate": ["2019-05-01", "2019-04-01"],
            "accessionNumber": ["0001045810-19-000010", "0001045810-19-000009"],
            "primaryDocument": ["nvda-20190501.htm", "s8.htm"],
        })
        rows = sec_edgar.parse_older_submissions(payload, "NVDA")
        assert rows == [{
            "accession": "0001045810-19-000010",
            "filing_date": "2019-05-01",
            "primary_document": "nvda-20190501.htm",
        }]


class TestParse8kItems:
    def test_extracts_unique_items_in_order(self):
        html = "<p>Item 2.02 Results of Operations</p><p>Item 9.01 Financial Statements</p><p>Item 2.02 again</p>"
        assert sec_edgar.parse_8k_items(html) == ["2.02", "9.01"]

    def test_no_items_returns_empty(self):
        assert sec_edgar.parse_8k_items("<p>no items here</p>") == []

    def test_is_earnings_filing(self):
        assert sec_edgar.is_earnings_filing(["2.02", "9.01"]) is True
        assert sec_edgar.is_earnings_filing(["5.07"]) is False
        assert sec_edgar.is_earnings_filing([]) is False


class TestFetchContracts:
    def test_fetch_cik_map_uses_edgar_user_agent_without_brotli(self):
        seen = {}

        def handler(request):
            seen["ua"] = request.headers.get("user-agent", "")
            seen["encoding"] = request.headers.get("accept-encoding", "")
            return httpx.Response(200, text=_company_tickers_json())

        result = sec_edgar.fetch_cik_map(http_client=_mock_client(handler))
        assert "Meowstreet" in seen["ua"]
        assert "br" not in seen["encoding"]
        assert result["NVDA"]["cik"] == 1045810

    def test_fetch_cik_map_raises_on_404(self):
        def handler(request):
            return httpx.Response(404, text="Not Found")

        with pytest.raises(ValueError, match="company tickers fetch failed: HTTP 404"):
            sec_edgar.fetch_cik_map(http_client=_mock_client(handler))

    def test_fetch_submissions_url_and_error(self):
        seen = {}

        def handler(request):
            seen["url"] = str(request.url)
            return httpx.Response(200, text=_submissions_json())

        sec_edgar.fetch_submissions(1045810, http_client=_mock_client(handler))
        assert seen["url"] == "https://data.sec.gov/submissions/CIK0001045810.json"

        def failing(request):
            return httpx.Response(403, text="Forbidden")

        with pytest.raises(ValueError, match="submissions CIK1045810 fetch failed: HTTP 403"):
            sec_edgar.fetch_submissions(1045810, http_client=_mock_client(failing))

    def test_fetch_filing_document_url(self):
        seen = {}

        def handler(request):
            seen["url"] = str(request.url)
            return httpx.Response(200, text="<p>Item 2.02 Results</p>")

        body = sec_edgar.fetch_filing_document(
            1045810, "0001045810-26-000073", "nvda-20260826.htm",
            http_client=_mock_client(handler),
        )
        assert seen["url"] == (
            "https://www.sec.gov/Archives/edgar/data/1045810/"
            "000104581026000073/nvda-20260826.htm"
        )
        assert sec_edgar.parse_8k_items(body) == ["2.02"]

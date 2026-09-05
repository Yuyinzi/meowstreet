import json
from datetime import date, timedelta

import httpx

from app.http_client import HttpClient
from app.services import insider_activity


def _mock_client(handler):
    return HttpClient(transport=httpx.MockTransport(handler), sleep=lambda _: None)


def _tickers_payload():
    return json.dumps({
        "0": {"cik_str": 1045810, "ticker": "NVDA", "title": "NVIDIA CORP"},
    })


def _recent_form4_date():
    return (date.today() - timedelta(days=10)).isoformat()


def _submissions_payload():
    return json.dumps({
        "filings": {
            "recent": {
                "form": ["4", "8-K"],
                "filingDate": [_recent_form4_date(), (date.today() - timedelta(days=30)).isoformat()],
                "accessionNumber": ["0001045810-26-000070", "0001045810-26-000073"],
                "primaryDocument": ["form4.xml", "nvda-earnings.htm"],
            },
            "files": [],
        }
    })


def _form4_xml():
    day = _recent_form4_date()
    return f"""<?xml version="1.0"?>
<ownershipDocument>
  <reportingOwner>
    <reportingOwnerId><rptOwnerName>HUANG JEN HSUN</rptOwnerName></reportingOwnerId>
    <reportingOwnerRelationship><isDirector>1</isDirector></reportingOwnerRelationship>
  </reportingOwner>
  <nonDerivativeTable>
    <nonDerivativeTransaction>
      <transactionDate><value>{day}</value></transactionDate>
      <transactionCoding><transactionCode>S</transactionCode></transactionCoding>
      <transactionAmounts>
        <transactionShares><value>60000</value></transactionShares>
        <transactionPricePerShare><value>177.82</value></transactionPricePerShare>
        <transactionAcquiredDisposedCode><value>D</value></transactionAcquiredDisposedCode>
      </transactionAmounts>
      <postTransactionAmounts><sharesOwnedFollowingTransaction><value>75400000</value></sharesOwnedFollowingTransaction></postTransactionAmounts>
    </nonDerivativeTransaction>
  </nonDerivativeTable>
</ownershipDocument>
"""


def _happy_handler(request):
    url = str(request.url)
    if "company_tickers" in url:
        return httpx.Response(200, text=_tickers_payload())
    if "data.sec.gov/submissions" in url:
        return httpx.Response(200, text=_submissions_payload())
    if "form4.xml" in url:
        return httpx.Response(200, text=_form4_xml())
    return httpx.Response(404, text="Not Found")


class TestInsiderActivity:
    def test_happy_path_returns_transactions(self, tmp_path):
        result = insider_activity.get_insider_activity(
            "NVDA", db_path=tmp_path / "market_data.sqlite", http_client=_mock_client(_happy_handler)
        )
        assert result["status"] == "ok"
        assert result["cik"] == 1045810
        assert len(result["transactions"]) == 1
        row = result["transactions"][0]
        assert row["insider_name"] == "HUANG JEN HSUN"
        assert row["insider_title"] == "Director"
        assert row["transaction_code"] == "S"
        assert row["code_label"] == "Open-market sale"
        assert row["value"] == round(60000 * 177.82, 2)
        assert row["pct_of_holding"] == round(60000 / (75400000 + 60000), 4)

    def test_second_call_uses_cached_documents(self, tmp_path):
        requests = []

        def counting_handler(request):
            requests.append(str(request.url))
            return _happy_handler(request)

        db_path = tmp_path / "market_data.sqlite"
        insider_activity.get_insider_activity(
            "NVDA", db_path=db_path, http_client=_mock_client(counting_handler)
        )
        first_call_count = len(requests)
        result = insider_activity.get_insider_activity(
            "NVDA", db_path=db_path, http_client=_mock_client(counting_handler)
        )
        assert result["status"] == "ok"
        assert len(result["transactions"]) == 1
        new_requests = requests[first_call_count:]
        assert [url for url in new_requests if "form4.xml" in url] == []
        assert [url for url in new_requests if "company_tickers" in url] == []

    def test_unmapped_symbol_returns_insufficient_data(self, tmp_path):
        def handler(request):
            return httpx.Response(200, text=json.dumps({
                "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
            }))

        result = insider_activity.get_insider_activity(
            "NVDA", db_path=tmp_path / "market_data.sqlite", http_client=_mock_client(handler)
        )
        assert result == {"status": "insufficient_data"}

    def test_refresh_failure_falls_back_to_cache(self, tmp_path):
        db_path = tmp_path / "market_data.sqlite"
        insider_activity.get_insider_activity(
            "NVDA", db_path=db_path, http_client=_mock_client(_happy_handler)
        )

        def failing_handler(request):
            return httpx.Response(500, text="Server Error")

        result = insider_activity.get_insider_activity(
            "NVDA", db_path=db_path, http_client=_mock_client(failing_handler)
        )
        assert result["status"] == "ok"
        assert len(result["transactions"]) == 1

    def test_document_fetch_failure_skips_filing(self, tmp_path):
        def handler(request):
            if "form4.xml" in str(request.url):
                return httpx.Response(500, text="Server Error")
            return _happy_handler(request)

        result = insider_activity.get_insider_activity(
            "NVDA", db_path=tmp_path / "market_data.sqlite", http_client=_mock_client(handler)
        )
        assert result["status"] == "ok"
        assert result["transactions"] == []

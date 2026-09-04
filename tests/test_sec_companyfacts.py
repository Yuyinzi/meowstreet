import json

import httpx
import pytest

from app.data_sources import sec_companyfacts
from app.http_client import HttpClient


def _quarter(start, end, val, filed="2026-08-20", form="10-Q"):
    return {"start": start, "end": end, "val": val, "fy": 2026, "fp": "Q3", "form": form, "filed": filed}


def _instant(end, val, filed="2026-08-20", form="10-Q"):
    return {"end": end, "val": val, "fy": 2026, "fp": "Q3", "form": form, "filed": filed}


def _facts_payload(gaap):
    return json.dumps({"cik": 1045810, "entityName": "NVIDIA", "facts": {"us-gaap": gaap}})


def _full_gaap():
    return {
        "OperatingIncomeLoss": {
            "units": {
                "USD": [
                    _quarter("2025-11-01", "2026-01-31", 100.0),
                    _quarter("2026-02-01", "2026-04-30", 110.0),
                    _quarter("2026-05-01", "2026-07-31", 120.0),
                    _quarter("2025-08-01", "2025-10-31", 90.0),
                    _quarter("2025-02-01", "2026-01-31", 600.0, form="10-K"),
                    _quarter("2025-05-01", "2026-04-30", 610.0, form="10-K"),
                    _quarter("2026-02-01", "2026-07-31", 230.0),
                ]
            }
        },
        "InterestExpenseNonoperating": {
            "units": {
                "USD": [
                    _quarter("2025-11-01", "2026-01-31", 10.0),
                    _quarter("2026-02-01", "2026-04-30", 10.0),
                    _quarter("2026-05-01", "2026-07-31", 10.0),
                    _quarter("2025-08-01", "2025-10-31", 10.0),
                ]
            }
        },
        "AssetsCurrent": {
            "units": {
                "USD": [
                    _instant("2026-07-31", 500.0),
                    _instant("2026-07-31", 480.0, filed="2026-08-10"),
                    _instant("2026-04-30", 450.0),
                ]
            }
        },
        "LiabilitiesCurrent": {"units": {"USD": [_instant("2026-07-31", 200.0)]}},
        "Assets": {"units": {"USD": [_instant("2026-07-31", 1000.0)]}},
    }


class TestParseCompanyFacts:
    def test_classifies_quarterly_annual_and_instant(self):
        payload = sec_companyfacts.parse_company_facts(_facts_payload(_full_gaap()), "nvda")

        assert payload["symbol"] == "NVDA"
        ebit = payload["facts"]["ebit"]
        assert ebit["tag"] == "OperatingIncomeLoss"
        assert [entry["val"] for entry in ebit["quarterly"]] == [120.0, 110.0, 100.0, 90.0]
        assert len(ebit["annual"]) == 2
        instants = payload["facts"]["assets_current"]["instant"]
        assert [entry["val"] for entry in instants] == [500.0, 450.0]

    def test_tag_chain_falls_back_to_alternative(self):
        payload = sec_companyfacts.parse_company_facts(_facts_payload(_full_gaap()), "NVDA")

        assert payload["facts"]["interest_expense"]["tag"] == "InterestExpenseNonoperating"

    def test_dedupe_keeps_latest_filed(self):
        payload = sec_companyfacts.parse_company_facts(_facts_payload(_full_gaap()), "NVDA")

        latest = payload["facts"]["assets_current"]["instant"][0]
        assert latest["val"] == 500.0
        assert latest["filed"] == "2026-08-20"

    def test_malformed_payload_raises(self):
        with pytest.raises(ValueError, match="companyfacts payload malformed for NVDA"):
            sec_companyfacts.parse_company_facts(json.dumps({"facts": {}}), "NVDA")

    def test_no_matching_tags_raises(self):
        gaap = {"Goodwill": {"units": {"USD": [_instant("2026-07-31", 1.0)]}}}
        with pytest.raises(ValueError, match="no usable us-gaap facts for NVDA"):
            sec_companyfacts.parse_company_facts(_facts_payload(gaap), "NVDA")

    def test_symbol_required(self):
        with pytest.raises(ValueError, match="symbol is required"):
            sec_companyfacts.parse_company_facts(_facts_payload(_full_gaap()), "  ")


class TestFetchCompanyFacts:
    def test_request_uses_padded_cik_and_edgar_headers(self):
        seen = {}

        def handler(request):
            seen["url"] = str(request.url)
            seen["user_agent"] = request.headers.get("user-agent")
            return httpx.Response(200, text=_facts_payload(_full_gaap()))

        client = HttpClient(transport=httpx.MockTransport(handler), sleep=lambda _: None)
        raw = sec_companyfacts.fetch_company_facts(1045810, http_client=client)

        assert seen["url"] == "https://data.sec.gov/api/xbrl/companyfacts/CIK0001045810.json"
        assert seen["user_agent"] is not None
        assert json.loads(raw)["cik"] == 1045810

    def test_http_error_raises_value_error(self):
        def handler(request):
            return httpx.Response(404, text="Not Found")

        client = HttpClient(transport=httpx.MockTransport(handler), sleep=lambda _: None)
        with pytest.raises(ValueError, match="companyfacts CIK1045810 fetch failed: HTTP 404"):
            sec_companyfacts.fetch_company_facts(1045810, http_client=client)

import json
from pathlib import Path

import pytest

from app.data_sources import nfib_sbet_api


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = ROOT / "tests" / "fixtures" / "nfib_sbet_api_regional_response.json"
FIXTURE_DATA = json.loads(FIXTURE_PATH.read_text())


class _FakeOpener:
    def __init__(self, response_data, status=200):
        self.response_data = response_data
        self.status = status
        self.last_url = None
        self.last_body = None

    def open(self, url, data=None, timeout=None):
        self.last_url = url
        self.last_body = data
        body = json.dumps(self.response_data).encode("utf-8")

        class _FakeResponse:
            def read(self):
                return body

        return _FakeResponse()

    def close(self):
        pass


def test_fetch_regional_data_posts_documented_request_shape():
    opener = _FakeOpener(FIXTURE_DATA)
    payload = nfib_sbet_api.fetch_regional_data("pacific", 2021, 2026, opener=opener)
    sent = json.loads(opener.last_body)
    assert sent["app_name"] == "sbet"
    assert isinstance(sent["params"], list)
    params_by_name = {p["name"]: p["value"] for p in sent["params"]}
    assert params_by_name["minYear"] == 2021
    assert params_by_name["maxYear"] == 2026
    assert params_by_name["minMonth"] == 1
    assert params_by_name["maxMonth"] == 12
    assert "emp_count_change_expect" in params_by_name["questions"]
    assert "expand_good" in params_by_name["questions"]
    assert params_by_name["statev"] == "AK,CA,HI,OR,WA"
    assert params_by_name["industry"] == ""
    assert params_by_name["employee"] == ""
    assert payload["region_id"] == "pacific"
    assert payload["frequency"] == "quarterly_3_month_aggregate"


def test_fetch_regional_data_parses_response_into_observations():
    opener = _FakeOpener(FIXTURE_DATA)
    payload = nfib_sbet_api.fetch_regional_data("pacific", 2026, 2026, opener=opener)
    assert len(payload["observations"]) == 1
    obs = payload["observations"][0]
    assert obs["date"] == "2026-06-30"
    assert obs["emp_count_change_expect"] is not None
    assert obs["expand_good"] is not None


def test_fetch_regional_data_handles_all_three_regions():
    for region_id in nfib_sbet_api._VALID_REGION_IDS:
        opener = _FakeOpener(FIXTURE_DATA)
        payload = nfib_sbet_api.fetch_regional_data(
            region_id, 2026, 2026, opener=opener
        )
        assert payload["region_id"] == region_id
        assert len(payload["observations"]) == 1


def test_fetch_regional_data_includes_provenance():
    opener = _FakeOpener(FIXTURE_DATA)
    payload = nfib_sbet_api.fetch_regional_data("pacific", 2026, 2026, opener=opener)
    assert "provenance" in payload
    assert payload["provenance"]["procedure"] == "getTotalsFullQuarter2"
    assert payload["provenance"]["url"] is not None
    assert payload["provenance"]["request_hash"] is not None
    assert payload["provenance"]["response_hash"] is not None
    assert payload["provenance"]["retrieval_time"] is not None
    assert payload["request_hash"] is not None
    assert payload["response_hash"] is not None
    assert payload["request_body"] is not None


def test_fetch_regional_data_rejects_unknown_region():
    with pytest.raises(ValueError, match="unknown region id"):
        nfib_sbet_api.fetch_regional_data("unknown", 2021, 2026)


def test_fetch_regional_data_rejects_non_json_response():
    class _BrokenOpener:
        def open(self, url, data=None, timeout=None):
            class _Resp:
                def read(self):
                    return b"not json"

            return _Resp()

    with pytest.raises(ValueError, match="non-json"):
        nfib_sbet_api.fetch_regional_data("pacific", 2021, 2026, opener=_BrokenOpener())


def test_fetch_regional_data_rejects_non_array_response():
    opener = _FakeOpener({"unexpected": []})
    with pytest.raises(ValueError, match="not an array"):
        nfib_sbet_api.fetch_regional_data("pacific", 2021, 2026, opener=opener)


def test_parse_distributions_computes_net_percentages():
    result = nfib_sbet_api._parse_distributions(FIXTURE_DATA)
    assert "2026-06-30" in result
    comps = result["2026-06-30"]
    assert comps["emp_count_change_expect"] == 38.0
    assert comps["expand_good"] == 9.0
    assert comps["inventory_expect"] == 10.0
    assert comps["bus_cond_expect"] == 2.0
    assert comps["sales_expect"] == 4.0
    assert comps["cap_ex_expect"] == 18.0
    assert comps["inventory_current"] == -2.0
    assert comps["job_opening_unfilled"] == 32.0
    assert comps["credit_access_expect"] == -10.0
    assert comps["earn_change"] == -4.0


def test_parse_distributions_empty_input():
    result = nfib_sbet_api._parse_distributions([])
    assert result == {}


def test_compute_optimism_from_components():
    components = {
        "emp_count_change_expect": 38.0,
        "expand_good": 9.0,
        "inventory_expect": 10.0,
        "bus_cond_expect": 2.0,
        "sales_expect": 4.0,
        "cap_ex_expect": 18.0,
        "inventory_current": -2.0,
        "job_opening_unfilled": 32.0,
        "credit_access_expect": -10.0,
        "earn_change": -4.0,
    }
    opt = nfib_sbet_api._compute_optimism_from_components(components)
    expected = (sum(components.values()) / 10 + 100) / 1.095
    assert opt == round(expected, 1)


def test_compute_optimism_returns_none_when_missing_components():
    components = {
        "emp_count_change_expect": 38.0,
        "expand_good": 9.0,
    }
    assert nfib_sbet_api._compute_optimism_from_components(components) is None


def test_fetch_national_data_sends_empty_statev():
    opener = _FakeOpener(FIXTURE_DATA)
    payload = nfib_sbet_api.fetch_national_data(2026, 2026, opener=opener)
    sent = json.loads(opener.last_body)
    params_by_name = {p["name"]: p["value"] for p in sent["params"]}
    assert params_by_name["statev"] == ""


def test_fetch_national_data_includes_response_hash_in_provenance():
    opener = _FakeOpener(FIXTURE_DATA)
    payload = nfib_sbet_api.fetch_national_data(2026, 2026, opener=opener)
    assert payload["provenance"]["response_hash"] == payload["response_hash"]


def test_single_quarter_response_produces_one_observation():
    single_quarter_data = [
        {
            "time_year": 2026,
            "time_quarter": 1,
            "time_month": 3,
            "resp_q_short": "emp_count_change_expect",
            "resp_acode": 1,
            "totalcount": 300,
            "DIM_SURVEY_id": 630,
        },
        {
            "time_year": 2026,
            "time_quarter": 1,
            "time_month": 3,
            "resp_q_short": "emp_count_change_expect",
            "resp_acode": 3,
            "totalcount": 200,
            "DIM_SURVEY_id": 630,
        },
        {
            "time_year": 2026,
            "time_quarter": 1,
            "time_month": 3,
            "resp_q_short": "expand_good",
            "resp_acode": 1,
            "totalcount": 40,
            "DIM_SURVEY_id": 630,
        },
        {
            "time_year": 2026,
            "time_quarter": 1,
            "time_month": 3,
            "resp_q_short": "expand_good",
            "resp_acode": 2,
            "totalcount": 460,
            "DIM_SURVEY_id": 630,
        },
        {
            "time_year": 2026,
            "time_quarter": 1,
            "time_month": 3,
            "resp_q_short": "inventory_expect",
            "resp_acode": 1,
            "totalcount": 100,
            "DIM_SURVEY_id": 630,
        },
        {
            "time_year": 2026,
            "time_quarter": 1,
            "time_month": 3,
            "resp_q_short": "inventory_expect",
            "resp_acode": 2,
            "totalcount": 100,
            "DIM_SURVEY_id": 630,
        },
        {
            "time_year": 2026,
            "time_quarter": 1,
            "time_month": 3,
            "resp_q_short": "inventory_expect",
            "resp_acode": 4,
            "totalcount": 100,
            "DIM_SURVEY_id": 630,
        },
        {
            "time_year": 2026,
            "time_quarter": 1,
            "time_month": 3,
            "resp_q_short": "inventory_expect",
            "resp_acode": 5,
            "totalcount": 100,
            "DIM_SURVEY_id": 630,
        },
        {
            "time_year": 2026,
            "time_quarter": 1,
            "time_month": 3,
            "resp_q_short": "bus_cond_expect",
            "resp_acode": 1,
            "totalcount": 60,
            "DIM_SURVEY_id": 630,
        },
        {
            "time_year": 2026,
            "time_quarter": 1,
            "time_month": 3,
            "resp_q_short": "bus_cond_expect",
            "resp_acode": 2,
            "totalcount": 140,
            "DIM_SURVEY_id": 630,
        },
        {
            "time_year": 2026,
            "time_quarter": 1,
            "time_month": 3,
            "resp_q_short": "bus_cond_expect",
            "resp_acode": 4,
            "totalcount": 100,
            "DIM_SURVEY_id": 630,
        },
        {
            "time_year": 2026,
            "time_quarter": 1,
            "time_month": 3,
            "resp_q_short": "bus_cond_expect",
            "resp_acode": 5,
            "totalcount": 100,
            "DIM_SURVEY_id": 630,
        },
        {
            "time_year": 2026,
            "time_quarter": 1,
            "time_month": 3,
            "resp_q_short": "sales_expect",
            "resp_acode": 1,
            "totalcount": 50,
            "DIM_SURVEY_id": 630,
        },
        {
            "time_year": 2026,
            "time_quarter": 1,
            "time_month": 3,
            "resp_q_short": "sales_expect",
            "resp_acode": 2,
            "totalcount": 50,
            "DIM_SURVEY_id": 630,
        },
        {
            "time_year": 2026,
            "time_quarter": 1,
            "time_month": 3,
            "resp_q_short": "sales_expect",
            "resp_acode": 4,
            "totalcount": 50,
            "DIM_SURVEY_id": 630,
        },
        {
            "time_year": 2026,
            "time_quarter": 1,
            "time_month": 3,
            "resp_q_short": "sales_expect",
            "resp_acode": 5,
            "totalcount": 50,
            "DIM_SURVEY_id": 630,
        },
        {
            "time_year": 2026,
            "time_quarter": 1,
            "time_month": 3,
            "resp_q_short": "cap_ex_expect",
            "resp_acode": 1,
            "totalcount": 100,
            "DIM_SURVEY_id": 630,
        },
        {
            "time_year": 2026,
            "time_quarter": 1,
            "time_month": 3,
            "resp_q_short": "cap_ex_expect",
            "resp_acode": 2,
            "totalcount": 400,
            "DIM_SURVEY_id": 630,
        },
        {
            "time_year": 2026,
            "time_quarter": 1,
            "time_month": 3,
            "resp_q_short": "inventory_current",
            "resp_acode": 1,
            "totalcount": 150,
            "DIM_SURVEY_id": 630,
        },
        {
            "time_year": 2026,
            "time_quarter": 1,
            "time_month": 3,
            "resp_q_short": "inventory_current",
            "resp_acode": 3,
            "totalcount": 100,
            "DIM_SURVEY_id": 630,
        },
        {
            "time_year": 2026,
            "time_quarter": 1,
            "time_month": 3,
            "resp_q_short": "inventory_current",
            "resp_acode": 2,
            "totalcount": 250,
            "DIM_SURVEY_id": 630,
        },
        {
            "time_year": 2026,
            "time_quarter": 1,
            "time_month": 3,
            "resp_q_short": "job_opening_unfilled",
            "resp_acode": 1,
            "totalcount": 40,
            "DIM_SURVEY_id": 630,
        },
        {
            "time_year": 2026,
            "time_quarter": 1,
            "time_month": 3,
            "resp_q_short": "job_opening_unfilled",
            "resp_acode": 2,
            "totalcount": 60,
            "DIM_SURVEY_id": 630,
        },
        {
            "time_year": 2026,
            "time_quarter": 1,
            "time_month": 3,
            "resp_q_short": "job_opening_unfilled",
            "resp_acode": 3,
            "totalcount": 50,
            "DIM_SURVEY_id": 630,
        },
        {
            "time_year": 2026,
            "time_quarter": 1,
            "time_month": 3,
            "resp_q_short": "job_opening_unfilled",
            "resp_acode": 4,
            "totalcount": 350,
            "DIM_SURVEY_id": 630,
        },
        {
            "time_year": 2026,
            "time_quarter": 1,
            "time_month": 3,
            "resp_q_short": "credit_access_expect",
            "resp_acode": 1,
            "totalcount": 40,
            "DIM_SURVEY_id": 630,
        },
        {
            "time_year": 2026,
            "time_quarter": 1,
            "time_month": 3,
            "resp_q_short": "credit_access_expect",
            "resp_acode": 3,
            "totalcount": 110,
            "DIM_SURVEY_id": 630,
        },
        {
            "time_year": 2026,
            "time_quarter": 1,
            "time_month": 3,
            "resp_q_short": "credit_access_expect",
            "resp_acode": 2,
            "totalcount": 350,
            "DIM_SURVEY_id": 630,
        },
        {
            "time_year": 2026,
            "time_quarter": 1,
            "time_month": 3,
            "resp_q_short": "earn_change",
            "resp_acode": 1,
            "totalcount": 70,
            "DIM_SURVEY_id": 630,
        },
        {
            "time_year": 2026,
            "time_quarter": 1,
            "time_month": 3,
            "resp_q_short": "earn_change",
            "resp_acode": 2,
            "totalcount": 90,
            "DIM_SURVEY_id": 630,
        },
        {
            "time_year": 2026,
            "time_quarter": 1,
            "time_month": 3,
            "resp_q_short": "earn_change",
            "resp_acode": 4,
            "totalcount": 70,
            "DIM_SURVEY_id": 630,
        },
        {
            "time_year": 2026,
            "time_quarter": 1,
            "time_month": 3,
            "resp_q_short": "earn_change",
            "resp_acode": 5,
            "totalcount": 70,
            "DIM_SURVEY_id": 630,
        },
        {
            "time_year": 2026,
            "time_quarter": 1,
            "time_month": 3,
            "resp_q_short": "earn_change",
            "resp_acode": 3,
            "totalcount": 200,
            "DIM_SURVEY_id": 630,
        },
    ]
    opener = _FakeOpener(single_quarter_data)
    payload = nfib_sbet_api.fetch_regional_data("pacific", 2026, 2026, opener=opener)
    assert len(payload["observations"]) == 1
    obs = payload["observations"][0]
    assert obs["date"] == "2026-03-31"
    assert obs["emp_count_change_expect"] == pytest.approx(20.0)
    assert obs["expand_good"] == pytest.approx(8.0)


def test_series_to_indicator_maps_all_eleven_series():
    assert len(nfib_sbet_api.SERIES_TO_INDICATOR) == 11
    for series_id, indicator_id in nfib_sbet_api.SERIES_TO_INDICATOR.items():
        assert isinstance(series_id, str)
        assert isinstance(indicator_id, str)


def test_region_mappings():
    assert nfib_sbet_api.REGIONS["pacific"]["statev"] == "AK,CA,HI,OR,WA"
    assert nfib_sbet_api.REGIONS["west_gulf"]["statev"] == "AR,LA,OK,TX"
    assert (
        nfib_sbet_api.REGIONS["north_atlantic"]["statev"]
        == "CT,MA,ME,NH,NJ,NY,PA,RI,VT"
    )

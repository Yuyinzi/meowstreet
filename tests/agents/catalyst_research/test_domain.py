import socket
from datetime import date

import pytest

from app.agents.catalyst_research.domain import (
    _discovery_queries,
    canonicalize_public_url,
    classify_title_by_rule,
    classify_observations,
    merge_classifications,
    normalize_observations,
    normalize_request,
    url_host,
    validate_redirect_chain,
)


def test_discovery_queries_are_bounded_and_cover_each_source_target():
    queries = _discovery_queries({"ticker": "NVDA", "company_name": "NVIDIA Corporation"})

    assert [item["source_type"] for item in queries] == [
        "ir_home",
        "press_releases",
        "events_presentations",
        "earnings_results",
    ]
    assert all(0 < len(item["query"]) <= 240 for item in queries)
    assert all("NVIDIA Corporation" in item["query"] for item in queries)


def test_discovery_query_identity_is_cleaned_before_each_distinct_suffix():
    queries = _discovery_queries({"ticker": "nv da!", "company_name": "A" * 300 + "\n<script>"})

    assert len(queries) == 4
    assert len({item["query"] for item in queries}) == 4
    assert all(len(item["query"]) <= 240 for item in queries)
    assert all("investor relations" in item["query"] for item in queries)
    assert all("<" not in item["query"] and ">" not in item["query"] for item in queries)


def test_discovery_queries_can_be_restricted_to_requested_source_types():
    queries = _discovery_queries(
        {"ticker": "NVDA", "company_name": "NVIDIA Corporation"},
        source_types={"press_releases", "events_presentations"},
    )

    assert [item["source_type"] for item in queries] == ["press_releases", "events_presentations"]


def test_normalize_request_defaults_to_v1_1_research_mode():
    result = normalize_request("nvda", years=1, as_of="2026-09-08")

    assert result["mode"] == "research"
    assert result["ticker"] == "NVDA"
    assert result["start"] == "2025-09-08"


@pytest.mark.parametrize("mode", ["research", "update", "rediscover"])
def test_normalize_request_accepts_v1_1_modes(mode):
    assert normalize_request("NVDA", 1, "2026-09-08", mode)["mode"] == mode


def test_normalize_request_rejects_unknown_mode():
    with pytest.raises(ValueError, match="research mode is invalid"):
        normalize_request("NVDA", 1, "2026-09-08", "crawl")


@pytest.mark.parametrize("ticker, expected", [(" nvda ", "NVDA"), ("aapl", "AAPL")])
def test_normalize_request_normalizes_ticker_and_window(ticker, expected):
    result = normalize_request(ticker, years=2, as_of=date(2024, 2, 29))

    assert result == {
        "ticker": expected,
        "years": 2,
        "as_of": "2024-02-29",
        "start": "2022-02-28",
        "end": "2024-02-29",
        "mode": "research",
    }


@pytest.mark.parametrize(
    ("years", "expected_start"),
    [(1, "2023-02-28"), (2, "2022-02-28"), (3, "2021-02-28"), (4, "2020-02-29")],
)
def test_normalize_request_clamps_leap_day(years, expected_start):
    assert normalize_request("NVDA", years=years, as_of=date(2024, 2, 29))["start"] == expected_start


@pytest.mark.parametrize("ticker, years", [("", 4), ("   ", 4), ("NVDA", 0), ("NVDA", 5), ("NVDA", True), ("NVDA", 2.0)])
def test_normalize_request_rejects_invalid_values(ticker, years):
    with pytest.raises(ValueError):
        normalize_request(ticker, years=years, as_of=date(2024, 1, 1))


@pytest.mark.parametrize(
    "url",
    [
        "file:///tmp/page.html",
        "https://user:password@example.com/page",
        "https:///missing-host",
        "https://localhost/page",
        "https://service.internal/page",
        "https://127.0.0.1/page",
        "https://[::1]/page",
        "https://10.0.0.4/page",
        "https://169.254.169.254/latest/meta-data",
        "https://224.0.0.1/page",
    ],
)
def test_canonicalize_public_url_rejects_unsafe_lexical_urls(url):
    with pytest.raises(ValueError):
        canonicalize_public_url(url)


def test_canonicalize_public_url_removes_fragments_tracking_and_normalizes_host():
    result = canonicalize_public_url(
        " HTTPS://Example.COM/news?utm_source=mail&b=2&gclid=x&a=1#details "
    )

    assert result == "https://example.com/news?a=1&b=2"
    assert url_host(result) == "example.com"


def test_validate_redirect_chain_checks_each_public_host_with_injected_resolver():
    addresses = {
        "example.com": ["93.184.216.34"],
        "cdn.example.com": ["2001:4860:4860::8888"],
    }

    result = validate_redirect_chain(
        ["https://example.com/start#x", "https://cdn.example.com/final?utm_medium=x"],
        resolver=lambda host: addresses[host],
    )

    assert result == ["https://example.com/start", "https://cdn.example.com/final"]


def test_validate_redirect_chain_resolves_every_hop_even_when_host_repeats():
    calls = []

    def resolver(host):
        calls.append(host)
        return ["93.184.216.34"]

    validate_redirect_chain(
        ["https://example.com/start", "https://example.com/final"],
        resolver=resolver,
    )

    assert calls == ["example.com", "example.com"]


def test_validate_redirect_chain_does_not_resolve_when_resolver_is_omitted(monkeypatch):
    def fail_if_called(host, *args):
        raise AssertionError("system DNS must not be called")

    monkeypatch.setattr("app.agents.catalyst_research.domain.socket.getaddrinfo", fail_if_called)

    assert validate_redirect_chain(["https://93.184.216.34/"], resolver=None) == ["https://93.184.216.34/"]


def test_validate_redirect_chain_rejects_private_dns_result():
    with pytest.raises(ValueError):
        validate_redirect_chain(["https://example.com/"], resolver=lambda host: ["192.168.1.10"])


def test_validate_redirect_chain_normalizes_resolver_failure_to_value_error():
    def resolver(host):
        raise socket.gaierror("temporary failure")

    with pytest.raises(ValueError):
        validate_redirect_chain(["https://example.com/"], resolver=resolver)


@pytest.mark.parametrize("url", ["https://127.1/", "https://2130706433/", "https://0x7f000001/"])
def test_canonicalize_public_url_rejects_noncanonical_private_ipv4_literals(url):
    with pytest.raises(ValueError):
        canonicalize_public_url(url)


def test_normalize_observations_maps_dates_excludes_future_and_out_of_window_and_deduplicates_channel():
    events = [
        {
            "id": 1,
            "published_date": "2024-01-15",
            "title": "  Product\u00a0update ",
            "url": "https://example.com/news?id=1&utm_source=x",
        },
        {
            "id": 2,
            "published_date": "2024-01-15",
            "title": "Product update",
            "url": "https://example.com/news?utm_medium=x&id=1",
        },
        {"id": 3, "published_date": "2023-12-31", "title": "Before", "url": "https://example.com/before"},
    ]

    result = normalize_observations(" nvda ", "press_releases", events, "2024-01-01", "2024-01-31")

    assert result["ticker"] == "NVDA"
    assert result["source_type"] == "press_releases"
    assert result["requested_start"] == "2024-01-01"
    assert result["requested_end"] == "2024-01-31"
    assert len(result["events"]) == 1
    assert result["events"][0]["title"] == "Product update"
    assert result["events"][0]["normalized_title"] == "product update"
    assert result["events"][0]["count_date"] == "2024-01-15"
    assert result["events"][0]["canonical_url"] == "https://example.com/news?id=1"


def test_normalize_observations_uses_event_date_and_preserves_cross_channel_records():
    event = {"published_date": "2024-01-05", "event_date": "2024-01-20", "title": "Investor day", "url": "https://example.com/item"}

    press = normalize_observations("NVDA", "press_releases", [event], "2024-01-01", "2024-01-31")
    presentation = normalize_observations("NVDA", "events_presentations", [event], "2024-01-01", "2024-01-31")

    assert press["events"][0]["count_date"] == "2024-01-05"
    assert presentation["events"][0]["count_date"] == "2024-01-20"


def test_normalize_observations_maps_adapter_date_field_by_channel():
    event = {"date": "2024-01-20", "title": "Investor day", "url": "https://example.com/item"}

    result = normalize_observations("NVDA", "events_presentations", [event], "2024-01-01", "2024-01-31")

    assert result["events"][0]["event_date"] == "2024-01-20"
    assert result["events"][0]["count_date"] == "2024-01-20"


def test_normalize_observations_rejects_future_press_release_but_excludes_future_presentation():
    future_press = {"published_date": "2024-02-01", "title": "Future", "url": "https://example.com/future"}
    with pytest.raises(ValueError, match="future press release date"):
        normalize_observations("NVDA", "press_releases", [future_press], "2024-01-01", "2024-01-31")

    future_event = {"event_date": "2024-02-01", "title": "Future", "url": "https://example.com/future"}
    result = normalize_observations("NVDA", "events_presentations", [future_event], "2024-01-01", "2024-01-31")
    assert result["events"] == []


@pytest.mark.parametrize(
    "event",
    [
        {"published_date": "2024-01-01", "url": "https://example.com"},
        {"published_date": "2024-01-01", "title": "Missing URL", "url": "file:///bad"},
    ],
)
def test_normalize_observations_rejects_missing_title_or_unsafe_url(event):
    with pytest.raises(ValueError):
        normalize_observations("NVDA", "press_releases", [event], "2024-01-01", "2024-01-31")


def test_normalize_observations_rejects_null_title():
    event = {"published_date": "2024-01-01", "title": None, "url": "https://example.com"}

    with pytest.raises(ValueError, match="event title is required"):
        normalize_observations("NVDA", "press_releases", [event], "2024-01-01", "2024-01-31")


@pytest.mark.parametrize(
    ("title", "source_type"),
    [
        ("Announces Fourth Quarter Financial Results", "press_releases"),
        ("Q2 Earnings Conference Call", "events_presentations"),
        ("Fiscal 2024 Annual Results", "press_releases"),
        ("Q1 2024 Earnings Release", "press_releases"),
        ("FY2024 Financial Results", "press_releases"),
        ("Earnings Release", "press_releases"),
        ("Q2 Results Presentation", "events_presentations"),
        ("Q2 Product Segment and Financial Results", "press_releases"),
    ],
)
def test_classify_title_by_rule_detects_narrow_earnings_titles(title, source_type):
    assert classify_title_by_rule(title, source_type) == "earnings"


@pytest.mark.parametrize(
    "title",
    [
        "Growth strategy update",
        "Guidance platform launch",
        "Earnings opportunity",
        "Reports customer results",
        "Q2 earnings opportunity",
        "FY2024 Earnings Opportunity",
        "Q2 release",
        "FY2024 release",
        "Quarterly earnings opportunity",
        "Q2 product results",
        "Q2 results update",
        "Product results presentation",
    ],
)
def test_classify_title_by_rule_does_not_treat_generic_economic_words_as_earnings(title):
    assert classify_title_by_rule(title, "press_releases") is None


def test_merge_classifications_uses_rules_and_valid_model_rows():
    events = [
        {"id": 1, "title": "Announces Fourth Quarter Financial Results", "source_type": "press_releases"},
        {"id": 2, "title": "New product launch", "source_type": "press_releases"},
    ]

    result = merge_classifications(
        events,
        {"classifications": [{"id": 2, "earnings_state": "non_earnings", "reason": "product"}]},
    )

    assert [(item["id"], item["earnings_state"], item["classification_method"]) for item in result] == [
        (1, "earnings", "rule_v1"),
        (2, "non_earnings", "llm_v1"),
    ]


@pytest.mark.parametrize(
    "payload",
    [
        None,
        {"classifications": []},
        {"classifications": [{"id": 1, "earnings_state": "non_earnings", "reason": "a"}, {"id": 1, "earnings_state": "non_earnings", "reason": "b"}]},
        {"classifications": [{"id": 99, "earnings_state": "non_earnings", "reason": "unknown"}]},
    ],
)
def test_merge_classifications_makes_missing_duplicate_and_unknown_model_output_ambiguous(payload):
    events = [{"id": 1, "title": "New product launch", "source_type": "press_releases"}]

    result = merge_classifications(events, payload)

    assert result[0]["earnings_state"] == "ambiguous"


def test_merge_classifications_makes_rule_model_conflict_ambiguous():
    events = [{"id": 1, "title": "Announces Fourth Quarter Financial Results", "source_type": "press_releases"}]

    result = merge_classifications(
        events,
        {"classifications": [{"id": 1, "earnings_state": "non_earnings", "reason": "conflict"}]},
    )

    assert result[0]["earnings_state"] == "ambiguous"


def test_merge_classifications_makes_valid_rows_ambiguous_when_payload_contains_unknown_id():
    events = [
        {"id": 1, "title": "New product launch", "source_type": "press_releases"},
        {"id": 2, "title": "New partnership", "source_type": "press_releases"},
    ]

    result = merge_classifications(
        events,
        {
            "classifications": [
                {"id": 1, "earnings_state": "non_earnings", "reason": "product"},
                {"id": 99, "earnings_state": "non_earnings", "reason": "unknown"},
            ]
        },
    )

    assert [item["earnings_state"] for item in result] == ["ambiguous", "ambiguous"]


def test_merge_classifications_maps_model_ids_by_position_when_events_have_string_ids():
    events = [{"event_id": "ire_a", "title": "New product launch", "source_type": "press_releases"}]

    result = merge_classifications(
        events,
        {"classifications": [{"id": 1, "earnings_state": "non_earnings", "reason": "product"}]},
    )

    assert result[0]["earnings_state"] == "non_earnings"


def test_merge_classifications_handles_unhashable_event_ids_as_ambiguous():
    events = [{"id": [], "title": "New product launch", "source_type": "press_releases"}]

    result = merge_classifications(
        events,
        {"classifications": [{"id": 1, "earnings_state": "non_earnings", "reason": "product"}]},
    )

    assert result[0]["earnings_state"] == "ambiguous"


def test_merge_classifications_handles_duplicate_event_ids_as_ambiguous():
    events = [
        {"id": 1, "title": "New product launch", "source_type": "press_releases"},
        {"id": 1, "title": "Business update", "source_type": "press_releases"},
    ]

    result = merge_classifications(
        events,
        {"classifications": [{"id": 1, "earnings_state": "non_earnings", "reason": "one"}]},
    )

    assert [item["earnings_state"] for item in result] == ["ambiguous", "ambiguous"]


def test_domain_public_functions_advertise_return_types():
    assert normalize_request.__annotations__["return"] is dict
    assert normalize_observations.__annotations__["return"] is dict


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("http://example.com:80/path", "http://example.com/path"),
        ("http://example.com:443/path", "http://example.com:443/path"),
        ("https://example.com:443/path", "https://example.com/path"),
        ("https://example.com:80/path", "https://example.com:80/path"),
    ],
)
def test_canonicalize_public_url_preserves_explicit_non_default_port(url, expected):
    assert canonicalize_public_url(url) == expected

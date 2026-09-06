import socket
from datetime import date

import pytest

from app.agents.catalyst_research.domain import (
    canonicalize_public_url,
    classify_title_by_rule,
    merge_classifications,
    normalize_observations,
    normalize_request,
    url_host,
    validate_redirect_chain,
)


@pytest.mark.parametrize("ticker, expected", [(" nvda ", "NVDA"), ("aapl", "AAPL")])
def test_normalize_request_normalizes_ticker_and_window(ticker, expected):
    result = normalize_request(ticker, years=2, as_of=date(2024, 2, 29))

    assert result == {
        "ticker": expected,
        "years": 2,
        "as_of": "2024-02-29",
        "start": "2022-02-28",
        "end": "2024-02-29",
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
        {"id": 4, "published_date": "2024-02-01", "title": "Future", "url": "https://example.com/future"},
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


@pytest.mark.parametrize(
    ("title", "source_type"),
    [
        ("Announces Fourth Quarter Financial Results", "press_releases"),
        ("Q2 Earnings Conference Call", "events_presentations"),
        ("Fiscal 2024 Annual Results", "press_releases"),
        ("Q1 2024 Earnings Release", "press_releases"),
        ("FY2024 Financial Results", "press_releases"),
    ],
)
def test_classify_title_by_rule_detects_narrow_earnings_titles(title, source_type):
    assert classify_title_by_rule(title, source_type) == "earnings"


@pytest.mark.parametrize(
    "title",
    ["Growth strategy update", "Guidance platform launch", "Earnings opportunity", "Reports customer results"],
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


def test_merge_classifications_maps_model_ids_by_position_when_events_have_string_ids():
    events = [{"event_id": "ire_a", "title": "New product launch", "source_type": "press_releases"}]

    result = merge_classifications(
        events,
        {"classifications": [{"id": 1, "earnings_state": "non_earnings", "reason": "product"}]},
    )

    assert result[0]["earnings_state"] == "non_earnings"

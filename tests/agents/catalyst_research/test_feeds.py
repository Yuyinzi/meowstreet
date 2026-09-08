import hashlib
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from pathlib import Path

import httpx
import pytest

from app.agents.catalyst_research.extraction.feeds import fetch_feed, parse_feed
from app.http_client import HttpClient


FIXTURES = Path(__file__).parent / "fixtures" / "v1_1"
RSS_XML = (FIXTURES / "nvda-news.xml").read_text(encoding="utf-8")
ATOM_XML = (FIXTURES / "atom-events.xml").read_text(encoding="utf-8")

VALID_RSS_XML = """<rss version="2.0"><channel>
<item><title>NVDA Item</title><link>https://nvidianews.nvidia.com/news/item</link><guid>nvda-1</guid><pubDate>Sun, 06 Sep 2026 10:00:00 GMT</pubDate><description>Latest item.</description></item>
<item><title>NVDA Older</title><link>https://nvidianews.nvidia.com/news/older</link><guid>nvda-2</guid><pubDate>Fri, 04 Sep 2026 10:00:00 GMT</pubDate><description>Older item.</description></item>
</channel></rss>"""


def endpoint_payload(endpoint_type="rss", **overrides):
    base = {
        "endpoint_id": "cse_nvda_feed",
        "ticker": "NVDA",
        "channel": "press_releases",
        "endpoint_type": endpoint_type,
        "url": "https://nvidianews.nvidia.com/news/rss",
        "domain": "nvidia.com",
        "status": "active",
    }
    base.update(overrides)
    return base


def client_for(handler):
    transport = httpx.MockTransport(handler)
    return HttpClient(transport=transport, sleep=lambda _: None, max_attempts=1)


def test_parse_rss_normalizes_items_without_using_guid_as_url():
    result = parse_feed(RSS_XML, endpoint_payload("rss"))
    assert result["format"] == "rss"
    assert result["items"][0] == {
        "external_guid": "nvda-100",
        "title": "NVIDIA Announces New Platform",
        "url": "https://nvidianews.nvidia.com/news/new-platform",
        "published_at": "2026-09-07T12:00:00+00:00",
        "summary": "NVIDIA announced a new platform.",
        "discovery_method": "rss",
        "endpoint_id": "cse_nvda_feed",
    }


def test_parse_rss_reads_cdata_and_strips_tags_from_content_summary():
    result = parse_feed(RSS_XML, endpoint_payload("rss"))
    summaries = [item["summary"] for item in result["items"]]
    assert summaries == [
        "NVIDIA announced a new platform.",
        "NVIDIA will participate in an upcoming investor conference.",
        "NVIDIA research won a scientific award.",
    ]


def test_parse_atom_uses_alternate_link_and_updated_date():
    result = parse_feed(ATOM_XML, endpoint_payload("atom", channel="events_presentations", url="https://investor.nvidia.com/events.atom"))
    assert result["format"] == "atom"
    first = result["items"][0]
    assert first["url"].endswith("/events/investor-day")
    assert first["url"] == "https://investor.nvidia.com/events/investor-day"
    assert first["published_at"] == "2026-09-05T09:30:00+00:00"
    assert first["external_guid"] == "urn:nvda:event:investor-day-2026"
    assert first["discovery_method"] == "atom"
    assert result["items"][1]["published_at"] == "2026-08-26T17:00:00+00:00"


def test_parse_atom_falls_back_to_published_date_and_link_without_rel():
    xml = """<feed xmlns="http://www.w3.org/2005/Atom"><entry>
<id>urn:e1</id><title>Only Published</title>
<link href="https://investor.nvidia.com/events/only-published"/>
<published>2026-09-01T08:00:00Z</published>
</entry></feed>"""
    result = parse_feed(xml, endpoint_payload("atom", url="https://investor.nvidia.com/events.atom"))
    assert result["items"][0]["published_at"] == "2026-09-01T08:00:00+00:00"
    assert result["items"][0]["url"] == "https://investor.nvidia.com/events/only-published"


def test_parse_feed_reads_items_under_namespaced_rss():
    xml = """<rss version="2.0" xmlns="http://purl.org/rss/2.0/"><channel>
<item><title>Namespaced</title><link>https://nvidianews.nvidia.com/news/namespaced</link><guid>ns-1</guid><pubDate>Sat, 05 Sep 2026 00:00:00 GMT</pubDate></item>
</channel></rss>"""
    result = parse_feed(xml, endpoint_payload("rss"))
    assert result["format"] == "rss"
    assert result["items"][0]["title"] == "Namespaced"


def test_parse_feed_keeps_guidless_items_with_none_external_guid():
    xml = """<rss version="2.0"><channel>
<item><title>No Guid</title><link>https://nvidianews.nvidia.com/news/no-guid</link><pubDate>Sat, 05 Sep 2026 00:00:00 GMT</pubDate></item>
</channel></rss>"""
    result = parse_feed(xml, endpoint_payload("rss"))
    assert len(result["items"]) == 1
    assert result["items"][0]["external_guid"] is None


def test_parse_feed_deduplicates_reused_guids_keeping_newest_entry():
    xml = """<rss version="2.0"><channel>
<item><title>Reused Newer</title><link>https://nvidianews.nvidia.com/news/reused-a</link><guid>dup-1</guid><pubDate>Sun, 06 Sep 2026 00:00:00 GMT</pubDate></item>
<item><title>Reused Older</title><link>https://nvidianews.nvidia.com/news/reused-b</link><guid>dup-1</guid><pubDate>Fri, 04 Sep 2026 00:00:00 GMT</pubDate></item>
</channel></rss>"""
    result = parse_feed(xml, endpoint_payload("rss"))
    assert result["item_count"] == 1
    assert result["items"][0]["title"] == "Reused Newer"


def test_parse_feed_deduplicates_guidless_entries_by_canonical_url():
    xml = """<rss version="2.0"><channel>
<item><title>First Copy</title><link>https://nvidianews.nvidia.com/news/shared?utm_source=a</link><pubDate>Sun, 06 Sep 2026 00:00:00 GMT</pubDate></item>
<item><title>Second Copy</title><link>https://nvidianews.nvidia.com/news/shared?utm_source=b</link><pubDate>Fri, 04 Sep 2026 00:00:00 GMT</pubDate></item>
</channel></rss>"""
    result = parse_feed(xml, endpoint_payload("rss"))
    assert result["item_count"] == 1
    assert result["items"][0]["url"] == "https://nvidianews.nvidia.com/news/shared"


def test_parse_feed_sorts_out_of_order_entries_newest_first():
    xml = """<rss version="2.0"><channel>
<item><title>oldest</title><link>https://nvidianews.nvidia.com/news/oldest</link><guid>g1</guid><pubDate>Tue, 01 Sep 2026 00:00:00 GMT</pubDate></item>
<item><title>newest</title><link>https://nvidianews.nvidia.com/news/newest</link><guid>g2</guid><pubDate>Mon, 07 Sep 2026 00:00:00 GMT</pubDate></item>
<item><title>middle</title><link>https://nvidianews.nvidia.com/news/middle</link><guid>g3</guid><pubDate>Thu, 03 Sep 2026 00:00:00 GMT</pubDate></item>
</channel></rss>"""
    result = parse_feed(xml, endpoint_payload("rss"))
    assert [item["title"] for item in result["items"]] == ["newest", "middle", "oldest"]
    assert result["newest_item_at"] == "2026-09-07T00:00:00+00:00"


def test_parse_feed_tolerates_invalid_dates_and_sorts_them_last():
    xml = """<rss version="2.0"><channel>
<item><title>Broken Date</title><link>https://nvidianews.nvidia.com/news/broken</link><guid>g-broken</guid><pubDate>not a date</pubDate></item>
<item><title>Dated</title><link>https://nvidianews.nvidia.com/news/dated</link><guid>g-dated</guid><pubDate>Mon, 07 Sep 2026 00:00:00 GMT</pubDate></item>
</channel></rss>"""
    result = parse_feed(xml, endpoint_payload("rss"))
    assert result["items"][1]["published_at"] is None
    assert result["items"][1]["title"] == "Broken Date"
    assert result["newest_item_at"] == "2026-09-07T00:00:00+00:00"


def test_parse_feed_tolerates_invalid_atom_dates():
    xml = """<feed xmlns="http://www.w3.org/2005/Atom"><entry>
<id>urn:e2</id><title>Broken Atom Date</title>
<link rel="alternate" href="https://investor.nvidia.com/events/broken"/>
<updated>not-a-date</updated>
</entry></feed>"""
    result = parse_feed(xml, endpoint_payload("atom", url="https://investor.nvidia.com/events.atom"))
    assert result["items"][0]["published_at"] is None


def test_parse_feed_skips_entries_missing_link():
    xml = """<rss version="2.0"><channel>
<item><title>No Link</title><guid>g-nolink</guid><pubDate>Mon, 07 Sep 2026 00:00:00 GMT</pubDate></item>
<item><title>Has Link</title><link>https://nvidianews.nvidia.com/news/has-link</link><guid>g-haslink</guid><pubDate>Sun, 06 Sep 2026 00:00:00 GMT</pubDate></item>
</channel></rss>"""
    result = parse_feed(xml, endpoint_payload("rss"))
    assert result["item_count"] == 1
    assert result["items"][0]["title"] == "Has Link"


def test_parse_feed_keeps_entries_with_missing_title_as_empty_title():
    xml = """<rss version="2.0"><channel>
<item><link>https://nvidianews.nvidia.com/news/no-title</link><guid>g-notitle</guid><pubDate>Mon, 07 Sep 2026 00:00:00 GMT</pubDate></item>
</channel></rss>"""
    result = parse_feed(xml, endpoint_payload("rss"))
    assert result["item_count"] == 1
    assert result["items"][0]["title"] == ""


def test_parse_feed_skips_entries_with_unapproved_url_hosts():
    xml = """<rss version="2.0"><channel>
<item><title>Off Domain</title><link>https://evil.example.net/news/off-domain</link><guid>g-off</guid><pubDate>Mon, 07 Sep 2026 00:00:00 GMT</pubDate></item>
<item><title>On Domain</title><link>https://nvidianews.nvidia.com/news/on-domain</link><guid>g-on</guid><pubDate>Sun, 06 Sep 2026 00:00:00 GMT</pubDate></item>
</channel></rss>"""
    result = parse_feed(xml, endpoint_payload("rss"))
    assert result["item_count"] == 1
    assert result["items"][0]["title"] == "On Domain"


def test_parse_feed_resolves_relative_links_against_feed_url():
    xml = """<rss version="2.0"><channel>
<item><title>Relative</title><link>/news/relative</link><guid>g-rel</guid><pubDate>Mon, 07 Sep 2026 00:00:00 GMT</pubDate></item>
</channel></rss>"""
    result = parse_feed(xml, endpoint_payload("rss"))
    assert result["items"][0]["url"] == "https://nvidianews.nvidia.com/news/relative"
    assert result["final_url"] == "https://nvidianews.nvidia.com/news/rss"


def test_parse_feed_returns_empty_feed_with_zero_items():
    xml = """<rss version="2.0"><channel><title>Quiet Feed</title></channel></rss>"""
    result = parse_feed(xml, endpoint_payload("rss"))
    assert result["format"] == "rss"
    assert result["items"] == []
    assert result["item_count"] == 0
    assert result["newest_item_at"] is None
    assert result["final_url"] == "https://nvidianews.nvidia.com/news/rss"
    assert len(result["content_hash"]) == 64


def test_parse_feed_caps_items_at_max_items_keeping_newest():
    entries = []
    for index in range(505):
        published = datetime(2026, 9, 7, tzinfo=UTC) - timedelta(days=index)
        entries.append(
            f"<item><title>n-{index}</title><link>https://nvidianews.nvidia.com/news/{index}</link>"
            f"<guid>guid-{index}</guid><pubDate>{format_datetime(published)}</pubDate></item>"
        )
    xml = f'<rss version="2.0"><channel>{"".join(entries)}</channel></rss>'
    result = parse_feed(xml, endpoint_payload("rss"))
    assert result["item_count"] == 500
    assert result["items"][0]["external_guid"] == "guid-0"
    assert result["items"][-1]["external_guid"] == "guid-499"
    assert result["newest_item_at"] == "2026-09-07T00:00:00+00:00"


@pytest.mark.parametrize("max_items", [0, -1, True, "10"])
def test_parse_feed_rejects_invalid_max_items(max_items):
    with pytest.raises(ValueError, match="max items"):
        parse_feed(RSS_XML, endpoint_payload("rss"), max_items=max_items)


def test_parse_feed_rejects_blank_or_non_string_xml():
    with pytest.raises(ValueError, match="feed xml is required"):
        parse_feed("   ", endpoint_payload("rss"))
    with pytest.raises(ValueError, match="feed xml is required"):
        parse_feed(b"<rss/>", endpoint_payload("rss"))


def test_parse_feed_rejects_malformed_xml():
    with pytest.raises(ValueError, match="feed xml is invalid"):
        parse_feed("<rss version=\"2.0\"><channel><item>", endpoint_payload("rss"))


def test_parse_feed_rejects_unsupported_feed_format():
    with pytest.raises(ValueError, match="feed format is unsupported"):
        parse_feed("<html><body>not a feed</body></html>", endpoint_payload("rss"))


def test_parse_feed_rejects_invalid_endpoints():
    with pytest.raises(ValueError, match="endpoint is required"):
        parse_feed(RSS_XML, None)
    with pytest.raises(ValueError, match="endpoint id is required"):
        parse_feed(RSS_XML, endpoint_payload("rss", endpoint_id=""))
    with pytest.raises(ValueError, match="endpoint type is invalid"):
        parse_feed(RSS_XML, endpoint_payload("search_domain"))
    with pytest.raises(ValueError, match="endpoint url is required"):
        parse_feed(RSS_XML, endpoint_payload("rss", url=None, domain=None))


def test_fetch_feed_sends_feed_accept_header_without_provider_auth_headers():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, headers={"Content-Type": "application/rss+xml"}, content=VALID_RSS_XML.encode("utf-8"))

    result = fetch_feed(
        endpoint_payload(),
        http_client=client_for(handler),
        resolver=lambda host: ["93.184.216.34"],
        approved_domains={"nvidia.com"},
    )

    assert len(requests) == 1
    request = requests[0]
    assert request.method == "GET"
    assert "application/rss+xml" in request.headers["accept"]
    assert request.headers["user-agent"].startswith("Meowstreet/")
    assert "authorization" not in request.headers
    assert not any(key.startswith("x-firecrawl") for key in request.headers)
    assert result["format"] == "rss"
    assert result["items"][0]["discovery_method"] == "rss"
    assert result["items"][0]["endpoint_id"] == "cse_nvda_feed"


def test_fetch_feed_returns_normalized_result_without_raw_xml():
    def handler(request):
        return httpx.Response(200, headers={"Content-Type": "application/rss+xml"}, content=VALID_RSS_XML.encode("utf-8"))

    result = fetch_feed(
        endpoint_payload(),
        http_client=client_for(handler),
        resolver=lambda host: ["93.184.216.34"],
        approved_domains={"nvidia.com"},
    )

    assert set(result) == {"format", "items", "item_count", "newest_item_at", "content_hash", "final_url"}
    assert result["content_hash"] == hashlib.sha256(VALID_RSS_XML.encode("utf-8")).hexdigest()
    assert result["final_url"] == "https://nvidianews.nvidia.com/news/rss"
    assert result["newest_item_at"] == "2026-09-06T10:00:00+00:00"
    assert all(set(item) == {"external_guid", "title", "url", "published_at", "summary", "discovery_method", "endpoint_id"} for item in result["items"])
    assert "channel" not in str(result)


@pytest.mark.parametrize(
    "content_type",
    ["application/rss+xml", "application/atom+xml", "application/xml", "text/xml"],
)
def test_fetch_feed_accepts_xml_content_types(content_type):
    def handler(request):
        return httpx.Response(200, headers={"Content-Type": f"{content_type}; charset=utf-8"}, content=VALID_RSS_XML.encode("utf-8"))

    result = fetch_feed(
        endpoint_payload(),
        http_client=client_for(handler),
        resolver=lambda host: ["93.184.216.34"],
        approved_domains={"nvidia.com"},
    )
    assert result["format"] == "rss"


@pytest.mark.parametrize("content_type", ["text/html", "application/json", ""])
def test_fetch_feed_rejects_non_xml_content_types(content_type):
    def handler(request):
        return httpx.Response(200, headers={"Content-Type": content_type}, content=VALID_RSS_XML.encode("utf-8"))

    with pytest.raises(ValueError, match="feed content type is not xml"):
        fetch_feed(
            endpoint_payload(),
            http_client=client_for(handler),
            resolver=lambda host: ["93.184.216.34"],
            approved_domains={"nvidia.com"},
        )


def test_fetch_follows_safe_redirect_within_approved_domains():
    requests = []

    def handler(request):
        requests.append(str(request.url))
        if request.url.path == "/old-rss":
            return httpx.Response(302, headers={"Location": "https://news.nvidia.com/rss"})
        return httpx.Response(200, headers={"Content-Type": "application/rss+xml"}, content=VALID_RSS_XML.encode("utf-8"))

    result = fetch_feed(
        endpoint_payload(url="https://nvidianews.nvidia.com/old-rss"),
        http_client=client_for(handler),
        resolver=lambda host: ["93.184.216.34"],
        approved_domains={"nvidia.com"},
    )

    assert requests == ["https://nvidianews.nvidia.com/old-rss", "https://news.nvidia.com/rss"]
    assert result["final_url"] == "https://news.nvidia.com/rss"


def test_fetch_rejects_redirect_host_outside_approved_domains():
    def handler(request):
        if request.url.host == "nvidianews.nvidia.com":
            return httpx.Response(302, headers={"Location": "https://feeds.thirdparty.net/rss"})
        return httpx.Response(200, headers={"Content-Type": "application/rss+xml"}, content=VALID_RSS_XML.encode("utf-8"))

    with pytest.raises(ValueError, match="feed redirect host is not allowed"):
        fetch_feed(
            endpoint_payload(),
            http_client=client_for(handler),
            resolver=lambda host: ["93.184.216.34"],
            approved_domains={"nvidia.com"},
        )


def test_fetch_rejects_private_redirect_target():
    def handler(request):
        return httpx.Response(302, headers={"Location": "https://internal.corp/rss"})

    def resolver(host):
        return ["192.168.1.8"] if host == "internal.corp" else ["93.184.216.34"]

    with pytest.raises(ValueError, match="url host is not public"):
        fetch_feed(
            endpoint_payload(),
            http_client=client_for(handler),
            resolver=resolver,
            approved_domains={"nvidia.com", "internal.corp"},
        )


def test_fetch_feed_enforces_response_size_limit():
    def handler(request):
        return httpx.Response(200, headers={"Content-Type": "application/rss+xml"}, content=b"<rss>" + b"x" * 5000)

    with pytest.raises(ValueError, match="feed response exceeds maximum bytes"):
        fetch_feed(
            endpoint_payload(),
            http_client=client_for(handler),
            resolver=lambda host: ["93.184.216.34"],
            approved_domains={"nvidia.com"},
            max_bytes=1024,
        )


def test_fetch_feed_rejects_empty_body():
    def handler(request):
        return httpx.Response(200, headers={"Content-Type": "application/rss+xml"}, content=b" \n\t")

    with pytest.raises(ValueError, match="feed body is empty"):
        fetch_feed(
            endpoint_payload(),
            http_client=client_for(handler),
            resolver=lambda host: ["93.184.216.34"],
            approved_domains={"nvidia.com"},
        )


def test_fetch_feed_normalizes_timeout_and_http_errors():
    def timeout_handler(request):
        raise httpx.ReadTimeout("timed out", request=request)

    with pytest.raises(ValueError, match="feed request timed out"):
        fetch_feed(
            endpoint_payload(),
            http_client=client_for(timeout_handler),
            resolver=lambda host: ["93.184.216.34"],
            approved_domains={"nvidia.com"},
        )

    def error_handler(request):
        return httpx.Response(503, request=request)

    with pytest.raises(ValueError, match="feed request failed"):
        fetch_feed(
            endpoint_payload(),
            http_client=client_for(error_handler),
            resolver=lambda host: ["93.184.216.34"],
            approved_domains={"nvidia.com"},
        )


def test_fetch_feed_validates_initial_dns_before_request():
    requests = []

    def handler(request):
        requests.append(str(request.url))
        return httpx.Response(200, headers={"Content-Type": "application/rss+xml"}, content=VALID_RSS_XML.encode("utf-8"))

    with pytest.raises(ValueError, match="url host is not public"):
        fetch_feed(
            endpoint_payload(),
            http_client=client_for(handler),
            resolver=lambda host: ["192.168.1.8"],
            approved_domains={"nvidia.com"},
        )

    assert requests == []


def test_fetch_feed_requires_approved_domains():
    def handler(request):
        return httpx.Response(200, headers={"Content-Type": "application/rss+xml"}, content=VALID_RSS_XML.encode("utf-8"))

    with pytest.raises(ValueError, match="approved domains are required"):
        fetch_feed(
            endpoint_payload(),
            http_client=client_for(handler),
            resolver=lambda host: ["93.184.216.34"],
            approved_domains=set(),
        )

    with pytest.raises(ValueError, match="approved domain is invalid"):
        fetch_feed(
            endpoint_payload(),
            http_client=client_for(handler),
            resolver=lambda host: ["93.184.216.34"],
            approved_domains={"nvidia.com", ""},
        )


def test_fetch_feed_rejects_invalid_endpoints():
    def handler(request):
        return httpx.Response(200, headers={"Content-Type": "application/rss+xml"}, content=VALID_RSS_XML.encode("utf-8"))

    with pytest.raises(ValueError, match="endpoint type is invalid"):
        fetch_feed(
            endpoint_payload("archive"),
            http_client=client_for(handler),
            resolver=lambda host: ["93.184.216.34"],
            approved_domains={"nvidia.com"},
        )

    with pytest.raises(ValueError, match="endpoint url is required"):
        fetch_feed(
            endpoint_payload(url=None, domain=None),
            http_client=client_for(handler),
            resolver=lambda host: ["93.184.216.34"],
            approved_domains={"nvidia.com"},
        )

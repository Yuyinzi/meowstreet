import httpx
import pytest

from app.agents.catalyst_research.extraction.articles import extract_direct_article
from app.http_client import HttpClient


URL = "https://nvidianews.nvidia.com/news/nvidia-announces-new-platform"
RESOLVER = {"nvidianews.nvidia.com": ["93.184.216.34"], "other.example.com": ["93.184.216.35"]}
COMPANY = {"ticker": "NVDA", "company_name": "NVIDIA Corporation"}
BODY = "<p>NVIDIA announced a new platform in a press release for investors.</p>"
ARTICLE_HTML = """<!doctype html>
<html>
<head>
<meta property="og:title" content="NVIDIA Announces New Platform" />
<meta property="article:published_time" content="2026-09-07T12:00:00Z" />
</head>
<body><h1>Visible Heading</h1>""" + BODY + "</body></html>"


def client_for(html, *, status=200, content_type="text/html; charset=utf-8"):
    def handler(request):
        return httpx.Response(status, headers={"Content-Type": content_type}, content=html.encode("utf-8"))

    return HttpClient(transport=httpx.MockTransport(handler), sleep=lambda _: None, max_attempts=1)


def extract(html, *, client=None, candidate=None, company=None, channel=None, approved_domains=None, **kwargs):
    return extract_direct_article(
        URL,
        http_client=client if client is not None else client_for(html),
        approved_domains={"nvidia.com"} if approved_domains is None else approved_domains,
        candidate=candidate,
        company=company,
        channel=channel,
        resolver=RESOLVER,
        **kwargs,
    )


def test_extract_direct_article_normalizes_static_html():
    result = extract_direct_article(
        URL,
        http_client=client_for(ARTICLE_HTML),
        approved_domains={"nvidianews.nvidia.com"},
        resolver=RESOLVER,
    )

    assert result["status"] == "extracted"
    assert result["title"] == "NVIDIA Announces New Platform"
    assert result["published_at"] == "2026-09-07T12:00:00+00:00"
    assert result["provider"] == "direct_http"
    assert result["url"] == URL
    assert result["final_url"] == URL
    assert "NVIDIA" in result["text"]


def test_json_ld_metadata_takes_priority_over_open_graph():
    html = """<html><head>
<script type="application/ld+json">
{"@context": "https://schema.org", "@type": "NewsArticle", "headline": "JSON-LD Headline", "datePublished": "2026-08-01T09:30:00Z", "url": "https://nvidianews.nvidia.com/news/json-ld-story"}
</script>
<meta property="og:title" content="OG Headline" />
<meta property="article:published_time" content="2026-09-07T12:00:00Z" />
</head><body><h1>Visible Heading</h1><time datetime="2026-07-04T10:00:00Z"></time>""" + BODY + "</body></html>"

    result = extract(html)

    assert result["title"] == "JSON-LD Headline"
    assert result["published_at"] == "2026-08-01T09:30:00+00:00"


def test_json_ld_graph_nodes_are_considered():
    html = """<html><head>
<script type="application/ld+json">
{"@graph": [{"@type": "Organization", "name": "NVIDIA"}, {"@type": "NewsArticle", "headline": "Graph Headline", "datePublished": "2026-08-02T09:30:00Z"}]}
</script>
</head><body><h1>Visible Heading</h1>""" + BODY + "</body></html>"

    result = extract(html)

    assert result["title"] == "Graph Headline"
    assert result["published_at"] == "2026-08-02T09:30:00+00:00"


def test_open_graph_metadata_precedes_visible_time_and_heading():
    html = """<html><head>
<meta property="og:title" content="OG Headline" />
<meta property="article:published_time" content="2026-09-07T12:00:00Z" />
</head><body><h1>Visible Heading</h1><time datetime="2026-07-04T10:00:00Z"></time>""" + BODY + "</body></html>"

    result = extract(html)

    assert result["title"] == "OG Headline"
    assert result["published_at"] == "2026-09-07T12:00:00+00:00"


def test_heading_and_time_element_fallback_before_candidate():
    html = "<html><body><h1>Visible Headline</h1><time datetime=\"2026-07-04T10:00:00Z\">July 4</time>" + BODY + "</body></html>"
    candidate = {"title": "Candidate Title", "published_at": "2026-06-01"}

    result = extract(html, candidate=candidate)

    assert result["title"] == "Visible Headline"
    assert result["published_at"] == "2026-07-04T10:00:00+00:00"


def test_candidate_metadata_is_last_fallback():
    html = "<html><body><p>NVIDIA announced a new platform for developers and partners worldwide.</p></body></html>"
    candidate = {"title": "Candidate Title", "published_at": "2026-06-01"}

    result = extract(html, candidate=candidate)

    assert result["title"] == "Candidate Title"
    assert result["published_at"] == "2026-06-01T00:00:00+00:00"


def test_time_element_text_is_used_without_datetime_attribute():
    html = "<html><body><h1>Visible Headline</h1><time>2026-05-04T10:00:00Z</time>" + BODY + "</body></html>"

    result = extract(html)

    assert result["published_at"] == "2026-05-04T10:00:00+00:00"


def test_missing_title_after_candidate_fallback_is_rejected():
    html = "<html><body><p>Some plain article body text without any heading at all.</p></body></html>"

    with pytest.raises(ValueError, match="metadata_missing"):
        extract(html, candidate={"published_at": "2026-06-01"})


def test_missing_date_after_candidate_fallback_is_rejected():
    html = "<html><body><h1>Visible Headline</h1><p>Some plain article body text without dates.</p></body></html>"

    with pytest.raises(ValueError, match="metadata_missing"):
        extract(html, candidate={"title": "Candidate Title"})


def test_final_url_outside_approved_domains_is_rejected():
    def handler(request):
        if request.url.host == "other.example.com":
            return httpx.Response(200, headers={"Content-Type": "text/html"}, content=b"<p>other</p>")
        return httpx.Response(302, headers={"Location": "https://other.example.com/story"})

    client = HttpClient(transport=httpx.MockTransport(handler), sleep=lambda _: None, max_attempts=1)

    with pytest.raises(ValueError, match="redirect_not_allowed"):
        extract(ARTICLE_HTML, client=client)


def test_unsafe_json_ld_url_is_rejected():
    html = """<html><head>
<script type="application/ld+json">
{"@type": "NewsArticle", "headline": "Story", "datePublished": "2026-08-01T09:30:00Z", "url": "javascript:alert(1)"}
</script>
</head><body>""" + BODY + "</body></html>"

    with pytest.raises(ValueError, match="unsafe_metadata_url"):
        extract(html)


def test_empty_visible_content_is_rejected():
    html = "<html><head><style>.hidden { color: red; }</style><script>var secret = 1;</script></head><body></body></html>"

    with pytest.raises(ValueError, match="empty_content"):
        extract(html)


def test_non_html_content_type_is_request_failed():
    with pytest.raises(ValueError, match="request_failed"):
        extract("anything", client=client_for("<p>x</p>", content_type="application/pdf"))


def test_request_error_is_stable_request_failed_outcome():
    def handler(request):
        return httpx.Response(503, content=b"unavailable")

    client = HttpClient(transport=httpx.MockTransport(handler), sleep=lambda _: None, max_attempts=1)

    with pytest.raises(ValueError, match="request_failed"):
        extract(ARTICLE_HTML, client=client)


def test_content_without_company_evidence_is_rejected():
    html = (
        "<html><body><h1>Platform Update</h1><time datetime=\"2026-07-04T10:00:00Z\"></time>"
        "<p>A generic platform update for developers and partners.</p></body></html>"
    )

    with pytest.raises(ValueError, match="identity_evidence_missing"):
        extract(html, company=COMPANY)


def test_content_without_channel_evidence_is_rejected():
    html = (
        "<html><body><h1>NVIDIA Platform Update</h1><time datetime=\"2026-07-04T10:00:00Z\"></time>"
        "<p>NVIDIA unveiled a new platform.</p></body></html>"
    )

    with pytest.raises(ValueError, match="channel_evidence_missing"):
        extract(html, company=COMPANY, channel="press_releases")


def test_company_and_channel_evidence_is_accepted():
    result = extract(ARTICLE_HTML, company=COMPANY, channel="press_releases")

    assert result["status"] == "extracted"


def test_invalid_channel_is_rejected():
    with pytest.raises(ValueError, match="candidate channel is invalid"):
        extract(ARTICLE_HTML, company=COMPANY, channel="browser")


def test_text_is_bounded_and_never_contains_raw_html():
    paragraph = "word " * 2000
    html = f"<html><body><h1>Visible Heading</h1><time datetime=\"2026-07-04T10:00:00Z\"></time><p>{paragraph}</p></body></html>"

    result = extract(html, max_text_chars=200)

    assert len(result["text"]) <= 200
    assert "<" not in result["text"]
    assert "html" not in result


def test_script_and_style_content_is_not_in_text():
    html = (
        "<html><head><script>var trackingSecret = 'leak-me-not';</script>"
        "<style>.leak-me-not { display: none; }</style></head>"
        "<body><h1>Visible Heading</h1><time datetime=\"2026-07-04T10:00:00Z\"></time>" + BODY + "</body></html>"
    )

    result = extract(html)

    assert "leak-me-not" not in result["text"]
    assert "trackingSecret" not in result["text"]


@pytest.mark.parametrize(
    "approved_domains",
    [[], set(), ["  "], [None], [42], "nvidia.com"],
)
def test_approved_domains_must_be_non_empty_strings(approved_domains):
    with pytest.raises(ValueError):
        extract(ARTICLE_HTML, approved_domains=approved_domains)


def test_candidate_must_be_a_mapping():
    with pytest.raises(ValueError, match="candidate is invalid"):
        extract(ARTICLE_HTML, candidate="not-a-mapping")

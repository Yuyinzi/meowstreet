import re

import pytest

from app.agents.catalyst_research.extraction.router import ExtractionRouter
from app.agents.catalyst_research.providers.firecrawl import FirecrawlProviderError


URL = "https://nvidianews.nvidia.com/news/nvidia-announces-new-platform"
SECOND_URL = "https://nvidianews.nvidia.com/news/nvidia-second-story"
DOMAINS = {"nvidia.com"}
OUTCOME_RE = re.compile(r"\A[a-z0-9_]{1,64}\Z")


def candidate(**overrides):
    base = {
        "url": URL,
        "title": "Candidate Title",
        "published_at": "2026-09-07T12:00:00+00:00",
        "channel": "press_releases",
    }
    base.update(overrides)
    return base


def company():
    return {"ticker": "NVDA", "company_name": "NVIDIA Corporation"}


def direct_article(**overrides):
    base = {
        "status": "extracted",
        "url": URL,
        "final_url": URL,
        "title": "NVIDIA Announces New Platform",
        "published_at": "2026-09-07T12:00:00+00:00",
        "text": "NVIDIA announced a new platform in a press release for investors.",
        "provider": "direct_http",
    }
    base.update(overrides)
    return base


def firecrawl_article(**overrides):
    base = {
        "url": URL,
        "final_url": URL,
        "title": "NVIDIA Announces New Platform",
        "markdown": "NVIDIA announced a new platform in a press release for investors.",
        "html": "<html><body>NVIDIA announced a new platform</body></html>",
        "published_at": "2026-09-07T12:00:00+00:00",
        "request_id": "fc-req-1",
        "provider": "firecrawl",
    }
    base.update(overrides)
    return base


class FakeDirect:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = []
        self.kwargs = []

    def __call__(self, url, **kwargs):
        self.calls.append(url)
        self.kwargs.append(kwargs)
        if self.error is not None:
            raise self.error
        return dict(self.result)


class FakeFirecrawl:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = []

    def extract(self, url):
        self.calls.append(url)
        if self.error is not None:
            raise self.error
        return self.result


def test_router_uses_firecrawl_only_after_direct_failure():
    direct = FakeDirect(error=ValueError("request_failed"))
    firecrawl = FakeFirecrawl(result=firecrawl_article())
    result = ExtractionRouter(direct, firecrawl).extract(candidate(), company=company(), approved_domains=DOMAINS)

    assert result["status"] == "extracted"
    assert result["extraction_provider"] == "firecrawl"
    assert result["title"] == "NVIDIA Announces New Platform"
    assert result["published_at"] == "2026-09-07T12:00:00+00:00"
    assert result["final_url"] == URL
    assert result["request_id"] == "fc-req-1"
    assert result["html"] == "<html><body>NVIDIA announced a new platform</body></html>"
    assert result["attempts"] == [
        {"provider": "direct_http", "outcome": "request_failed"},
        {"provider": "firecrawl", "outcome": "extracted"},
    ]
    assert direct.calls == [URL]
    assert firecrawl.calls == [URL]


def test_router_returns_direct_success_without_calling_firecrawl():
    direct = FakeDirect(result=direct_article())
    firecrawl = FakeFirecrawl(result=firecrawl_article())

    result = ExtractionRouter(direct, firecrawl).extract(candidate(), company=company(), approved_domains=DOMAINS)

    assert result["status"] == "extracted"
    assert result["extraction_provider"] == "direct_http"
    assert result["title"] == "NVIDIA Announces New Platform"
    assert result["attempts"] == [{"provider": "direct_http", "outcome": "extracted"}]
    assert firecrawl.calls == []


def test_router_passes_company_channel_and_domains_to_direct_extractor():
    direct = FakeDirect(result=direct_article())

    ExtractionRouter(direct).extract(candidate(), company=company(), approved_domains=DOMAINS)

    assert direct.kwargs[0]["company"] == company()
    assert direct.kwargs[0]["channel"] == "press_releases"
    assert direct.kwargs[0]["approved_domains"] == DOMAINS


def test_router_falls_back_to_manual_without_firecrawl():
    direct = FakeDirect(error=ValueError("request_failed"))

    result = ExtractionRouter(direct).extract(candidate(), company=company(), approved_domains=DOMAINS)

    assert result == {
        "status": "manual_review_required",
        "url": URL,
        "extraction_provider": "manual",
        "attempts": [{"provider": "direct_http", "outcome": "request_failed"}],
    }


def test_router_records_stable_attempts_when_both_providers_fail():
    direct = FakeDirect(error=ValueError("request_failed"))
    firecrawl = FakeFirecrawl(
        error=FirecrawlProviderError("payment_required", "firecrawl payment required", disable_provider=True)
    )
    router = ExtractionRouter(direct, firecrawl)

    result = router.extract(candidate(), company=company(), approved_domains=DOMAINS)

    assert result == {
        "status": "manual_review_required",
        "url": URL,
        "extraction_provider": "manual",
        "attempts": [
            {"provider": "direct_http", "outcome": "request_failed"},
            {"provider": "firecrawl", "outcome": "payment_required"},
        ],
    }
    assert router.firecrawl_disabled_reason == "payment_required"


@pytest.mark.parametrize(
    ("reason", "disable"),
    [
        ("authentication_failed", True),
        ("payment_required", True),
        ("rate_limited", False),
        ("timeout", False),
        ("provider_error", False),
    ],
)
def test_router_disables_firecrawl_for_later_urls_only_for_disabling_errors(reason, disable):
    direct = FakeDirect(error=ValueError("request_failed"))
    firecrawl = FakeFirecrawl(error=FirecrawlProviderError(reason, f"firecrawl {reason}", disable_provider=disable))
    router = ExtractionRouter(direct, firecrawl)

    first = router.extract(candidate(), company=company(), approved_domains=DOMAINS)
    assert first["status"] == "manual_review_required"

    second = router.extract(candidate(url=SECOND_URL), company=company(), approved_domains=DOMAINS)
    assert second["url"] == SECOND_URL
    assert second["status"] == "manual_review_required"

    if disable:
        assert router.firecrawl_disabled_reason == reason
        assert firecrawl.calls == [URL]
        assert second["attempts"] == [
            {"provider": "direct_http", "outcome": "request_failed"},
            {"provider": "firecrawl", "outcome": reason},
        ]
    else:
        assert router.firecrawl_disabled_reason is None
        assert firecrawl.calls == [URL, SECOND_URL]


@pytest.mark.parametrize(
    "result",
    [None, {}, {"markdown": ""}, {"markdown": "   "}, "not-a-mapping", 42],
)
def test_router_rejects_malformed_firecrawl_results(result):
    direct = FakeDirect(error=ValueError("request_failed"))
    firecrawl = FakeFirecrawl(result=result)

    outcome = ExtractionRouter(direct, firecrawl).extract(candidate(), company=company(), approved_domains=DOMAINS)

    assert outcome["status"] == "manual_review_required"
    assert outcome["attempts"][-1] == {"provider": "firecrawl", "outcome": "malformed_response"}


@pytest.mark.parametrize("final_url", ["https://other.example.com/story", "javascript:alert(1)", None])
def test_router_rejects_unsafe_firecrawl_final_urls(final_url):
    direct = FakeDirect(error=ValueError("request_failed"))
    firecrawl = FakeFirecrawl(result=firecrawl_article(final_url=final_url))

    outcome = ExtractionRouter(direct, firecrawl).extract(candidate(), company=company(), approved_domains=DOMAINS)

    assert outcome["status"] == "manual_review_required"
    assert outcome["attempts"][-1] == {"provider": "firecrawl", "outcome": "unsafe_final_url"}


def test_router_falls_back_to_candidate_date_for_firecrawl_results():
    direct = FakeDirect(error=ValueError("request_failed"))
    firecrawl = FakeFirecrawl(result=firecrawl_article(published_at=None))

    result = ExtractionRouter(direct, firecrawl).extract(candidate(), company=company(), approved_domains=DOMAINS)

    assert result["status"] == "extracted"
    assert result["extraction_provider"] == "firecrawl"
    assert result["published_at"] == "2026-09-07T12:00:00+00:00"


def test_router_rejects_firecrawl_results_without_any_date():
    direct = FakeDirect(error=ValueError("request_failed"))
    firecrawl = FakeFirecrawl(result=firecrawl_article(published_at=None))

    outcome = ExtractionRouter(direct, firecrawl).extract(
        candidate(published_at=None), company=company(), approved_domains=DOMAINS
    )

    assert outcome["status"] == "manual_review_required"
    assert outcome["attempts"][-1] == {"provider": "firecrawl", "outcome": "metadata_missing"}


def test_router_rejects_firecrawl_results_without_company_evidence():
    direct = FakeDirect(error=ValueError("request_failed"))
    firecrawl = FakeFirecrawl(
        result=firecrawl_article(title="Platform Update", markdown="A generic platform update for developers.")
    )

    outcome = ExtractionRouter(direct, firecrawl).extract(candidate(), company=company(), approved_domains=DOMAINS)

    assert outcome["status"] == "manual_review_required"
    assert outcome["attempts"][-1] == {"provider": "firecrawl", "outcome": "identity_evidence_missing"}


def test_router_rejects_firecrawl_results_without_channel_evidence():
    direct = FakeDirect(error=ValueError("request_failed"))
    firecrawl = FakeFirecrawl(result=firecrawl_article(markdown="NVIDIA unveiled a new platform."))

    outcome = ExtractionRouter(direct, firecrawl).extract(candidate(), company=company(), approved_domains=DOMAINS)

    assert outcome["status"] == "manual_review_required"
    assert outcome["attempts"][-1] == {"provider": "firecrawl", "outcome": "channel_evidence_missing"}


def test_router_firecrawl_text_is_bounded():
    direct = FakeDirect(error=ValueError("request_failed"))
    firecrawl = FakeFirecrawl(result=firecrawl_article(markdown="NVIDIA press release " * 1500))

    result = ExtractionRouter(direct, firecrawl).extract(candidate(), company=company(), approved_domains=DOMAINS)

    assert result["status"] == "extracted"
    assert len(result["text"]) <= 20_000


def test_router_redacts_unexpected_direct_errors_to_stable_codes():
    direct = FakeDirect(error=RuntimeError("private upstream payload"))
    firecrawl = FakeFirecrawl(error=FirecrawlProviderError("provider_error", "firecrawl request failed"))

    outcome = ExtractionRouter(direct, firecrawl).extract(candidate(), company=company(), approved_domains=DOMAINS)

    assert outcome["status"] == "manual_review_required"
    assert outcome["attempts"] == [
        {"provider": "direct_http", "outcome": "provider_error"},
        {"provider": "firecrawl", "outcome": "provider_error"},
    ]


def test_router_redacts_non_code_direct_value_errors():
    direct = FakeDirect(error=ValueError("private upstream payload detail"))

    outcome = ExtractionRouter(direct).extract(candidate(), company=company(), approved_domains=DOMAINS)

    assert outcome["attempts"] == [{"provider": "direct_http", "outcome": "provider_error"}]


def test_router_attempt_outcomes_are_always_stable_codes():
    direct = FakeDirect(error=ValueError("redirect_not_allowed"))
    firecrawl = FakeFirecrawl(error=FirecrawlProviderError("rate_limited", "firecrawl rate limit reached", retryable=True))

    outcome = ExtractionRouter(direct, firecrawl).extract(candidate(), company=company(), approved_domains=DOMAINS)

    for attempt in outcome["attempts"]:
        assert OUTCOME_RE.fullmatch(attempt["outcome"])


def test_router_requires_callable_direct_extractor():
    with pytest.raises(ValueError, match="direct extractor is required"):
        ExtractionRouter(None)


def test_router_rejects_firecrawl_provider_without_extract():
    with pytest.raises(ValueError, match="firecrawl provider is invalid"):
        ExtractionRouter(FakeDirect(result=direct_article()), firecrawl_provider=object())


def test_router_validates_candidate_url():
    router = ExtractionRouter(FakeDirect(result=direct_article()))

    with pytest.raises(ValueError, match="candidate url is required"):
        router.extract({"title": "x"}, company=company(), approved_domains=DOMAINS)
    with pytest.raises(ValueError, match="candidate url is invalid"):
        router.extract(candidate(url="ftp://example.com/report"), company=company(), approved_domains=DOMAINS)


def test_router_validates_channel_company_and_domains():
    router = ExtractionRouter(FakeDirect(result=direct_article()))

    with pytest.raises(ValueError, match="candidate channel is invalid"):
        router.extract(candidate(channel="browser"), company=company(), approved_domains=DOMAINS)
    with pytest.raises(ValueError, match="company is required"):
        router.extract(candidate(), company=None, approved_domains=DOMAINS)
    with pytest.raises(ValueError, match="approved domains are required"):
        router.extract(candidate(), company=company(), approved_domains=set())


def test_firecrawl_html_metadata_supplies_missing_date_and_title():
    direct = FakeDirect(error=ValueError("request_failed"))
    html = """<html><head>
<meta property="og:title" content="NVIDIA Announces Html Story" />
<meta property="article:published_time" content="2026-08-15T08:00:00Z" />
</head><body><h1>Ignored</h1></body></html>"""
    firecrawl = FakeFirecrawl(result=firecrawl_article(title="", published_at=None, html=html))

    result = ExtractionRouter(direct, firecrawl).extract(candidate(published_at=None), company=company(), approved_domains=DOMAINS)

    assert result["status"] == "extracted"
    assert result["extraction_provider"] == "firecrawl"
    assert result["title"] == "NVIDIA Announces Html Story"
    assert result["published_at"] == "2026-08-15T08:00:00+00:00"


def test_firecrawl_html_date_container_supplies_missing_date():
    direct = FakeDirect(error=ValueError("request_failed"))
    html = "<html><body><div class=\"article-date\">May 20, 2026</div></body></html>"
    firecrawl = FakeFirecrawl(result=firecrawl_article(published_at=None, html=html))

    result = ExtractionRouter(direct, firecrawl).extract(candidate(published_at=None), company=company(), approved_domains=DOMAINS)

    assert result["status"] == "extracted"
    assert result["published_at"] == "2026-05-20T00:00:00+00:00"


def test_firecrawl_without_html_and_without_any_date_is_manual_review():
    direct = FakeDirect(error=ValueError("request_failed"))
    firecrawl = FakeFirecrawl(result=firecrawl_article(published_at=None, html=None))

    result = ExtractionRouter(direct, firecrawl).extract(candidate(published_at=None), company=company(), approved_domains=DOMAINS)

    assert result["status"] == "manual_review_required"
    assert result["attempts"][-1] == {"provider": "firecrawl", "outcome": "metadata_missing"}


def test_firecrawl_provider_metadata_beats_html_metadata():
    direct = FakeDirect(error=ValueError("request_failed"))
    html = """<html><head><meta property="article:published_time" content="2026-01-01T00:00:00Z" /></head><body></body></html>"""
    firecrawl = FakeFirecrawl(result=firecrawl_article(published_at="2026-09-07T12:00:00Z", html=html))

    result = ExtractionRouter(direct, firecrawl).extract(candidate(), company=company(), approved_domains=DOMAINS)

    assert result["published_at"] == "2026-09-07T12:00:00+00:00"

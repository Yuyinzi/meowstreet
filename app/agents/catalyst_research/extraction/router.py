import re
from collections.abc import Mapping

from app.agents.catalyst_research.domain import canonicalize_public_url, url_host
from app.agents.catalyst_research.extraction.articles import _approved_domains, _has_channel_evidence, _has_company_evidence, _host_in_domains, _normalize_datetime, parse_article_metadata, strip_title_site_prefix
from app.agents.catalyst_research.providers.firecrawl import FirecrawlProviderError


_DIRECT_PROVIDER = "direct_http"
_FIRECRAWL_PROVIDER = "firecrawl"
_MAX_PROVIDER_TEXT_CHARS = 20_000
_MAX_TITLE_CHARS = 500
_REQUEST_ID_CHARS = 200
_OUTCOME_RE = re.compile(r"\A[a-z0-9_]{1,64}\Z")


def _fold(value):
    return " ".join(str(value or "").split())


def _stable_outcome(error):
    message = _fold(error)
    if _OUTCOME_RE.fullmatch(message):
        return message
    return "provider_error"


def _firecrawl_html_metadata(result):
    html = result.get("html")
    if not isinstance(html, str) or not html.strip():
        return {}
    try:
        return parse_article_metadata(html)
    except Exception:
        return {}


class ExtractionRouter:
    def __init__(self, direct_extractor, firecrawl_provider=None):
        if not callable(direct_extractor):
            raise ValueError("direct extractor is required")
        if firecrawl_provider is not None and not callable(getattr(firecrawl_provider, "extract", None)):
            raise ValueError("firecrawl provider is invalid")
        self._direct_extractor = direct_extractor
        self._firecrawl_provider = firecrawl_provider
        self.firecrawl_disabled_reason = None

    def extract(self, candidate, *, company, approved_domains):
        url, candidate, company, domains = self._validate_inputs(candidate, company, approved_domains)
        attempts = []
        direct = self._extract_direct(url, candidate, company, domains, attempts)
        if direct is not None:
            return direct
        firecrawl = self._extract_firecrawl(url, candidate, company, domains, attempts)
        if firecrawl is not None:
            return firecrawl
        return {
            "status": "manual_review_required",
            "url": url,
            "extraction_provider": "manual",
            "attempts": attempts,
        }

    def _validate_inputs(self, candidate, company, approved_domains):
        if not isinstance(candidate, Mapping):
            raise ValueError("candidate is required")
        raw_url = candidate.get("url")
        if not isinstance(raw_url, str) or not raw_url.strip():
            raise ValueError("candidate url is required")
        try:
            url = canonicalize_public_url(raw_url)
        except ValueError as exc:
            raise ValueError("candidate url is invalid") from exc
        channel = candidate.get("channel")
        if channel is not None and channel not in {"press_releases", "events_presentations", "earnings_results"}:
            raise ValueError("candidate channel is invalid")
        if not isinstance(company, Mapping):
            raise ValueError("company is required")
        return url, dict(candidate), dict(company), _approved_domains(approved_domains)

    def _extract_direct(self, url, candidate, company, domains, attempts):
        try:
            result = self._direct_extractor(
                url,
                candidate=candidate,
                company=company,
                channel=candidate.get("channel"),
                approved_domains=domains,
            )
        except ValueError as exc:
            attempts.append({"provider": _DIRECT_PROVIDER, "outcome": _stable_outcome(exc)})
            return None
        except Exception:
            attempts.append({"provider": _DIRECT_PROVIDER, "outcome": "provider_error"})
            return None
        if not isinstance(result, Mapping) or result.get("status") != "extracted":
            attempts.append({"provider": _DIRECT_PROVIDER, "outcome": "malformed_response"})
            return None
        normalized = dict(result)
        normalized["url"] = url
        normalized["extraction_provider"] = _DIRECT_PROVIDER
        normalized["attempts"] = attempts + [{"provider": _DIRECT_PROVIDER, "outcome": "extracted"}]
        return normalized

    def _extract_firecrawl(self, url, candidate, company, domains, attempts):
        if self._firecrawl_provider is None:
            return None
        if self.firecrawl_disabled_reason is not None:
            attempts.append({"provider": _FIRECRAWL_PROVIDER, "outcome": self.firecrawl_disabled_reason})
            return None
        try:
            result = self._firecrawl_provider.extract(url)
        except FirecrawlProviderError as exc:
            attempts.append({"provider": _FIRECRAWL_PROVIDER, "outcome": exc.reason_code})
            if exc.disable_provider:
                self.firecrawl_disabled_reason = exc.reason_code
            return None
        except Exception:
            attempts.append({"provider": _FIRECRAWL_PROVIDER, "outcome": "provider_error"})
            return None
        return self._normalize_firecrawl(result, url, candidate, company, domains, attempts)

    def _normalize_firecrawl(self, result, url, candidate, company, domains, attempts):
        failure = self._firecrawl_failure(result, candidate, company, domains)
        if failure is not None:
            attempts.append({"provider": _FIRECRAWL_PROVIDER, "outcome": failure})
            return None
        final_url = canonicalize_public_url(result.get("final_url"))
        request_id = _fold(result.get("request_id"))[:_REQUEST_ID_CHARS] or None
        html_metadata = _firecrawl_html_metadata(result)
        return {
            "status": "extracted",
            "url": url,
            "final_url": final_url,
            "title": strip_title_site_prefix(_fold(result.get("title")) or _fold(html_metadata.get("title")), company)[:_MAX_TITLE_CHARS],
            "published_at": _normalize_datetime(result.get("published_at")) or _normalize_datetime(html_metadata.get("published_at")) or _normalize_datetime(candidate.get("published_at")),
            "text": _fold(result.get("markdown"))[:_MAX_PROVIDER_TEXT_CHARS],
            "html": result.get("html"),
            "extraction_provider": _FIRECRAWL_PROVIDER,
            "request_id": request_id,
            "attempts": attempts + [{"provider": _FIRECRAWL_PROVIDER, "outcome": "extracted"}],
        }

    def _firecrawl_failure(self, result, candidate, company, domains):
        if not isinstance(result, Mapping) or not _fold(result.get("markdown")):
            return "malformed_response"
        try:
            final_url = canonicalize_public_url(result.get("final_url"))
        except ValueError:
            return "unsafe_final_url"
        if not _host_in_domains(url_host(final_url), domains):
            return "unsafe_final_url"
        html_metadata = _firecrawl_html_metadata(result)
        title = _fold(result.get("title")) or _fold(html_metadata.get("title"))
        if not title:
            return "metadata_missing"
        published_at = (
            _normalize_datetime(result.get("published_at"))
            or _normalize_datetime(html_metadata.get("published_at"))
            or _normalize_datetime(candidate.get("published_at"))
        )
        if published_at is None:
            return "metadata_missing"
        text = _fold(result.get("markdown"))[:_MAX_PROVIDER_TEXT_CHARS]
        if not _has_company_evidence(company, title, text):
            return "identity_evidence_missing"
        channel = candidate.get("channel")
        if channel is not None and not _has_channel_evidence(channel, title, text):
            return "channel_evidence_missing"
        return None

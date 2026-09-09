import time
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit

from app.agents.catalyst_research.providers.base import mapping_value
from app.agents.catalyst_research.providers.base import safe_string
from app.agents.catalyst_research.providers.base import status_code


FIRECRAWL_REASON_CODES = frozenset(
    {
        "not_configured",
        "authentication_failed",
        "payment_required",
        "rate_limited",
        "timeout",
        "provider_error",
        "empty_content",
        "unsafe_final_url",
        "malformed_response",
    }
)
MAX_ATTEMPTS = 2
RETRY_DELAY_SECONDS = 2.0
_METADATA_FINAL_URL_KEYS = ("url", "sourceURL", "source_url")
_METADATA_TITLE_KEYS = ("title",)
_METADATA_PUBLISHED_KEYS = ("publishedDate", "published_time", "published")
_METADATA_REQUEST_ID_KEYS = ("requestId", "request_id", "scrape_id")


class FirecrawlProviderError(Exception):
    def __init__(
        self,
        reason_code: str,
        message: str,
        *,
        disable_provider: bool = False,
        retryable: bool = False,
    ):
        super().__init__(message)
        self.reason_code = reason_code
        self.disable_provider = disable_provider
        self.retryable = retryable


def _first_metadata_value(metadata: Mapping, keys: tuple[str, ...]) -> str:
    for key in keys:
        value = safe_string(mapping_value(metadata, key))
        if value:
            return value
    return ""


def _payload_dict(value: Any) -> dict | None:
    if isinstance(value, Mapping):
        return dict(value)
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        try:
            dumped = model_dump()
        except Exception:
            return None
        if isinstance(dumped, Mapping):
            return dict(dumped)
    return None


def _validate_url(url: str) -> str:
    if not isinstance(url, str) or not url.strip():
        raise ValueError("url is required")
    candidate = url.strip()
    try:
        parsed = urlsplit(candidate)
    except ValueError as exc:
        raise ValueError("url must be an http or https url") from exc
    if parsed.scheme.casefold() not in {"http", "https"} or not parsed.hostname:
        raise ValueError("url must be an http or https url")
    return candidate


def _safe_final_url(candidate: str) -> str:
    try:
        parsed = urlsplit(candidate)
    except ValueError:
        return ""
    if parsed.scheme.casefold() not in {"http", "https"} or not parsed.hostname:
        return ""
    return candidate


def _classify_exception(error: BaseException) -> FirecrawlProviderError:
    code = status_code(error)
    error_name = type(error).__name__.lower()
    text = error_name + " " + str(error).lower()
    if code in {401, 403} or any(
        token in text for token in ("unauthorized", "forbidden", "authentication", "api key", "invalid key")
    ):
        return FirecrawlProviderError(
            "authentication_failed", "firecrawl authentication failed", disable_provider=True
        )
    if code == 402 or "payment" in text or "credit" in text:
        return FirecrawlProviderError(
            "payment_required", "firecrawl payment required", disable_provider=True
        )
    if code == 429 or "rate limit" in text or "ratelimit" in text or "too many requests" in text:
        return FirecrawlProviderError(
            "rate_limited", "firecrawl rate limit reached", retryable=True
        )
    if isinstance(error, TimeoutError) or "timeout" in text or "timed out" in text:
        return FirecrawlProviderError(
            "timeout", "firecrawl request timed out", retryable=True
        )
    if code is not None and code >= 500:
        return FirecrawlProviderError(
            "provider_error", "firecrawl request failed", retryable=True
        )
    if any(token in text for token in ("connection", "connecterror", "network", "temporarily unavailable")):
        return FirecrawlProviderError(
            "provider_error", "firecrawl request failed", retryable=True
        )
    return FirecrawlProviderError("provider_error", "firecrawl request failed")


def _default_client(api_key: str, base_url: str | None):
    try:
        from firecrawl.v2 import FirecrawlClient
    except ImportError as exc:
        raise FirecrawlProviderError(
            "not_configured", "firecrawl sdk is not installed"
        ) from exc
    if base_url:
        return FirecrawlClient(api_key=api_key, api_url=base_url)
    return FirecrawlClient(api_key=api_key)


class FirecrawlExtractProvider:
    name = "firecrawl"

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str | None = None,
        client: Any = None,
        client_factory: Any = None,
        sleep: Any = None,
    ):
        self._api_key = api_key.strip() if isinstance(api_key, str) and api_key.strip() else None
        self._base_url = base_url
        self._client = client
        self._sleep = sleep if callable(sleep) else time.sleep
        if self._client is None and self._api_key:
            factory = client_factory or _default_client
            self._client = factory(self._api_key, self._base_url)
        self.last_request_id = None

    @property
    def ready(self) -> bool:
        return self._api_key is not None and self._client is not None

    def extract(self, url: str) -> dict:
        self.last_request_id = None
        url = _validate_url(url)
        if not self.ready:
            raise FirecrawlProviderError(
                "not_configured", "firecrawl extraction provider is not configured"
            )
        safe_error = None
        for attempt in range(MAX_ATTEMPTS):
            try:
                response = self._client.scrape(url, formats=["markdown", "html"])
            except Exception as exc:
                candidate = _classify_exception(exc)
                if candidate.retryable and attempt < MAX_ATTEMPTS - 1:
                    self._sleep(RETRY_DELAY_SECONDS)
                    continue
                safe_error = candidate
                break
            try:
                result = self._normalize(url, response)
            except FirecrawlProviderError as exc:
                safe_error = exc
                break
            self.last_request_id = result["request_id"]
            return result
        raise safe_error

    def _normalize(self, requested_url: str, response: Any) -> dict:
        payload = _payload_dict(response)
        if payload is None or "markdown" not in payload:
            raise FirecrawlProviderError(
                "malformed_response", "firecrawl returned a malformed response"
            )
        markdown = payload.get("markdown")
        if not isinstance(markdown, str):
            raise FirecrawlProviderError(
                "malformed_response", "firecrawl returned a malformed response"
            )
        if not markdown.strip():
            raise FirecrawlProviderError(
                "empty_content", "firecrawl returned empty content"
            )
        metadata = _payload_dict(payload.get("metadata")) or {}
        final_url = _first_metadata_value(metadata, _METADATA_FINAL_URL_KEYS) or requested_url
        final_url = _safe_final_url(final_url)
        if not final_url:
            raise FirecrawlProviderError(
                "unsafe_final_url", "firecrawl returned an unsafe final url"
            )
        published_at = _first_metadata_value(metadata, _METADATA_PUBLISHED_KEYS) or None
        request_id = _first_metadata_value(metadata, _METADATA_REQUEST_ID_KEYS) or None
        html = payload.get("html")
        return {
            "url": requested_url,
            "final_url": final_url,
            "title": _first_metadata_value(metadata, _METADATA_TITLE_KEYS),
            "markdown": markdown,
            "html": html if isinstance(html, str) and html.strip() else None,
            "published_at": published_at,
            "request_id": request_id,
            "provider": self.name,
        }


def build_firecrawl_provider(config: dict) -> FirecrawlExtractProvider | None:
    if not isinstance(config, Mapping):
        return None
    api_key = config.get("firecrawl_api_key")
    if not isinstance(api_key, str) or not api_key.strip():
        return None
    return FirecrawlExtractProvider(
        api_key=api_key,
        base_url=config.get("firecrawl_base_url"),
    )

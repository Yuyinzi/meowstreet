from collections.abc import Mapping
from typing import Any
from typing import Protocol
from typing import runtime_checkable


MAX_SEARCH_LIMIT = 50
NORMALIZED_RESULT_KEYS = (
    "title",
    "url",
    "snippet",
    "provider_rank",
    "provider_metadata",
)
VALID_REASON_CODES = frozenset(
    {
        "authentication_failed",
        "rate_limited",
        "timeout",
        "provider_error",
        "unsupported_tool",
        "empty_results",
        "malformed_response",
        "not_configured",
    }
)
_MISSING = object()


@runtime_checkable
class SearchProvider(Protocol):
    name: str
    ready: bool
    last_request_id: str | None

    async def search(self, query: str, *, limit: int) -> list[dict]: ...


class SearchProviderError(Exception):
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


def validate_search_inputs(query: str, limit: int) -> tuple[str, int]:
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query is required")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_SEARCH_LIMIT:
        raise ValueError(f"limit must be between 1 and {MAX_SEARCH_LIMIT}")
    return query.strip(), limit


def mapping_value(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(key, default)
    return getattr(value, key, default)


def safe_string(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def request_id(value: Any) -> str | None:
    for key in ("request_id", "_request_id", "id"):
        candidate = safe_string(mapping_value(value, key))
        if candidate:
            return candidate
    return None


def normalized_result(
    title: Any,
    url: Any,
    snippet: Any,
    rank: int,
    metadata: Mapping[str, Any] | None = None,
) -> dict:
    return {
        "title": safe_string(title),
        "url": safe_string(url),
        "snippet": safe_string(snippet),
        "provider_rank": rank,
        "provider_metadata": _bounded_metadata(metadata),
    }


def status_code(error: BaseException) -> int | None:
    candidates = [error, getattr(error, "response", None), mapping_value(error, "body")]
    for candidate in candidates:
        value = mapping_value(candidate, "status_code", _MISSING)
        if value is _MISSING:
            value = mapping_value(candidate, "status", _MISSING)
        try:
            if value is not _MISSING and value is not None:
                return int(value)
        except (TypeError, ValueError):
            continue
    return None


def _bounded_metadata(metadata: Mapping[str, Any] | None) -> dict:
    if not isinstance(metadata, Mapping):
        return {}
    bounded = {}
    for key, value in list(metadata.items())[:8]:
        if not isinstance(key, str) or not key or len(key) > 64:
            continue
        if isinstance(value, bool) or isinstance(value, (int, float)):
            bounded[key] = value
        elif isinstance(value, str):
            bounded[key] = value[:200]
    return bounded


def classify_provider_exception(error: BaseException) -> tuple[str, bool, bool]:
    status = status_code(error)
    error_name = type(error).__name__.lower()
    text = type(error).__name__.lower() + " " + str(error).lower()
    if status in {401, 403} or error_name in {"invalidapikeyerror", "missingapikeyerror", "forbiddenerror"} or any(token in text for token in ("unauthorized", "forbidden", "authentication", "api key", "invalid key")):
        return "authentication_failed", True, False
    if status == 429 or error_name in {"usagelimitexceedederror", "tavilykeylesslimiterror"} or "rate limit" in text or "ratelimit" in text or "too many requests" in text:
        return "rate_limited", False, True
    if isinstance(error, (TimeoutError,)) or error_name in {"timeouterror", "apitimeouterror"} or "timeout" in text:
        return "timeout", False, True
    if status is not None and status >= 500:
        return "provider_error", False, True
    if any(token in text for token in ("connection", "connecterror", "network", "temporarily unavailable")):
        return "provider_error", False, True
    return "provider_error", False, False


def provider_error(error: BaseException) -> SearchProviderError:
    reason_code, disable_provider, retryable = classify_provider_exception(error)
    messages = {
        "authentication_failed": "search provider authentication failed",
        "rate_limited": "search provider rate limit reached",
        "timeout": "search provider request timed out",
        "provider_error": "search provider request failed",
    }
    return SearchProviderError(
        reason_code,
        messages[reason_code],
        disable_provider=disable_provider,
        retryable=retryable,
    )


def sanitize_provider_error(error: SearchProviderError, provider_name: str) -> SearchProviderError:
    reason_code = error.reason_code if error.reason_code in VALID_REASON_CODES else "provider_error"
    return SearchProviderError(
        reason_code,
        f"{provider_name} search provider request failed",
        disable_provider=bool(error.disable_provider),
        retryable=bool(error.retryable),
    )


def ensure_normalized_results(rows: list[dict]) -> list[dict]:
    if not rows:
        raise SearchProviderError("empty_results", "search provider returned no results")
    if any(not row["url"] for row in rows):
        raise SearchProviderError(
            "malformed_response", "search provider returned malformed results"
        )
    return rows


def is_server_error(error: BaseException) -> bool:
    code = status_code(error)
    if code is not None:
        return 500 <= code <= 599
    text = type(error).__name__.lower() + " " + str(error).lower()
    return "server error" in text or "internal server" in text or " 5xx" in text

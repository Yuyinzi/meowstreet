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
        "provider_metadata": dict(metadata or {}),
    }


def classify_provider_exception(error: BaseException) -> tuple[str, bool, bool]:
    status = mapping_value(error, "status_code")
    if status is None:
        status = mapping_value(error, "status")
    try:
        status = int(status)
    except (TypeError, ValueError):
        status = None
    text = type(error).__name__.lower() + " " + str(error).lower()
    if status in {401, 403} or any(token in text for token in (" 401", " 403", "unauthorized", "forbidden", "authentication", "api key", "invalid key")):
        return "authentication", True, False
    if status == 429 or "rate limit" in text or "ratelimit" in text or "too many requests" in text:
        return "rate_limit", False, True
    if isinstance(error, (TimeoutError,)) or "timeout" in text:
        return "timeout", False, True
    if status is not None and status >= 500:
        return "server_error", False, True
    if any(token in text for token in ("connection", "connecterror", "network", "temporarily unavailable")):
        return "connection_error", False, True
    return "provider_error", False, False


def provider_error(error: BaseException) -> SearchProviderError:
    reason_code, disable_provider, retryable = classify_provider_exception(error)
    messages = {
        "authentication": "search provider authentication failed",
        "rate_limit": "search provider rate limit reached",
        "timeout": "search provider request timed out",
        "server_error": "search provider server error",
        "connection_error": "search provider connection failed",
        "provider_error": "search provider request failed",
    }
    return SearchProviderError(
        reason_code,
        messages[reason_code],
        disable_provider=disable_provider,
        retryable=retryable,
    )


def ensure_normalized_results(rows: list[dict]) -> list[dict]:
    if not rows:
        raise SearchProviderError("empty_results", "search provider returned no results")
    if any(not row["url"] for row in rows):
        raise SearchProviderError(
            "malformed_response", "search provider returned malformed results"
        )
    return rows

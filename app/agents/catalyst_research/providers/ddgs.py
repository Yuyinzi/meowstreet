import asyncio
from typing import Any

from ddgs import DDGS
from ddgs.exceptions import DDGSException

from app.agents.catalyst_research.providers.base import SearchProviderError
from app.agents.catalyst_research.providers.base import ensure_normalized_results
from app.agents.catalyst_research.providers.base import mapping_value
from app.agents.catalyst_research.providers.base import normalized_result
from app.agents.catalyst_research.providers.base import provider_error
from app.agents.catalyst_research.providers.base import sanitize_provider_error
from app.agents.catalyst_research.providers.base import validate_search_inputs


class DDGSSearchProvider:
    name = "ddgs"
    ready = True

    def __init__(self, client_factory=DDGS, *, client: Any = None):
        self._client_factory = client_factory
        self._client = client
        self.last_request_id = None

    async def search(self, query: str, *, limit: int) -> list[dict]:
        self.last_request_id = None
        query, limit = validate_search_inputs(query, limit)
        safe_error = None
        raw_rows = None
        try:
            raw_rows = await asyncio.to_thread(self._search_sync, query, limit)
        except SearchProviderError as exc:
            safe_error = sanitize_provider_error(exc, "ddgs")
        except DDGSException as exc:
            if _is_no_results_error(exc):
                safe_error = SearchProviderError(
                    "empty_results", "ddgs search provider returned no results"
                )
            else:
                safe_error = provider_error(exc)
        except Exception as exc:
            safe_error = provider_error(exc)
        if safe_error is not None:
            raise safe_error
        if not isinstance(raw_rows, list):
            raise SearchProviderError("malformed_response", "ddgs returned malformed results")
        rows = []
        for rank, raw in enumerate(raw_rows[:limit], start=1):
            title = mapping_value(raw, "title")
            url = mapping_value(raw, "href") or mapping_value(raw, "url")
            snippet = mapping_value(raw, "body") or mapping_value(raw, "snippet") or mapping_value(raw, "content")
            rows.append(normalized_result(title, url, snippet, rank))
        return ensure_normalized_results(rows)

    def _search_sync(self, query: str, limit: int) -> list[dict]:
        if self._client is not None:
            return self._client.text(query, max_results=limit)
        client = self._client_factory()
        if hasattr(client, "__enter__"):
            with client as active_client:
                return active_client.text(query, max_results=limit)
        return client.text(query, max_results=limit)


def _is_no_results_error(error: DDGSException) -> bool:
    normalized = " ".join(str(error).casefold().strip().rstrip(".!?").split())
    return normalized in {"no results", "no results found"} or normalized.startswith("no results found for ")

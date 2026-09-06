from typing import Any

from tavily import AsyncTavilyClient

from app.agents.catalyst_research.providers.base import SearchProviderError
from app.agents.catalyst_research.providers.base import ensure_normalized_results
from app.agents.catalyst_research.providers.base import mapping_value
from app.agents.catalyst_research.providers.base import normalized_result
from app.agents.catalyst_research.providers.base import provider_error
from app.agents.catalyst_research.providers.base import request_id
from app.agents.catalyst_research.providers.base import validate_search_inputs


class TavilySearchProvider:
    name = "tavily"

    def __init__(self, api_key: str | None = None, *, client: Any = None, client_factory=AsyncTavilyClient):
        self._api_key = api_key.strip() if isinstance(api_key, str) and api_key.strip() else None
        self._client = client
        if self._client is None and self._api_key:
            self._client = client_factory(api_key=self._api_key)
        self.last_request_id = None

    @property
    def ready(self) -> bool:
        return self._api_key is not None and self._client is not None

    async def search(self, query: str, *, limit: int) -> list[dict]:
        self.last_request_id = None
        query, limit = validate_search_inputs(query, limit)
        if not self.ready:
            raise SearchProviderError(
                "not_configured", "tavily search provider is not configured", disable_provider=True
            )
        try:
            response = await self._client.search(
                query=query,
                max_results=limit,
                search_depth="basic",
                include_answer=False,
                include_raw_content=False,
            )
        except SearchProviderError:
            raise
        except Exception as exc:
            raise provider_error(exc) from exc
        self.last_request_id = request_id(response)
        raw_rows = mapping_value(response, "results")
        if not isinstance(raw_rows, list):
            raise SearchProviderError(
                "malformed_response", "tavily returned malformed results"
            )
        rows = []
        for rank, raw in enumerate(raw_rows[:limit], start=1):
            title = mapping_value(raw, "title")
            url = mapping_value(raw, "url")
            snippet = mapping_value(raw, "content")
            if snippet is None:
                snippet = mapping_value(raw, "snippet")
            score = mapping_value(raw, "score")
            metadata = {"score": score} if isinstance(score, (int, float)) else {}
            rows.append(normalized_result(title, url, snippet, rank, metadata))
        return ensure_normalized_results(rows)

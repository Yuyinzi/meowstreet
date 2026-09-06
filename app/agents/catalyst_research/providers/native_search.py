from typing import Any

from app.agents.catalyst_research.providers.base import SearchProviderError
from app.agents.catalyst_research.providers.base import ensure_normalized_results
from app.agents.catalyst_research.providers.base import mapping_value
from app.agents.catalyst_research.providers.base import normalized_result
from app.agents.catalyst_research.providers.base import provider_error
from app.agents.catalyst_research.providers.base import request_id
from app.agents.catalyst_research.providers.base import sanitize_provider_error
from app.agents.catalyst_research.providers.base import safe_string
from app.agents.catalyst_research.providers.base import status_code
from app.agents.catalyst_research.providers.base import validate_search_inputs


class NativeSearchProvider:
    name = "native_search"

    def __init__(
        self,
        client: Any,
        model: str,
        *,
        base_url: str | None = None,
        native_search_supported: str | bool = "auto",
    ):
        self._client = client
        self._model = model.strip() if isinstance(model, str) else ""
        self._base_url = base_url or self._client_base_url(client)
        self._support = native_search_supported
        self.last_request_id = None

    @staticmethod
    def _client_base_url(client: Any) -> str | None:
        value = getattr(client, "base_url", None)
        return str(value) if value is not None else None

    @staticmethod
    def _is_official_openai_endpoint(base_url: str | None) -> bool:
        if not base_url:
            return True
        value = base_url.lower().rstrip("/")
        return value in {"https://api.openai.com", "https://api.openai.com/v1"}

    @property
    def ready(self) -> bool:
        if self._client is None or not self._model:
            return False
        if self._support is True or str(self._support).lower() == "true":
            return True
        if self._support is False or str(self._support).lower() == "false":
            return False
        return self._is_official_openai_endpoint(self._base_url)

    async def search(self, query: str, *, limit: int) -> list[dict]:
        self.last_request_id = None
        query, limit = validate_search_inputs(query, limit)
        if not self.ready:
            raise SearchProviderError(
                "not_configured", "native search provider is not capability-ready", disable_provider=True
            )
        safe_error = None
        response = None
        try:
            response = await self._client.responses.create(
                model=self._model,
                input=query,
                tools=[{"type": "web_search"}],
            )
        except SearchProviderError as exc:
            safe_error = sanitize_provider_error(exc, "native")
        except Exception as exc:
            if _is_unsupported_tool(exc):
                safe_error = SearchProviderError(
                    "unsupported_tool",
                    "native search tool is unsupported by the endpoint",
                    disable_provider=True,
                )
            else:
                safe_error = provider_error(exc)
        if safe_error is not None:
            raise safe_error
        self.last_request_id = request_id(response)
        rows = _normalize_response(response, limit)
        return ensure_normalized_results(rows)


def _is_unsupported_tool(error: BaseException) -> bool:
    code = status_code(error)
    text = type(error).__name__.lower() + " " + str(error).lower()
    if code is not None and code != 400:
        return False
    if code == 400:
        return "web_search" in text and any(token in text for token in ("unsupported", "supported", "invalid value", "unknown"))
    return any(token in text for token in ("unsupported tool", "unknown tool", "unrecognized tool", "web_search is not supported"))


def _normalize_response(response: Any, limit: int) -> list[dict]:
    records: dict[str, dict] = {}
    output = mapping_value(response, "output", _MISSING)
    if output is _MISSING or output is None or not isinstance(output, list):
        raise SearchProviderError("malformed_response", "native search returned malformed output")
    for item in output:
        item_type = safe_string(mapping_value(item, "type"))
        if item_type == "web_search_call":
            action = mapping_value(item, "action")
            sources = mapping_value(action, "sources", _MISSING) if action is not None else _MISSING
            if sources is _MISSING or not isinstance(sources, (list, tuple)):
                raise SearchProviderError("malformed_response", "native search returned malformed sources")
            for source in sources:
                if not _record_source(records, source, ""):
                    raise SearchProviderError("malformed_response", "native search returned malformed source")
        if item_type != "message":
            continue
        contents = mapping_value(item, "content", _MISSING)
        if contents is _MISSING or not isinstance(contents, list):
            raise SearchProviderError("malformed_response", "native search returned malformed message")
        for content in contents:
            if safe_string(mapping_value(content, "type")) != "output_text":
                continue
            text = safe_string(mapping_value(content, "text"))
            annotations = mapping_value(content, "annotations", _MISSING)
            if annotations is _MISSING:
                annotations = []
            if not isinstance(annotations, list):
                raise SearchProviderError("malformed_response", "native search returned malformed citations")
            for annotation in annotations:
                if safe_string(mapping_value(annotation, "type")) != "url_citation":
                    continue
                if not _record_source(records, annotation, text):
                    raise SearchProviderError("malformed_response", "native search returned malformed citation")
    rows = []
    for rank, record in enumerate(records.values(), start=1):
        rows.append(
            normalized_result(
                record["title"],
                record["url"],
                record["snippet"],
                rank,
                record["metadata"],
            )
        )
        if len(rows) >= limit:
            break
    return rows


def _record_source(records: dict[str, dict], source: Any, snippet: str) -> bool:
    url = safe_string(mapping_value(source, "url"))
    if not url:
        return False
    current = records.setdefault(
        url,
        {"url": url, "title": "", "snippet": "", "metadata": {}},
    )
    title = safe_string(mapping_value(source, "title"))
    if title:
        current["title"] = title
    source_snippet = safe_string(mapping_value(source, "snippet"))
    if source_snippet:
        current["snippet"] = source_snippet
    elif snippet and not current["snippet"]:
        current["snippet"] = snippet
    return True


_MISSING = object()

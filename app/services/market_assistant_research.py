from typing import Protocol

from app.data_sources.openai_web_search import OpenAIWebSearchError
from app.data_sources.openai_web_search import OpenAIWebSearchProvider
from app.llm import build_async_client
from app.tools.market_assistant_research import build_research_result
from app.tools.market_assistant_research import validate_research_task


class ResearchProvider(Protocol):
    async def search(self, task: dict) -> dict: ...


async def acquire_research(
    provider, task, *, result_id, searched_at, explicit_deep=False
):
    try:
        validated_task = validate_research_task(task, explicit_deep=explicit_deep)
    except ValueError:
        return _research_unavailable(result_id, searched_at, "invalid_task")
    try:
        provider_payload = await provider.search(validated_task)
    except OpenAIWebSearchError as exc:
        return _research_unavailable(result_id, searched_at, exc.reason_code)
    except Exception:
        return _research_unavailable(result_id, searched_at, "provider_error")
    try:
        return build_research_result(
            task=validated_task,
            provider_payload=provider_payload,
            result_id=result_id,
            searched_at=searched_at,
        )
    except ValueError:
        return _research_unavailable(result_id, searched_at, "provider_error")


async def acquire_research_from_config(
    config, task, *, result_id, searched_at, explicit_deep=False
):
    try:
        provider = build_research_provider(config)
    except OpenAIWebSearchError as exc:
        return _research_unavailable(result_id, searched_at, exc.reason_code)
    return await acquire_research(
        provider,
        task,
        result_id=result_id,
        searched_at=searched_at,
        explicit_deep=explicit_deep,
    )


def build_research_provider(config):
    if not config.get("research_enabled"):
        raise OpenAIWebSearchError("configuration_unavailable", "research is disabled")
    if not config.get("research_model"):
        raise OpenAIWebSearchError(
            "configuration_unavailable", "research model is required"
        )
    if config.get("base_url") and not config.get("supports_web_search"):
        raise OpenAIWebSearchError(
            "configuration_unavailable", "web search support must be explicitly enabled"
        )
    if not config.get("api_key"):
        raise OpenAIWebSearchError(
            "configuration_unavailable", "openai api key is required"
        )
    try:
        client = build_async_client(config, error_context="market research")
    except RuntimeError as exc:
        raise OpenAIWebSearchError("configuration_unavailable", str(exc)) from exc
    return OpenAIWebSearchProvider(client, config["research_model"])


def _research_unavailable(result_id, searched_at, reason_code):
    return {
        "authority": "external_research",
        "market_setup_relation": "non_decision",
        "research_result_id": result_id,
        "status": "research_unavailable",
        "reason_code": reason_code,
        "searched_at": searched_at,
    }

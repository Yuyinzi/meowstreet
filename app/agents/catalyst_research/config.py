import os
from pathlib import Path

from app import llm


ROOT = Path(__file__).resolve().parents[3]
RESEARCH_VERSION = "catalyst_research_v1"
RESULT_SCHEMA_VERSION = "catalyst_research_result_v1"
ADAPTER_SCHEMA_VERSION = "ir_source_adapter_v1"
PROMPT_VERSIONS = {
    "source_selection": "source_selection_v2",
    "adapter_generation": "adapter_generation_v1",
    "classification": "classification_v1",
}

_SEARCH_PROVIDERS = {"auto", "tavily", "native_search", "ddgs"}
_SEARCH_FALLBACKS = {"auto", "ddgs", "none"}
_NATIVE_SEARCH_SUPPORT = {"auto", "true", "false"}


def _argument(args, *names):
    if args is None:
        return None
    for name in names:
        value = getattr(args, name, None)
        if value:
            return value
    return None


def _setting(args, argument_names, environment_name):
    return _argument(args, *argument_names) or os.getenv(environment_name)


def _normalized_setting(value, default, valid, message):
    normalized = default if value is None or not str(value).strip() else str(value).strip().lower()
    if normalized not in valid:
        raise ValueError(message)
    return normalized


def load_search_config(args=None, root=ROOT):
    llm.load_env(root)
    provider = _normalized_setting(
        _setting(args, ("catalyst_search_provider", "search_provider"), "CATALYST_SEARCH_PROVIDER"),
        "auto",
        _SEARCH_PROVIDERS,
        "catalyst search provider is invalid",
    )
    fallback = _normalized_setting(
        _setting(args, ("catalyst_search_fallback", "search_fallback"), "CATALYST_SEARCH_FALLBACK"),
        "auto",
        _SEARCH_FALLBACKS,
        "catalyst search fallback is invalid",
    )
    native_search_supported = _normalized_setting(
        _setting(
            args,
            ("catalyst_native_search_supported", "native_search_supported"),
            "CATALYST_NATIVE_SEARCH_SUPPORTED",
        ),
        "auto",
        _NATIVE_SEARCH_SUPPORT,
        "catalyst native search support is invalid",
    )
    tavily_api_key = _setting(args, ("tavily_api_key",), "TAVILY_API_KEY")
    return {
        "provider": provider,
        "fallback": fallback,
        "native_search_supported": native_search_supported,
        "tavily_api_key": tavily_api_key.strip() if tavily_api_key and tavily_api_key.strip() else None,
    }


def load_inference_bundle(args=None, root=ROOT):
    return llm.build_async_client_bundle(
        args,
        root=root,
        model_specs=[
            {
                "name": "source_selection_model",
                "arg_name": "catalyst_source_selection_model",
                "env_names": ["CATALYST_SOURCE_SELECTION_MODEL", "OPENAI_MODEL"],
                "label": "catalyst source selection model",
            },
            {
                "name": "adapter_generation_model",
                "arg_name": "catalyst_adapter_generation_model",
                "env_names": ["CATALYST_ADAPTER_GENERATION_MODEL", "OPENAI_MODEL"],
                "label": "catalyst adapter generation model",
            },
            {
                "name": "classification_model",
                "arg_name": "catalyst_classification_model",
                "env_names": ["CATALYST_CLASSIFICATION_MODEL", "OPENAI_MODEL"],
                "label": "catalyst classification model",
            },
        ],
        max_retries=0,
        timeout=300.0,
        error_context="Catalyst Research Agent",
    )

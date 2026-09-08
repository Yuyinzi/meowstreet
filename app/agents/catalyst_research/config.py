import os
from pathlib import Path
from urllib.parse import urlsplit

from app import llm


ROOT = Path(__file__).resolve().parents[3]
LEGACY_RESULT_SCHEMA_VERSION = "catalyst_research_result_v1"
RESULT_SCHEMA_VERSION = "catalyst_research_result_v1_1"
RESEARCH_VERSION = "catalyst_research_v1_1"
RESEARCH_MODES = frozenset({"research", "update", "rediscover"})
ADAPTER_SCHEMA_VERSION = "ir_source_adapter_v1"
PROMPT_VERSIONS = {
    "source_selection": "source_selection_v2",
    "adapter_generation": "adapter_generation_v1",
    "classification": "classification_v1",
}

_SEARCH_PROVIDERS = {"auto", "tavily", "native_search", "ddgs"}
_SEARCH_FALLBACKS = {"auto", "ddgs", "none"}
_NATIVE_SEARCH_SUPPORT = {"auto", "true", "false"}

COLLECTION_ENV_NAMES = (
    "CATALYST_HISTORICAL_SLICE_DAYS",
    "CATALYST_MAX_HISTORICAL_QUERIES_PER_CHANNEL",
    "CATALYST_SEARCH_RESULT_LIMIT",
    "CATALYST_MAX_UNSEEN_URLS_PER_CHANNEL",
    "CATALYST_GAP_LOOKBACK_DAYS",
    "CATALYST_MAX_GAP_QUERIES_PER_CHANNEL",
    "CATALYST_GAP_SEARCH_INTERVAL_DAYS",
    "CATALYST_FEED_FAILURE_THRESHOLD",
    "FIRECRAWL_API_KEY",
    "FIRECRAWL_BASE_URL",
    "CATALYST_ARCHIVE_ENRICHMENT_ENABLED",
)

_COLLECTION_INTEGER_SETTINGS = (
    (
        "historical_slice_days",
        ("catalyst_historical_slice_days", "historical_slice_days"),
        "CATALYST_HISTORICAL_SLICE_DAYS",
        92,
        30,
        366,
        "historical slice days",
    ),
    (
        "max_historical_queries_per_channel",
        ("catalyst_max_historical_queries_per_channel", "max_historical_queries_per_channel"),
        "CATALYST_MAX_HISTORICAL_QUERIES_PER_CHANNEL",
        16,
        1,
        32,
        "historical queries per channel",
    ),
    (
        "search_result_limit",
        ("catalyst_search_result_limit", "search_result_limit"),
        "CATALYST_SEARCH_RESULT_LIMIT",
        10,
        1,
        20,
        "search result limit",
    ),
    (
        "max_unseen_urls_per_channel",
        ("catalyst_max_unseen_urls_per_channel", "max_unseen_urls_per_channel"),
        "CATALYST_MAX_UNSEEN_URLS_PER_CHANNEL",
        200,
        1,
        500,
        "unseen urls per channel",
    ),
    (
        "gap_lookback_days",
        ("catalyst_gap_lookback_days", "gap_lookback_days"),
        "CATALYST_GAP_LOOKBACK_DAYS",
        14,
        1,
        45,
        "gap lookback days",
    ),
    (
        "max_gap_queries_per_channel",
        ("catalyst_max_gap_queries_per_channel", "max_gap_queries_per_channel"),
        "CATALYST_MAX_GAP_QUERIES_PER_CHANNEL",
        2,
        1,
        4,
        "gap queries per channel",
    ),
    (
        "gap_search_interval_days",
        ("catalyst_gap_search_interval_days", "gap_search_interval_days"),
        "CATALYST_GAP_SEARCH_INTERVAL_DAYS",
        7,
        1,
        30,
        "gap search interval days",
    ),
    (
        "feed_failure_threshold",
        ("catalyst_feed_failure_threshold", "feed_failure_threshold"),
        "CATALYST_FEED_FAILURE_THRESHOLD",
        3,
        1,
        10,
        "feed failure threshold",
    ),
)


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


def _bounded_integer_setting(value, default, minimum, maximum, label):
    candidate = default if value is None or not str(value).strip() else value
    try:
        parsed = int(candidate)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be between {minimum} and {maximum}") from exc
    if not minimum <= parsed <= maximum:
        raise ValueError(f"{label} must be between {minimum} and {maximum}")
    return parsed


def _boolean_setting(value, default=False):
    normalized = str(value).strip().casefold() if value is not None and str(value).strip() else None
    if normalized is None:
        return default
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise ValueError("catalyst archive enrichment must be true or false")


def _firecrawl_base_url(value):
    if value is None or not str(value).strip():
        return None
    candidate = str(value).strip()
    try:
        parsed = urlsplit(candidate)
    except ValueError as exc:
        raise ValueError("firecrawl base url must be an https url") from exc
    if parsed.scheme.casefold() != "https" or not parsed.hostname:
        raise ValueError("firecrawl base url must be an https url")
    return candidate


def load_collection_config(args=None, root=ROOT):
    llm.load_env(root)
    config = {
        key: _bounded_integer_setting(
            _setting(args, argument_names, environment_name),
            default,
            minimum,
            maximum,
            label,
        )
        for key, argument_names, environment_name, default, minimum, maximum, label in _COLLECTION_INTEGER_SETTINGS
    }
    firecrawl_api_key = _setting(args, ("firecrawl_api_key",), "FIRECRAWL_API_KEY")
    config["firecrawl_api_key"] = firecrawl_api_key.strip() if firecrawl_api_key and firecrawl_api_key.strip() else None
    config["firecrawl_base_url"] = _firecrawl_base_url(
        _setting(args, ("firecrawl_base_url",), "FIRECRAWL_BASE_URL")
    )
    config["archive_enrichment_enabled"] = _boolean_setting(
        _setting(
            args,
            ("catalyst_archive_enrichment_enabled", "archive_enrichment_enabled"),
            "CATALYST_ARCHIVE_ENRICHMENT_ENABLED",
        )
    )
    return config


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

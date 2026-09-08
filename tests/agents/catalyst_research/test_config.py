from types import SimpleNamespace

import pytest

from app.agents.catalyst_research.config import (
    COLLECTION_ENV_NAMES,
    LEGACY_RESULT_SCHEMA_VERSION,
    RESEARCH_VERSION,
    RESULT_SCHEMA_VERSION,
    load_collection_config,
    load_inference_bundle,
    load_search_config,
)


def test_v1_1_version_constants():
    assert LEGACY_RESULT_SCHEMA_VERSION == "catalyst_research_result_v1"
    assert RESULT_SCHEMA_VERSION == "catalyst_research_result_v1_1"
    assert RESEARCH_VERSION == "catalyst_research_v1_1"


def test_collection_config_uses_v1_1_defaults(monkeypatch, tmp_path):
    for name in COLLECTION_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)

    result = load_collection_config(root=tmp_path)

    assert result == {
        "historical_slice_days": 92,
        "max_historical_queries_per_channel": 16,
        "search_result_limit": 10,
        "max_unseen_urls_per_channel": 200,
        "gap_lookback_days": 14,
        "max_gap_queries_per_channel": 2,
        "gap_search_interval_days": 7,
        "feed_failure_threshold": 3,
        "firecrawl_api_key": None,
        "firecrawl_base_url": None,
        "archive_enrichment_enabled": False,
    }


def test_collection_config_rejects_out_of_range_slice(monkeypatch, tmp_path):
    monkeypatch.setenv("CATALYST_HISTORICAL_SLICE_DAYS", "29")

    with pytest.raises(ValueError, match="historical slice days must be between 30 and 366"):
        load_collection_config(root=tmp_path)


@pytest.mark.parametrize(
    ("name", "minimum", "maximum", "label"),
    [
        ("CATALYST_HISTORICAL_SLICE_DAYS", 30, 366, "historical slice days"),
        ("CATALYST_MAX_HISTORICAL_QUERIES_PER_CHANNEL", 1, 32, "historical queries per channel"),
        ("CATALYST_SEARCH_RESULT_LIMIT", 1, 20, "search result limit"),
        ("CATALYST_MAX_UNSEEN_URLS_PER_CHANNEL", 1, 500, "unseen urls per channel"),
        ("CATALYST_GAP_LOOKBACK_DAYS", 1, 45, "gap lookback days"),
        ("CATALYST_MAX_GAP_QUERIES_PER_CHANNEL", 1, 4, "gap queries per channel"),
    ],
)
def test_collection_config_rejects_out_of_range_values(monkeypatch, tmp_path, name, minimum, maximum, label):
    for env_name in COLLECTION_ENV_NAMES:
        monkeypatch.delenv(env_name, raising=False)
    monkeypatch.setenv(name, str(maximum + 1))

    with pytest.raises(ValueError, match=f"{label} must be between {minimum} and {maximum}"):
        load_collection_config(root=tmp_path)


@pytest.mark.parametrize("value", ["true", "TRUE", " True "])
def test_collection_config_parses_archive_enrichment_true(monkeypatch, tmp_path, value):
    monkeypatch.setenv("CATALYST_ARCHIVE_ENRICHMENT_ENABLED", value)

    assert load_collection_config(root=tmp_path)["archive_enrichment_enabled"] is True


@pytest.mark.parametrize("value", ["yes", "1", "enabled"])
def test_collection_config_rejects_non_boolean_archive_enrichment(monkeypatch, tmp_path, value):
    monkeypatch.setenv("CATALYST_ARCHIVE_ENRICHMENT_ENABLED", value)

    with pytest.raises(ValueError, match="catalyst archive enrichment must be true or false"):
        load_collection_config(root=tmp_path)


def test_collection_config_strips_firecrawl_key_and_validates_https_base_url(monkeypatch, tmp_path):
    monkeypatch.setenv("FIRECRAWL_API_KEY", "  fc-key  ")
    monkeypatch.setenv("FIRECRAWL_BASE_URL", " https://firecrawl.example.com ")

    result = load_collection_config(root=tmp_path)

    assert result["firecrawl_api_key"] == "fc-key"
    assert result["firecrawl_base_url"] == "https://firecrawl.example.com"


@pytest.mark.parametrize("value", ["http://firecrawl.example.com", "ftp://firecrawl.example.com", "not-a-url"])
def test_collection_config_rejects_non_https_firecrawl_base_url(monkeypatch, tmp_path, value):
    monkeypatch.setenv("FIRECRAWL_BASE_URL", value)

    with pytest.raises(ValueError, match="firecrawl base url must be an https url"):
        load_collection_config(root=tmp_path)


def test_search_config_defaults_to_key_free_auto(monkeypatch, tmp_path):
    monkeypatch.delenv("CATALYST_SEARCH_PROVIDER", raising=False)
    monkeypatch.delenv("CATALYST_SEARCH_FALLBACK", raising=False)
    monkeypatch.delenv("CATALYST_NATIVE_SEARCH_SUPPORTED", raising=False)
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)

    result = load_search_config(root=tmp_path)

    assert result == {
        "provider": "auto",
        "fallback": "auto",
        "native_search_supported": "auto",
        "tavily_api_key": None,
    }


@pytest.mark.parametrize(
    ("name", "value", "message"),
    [
        ("CATALYST_SEARCH_PROVIDER", "google", "catalyst search provider is invalid"),
        ("CATALYST_SEARCH_FALLBACK", "tavily", "catalyst search fallback is invalid"),
        (
            "CATALYST_NATIVE_SEARCH_SUPPORTED",
            "yes",
            "catalyst native search support is invalid",
        ),
    ],
)
def test_search_config_rejects_invalid_values(monkeypatch, tmp_path, name, value, message):
    monkeypatch.setenv(name, value)

    with pytest.raises(ValueError, match=message):
        load_search_config(root=tmp_path)


def test_search_config_reads_args_and_normalizes_empty_key(monkeypatch, tmp_path):
    monkeypatch.setenv("TAVILY_API_KEY", "")
    args = SimpleNamespace(
        catalyst_search_provider="DDGS",
        catalyst_search_fallback="NONE",
        catalyst_native_search_supported="TRUE",
        tavily_api_key="",
    )

    assert load_search_config(args=args, root=tmp_path) == {
        "provider": "ddgs",
        "fallback": "none",
        "native_search_supported": "true",
        "tavily_api_key": None,
    }


def test_inference_bundle_delegates_named_models_to_llm(monkeypatch, tmp_path):
    expected = {"client": object(), "config": {"api_key": "secret"}, "models": {}}
    calls = {}

    def fake_bundle(*args, **kwargs):
        calls["args"] = args
        calls["kwargs"] = kwargs
        return expected

    monkeypatch.setattr(
        "app.agents.catalyst_research.config.llm.build_async_client_bundle",
        fake_bundle,
    )

    result = load_inference_bundle(root=tmp_path)

    assert result is expected
    specs = calls["kwargs"]["model_specs"]
    assert [spec["name"] for spec in specs] == [
        "source_selection_model",
        "adapter_generation_model",
        "classification_model",
    ]
    assert [spec["env_names"] for spec in specs] == [
        ["CATALYST_SOURCE_SELECTION_MODEL", "OPENAI_MODEL"],
        ["CATALYST_ADAPTER_GENERATION_MODEL", "OPENAI_MODEL"],
        ["CATALYST_CLASSIFICATION_MODEL", "OPENAI_MODEL"],
    ]

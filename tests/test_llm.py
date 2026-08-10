import os
from types import SimpleNamespace

import pytest

from app import llm


MARKET_ENV_NAMES = (
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
    "MARKET_ASSISTANT_MODEL",
    "MARKET_ASSISTANT_RESEARCH_MODEL",
    "MARKET_ASSISTANT_RESEARCH_PROVIDER",
    "MARKET_ASSISTANT_RESEARCH_ENABLED",
    "MARKET_ASSISTANT_RESEARCH_SUPPORTS_WEB_SEARCH",
)


def write_env(tmp_path, **overrides):
    env = {
        "MARKET_ASSISTANT_MODEL": "assistant-model",
        "MARKET_ASSISTANT_RESEARCH_MODEL": "research-model",
        "MARKET_ASSISTANT_RESEARCH_PROVIDER": "openai_responses",
        "MARKET_ASSISTANT_RESEARCH_ENABLED": "true",
        "OPENAI_API_KEY": "test-key",
    }
    key_map = {
        "model": "MARKET_ASSISTANT_MODEL",
        "research_model": "MARKET_ASSISTANT_RESEARCH_MODEL",
        "provider": "MARKET_ASSISTANT_RESEARCH_PROVIDER",
        "base_url": "OPENAI_BASE_URL",
        "supports": "MARKET_ASSISTANT_RESEARCH_SUPPORTS_WEB_SEARCH",
        "api_key": "OPENAI_API_KEY",
        "enabled": "MARKET_ASSISTANT_RESEARCH_ENABLED",
    }
    for key, value in overrides.items():
        env[key_map.get(key, key)] = str(value)
    lines = [f"{name}={value}" for name, value in env.items()]
    (tmp_path / ".env").write_text("\n".join(lines) + "\n", encoding="utf-8")


def clear_market_env(monkeypatch):
    for name in MARKET_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)


def test_load_openai_config_uses_dotenv_interpolation(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text(
        "OPENAI_API_KEY=test-key\nMETHOD_EXTRACTION_MODEL=${OPENAI_API_KEY}-model\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("METHOD_EXTRACTION_MODEL", raising=False)

    config = llm.load_openai_config(SimpleNamespace(), root=tmp_path)

    assert config["api_key"] == "test-key"
    assert config["model"] == "test-key-model"


def test_build_async_client_bundle_loads_named_models_from_env(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    env_path.write_text(
        "OPENAI_API_KEY=test-key\n"
        "OPENAI_BASE_URL=https://example.test/v1\n"
        "FOMC_TONE_EXTRACTOR_MODEL=extractor-model\n"
        "FOMC_TONE_REVIEWER_MODEL=reviewer-model\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("FOMC_TONE_EXTRACTOR_MODEL", raising=False)
    monkeypatch.delenv("FOMC_TONE_REVIEWER_MODEL", raising=False)

    bundle = llm.build_async_client_bundle(
        SimpleNamespace(
            openai_api_key="",
            openai_base_url="",
            extractor_model="",
            reviewer_model="",
        ),
        root=tmp_path,
        model_specs=[
            {
                "name": "extractor_model",
                "arg_name": "extractor_model",
                "env_names": ["FOMC_TONE_EXTRACTOR_MODEL", "OPENAI_MODEL"],
                "label": "FOMC tone extractor model",
            },
            {
                "name": "reviewer_model",
                "arg_name": "reviewer_model",
                "env_names": ["FOMC_TONE_REVIEWER_MODEL", "OPENAI_MODEL"],
                "label": "FOMC tone reviewer model",
            },
        ],
        max_retries=0,
        timeout=120,
        error_context="FOMC tone extraction",
    )

    assert bundle["config"]["api_key"] == "test-key"
    assert bundle["config"]["base_url"] == "https://example.test/v1"
    assert bundle["models"] == {
        "extractor_model": "extractor-model",
        "reviewer_model": "reviewer-model",
    }
    assert bundle["client"] is not None


def test_build_async_client_bundle_requires_named_models(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    env_path.write_text("OPENAI_API_KEY=test-key\n", encoding="utf-8")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("FOMC_TONE_EXTRACTOR_MODEL", raising=False)
    monkeypatch.delenv("FOMC_TONE_REVIEWER_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)

    with pytest.raises(RuntimeError, match="FOMC tone extractor model is required"):
        llm.build_async_client_bundle(
            SimpleNamespace(
                openai_api_key="",
                openai_base_url="",
                extractor_model="",
                reviewer_model="",
            ),
            root=tmp_path,
            model_specs=[
                {
                    "name": "extractor_model",
                    "arg_name": "extractor_model",
                    "env_names": ["FOMC_TONE_EXTRACTOR_MODEL", "OPENAI_MODEL"],
                    "label": "FOMC tone extractor model",
                },
            ],
            max_retries=0,
            timeout=120,
            error_context="FOMC tone extraction",
        )


def test_build_async_client_bundle_requires_api_key(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    env_path.write_text(
        "FOMC_TONE_EXTRACTOR_MODEL=extractor\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY is required"):
        llm.build_async_client_bundle(
            SimpleNamespace(
                openai_api_key="",
                openai_base_url="",
                extractor_model="",
                reviewer_model="",
            ),
            root=tmp_path,
            model_specs=[
                {
                    "name": "extractor_model",
                    "arg_name": "extractor_model",
                    "env_names": ["FOMC_TONE_EXTRACTOR_MODEL", "OPENAI_MODEL"],
                    "label": "FOMC tone extractor model",
                },
            ],
            max_retries=0,
            timeout=120,
            error_context="FOMC tone extraction",
        )


def test_load_market_assistant_config_requires_env_vars(tmp_path, monkeypatch):
    clear_market_env(monkeypatch)
    write_env(tmp_path, model="")

    with pytest.raises(RuntimeError, match="MARKET_ASSISTANT_MODEL is required"):
        llm.load_market_assistant_config(root=tmp_path)


def test_load_market_assistant_config_requires_research_model(tmp_path, monkeypatch):
    clear_market_env(monkeypatch)
    write_env(tmp_path, research_model="")

    with pytest.raises(
        RuntimeError, match="MARKET_ASSISTANT_RESEARCH_MODEL is required"
    ):
        llm.load_market_assistant_config(root=tmp_path)


def test_load_market_assistant_config_requires_openai_responses_provider(
    tmp_path, monkeypatch
):
    clear_market_env(monkeypatch)
    write_env(tmp_path, provider="anthropic")

    with pytest.raises(
        RuntimeError,
        match="MARKET_ASSISTANT_RESEARCH_PROVIDER must be openai_responses",
    ):
        llm.load_market_assistant_config(root=tmp_path)


def test_custom_base_url_requires_explicit_web_search_support(tmp_path, monkeypatch):
    clear_market_env(monkeypatch)
    write_env(tmp_path, base_url="https://compatible.test/v1", supports="false")
    with pytest.raises(
        RuntimeError, match="web search support must be explicitly enabled"
    ):
        llm.load_market_assistant_config(root=tmp_path)


def test_custom_base_url_with_explicit_support_passes(tmp_path, monkeypatch):
    clear_market_env(monkeypatch)
    write_env(tmp_path, base_url="https://compatible.test/v1", supports="true")

    config = llm.load_market_assistant_config(root=tmp_path)

    assert config["base_url"] == "https://compatible.test/v1"
    assert config["supports_web_search"] is True


def test_load_market_assistant_config_returns_full_config(tmp_path, monkeypatch):
    clear_market_env(monkeypatch)
    write_env(tmp_path)

    config = llm.load_market_assistant_config(root=tmp_path)

    assert config["api_key"] == "test-key"
    assert config["model"] == "assistant-model"
    assert config["research_model"] == "research-model"
    assert config["provider"] == "openai_responses"
    assert config["research_enabled"] is True
    assert config["supports_web_search"] is False


def test_load_market_assistant_config_parses_disabled_research(tmp_path, monkeypatch):
    clear_market_env(monkeypatch)
    write_env(tmp_path)
    monkeypatch.setenv("MARKET_ASSISTANT_RESEARCH_ENABLED", "false")

    config = llm.load_market_assistant_config(root=tmp_path)

    assert config["research_enabled"] is False


def test_load_market_assistant_config_builds_client_via_build_async_client(
    tmp_path, monkeypatch
):
    clear_market_env(monkeypatch)
    write_env(tmp_path)

    config = llm.load_market_assistant_config(root=tmp_path)
    client = llm.build_async_client(config, error_context="market research")

    assert client is not None

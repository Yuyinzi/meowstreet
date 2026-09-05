from types import SimpleNamespace

import pytest

from app.agents.catalyst_research.config import load_inference_bundle, load_search_config


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

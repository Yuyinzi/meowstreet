import os
from types import SimpleNamespace

import pytest

from app import llm


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

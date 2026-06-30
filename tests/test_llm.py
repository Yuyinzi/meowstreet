from types import SimpleNamespace

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

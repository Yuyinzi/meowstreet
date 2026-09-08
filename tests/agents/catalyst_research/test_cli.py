import json
from pathlib import Path

import pytest

from app.agents.catalyst_research import __main__ as cli


class FakeHttpClient:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False


def _install(monkeypatch, result=None, error=None):
    captured = {}

    async def run(request, *, db_path=None, http_client=None, dependencies=None):
        captured.update({"request": request, "db_path": db_path, "http_client": http_client, "dependencies": dependencies})
        if error is not None:
            raise error
        return result if result is not None else {"status": "completed", "job_id": "cr_1", "sources": []}

    monkeypatch.setattr(cli, "run_research", run)
    monkeypatch.setattr(cli, "HttpClient", FakeHttpClient)
    return captured


def test_cli_completed_returns_zero_and_prints_final_json(monkeypatch, capsys):
    result = {"status": "completed", "job_id": "cr_1", "sources": [{"source_type": "press_releases", "extraction_status": "complete", "execution_path": "hot"}]}
    captured = _install(monkeypatch, result=result)

    exit_code = cli.main(["acme"])

    output = capsys.readouterr()
    assert exit_code == 0
    assert json.loads(output.out) == result
    assert "started" in output.err
    assert "press_releases" in output.err
    assert "completed" in output.err
    assert captured["request"] == {"ticker": "acme", "years": 4, "force_discovery": False}
    assert captured["db_path"] is None
    assert captured["dependencies"] == {"progress": cli._stage_progress}


def test_cli_passes_years_force_discovery_db_path_and_repeatable_source_overrides(monkeypatch, tmp_path):
    captured = _install(monkeypatch)

    exit_code = cli.main([
        "NVDA", "--years", "2", "--db-path", str(tmp_path / "db.sqlite"), "--force-discovery",
        "--source", "press_releases=https://example.com/investors/news",
        "--source", "events_presentations=https://example.com/investors/events",
    ])

    assert exit_code == 0
    assert captured["request"]["years"] == 2
    assert captured["request"]["force_discovery"] is True
    assert captured["request"]["source_overrides"] == {
        "press_releases": "https://example.com/investors/news",
        "events_presentations": "https://example.com/investors/events",
    }
    assert captured["db_path"] == tmp_path / "db.sqlite"


def test_cli_prints_stage_progress_lines(monkeypatch, capsys):
    captured = _install(monkeypatch)

    async def run(request, *, db_path=None, http_client=None, dependencies=None):
        captured.update({"request": request, "db_path": db_path, "http_client": http_client, "dependencies": dependencies})
        dependencies["progress"]("discovery", channels="press_releases")
        return {"status": "completed", "job_id": "cr_1", "sources": []}

    monkeypatch.setattr(cli, "run_research", run)

    exit_code = cli.main(["NVDA"])

    assert exit_code == 0
    assert "stage discovery channels=press_releases" in capsys.readouterr().err


def test_cli_override_flags_default_to_none():
    args = cli._parser().parse_args(["ACME"])

    assert args.ticker == "ACME"
    assert args.years == 4
    assert args.db_path is None
    assert args.source is None
    assert args.force_discovery is False
    assert args.mode is None
    assert args.archive_enrichment_enabled is None
    for name in (
        "catalyst_search_provider", "catalyst_search_fallback", "catalyst_native_search_supported",
        "tavily_api_key", "catalyst_source_selection_model", "catalyst_adapter_generation_model",
        "catalyst_classification_model", "openai_api_key", "openai_base_url",
        "firecrawl_api_key", "firecrawl_base_url",
    ):
        assert getattr(args, name) is None


@pytest.mark.parametrize(
    "source",
    ["press_releases", "ir_home=https://example.com/", "=https://example.com/news", "press_releases="],
)
def test_cli_invalid_source_override_returns_two(monkeypatch, capsys, source):
    _install(monkeypatch)

    exit_code = cli.main(["ACME", "--source", source])

    assert exit_code == 2
    assert "error:" in capsys.readouterr().err


def test_cli_duplicate_source_override_returns_two(monkeypatch, capsys):
    _install(monkeypatch)

    exit_code = cli.main([
        "ACME",
        "--source", "press_releases=https://example.com/news",
        "--source", "press_releases=https://example.com/other",
    ])

    assert exit_code == 2
    assert "duplicated" in capsys.readouterr().err


@pytest.mark.parametrize(
    "status,expected",
    [("completed", 0), ("completed_partial", 0), ("unsupported", 1), ("failed", 1)],
)
def test_cli_exit_codes_follow_final_status(monkeypatch, status, expected):
    _install(monkeypatch, result={"status": status, "job_id": "cr_1", "sources": []})

    assert cli.main(["ACME"]) == expected


@pytest.mark.parametrize("error", [ValueError("ticker is required"), RuntimeError("catalyst configuration failed")])
def test_cli_validation_and_configuration_errors_return_two(monkeypatch, capsys, error):
    _install(monkeypatch, error=error)

    exit_code = cli.main(["ACME"])

    assert exit_code == 2
    assert str(error) in capsys.readouterr().err


def test_cli_model_and_api_flags_are_validated_and_forwarded(monkeypatch):
    seen = {}

    def inference(args=None, **kwargs):
        seen["inference"] = args
        return {"client": None, "models": {}}

    def search(args=None, **kwargs):
        seen["search"] = args
        return {}

    monkeypatch.setattr(cli.config, "load_inference_bundle", inference)
    monkeypatch.setattr(cli.config, "load_search_config", search)
    captured = _install(monkeypatch)

    exit_code = cli.main([
        "ACME",
        "--adapter-generation-model", "adapter-m", "--classification-model", "class-m",
        "--openai-api-key", "sk-test", "--openai-base-url", "https://api.example.test",
        "--search-provider", "ddgs",
    ])

    assert exit_code == 0
    assert seen["inference"].catalyst_adapter_generation_model == "adapter-m"
    assert seen["inference"].openai_api_key == "sk-test"
    assert seen["inference"].openai_base_url == "https://api.example.test"
    assert seen["search"].catalyst_search_provider == "ddgs"
    dependencies = captured["dependencies"]
    assert dependencies["config_args"].catalyst_adapter_generation_model == "adapter-m"


def test_cli_search_flags_alone_do_not_require_llm_configuration(monkeypatch):
    seen = {}

    def inference(args=None, **kwargs):
        raise AssertionError("inference configuration should not load")

    def search(args=None, **kwargs):
        seen["search"] = args
        return {}

    monkeypatch.setattr(cli.config, "load_inference_bundle", inference)
    monkeypatch.setattr(cli.config, "load_search_config", search)
    captured = _install(monkeypatch)

    exit_code = cli.main(["ACME", "--search-provider", "ddgs"])

    assert exit_code == 0
    assert seen["search"].catalyst_search_provider == "ddgs"
    assert "config_args" in captured["dependencies"]


def test_cli_invalid_search_provider_returns_two(monkeypatch, capsys):
    _install(monkeypatch)

    exit_code = cli.main(["ACME", "--search-provider", "bogus"])

    assert exit_code == 2
    assert "error:" in capsys.readouterr().err


@pytest.mark.parametrize("mode", ["research", "update", "rediscover"])
def test_cli_mode_flag_flows_into_request(monkeypatch, mode):
    captured = _install(monkeypatch)

    exit_code = cli.main(["NVDA", "--mode", mode])

    assert exit_code == 0
    assert captured["request"]["mode"] == mode


def test_cli_omits_mode_without_flag_to_keep_legacy_dispatch(monkeypatch):
    captured = _install(monkeypatch)

    exit_code = cli.main(["NVDA"])

    assert exit_code == 0
    assert "mode" not in captured["request"]


def test_cli_builds_update_request_without_forcing_discovery(monkeypatch):
    captured = _install(monkeypatch)

    exit_code = cli.main(["NVDA", "--mode", "update"])

    assert exit_code == 0
    assert captured["request"]["mode"] == "update"
    assert captured["request"]["force_discovery"] is False


def test_cli_invalid_mode_exits_two(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["ACME", "--mode", "bogus"])

    assert exc.value.code == 2
    assert "invalid choice" in capsys.readouterr().err


def test_cli_progress_lines_name_feeds_and_gap_search_stages(monkeypatch, capsys):
    async def run(request, *, db_path=None, http_client=None, dependencies=None):
        dependencies["progress"]("feeds", endpoints=2)
        dependencies["progress"]("gap_search", channels="press_releases")
        return {"status": "completed", "job_id": "cr_1", "sources": []}

    monkeypatch.setattr(cli, "run_research", run)
    monkeypatch.setattr(cli, "HttpClient", FakeHttpClient)

    exit_code = cli.main(["NVDA", "--mode", "update"])

    assert exit_code == 0
    err = capsys.readouterr().err
    assert "stage feeds" in err
    assert "stage gap_search" in err


def test_cli_firecrawl_flags_flow_through_collection_config(monkeypatch, capsys):
    seen = {}

    def collection(args=None, **kwargs):
        seen["args"] = args
        return {}

    monkeypatch.setattr(cli.config, "load_collection_config", collection)
    captured = _install(monkeypatch)

    exit_code = cli.main([
        "ACME",
        "--firecrawl-api-key", "fc-secret-key",
        "--firecrawl-base-url", "https://api.firecrawl.test",
    ])

    output = capsys.readouterr()
    assert exit_code == 0
    assert seen["args"].firecrawl_api_key == "fc-secret-key"
    assert seen["args"].firecrawl_base_url == "https://api.firecrawl.test"
    assert captured["dependencies"]["config_args"].firecrawl_api_key == "fc-secret-key"
    assert "fc-secret-key" not in output.out
    assert "fc-secret-key" not in output.err


def test_cli_archive_enrichment_flag_flows_through_collection_config(monkeypatch):
    seen = {}

    def collection(args=None, **kwargs):
        seen["args"] = args
        return {}

    monkeypatch.setattr(cli.config, "load_collection_config", collection)
    captured = _install(monkeypatch)

    exit_code = cli.main(["ACME", "--archive-enrichment"])

    assert exit_code == 0
    assert seen["args"].archive_enrichment_enabled is True
    assert captured["dependencies"]["config_args"].archive_enrichment_enabled is True


def test_cli_collection_config_stays_env_authoritative_without_flags(monkeypatch):
    def collection(args=None, **kwargs):
        raise AssertionError("collection config should not load")

    monkeypatch.setattr(cli.config, "load_collection_config", collection)
    captured = _install(monkeypatch)

    exit_code = cli.main(["ACME"])

    assert exit_code == 0
    assert "config_args" not in captured["dependencies"]

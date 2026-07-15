from pathlib import Path

import pytest

from app.db import growth_cycle
from app.db import us_rates_liquidity
from app.tools import ism_ai_extraction
from scripts import extract_ism_report_ai


def report_html():
    return (
        "<html><article>June 2026 ISM report text. WHAT RESPONDENTS ARE "
        'SAYING "Input costs remain elevated." [Chemical Products]</article></html>'
    )


class FakeDelta:
    def __init__(self, content):
        self.content = content


class FakeChoice:
    def __init__(self, content):
        self.delta = FakeDelta(content)


class FakeChunk:
    def __init__(self, content):
        self.choices = [FakeChoice(content)]


class FakeAsyncStream:
    def __init__(self, chunks):
        self.chunks = chunks

    def __aiter__(self):
        return self._iterate()

    async def _iterate(self):
        for chunk in self.chunks:
            yield chunk


class FakeCompletions:
    def __init__(self, chunks):
        self.chunks = chunks
        self.kwargs = None
        self.calls = 0

    async def create(self, **kwargs):
        self.calls += 1
        self.kwargs = kwargs
        return FakeAsyncStream(self.chunks)


class FakeChat:
    def __init__(self, completions):
        self.completions = completions


class FakeStreamingOpenAIClient:
    def __init__(self, chunks):
        self.completions = FakeCompletions(chunks)
        self.chat = FakeChat(self.completions)


class FakeFlakyCompletions:
    def __init__(self, chunks):
        self.chunks = chunks
        self.calls = 0

    async def create(self, **kwargs):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("temporary connection error")
        return FakeAsyncStream(self.chunks)


class FakeFlakyOpenAIClient:
    def __init__(self, chunks):
        self.completions = FakeFlakyCompletions(chunks)
        self.chat = FakeChat(self.completions)


def test_openai_json_client_streams_and_parses_json_chunks():
    fake_openai = FakeStreamingOpenAIClient(
        [
            FakeChunk('{"ok":'),
            FakeChunk(" true"),
            FakeChunk("}"),
        ]
    )
    client = extract_ism_report_ai.OpenAIJsonClient(fake_openai, "env-model")

    result = client.complete_json("Return JSON")

    assert result == {"ok": True}
    assert fake_openai.completions.kwargs["stream"] is True
    assert fake_openai.completions.kwargs["model"] == "env-model"


@pytest.mark.asyncio
async def test_openai_json_client_supports_async_json_completion():
    fake_openai = FakeStreamingOpenAIClient(
        [
            FakeChunk('{"ok":'),
            FakeChunk(" true"),
            FakeChunk("}"),
        ]
    )
    client = extract_ism_report_ai.OpenAIJsonClient(fake_openai, "env-model")

    result = await client.complete_json_async("Return JSON")

    assert result == {"ok": True}
    assert fake_openai.completions.kwargs["stream"] is True
    assert fake_openai.completions.kwargs["model"] == "env-model"


def test_openai_json_client_retries_stream_connection_errors():
    fake_openai = FakeFlakyOpenAIClient(
        [
            FakeChunk('{"ok":'),
            FakeChunk(" true}"),
        ]
    )
    client = extract_ism_report_ai.OpenAIJsonClient(fake_openai, "env-model")

    result = client.complete_json("Return JSON")

    assert result == {"ok": True}
    assert fake_openai.completions.calls == 2


def test_extract_snapshot_with_client_saves_ai_payload(tmp_path):
    con = us_rates_liquidity.connect(tmp_path / "market_data.sqlite")
    growth_cycle.init_db(con)
    growth_cycle.replace_ism_report_source_snapshot(
        con,
        {
            "source_url": "https://example.com/report.html",
            "source_name": "prnewswire",
            "source_hash": "abc123",
            "fetched_at": "2026-07-15T10:00:00Z",
            "raw_html": report_html(),
            "parse_status": "failed",
            "parse_error": "rankings missing",
            "report_id": None,
            "report_month": None,
        },
    )

    class FakeClient:
        def complete_json(self, prompt):
            payload = ism_ai_extraction_test_payload()
            return payload

    result = extract_ism_report_ai.extract_snapshot(
        con,
        "https://example.com/report.html",
        FakeClient(),
        model="fake-model",
    )

    assert result == {
        "report_id": "ism_manufacturing_2026_06",
        "industry_signals": 2,
    }


def test_extract_snapshot_uses_async_full_extraction(tmp_path, monkeypatch):
    con = us_rates_liquidity.connect(tmp_path / "market_data.sqlite")
    growth_cycle.init_db(con)
    growth_cycle.replace_ism_report_source_snapshot(
        con,
        {
            "source_url": "https://example.com/report.html",
            "source_name": "prnewswire",
            "source_hash": "abc123",
            "fetched_at": "2026-07-15T10:00:00Z",
            "raw_html": report_html(),
            "parse_status": "failed",
            "parse_error": "rankings missing",
            "report_id": None,
            "report_month": None,
        },
    )
    seen = {}

    async def fake_extract(report_text, client, max_attempts=2, max_concurrency=3):
        seen["max_concurrency"] = max_concurrency
        return ism_ai_extraction_test_payload()

    monkeypatch.setattr(
        extract_ism_report_ai.ism_ai_extraction,
        "extract_with_client_async",
        fake_extract,
    )

    result = extract_ism_report_ai.extract_snapshot(
        con,
        "https://example.com/report.html",
        object(),
        model="fake-model",
    )

    assert result["report_id"] == "ism_manufacturing_2026_06"
    assert seen["max_concurrency"] == 3


def test_extract_snapshot_rejects_llm_report_month_mismatch(tmp_path):
    con = us_rates_liquidity.connect(tmp_path / "market_data.sqlite")
    growth_cycle.init_db(con)
    growth_cycle.replace_ism_report_source_snapshot(
        con,
        {
            "source_url": "https://example.com/report.html",
            "source_name": "prnewswire",
            "source_hash": "abc123",
            "fetched_at": "2026-07-15T10:00:00Z",
            "raw_html": report_html(),
            "parse_status": "failed",
            "parse_error": "rankings missing",
            "report_id": None,
            "report_month": None,
        },
    )

    class FakeClient:
        def complete_json(self, prompt):
            payload = ism_ai_extraction_test_payload()
            payload["report"]["report_month"] = "2026-01-01"
            return payload

    with pytest.raises(ValueError, match="llm report_month mismatch"):
        extract_ism_report_ai.extract_snapshot(
            con,
            "https://example.com/report.html",
            FakeClient(),
            model="fake-model",
        )


def test_extract_snapshot_saves_ai_summary(tmp_path):
    con = us_rates_liquidity.connect(tmp_path / "market_data.sqlite")
    growth_cycle.init_db(con)
    growth_cycle.replace_ism_report_source_snapshot(
        con,
        {
            "source_url": "https://example.com/report.html",
            "source_name": "prnewswire",
            "source_hash": "abc123",
            "fetched_at": "2026-07-15T10:00:00Z",
            "raw_html": report_html(),
            "parse_status": "failed",
            "parse_error": "rankings missing",
            "report_id": None,
            "report_month": None,
        },
    )

    class FakeClient:
        def complete_json(self, prompt):
            return ism_ai_extraction_test_payload()

    extract_ism_report_ai.extract_snapshot(
        con,
        "https://example.com/report.html",
        FakeClient(),
        model="fake-model",
    )

    summary = growth_cycle.load_ism_report_ai_summary(
        con,
        "ism_manufacturing_2026_06",
    )
    assert summary["summary_text"]


def test_main_extracts_source_url_with_injected_client(tmp_path, capsys):
    db_path = tmp_path / "market_data.sqlite"
    con = us_rates_liquidity.connect(db_path)
    growth_cycle.init_db(con)
    growth_cycle.replace_ism_report_source_snapshot(
        con,
        {
            "source_url": "https://example.com/report.html",
            "source_name": "prnewswire",
            "source_hash": "abc123",
            "fetched_at": "2026-07-15T10:00:00Z",
            "raw_html": report_html(),
            "parse_status": "failed",
            "parse_error": "rankings missing",
            "report_id": None,
            "report_month": None,
        },
    )
    con.close()

    class FakeClient:
        def complete_json(self, prompt):
            return ism_ai_extraction_test_payload()

    exit_code = extract_ism_report_ai.main(
        [
            "--db-path",
            str(db_path),
            "--source-url",
            "https://example.com/report.html",
            "--model",
            "fake-model",
        ],
        client_factory=lambda config: FakeClient(),
    )

    assert exit_code == 0
    assert "ism_manufacturing_2026_06: industry_signals=2" in capsys.readouterr().out


def test_main_without_model_uses_env_model_config(tmp_path, monkeypatch):
    db_path = tmp_path / "market_data.sqlite"
    con = us_rates_liquidity.connect(db_path)
    growth_cycle.init_db(con)
    growth_cycle.replace_ism_report_source_snapshot(
        con,
        {
            "source_url": "https://example.com/report.html",
            "source_name": "prnewswire",
            "source_hash": "abc123",
            "fetched_at": "2026-07-15T10:00:00Z",
            "raw_html": report_html(),
            "parse_status": "failed",
            "parse_error": "rankings missing",
            "report_id": None,
            "report_month": None,
        },
    )
    con.close()
    monkeypatch.setenv("OPENAI_MODEL", "env-model")
    seen = {}

    class FakeClient:
        def complete_json(self, prompt):
            return ism_ai_extraction_test_payload()

    def fake_client_factory(config):
        seen["model"] = config["model"]
        return FakeClient()

    exit_code = extract_ism_report_ai.main(
        [
            "--db-path",
            str(db_path),
            "--source-url",
            "https://example.com/report.html",
        ],
        client_factory=fake_client_factory,
    )

    assert exit_code == 0
    assert seen["model"] == "env-model"


def test_build_client_uses_granular_llm_timeout(monkeypatch):
    seen = {}

    def fake_build_async_client(config, **kwargs):
        seen.update(kwargs)
        return object()

    monkeypatch.setattr(
        extract_ism_report_ai.llm,
        "build_async_client",
        fake_build_async_client,
    )

    extract_ism_report_ai.build_client({"api_key": "x", "model": "env-model"})

    assert "Timeout(connect=20.0" in repr(seen["timeout"])
    assert "read=300.0" in repr(seen["timeout"])
    assert "write=300.0" in repr(seen["timeout"])


def ism_ai_extraction_test_payload():
    from tests.test_ism_ai_extraction import valid_extraction

    return valid_extraction()

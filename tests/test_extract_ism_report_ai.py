from pathlib import Path

import pytest

from app.db import growth_cycle
from app.db import macro_indicators
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


def test_extract_snapshot_uses_checkpointed_extraction(tmp_path, monkeypatch):
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

    async def fake_extract(
        con,
        report_text,
        source,
        client,
        force_sections=None,
        retry_failed=True,
        sections=None,
        max_concurrency=3,
        progress=None,
    ):
        seen["source"] = source
        payload = ism_ai_extraction_test_payload()
        return {k: v for k, v in payload.items() if k != "ai_summary"}

    def fake_summary(*args, **kwargs):
        payload = ism_ai_extraction_test_payload()
        return payload["ai_summary"]

    monkeypatch.setattr(
        extract_ism_report_ai,
        "extract_or_load_factual_sections_async",
        fake_extract,
    )
    monkeypatch.setattr(
        extract_ism_report_ai,
        "generate_or_load_summary",
        fake_summary,
    )

    result = extract_ism_report_ai.extract_snapshot(
        con,
        "https://example.com/report.html",
        object(),
        model="fake-model",
    )

    assert result["report_id"] == "ism_manufacturing_2026_06"
    assert seen["source"]["source_url"] == "https://example.com/report.html"


def test_extract_snapshot_facts_only_saves_dashboard_metrics(tmp_path, monkeypatch):
    con = us_rates_liquidity.connect(tmp_path / "market_data.sqlite")
    growth_cycle.init_db(con)
    source_url = "https://example.com/report.html"
    growth_cycle.replace_ism_report_source_snapshot(
        con,
        {
            "source_url": source_url,
            "source_name": "prnewswire",
            "source_hash": "abc123",
            "fetched_at": "2026-07-15T10:00:00Z",
            "raw_html": report_html(),
            "parse_status": "prepared",
            "parse_error": None,
            "report_id": "ism_manufacturing_2026_06",
            "report_month": "2026-06-01",
        },
    )
    factual = {
        key: value
        for key, value in ism_ai_extraction_test_payload().items()
        if key != "ai_summary"
    }

    async def fake_extract(*args, **kwargs):
        return factual

    monkeypatch.setattr(
        extract_ism_report_ai,
        "extract_or_load_factual_sections_async",
        fake_extract,
    )

    extract_ism_report_ai.extract_snapshot(
        con,
        source_url,
        object(),
        model="fake-model",
        facts_only=True,
    )

    points = macro_indicators.load_macro_indicator_points(
        con,
        "ism_manufacturing_pmi",
    )
    rows = growth_cycle.load_ism_at_a_glance_rows(
        con,
        "ism_manufacturing_2026_06",
    )

    assert points[-1]["date"] == "2026-06-01"
    assert points[-1]["value"] == 50.0
    assert len(rows) == 11


def test_facts_only_promotion_rolls_back_core_values_and_provenance_on_late_failure(
    tmp_path, monkeypatch
):
    con = us_rates_liquidity.connect(tmp_path / "market_data.sqlite")
    growth_cycle.init_db(con)
    source_url = "https://example.com/report.html"
    report_id = "ism_manufacturing_2026_06"
    growth_cycle.replace_ism_report_source_snapshot(
        con,
        {
            "source_url": source_url,
            "source_name": "prnewswire",
            "source_hash": "new-hash",
            "fetched_at": "2026-07-15T10:00:00Z",
            "raw_html": report_html(),
            "parse_status": "prepared",
            "parse_error": None,
            "report_id": report_id,
            "report_month": "2026-06-01",
        },
    )
    macro_indicators.merge_macro_indicator_points(
        con,
        {
            "series_id": "ism_manufacturing_pmi",
            "title": "Manufacturing PMI",
            "units": "index",
            "source": "prior core source",
        },
        [
            {
                "date": "2026-06-01",
                "value": 47.0,
                "source": "prior core source",
            }
        ],
    )
    old_report = {
        "report_id": report_id,
        "report_month": "2026-06-01",
        "title": "Prior core report",
        "source_url": "https://example.com/prior",
        "source_hash": "prior-hash",
        "fetched_at": "2026-07-01T10:00:00Z",
        "parse_status": "ok",
        "next_report_period": None,
        "next_release_at": None,
        "next_release_label": "",
    }
    growth_cycle.replace_ism_report_snapshot(con, old_report, [])
    growth_cycle.replace_ism_at_a_glance_rows(
        con,
        [
            {
                "report_id": report_id,
                "report_month": "2026-06-01",
                "series_id": "ism_manufacturing_pmi",
                "label": "Manufacturing PMI",
                "current_value": 47.0,
                "previous_value": 46.0,
                "point_change": 1.0,
                "direction": "Growing",
                "rate_of_change": "Faster",
                "trend_months": 1,
                "source_url": "https://example.com/prior",
                "source_hash": "prior-hash",
            }
        ],
    )
    factual = {
        key: value
        for key, value in ism_ai_extraction_test_payload().items()
        if key != "ai_summary"
    }

    async def fake_extract(*args, **kwargs):
        return factual

    monkeypatch.setattr(
        extract_ism_report_ai,
        "extract_or_load_factual_sections_async",
        fake_extract,
    )
    monkeypatch.setattr(
        extract_ism_report_ai.growth_cycle,
        "replace_ism_ai_report_outputs",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("late failure")),
    )

    with pytest.raises(RuntimeError, match="late failure"):
        extract_ism_report_ai.extract_snapshot(
            con,
            source_url,
            object(),
            model="fake-model",
            facts_only=True,
        )

    point = macro_indicators.load_macro_indicator_points(
        con,
        "ism_manufacturing_pmi",
    )[-1]
    report = growth_cycle.load_latest_ism_report_snapshot(con)
    row = growth_cycle.load_ism_at_a_glance_rows(con, report_id)[0]
    assert point["value"] == 47.0
    assert point["source"] == "prior core source"
    assert report["source_url"] == "https://example.com/prior"
    assert report["source_hash"] == "prior-hash"
    assert row["current_value"] == 47.0
    assert row["source_hash"] == "prior-hash"


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


def test_extract_snapshot_skips_ok_section_checkpoint(tmp_path, monkeypatch):
    from app.db import growth_cycle

    payload = ism_ai_extraction_test_payload()
    factual = {key: value for key, value in payload.items() if key != "ai_summary"}
    db_path = tmp_path / "market_data.sqlite"
    con = us_rates_liquidity.connect(db_path)
    growth_cycle.init_db(con)
    source_url = "https://example.com/report.html"
    growth_cycle.replace_ism_report_source_snapshot(
        con,
        {
            "source_url": source_url,
            "source_name": "prnewswire",
            "source_hash": "abc123",
            "fetched_at": "2026-07-15T10:00:00Z",
            "raw_html": report_html(),
            "parse_status": "prepared",
            "parse_error": None,
            "report_id": "ism_manufacturing_2026_06",
            "report_month": "2026-06-01",
        },
    )
    growth_cycle.replace_ism_ai_section_extraction(
        con,
        {
            "report_id": "ism_manufacturing_2026_06",
            "source_url": source_url,
            "report_month": "2026-06-01",
            "source_hash": "abc123",
            "section_name": "report",
            "status": "ok",
            "payload_json": {"report": factual["report"]},
            "error": None,
            "attempt_count": 1,
            "model": "fake-model",
            "prompt_version": ism_ai_extraction.PROMPT_VERSION,
            "updated_at": "2026-07-15T10:00:00Z",
        },
    )
    calls = []

    class FakeClient:
        def complete_json(self, prompt):
            calls.append(prompt)
            if "Extract only report metadata" in prompt:
                raise AssertionError("report section should be skipped")
            if "Extract only MANUFACTURING AT A GLANCE" in prompt:
                return {"at_a_glance_rows": factual["at_a_glance_rows"]}
            if "Extract only industry signal lists" in prompt:
                return {"industry_signals": factual["industry_signals"]}
            if "Extract only respondent comments and commodities" in prompt:
                return {
                    "respondent_comments": factual["respondent_comments"],
                    "commodities": factual["commodities"],
                }
            if "Extract only narrative facts" in prompt:
                return {"narrative_facts": factual["narrative_facts"]}
            if "Summarize only the validated ISM Manufacturing facts" in prompt:
                return {
                    "summary_text": payload["ai_summary"]["summary_text"],
                    "summary_text_zh": payload["ai_summary"]["summary_text_zh"],
                    "headline_changes": payload["ai_summary"]["headline_changes"],
                    "major_changes": payload["ai_summary"]["major_changes"],
                    "major_changes_zh": payload["ai_summary"]["major_changes_zh"],
                    "cat_takeaway_en": payload["ai_summary"]["cat_takeaway_en"],
                    "cat_takeaway_zh": payload["ai_summary"]["cat_takeaway_zh"],
                }
            raise AssertionError(prompt)

    result = extract_ism_report_ai.extract_snapshot(
        con,
        source_url,
        FakeClient(),
        model="fake-model",
    )

    assert result["report_id"] == "ism_manufacturing_2026_06"
    assert not any("Extract only report metadata" in prompt for prompt in calls)


def test_should_reuse_section_rejects_duplicate_industry_signal_checkpoint():
    evidence = (
        "The two manufacturing industries reporting growth are: Machinery; "
        "and Chemical Products."
    )
    existing = {
        "section_name": "industry_signals",
        "status": "ok",
        "payload_json": {
            "industry_signals": [
                {
                    "signal_type": "overall_growth",
                    "direction": "growth",
                    "industry": "Machinery",
                    "rank": 1,
                    "evidence_text": evidence,
                },
                {
                    "signal_type": "overall_growth",
                    "direction": "growth",
                    "industry": "Machinery",
                    "rank": 2,
                    "evidence_text": evidence,
                },
            ]
        },
    }

    reuse, error = extract_ism_report_ai.should_reuse_section(
        existing,
        set(),
        True,
        evidence,
    )

    assert reuse is False
    assert "duplicated" in error


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


def test_summary_only_uses_stored_sections_without_section_calls(tmp_path):
    payload = ism_ai_extraction_test_payload()
    factual = {key: value for key, value in payload.items() if key != "ai_summary"}
    con = growth_cycle.connect(tmp_path / "market_data.sqlite")
    source_url = "https://example.com/report.html"
    source_hash = "abc123"
    for section in [
        ("report", {"report": factual["report"]}),
        ("at_a_glance_rows", {"at_a_glance_rows": factual["at_a_glance_rows"]}),
        ("industry_signals", {"industry_signals": factual["industry_signals"]}),
        (
            "comments_commodities",
            {
                "respondent_comments": factual["respondent_comments"],
                "commodities": factual["commodities"],
            },
        ),
        ("narrative_facts", {"narrative_facts": factual["narrative_facts"]}),
    ]:
        growth_cycle.replace_ism_ai_section_extraction(
            con,
            {
                "report_id": factual["report"]["report_id"],
                "source_url": source_url,
                "report_month": factual["report"]["report_month"],
                "source_hash": source_hash,
                "section_name": section[0],
                "status": "ok",
                "payload_json": section[1],
                "error": None,
                "attempt_count": 1,
                "model": "fake-model",
                "prompt_version": ism_ai_extraction.PROMPT_VERSION,
                "updated_at": "2026-07-15T10:00:00Z",
            },
        )

    class FakeClient:
        def complete_json(self, prompt):
            if "Summarize only the validated ISM Manufacturing facts" not in prompt:
                raise AssertionError("summary-only should not extract factual sections")
            return {
                "summary_text": payload["ai_summary"]["summary_text"],
                "summary_text_zh": payload["ai_summary"]["summary_text_zh"],
                "headline_changes": payload["ai_summary"]["headline_changes"],
                "major_changes": payload["ai_summary"]["major_changes"],
                "major_changes_zh": payload["ai_summary"]["major_changes_zh"],
                "cat_takeaway_en": payload["ai_summary"]["cat_takeaway_en"],
                "cat_takeaway_zh": payload["ai_summary"]["cat_takeaway_zh"],
            }

    summary = extract_ism_report_ai.generate_or_load_summary(
        con,
        factual,
        {
            "report_id": factual["report"]["report_id"],
            "report_month": factual["report"]["report_month"],
            "source_url": source_url,
            "source_hash": source_hash,
            "model": "fake-model",
            "updated_at": "2026-07-15T10:00:00Z",
        },
        FakeClient(),
        force_summary=True,
        guidance="Avoid confusing contraction streak wording.",
    )

    assert summary["summary_text_zh"]


def test_main_passes_summary_only_guidance(tmp_path, monkeypatch):
    seen = {}

    def fake_extract_snapshot_with_options(con, source_url, client, model, **kwargs):
        seen.update(kwargs)
        return {"report_id": "ism_manufacturing_2026_06", "industry_signals": 2}

    monkeypatch.setattr(
        extract_ism_report_ai,
        "extract_snapshot_with_options",
        fake_extract_snapshot_with_options,
    )

    exit_code = extract_ism_report_ai.main(
        [
            "--db-path",
            str(tmp_path / "market_data.sqlite"),
            "--source-url",
            "https://example.com/report.html",
            "--summary-only",
            "--force-summary",
            "--summary-guidance",
            "Use current expansion streak wording.",
        ],
        client_factory=lambda config: object(),
    )

    assert exit_code == 0
    assert seen["summary_only"] is True
    assert seen["force_summary"] is True
    assert seen["summary_guidance"] == "Use current expansion streak wording."


def ism_ai_extraction_test_payload():
    from tests.test_ism_ai_extraction import valid_extraction

    return valid_extraction()

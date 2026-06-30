import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_refine_module():
    path = ROOT / "scripts" / "refine_method_extraction.py"
    spec = importlib.util.spec_from_file_location("refine_method_extraction", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_refine_arg_parser_defaults_to_separate_refinement_directories():
    module = load_refine_module()

    args = module.build_arg_parser().parse_args([])

    assert Path(args.notes_dir).name == "method_notes"
    assert Path(args.input_dir).name == "extraction_results"
    assert Path(args.output_dir).name == "extraction_refined"
    assert Path(args.prompts_dir).name == "refinement_prompts"
    assert Path(args.repairs_dir).name == "refinement_repairs"
    assert Path(args.audits_dir).name == "refinement_audits"
    assert args.refine == "indicators"
    assert args.max_audit_repair_rounds == 2
    assert args.workers == 2


import json


def baseline_extraction(
    document="method_notes/P10 Leading Indicators 6_method_notes.md",
):
    return {
        "document": document,
        "title": "",
        "items": [
            {
                "id": "building_permits_sa_annual_rate",
                "type": "indicator",
                "title": "Building Permits SA Annual Rate",
                "summary": "Seasonally adjusted annual rate of building permits.",
                "decision_area": "macro regime",
                "formula": "",
                "required_inputs": [],
                "long_side_usage": "",
                "short_side_usage": "",
                "compute_status": "manual_input",
                "future_tool_hooks": [],
                "source_refs": [
                    {
                        "document": document,
                        "section": "Methodology / Workflow",
                    }
                ],
            }
        ],
        "proposed_nodes": [],
        "dependencies": [],
    }


def test_normalize_patch_generates_source_refs_from_source_sections():
    module = load_refine_module()
    patch = {
        "items": [
            {
                "id": "permits_mom_pct_change",
                "type": "formula",
                "title": "Permits Month-on-Month Percentage Change",
                "summary": "Computes month-on-month percentage change in building permits.",
                "decision_area": "macro regime",
                "formula": "(permits_t - permits_t_minus_1) / permits_t_minus_1 * 100",
                "required_inputs": ["macro.permits_sa", "macro.permits_sa_lag_1"],
                "long_side_usage": "Rising permits can support long bias when confirmed.",
                "short_side_usage": "Falling permits can support short bias when confirmed.",
                "compute_status": "future_tool_hook",
                "future_tool_hooks": ["census_housing_permits"],
                "source_sections": ["Methodology / Workflow"],
            }
        ],
        "proposed_nodes": [],
        "dependencies": [],
    }

    normalized = module._normalize_patch(
        patch,
        baseline_extraction(),
        "method_notes/P10 Leading Indicators 6_method_notes.md",
    )

    assert normalized["items"][0]["source_refs"] == [
        {
            "document": "",
            "section": "Methodology / Workflow",
        }
    ]
    assert "source_sections" not in normalized["items"][0]


def test_write_json_atomic_replaces_target_without_tmp_file(tmp_path):
    module = load_refine_module()
    target = tmp_path / "refined.json"

    module._write_json_atomic(target, {"value": 1})

    assert json.loads(target.read_text(encoding="utf-8")) == {"value": 1}
    assert not list(tmp_path.glob("*.tmp"))


def test_high_signal_sections_keep_methodology_and_checklist_but_drop_transcript_gaps():
    module = load_refine_module()
    doc = {
        "path": "",
        "title": "",
        "sections": {
            "Key Points": "Building permits have thresholds.",
            "Methodology / Workflow": "Compute month-on-month and year-on-year changes.",
            "Examples & Applications": "Long historical example.",
            "Actionable Checklist": "Calculate a 12-month moving average.",
            "Transcript Gaps / Incomplete Segments": "None flagged.",
        },
    }

    sections = module._high_signal_sections(doc)

    assert "Key Points" in sections
    assert "Methodology / Workflow" in sections
    assert "Actionable Checklist" in sections
    assert "Transcript Gaps / Incomplete Segments" not in sections


def test_indicator_refinement_prompt_is_patch_only_and_mentions_existing_ids():
    module = load_refine_module()
    doc = {
        "path": "",
        "title": "",
        "sections": {
            "Methodology / Workflow": "Compute month-on-month and year-on-year changes.",
            "Actionable Checklist": "Calculate a 12-month moving average.",
        },
    }
    baseline = baseline_extraction()

    prompt = module._indicator_refinement_prompt(doc, baseline)

    assert "Return strict JSON" in prompt
    assert "patch-only refinement" in prompt
    assert "Do not rewrite the full extraction" in prompt
    assert "building_permits_sa_annual_rate" in prompt
    assert "month-on-month" in prompt
    assert "source_sections" in prompt
    assert "source_refs" not in prompt


def test_merge_patch_adds_new_items_and_keeps_existing_items():
    module = load_refine_module()
    baseline = baseline_extraction()
    patch = {
        "document": baseline["document"],
        "title": baseline["title"],
        "items": [
            {
                "id": "permits_mom_pct_change",
                "type": "formula",
                "title": "Permits Month-on-Month Percentage Change",
                "summary": "Computes month-on-month percentage change in building permits.",
                "decision_area": "macro regime",
                "formula": "(permits_t - permits_t_minus_1) / permits_t_minus_1 * 100",
                "required_inputs": ["macro.permits_sa", "macro.permits_sa_lag_1"],
                "long_side_usage": "",
                "short_side_usage": "",
                "compute_status": "future_tool_hook",
                "future_tool_hooks": ["census_housing_permits"],
                "source_refs": [
                    {
                        "document": baseline["document"],
                        "section": "Methodology / Workflow",
                    }
                ],
            }
        ],
        "proposed_nodes": [],
        "dependencies": [],
    }

    merged = module._merge_patch(baseline, patch, allow_overwrite=False)

    assert [item["id"] for item in merged["items"]] == [
        "building_permits_sa_annual_rate",
        "permits_mom_pct_change",
    ]


def test_merge_patch_rejects_duplicate_item_ids_by_default():
    module = load_refine_module()
    baseline = baseline_extraction()
    patch = {
        "document": baseline["document"],
        "title": baseline["title"],
        "items": [dict(baseline["items"][0])],
        "proposed_nodes": [],
        "dependencies": [],
    }

    try:
        module._merge_patch(baseline, patch, allow_overwrite=False)
    except ValueError as exc:
        assert str(exc) == "repair item building_permits_sa_annual_rate already exists"
    else:
        raise AssertionError("expected duplicate item rejection")


import asyncio


class FakeDelta:
    def __init__(self, content):
        self.content = content


class FakeStreamChoice:
    def __init__(self, content="", finish_reason=None):
        self.delta = FakeDelta(content)
        self.finish_reason = finish_reason


class FakeStreamChunk:
    def __init__(self, content="", finish_reason=None):
        self.choices = [FakeStreamChoice(content, finish_reason=finish_reason)]


class FakeStream:
    def __init__(self, chunks):
        self.chunks = chunks

    async def __aiter__(self):
        for chunk in self.chunks:
            yield chunk


class FakeAsyncCompletions:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    async def create(self, **kwargs):
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class FakeAsyncClient:
    def __init__(self, outcomes):
        completions = FakeAsyncCompletions(outcomes)
        self.chat = type("Chat", (), {"completions": completions})()
        self.completions = completions


def test_call_openai_json_retries_transient_refinement_failure():
    module = load_refine_module()
    client = FakeAsyncClient(
        [
            RuntimeError("temporary"),
            FakeStream(
                [
                    FakeStreamChunk(
                        '{"items":[],"proposed_nodes":[],"dependencies":[]}',
                        finish_reason="stop",
                    )
                ]
            ),
        ]
    )

    result = asyncio.run(
        module._call_openai_json(
            client,
            model="gpt-test",
            prompt="prompt",
            max_output_tokens=12000,
            max_retries=2,
            retry_base_delay=0,
            label="P10 refinement",
        )
    )

    assert result == {"items": [], "proposed_nodes": [], "dependencies": []}
    assert client.completions.calls == 2


def test_call_openai_json_does_not_retry_length_refinement_failure():
    module = load_refine_module()
    client = FakeAsyncClient(
        [FakeStream([FakeStreamChunk('{"items":[]}', finish_reason="length")])]
    )

    try:
        asyncio.run(
            module._call_openai_json(
                client,
                model="gpt-test",
                prompt="prompt",
                max_output_tokens=12000,
                max_retries=3,
                retry_base_delay=0,
                label="P10 refinement",
            )
        )
    except RuntimeError as exc:
        assert "finish_reason=length" in str(exc)
    else:
        raise AssertionError("expected length failure")

    assert client.completions.calls == 1


def test_refine_doc_merges_patch_and_writes_prompt_and_output(tmp_path):
    module = load_refine_module()
    doc = {
        "path": "",
        "title": "",
        "sections": {
            "Methodology / Workflow": "Compute month-on-month changes.",
            "Actionable Checklist": "Calculate year-on-year changes.",
        },
    }
    baseline = baseline_extraction()
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    prompts_dir = tmp_path / "prompts"
    repairs_dir = tmp_path / "repairs"
    audits_dir = tmp_path / "audits"
    input_path = module._extraction_path_for(input_dir, doc)
    module._write_json_atomic(input_path, baseline)
    patch = {
        "items": [
            {
                "id": "permits_mom_pct_change",
                "type": "formula",
                "title": "Permits Month-on-Month Percentage Change",
                "summary": "Computes month-on-month percentage change in building permits.",
                "decision_area": "macro regime",
                "formula": "(permits_t - permits_t_minus_1) / permits_t_minus_1 * 100",
                "required_inputs": ["macro.permits_sa", "macro.permits_sa_lag_1"],
                "long_side_usage": "",
                "short_side_usage": "",
                "compute_status": "future_tool_hook",
                "future_tool_hooks": ["census_housing_permits"],
                "source_sections": ["Methodology / Workflow"],
            }
        ],
        "proposed_nodes": [],
        "dependencies": [],
    }

    async def fake_call(prompt, label):
        return patch

    result_path = asyncio.run(
        module._refine_doc(
            doc,
            input_dir,
            output_dir,
            prompts_dir,
            repairs_dir,
            audits_dir,
            type(
                "Args",
                (),
                {
                    "allow_repair_overwrite": False,
                    "write_prompts_only": False,
                    "max_audit_repair_rounds": 0,
                },
            )(),
            fake_call,
        )
    )

    refined = json.loads(Path(result_path).read_text(encoding="utf-8"))

    assert [item["id"] for item in refined["items"]] == [
        "building_permits_sa_annual_rate",
        "permits_mom_pct_change",
    ]
    assert list(prompts_dir.glob("*.prompt.md"))
    assert list(repairs_dir.glob("*.patch.json"))


def test_should_skip_existing_refined_output(tmp_path):
    module = load_refine_module()
    doc = {"path": ""}
    args = type("Args", (), {"skip_existing": True})()

    assert module._should_skip_existing(tmp_path, doc, args) is False
    module._write_json_atomic(module._extraction_path_for(tmp_path, doc), {"ok": True})

    assert module._should_skip_existing(tmp_path, doc, args) is True


def test_audit_prompt_compares_note_to_refined_extraction():
    module = load_refine_module()
    doc = {
        "path": "",
        "title": "",
        "sections": {
            "Methodology / Workflow": "Compute month-on-month and year-on-year changes.",
        },
    }
    refined = baseline_extraction()

    prompt = module._audit_prompt(doc, refined)

    assert "semantic audit" in prompt
    assert "missing or under-specified" in prompt
    assert "building_permits_sa_annual_rate" in prompt
    assert "month-on-month" in prompt


def test_repair_prompt_is_patch_only_and_uses_audit_findings():
    module = load_refine_module()
    doc = {
        "path": "",
        "title": "",
        "sections": {
            "Methodology / Workflow": "Compute month-on-month and year-on-year changes.",
        },
    }
    refined = baseline_extraction()
    audit = {
        "findings": [
            {
                "kind": "formula",
                "title_hint": "Permits Month-on-Month Percentage Change",
                "evidence": "Compute month-on-month changes.",
                "source_section": "Methodology / Workflow",
                "reason": "Missing standalone formula.",
            }
        ]
    }

    prompt = module._repair_prompt(doc, refined, audit)

    assert "patch-only repair" in prompt
    assert "Permits Month-on-Month Percentage Change" in prompt
    assert "Do not rewrite the full extraction" in prompt
    assert "source_sections" in prompt


def test_apply_audit_repair_round_adds_patch_when_findings_exist(tmp_path):
    module = load_refine_module()
    doc = {
        "path": "",
        "title": "",
        "sections": {
            "Methodology / Workflow": "Compute month-on-month changes.",
        },
    }
    refined = baseline_extraction()
    calls = []

    async def fake_call(prompt, label):
        calls.append((prompt, label))
        if "semantic audit" in prompt:
            return {
                "findings": [
                    {
                        "kind": "formula",
                        "title_hint": "Permits Month-on-Month Percentage Change",
                        "evidence": "Compute month-on-month changes.",
                        "source_section": "Methodology / Workflow",
                        "reason": "Missing standalone formula.",
                    }
                ]
            }
        return {
            "items": [
                {
                    "id": "permits_mom_pct_change",
                    "type": "formula",
                    "title": "Permits Month-on-Month Percentage Change",
                    "summary": "Computes month-on-month percentage change in building permits.",
                    "decision_area": "macro regime",
                    "formula": "(permits_t - permits_t_minus_1) / permits_t_minus_1 * 100",
                    "required_inputs": ["macro.permits_sa", "macro.permits_sa_lag_1"],
                    "long_side_usage": "",
                    "short_side_usage": "",
                    "compute_status": "future_tool_hook",
                    "future_tool_hooks": ["census_housing_permits"],
                    "source_sections": ["Methodology / Workflow"],
                }
            ],
            "proposed_nodes": [],
            "dependencies": [],
        }

    repaired = asyncio.run(
        module._apply_audit_repair_rounds(
            doc,
            refined,
            tmp_path,
            tmp_path,
            type(
                "Args",
                (),
                {"max_audit_repair_rounds": 1, "allow_repair_overwrite": False},
            )(),
            fake_call,
        )
    )

    assert [item["id"] for item in repaired["items"]] == [
        "building_permits_sa_annual_rate",
        "permits_mom_pct_change",
    ]
    assert len(calls) == 2

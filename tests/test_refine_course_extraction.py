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

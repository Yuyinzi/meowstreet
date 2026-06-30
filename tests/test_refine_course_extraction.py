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

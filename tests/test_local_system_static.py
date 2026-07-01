from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
method_SYSTEM_JS = ROOT / "static" / "method-system.js"


def test_graph_node_mapping_preserves_source_refs_separately_from_method_basis():
    script = method_SYSTEM_JS.read_text(encoding="utf-8")

    assert "source_refs: node.source_refs || []" in script
    assert "evaluation_basis: result.method_basis ||" in script
    assert "method_basis: result.method_basis || node.source_refs || []" not in script


def test_method_basis_renderer_shortens_method_note_paths():
    script = method_SYSTEM_JS.read_text(encoding="utf-8")

    assert "function fmtSourceDocument(document)" in script
    assert '.replace(/^method_notes\\//, "")' in script
    assert '.replace(/_method_notes\\.md$/, "")' in script
    assert "fmtSourceDocument(ref.document)" in script


def test_local_system_js_supports_grouped_checks():
    content = method_SYSTEM_JS.read_text(encoding="utf-8")

    assert "groupChecksByGroup" in content
    assert "Instrument Identity" in content
    assert "Market Data" in content
    assert "Liquidity / Tradability" in content

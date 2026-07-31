from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TICKER_WORKFLOW_JS = ROOT / "static" / "ticker-workflow.js"
TICKER_WORKFLOW_HTML = ROOT / "static" / "ticker-workflow.html"


def test_graph_node_mapping_preserves_source_refs_separately_from_method_basis():
    script = TICKER_WORKFLOW_JS.read_text(encoding="utf-8")

    assert "source_refs: node.source_refs || []" in script
    assert "evaluation_basis: result.method_basis ||" in script
    assert "method_basis: result.method_basis || node.source_refs || []" not in script


def test_method_basis_renderer_shortens_method_note_paths():
    script = TICKER_WORKFLOW_JS.read_text(encoding="utf-8")

    assert "function fmtSourceDocument(document)" in script
    assert '.replace(/^method_notes\\//, "")' in script
    assert '.replace(/_method_notes\\.md$/, "")' in script
    assert "fmtSourceDocument(ref.document)" in script


def test_ticker_workflow_js_supports_grouped_checks():
    content = TICKER_WORKFLOW_JS.read_text(encoding="utf-8")

    assert "groupChecksByGroup" in content
    assert "Instrument Identity" in content
    assert "Market Data" in content
    assert "Liquidity / Tradability" in content


def test_ticker_workflow_js_supports_macro_dashboard_grid_mock():
    content = TICKER_WORKFLOW_JS.read_text(encoding="utf-8")

    assert "MOCK_MACRO_DASHBOARD_GROUPS" in content
    assert "renderMacroDashboard" in content
    assert "macroDashboardSection" in content
    assert "metric-tile-${escapeHtml(status)}" in content


def test_ticker_workflow_html_links_to_macro_dashboard():
    html = TICKER_WORKFLOW_HTML.read_text(encoding="utf-8")

    assert 'href="/macro-dashboard.html"' in html
    assert "Macro Dashboard" in html

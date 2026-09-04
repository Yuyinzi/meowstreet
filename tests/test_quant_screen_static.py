from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


_ASSISTANT_IDS = (
    "marketAssistantFab",
    "marketAssistantWindow",
    "marketAssistantWindowHead",
    "marketAssistantNewConversation",
    "marketAssistantWindowClose",
    "marketAssistantLog",
    "marketAssistantForm",
    "marketAssistantQuestion",
    "marketAssistantSubmit",
    "marketAssistantExternalSearch",
    "marketAssistantDeepResearch",
    "marketAssistantDeepAnalysis",
    "marketAssistantStatus",
    "marketAssistantValidationDisabledNotice",
)


def test_quant_screen_mounts_assistant_and_ticker_detail_panel():
    html = (ROOT / "static" / "quant-screen.html").read_text(encoding="utf-8")

    assert '<main class="workflow-shell quant-shell" id="quantScreenApp">' in html
    assert '<div class="quant-main">' in html
    assert '<aside class="detail-panel" id="tickerDetailPanel"' in html
    assert 'href="/market-assistant.css?v=' in html
    assert 'src="/quant-screen-ticker-panel.js?v=' in html
    assert 'src="/market-assistant.js?v=' in html
    assert "marked.min.js" in html
    for element_id in _ASSISTANT_IDS:
        assert f'id="{element_id}"' in html


def test_ticker_context_mounts_assistant():
    html = (ROOT / "static" / "ticker-context.html").read_text(encoding="utf-8")

    assert 'href="/market-assistant.css?v=' in html
    assert 'src="/market-assistant.js?v=' in html
    assert "marked.min.js" in html
    for element_id in _ASSISTANT_IDS:
        assert f'id="{element_id}"' in html


def test_quant_screen_wires_panel_clicks_and_auto_interpretation():
    source = (ROOT / "static" / "quant-screen.js").read_text(encoding="utf-8")
    panel_source = (ROOT / "static" / "quant-screen-ticker-panel.js").read_text(
        encoding="utf-8"
    )

    assert 'data-symbol="' in source
    assert "QuantScreenTickerPanel.open" in source
    assert "openWithContext" in source
    assert "tickerQuantContextText" in panel_source
    assert "window.QuantScreenTickerPanel" in panel_source
    assert "/api/ticker-context/" in panel_source
    assert "/api/ticker-quant/" in panel_source
    assert "estimateConsensusLine" in panel_source
    assert "Estimate Consensus" in panel_source


def test_ticker_context_auto_interprets_quant_result():
    source = (ROOT / "static" / "ticker-context.js").read_text(encoding="utf-8")

    assert "openWithContext" in source
    assert "量化体检结果" in source


def test_ticker_context_quant_card_offers_forced_refresh():
    source = (ROOT / "static" / "ticker-context.js").read_text(encoding="utf-8")

    assert 'id="quantRefresh"' in source
    assert "refresh=true" in source
    assert "Refreshing…" in source


def test_ticker_context_discards_stale_quant_responses():
    source = (ROOT / "static" / "ticker-context.js").read_text(encoding="utf-8")

    assert "var quantRequestId = 0;" in source
    assert "requestId !== quantRequestId" in source


def test_ticker_context_discards_peer_response_after_quant_refresh():
    source = (ROOT / "static" / "ticker-context.js").read_text(encoding="utf-8")

    assert "var peerRequestId = quantRequestId;" in source
    assert source.count("peerRequestId !== quantRequestId") == 2


def test_ticker_context_disables_peer_comparison_during_refresh():
    source = (ROOT / "static" / "ticker-context.js").read_text(encoding="utf-8")

    assert 'var peerApply = document.getElementById("quantPeerApply");' in source
    assert "peerApply.disabled = true;" in source
    assert "peerApply.disabled = false;" in source


def test_ticker_views_explain_unavailable_dividend_and_ratios():
    context_source = (ROOT / "static" / "ticker-context.js").read_text(
        encoding="utf-8"
    )
    panel_source = (ROOT / "static" / "quant-screen-ticker-panel.js").read_text(
        encoding="utf-8"
    )

    for source in (context_source, panel_source):
        assert "escapeHtml(dividend.note)" in source
        assert "escapeHtml(ratio.note)" in source
        assert "dividend.yield == null && dividend.note" in source


def test_ticker_views_label_unreported_dividend_yield():
    context_source = (ROOT / "static" / "ticker-context.js").read_text(
        encoding="utf-8"
    )
    panel_source = (ROOT / "static" / "quant-screen-ticker-panel.js").read_text(
        encoding="utf-8"
    )

    for source in (context_source, panel_source):
        assert 'dividend.yield == null ? "Not reported" : fmtPct(dividend.yield)' in source

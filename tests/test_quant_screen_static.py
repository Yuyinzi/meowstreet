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


def test_ticker_context_auto_interprets_quant_result():
    source = (ROOT / "static" / "ticker-context.js").read_text(encoding="utf-8")

    assert "openWithContext" in source
    assert "量化体检结果" in source

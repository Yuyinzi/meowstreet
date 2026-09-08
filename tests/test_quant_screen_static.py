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


_CATALYST_REVIEW_CSS = "/static/agents/catalyst-research/catalyst-research.css"
_CATALYST_REVIEW_JS = "/static/agents/catalyst-research/catalyst-research.js"


def _ticker_view_sources():
    return [
        (ROOT / "static" / name).read_text(encoding="utf-8")
        for name in ("ticker-context.js", "quant-screen-ticker-panel.js")
    ]


def _catalyst_research_js():
    return (
        ROOT / "static" / "agents" / "catalyst-research" / "catalyst-research.js"
    ).read_text(encoding="utf-8")


def test_ticker_pages_mount_shared_catalyst_research_assets():
    for page in ("ticker-context.html", "quant-screen.html"):
        html = (ROOT / "static" / page).read_text(encoding="utf-8")
        assert _CATALYST_REVIEW_CSS in html
        assert _CATALYST_REVIEW_JS in html


def test_catalyst_research_renderer_contract():
    source = _catalyst_research_js()

    assert "window.CatalystResearch" in source
    assert "load: load" in source
    assert "render: render" in source
    assert "/catalyst-research" in source
    assert "/catalyst-research/events" not in source
    assert "not_researched" in source
    assert "Press Releases" in source
    assert "Events &amp; Presentations" in source
    assert "partial" in source
    assert "unsupported" in source
    assert "ambiguous" in source
    assert "fallback" in source
    assert "truncation_reason" in source
    assert "escapeHtml" in source
    lowered = source.lower()
    for forbidden in ("tumbleweed", "buy", "sell", "score", "grade"):
        assert forbidden not in lowered


def test_catalyst_research_renderer_supports_v1_1_observed_channels():
    source = _catalyst_research_js()

    assert "channel.coverage_status || channel.status" in source
    assert "channel.observed_total == null ? channel.total : channel.observed_total" in source
    assert "channel.observed_earnings == null ? channel.earnings : channel.observed_earnings" in source
    assert "channel.observed_non_earnings == null ? channel.non_earnings : channel.observed_non_earnings" in source
    assert "Observed communications" in source
    assert "coverage_warning" in source
    assert "payload.channels || payload.statistics" in source
    assert "observed_partial" in source


def test_ticker_pages_bump_shared_catalyst_research_asset_version():
    for page in ("ticker-context.html", "quant-screen.html"):
        html = (ROOT / "static" / page).read_text(encoding="utf-8")
        assert _CATALYST_REVIEW_JS + "?v=2" in html


def test_catalyst_research_styles_are_scoped_to_agent_selectors():
    css = (
        ROOT / "static" / "agents" / "catalyst-research" / "catalyst-research.css"
    ).read_text(encoding="utf-8")

    assert css.strip()
    for line in css.splitlines():
        stripped = line.strip()
        if stripped.endswith("{") and not stripped.startswith("@"):
            assert stripped.startswith(".catalyst-research"), stripped


def test_ir_section_is_separate_from_8k_catalyst_section():
    for source in _ticker_view_sources():
        assert "Catalyst activity (8-K filings)" in source
        assert "IR communication history" in source
        assert "CatalystResearch.load" in source


def test_ticker_views_guard_catalyst_research_responses_by_symbol():
    context_source, panel_source = _ticker_view_sources()

    assert "latestQuantPayload.symbol !== symbol" in context_source
    assert "activeSymbol !== symbol" in panel_source


def test_assistant_seed_describes_ir_history_as_frequency_evidence():
    for source in _ticker_view_sources():
        assert "historical communication frequency" in source

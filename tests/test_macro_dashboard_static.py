from pathlib import Path
import json
import subprocess
import textwrap


ROOT = Path(__file__).resolve().parents[1]
STATIC_JS = ROOT / "static" / "macro-dashboard.js"
STATIC_CSS = ROOT / "static" / "macro-dashboard.css"


def test_macro_dashboard_html_links_assets_and_app_root():
    html = (ROOT / "static" / "macro-dashboard.html").read_text()

    assert 'id="macroDashboardApp"' in html
    assert 'href="/macro-dashboard.css"' in html
    assert 'src="/macro-dashboard.js"' in html


def test_macro_dashboard_html_embeds_us_rates_credit_section():
    html = (ROOT / "static" / "macro-dashboard.html").read_text()

    assert 'id="usRatesLiquidity"' in html
    assert "US Rates & Credit" in html
    assert "US Rates / Liquidity" not in html
    assert "Import-backed" in html


def test_macro_dashboard_html_embeds_growth_cycle_section():
    html = (ROOT / "static" / "macro-dashboard.html").read_text()

    assert 'id="growthCycle"' in html
    assert "Growth Cycle" in html
    assert "M2 Money Supply" not in html


def test_macro_dashboard_js_fetches_us_rates_liquidity_api():
    js = (ROOT / "static" / "macro-dashboard.js").read_text()

    assert 'fetch("/api/macro-dashboard/us-rates-liquidity")' in js
    assert "renderUsRatesLiquidity" in js
    assert "state.usRatesLiquidity" in js
    assert "As of ${escapeHtml(fmtDate(card.date))}" not in js
    assert "card.date" not in js
    assert "card.context" not in js
    assert "CPI Real Rate" in js
    assert "payload.derived?.vix" in js
    assert "payload.derived?.sp500_pe" not in js
    assert "S&P PE" not in js


def test_macro_dashboard_html_keeps_rates_credit_mount_without_mock_values():
    html = (ROOT / "static" / "macro-dashboard.html").read_text()

    assert 'id="usRatesLiquidity"' in html
    assert "US Rates & Credit" in html
    assert "0.93%" not in html
    assert "-1.03%" not in html
    assert "10Y - 2Y Spread" not in html


def test_macro_dashboard_js_fetches_overview_and_lazy_loads_market_detail():
    js = (ROOT / "static" / "macro-dashboard.js").read_text()

    assert 'fetch("/api/macro-dashboard/market-phase")' in js
    assert (
        "fetch(`/api/macro-dashboard/market-phase/${encodeURIComponent(benchmarkId)}`)"
        in js
    )
    assert "marketDetailsById" in js
    assert "visibleMarketPhaseMarkets" in js
    assert 'String(market.region ?? "").toUpperCase() === "US"' in js
    assert "loadMarketDetail" in js
    assert "renderOverview" in js
    assert "renderMarketChart" in js
    assert "chartSegments" in js
    assert "renderChartPolylines" in js
    assert "fullSeries" in js
    assert "renderXAxisTicks" in js
    assert "tick.date" in js
    assert "bear_market_level" in js
    assert "bull_market_index" in js
    assert "bear_market_index" in js
    assert "CHART_WIDTH" in js
    assert "const CHART_HEIGHT = 400;" in js
    assert "const MARGIN_TOP = 18;" in js
    assert "const MARGIN_BOTTOM = 84;" in js
    assert "const MARKET_X_LABEL_Y = 32;" in js
    assert "const RELATIONSHIP_X_LABEL_Y = 36;" in js
    assert "const PLOT_BOTTOM = CHART_HEIGHT - MARGIN_BOTTOM;" in js
    assert "function yTickLabelY(" in js
    assert "function visibleYAxisTicks(" in js
    assert "PLOT_WIDTH" in js
    assert "PLOT_HEIGHT" in js
    assert "function xAt(" in js
    assert "function yAt(" in js
    assert "function niceTicks(" in js
    assert "function yAxisTicks(" in js
    assert "function renderYAxisAndGrid(" in js
    assert "function relationshipYAxisTicks(" in js
    assert "function relationshipXAxisTicks(" in js
    assert "function renderRelationshipYAxisAndGrid(" in js
    assert "function renderRelationshipLineChart(" in js
    assert "function attachRelationshipChartTooltip(" in js
    assert "function fmtMonthYear(" in js
    assert "chart-axis" in js
    assert "chart-grid" in js
    assert "chart-y-tick" in js
    assert "function renderChartDots(" not in js
    assert "renderChartDots(" not in js
    assert "function attachChartTooltip(" in js
    assert "chart-wrap" in js
    assert "chart-dot" not in js
    assert "chart-tooltip" in js
    assert "state.selectedBenchmarkId === button.dataset.benchmarkId" in js
    assert "closeDetailPanel()" in js
    assert "detail-panel-head" in js


def test_macro_dashboard_js_has_mock_gdp_relationship_panel():
    js = (ROOT / "static" / "macro-dashboard.js").read_text()

    assert 'fetch("/api/macro-dashboard/gdp-relationships")' in js
    assert (
        "fetch(`/api/macro-dashboard/gdp-relationships/${encodeURIComponent(relationshipId)}`)"
        in js
    )
    assert "gdpRelationshipDetailsById" in js
    assert "loadGdpRelationshipDetail" in js
    assert "MOCK_GDP_RELATIONSHIPS" not in js
    assert "Portfolio bias requires GDP forecast" not in js
    assert "Method Video 03 workflow data" not in js
    assert "GDP / Market Relationship" in js
    assert "renderGdpRelationshipOverview" in js
    assert "renderGdpDetailInPanel" in js
    assert (
        "state.selectedRelationshipId = state.gdpRelationships[0]?.relationship_id || null"
        not in js
    )
    assert "|| state.gdpRelationships[0]" not in js
    assert "state.selectedRelationshipId === button.dataset.relationshipId" in js

    assert "rolling_index_gdp_correlation" not in js
    assert "function fmtCorrelationPercent(" in js
    assert "fmtCorrelationPercent(card.latest?.rolling_index_gdp_correlation)" not in js
    assert "fmtCorrelationPercent(card.latest?.average_10y_correlation)" in js
    assert "fmtCorrelationPercent(latest.rolling_index_gdp_correlation)" not in js
    assert "fmtCorrelationPercent(latest.average_10y_correlation)" in js
    assert "valueFormatter: fmtCorrelationPercent" in js
    assert "same_direction_pct" in js
    assert "method_explainable_pct" in js
    assert "macro_relationship_confidence" in js
    assert "relationship_signal_usability" in js
    assert "portfolio_bias_status" in js
    assert "quadnomial_current_plain_label || latest.quadnomial_current_case" in js
    assert "quadnomial_current_label || card.latest?.quadnomial_current_case" not in js
    assert "gdp-card-topline" in js
    assert "gdp-card-confidence" in js
    assert "gdp-card-summary" in js
    assert "gdp-card-metrics" not in js
    assert "gdp-card-row" not in js
    assert "signalUsabilityMeta" in js
    assert "portfolioBiasMeta" in js
    assert "signal-status" in js
    assert "signal-usable" in js
    assert "signal-caution" in js
    assert "signal-weak" in js
    assert (
        'return { label: "requires GDP forecast", className: "signal-caution" };' in js
    )
    assert "relationship-case" not in js
    assert "relationship-bias" not in js
    assert 'class="gdp-card${selected}"' in js
    assert "Index YoY vs GDP YoY" in js
    assert "<span>Rolling Correlation</span>" not in js
    assert "Rolling correlation" in js
    assert "Average 10Y Correlation" in js
    assert "requires GDP forecast" in js
    assert "requires GDP forcast" not in js
    assert (
        "Usability is strong when the primary-lag average 10Y correlation is at least 40%"
        in js
    )
    assert (
        "The confidence badge uses the same evidence: high when both strong thresholds are met"
        in js
    )
    assert "If corr >= 0.4" not in js
    assert "Rolling 10Y correlations by lag" in js
    assert "lag_correlation_series" in js
    assert "Object.keys(payload.lag_correlation_labels || {})" in js
    assert "relationship-chart-wide" in js
    assert "Y-axis: value" not in js
    assert "X-axis: period" not in js
    assert "Source:" not in js
    assert "M lag ${escapeHtml(fmtDate(latest.primary_lag_date))}" in js
    assert (
        "Quadnomial ${escapeHtml(latest.quadnomial_period_label || fmtDate(latest.quadnomial_date))}"
        in js
    )
    assert "Derived from correlation and same-direction rate" not in js
    assert "Requires future GDP forecast input" not in js
    assert "relationship-legend" in js
    assert "chart-axis" in js
    assert "relationship-axis-labels" not in js
    assert "Index YoY" in js
    assert "GDP YoY" in js
    assert "series[0].label || series[0].date" in js
    assert "Quadnomial distribution" in js
    assert "Method Coverage" in js
    assert "M lag A + B + C" in js
    assert "M lag A + B" in js
    assert "M lag rate" in js
    assert "Quadnomial distribution defines A as index down/GDP down" in js
    assert "Method coverage combines A, B, and C" in js
    assert js.index("${renderQuadBars(payload)}") < js.index(
        "${renderYoyComparison(payload)}"
    )
    assert js.index("relationship-chart-grid-pre-method") < js.index("method-note")
    assert "Signal usability" in js
    assert "Mock data" not in js
    assert "Fake data" not in js
    assert "Mock data based on" not in js
    assert "portfolio_bias_status" in js
    assert "Index YoY vs GDP YoY" in js
    assert "<span>Rolling Correlation</span>" not in js
    assert "Rolling correlation" in js
    assert "Quadnomial distribution" in js
    assert "Signal usability" in js
    assert "signal-neutral" in js
    assert "Mock data" not in js
    assert "Fake data" not in js
    assert "Mock data based on" not in js
    assert "portfolio_bias_status" in js


def test_macro_dashboard_js_has_mock_lag_comparison_metrics():
    js = (ROOT / "static" / "macro-dashboard.js").read_text()

    assert "lag_correlations" in js
    assert "renderLagComparison" in js
    assert "Lag comparison" in js
    assert "method_primary" in js


def test_macro_dashboard_css_has_overview_and_chart_classes():
    css = (ROOT / "static" / "macro-dashboard.css").read_text()

    assert ".market-grid" in css
    assert ".market-card" in css
    assert ".market-detail" in css
    assert ".market-chart" in css
    assert ".chart-axis" in css
    assert ".chart-grid" in css
    assert ".chart-y-tick" in css
    assert ".chart-wrap" in css
    assert ".chart-dot" not in css
    assert ".chart-tooltip" in css


def test_macro_dashboard_css_has_mock_gdp_relationship_styles():
    css = (ROOT / "static" / "macro-dashboard.css").read_text()

    assert ".gdp-relationship" in css
    assert ".gdp-card" in css
    assert ".gdp-card.selected" in css
    assert "grid-template-columns: repeat(auto-fit, minmax(220px, 280px));" in css
    assert ".gdp-card-topline" in css
    assert ".gdp-card-confidence" in css
    assert ".gdp-card-summary" in css
    assert ".gdp-card-summary strong.signal-usable" in css
    assert ".gdp-card-summary strong.signal-caution" in css
    assert ".gdp-card-summary strong.signal-weak" in css
    assert ".gdp-card-metrics" not in css
    assert ".gdp-card-row" not in css
    assert ".relationship-case" not in css
    assert ".relationship-bias" not in css
    assert ".gdp-detail" in css
    assert ".relationship-chart" in css
    assert ".relationship-chart-grid-pre-method" in css
    assert ".relationship-legend" in css
    assert ".relationship-chart-wide" in css
    assert ".chart-axis" in css
    assert ".chart-grid" in css
    assert ".chart-y-tick" in css
    assert ".signal-status" in css
    assert ".signal-status::before" not in css
    assert "background: transparent;" in css
    assert "text-transform: uppercase;" in css
    assert ".metric-strip strong.signal-usable" in css
    assert ".metric-strip strong.signal-caution" in css
    assert ".metric-strip strong.signal-weak" in css
    assert ".signal-usable" in css
    assert ".signal-caution" in css
    assert ".signal-weak" in css
    assert ".signal-neutral" in css
    assert ".relationship-line-4" in css
    assert ".relationship-line-key-4" in css
    assert ".metric-context" in css
    assert "grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));" in css
    assert ".metric-source" not in css
    assert ".quad-bars" in css
    assert ".confidence-high" in css
    assert ".confidence-medium" in css
    assert ".confidence-low" in css


def test_macro_dashboard_css_has_lag_comparison_styles():
    css = (ROOT / "static" / "macro-dashboard.css").read_text()

    assert ".lag-table" in css
    assert ".lag-row" in css
    assert ".lag-row-primary" in css
    assert ".lag-primary-pill" in css


def test_macro_dashboard_chart_helpers_are_exercised_with_node():
    script = textwrap.dedent(
        """
        const fs = require("fs");
        const vm = require("vm");

        const elements = {
          dashboardStatus: {},
          marketGrid: { innerHTML: "", querySelectorAll: () => [] },
          marketDetail: { innerHTML: "" },
        };

        global.window = { __MEOWSTREET_TEST__: true };
        global.document = {
          getElementById: (id) => elements[id],
        };
        global.fetch = async () => ({
          ok: true,
          status: 200,
          json: async () => ({ markets: [] }),
        });

        vm.runInThisContext(fs.readFileSync("static/macro-dashboard.js", "utf8"));

        const hooks = window.__macroDashboardTestHooks;
        const series = [
          { date: "2020-01-01", close: 100, bear_market_level: 80 },
          { date: "2020-01-02", close: 90, bear_market_level: 80 },
          { date: "2020-01-03", close: 79, bear_market_level: 80 },
        ];
        const relationshipSeries = [
          { date: "2020-01-01", index: 4.5, gdp: -1.5, value: 0.17, lag_0: 0.17, lag_3: 0.16 },
          { date: "2020-04-01", index: 5.0, gdp: null, value: 0.11, lag_0: 0.11, lag_3: null },
          { date: "2020-07-01", index: 5.4, gdp: 2.3, value: -0.05, lag_0: -0.05, lag_3: -0.02 },
        ];
        const longSeries = Array.from({ length: 60 }, (_, index) => ({
          date: `2020-${String(Math.floor(index / 28) + 1).padStart(2, "0")}-${String((index % 28) + 1).padStart(2, "0")}`,
          close: 100 + index,
          bear_market_level: 80 + index,
        }));

        console.log(JSON.stringify({
          xAxisTickCount: hooks.X_AXIS_TICK_COUNT,
          yAxisTickCount: hooks.Y_AXIS_TICK_COUNT,
          formattedDate: hooks.fmtMonthYear("2021-10-11"),
          firstX: hooks.xAt(0, 3),
          lastX: hooks.xAt(2, 3),
          ticks: hooks.xAxisTicks(series).map((tick) => tick.date),
          longTickCount: hooks.xAxisTicks(longSeries).length,
          xAxisMarkup: hooks.renderXAxisTicks(series),
          yTicks: hooks.yAxisTicks(series, 9),
          relationshipYTicks: hooks.relationshipYAxisTicks(relationshipSeries, ["index", "gdp"], 7),
          relationshipXTicks: hooks.relationshipXAxisTicks(relationshipSeries),
          relationshipMarkup: hooks.renderRelationshipLineChart("GDP / Market Relationship", relationshipSeries, ["index", "gdp"], { index: "Index YoY", gdp: "GDP YoY" }, { wide: true, valueFormatter: (value) => `${value}%` }),
          lagMarkup: hooks.renderRelationshipLineChart("Rolling 10Y correlations by lag", relationshipSeries, ["lag_0", "lag_3"], { lag_0: "No lag", lag_3: "3M lag" }, { wide: true }),
        }));
        """
    )

    result = subprocess.run(
        ["node", "-e", script],
        cwd=ROOT,
        capture_output=True,
        check=True,
        text=True,
    )
    payload = json.loads(result.stdout)

    assert payload["formattedDate"] == "Oct 2021"
    assert payload["xAxisTickCount"] == 12
    assert payload["yAxisTickCount"] == 9
    assert payload["firstX"] == 50
    assert payload["lastX"] == 910
    assert payload["ticks"] == ["2020-01-01", "2020-01-02", "2020-01-03"]
    assert payload["longTickCount"] >= 9
    assert 'class="chart-x-label chart-x-label-last"' not in payload["xAxisMarkup"]
    assert 'text-anchor="middle"' in payload["xAxisMarkup"]
    assert 'x="-18"' not in payload["xAxisMarkup"]
    assert "translate(50.00 316)" in payload["xAxisMarkup"]
    assert payload["yTicks"][0] <= 79
    assert payload["yTicks"][-1] >= 100
    assert payload["relationshipYTicks"][0] <= -1.5
    assert payload["relationshipYTicks"][-1] >= 5.4
    assert [tick["date"] for tick in payload["relationshipXTicks"]] == [
        "2020-01-01",
        "2020-04-01",
        "2020-07-01",
    ]
    assert "relationship-chart-wide" in payload["relationshipMarkup"]
    assert "chart-wrap" in payload["relationshipMarkup"]
    assert "chart-tooltip" in payload["relationshipMarkup"]
    assert 'y1="322.00"' not in payload["relationshipMarkup"]
    assert (
        payload["relationshipMarkup"].count(
            'class="relationship-line relationship-line-0"'
        )
        == 1
    )
    assert (
        payload["relationshipMarkup"].count(
            'class="relationship-line relationship-line-1"'
        )
        == 2
    )
    assert "Index YoY" in payload["relationshipMarkup"]
    assert "GDP YoY" in payload["relationshipMarkup"]
    assert (
        payload["lagMarkup"].count('class="relationship-line relationship-line-0"') == 1
    )
    assert (
        payload["lagMarkup"].count('class="relationship-line relationship-line-1"') == 2
    )
    assert 'y="36"' in payload["relationshipMarkup"]


def test_macro_dashboard_js_removes_dot_layer_and_keeps_mouse_tooltip():
    js = (ROOT / "static" / "macro-dashboard.js").read_text()

    assert 'event.key === "Escape"' in js
    assert 'svg.addEventListener("mousemove"' in js
    assert 'svg.addEventListener("mouseleave", hide)' in js
    assert 'event.target.closest(".chart-dot")' not in js
    assert "const markets = visibleMarketPhaseMarkets(state.markets);" in js
    assert (
        "const currentMarket = markets.find((market) => market.benchmark_id === state.selectedBenchmarkId)"
        in js
    )
    assert "state.markets = visibleMarketPhaseMarkets(payload.markets || []);" in js
    assert "market.benchmark_id === currentMarket?.benchmark_id" in js


def test_macro_dashboard_chart_css_stays_before_mobile_media_query():
    css = (ROOT / "static" / "macro-dashboard.css").read_text()

    assert css.index(".chart-axis") < css.index("@media (max-width: 820px)")


def test_macro_dashboard_js_explains_market_phase_method():
    js = (ROOT / "static" / "macro-dashboard.js").read_text()

    assert "function renderMarketPhaseMethod(" in js
    assert "Rolling High = highest high seen so far in the series." in js
    assert "Bear/Bull Level = Rolling High x 80%." in js
    assert "Drawdown = Close / Rolling High - 1." in js
    assert "Bull market: Close is above the Bear/Bull Level." in js
    assert "Bear market: Close is at or below the Bear/Bull Level." in js
    assert "Green line shows bull-market close segments" in js
    assert "${renderMarketPhaseMethod()}" in js


def test_macro_dashboard_css_has_market_phase_method_note_styles():
    css = (ROOT / "static" / "macro-dashboard.css").read_text()

    assert ".method-note" in css
    assert ".method-formula-list" in css
    assert ".method-chart-key" in css


def test_macro_dashboard_js_has_per_market_refresh_action():
    js = (ROOT / "static" / "macro-dashboard.js").read_text()

    assert 'class="market-refresh"' in js
    assert 'aria-label="Refresh ${escapeHtml(market.title)}"' in js
    assert 'data-refresh-benchmark-id="${escapeHtml(market.benchmark_id)}"' in js
    assert "\u21bb" in js
    assert "event.stopPropagation()" in js
    assert "refreshMarket(button.dataset.refreshBenchmarkId, button)" in js
    assert "function refreshMarket(" in js
    assert "state.marketDetailsById[benchmarkId]" in js
    assert "delete state.marketDetailsById[benchmarkId]" in js
    assert "renderOverview();" in js
    assert "renderDetailPanel();" in js
    assert "rows_upserted" in js
    assert "latest_date" in js


def test_macro_dashboard_css_has_refresh_button_styles():
    css = (ROOT / "static" / "macro-dashboard.css").read_text()

    assert ".market-refresh" in css
    assert ".market-refresh:disabled" in css


def test_macro_dashboard_js_lazy_loads_us_rates_detail_charts():
    js = (ROOT / "static" / "macro-dashboard.js").read_text()

    assert "selectedRatesDetailId" in js
    assert "usRatesDetailsById" in js
    assert "loadUsRatesLiquidityDetail" in js
    assert "renderRatesDetailInPanel" in js
    assert "fetch(url.toString())" in js
    assert "selectedNominalCurrentDate" in js
    assert "selectedNominalComparisonDate" in js
    assert "selectedRealCurrentDate" in js
    assert "selectedRealComparisonDate" in js
    assert "nominalCurrentDate" in js
    assert "nominalComparisonDate" in js
    assert "realCurrentDate" in js
    assert "realComparisonDate" in js
    assert 'class="rates-signal-card${selected}"' in js
    assert "data-rates-detail-id" in js
    assert "state.selectedRatesDetailId === button.dataset.ratesDetailId" in js
    assert '$("detailPanel")' in js
    assert "renderRatesDetailChart" in js
    assert "attachRelationshipChartTooltip" in js


def test_macro_dashboard_js_renders_rates_detail_with_dashboard_chart_pattern():
    js = (ROOT / "static" / "macro-dashboard.js").read_text()

    assert "renderRatesTimeSeriesChart" in js
    assert "renderRatesCurveComparisonChart" in js
    assert "renderRatesDetailPayload" in js
    assert "bindRatesCurveControls" in js
    assert "data-curve-date-kind" in js
    assert "data-curve-date-role" in js
    assert "rates-curve-date-controls" in js
    assert "categoricalXAxis: true" in js
    assert "renderRelationshipXAxisTicks(series, options)" in js
    assert "options.categoricalXAxis" in js
    assert "relationship-chart" in js
    assert "relationship-legend" in js
    assert "chart-axis" in js
    assert "chart-grid" in js
    assert "chart-y-tick" in js
    assert "chart-tick" in js
    assert "chart-tooltip" in js
    assert (
        "payload.charts.map((chart, index) => renderRatesDetailChart(chart, index)).join"
        in js
    )
    assert "multi_series" in js
    assert "renderRatesMultiSeriesChart" in js
    assert "secondary_series" in js


def test_macro_dashboard_css_has_rates_detail_clickable_styles():
    css = (ROOT / "static" / "macro-dashboard.css").read_text()

    assert ".rates-signal-card.selected" in css
    assert "min-height: 88px;" in css
    assert ".rates-panel-button" in css
    assert ".rates-panel-button.selected" in css
    assert ".rates-detail" in css
    assert ".rates-curve-date-controls" in css


def test_macro_dashboard_js_has_simplified_credit_conditions_labels():
    js = (ROOT / "static" / "macro-dashboard.js").read_text()

    assert "Credit Conditions" in js
    assert "BBB Credit Spread" in js
    assert "CCC Credit Spread" in js
    assert "CCC vs BBB Quality Spread" in js
    assert "BBB - 10Y" in js
    assert "CCC - 10Y" in js
    assert "CCC - BBB" in js

    assert "AAA Credit Spread" not in js
    assert "BBB vs AAA Quality Spread" not in js
    assert "CCC vs AAA Quality Spread" not in js
    assert "Rating Detail" not in js
    assert "rating-detail-tabs" not in js


def test_macro_dashboard_js_has_credit_zh_translations():
    js = (ROOT / "static" / "macro-dashboard.js").read_text()

    assert "BBB信用利差" in js
    assert "CCC信用利差" in js
    assert "CCC与BBB质量利差" in js
    assert "信用环境" in js
    assert "BBB - 10年" in js
    assert "CCC - 10年" in js
    assert "CCC - BBB" in js
    assert "信用环境诊断" in js
    assert "历史分位" in js
    assert "1个月趋势" in js
    assert "3个月趋势" in js
    assert "加速" in js


def test_macro_dashboard_js_renders_credit_diagnostics():
    js = (ROOT / "static" / "macro-dashboard.js").read_text()

    assert "credit_conditions_diagnostics" in js
    assert "credit_diagnostics" in js
    assert "renderCreditDiagnosticsChart" in js
    assert "creditDiagnosticInterpretation" in js
    assert "credit-interpretation-strip" in js
    assert "Full-History Percentile" in js
    assert "1M Trend" in js
    assert "3M Trend" in js
    assert "Acceleration" in js
    assert "Weak Credit Warning" in js
    assert "Overall credit risk is low" in js
    assert "Risk Rising" in js
    assert "Crisis Stress" in js
    assert "renderCreditCoverageNote" in js
    assert "credit-data-gap-note" in js
    assert "P05 workbook history is merged with latest FRED ICE/BofA observations" in js
    assert "renderCreditAiInterpretation" in js
    assert "credit-ai-interpretation" in js
    assert "CaiCai" in js
    assert "财财" in js


def test_macro_dashboard_css_contains_credit_gap_note_styles():
    css = (ROOT / "static" / "macro-dashboard.css").read_text()

    assert ".credit-data-gap-note" in css


def test_macro_dashboard_css_contains_credit_ai_interpretation_styles():
    css = (ROOT / "static" / "macro-dashboard.css").read_text()

    assert ".credit-ai-interpretation" in css


def test_macro_dashboard_css_contains_credit_interpretation_styles():
    css = (ROOT / "static" / "macro-dashboard.css").read_text()

    assert ".credit-interpretation-strip" in css
    assert ".credit-interpretation-healthy" in css
    assert ".credit-interpretation-weak-credit-warning" in css
    assert ".credit-interpretation-risk-rising" in css
    assert ".credit-interpretation-crisis-stress" in css


def test_macro_dashboard_js_fetches_and_renders_growth_cycle_m2_card():
    js = (ROOT / "static" / "macro-dashboard.js").read_text()

    assert 'fetch("/api/macro-dashboard/growth-cycle")' in js
    assert "state.growthCycle" in js
    assert "renderGrowthCycle" in js
    assert "renderM2MoneySupplyCard" in js
    assert "YoY Growth" in js
    assert "3M Change" in js
    assert "MoM Shock" in js
    assert "fmtDirectionalPct" in js
    assert "fmtDirectionalPercentRank" in js
    assert "YoY growth vs same month last year" in js
    assert "percentile of history" in js
    assert "同比增速：较去年同月" in js
    assert "历史第" in js
    assert "latest level vs 3 months ago" in js
    assert "最新水平较3个月前" in js
    assert "最新月环比增长" in js
    assert "M2 Level" in js
    assert "M2总量" in js
    assert "M2 Money Supply" in js
    assert "P06" not in js


def test_macro_dashboard_js_wires_growth_cycle_detail_panel():
    js = (ROOT / "static" / "macro-dashboard.js").read_text()

    assert "selectedGrowthCycleDetailId" in js
    assert "growthCycleDetailsById" in js
    assert "loadGrowthCycleDetail" in js
    assert "renderGrowthCycleDetailInPanel" in js
    assert "data-growth-cycle-detail-id" in js
    assert (
        "fetch(`/api/macro-dashboard/growth-cycle/${encodeURIComponent(detailId)}`)"
        in js
    )
    assert "renderRatesDetailChart(chart, index)" in js
    assert "attachRatesChartTooltips(body, payload.charts)" in js


def test_macro_dashboard_css_has_clickable_m2_card_styles():
    css = (ROOT / "static" / "macro-dashboard.css").read_text()

    assert ".m2-card-button" in css
    assert ".m2-card.selected" in css


def test_macro_dashboard_css_has_growth_cycle_card_styles():
    css = (ROOT / "static" / "macro-dashboard.css").read_text()

    assert ".growth-cycle" in css
    assert ".m2-card" in css
    assert ".m2-metric-band" in css
    assert ".m2-level-row" in css


def test_macro_dashboard_js_renders_m2_ai_interpretation():
    js = (ROOT / "static" / "macro-dashboard.js").read_text()

    assert "renderMacroAiInterpretation" in js
    assert "m2_ai_interpretation" in js
    assert "CaiCai" in js
    assert "财财解读" in js
    assert "macro-ai-interpretation" in js


def test_macro_dashboard_css_contains_macro_ai_interpretation_styles():
    css = (ROOT / "static" / "macro-dashboard.css").read_text()

    assert ".macro-ai-interpretation" in css


def test_macro_dashboard_js_renders_fed_balance_sheet_card():
    js = (ROOT / "static" / "macro-dashboard.js").read_text()

    assert "renderFedBalanceSheetCard" in js
    assert "Fed Balance Sheet" in js
    assert "美联储资产负债表" in js
    assert "Liquidity Context" in js
    assert "Total Assets" in js
    assert "Total Assets 13W Net Change" in js
    assert "Treasury 13W Net Change" in js
    assert "MBS 13W Net Change" in js
    assert "总资产13周净变化" in js
    assert "美债持仓13周净变化" in js
    assert "MBS持仓13周净变化" in js
    assert "Positive = expansion, negative = runoff" in js
    assert "正值=扩表，负值=缩表" in js
    assert "fmtSignedUsdMillions" in js
    assert "美联储总资产同比" in js
    assert "美联储资产负债表13周构成" in js


def test_macro_dashboard_js_renders_gdp_expectations_placeholder_card():
    js = (ROOT / "static" / "macro-dashboard.js").read_text()

    assert "renderGdpExpectationsCard" in js
    assert "GDP Expectations" in js
    assert "GDP预期" in js
    assert "Pending Inputs" in js
    assert "待输入" in js


def test_macro_dashboard_js_renders_inflation_context_card():
    js = (ROOT / "static" / "macro-dashboard.js").read_text()

    assert "renderInflationContextCard" in js
    assert "Inflation Context" in js
    assert "Core PCE YoY" in js
    assert "Gap vs Fed 2% Target" in js
    assert "通胀环境" in js
    assert "核心PCE同比" in js
    assert "相对美联储2%目标" in js
    assert "Fed 2% Target" in js


def test_macro_dashboard_static_includes_fomc_chart_marker_renderer():
    js = ROOT.joinpath("static/macro-dashboard.js").read_text(encoding="utf-8")

    assert "renderRelationshipEventMarkers" in js
    assert "relationship-event-marker" in js
    assert "policy_tone" in js


def test_macro_dashboard_static_includes_fomc_card_labels():
    js = ROOT.joinpath("static/macro-dashboard.js").read_text(encoding="utf-8")

    assert "FOMC Calendar" in js
    assert "Next Meeting" in js
    assert "Policy Timing" in js


def test_macro_dashboard_static_includes_fomc_tone_card():
    js = ROOT.joinpath("static/macro-dashboard.js").read_text(encoding="utf-8")

    assert "fomc_tone" in js
    assert "renderFomcToneCard" in js
    assert "Next FOMC Meeting" in js
    assert "Latest FOMC Tone" in js
    assert "Action" in js
    assert "Guidance" in js
    assert "Language" in js
    assert "Bias" in js
    assert "Change" in js
    assert "policy_action" in js
    assert "guidance_bias" in js
    assert "language_tone" in js
    assert "overall_bias" in js
    assert "tone_change" in js
    assert "marker_tone" in js
    assert "formatPolicyAction" in js
    assert "formatToneValue" in js
    assert "formatOverallBias" in js
    assert "formatToneChange" in js
    assert "toneBadgeClass" in js
    assert "fomc-tone-badge" in js
    assert "fomc-tone-card" in js
    assert "tone-hawkish" in js
    assert "tone-dovish" in js
    assert "tone-neutral" in js
    assert "No scheduled meeting" in js
    assert "Tone unavailable" in js


def test_macro_dashboard_renders_fomc_minutes_policy_read_rows():
    js = ROOT.joinpath("static/macro-dashboard.js").read_text(encoding="utf-8")

    assert "Minutes Confirmation" in js
    assert "Risk Focus" in js
    assert "Policy Conviction" in js
    assert "minutes_confirmation" in js
    assert "policy_conviction" in js


def test_macro_dashboard_range_filter_hooks_filter_series_and_events():
    script = textwrap.dedent(
        """
        const fs = require("fs");
        const vm = require("vm");

        const elements = {
          dashboardStatus: {},
          marketGrid: { innerHTML: "", querySelectorAll: () => [] },
          marketDetail: { innerHTML: "" },
        };

        global.window = { __MEOWSTREET_TEST__: true };
        global.document = {
          getElementById: (id) => elements[id],
        };
        global.fetch = async () => ({
          ok: true,
          status: 200,
          json: async () => ({ markets: [] }),
        });

        vm.runInThisContext(fs.readFileSync("static/macro-dashboard.js", "utf8"));
        const hooks = window.__macroDashboardTestHooks;

        const series = [
          { date: "2015-01-01", value: 1 },
          { date: "2019-12-01", value: 2 },
          { date: "2020-01-01", value: 3 },
          { date: "2024-12-01", value: 4 },
          { date: "2025-01-01", value: 5 },
        ];
        const events = [
          { date: "2019-12-01", event_date: "2019-12-11", label: "FOMC" },
          { date: "2020-01-01", event_date: "2020-01-29", label: "FOMC" },
          { date: "2025-01-01", event_date: "2025-01-29", label: "FOMC" },
        ];
        const chart = { series, events };

        console.log(JSON.stringify({
          tenYearSeries: hooks.filterChartForRange(chart, "10y").series.map((point) => point.date),
          fiveYearSeries: hooks.filterChartForRange(chart, "5y").series.map((point) => point.date),
          fiveYearEvents: hooks.filterChartForRange(chart, "5y").events.map((event) => event.date),
          maxSeries: hooks.filterChartForRange(chart, "max").series.map((point) => point.date),
          maxEvents: hooks.filterChartForRange(chart, "max").events.map((event) => event.date),
        }));
        """
    )

    result = subprocess.run(
        ["node", "-e", script],
        cwd=ROOT,
        capture_output=True,
        check=True,
        text=True,
    )
    payload = json.loads(result.stdout)

    assert payload["tenYearSeries"] == [
        "2015-01-01",
        "2019-12-01",
        "2020-01-01",
        "2024-12-01",
        "2025-01-01",
    ]
    assert payload["fiveYearSeries"] == ["2020-01-01", "2024-12-01", "2025-01-01"]
    assert payload["fiveYearEvents"] == ["2020-01-01", "2025-01-01"]
    assert payload["maxSeries"] == [
        "2015-01-01",
        "2019-12-01",
        "2020-01-01",
        "2024-12-01",
        "2025-01-01",
    ]
    assert payload["maxEvents"] == []


def test_macro_dashboard_css_has_fomc_tone_card_styles():
    css = ROOT.joinpath("static/macro-dashboard.css").read_text(encoding="utf-8")

    assert ".fomc-tone-card .m2-detail-rows" in css
    assert ".fomc-tone-badge" in css
    assert ".fomc-tone-badge.tone-hawkish" in css
    assert ".fomc-tone-badge.tone-dovish" in css
    assert ".fomc-tone-badge.tone-neutral" in css


def test_macro_dashboard_static_includes_m2_range_control():
    js = ROOT.joinpath("static/macro-dashboard.js").read_text(encoding="utf-8")
    css = ROOT.joinpath("static/macro-dashboard.css").read_text(encoding="utf-8")

    assert "renderGrowthCycleRangeControl" in js
    assert "data-growth-cycle-chart-range" in js
    assert "selectedGrowthCycleChartRange" in js
    assert "5Y" in js
    assert "10Y" in js
    assert "20Y" in js
    assert "Max" in js
    assert ".chart-range-control" in css
    assert "chart-range-control-sticky" in js
    assert ".chart-range-control-sticky" in css
    assert "rerenderGrowthCycleDetailBodyPreservingScroll" in js
    assert "scrollTop" in js


def test_macro_dashboard_static_includes_fomc_tone_tooltip_fields():
    js = ROOT.joinpath("static/macro-dashboard.js").read_text(encoding="utf-8")

    assert "tone_change" in js
    assert "statement_tone" in js
    assert "confidence" in js


def test_macro_dashboard_relationship_tooltip_uses_pinned_positioning():
    js = ROOT.joinpath("static/macro-dashboard.js").read_text(encoding="utf-8")
    css = ROOT.joinpath("static/macro-dashboard.css").read_text(encoding="utf-8")

    assert "positionRelationshipTooltip" in js
    assert "relationship-tooltip-pinned" in js
    assert "index < series.length / 2" in js
    assert "grid-template-columns: minmax(0, 1fr) auto" in css
    assert ".chart-tooltip-row span" in css
    assert "overflow-wrap: anywhere" in css


def test_macro_dashboard_hides_event_marker_labels_when_requested():
    script = textwrap.dedent(
        """
        const fs = require("fs");
        const vm = require("vm");

        const elements = {
          dashboardStatus: {},
          marketGrid: { innerHTML: "", querySelectorAll: () => [] },
          marketDetail: { innerHTML: "" },
        };

        global.window = { __MEOWSTREET_TEST__: true };
        global.document = {
          getElementById: (id) => elements[id],
        };
        global.fetch = async () => ({
          ok: true,
          status: 200,
          json: async () => ({ markets: [] }),
        });

        vm.runInThisContext(fs.readFileSync("static/macro-dashboard.js", "utf8"));
        const hooks = window.__macroDashboardTestHooks;
        const markup = hooks.renderRelationshipLineChart(
          "Test",
          [{ date: "2025-01-01", value: 1 }],
          ["value"],
          { value: "Value" },
          {
            events: [{ date: "2025-01-01", label: "FOMC", policy_tone: "unknown" }],
            hideEventLabels: true,
          },
        );

        console.log(JSON.stringify({
          hasMarker: markup.includes("relationship-event-marker"),
          hasLabel: markup.includes(">FOMC</text>"),
        }));
        """
    )

    result = subprocess.run(
        ["node", "-e", script],
        cwd=ROOT,
        capture_output=True,
        check=True,
        text=True,
    )
    payload = json.loads(result.stdout)

    assert payload["hasMarker"] is True
    assert payload["hasLabel"] is False


def test_macro_dashboard_renders_fomc_events_as_tone_bars_to_highest_line():
    script = textwrap.dedent(
        """
        const fs = require("fs");
        const vm = require("vm");

        const elements = {
          dashboardStatus: {},
          marketGrid: { innerHTML: "", querySelectorAll: () => [] },
          marketDetail: { innerHTML: "" },
        };

        global.window = { __MEOWSTREET_TEST__: true };
        global.document = {
          getElementById: (id) => elements[id],
        };
        global.fetch = async () => ({
          ok: true,
          status: 200,
          json: async () => ({ markets: [] }),
        });

        vm.runInThisContext(fs.readFileSync("static/macro-dashboard.js", "utf8"));
        const hooks = window.__macroDashboardTestHooks;
        const markup = hooks.renderRelationshipLineChart(
          "Test",
          [{ date: "2025-01-01", m2: 4, pce: 6, target: 2 }],
          ["m2", "pce", "target"],
          { m2: "M2", pce: "PCE", target: "Target" },
          {
            yDomain: { min: 0, max: 10 },
            events: [{ date: "2025-01-01", label: "FOMC", policy_tone: "hawkish" }],
          },
        );
        const expectedTop = hooks.yAt(6, { min: 0, max: 10, range: 10, height: hooks.PLOT_BOTTOM - hooks.MARGIN_TOP }).toFixed(2);

        console.log(JSON.stringify({
          hasBar: markup.includes("relationship-event-bar"),
          hasTick: markup.includes("relationship-event-tick"),
          hasHawkishClass: markup.includes("relationship-event-marker-hawkish"),
          hasTopAtHighestLine: markup.includes(`y1="${expectedTop}"`),
          hasFullHeightMarker: markup.includes(`y1="${hooks.MARGIN_TOP}" y2="${hooks.PLOT_BOTTOM}"`),
          hasLabel: markup.includes(">FOMC</text>"),
        }));
        """
    )

    result = subprocess.run(
        ["node", "-e", script],
        cwd=ROOT,
        capture_output=True,
        check=True,
        text=True,
    )
    payload = json.loads(result.stdout)

    assert payload["hasBar"] is True
    assert payload["hasTick"] is False
    assert payload["hasHawkishClass"] is True
    assert payload["hasTopAtHighestLine"] is True
    assert payload["hasFullHeightMarker"] is False
    assert payload["hasLabel"] is False


def test_macro_dashboard_static_includes_expandable_detail_panel_hooks():
    js = ROOT.joinpath("static/macro-dashboard.js").read_text(encoding="utf-8")
    css = ROOT.joinpath("static/macro-dashboard.css").read_text(encoding="utf-8")

    assert "isDetailPanelExpanded" in js
    assert "toggleDetailPanelExpanded" in js
    assert "panel-expanded" in js
    assert "detail-panel-expand" in js
    assert "DETAIL_PANEL_EXPAND_LABEL" in js
    assert "DETAIL_PANEL_COLLAPSE_LABEL" in js
    assert '"Expand detail panel"' in js
    assert '"Collapse detail panel"' in js
    assert ".macro-shell.panel-open.panel-expanded" in css
    assert "minmax(720px" in css
    assert ".detail-panel-expand" in css


def test_macro_dashboard_detail_panel_expand_button_toggles_class():
    script = textwrap.dedent(
        """
        const fs = require("fs");
        const vm = require("vm");

        const classNames = new Set();
        const detailPanel = {
          innerHTML: "",
          querySelector: (selector) => {
            if (selector === ".detail-panel-close") {
              return { addEventListener: () => {} };
            }
            if (selector === ".detail-panel-expand") {
              return {
                addEventListener: (eventName, handler) => {
                  detailPanel.expandHandler = handler;
                },
              };
            }
            if (selector === ".detail-panel-body") {
              return { innerHTML: "" };
            }
            return null;
          },
        };
        const elements = {
          macroDashboardApp: {
            classList: {
              add: (name) => classNames.add(name),
              remove: (name) => classNames.delete(name),
              toggle: (name, enabled) => {
                if (enabled) classNames.add(name);
                else classNames.delete(name);
              },
            },
            insertAdjacentHTML: () => {},
          },
          detailPanel,
          dashboardStatus: {},
          marketGrid: { innerHTML: "", querySelectorAll: () => [] },
          marketDetail: { innerHTML: "" },
        };

        global.window = { __MEOWSTREET_TEST__: true };
        global.document = {
          getElementById: (id) => elements[id],
        };
        global.fetch = async () => ({
          ok: true,
          status: 200,
          json: async () => ({ markets: [] }),
        });

        vm.runInThisContext(fs.readFileSync("static/macro-dashboard.js", "utf8"));
        const hooks = window.__macroDashboardTestHooks;
        hooks.state.selectedGrowthCycleDetailId = "m2_money_supply";
        hooks.renderDetailPanel();
        const before = classNames.has("panel-expanded");
        detailPanel.expandHandler({ stopPropagation: () => {} });
        const after = classNames.has("panel-expanded");

        console.log(JSON.stringify({ before, after }));
        """
    )

    result = subprocess.run(
        ["node", "-e", script],
        cwd=ROOT,
        capture_output=True,
        check=True,
        text=True,
    )
    payload = json.loads(result.stdout)

    assert payload == {"before": False, "after": True}


def test_macro_dashboard_static_includes_fomc_policy_track_renderer():
    js = ROOT.joinpath("static/macro-dashboard.js").read_text(encoding="utf-8")
    css = ROOT.joinpath("static/macro-dashboard.css").read_text(encoding="utf-8")

    assert "renderRelationshipPolicyTrack" in js
    assert "relationship-policy-track" in js
    assert "policyTrackEvents" in js
    assert "policyToneFill" in js
    assert "<circle" in js  # statement markers
    assert "M0 -5 L5 5 L-5 5 Z" in js  # minutes triangle path
    assert "policy-legend-circle" in js
    assert "policy-legend-triangle" in js
    assert "policy-color-swatch" in js
    assert ".relationship-policy-axis" in css
    assert ".policy-legend-circle" in css
    assert ".policy-legend-triangle" in css
    assert ".policy-color-swatch" in css
    assert ".policy-color-hawkish" in css


def test_macro_dashboard_policy_track_replaces_in_plot_event_bars_for_m2_chart():
    script = textwrap.dedent(
        """
        const fs = require("fs");
        const vm = require("vm");
        const code = fs.readFileSync("static/macro-dashboard.js", "utf8");
        const sandbox = {
          window: { __MEOWSTREET_TEST__: true },
          document: {
            addEventListener: () => {},
            getElementById: () => ({
              querySelector: () => null,
              querySelectorAll: () => [],
              addEventListener: () => {},
              insertAdjacentHTML: () => {},
              textContent: "",
              innerHTML: "",
              classList: {
                add: () => {},
                remove: () => {},
                toggle: () => {},
              },
            }),
            querySelectorAll: () => [],
          },
          console,
          fetch: async () => ({ ok: true, json: async () => ({ markets: [] }) }),
        };
        vm.createContext(sandbox);
        vm.runInContext(code, sandbox);
        const hooks = sandbox.window.__macroDashboardTestHooks;
        const series = [
          { date: "2026-05-01", m2_yoy: 4, core_pce_yoy: 3, fed_target: 2 },
          { date: "2026-06-01", m2_yoy: 5, core_pce_yoy: 3, fed_target: 2 },
        ];
        const markup = hooks.renderRelationshipLineChart(
          "M2 YoY Growth vs Inflation Constraint",
          series,
          ["m2_yoy", "core_pce_yoy", "fed_target"],
          { m2_yoy: "M2", core_pce_yoy: "Core PCE", fed_target: "Target" },
          {
            events: [
              {
                date: "2026-06-01",
                event_date: "2026-06-16",
                policy_tone: "hawkish",
                statement_tone: "hawkish",
                minutes_status: "available",
                minutes_confirmation: "confirmed_but_divided",
                risk_focus: "inflation",
                risk_bias: "hawkish",
                policy_conviction: "divided",
              }
            ],
            policyTrack: true,
          }
        );
        console.log(JSON.stringify({
          hasPolicyTrack: markup.includes("relationship-policy-track"),
          hasCircle: markup.includes("<circle"),
          hasPath: markup.includes("<path"),
          hasInPlotBar: markup.includes("relationship-event-bar")
        }));
        """
    )
    result = subprocess.run(
        ["node", "-e", script],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload == {
        "hasPolicyTrack": True,
        "hasCircle": True,
        "hasPath": True,
        "hasInPlotBar": False,
    }


def test_macro_dashboard_js_renders_growth_cycle_sections():
    js = ROOT.joinpath("static/macro-dashboard.js").read_text(encoding="utf-8")

    assert "function renderGrowthCycleSections(" in js
    assert "function renderGrowthCycleSection(" in js
    assert "function renderGrowthCycleStatusPanel(" in js
    assert "state.growthCycle.sections || []" in js
    assert "growth-section" in js
    assert "growth-section-card-grid" in js


def test_macro_dashboard_static_assets_render_ism_industry_breadth():
    js = STATIC_JS.read_text()
    css = STATIC_CSS.read_text()

    assert "function renderIsmIndustryBreadthSegment(" in js
    assert "function renderIsmIndustryBreadthGroup(" in js
    assert "ism-industry-ranking" in js
    assert ".ism-industry-ranking" in css
    assert ".ism-industry-list" in css


def test_macro_dashboard_js_renders_ism_overview_cards():
    js = ROOT.joinpath("static/macro-dashboard.js").read_text(encoding="utf-8")

    assert "function renderIsmManufacturingCard(" in js
    assert 'card.id === "ism_manufacturing"' in js


def test_macro_dashboard_css_styles_ism_overview_cards():
    css = ROOT.joinpath("static/macro-dashboard.css").read_text(encoding="utf-8")

    assert ".ism-card" in css
    assert ".ism-card-primary" in css
    assert ".ism-card-grid" in css
    assert ".ism-metric-row" in css
    assert ".ism-card-supportive" in css
    assert ".ism-card-warning" in css


def test_macro_dashboard_css_styles_growth_cycle_sections():
    css = ROOT.joinpath("static/macro-dashboard.css").read_text(encoding="utf-8")

    assert ".growth-section-list" in css
    assert ".growth-section {" in css
    assert ".growth-section-head" in css
    assert ".growth-section-card-grid" in css
    assert ".growth-section-status" in css


def test_growth_cycle_ism_cards_open_focused_detail_static_assets():
    js = ROOT.joinpath("static/macro-dashboard.js").read_text(encoding="utf-8")
    css = ROOT.joinpath("static/macro-dashboard.css").read_text(encoding="utf-8")

    assert "selectedGrowthCycleDetailId" in js
    assert "renderIsmManufacturingCard" in js
    assert 'data-growth-cycle-detail-id="ism_manufacturing"' in js
    assert ".ism-card-button" in css
    assert ".ism-card-button.selected" in css
    assert ".ism-metric-band" in css


def test_growth_cycle_ism_detail_renderer_static_assets():
    js = ROOT.joinpath("static/macro-dashboard.js").read_text(encoding="utf-8")
    css = ROOT.joinpath("static/macro-dashboard.css").read_text(encoding="utf-8")

    assert "function renderIsmDetailInPanel(" in js
    assert "function renderIsmDetailChart(" in js
    assert "function renderIsmHeatMap(" in js
    assert "function renderIsmSmallMultiples(" in js
    assert "function renderIsmSmallMultiplePanel(" in js
    assert "function renderIsmSparklineSvg(" in js
    assert "function ismSparklineSegments(" in js
    assert "function renderIsmRelationshipContext(" in js
    assert "function attachIsmSharedTooltip(" in js
    assert "function rebaseVisibleSmallMultipleSeries(" in js
    assert "chart.contexts" in js
    assert 'chart.kind === "small_multiples"' in js
    assert "panel.line_shape" in js
    assert "function ismSparklineYearTicks(" in js
    assert "showXAxis" in js
    assert "renderRelationshipReferenceLines" in js
    assert ".relationship-reference-line" in css
    assert "payload.detail_groups" in js
    assert ".ism-detail-heat-map" in css
    assert ".ism-small-multiples" in css
    assert ".ism-small-panel" in css
    assert ".ism-sparkline-svg" in css
    assert "grid-template-columns: 140px minmax(0, 1fr)" in css
    assert ".ism-shared-tooltip" in css
    assert ".ism-relationship-context" in css


def test_macro_dashboard_renders_ism_report_summary_as_compact_rows():
    js = ROOT.joinpath("static/macro-dashboard.js").read_text(encoding="utf-8")
    css = ROOT.joinpath("static/macro-dashboard.css").read_text(encoding="utf-8")

    assert "ism-official-summary-row" in js
    assert "ism-official-summary-label" in js
    assert "ism-official-summary-value" in js
    assert "ism-official-major-change-list" in js
    assert "ism-official-major-change" in js
    assert "ism-official-comment-list" in js
    assert "ism-official-comment-row" in js
    assert "ism-official-comment-industry" in js
    assert "ism-official-comment-text" in js
    assert ".ism-official-summary-row" in css
    assert ".ism-official-summary-label" in css
    assert ".ism-official-summary-value" in css
    assert ".ism-official-major-change-list" in css
    assert ".ism-official-major-change" in css
    assert ".ism-official-comment-list" in css
    assert ".ism-official-comment-row" in css
    assert ".ism-official-comment-industry" in css
    assert ".ism-official-comment-text" in css


def test_macro_dashboard_renders_ism_comment_expander_static_assets():
    js = ROOT.joinpath("static/macro-dashboard.js").read_text(encoding="utf-8")
    css = ROOT.joinpath("static/macro-dashboard.css").read_text(encoding="utf-8")

    assert "comment_preview_count" in js
    assert "ism-official-comment-row-extra" in js
    assert "ism-official-comment-toggle" in js
    assert "data-ism-comment-toggle" in js
    assert "attachIsmOfficialSummaryHandlers" in js
    assert ".ism-official-comment-row-extra" in css
    assert ".ism-official-comment-toggle" in css
    assert ".ism-official-comment-list.expanded" in css


def test_macro_dashboard_static_assets_render_ism_trend_metadata():
    js = STATIC_JS.read_text()
    css = STATIC_CSS.read_text()

    assert "function fmtIsmPointChange(" in js
    assert "function renderIsmTrendChip(" in js
    assert "latest_metadata" in js
    assert ".ism-trend-chip" in css
    assert ".ism-trend-chip-green" in css
    assert ".ism-trend-chip-amber" in css
    assert ".ism-trend-chip-red" in css

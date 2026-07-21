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
    assert "Scenario Coverage" in js
    assert "M lag A + B + C" in js
    assert "M lag A + B" in js
    assert "M lag rate" in js
    assert "Quadnomial distribution defines A as index down/GDP down" in js
    assert "Scenario coverage combines A, B, and C" in js
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
    assert (
        'class="rates-signal-card${selected}${targetId ? " evidence-target" : ""}"'
        in js
    )
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
    assert "ISM-Implied Direction" in js
    assert "Macro Portfolio Bias" in js
    assert "Method 07" not in js
    assert "Not Loaded" in js
    assert "componentStatusBadge(" in js
    assert "componentLabel(" in js
    assert "gdp-component-row" in js
    assert "comp.id" in js
    assert "comp.status" in js
    assert "card.evidence" in js
    assert "Expected Direction" in js


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
    assert "formatPressureValue" in js
    assert "Policy Pressure" in js
    assert "Combined Pressure" in js
    assert "Growth Pressure" in js
    assert "Inflation Pressure" in js
    assert "Supply Pressure" in js
    assert "inflation_caution" in js
    assert "less_easing_pressure" in js
    assert "ism-policy-pressure" in js


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


def test_growth_cycle_detail_reloads_current_data_when_reopened():
    js = ROOT.joinpath("static/macro-dashboard.js").read_text(encoding="utf-8")
    function_body = js.split("async function loadGrowthCycleDetail(detailId) {", 1)[
        1
    ].split("\n  }", 1)[0]

    assert "fetch(`/api/macro-dashboard/growth-cycle/" in function_body
    assert "if (state.growthCycleDetailsById[detailId])" not in function_body


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


def test_macro_dashboard_js_has_industry_analysis_renderers():
    js = STATIC_JS.read_text()
    css = STATIC_CSS.read_text()

    assert "selectedIsmIndustry" in js
    assert "function ismScoreLabelClass(" in js
    assert "function ismSignalBadgeClass(" in js
    assert "function ismSignalRowClass(" in js
    assert "function ismSignalLabel(" in js
    assert "function ismOverallTrendLabel(" in js
    assert "function renderIsmSignalBadge(" in js
    assert "function renderIsmRankText(" in js
    assert "function renderIsmIndustryAnalysisSection(" in js
    assert "function renderIsmIndustryDetailView(" in js
    assert "function renderIsmCoreSignalRow(" in js
    assert "function renderIsmScoreComponentDetail(" in js
    assert "function renderIsmMacroContext(" in js
    assert "function renderIsmIndustryTrend(" in js
    assert "function bindIsmIndustrySelector(" in js
    assert "data-ism-industry-select" in js
    assert "data-ism-industry-detail" in js
    assert "ISM signal configuration, not an investment recommendation" in js
    assert "No respondent comment in this report" in js
    assert "Score Components" in js
    assert "ism-demand" in js
    assert "Macro Demand Context" in js
    assert "Signal Trend" in js
    assert "Historical coverage unavailable" in js
    assert ".ism-industry-analysis" in css
    assert ".ism-industry-select" in css
    assert ".ism-industry-detail" in css
    assert ".ism-score-value" in css
    assert ".ism-score-label" in css
    assert ".ism-score-strong" in css
    assert ".ism-score-improving" in css
    assert ".ism-score-mixed" in css
    assert ".ism-score-weakening" in css
    assert ".ism-score-weak" in css
    assert ".ism-score-unavailable" in css
    assert ".ism-signal-badge" in css
    assert ".ism-signal-positive" in css
    assert ".ism-signal-negative" in css
    assert ".ism-signal-not-reported" in css
    assert ".ism-signal-unavailable" in css
    assert ".ism-signal-row-positive" in css
    assert ".ism-signal-row-negative" in css
    assert ".ism-signal-row-not-reported" in css
    assert ".ism-signal-row-unavailable" in css
    assert ".ism-component-bar" in css
    assert ".ism-trend-table" in css
    assert ".ism-industry-component" in css
    assert ".ism-demand-wrap" in css
    assert ".ism-demand-row" in css
    assert ".ism-demand-right" in css
    assert ".ism-industry-source" in css


def test_macro_dashboard_js_industry_analysis_renderers_produce_correct_html():
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

        // Test helper functions
        console.log(JSON.stringify({
          scoreLabelStrong: hooks.ismScoreLabelClass("strong"),
          scoreLabelWeak: hooks.ismScoreLabelClass("weak"),
          scoreLabelUnknown: hooks.ismScoreLabelClass("unknown"),
          signalBadgePositive: hooks.ismSignalBadgeClass("positive"),
          signalBadgeNotReported: hooks.ismSignalBadgeClass("not_reported"),
          signalBadgeUnavailable: hooks.ismSignalBadgeClass("unavailable"),
          signalRowPositive: hooks.ismSignalRowClass("positive"),
          signalRowNegative: hooks.ismSignalRowClass("negative"),
          signalLabelPositive: hooks.ismSignalLabel("positive"),
          signalLabelNotReported: hooks.ismSignalLabel("not_reported"),
          signalLabelUnavailable: hooks.ismSignalLabel("unavailable"),
          rankTextNormal: hooks.renderIsmRankText(11, 3),
          rankTextNull: hooks.renderIsmRankText(null, null),
          signalBadgeHtml: hooks.renderIsmSignalBadge({ status: "positive", rank: 3, list_size: 11, component_score: 90.9 }),
          signalBadgeUnavailableHtml: hooks.renderIsmSignalBadge({}),
          coreSignalRowHtml: hooks.renderIsmCoreSignalRow("new_orders", { status: "positive", rank: 3, list_size: 11, component_score: 90.9 }, "New Orders"),
          coreSignalRowNegative: hooks.renderIsmCoreSignalRow("new_orders", { status: "negative", rank: 1, list_size: 6, component_score: 0.0 }, "New Orders"),
          coreSignalRowNotReported: hooks.renderIsmCoreSignalRow("backlog", { status: "not_reported", rank: null, list_size: null, component_score: 50.0 }, "Backlog"),
          unavailableSection: hooks.renderIsmIndustryAnalysisSection({ status: "unavailable", reason: "latest ISM report is unavailable", industries: [] }, null),
          noAnalysis: hooks.renderIsmIndustryAnalysisSection(null, null),
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

    assert payload["scoreLabelStrong"] == "ism-score-strong"
    assert payload["scoreLabelWeak"] == "ism-score-weak"
    assert payload["scoreLabelUnknown"] == "ism-score-unavailable"
    assert payload["signalBadgePositive"] == "ism-signal-positive"
    assert payload["signalBadgeNotReported"] == "ism-signal-not-reported"
    assert payload["signalBadgeUnavailable"] == "ism-signal-unavailable"
    assert payload["signalRowPositive"] == "ism-signal-row-positive"
    assert payload["signalRowNegative"] == "ism-signal-row-negative"
    assert payload["signalLabelPositive"] == "Positive"
    assert payload["signalLabelNotReported"] == "Not listed"
    assert payload["signalLabelUnavailable"] == "Unavailable"
    assert payload["rankTextNormal"] == "#3 of 11"
    assert payload["rankTextNull"] == "\u2014"
    assert "ism-signal-positive" in payload["signalBadgeHtml"]
    assert "Growth" in payload["signalBadgeHtml"]
    assert "ism-signal-unavailable" in payload["signalBadgeUnavailableHtml"]
    assert "ism-signal-row-positive" in payload["coreSignalRowHtml"]
    assert "New Orders" in payload["coreSignalRowHtml"]
    assert "#3 of 11 growing industries" in payload["coreSignalRowHtml"]
    assert "90.9" in payload["coreSignalRowHtml"]
    assert "Strongest decline" in payload["coreSignalRowNegative"]
    assert "#1 of 6 declining industries" in payload["coreSignalRowNegative"]
    assert "ism-signal-row-not-reported" in payload["coreSignalRowNotReported"]
    assert "Not listed" in payload["coreSignalRowNotReported"]
    assert "\u2014" in payload["coreSignalRowNotReported"]
    assert "ISM report is unavailable" in payload["unavailableSection"]
    assert payload["noAnalysis"] == ""


def test_macro_dashboard_js_renders_industry_analysis_detail_view():
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

        const analysis = {
          status: "available",
          score_version: "ism_industry_signal_v1",
          score_weights: { new_orders: 0.40, production: 0.30, backlog: 0.20, overall: 0.10 },
          coverage_summary: { complete_components: 4, unavailable_components: 0 },
          report_id: "ism_manufacturing_2026_06",
          period: "2026-06-01",
          source_url: "https://example.com/report",
          macro_context: {
            new_orders: { value: 56.0, direction: "Growing", rate_of_change: "Slower", point_change: -1.5, trend_months: 8, tone: "amber" },
            production: { value: 52.2, direction: "Growing", rate_of_change: "Slower", point_change: -0.8, trend_months: 6, tone: "amber" },
            backlog: { value: 50.5, direction: "Growing", rate_of_change: "Slower", point_change: -2.1, trend_months: 4, tone: "amber" },
            inventories: { value: 51.4, direction: "Growing", rate_of_change: "From Contracting", point_change: 3.2, trend_months: 2, tone: "amber" },
            customer_inventories: { value: 42.3, direction: "Too Low", rate_of_change: "Faster", point_change: -4.1, trend_months: 5, tone: "amber" },
          },
          industries: [
            {
              industry: "Printing & Related Support Activities",
              overall_signal: { status: "positive", direction: "growth", rank: 1, list_size: 14, component_score: 100.0 },
              score: 86.4,
              score_coverage: 100.0,
              score_label: "strong",
              summary: "New Orders and Production are strong; Backlog was not reported.",
              core_signals: {
                new_orders: { status: "positive", direction: "growth", rank: 3, list_size: 11, component_score: 90.9, evidence_text: null },
                production: { status: "positive", direction: "growth", rank: 1, list_size: 8, component_score: 100.0, evidence_text: null },
                backlog: { status: "not_reported", direction: null, rank: null, list_size: null, component_score: 50.0, evidence_text: null },
              },
              secondary_signals: {},
              comments: [],
              trend: [
                { period: "2026-05-01", score: 71.2, score_coverage: 100.0, overall_rank: 4, overall_direction: "growth", positive_confirmation_count: 2, new_orders: { status: "positive", rank: 5 }, production: { status: "positive", rank: 3 }, backlog: { status: "not_reported", rank: null } },
                { period: "2026-06-01", score: 86.4, score_coverage: 100.0, overall_rank: 1, overall_direction: "growth", positive_confirmation_count: 2, new_orders: { status: "positive", rank: 3 }, production: { status: "positive", rank: 1 }, backlog: { status: "not_reported", rank: null } },
              ],
            },
          ],
        };

        const sectionHtml = hooks.renderIsmIndustryAnalysisSection(analysis, analysis.industries[0]);
        const detailHtml = hooks.renderIsmIndustryDetailView(analysis.industries[0], analysis);

        console.log(JSON.stringify({
          sectionHasIndustry: sectionHtml.indexOf("Printing &amp; Related Support Activities") !== -1,
          sectionHasVersion: sectionHtml.indexOf("ism_industry_signal_v1") !== -1,
          sectionHasSelector: sectionHtml.indexOf("data-ism-industry-select") !== -1,
          sectionHasDetailContainer: sectionHtml.indexOf("data-ism-industry-detail") !== -1,
          sectionHasSourceLink: sectionHtml.indexOf("https://example.com/report") !== -1,
          sectionHasScoreExplanation: sectionHtml.indexOf("ISM signal configuration") !== -1,
          detailHasScore: detailHtml.indexOf("86.4") !== -1,
          detailHasScoreLabel: detailHtml.indexOf("ism-score-strong") !== -1,
          detailHasSummary: detailHtml.indexOf("New Orders and Production are strong") !== -1,
          detailHasNewOrdersRow: detailHtml.indexOf("New Orders") !== -1,
          detailHasProductionRow: detailHtml.indexOf("Production") !== -1,
          detailHasBacklogRow: detailHtml.indexOf("Backlog") !== -1,
          detailHasOverallRow: detailHtml.indexOf("Overall") !== -1,
          detailHasRank3Of11: detailHtml.indexOf("#3 of 11") !== -1,
          detailHasRank1Of8: detailHtml.indexOf("#1 of 8") !== -1,
          detailHasPositiveBadge: (detailHtml.match(/class="[^"]*ism-signal-positive[^"]*"/g) || []).length >= 1,
          detailHasNotReportedBadge: detailHtml.indexOf("Not listed") !== -1,
          detailHasScoreComponents: detailHtml.indexOf("Score Components") !== -1,
          sectionHasMacroContextBeforeSelector: sectionHtml.indexOf("ism-demand-wrap") !== -1 && sectionHtml.indexOf("ism-demand-wrap") < sectionHtml.indexOf("data-ism-industry-select"),
          detailHasNoComment: detailHtml.indexOf("No respondent comment in this report") !== -1,
          detailHasTrend: detailHtml.indexOf("Signal Trend") !== -1,
          detailHasTrendRow: detailHtml.indexOf("May 2026") !== -1 && detailHtml.indexOf("Jun 2026") !== -1,
          detailHasTrendScore: detailHtml.indexOf("71.2") !== -1 && detailHtml.indexOf("86.4") !== -1,
          detailHasOfficialLink: detailHtml.indexOf("Official ISM Report") !== -1,
          scoreComponentNewOrders: hooks.renderIsmScoreComponentDetail(analysis.industries[0].core_signals, analysis.industries[0].overall_signal, analysis.score_weights),
          macroContextHtml: hooks.renderIsmMacroContext(analysis.macro_context),
          trendHtml: hooks.renderIsmIndustryTrend(analysis.industries[0].trend),
          emptyTrendHtml: hooks.renderIsmIndustryTrend([]),
          allNullTrendHtml: hooks.renderIsmIndustryTrend([
            { period: "2026-05-01", score: null, score_coverage: 0.0, overall_rank: null, overall_direction: null, positive_confirmation_count: 0, new_orders: { status: null }, production: { status: null }, backlog: { status: null } },
            { period: "2026-06-01", score: null, score_coverage: 0.0, overall_rank: null, overall_direction: null, positive_confirmation_count: 0, new_orders: { status: null }, production: { status: null }, backlog: { status: null } },
          ]),
          oneMonthTrendHtml: hooks.renderIsmIndustryTrend([
            { period: "2026-06-01", score: 75.0, score_coverage: 100.0, overall_rank: 1, overall_direction: "growth", positive_confirmation_count: 2, new_orders: { status: "positive", rank: 3 }, production: { status: "positive", rank: 1 }, backlog: { status: "not_reported", rank: null } },
          ]),
          svgChartMarkup: hooks.renderIsmScoreTrendSvg([
            { period: "2026-05-01", score: 71.2, score_coverage: 100.0, overall_rank: 4, overall_direction: "growth", positive_confirmation_count: 2, new_orders: { status: "positive", rank: 5 }, production: { status: "positive", rank: 3 }, backlog: { status: "not_reported", rank: null } },
            { period: "2026-06-01", score: 86.4, score_coverage: 100.0, overall_rank: 1, overall_direction: "growth", positive_confirmation_count: 2, new_orders: { status: "positive", rank: 3 }, production: { status: "positive", rank: 1 }, backlog: { status: "not_reported", rank: null } },
          ]),
          svgGapChart: hooks.renderIsmScoreTrendSvg([
            { period: "2026-05-01", score: 71.2, score_coverage: 100.0, overall_rank: 4, overall_direction: "growth", positive_confirmation_count: 2, new_orders: { status: "positive", rank: 5 }, production: { status: "positive", rank: 3 }, backlog: { status: "not_reported", rank: null } },
            { period: "2026-06-01", score: null, score_coverage: 0.0, overall_rank: null, overall_direction: null, positive_confirmation_count: 0, new_orders: { status: null }, production: { status: null }, backlog: { status: null } },
            { period: "2026-07-01", score: 86.4, score_coverage: 100.0, overall_rank: 1, overall_direction: "growth", positive_confirmation_count: 2, new_orders: { status: "positive", rank: 3 }, production: { status: "positive", rank: 1 }, backlog: { status: "not_reported", rank: null } },
          ]),
          scoreChangePositive: hooks.renderIsmIndustryTrend([
            { period: "2026-05-01", score: 50.0, score_coverage: 100.0, overall_rank: 5, overall_direction: "growth", positive_confirmation_count: 1, new_orders: { status: "positive", rank: 5 }, production: { status: "positive", rank: 5 }, backlog: { status: "not_reported", rank: null } },
            { period: "2026-06-01", score: 65.2, score_coverage: 100.0, overall_rank: 3, overall_direction: "growth", positive_confirmation_count: 2, new_orders: { status: "positive", rank: 3 }, production: { status: "positive", rank: 3 }, backlog: { status: "not_reported", rank: null } },
          ], { latest_score_change: 15.2 }),
          scoreChangeNull: hooks.renderIsmIndustryTrend([
            { period: "2026-06-01", score: 65.2, score_coverage: 100.0, overall_rank: 3, overall_direction: "growth", positive_confirmation_count: 2, new_orders: { status: "positive", rank: 3 }, production: { status: "positive", rank: 3 }, backlog: { status: "not_reported", rank: null } },
          ], { latest_score_change: null }),
          scoreChangeNegative: hooks.renderIsmIndustryTrend([
            { period: "2026-05-01", score: 68.3, score_coverage: 100.0, overall_rank: 2, overall_direction: "growth", positive_confirmation_count: 2, new_orders: { status: "positive", rank: 2 }, production: { status: "positive", rank: 2 }, backlog: { status: "not_reported", rank: null } },
            { period: "2026-06-01", score: 65.2, score_coverage: 100.0, overall_rank: 3, overall_direction: "growth", positive_confirmation_count: 2, new_orders: { status: "positive", rank: 3 }, production: { status: "positive", rank: 3 }, backlog: { status: "not_reported", rank: null } },
          ], { latest_score_change: -3.1 }),
          broadOneMonth: hooks.renderIsmIndustryTrend([
            { period: "2026-06-01", score: 89.2, score_coverage: 100.0, overall_rank: 1, overall_direction: "growth", positive_confirmation_count: 3, new_orders: { status: "positive", rank: 1 }, production: { status: "positive", rank: 1 }, backlog: { status: "positive", rank: 1 } },
          ], { latest_positive_confirmation_count: 3, broad_confirmation_streak: 1 }),
          broadPersistent: hooks.renderIsmIndustryTrend([
            { period: "2026-05-01", score: null, score_coverage: 90.0, overall_rank: null, overall_direction: null, positive_confirmation_count: 3, new_orders: { status: "positive", rank: 2 }, production: { status: "positive", rank: 2 }, backlog: { status: "positive", rank: 2 } },
            { period: "2026-06-01", score: 89.2, score_coverage: 100.0, overall_rank: 1, overall_direction: "growth", positive_confirmation_count: 3, new_orders: { status: "positive", rank: 1 }, production: { status: "positive", rank: 1 }, backlog: { status: "positive", rank: 1 } },
          ], { latest_positive_confirmation_count: 3, broad_confirmation_streak: 2 }),
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

    assert payload["sectionHasIndustry"] is True
    assert payload["sectionHasVersion"] is True
    assert payload["sectionHasSelector"] is True
    assert payload["sectionHasDetailContainer"] is True
    assert payload["sectionHasSourceLink"] is True
    assert payload["sectionHasScoreExplanation"] is True
    assert payload["detailHasScore"] is True
    assert payload["detailHasScoreLabel"] is True
    assert payload["detailHasSummary"] is True
    assert payload["detailHasNewOrdersRow"] is True
    assert payload["detailHasProductionRow"] is True
    assert payload["detailHasBacklogRow"] is True
    assert payload["detailHasOverallRow"] is True
    assert payload["detailHasRank3Of11"] is True
    assert payload["detailHasRank1Of8"] is True
    assert payload["detailHasPositiveBadge"] is True
    assert payload["detailHasNotReportedBadge"] is True
    assert payload["detailHasScoreComponents"] is True
    assert payload["sectionHasMacroContextBeforeSelector"] is True
    assert payload["detailHasNoComment"] is True
    assert payload["detailHasTrend"] is True
    assert payload["detailHasTrendRow"] is True
    assert payload["detailHasTrendScore"] is True
    assert payload["detailHasOfficialLink"] is True
    assert "ism-component-bar" in payload["scoreComponentNewOrders"]
    assert "40%" in payload["scoreComponentNewOrders"]
    assert "90.9" in payload["scoreComponentNewOrders"]
    assert "ism-demand-row" in payload["macroContextHtml"]
    assert "New Orders" in payload["macroContextHtml"]
    assert "56.0" in payload["macroContextHtml"]
    assert "ism-trend-chip" in payload["macroContextHtml"]
    assert "ism-trend-table" in payload["trendHtml"]
    assert "May 2026" in payload["trendHtml"]
    assert ">Coverage<" in payload["trendHtml"]
    assert ">Overall Industry<" in payload["trendHtml"]
    assert ">New Orders<" in payload["trendHtml"]
    assert ">Production<" in payload["trendHtml"]
    assert ">Order Backlogs<" in payload["trendHtml"]
    assert "Overall\u6574\u4f53" not in payload["trendHtml"]
    assert "Growth" in payload["trendHtml"]
    assert "Not listed" in payload["trendHtml"]
    assert "Historical coverage unavailable" in payload["emptyTrendHtml"]

    assert "+15.2" in payload["scoreChangePositive"]
    assert "Score change:" not in payload["scoreChangeNull"]
    assert "-3.1" in payload["scoreChangeNegative"]
    assert "only a one-month signal" in payload["broadOneMonth"]
    assert "Broad and persistent improvement" in payload["broadPersistent"]
    assert "New Orders, Production, and Order Backlogs" in payload["broadPersistent"]
    assert "Positive core signals: 3/3" in payload["broadPersistent"]
    assert "Historical coverage unavailable" in payload["allNullTrendHtml"]
    assert "Jun 2026" in payload["oneMonthTrendHtml"]
    assert "75.0" in payload["oneMonthTrendHtml"]
    assert "<polyline" in payload["svgChartMarkup"]
    assert "<circle" in payload["svgChartMarkup"]
    assert 'tabindex="0"' in payload["svgChartMarkup"]
    assert "aria-label" in payload["svgChartMarkup"]
    assert "Rank:" in payload["svgChartMarkup"]
    assert "New Orders:" in payload["svgChartMarkup"]
    assert "Production:" in payload["svgChartMarkup"]
    assert "Order Backlogs:" in payload["svgChartMarkup"]
    assert "Cov:" in payload["svgChartMarkup"]
    assert "#5" in payload["svgChartMarkup"]  # New Orders rank
    assert "#3" in payload["svgChartMarkup"]  # Production rank
    assert "<title>" in payload["svgChartMarkup"]
    assert 'stroke-dasharray="3,2"' in payload["svgChartMarkup"]
    assert "max-width:100%" not in payload["svgChartMarkup"]
    assert "height:auto" not in payload["svgChartMarkup"]
    # Gap chart should have no line connecting through null midpoint
    gap_polyline_count = payload["svgGapChart"].count("<polyline")
    assert gap_polyline_count == 0  # both segments have only 1 point, so no polyline


def test_macro_dashboard_js_industry_analysis_evidence_section():
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

        const coreSignals = {
          new_orders: { status: "positive", evidence_text: "The 11 manufacturing industries reporting growth in New Orders in June, in rank order, are..." },
          production: { status: "positive", evidence_text: null },
          backlog: { status: "not_reported", evidence_text: null },
        };
        const evidenceHtml = hooks.renderIsmEvidenceDetail(coreSignals);
        const evidenceEmpty = hooks.renderIsmEvidenceDetail({});

        console.log(JSON.stringify({
          hasEvidence: evidenceHtml.indexOf("Source Evidence") !== -1,
          hasNewOrdersEvidence: evidenceHtml.indexOf("11 manufacturing industries") !== -1,
          hasSummaryTag: evidenceHtml.indexOf("<summary>") !== -1,
          emptyReturnsEmpty: evidenceEmpty === "",
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

    assert payload["hasEvidence"] is True
    assert payload["hasNewOrdersEvidence"] is True
    assert payload["hasSummaryTag"] is True
    assert payload["emptyReturnsEmpty"] is True


def test_macro_dashboard_js_industry_list_renders_buttons():
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

        const growthItems = [
          { industry: "Printing & Related Support Activities" },
          { industry: "Machinery" },
        ];
        const contractionItems = [
          { industry: "Primary Metals" },
        ];

        const growthHtml = hooks.renderIsmIndustryList(growthItems, "growth", "No growth");
        const contractionHtml = hooks.renderIsmIndustryList(contractionItems, "contraction", "No contraction");
        const emptyHtml = hooks.renderIsmIndustryList([], "growth", "No industries");

        console.log(JSON.stringify({
          growthIsButtons: growthHtml.indexOf("<button") !== -1 && growthHtml.indexOf("</button>") !== -1,
          growthHasDataAttribute: growthHtml.indexOf('data-ism-industry="Printing') !== -1,
          growthHasIndustryName: growthHtml.indexOf("Printing") !== -1,
          growthHasMedal: growthHtml.indexOf("\\ud83e\\udd47") !== -1,
          contractionIsButton: contractionHtml.indexOf("<button") !== -1 && contractionHtml.indexOf("</button>") !== -1,
          contractionHasRedTriangle: contractionHtml.indexOf("\\ud83d\\udd3b") !== -1,
          emptyFallsBack: emptyHtml.indexOf("No industries") !== -1,
          emptyIsParagraph: emptyHtml.indexOf("<p") !== -1,
          growthButtonCount: (growthHtml.match(/data-ism-industry/g) || []).length,
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

    assert payload["growthIsButtons"] is True
    assert payload["growthHasDataAttribute"] is True
    assert payload["growthHasIndustryName"] is True
    assert payload["growthHasMedal"] is True
    assert payload["contractionIsButton"] is True
    assert payload["contractionHasRedTriangle"] is True
    assert payload["emptyFallsBack"] is True
    assert payload["emptyIsParagraph"] is True
    assert payload["growthButtonCount"] == 2


def test_macro_dashboard_js_industry_selection_interaction():
    script = textwrap.dedent(
        """
        const fs = require("fs");
        const vm = require("vm");

        const relationshipHead = { outerHTML: '<div class="relationship-head"></div>' };
        const bodyEventHandlers = {};
        const elements = {
          dashboardStatus: {},
          macroDashboardApp: {
            classList: { add: () => {}, remove: () => {}, toggle: () => {} },
            insertAdjacentHTML: () => {},
          },
          detailPanel: {
            innerHTML: "",
            querySelector: (sel) => {
              if (sel === ".detail-panel-close") return { addEventListener: () => {} };
              if (sel === ".detail-panel-expand") return { addEventListener: () => {} };
              if (sel === ".detail-panel-body") return { innerHTML: "", scrollTop: 0, querySelectorAll: () => [], addEventListener: () => {} };
              return null;
            },
            querySelectorAll: () => [],
          },
          marketGrid: { innerHTML: "", querySelectorAll: () => [] },
          marketDetail: { innerHTML: "" },
          growthCycle: { innerHTML: '<div class="relationship-head"></div>', querySelector: (sel) => sel === ".relationship-head" ? relationshipHead : null, querySelectorAll: () => [] },
        };

        global.window = { __MEOWSTREET_TEST__: true };
        global.document = {
          getElementById: (id) => elements[id],
        };
        global.fetch = async () => ({
          ok: true,
          status: 200,
          json: async () => ({ markets: [], headline: [], sections: [] }),
        });

        vm.runInThisContext(fs.readFileSync("static/macro-dashboard.js", "utf8"));
        const hooks = global.window.__macroDashboardTestHooks;

        const analysis = {
          status: "available",
          industries: [
            { industry: "Printing & Related Support Activities", overall_signal: { status: "positive", rank: 1, list_size: 14, component_score: 100.0 }, score: 86.4, score_coverage: 100.0, score_label: "strong", core_signals: { new_orders: { status: "positive", rank: 3, list_size: 11, component_score: 90.9 }, production: { status: "positive", rank: 1, list_size: 8, component_score: 100.0 }, backlog: { status: "not_reported", component_score: 50.0 } }, secondary_signals: {}, comments: [], trend: [] },
            { industry: "Machinery", overall_signal: { status: "positive", rank: 2, list_size: 14, component_score: 85.0 }, score: 75.0, score_coverage: 100.0, score_label: "strong", core_signals: { new_orders: { status: "positive", rank: 5, list_size: 11, component_score: 81.8 }, production: { status: "positive", rank: 3, list_size: 8, component_score: 87.5 }, backlog: { status: "not_reported", component_score: 50.0 } }, secondary_signals: {}, comments: [], trend: [] },
          ],
        };

        // Build a body mock that tracks event listeners as arrays to detect duplicates
        const listenerArrays = { change: [], click: [] };
        let detailContainer = { outerHTML: "", dataset: {} };
        let buttons = [
          { dataset: { ismIndustry: "Printing & Related Support Activities" }, classList: { toggle: () => {} } },
          { dataset: { ismIndustry: "Machinery" }, classList: { toggle: () => {} } },
        ];
        let selectEl = { value: "Printing & Related Support Activities", dataset: {}, closest: (sel) => sel === "[data-ism-industry-select]" ? selectEl : null };
        Object.defineProperty(detailContainer, "outerHTML", {
          set(val) { body.innerHtml = val; },
          get() { return body.innerHtml || ""; },
          configurable: true,
        });

        const body = {
          innerHtml: "",
          dataset: {},
          addEventListener: (evt, fn) => { listenerArrays[evt].push(fn); },
          querySelector: (sel) => {
            if (sel === "[data-ism-industry-detail]") return detailContainer;
            if (sel === "[data-ism-industry-select]") return selectEl;
            return null;
          },
          querySelectorAll: (sel) => {
            if (sel === "[data-ism-industry]") return buttons;
            return [];
          },
        };

        // Set initial detail HTML for Printing
        body.innerHtml = hooks.renderIsmIndustryDetailView(analysis.industries[0], analysis);
        hooks.state.selectedIsmIndustry = null;

        // Call bindIsmIndustrySelector twice to verify no duplicate listener accumulation
        hooks.bindIsmIndustrySelector(body, analysis);
        hooks.bindIsmIndustrySelector(body, analysis);
        const listenerCount = listenerArrays.change.length + listenerArrays.click.length;

        // Bind again with a different analysis payload to verify refreshed data
        const analysis2 = JSON.parse(JSON.stringify(analysis));
        analysis2.industries[0].industry = "Updated Printing";
        hooks.bindIsmIndustrySelector(body, analysis2);
        // Verify second bind still no duplication
        const listenerCountAfterFresh = listenerArrays.change.length + listenerArrays.click.length;

        // Dispatch change event and verify it uses latest analysis
        selectEl.value = "Updated Printing";
        listenerArrays.change[0]({ target: selectEl });
        const afterChangeState = hooks.state.selectedIsmIndustry;

        // Dispatch click event via a button
        hooks.state.selectedIsmIndustry = null;
        const buttonTarget = { closest: (sel) => sel === "[data-ism-industry]" ? { dataset: { ismIndustry: "Machinery" } } : null };
        listenerArrays.click[0]({ target: buttonTarget });
        const afterClickState = hooks.state.selectedIsmIndustry;

        console.log(JSON.stringify({
          listenerCount: listenerCount,
          noExtraListeners: listenerCountAfterFresh === listenerCount,
          afterChangeUsesLatest: afterChangeState === "Updated Printing",
          afterClickIsMachinery: afterClickState === "Machinery",
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

    assert payload["listenerCount"] == 2
    assert payload["noExtraListeners"] is True
    assert payload["afterChangeUsesLatest"] is True
    assert payload["afterClickIsMachinery"] is True


def test_macro_dashboard_css_has_gdp_expectations_component_styles():
    css = STATIC_CSS.read_text()

    assert ".gdp-components" in css
    assert ".gdp-component-row" in css
    assert ".gdp-component-row-right" in css
    assert ".component-status-available" in css
    assert ".component-status-pending" in css
    assert ".component-status-unavailable" in css


def test_macro_dashboard_css_has_ism_policy_pressure_styles():
    css = STATIC_CSS.read_text()

    assert ".ism-policy-pressure" in css
    assert ".ism-policy-pressure-head" in css


def test_macro_dashboard_css_has_bias_evidence_strip_styles():
    css = STATIC_CSS.read_text()

    assert ".bias-evidence-strip" in css
    assert ".bias-evidence-head" in css
    assert ".bias-evidence-body" in css
    assert ".bias-components" in css
    assert ".bias-component" in css
    assert ".bias-reasons" in css
    assert ".bias-available" in css
    assert ".bias-pending" in css


def test_macro_dashboard_js_renders_gdp_expectations_card_with_components():
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

        const card = {
          id: "gdp_expectations",
          label: "GDP Expectations",
          status: "available",
          status_label: "ISM Outlook",
          components: [
            { id: "ism_manufacturing", status: "available", direction: "supports_growth", period: "2026-06-01" },
            { id: "ism_services", status: "not_loaded", role: "confirmation" },
            { id: "labor_trend", status: "not_loaded", role: "confirmation" },
            { id: "consumer_indicators", status: "not_loaded", role: "confirmation" },
          ],
          evidence: ["Manufacturing PMI is above 50 and rising"],
          supporting_context: "GDP direction matters for market correlation.",
          expected_direction: "rising",
        };

        const html = hooks.renderGdpExpectationsCard(card);

        console.log(JSON.stringify({
          hasComponents: html.indexOf("gdp-component-row") !== -1,
          ismManufacturingLabel: html.indexOf("ISM Manufacturing") !== -1,
          ismServicesLabel: html.indexOf("ISM Services") !== -1,
          laborTrendLabel: html.indexOf("Labor Trend") !== -1,
          consumerIndicatorsLabel: html.indexOf("Consumer Indicators") !== -1,
          availableBadge: html.indexOf("Available") !== -1,
          notLoadedBadge: html.indexOf("Not Loaded") !== -1,
          supportsGrowth: html.indexOf("Supports Growth") !== -1,
          evidenceText: html.indexOf("Manufacturing PMI") !== -1,
          impliedDirection: html.indexOf("ISM-Implied Direction") !== -1,
          risingDirection: html.indexOf("Rising") !== -1,
          oldRequiredInputs: html.indexOf("Required Inputs") === -1,
          componentStatusAvailable: html.indexOf("component-status-available") !== -1,
          componentStatusPending: html.indexOf("component-status-pending") !== -1,
          componentStatusUnavailable: html.indexOf("component-status-unavailable") !== -1,
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

    assert payload["hasComponents"] is True
    assert payload["ismManufacturingLabel"] is True
    assert payload["ismServicesLabel"] is True
    assert payload["laborTrendLabel"] is True
    assert payload["consumerIndicatorsLabel"] is True
    assert payload["availableBadge"] is True
    assert payload["notLoadedBadge"] is True
    assert payload["supportsGrowth"] is True
    assert payload["evidenceText"] is True
    assert payload["impliedDirection"] is True
    assert payload["risingDirection"] is True
    assert payload["oldRequiredInputs"] is True
    assert payload["componentStatusAvailable"] is True
    assert payload["componentStatusPending"] is True
    assert payload["componentStatusUnavailable"] is False


def test_macro_dashboard_js_keeps_ism_policy_pressure_out_of_fomc_card():
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

        const card = {
          id: "fomc_tone",
          label: "FOMC Policy Read",
          status: "context",
          latest_tone: {
            marker_tone: "hawkish",
            policy_action: "hold",
            guidance_bias: "hawkish",
            language_tone: "hawkish",
            overall_bias: "hawkish",
            tone_change: "unchanged",
            start_date: "2026-06-16",
            end_date: "2026-06-17",
            minutes_status: "available",
            minutes_confirmation: "confirmed_but_divided",
            risk_focus: "inflation",
            policy_conviction: "divided",
          },
          ism_policy_context: {
            combined_pressure: "inflation_caution",
            growth_pressure: "less_easing_pressure",
            inflation_pressure: "elevated",
            supply_pressure: "normal",
            period: "2026-06-01",
            version: "ism_macro_signal_v1",
          },
        };

        const html = hooks.renderFomcToneCard(card);

        console.log(JSON.stringify({
          hasToneSection: html.indexOf("fomc-tone-badge") !== -1,
          hasAction: html.indexOf("Action") !== -1,
          hasGuidance: html.indexOf("Guidance") !== -1,
          hasLanguage: html.indexOf("Language") !== -1,
          hasBias: html.indexOf("Bias") !== -1,
          hasChange: html.indexOf("Change") !== -1,
          hasIsmPolicyContext: html.indexOf("ism-policy-context") !== -1,
          hasCombinedPressure: html.indexOf("Combined Pressure") !== -1,
          hasGrowthPressure: html.indexOf("Growth Pressure") !== -1,
          hasInflationPressure: html.indexOf("Inflation Pressure") !== -1,
          hasSupplyPressure: html.indexOf("Supply Pressure") !== -1,
          hasInflationCaution: html.indexOf("Inflation Caution") !== -1,
          hasLessEasing: html.indexOf("Less Easing Pressure") !== -1,
          hasElevated: html.indexOf("Elevated") !== -1,
          hasNormal: html.indexOf("Normal") !== -1,
          hasMinutesBlock: html.indexOf("Minutes Confirmation") !== -1,
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

    assert payload["hasToneSection"] is True
    assert payload["hasAction"] is True
    assert payload["hasGuidance"] is True
    assert payload["hasLanguage"] is True
    assert payload["hasBias"] is True
    assert payload["hasChange"] is True
    assert payload["hasIsmPolicyContext"] is False
    assert payload["hasCombinedPressure"] is False
    assert payload["hasGrowthPressure"] is False
    assert payload["hasInflationPressure"] is False
    assert payload["hasSupplyPressure"] is False
    assert payload["hasInflationCaution"] is False
    assert payload["hasLessEasing"] is False
    assert payload["hasElevated"] is False
    assert payload["hasNormal"] is False
    assert payload["hasMinutesBlock"] is True


def test_macro_dashboard_js_does_not_use_ism_context_as_fomc_fallback():
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

        const card = {
          id: "fomc_tone",
          label: "FOMC Policy Read",
          status: "context",
          latest_tone: null,
          ism_policy_context: {
            combined_pressure: "inflation_caution",
            growth_pressure: "less_easing_pressure",
            inflation_pressure: "elevated",
            supply_pressure: "normal",
            period: "2026-06-01",
            version: "ism_macro_signal_v1",
          },
        };

        const html = hooks.renderFomcToneCard(card);

        console.log(JSON.stringify({
          hasIsmPolicyContext: html.indexOf("ism-policy-context") !== -1,
          hasCombinedPressure: html.indexOf("Combined Pressure") !== -1,
          hasGrowthPressure: html.indexOf("Growth Pressure") !== -1,
          hasInflationPressure: html.indexOf("Inflation Pressure") !== -1,
          hasSupplyPressure: html.indexOf("Supply Pressure") !== -1,
          hasInflationCaution: html.indexOf("Inflation Caution") !== -1,
          noToneUnavailable: html.indexOf("Tone unavailable") === -1,
          noToneBadge: html.indexOf("fomc-tone-badge") === -1,
          notMissingCard: html.indexOf("m2-card-missing") === -1,
          isContextCard: html.indexOf("m2-card m2-card-context") !== -1,
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

    assert payload["hasIsmPolicyContext"] is False
    assert payload["hasCombinedPressure"] is False
    assert payload["hasGrowthPressure"] is False
    assert payload["hasInflationPressure"] is False
    assert payload["hasSupplyPressure"] is False
    assert payload["hasInflationCaution"] is False
    assert payload["noToneUnavailable"] is False
    assert payload["noToneBadge"] is True
    assert payload["notMissingCard"] is False
    assert payload["isContextCard"] is False


def test_macro_dashboard_js_renders_policy_pressure_in_ism_card():
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
        global.document = { getElementById: (id) => elements[id] };
        global.fetch = async () => ({
          ok: true,
          status: 200,
          json: async () => ({ markets: [] }),
        });

        vm.runInThisContext(fs.readFileSync("static/macro-dashboard.js", "utf8"));
        const html = window.__macroDashboardTestHooks.renderIsmPolicyPressure({
          combined_pressure: "inflation_caution",
          growth_pressure: "less_easing_pressure",
          inflation_pressure: "elevated",
          supply_pressure: "normal",
        });

        console.log(JSON.stringify({
          hasContainer: html.indexOf("ism-policy-pressure") !== -1,
          hasTitle: html.indexOf("Policy Pressure") !== -1,
          hasCombined: html.indexOf("Combined Pressure") !== -1,
          hasGrowth: html.indexOf("Growth Pressure") !== -1,
          hasInflation: html.indexOf("Inflation Pressure") !== -1,
          hasSupply: html.indexOf("Supply Pressure") !== -1,
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

    assert all(payload.values())


def test_macro_dashboard_js_renders_bias_evidence_strip():
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

        const evidence = {
          version: "growth_cycle_bias_v2",
          status: "pending_inputs",
          bias: null,
          ism_contribution: "supports_long",
          components: {
            ism_manufacturing: "supports_growth",
            ism_services: "unavailable",
            labor: "unavailable",
          },
          missing_inputs: ["ISM Services", "Labor trend"],
          reasons: ["Manufacturing growth evidence is supportive but lacks cross-validation"],
        };

        const availableEvidence = {
          version: "growth_cycle_bias_v3",
          status: "available",
          bias: "long",
          scope: "ism_manufacturing",
          confirmation_status: "partial",
          ism_contribution: "supports_long",
          components: {
            ism_manufacturing: "supports_growth",
            ism_services: "supports_growth",
            labor: "supports_growth",
          },
          missing_inputs: [],
          reasons: ["All three sectors support a long bias"],
        };

        const pendingHtml = hooks.renderBiasEvidenceStrip(evidence);
        const availableHtml = hooks.renderBiasEvidenceStrip(availableEvidence);

        console.log(JSON.stringify({
          pendingHasStrip: pendingHtml.indexOf("bias-evidence-strip") !== -1,
          pendingShowsPending: pendingHtml.indexOf("Pending Inputs") !== -1,
          pendingHasM2LevelRow: pendingHtml.indexOf("m2-level-row") !== -1,
          pendingHasIsmContribution: pendingHtml.indexOf("ISM Contribution") !== -1,
          pendingHasComponents: pendingHtml.indexOf("bias-components") !== -1,
          pendingHasManufacturingSupport: pendingHtml.indexOf("Supports Growth") !== -1,
          pendingHasManufacturingLabel: pendingHtml.indexOf("Manufacturing") !== -1,
          pendingHasServices: pendingHtml.indexOf("Services") !== -1,
          pendingHasLabor: pendingHtml.indexOf("Labor") !== -1,
          pendingHasUnavailable: pendingHtml.indexOf("Unavailable") !== -1,
          pendingHasReasons: pendingHtml.indexOf("bias-reasons") !== -1,
          pendingHasReasonText: pendingHtml.indexOf("cross-validation") !== -1,
          pendingNotBiasAvailable: pendingHtml.indexOf("bias-available") === -1,
          pendingIsBiasPending: pendingHtml.indexOf("bias-pending") !== -1,
          availableShowsLong: availableHtml.indexOf("Long") !== -1,
          availableIsBiasAvailable: availableHtml.indexOf("bias-available") !== -1,
          availableShowsMacroBias: availableHtml.indexOf("Macro Portfolio Bias") !== -1,
          availableShowsConfirmation: availableHtml.indexOf("Confirmation Status") !== -1,
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

    assert payload["pendingHasStrip"] is True
    assert payload["pendingShowsPending"] is True
    assert payload["pendingHasM2LevelRow"] is True
    assert payload["pendingHasIsmContribution"] is True
    assert payload["pendingHasComponents"] is True
    assert payload["pendingHasManufacturingSupport"] is True
    assert payload["pendingHasManufacturingLabel"] is True
    assert payload["pendingHasServices"] is True
    assert payload["pendingHasLabor"] is True
    assert payload["pendingHasUnavailable"] is True
    assert payload["pendingHasReasons"] is True
    assert payload["pendingHasReasonText"] is True
    assert payload["pendingNotBiasAvailable"] is True
    assert payload["pendingIsBiasPending"] is True
    assert payload["availableShowsLong"] is True
    assert payload["availableIsBiasAvailable"] is True
    assert payload["availableShowsMacroBias"] is True
    assert payload["availableShowsConfirmation"] is True


# --- Market Setup Decision Hero Tests ---


def test_market_setup_hero_aligned_signal():
    script = textwrap.dedent("""\
        const fs = require("fs");
        const vm = require("vm");

        const elements = {
          dashboardStatus: {},
          marketGrid: { innerHTML: "", querySelectorAll: () => [] },
          marketDetail: { innerHTML: "" },
          marketSetup: { innerHTML: "", querySelectorAll: () => [] },
          marketSetupStatus: { textContent: "" },
        };

        global.window = { __MEOWSTREET_TEST__: true };
        global.document = {
          getElementById: (id) => elements[id],
          querySelectorAll: () => [],
        };
        global.fetch = async () => ({
          ok: true,
          status: 200,
          json: async () => ({ markets: [] }),
        });

        vm.runInThisContext(fs.readFileSync("static/macro-dashboard.js", "utf8"));
        const hooks = window.__macroDashboardTestHooks;

        const setup = {
          version: "market_setup_v1",
          status: "available",
          as_of: "2026-06-17",
          market_environment: { state: "bull_market" },
          expected_growth: { state: "expansion" },
          financial_conditions: { state: "accommodative" },
          policy_response: { state: "restrictive" },
          setup_type: "growth_and_conditions_aligned",
          portfolio_posture: "long",
          agreements: ["Growth and conditions are aligned"],
          conflicts: [],
          missing_inputs: [],
          pending_confirmations: ["ISM Services", "Labor trend"],
          market_conclusion: {
            code: "qualified_long_candidate",
            title: "Qualified Long Candidate",
            summary: "Growth is slowing but conditions remain supportive.",
          },
          portfolio_guidance: {
            posture: "long",
            summary: "Maintain long posture",
            actions: ["Maintain broad-market long exposure"],
            avoid: ["Avoid adding defensive positions"],
          },
          evidence_chain: [{
            title: "Growth Trend",
            finding: "Growth is slowing but above trend",
            implication: "Supports moderate long exposure",
            tone: "constructive",
            evidence: ["ISM Manufacturing at 52.3"],
            evidence_links: ["ism_manufacturing"],
          }],
          conviction_limits: {
            summary: "Some offsets limit conviction",
            offsets: [{ finding: "Bull market intact", effect: "Offset", evidence_links: ["market_phase"] }],
          },
          confirmation_conditions: {
            more_defensive: ["ISM drops below 50"],
            more_constructive: ["Services sector confirms expansion"],
          },
        };

        const pr = hooks.buildMarketSetupPresentation(setup);

        console.log(JSON.stringify({
          signalAgreement: pr.signalAgreement,
          conclusionTitle: pr.conclusionTitle,
          asOf: pr.asOf,
          hasEvidence: pr.primaryEvidence.length === 1,
          hasOffsets: pr.offsets.length === 1,
          hasDoActions: pr.doActions.length === 1,
          hasAvoidActions: pr.avoidActions.length === 1,
          hasPending: pr.pendingConfirmations.length === 2,
          marketPhaseSentiment: hooks.stateSentimentClass(pr.marketPhase),
          heroHtml: hooks.renderDecisionHero(pr),
          detailedHtml: hooks.renderDetailedReasoning(pr),
          offsetLinks: pr.offsets[0].links,
        }));
    """)

    result = subprocess.run(
        ["node", "-e", script],
        cwd=ROOT,
        capture_output=True,
        check=True,
        text=True,
    )
    payload = json.loads(result.stdout)

    assert payload["signalAgreement"] == "aligned"
    assert payload["conclusionTitle"] == "Qualified Long Candidate"
    assert payload["asOf"] == "2026-06-17"
    assert payload["hasEvidence"] is True
    assert payload["hasOffsets"] is True
    assert payload["offsetLinks"] == ["market_phase"]
    assert payload["hasDoActions"] is True
    assert payload["hasAvoidActions"] is True
    assert payload["hasPending"] is True
    assert payload["marketPhaseSentiment"] == "constructive"
    assert "ms-hero" in payload["heroHtml"]
    assert "ms-state-strip" in payload["heroHtml"]
    assert "ms-state-cell" in payload["heroHtml"]
    assert "Qualified Long Candidate" in payload["heroHtml"]
    assert "Evidence through" in payload["heroHtml"]
    assert "Practical Guidance" in payload["heroHtml"]
    assert "Conviction limited by 1 offset" in payload["heroHtml"]
    assert "Bull Market" in payload["heroHtml"]
    assert "bull_market" not in payload["heroHtml"]
    assert "ms-detailed" in payload["detailedHtml"]
    assert "ms-evidence-card" in payload["detailedHtml"]
    assert "ms-change-view" in payload["detailedHtml"]
    assert "ms-conviction" in payload["detailedHtml"]
    assert "ms-evidence-link" in payload["detailedHtml"]
    assert "evidence-market-phase" in payload["detailedHtml"]
    assert "ms-pending-confirmations" in payload["detailedHtml"]
    assert "ms-component-data" in payload["detailedHtml"]


def test_market_setup_hero_preserves_compound_macro_conclusion():
    script = textwrap.dedent("""\
        const fs = require("fs");
        const vm = require("vm");
        const elements = {
          dashboardStatus: {},
          marketGrid: { innerHTML: "", querySelectorAll: () => [] },
          marketDetail: { innerHTML: "" },
          marketSetup: { innerHTML: "", querySelectorAll: () => [] },
          marketSetupStatus: { textContent: "" },
        };
        global.window = { __MEOWSTREET_TEST__: true };
        global.document = {
          getElementById: (id) => elements[id],
          querySelectorAll: () => [],
        };
        global.fetch = async () => ({ ok: true, status: 200, json: async () => ({ markets: [] }) });
        vm.runInThisContext(fs.readFileSync("static/macro-dashboard.js", "utf8"));
        const hooks = window.__macroDashboardTestHooks;
        const presentation = hooks.buildMarketSetupPresentation({
          status: "available",
          as_of: "2026-06-01",
          market_environment: { state: "bull_market" },
          setup_type: "contraction_risk_aligned",
          portfolio_posture: "neutral",
          agreements: [],
          conflicts: ["Bull market conflicts with contraction risk"],
          missing_inputs: [],
          market_conclusion: {
            code: "macro_risk_rising_bull_intact",
            title: "Macro risk rising; bull market intact",
            summary: "Macro risk is rising, but the bull phase remains intact."
          },
          portfolio_guidance: { actions: ["Maintain balanced exposure"], avoid: [] },
          evidence_chain: [],
          conviction_limits: {},
          confirmation_conditions: {}
        });
        const html = hooks.renderDecisionHero(presentation);
        console.log(JSON.stringify({
          headline: html.includes("Macro risk rising; bull market intact"),
          phase: html.includes("Bull Market"),
          setup: html.includes("Contraction Risk Aligned"),
          posture: html.includes("Neutral")
        }));
    """)
    result = subprocess.run(
        ["node", "-e", script], cwd=ROOT, capture_output=True, check=True, text=True
    )
    assert all(json.loads(result.stdout).values())


def test_market_setup_hero_conflicting_signal():
    script = textwrap.dedent("""\
        const fs = require("fs");
        const vm = require("vm");

        const elements = {
          dashboardStatus: {},
          marketGrid: { innerHTML: "", querySelectorAll: () => [] },
          marketDetail: { innerHTML: "" },
          marketSetup: { innerHTML: "", querySelectorAll: () => [] },
          marketSetupStatus: { textContent: "" },
        };

        global.window = { __MEOWSTREET_TEST__: true };
        global.document = {
          getElementById: (id) => elements[id],
          querySelectorAll: () => [],
        };
        global.fetch = async () => ({
          ok: true,
          status: 200,
          json: async () => ({ markets: [] }),
        });

        vm.runInThisContext(fs.readFileSync("static/macro-dashboard.js", "utf8"));
        const hooks = window.__macroDashboardTestHooks;

        const pr = hooks.buildMarketSetupPresentation({
          status: "available",
          as_of: "2026-06-17",
          market_environment: { state: "bull_market" },
          setup_type: "conflicting_evidence",
          portfolio_posture: "neutral",
          agreements: [],
          conflicts: ["Growth slowing but conditions supportive"],
          missing_inputs: [],
          pending_confirmations: [],
          market_conclusion: { code: "conflicting_evidence", title: "Conflicting Evidence", summary: "Mixed signals" },
          portfolio_guidance: { actions: ["Be selective"] },
          evidence_chain: [{ title: "Risk", finding: "Mixed signals", tone: "caution" }],
          conviction_limits: {},
          confirmation_conditions: {},
        });

        const heroHtml = hooks.renderDecisionHero(pr);

        console.log(JSON.stringify({
          signalAgreement: pr.signalAgreement,
          hasConflicts: heroHtml.indexOf("Offsets &amp; Conflicts") !== -1,
          hasPrimary: heroHtml.indexOf("Primary Evidence") !== -1,
        }));
    """)

    result = subprocess.run(
        ["node", "-e", script],
        cwd=ROOT,
        capture_output=True,
        check=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    assert payload["signalAgreement"] == "conflicting"
    assert payload["hasConflicts"] is True
    assert payload["hasPrimary"] is True


def test_market_setup_hero_incomplete_state():
    script = textwrap.dedent("""\
        const fs = require("fs");
        const vm = require("vm");

        const elements = {
          dashboardStatus: {},
          marketGrid: { innerHTML: "", querySelectorAll: () => [] },
          marketDetail: { innerHTML: "" },
          marketSetup: { innerHTML: "", querySelectorAll: () => [] },
          marketSetupStatus: { textContent: "" },
        };

        global.window = { __MEOWSTREET_TEST__: true };
        global.document = {
          getElementById: (id) => elements[id],
          querySelectorAll: () => [],
        };
        global.fetch = async () => ({
          ok: true,
          status: 200,
          json: async () => ({ markets: [] }),
        });

        vm.runInThisContext(fs.readFileSync("static/macro-dashboard.js", "utf8"));
        const hooks = window.__macroDashboardTestHooks;

        const pr = hooks.buildMarketSetupPresentation({
          status: "partial",
          as_of: "2026-06-17",
          market_environment: { state: "bull_market" },
          setup_type: "insufficient_data",
          portfolio_posture: "neutral",
          agreements: [],
          conflicts: [],
          missing_inputs: ["ISM manufacturing signal", "US rates data"],
          pending_confirmations: [],
          market_conclusion: { code: "insufficient_evidence", title: "Insufficient Evidence", summary: "Partial data" },
          portfolio_guidance: {
            posture: "neutral",
            summary: "Conflicting signals or insufficient evidence support a neutral posture",
            actions: ["Maintain balanced exposure with no net directional bias"],
            avoid: ["Building large directional positions without clearer alignment"],
          },
          evidence_chain: [],
          conviction_limits: {},
          confirmation_conditions: {},
        });

        const heroHtml = hooks.renderDecisionHero(pr);

        console.log(JSON.stringify({
          signalAgreement: pr.signalAgreement,
          hasInsufficientBadge: heroHtml.indexOf("Insufficient Data") !== -1,
          hasMissingInputs: heroHtml.indexOf("ISM manufacturing signal") !== -1,
          hasNoGuidance: heroHtml.indexOf("Practical Guidance") === -1,
        }));
    """)

    result = subprocess.run(
        ["node", "-e", script],
        cwd=ROOT,
        capture_output=True,
        check=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    assert payload["signalAgreement"] == "incomplete"
    assert payload["hasInsufficientBadge"] is True
    assert payload["hasMissingInputs"] is True
    assert payload["hasNoGuidance"] is True


def test_market_setup_hero_insufficient_state():
    script = textwrap.dedent("""\
        const fs = require("fs");
        const vm = require("vm");

        const elements = {
          dashboardStatus: {},
          marketGrid: { innerHTML: "", querySelectorAll: () => [] },
          marketDetail: { innerHTML: "" },
          marketSetup: { innerHTML: "", querySelectorAll: () => [] },
          marketSetupStatus: { textContent: "" },
        };

        global.window = { __MEOWSTREET_TEST__: true };
        global.document = {
          getElementById: (id) => elements[id],
          querySelectorAll: () => [],
        };
        global.fetch = async () => ({
          ok: true,
          status: 200,
          json: async () => ({ markets: [] }),
        });

        vm.runInThisContext(fs.readFileSync("static/macro-dashboard.js", "utf8"));
        const hooks = window.__macroDashboardTestHooks;

        const pr = hooks.buildMarketSetupPresentation({
          status: "insufficient",
          market_environment: {},
          setup_type: "insufficient_data",
          portfolio_posture: null,
          agreements: [],
          conflicts: [],
          missing_inputs: ["All inputs unavailable"],
          pending_confirmations: [],
          market_conclusion: { code: "insufficient_evidence" },
          portfolio_guidance: {},
          evidence_chain: [],
          conviction_limits: {},
          confirmation_conditions: {},
        });

        const heroHtml = hooks.renderDecisionHero(pr);

        console.log(JSON.stringify({
          signalAgreement: pr.signalAgreement,
          hasInsufficientBadge: heroHtml.indexOf("Insufficient Data") !== -1,
          hasRequiredInputs: heroHtml.indexOf("Required Inputs") !== -1,
        }));
    """)

    result = subprocess.run(
        ["node", "-e", script],
        cwd=ROOT,
        capture_output=True,
        check=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    assert payload["signalAgreement"] == "incomplete"
    assert payload["hasInsufficientBadge"] is True
    assert payload["hasRequiredInputs"] is True


def test_market_setup_hero_error_state():
    script = textwrap.dedent("""\
        const fs = require("fs");
        const vm = require("vm");

        const elements = {
          dashboardStatus: {},
          marketGrid: { innerHTML: "", querySelectorAll: () => [] },
          marketDetail: { innerHTML: "" },
          marketSetup: { innerHTML: "", querySelectorAll: () => [] },
          marketSetupStatus: { textContent: "" },
        };

        global.window = { __MEOWSTREET_TEST__: true };
        global.document = {
          getElementById: (id) => elements[id],
          querySelectorAll: () => [],
        };
        global.fetch = async () => ({
          ok: true,
          status: 200,
          json: async () => ({ markets: [] }),
        });

        vm.runInThisContext(fs.readFileSync("static/macro-dashboard.js", "utf8"));
        const hooks = window.__macroDashboardTestHooks;

        const errorHtml = hooks.renderMarketSetupError("Network error");

        console.log(JSON.stringify({
          hasError: errorHtml.indexOf("ms-error") !== -1,
          hasRetryBtn: errorHtml.indexOf("Retry Market Setup") !== -1,
          hasErrorMessage: errorHtml.indexOf("Network error") !== -1,
        }));
    """)

    result = subprocess.run(
        ["node", "-e", script],
        cwd=ROOT,
        capture_output=True,
        check=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    assert payload["hasError"] is True
    assert payload["hasRetryBtn"] is True
    assert payload["hasErrorMessage"] is True


def test_market_setup_hero_loading_state():
    script = textwrap.dedent("""\
        const fs = require("fs");
        const vm = require("vm");

        const elements = {
          dashboardStatus: {},
          marketGrid: { innerHTML: "", querySelectorAll: () => [] },
          marketDetail: { innerHTML: "" },
          marketSetup: { innerHTML: "", querySelectorAll: () => [] },
          marketSetupStatus: { textContent: "" },
        };

        global.window = { __MEOWSTREET_TEST__: true };
        global.document = {
          getElementById: (id) => elements[id],
          querySelectorAll: () => [],
        };
        global.fetch = async () => ({
          ok: true,
          status: 200,
          json: async () => ({ markets: [] }),
        });

        vm.runInThisContext(fs.readFileSync("static/macro-dashboard.js", "utf8"));
        const hooks = window.__macroDashboardTestHooks;

        const loadingHtml = hooks.renderMarketSetupLoading();

        console.log(JSON.stringify({
          hasLoading: loadingHtml.indexOf("Loading market setup") !== -1,
          hasBusy: loadingHtml.indexOf("aria-busy") !== -1,
        }));
    """)

    result = subprocess.run(
        ["node", "-e", script],
        cwd=ROOT,
        capture_output=True,
        check=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    assert payload["hasLoading"] is True
    assert payload["hasBusy"] is True


def test_market_setup_hero_state_sentiment_class():
    script = textwrap.dedent("""\
        const fs = require("fs");
        const vm = require("vm");

        const elements = {
          dashboardStatus: {},
          marketGrid: { innerHTML: "", querySelectorAll: () => [] },
          marketDetail: { innerHTML: "" },
          marketSetup: { innerHTML: "", querySelectorAll: () => [] },
          marketSetupStatus: { textContent: "" },
        };

        global.window = { __MEOWSTREET_TEST__: true };
        global.document = {
          getElementById: (id) => elements[id],
          querySelectorAll: () => [],
        };
        global.fetch = async () => ({
          ok: true,
          status: 200,
          json: async () => ({ markets: [] }),
        });

        vm.runInThisContext(fs.readFileSync("static/macro-dashboard.js", "utf8"));
        const hooks = window.__macroDashboardTestHooks;

        console.log(JSON.stringify({
          constructive: hooks.stateSentimentClass("bull_market"),
          defensive: hooks.stateSentimentClass("bear_market"),
          caution: hooks.stateSentimentClass("conflict"),
          alignedSetup: hooks.stateSentimentClass("growth_and_conditions_aligned"),
          contractionSetup: hooks.stateSentimentClass("contraction_risk_aligned"),
          conflictSetup: hooks.stateSentimentClass("growth_liquidity_conflict"),
          longPosture: hooks.stateSentimentClass("long"),
          shortPosture: hooks.stateSentimentClass("short_or_neutral"),
          neutral: hooks.stateSentimentClass("unknown_value"),
          nullValue: hooks.stateSentimentClass(null),
        }));
    """)

    result = subprocess.run(
        ["node", "-e", script],
        cwd=ROOT,
        capture_output=True,
        check=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    assert payload["constructive"] == "constructive"
    assert payload["defensive"] == "defensive"
    assert payload["caution"] == "caution"
    assert payload["alignedSetup"] == "constructive"
    assert payload["contractionSetup"] == "defensive"
    assert payload["conflictSetup"] == "caution"
    assert payload["longPosture"] == "constructive"
    assert payload["shortPosture"] == "defensive"
    assert payload["neutral"] == "neutral-state"
    assert payload["nullValue"] == "neutral-state"


def test_market_setup_component_sentiments_use_renderable_classes():
    script = textwrap.dedent("""\
        const fs = require("fs");
        const vm = require("vm");

        const elements = {
          dashboardStatus: {},
          marketGrid: { innerHTML: "", querySelectorAll: () => [] },
          marketDetail: { innerHTML: "" },
          marketSetup: { innerHTML: "", querySelectorAll: () => [] },
          marketSetupStatus: { textContent: "" },
        };

        global.window = { __MEOWSTREET_TEST__: true };
        global.document = {
          getElementById: (id) => elements[id],
          querySelectorAll: () => [],
        };
        global.fetch = async () => ({
          ok: true,
          status: 200,
          json: async () => ({ markets: [] }),
        });

        vm.runInThisContext(fs.readFileSync("static/macro-dashboard.js", "utf8"));
        const hooks = window.__macroDashboardTestHooks;
        const presentation = hooks.buildMarketSetupPresentation({
          market_environment: { state: "bull_market" },
          expected_growth: { state: "expansion_rising" },
          financial_conditions: { state: "confirms_contraction_risk" },
          policy_response: { state: "policy_liquidity_conflict" },
        });

        console.log(JSON.stringify({
          market: presentation.components.marketEnvironment.sentiment,
          growth: presentation.components.expectedGrowth.sentiment,
          conditions: presentation.components.financialConditions.sentiment,
          policy: presentation.components.policyResponse.sentiment,
        }));
    """)

    result = subprocess.run(
        ["node", "-e", script],
        cwd=ROOT,
        capture_output=True,
        check=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    assert payload == {
        "market": "constructive",
        "growth": "constructive",
        "conditions": "defensive",
        "policy": "caution",
    }


def test_market_setup_hero_compute_signal_agreement():
    script = textwrap.dedent("""\
        const fs = require("fs");
        const vm = require("vm");

        const elements = {
          dashboardStatus: {},
          marketGrid: { innerHTML: "", querySelectorAll: () => [] },
          marketDetail: { innerHTML: "" },
          marketSetup: { innerHTML: "", querySelectorAll: () => [] },
          marketSetupStatus: { textContent: "" },
        };

        global.window = { __MEOWSTREET_TEST__: true };
        global.document = {
          getElementById: (id) => elements[id],
          querySelectorAll: () => [],
        };
        global.fetch = async () => ({
          ok: true,
          status: 200,
          json: async () => ({ markets: [] }),
        });

        vm.runInThisContext(fs.readFileSync("static/macro-dashboard.js", "utf8"));
        const hooks = window.__macroDashboardTestHooks;

        console.log(JSON.stringify({
          aligned: hooks.computeSignalAgreement({ agreements: ["ok"], conflicts: [], missing_inputs: [], status: "available" }),
          conflicting: hooks.computeSignalAgreement({ agreements: ["ok"], conflicts: ["bad"], missing_inputs: [], status: "available" }),
          incomplete: hooks.computeSignalAgreement({ agreements: [], conflicts: [], missing_inputs: ["x"], status: "partial" }),
          mixed: hooks.computeSignalAgreement({ agreements: [], conflicts: [], missing_inputs: [], status: "available" }),
        }));
    """)

    result = subprocess.run(
        ["node", "-e", script],
        cwd=ROOT,
        capture_output=True,
        check=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    assert payload["aligned"] == "aligned"
    assert payload["conflicting"] == "conflicting"
    assert payload["incomplete"] == "incomplete"
    assert payload["mixed"] == "mixed"


def test_market_setup_evidence_links_are_semantic_deep_links():
    script = textwrap.dedent("""\
        const fs = require("fs");
        const vm = require("vm");

        const elements = {
          dashboardStatus: {},
          marketGrid: { innerHTML: "", querySelectorAll: () => [] },
          marketDetail: { innerHTML: "" },
          marketSetup: { innerHTML: "", querySelectorAll: () => [] },
          marketSetupStatus: { textContent: "" },
        };

        global.window = { __MEOWSTREET_TEST__: true };
        global.document = {
          getElementById: (id) => elements[id],
          querySelectorAll: () => [],
        };
        global.fetch = async () => ({
          ok: true,
          status: 200,
          json: async () => ({ markets: [] }),
        });

        vm.runInThisContext(fs.readFileSync("static/macro-dashboard.js", "utf8"));
        const hooks = window.__macroDashboardTestHooks;
        const evidenceTypes = [
          "market_phase",
          "ism_manufacturing",
          "yield_curve",
          "credit_conditions",
          "real_rate_risk",
          "vix",
          "fomc_policy",
          "m2_money_supply",
        ];

        console.log(JSON.stringify({
          targetIds: evidenceTypes.map((link) => hooks.evidenceTargetId(link)),
          anchor: hooks.renderEvidenceLink("yield_curve"),
          unknownTarget: hooks.evidenceTargetId("unknown_evidence"),
          unknownLink: hooks.renderEvidenceLink("unknown_evidence"),
        }));
    """)

    result = subprocess.run(
        ["node", "-e", script], cwd=ROOT, capture_output=True, text=True
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["targetIds"] == [
        "evidence-market-phase",
        "evidence-ism-manufacturing",
        "evidence-yield-curve",
        "evidence-credit-conditions",
        "evidence-real-rate-risk",
        "evidence-vix",
        "evidence-fomc-policy",
        "evidence-m2-money-supply",
    ]
    assert payload["anchor"] == (
        '<a class="ms-evidence-link" href="#evidence-yield-curve" '
        'data-evidence-target="evidence-yield-curve">Yield Curve</a>'
    )
    assert payload["unknownTarget"] is None
    assert payload["unknownLink"] == ""


def test_market_setup_evidence_navigation_updates_hash_and_respects_motion():
    script = textwrap.dedent("""\
        const fs = require("fs");
        const vm = require("vm");

        const target = {
          scrollCalls: [],
          classList: { add: () => {}, remove: () => {} },
          scrollIntoView(options) { this.scrollCalls.push(options); },
        };
        const link = {
          dataset: { evidenceTarget: "evidence-vix" },
          addEventListener(name, callback) { this.listener = callback; },
        };
        const section = { querySelectorAll: () => [link] };
        const elements = {
          dashboardStatus: {},
          marketGrid: { innerHTML: "", querySelectorAll: () => [] },
          marketDetail: { innerHTML: "" },
          marketSetup: { innerHTML: "", querySelectorAll: () => [] },
          marketSetupStatus: { textContent: "" },
          "evidence-vix": target,
        };
        let reduceMotion = false;
        const hashes = [];

        global.window = {
          __MEOWSTREET_TEST__: true,
          matchMedia: () => ({ matches: reduceMotion }),
        };
        global.history = {
          replaceState: (_state, _title, hash) => hashes.push(hash),
        };
        global.document = {
          getElementById: (id) => elements[id],
          querySelectorAll: () => [],
        };
        global.fetch = async () => ({
          ok: true,
          status: 200,
          json: async () => ({ markets: [] }),
        });

        vm.runInThisContext(fs.readFileSync("static/macro-dashboard.js", "utf8"));
        const hooks = window.__macroDashboardTestHooks;
        hooks.bindEvidenceLinks(section);
        let prevented = 0;
        link.listener({ preventDefault: () => { prevented += 1; } });
        reduceMotion = true;
        link.listener({ preventDefault: () => { prevented += 1; } });

        console.log(JSON.stringify({
          hashes,
          prevented,
          scrollCalls: target.scrollCalls,
        }));
    """)

    result = subprocess.run(
        ["node", "-e", script], cwd=ROOT, capture_output=True, text=True
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["hashes"] == ["#evidence-vix", "#evidence-vix"]
    assert payload["prevented"] == 2
    assert payload["scrollCalls"] == [
        {"behavior": "smooth", "block": "start"},
        {"behavior": "auto", "block": "start"},
    ]


def test_macro_dashboard_renders_stable_evidence_target_ids():
    js = STATIC_JS.read_text()
    target_ids = {
        "evidence-market-phase",
        "evidence-ism-manufacturing",
        "evidence-yield-curve",
        "evidence-credit-conditions",
        "evidence-real-rate-risk",
        "evidence-vix",
        "evidence-fomc-policy",
        "evidence-m2-money-supply",
    }

    assert all(js.count(target_id) >= 2 for target_id in target_ids)
    assert '<span class="ms-evidence-link"' not in js


def test_market_setup_css_styles_evidence_link_layout_and_keyboard_focus():
    css = STATIC_CSS.read_text()

    assert ".ms-evidence-links" in css
    assert ".ms-evidence-link:focus-visible" in css
    assert "outline: 2px solid #3B5F85;" in css


def test_market_setup_css_has_hero_styles():
    css = STATIC_CSS.read_text()
    assert ".ms-hero" in css
    assert ".ms-state-strip" in css
    assert ".ms-state-cell" in css
    assert ".ms-conflict-row" in css
    assert ".ms-evidence-item" in css
    assert ".ms-evidence-card" in css
    assert ".ms-detailed" in css
    assert ".ms-change-view" in css
    assert ".ms-conviction" in css
    assert ".ms-component-data" in css
    assert ".ms-error" in css
    assert ".ms-evidence-link" in css
    assert ".ms-retry-btn" in css
    assert ".skip-link" in css
    assert ".skip-link:focus-visible" in css
    assert ".evidence-target" in css
    assert "@media (prefers-reduced-motion: reduce)" in css


def test_macro_dashboard_html_has_benchmark_indices_heading():
    html = (ROOT / "static" / "macro-dashboard.html").read_text()
    assert "<h2>Benchmark Indices</h2>" in html


def test_macro_dashboard_html_has_skip_link():
    html = (ROOT / "static" / "macro-dashboard.html").read_text()
    assert 'class="skip-link"' in html
    assert 'href="#macroDashboardApp"' in html
    assert "Skip to main content" in html


def test_macro_dashboard_html_loading_copy_uses_ellipsis_character():
    html = (ROOT / "static" / "macro-dashboard.html").read_text()
    assert "Loading market setup\N{HORIZONTAL ELLIPSIS}" in html
    assert "Loading market setup..." not in html


def test_market_setup_load_lifecycle_has_explicit_loading_state():
    js = STATIC_JS.read_text()
    assert "marketSetupLoading: false" in js
    assert "state.marketSetupLoading = true" in js
    assert "state.marketSetupLoading = false" in js
    assert "if (state.marketSetupLoading)" in js


def test_market_setup_detailed_reasoning_uses_css_classes_not_inline_styles():
    js = STATIC_JS.read_text()
    source = js[
        js.index("function renderDetailedReasoning") : js.index(
            "function renderMarketSetupLoading"
        )
    ]
    assert 'style="' not in source
    assert "ms-evidence-links" in source
    assert "ms-missing-inputs" in source

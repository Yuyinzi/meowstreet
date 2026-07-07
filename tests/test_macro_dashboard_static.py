from pathlib import Path
import json
import subprocess
import textwrap


ROOT = Path(__file__).resolve().parents[1]


def test_macro_dashboard_html_links_assets_and_app_root():
    html = (ROOT / "static" / "macro-dashboard.html").read_text()

    assert 'id="macroDashboardApp"' in html
    assert 'href="/macro-dashboard.css"' in html
    assert 'src="/macro-dashboard.js"' in html


def test_macro_dashboard_html_embeds_us_rates_liquidity_section():
    html = (ROOT / "static" / "macro-dashboard.html").read_text()

    assert 'id="usRatesLiquidity"' in html
    assert "US Rates / Liquidity" in html
    assert "Import-backed" in html


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


def test_macro_dashboard_html_keeps_rates_liquidity_mount_without_mock_values():
    html = (ROOT / "static" / "macro-dashboard.html").read_text()

    assert 'id="usRatesLiquidity"' in html
    assert "US Rates / Liquidity" in html
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
    assert "detail.hidden = true" in js
    assert "detail.hidden = false" in js


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
    assert "renderGdpRelationshipDetail" in js
    assert (
        "state.selectedRelationshipId = state.gdpRelationships[0]?.relationship_id || null"
        not in js
    )
    assert "|| state.gdpRelationships[0]" not in js
    assert "state.selectedRelationshipId === button.dataset.relationshipId" in js
    assert (
        '${state.selectedRelationshipId ? `<div class="gdp-detail" id="gdpRelationshipDetail"></div>` : ""}'
        in js
    )
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
    assert "renderDetail();" in js
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
    assert "renderUsRatesLiquidityDetail" in js
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
    assert 'id="usRatesLiquidityDetail"' in js
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


def test_macro_dashboard_css_contains_credit_interpretation_styles():
    css = (ROOT / "static" / "macro-dashboard.css").read_text()

    assert ".credit-interpretation-strip" in css
    assert ".credit-interpretation-healthy" in css
    assert ".credit-interpretation-weak-credit-warning" in css
    assert ".credit-interpretation-risk-rising" in css
    assert ".credit-interpretation-crisis-stress" in css

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


def test_survey_synthesis_mount_is_between_market_setup_and_benchmarks():
    html = (ROOT / "static" / "macro-dashboard.html").read_text()

    market_setup = html.index('id="marketSetup"')
    survey_synthesis = html.index('id="surveySynthesis"')
    benchmarks = html.index('aria-label="Benchmark market phase overview"')
    growth_cycle = html.index('id="growthCycle"')

    assert market_setup < survey_synthesis < benchmarks < growth_cycle
    assert 'aria-label="ISM survey synthesis decision layer"' in html
    assert (
        'aria-live="polite"'
        in html[survey_synthesis : html.index(">", survey_synthesis)]
    )
    assert (
        'aria-atomic="true"'
        in html[survey_synthesis : html.index(">", survey_synthesis)]
    )
    assert "Loading survey synthesis" in html
    assert html.count("<h2>Survey Synthesis</h2>") == 1


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
    assert "attachRelationshipChartTooltip" in js
    assert "window.__chartHelpers" in js
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


def test_macro_dashboard_js_removes_gdp_relationship_panel():
    js = (ROOT / "static" / "macro-dashboard.js").read_text()

    assert 'fetch("/api/macro-dashboard/gdp-relationships")' not in js
    assert (
        "fetch(`/api/macro-dashboard/gdp-relationships/${encodeURIComponent(relationshipId)}`)"
        not in js
    )
    assert "gdpRelationshipDetailsById" not in js
    assert "loadGdpRelationshipDetail" not in js
    assert "GDP / Market Relationship" not in js
    assert "renderGdpRelationshipOverview" not in js
    assert "renderGdpDetailInPanel" not in js
    assert "state.selectedRelationshipId" not in js
    assert "gdpRelationships" not in js
    assert "gdpRelationship" not in js

    assert "function fmtCorrelationPercent(" in js
    assert "chart-axis" in js
    assert "series[0].label || series[0].date" in js


def test_macro_dashboard_js_has_mock_lag_comparison_metrics():
    js = (ROOT / "static" / "macro-dashboard.js").read_text()

    assert "lag_correlations" not in js
    assert "renderLagComparison" not in js
    assert "Lag comparison" not in js
    assert "method_primary" not in js


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
    assert ".relationship-chart" in css
    assert ".relationship-legend" in css
    assert ".relationship-chart-wide" in css
    assert ".chart-axis" in css
    assert ".chart-grid" in css
    assert ".chart-y-tick" in css
    assert ".signal-status" in css
    assert "background: transparent;" in css
    assert "text-transform: uppercase;" in css
    assert ".signal-usable" in css
    assert ".signal-caution" in css
    assert ".signal-weak" in css
    assert ".signal-neutral" in css
    assert ".relationship-line-4" in css
    assert ".relationship-line-key-4" in css
    assert ".metric-context" in css
    assert "grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));" in css


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


def test_macro_dashboard_js_renders_services_latest_values():
    script = textwrap.dedent("""
        const fs = require("fs");
        const vm = require("vm");

        const body = {
          innerHTML: "",
          querySelectorAll: () => [],
          querySelector: () => null,
        };

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

        const latest = {
          pmi: 52.0,
          business_activity: 54.0,
          new_orders: 55.0,
          order_backlog: 48.0,
          employment: 51.0,
          inventories: 45.0,
          inventory_sentiment: 47.5,
          prices: 56.0,
          supplier_deliveries: 49.0,
          new_export_orders: 50.0,
          imports: 51.5,
        };

        const latest_metadata = {
          pmi: { tone: "green", point_change: 0.5, direction: "up", rate_of_change: "accelerating", trend_months: 3, label: "Services PMI" },
          business_activity: { tone: "green", point_change: 0.3, direction: "up", rate_of_change: "steady", trend_months: 2, label: "Business Activity" },
          new_orders: { tone: "green", point_change: 0.2, direction: "up", rate_of_change: "steady", trend_months: 1, label: "New Orders" },
          order_backlog: { tone: "amber", point_change: -0.5, direction: "down", rate_of_change: "accelerating", trend_months: 2, label: "Order Backlog" },
          employment: { tone: "green", point_change: 0.1, direction: "up", rate_of_change: "steady", trend_months: 4, label: "Employment" },
          inventories: { tone: "red", point_change: -1.2, direction: "down", rate_of_change: "accelerating", trend_months: 2, label: "Inventories" },
          inventory_sentiment: { tone: "amber", point_change: 0.0, direction: "flat", rate_of_change: "steady", trend_months: 1, label: "Inventory Sentiment" },
          prices: { tone: "amber", point_change: 0.8, direction: "up", rate_of_change: "accelerating", trend_months: 3, label: "Prices" },
          supplier_deliveries: { tone: "amber", point_change: -0.3, direction: "down", rate_of_change: "steady", trend_months: 2, label: "Supplier Deliveries" },
          new_export_orders: { tone: "muted", point_change: null, direction: "n/a", rate_of_change: "n/a", trend_months: 0, label: "New Export Orders" },
          imports: { tone: "green", point_change: 0.2, direction: "up", rate_of_change: "steady", trend_months: 2, label: "Imports" },
        };

        const detail_groups = [
          { label: "Business Cycle", keys: ["pmi"] },
          { label: "Demand & Activity", keys: ["business_activity", "new_orders", "order_backlog"] },
          { label: "Labor & Inventories", keys: ["employment", "inventories", "inventory_sentiment"] },
          { label: "Inflation & Supply", keys: ["prices", "supplier_deliveries", "new_export_orders", "imports"] },
        ];

        const payload = { latest, latest_metadata, detail_groups, signal: { state: "supports_growth", backlog_confirmation: "stable" } };

        hooks.renderServicesDetailInPanel(body, payload);
        const html = body.innerHTML;

        const body2 = { innerHTML: "", querySelectorAll: () => [], querySelector: () => null };

        const payload2 = {
          latest,
          latest_metadata,
          signal: {
            state: "supports_growth",
            backlog_confirmation: "stable",
            metrics: {
              pmi: { value: 52.0, point_change: 0.5, level: "expansion", momentum: "accelerating" },
              business_activity: { value: 54.0, point_change: 0.3, level: "expansion", momentum: "steady" },
              new_orders: { value: 55.0, point_change: 0.2, level: "expansion", momentum: "steady" },
              order_backlog: { value: 48.0, point_change: -0.5, level: "contraction", momentum: "accelerating" },
            },
          },
        };

        hooks.renderServicesDetailInPanel(body2, payload2);
        const html2 = body2.innerHTML;

        console.log(JSON.stringify({ html, html2 }));
    """)

    result = subprocess.run(
        ["node", "-e", script],
        cwd=ROOT,
        capture_output=True,
        check=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    html = payload["html"]
    html2 = payload["html2"]

    assert html.count('class="ism-metric-row"') == 11
    assert "Business Cycle" in html
    assert "Demand &amp; Activity" in html
    assert "Labor &amp; Inventories" in html
    assert "Inflation &amp; Supply" in html
    assert "ism-trend-chip-green" in html
    assert "ism-trend-chip-amber" in html
    assert "ism-trend-chip-red" in html
    assert "<th>Metric</th>" not in html

    assert "ism-signal-badge" in html2
    assert "<th>Metric</th>" in html2
    assert "Backlog: stable" in html2


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


def test_survey_synthesis_contains_services_backlog_signal_row():
    js = STATIC_JS.read_text()

    assert "Services Backlog Signal" in js
    assert "服务业订单积压信号" in js
    assert "Supports Growth" in js
    assert "Supports Contraction" in js


def test_macro_dashboard_js_renders_survey_synthesis_placeholder_card():
    js = (ROOT / "static" / "macro-dashboard.js").read_text()

    assert "renderSurveySynthesisCard" in js
    assert "Survey Synthesis" in js
    assert "Pending Inputs" in js
    assert "待输入" in js
    assert "ISM Growth Direction" in js
    assert "ISM增长方向" in js
    assert "Manufacturing & Services PMI Trend" in js
    assert "制造业与服务业PMI走势" in js
    assert "Surveys aligned?" not in js
    assert "New Orders Signal" in js
    assert "新订单信号" in js
    assert "Leading Indicator Comparison" in js
    assert "领先指标对比" in js
    assert "ISM-implied GDP Growth" in js
    assert "ISM指向的GDP增长" in js
    assert "ISM Portfolio Contribution" in js
    assert "ISM对组合倾向的影响" in js
    assert "Observation Status" in js
    assert "观察状态" in js
    assert "Services Backlog Signal" in js
    assert "服务业订单积压信号" in js
    assert "survey-synthesis-row" in js
    assert "survey-synthesis-question" in js
    assert "survey-synthesis-answer" in js
    assert "survey-synthesis-grid" in js
    assert "card.economic_direction" in js
    assert "card.growth_momentum" in js
    assert "card.demand_alignment" in js
    assert "card.cross_sector_comparison" in js
    assert "card.expected_gdp_direction" in js
    assert "card.survey_portfolio_implication" in js


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


def test_macro_dashboard_js_renders_survey_synthesis_card_with_available_data():
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
          id: "survey_synthesis",
          status: "available",
          economic_direction: "aligned_expansion",
          growth_momentum: "falling",
          survey_alignment: "aligned",
          demand_alignment: "aligned_falling",
          leading_side: "not_applicable",
          cross_sector_comparison: "aligned",
          expected_gdp_direction: "slowing",
          survey_portfolio_implication: "long",
          bias_confirmation: "awaiting_confirmation",
          backlog_confirmation: "supports_growth",
          components: {
            manufacturing: { demand_level: "expanding", demand_momentum: "falling" },
            services: {
              demand_level: "expanding",
              demand_momentum: "falling",
              activity_level: "expanding",
              activity_momentum: "falling",
            },
          },
          agreements: ["Both surveys expanding"],
          conflicts: [],
          reasons: ["Broad expansion", "Demand slowing"],
        };

        const html = hooks.renderSurveySynthesisCard(card);

        console.log(JSON.stringify({
          hasIsmGrowthDirection: html.indexOf("ISM Growth Direction") !== -1
            && html.indexOf("ISM增长方向") !== -1,
          hasBothExpanding: html.indexOf("Both Expanding") !== -1
            && html.indexOf("制造业与服务业均扩张") !== -1,
          hasPmiTrend: html.indexOf("Manufacturing &amp; Services PMI Trend") !== -1
            && html.indexOf("制造业与服务业PMI走势") !== -1
            && html.indexOf("Both Lower Than Last Month") !== -1
            && html.indexOf("两者均低于上月") !== -1,
          removedSurveyAlignment: html.indexOf("Surveys aligned?") === -1,
          hasNewOrdersSignal: html.indexOf("New Orders Signal") !== -1
            && html.indexOf("新订单信号") !== -1
            && html.indexOf("Expanding but Slowing") !== -1
            && html.indexOf("仍在扩张，但正在放缓") !== -1,
          hasLeadingIndicatorComparison: html.indexOf("Leading Indicator Comparison") !== -1
            && html.indexOf("领先指标对比") !== -1,
          hasSlowingTogether: html.indexOf("Slowing Together") !== -1
            && html.indexOf("同步放缓") !== -1,
          hasIsmImpliedGdpGrowth: html.indexOf("ISM-implied GDP Growth") !== -1
            && html.indexOf("ISM指向的GDP增长") !== -1
            && html.indexOf("Growth Slowing") !== -1
            && html.indexOf("增长速度可能放缓") !== -1,
          hasPortfolioContribution: html.indexOf("ISM Portfolio Contribution") !== -1
            && html.indexOf("ISM对组合倾向的影响") !== -1
            && html.indexOf("Supports Long Bias") !== -1
            && html.indexOf("支持偏多倾向") !== -1,
          hasObservationStatus: html.indexOf("Observation Status") !== -1
            && html.indexOf("观察状态") !== -1
            && html.indexOf("Continue Observing") !== -1
            && html.indexOf("继续观察") !== -1,
          hasServicesBacklogSignal: html.indexOf("Services Backlog Signal") !== -1
            && html.indexOf("服务业订单积压信号") !== -1
            && html.indexOf("Supports Continued Growth") !== -1
            && html.indexOf("支持增长延续") !== -1,
          hasRawEvidenceHtml: html.indexOf('<span class="survey-synthesis-evidence-line">') !== -1,
          hasNoEscapedEvidenceHtml: html.indexOf("&lt;span") === -1,
          hasManufacturingNewOrders: html.indexOf("Manufacturing New Orders") !== -1
            && html.indexOf("制造业新订单") !== -1,
          hasServicesBusinessActivity: html.indexOf("Services Business Activity") !== -1
            && html.indexOf("服务业商业活动") !== -1,
          hasSlowing: html.indexOf("Slowing") !== -1,
          hasBroadExpansion: html.indexOf("Broad expansion") !== -1,
          hasDemandSlowing: html.indexOf("Demand slowing") !== -1,
          hasSurveySynthesisCard: html.indexOf("survey-synthesis-card") !== -1,
          hasNoSummaryBadge: html.indexOf("survey-synthesis-summary") === -1,
          hasPendingInputsBadge: html.indexOf("Pending Inputs") === -1,
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

    assert payload["hasIsmGrowthDirection"] is True
    assert payload["hasBothExpanding"] is True
    assert payload["hasPmiTrend"] is True
    assert payload["removedSurveyAlignment"] is True
    assert payload["hasNewOrdersSignal"] is True
    assert payload["hasLeadingIndicatorComparison"] is True
    assert payload["hasSlowingTogether"] is True
    assert payload["hasIsmImpliedGdpGrowth"] is True
    assert payload["hasPortfolioContribution"] is True
    assert payload["hasObservationStatus"] is True
    assert payload["hasServicesBacklogSignal"] is True
    assert payload["hasRawEvidenceHtml"] is True
    assert payload["hasNoEscapedEvidenceHtml"] is True
    assert payload["hasManufacturingNewOrders"] is True
    assert payload["hasServicesBusinessActivity"] is True
    assert payload["hasSlowing"] is True
    assert payload["hasBroadExpansion"] is True
    assert payload["hasDemandSlowing"] is True
    assert payload["hasSurveySynthesisCard"] is True
    assert payload["hasNoSummaryBadge"] is True
    assert payload["hasPendingInputsBadge"] is True


def test_survey_synthesis_uses_ism_labels_and_dynamic_portfolio_bias_explanations():
    script = textwrap.dedent(
        """
        const fs = require("fs");
        const vm = require("vm");

        const elements = {
          dashboardStatus: {},
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
        const baseCard = {
          id: "survey_synthesis",
          status: "available",
          economic_direction: "aligned_expansion",
          growth_momentum: "falling",
          survey_alignment: "aligned",
          demand_alignment: "aligned_falling",
          leading_side: "not_applicable",
          expected_gdp_direction: "slowing",
          reasons: [],
          conflicts: [],
        };
        const renderBias = (bias, status = "available") =>
          hooks.renderSurveySynthesisCard({
            ...baseCard,
            status,
            survey_portfolio_implication: bias,
          });

        const neutral = renderBias("neutral");
        const long = renderBias("long");
        const defensive = renderBias("short_or_neutral");
        const unavailable = renderBias(null, "partial");
        const observing = hooks.renderSurveySynthesisCard({
          ...baseCard,
          survey_portfolio_implication: "long",
          bias_confirmation: "awaiting_confirmation",
        });

        console.log(JSON.stringify({
          hasPmiTrend: neutral.includes("Manufacturing &amp; Services PMI Trend")
            && neutral.includes("制造业与服务业PMI走势"),
          hasPortfolioContribution: neutral.includes("ISM Portfolio Contribution") && neutral.includes("ISM对组合倾向的影响"),
          removedOldLabels: !neutral.includes("Growth momentum")
            && !neutral.includes("Survey implication")
            && !neutral.includes("ISM Momentum")
            && !neutral.includes("ISM Portfolio Bias"),
          neutralExplanation: neutral.includes("ISM signals alone do not support materially increasing risk exposure or shifting to a short posture."),
          neutralChinese: neutral.includes("仅凭ISM信号，不足以支持明显增加风险资产敞口，也不足以支持转向做空。"),
          longExplanation: long.includes("ISM signals support a more constructive risk-asset posture, while Market Setup determines the final portfolio posture."),
          defensiveExplanation: defensive.includes("ISM signals support a neutral or more defensive posture, while Market Setup determines the final portfolio posture."),
          unavailableExplanation: unavailable.includes("Manufacturing and Services data are insufficient to form an ISM portfolio bias."),
          observingChinese: observing.includes("继续观察") && !observing.includes("等待确认"),
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

    assert json.loads(result.stdout) == {
        "hasPmiTrend": True,
        "hasPortfolioContribution": True,
        "removedOldLabels": True,
        "neutralExplanation": True,
        "neutralChinese": True,
        "longExplanation": True,
        "defensiveExplanation": True,
        "unavailableExplanation": True,
        "observingChinese": True,
    }


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


def test_macro_dashboard_js_survey_synthesis_card_replaces_removed_features():
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

        console.log(JSON.stringify({
          hasSurveySynthesis: typeof hooks.renderSurveySynthesisCard === "function",
          hasBiasEvidenceStrip: typeof hooks.renderBiasEvidenceStrip === "undefined",
          hasGdpExpectationsCard: typeof hooks.renderGdpExpectationsCard === "undefined",
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

    assert payload["hasSurveySynthesis"] is True
    assert payload["hasBiasEvidenceStrip"] is True
    assert payload["hasGdpExpectationsCard"] is True


def test_macro_dashboard_js_renders_survey_synthesis_as_standalone_layer():
    script = textwrap.dedent(
        """
        const fs = require("fs");
        const vm = require("vm");

        const surveyHead = {
          outerHTML: '<div class="relationship-head"><h2>Survey Synthesis</h2></div>',
        };
        const elements = {
          dashboardStatus: {},
          surveySynthesis: {
            innerHTML: "",
            querySelector: () => surveyHead,
            querySelectorAll: () => [],
          },
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

        const growthCycle = {
          headline: [{
            id: "survey_synthesis",
            status: "available",
            economic_direction: "aligned_expansion",
            growth_momentum: "falling",
            survey_alignment: "aligned",
            demand_alignment: "aligned_falling",
            leading_side: "not_applicable",
            expected_gdp_direction: "slowing",
            survey_portfolio_implication: "neutral",
            reasons: ["Business surveys indicate broad expansion"],
            conflicts: [],
          }],
        };

        hooks.state.growthCycle = growthCycle;
        hooks.renderSurveySynthesis();

        console.log(JSON.stringify({
          hasDecisionLayerTitle: elements.surveySynthesis.innerHTML.includes("Survey Synthesis"),
          hasGdpDirection: elements.surveySynthesis.innerHTML.includes("Slowing"),
          hasEvidence: elements.surveySynthesis.innerHTML.includes("Business surveys indicate broad expansion"),
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

    assert payload["hasDecisionLayerTitle"] is True
    assert payload["hasGdpDirection"] is True
    assert payload["hasEvidence"] is True


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
            title: "Macro Risk Rising; Bull Market Intact",
            summary: "Macro risk is rising, but the bull phase remains intact."
          },
          portfolio_guidance: { actions: ["Maintain balanced exposure"], avoid: [] },
          evidence_chain: [],
          conviction_limits: {},
          confirmation_conditions: {}
        });
        const html = hooks.renderDecisionHero(presentation);
        console.log(JSON.stringify({
          headline: html.includes("Macro Risk Rising; Bull Market Intact"),
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


def test_market_setup_hero_names_ism_survey_sources():
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
          expected_growth: {
            state: "aligned_expansion",
            expected_gdp_direction: "slowing",
            growth_momentum: "falling",
            survey_alignment: "aligned",
            demand_alignment: "aligned_falling",
            evidence_links: ["ism_manufacturing", "ism_services"],
            components: {
              manufacturing: { level: "expanding", momentum: "falling" },
              services: { level: "expanding", momentum: "falling" },
            },
          },
          financial_conditions: { state: "accommodative" },
          policy_response: { state: "restrictive" },
          setup_type: "growth_and_conditions_aligned",
          portfolio_posture: "long",
          agreements: ["Growth and conditions are aligned"],
          conflicts: [],
          missing_inputs: [],
          pending_confirmations: [],
          market_conclusion: {
            code: "qualified_long_candidate",
            title: "Qualified Long Candidate",
            summary: "Growth is slowing but conditions remain supportive.",
          },
          portfolio_guidance: {
            posture: "long",
            summary: "Maintain long posture",
            actions: [],
            avoid: [],
          },
          evidence_chain: [{
            id: "growth_path",
            title: "Growth Trend",
            finding: "Growth is slowing but above trend",
            implication: "Supports moderate long exposure",
            tone: "constructive",
            evidence: ["ISM Manufacturing at 52.3", "ISM Services at 54.1"],
            evidence_links: ["ism_manufacturing", "ism_services"],
          }],
          conviction_limits: {},
          confirmation_conditions: {},
        };

        const pr = hooks.buildMarketSetupPresentation(setup);
        const hero = hooks.renderDecisionHero(pr);
        const detail = hooks.renderDetailedReasoning(pr);

        console.log(JSON.stringify({
          heroNamesManufacturing: hero.indexOf("ISM Manufacturing") !== -1,
          heroNamesServices: hero.indexOf("ISM Services") !== -1,
          detailShowsGrowthDirection: detail.indexOf("Slowing") !== -1,
          detailShowsSurveyAlignment: detail.indexOf("Aligned") !== -1,
          manufacturingLinkExists: detail.indexOf("evidence-ism-manufacturing") !== -1,
          servicesLinkExists: detail.indexOf("evidence-ism-services") !== -1,
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
        "heroNamesManufacturing": True,
        "heroNamesServices": True,
        "detailShowsGrowthDirection": True,
        "detailShowsSurveyAlignment": True,
        "manufacturingLinkExists": True,
        "servicesLinkExists": True,
    }


def test_macro_dashboard_renders_stable_evidence_target_ids():
    js = STATIC_JS.read_text()
    target_ids = {
        "evidence-market-phase",
        "evidence-ism-manufacturing",
        "evidence-ism-services",
        "evidence-yield-curve",
        "evidence-credit-conditions",
        "evidence-real-rate-risk",
        "evidence-vix",
        "evidence-fomc-policy",
        "evidence-m2-money-supply",
    }

    assert all(
        js.count(target_id) >= 2 for target_id in target_ids - {"evidence-ism-services"}
    )
    assert js.count("evidence-ism-services") >= 1
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


def test_macro_dashboard_html_loads_ism_services_assets():
    html = (ROOT / "static" / "macro-dashboard.html").read_text()

    assert '<script src="/ism-services.js"></script>' in html
    assert '<link rel="stylesheet" href="/ism-services.css" />' in html


def test_macro_dashboard_js_delegates_ism_services_card():
    js = STATIC_JS.read_text()

    assert 'card.id === "ism_services"' in js
    assert 'ism_services"' in js


def test_macro_dashboard_js_routes_ism_services_detail():
    js = STATIC_JS.read_text()

    assert 'payload.detail_id === "ism_services"' in js


def test_ism_services_js_no_peak_trough_text():
    services_js = (ROOT / "static" / "ism-services.js").read_text()

    assert "possible peak" not in services_js.lower()
    assert "possible trough" not in services_js.lower()


def test_ism_services_js_renders_card_with_node():
    script = textwrap.dedent("""\
        const vm = require("vm");

        global.window = {};

        vm.runInThisContext(require("fs").readFileSync("static/ism-services.js", "utf8"));

        const card = {
            id: "ism_services",
            segments: {
                services_cycle: { value: 51.2, label: "Expansion" },
                business_activity: { value: 53.5, trend: "Rising" },
                new_orders: { value: 52.8, trend: "Stable" },
                industry_breadth: { growth_count: 12, total_count: 18 },
            },
        };

        const helpers = {
            escapeHtml: (s) => String(s || "")
                .replaceAll("&", "&amp;")
                .replaceAll("<", "&lt;")
                .replaceAll(">", "&gt;"),
            formatIndex: (v) => v !== null && v !== undefined && !Number.isNaN(Number(v)) ? Number(v).toFixed(1) : "n/a",
        };

        const html = window.ismServicesUi.renderCard(card, helpers);
        const count = (s) => html.split(s).length - 1;

        console.log(JSON.stringify({
            servicesCycleCount: count("Services Cycle"),
            businessActivityCount: count("Business Activity"),
            newOrdersCount: count("New Orders"),
            industryBreadthCount: count("Industry Breadth"),
            containsExpansion: html.indexOf("Expansion") !== -1,
            containsRising: html.indexOf("Rising") !== -1,
            containsStable: html.indexOf("Stable") !== -1,
            containsGrowing: html.indexOf("Growing") !== -1,
            contains12of18: html.indexOf("12/18") !== -1,
            isButton: html.indexOf('<button') !== -1,
            hasDetailId: html.indexOf('data-growth-cycle-detail-id="ism_services"') !== -1,
            hasEvidenceId: html.indexOf('id="evidence-ism-services"') !== -1,
            hasEvidenceTargetClass: html.indexOf("evidence-target") !== -1,
            hasIsmCardButton: html.indexOf("ism-card-button") !== -1,
            hasM2Card: html.indexOf("m2-card") !== -1,
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

    assert payload["servicesCycleCount"] == 1
    assert payload["businessActivityCount"] == 1
    assert payload["newOrdersCount"] == 1
    assert payload["industryBreadthCount"] == 1
    assert payload["containsExpansion"] is True
    assert payload["containsRising"] is True
    assert payload["containsStable"] is True
    assert payload["containsGrowing"] is True
    assert payload["contains12of18"] is True
    assert payload["isButton"] is True
    assert payload["hasDetailId"] is True
    assert payload["hasEvidenceId"] is True
    assert payload["hasEvidenceTargetClass"] is True
    assert payload["hasIsmCardButton"] is True
    assert payload["hasM2Card"] is True


def test_services_evidence_uses_readable_labels_without_schema_tokens():
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
        const commodities = hooks.renderServicesCommodityGroups([
          { commodity: "Aluminum", signal_type: "up_in_price", months: 4 },
          { commodity: "Beef", signal_type: "down_in_price", months: null },
          { commodity: "Electrical Components", signal_type: "short_supply", months: 2 },
        ]);
        const narrative = hooks.renderServicesNarrativeFacts({
          consecutive_expansion_months: 24,
          services_economy_gdp_share_percent: 79,
          broad_based_expansion_mentioned: true,
          inflationary_pressure_mentioned: false,
        });

        console.log(JSON.stringify({ commodities, narrative }));
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

    assert "Prices increased" in payload["commodities"]
    assert "Aluminum" in payload["commodities"]
    assert "4 months" in payload["commodities"]
    assert "Prices decreased" in payload["commodities"]
    assert "In short supply" in payload["commodities"]
    assert "up_in_price" not in payload["commodities"]
    assert "expanded for 24 consecutive months" in payload["narrative"]
    assert "79% of U.S. GDP" in payload["narrative"]
    assert "Broad-based expansion was mentioned" in payload["narrative"]
    assert "Inflationary pressure was not mentioned" in payload["narrative"]


def test_services_signal_trend_renderer_is_defined():
    script = textwrap.dedent(
        """
        const fs = require("fs");
        const vm = require("vm");
        global.window = { __MEOWSTREET_TEST__: true };
        global.document = { getElementById: () => null };
        global.fetch = async () => ({ ok: true, status: 200, json: async () => ({ markets: [] }) });
        global.$ = () => ({ textContent: "" });
        global.loadUsRatesLiquidity = async () => {};
        global.loadGdpRelationshipOverview = async () => {};
        global.loadGrowthCycle = async () => {};
        global.loadConsumerSentiment = async () => {};
        global.loadMarketSetup = async () => {};
        process.on("unhandledRejection", () => {});
        global.loadUsRatesLiquidity = async () => {};
        global.loadGdpRelationshipOverview = async () => {};
        global.loadGrowthCycle = async () => {};
        global.loadConsumerSentiment = async () => {};
        global.loadMarketSetup = async () => {};
        process.on("unhandledRejection", () => {});
        vm.runInThisContext(fs.readFileSync("static/macro-dashboard.js", "utf8"));
        const hooks = window.__macroDashboardTestHooks;
        console.log(JSON.stringify({
          hasSignalTrend: typeof hooks.renderServicesSignalTrend === "function",
          hasCellRenderer: typeof hooks.renderSignalTrendCell === "function",
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
    assert payload["hasSignalTrend"] is True
    assert payload["hasCellRenderer"] is True


def test_services_signal_trend_renders_all_12_headers():
    script = textwrap.dedent(
        """
        const fs = require("fs");
        const vm = require("vm");

        global.window = { __MEOWSTREET_TEST__: true };
        global.document = {
          getElementById: () => null,
        };
        global.fetch = async () => ({ ok: true, status: 200, json: async () => ({ markets: [] }) });
        global.$ = () => ({ textContent: "" });
        global.loadUsRatesLiquidity = async () => {};
        global.loadGdpRelationshipOverview = async () => {};
        global.loadGrowthCycle = async () => {};
        global.loadConsumerSentiment = async () => {};
        global.loadMarketSetup = async () => {};
        process.on("unhandledRejection", () => {});

        vm.runInThisContext(fs.readFileSync("static/macro-dashboard.js", "utf8"));
        const hooks = window.__macroDashboardTestHooks;

        const trend = [{
          period: "2026-06-01",
          overall: { status: "listed", direction: "growth", direction_label: "Growth", rank: 1, list_size: 14 },
          components: {
            business_activity: { status: "listed", direction: "increase", direction_label: "Increase", rank: 2, list_size: 8 },
            new_orders: { status: "unavailable", direction: null, direction_label: "Unavailable", rank: null, list_size: null },
            employment: { status: "unavailable", direction: null, direction_label: "Unavailable", rank: null, list_size: null },
            supplier_deliveries: { status: "unavailable", direction: null, direction_label: "Unavailable", rank: null, list_size: null },
            inventories: { status: "unavailable", direction: null, direction_label: "Unavailable", rank: null, list_size: null },
            inventory_sentiment: { status: "unavailable", direction: null, direction_label: "Unavailable", rank: null, list_size: null },
            prices: { status: "unavailable", direction: null, direction_label: "Unavailable", rank: null, list_size: null },
            backlog: { status: "unavailable", direction: null, direction_label: "Unavailable", rank: null, list_size: null },
            new_export_orders: { status: "unavailable", direction: null, direction_label: "Unavailable", rank: null, list_size: null },
            imports: { status: "unavailable", direction: null, direction_label: "Unavailable", rank: null, list_size: null },
          },
        }];

        const html = hooks.renderServicesSignalTrend(trend);
        console.log(JSON.stringify({
          hasPeriod: html.indexOf("Period") !== -1,
          hasOverall: html.indexOf("Overall") !== -1,
          hasBusinessActivity: html.indexOf("Business Activity") !== -1,
          hasNewOrders: html.indexOf("New Orders") !== -1,
          hasEmployment: html.indexOf("Employment") !== -1,
          hasSupplierDeliveries: html.indexOf("Supplier Deliveries") !== -1,
          hasInventories: html.indexOf("Inventories") !== -1,
          hasInventorySentiment: html.indexOf("Inventory Sentiment") !== -1,
          hasPrices: html.indexOf("Prices") !== -1,
          hasOrderBacklog: html.indexOf("Order Backlog") !== -1,
          hasNewExportOrders: html.indexOf("New Export Orders") !== -1,
          hasImports: html.indexOf("Imports") !== -1,
          hasSignalTrend: html.indexOf("Signal Trend") !== -1,
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
    for key, val in payload.items():
        assert val is True, f"{key} was false"


def test_services_signal_trend_listed_cell_includes_direction_and_rank():
    script = textwrap.dedent(
        """
        const fs = require("fs");
        const vm = require("vm");

        global.window = { __MEOWSTREET_TEST__: true };
        global.document = { getElementById: () => null };
        global.fetch = async () => ({ ok: true, status: 200, json: async () => ({ markets: [] }) });
        global.$ = () => ({ textContent: "" });
        global.loadUsRatesLiquidity = async () => {};
        global.loadGdpRelationshipOverview = async () => {};
        global.loadGrowthCycle = async () => {};
        global.loadConsumerSentiment = async () => {};
        global.loadMarketSetup = async () => {};
        process.on("unhandledRejection", () => {});

        vm.runInThisContext(fs.readFileSync("static/macro-dashboard.js", "utf8"));
        const hooks = window.__macroDashboardTestHooks;

        const trend = [{
          period: "2026-06-01",
          overall: { status: "listed", direction: "growth", direction_label: "Growth", rank: 1, list_size: 14 },
          components: {
            business_activity: { status: "listed", direction: "increase", direction_label: "Increase", rank: 2, list_size: 8 },
            new_orders: { status: "unavailable", direction: null, direction_label: "Unavailable", rank: null, list_size: null },
            employment: { status: "unavailable", direction: null, direction_label: "Unavailable", rank: null, list_size: null },
            supplier_deliveries: { status: "unavailable", direction: null, direction_label: "Unavailable", rank: null, list_size: null },
            inventories: { status: "unavailable", direction: null, direction_label: "Unavailable", rank: null, list_size: null },
            inventory_sentiment: { status: "unavailable", direction: null, direction_label: "Unavailable", rank: null, list_size: null },
            prices: { status: "unavailable", direction: null, direction_label: "Unavailable", rank: null, list_size: null },
            backlog: { status: "unavailable", direction: null, direction_label: "Unavailable", rank: null, list_size: null },
            new_export_orders: { status: "unavailable", direction: null, direction_label: "Unavailable", rank: null, list_size: null },
            imports: { status: "unavailable", direction: null, direction_label: "Unavailable", rank: null, list_size: null },
          },
        }];

        const html = hooks.renderServicesSignalTrend(trend);
        console.log(JSON.stringify({
          hasGrowthRank: html.indexOf("Growth #1/14") !== -1,
          hasIncreaseRank: html.indexOf("Increase #2/8") !== -1,
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
    assert payload["hasGrowthRank"] is True
    assert payload["hasIncreaseRank"] is True


def test_services_signal_trend_unavailable_not_listed_conflicting_distinct():
    script = textwrap.dedent(
        """
        const fs = require("fs");
        const vm = require("vm");

        global.window = { __MEOWSTREET_TEST__: true };
        global.document = { getElementById: () => null };
        global.fetch = async () => ({ ok: true, status: 200, json: async () => ({ markets: [] }) });
        global.$ = () => ({ textContent: "" });
        global.loadUsRatesLiquidity = async () => {};
        global.loadGdpRelationshipOverview = async () => {};
        global.loadGrowthCycle = async () => {};
        global.loadConsumerSentiment = async () => {};
        global.loadMarketSetup = async () => {};
        process.on("unhandledRejection", () => {});

        function makeUnavailable() {
          const result = {};
          for (const k of ["business_activity","new_orders","employment","supplier_deliveries","inventories","inventory_sentiment","prices","backlog","new_export_orders","imports"]) {
            result[k] = { status: "unavailable", direction: null, direction_label: "Unavailable", rank: null, list_size: null };
          }
          return result;
        }

        vm.runInThisContext(fs.readFileSync("static/macro-dashboard.js", "utf8"));
        const hooks = window.__macroDashboardTestHooks;

        const trendNotListed = [{
          period: "2026-06-01",
          overall: { status: "not_listed", direction: null, direction_label: "Not listed", rank: null, list_size: null },
          components: makeUnavailable(),
        }];
        const htmlNotListed = hooks.renderServicesSignalTrend(trendNotListed);

        const trendConflicting = [{
          period: "2026-06-01",
          overall: { status: "conflicting", direction: null, direction_label: "Conflicting", rank: null, list_size: null },
          components: makeUnavailable(),
        }];
        const htmlConflicting = hooks.renderServicesSignalTrend(trendConflicting);

        const trendUnavailable = [{
          period: "2026-06-01",
          overall: { status: "unavailable", direction: null, direction_label: "Unavailable", rank: null, list_size: null },
          components: makeUnavailable(),
        }];
        const htmlUnavailable = hooks.renderServicesSignalTrend(trendUnavailable);

        console.log(JSON.stringify({
          hasNotListed: htmlNotListed.indexOf("Not listed") !== -1,
          hasConflicting: htmlConflicting.indexOf("Conflicting") !== -1,
          hasUnavailable: htmlUnavailable.indexOf("Unavailable") !== -1,
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
    assert payload["hasNotListed"] is True
    assert payload["hasConflicting"] is True
    assert payload["hasUnavailable"] is True


def test_services_signal_trend_shows_all_input_rows():
    script = textwrap.dedent(
        """
        const fs = require("fs");
        const vm = require("vm");

        global.window = { __MEOWSTREET_TEST__: true };
        global.document = { getElementById: () => null };
        global.fetch = async () => ({ ok: true, status: 200, json: async () => ({ markets: [] }) });
        global.$ = () => ({ textContent: "" });
        global.loadUsRatesLiquidity = async () => {};
        global.loadGdpRelationshipOverview = async () => {};
        global.loadGrowthCycle = async () => {};
        global.loadConsumerSentiment = async () => {};
        global.loadMarketSetup = async () => {};
        process.on("unhandledRejection", () => {});

        function makeUnavailable() {
          const result = {};
          for (const k of ["business_activity","new_orders","employment","supplier_deliveries","inventories","inventory_sentiment","prices","backlog","new_export_orders","imports"]) {
            result[k] = { status: "unavailable", direction: null, direction_label: "Unavailable", rank: null, list_size: null };
          }
          return result;
        }

        vm.runInThisContext(fs.readFileSync("static/macro-dashboard.js", "utf8"));
        const hooks = window.__macroDashboardTestHooks;

        const trend = [];
        for (let m = 1; m <= 3; m++) {
          const period = "2026-" + String(m).padStart(2, "0") + "-01";
          trend.push({
            period: period,
            overall: { status: "listed", direction: "growth", direction_label: "Growth", rank: 1, list_size: 14 },
            components: makeUnavailable(),
          });
        }

        const html = hooks.renderServicesSignalTrend(trend);
        const rows = html.split("<tbody>")[1] || "";
        const rowCount = (rows.match(/<tr>/g) || []).length;
        console.log(JSON.stringify({ rowCount: rowCount }));
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
    assert payload["rowCount"] == 3


def test_services_signal_trend_returns_empty_for_no_data():
    script = textwrap.dedent(
        """
        const fs = require("fs");
        const vm = require("vm");

        global.window = { __MEOWSTREET_TEST__: true };
        global.document = { getElementById: () => null };
        global.fetch = async () => ({ ok: true, status: 200, json: async () => ({ markets: [] }) });
        global.$ = () => ({ textContent: "" });
        global.loadUsRatesLiquidity = async () => {};
        global.loadGdpRelationshipOverview = async () => {};
        global.loadGrowthCycle = async () => {};
        global.loadConsumerSentiment = async () => {};
        global.loadMarketSetup = async () => {};
        process.on("unhandledRejection", () => {});

        vm.runInThisContext(fs.readFileSync("static/macro-dashboard.js", "utf8"));
        const hooks = window.__macroDashboardTestHooks;

        const html = hooks.renderServicesSignalTrend([]);
        console.log(JSON.stringify({ empty: html === "" }));
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
    assert payload["empty"] is True


def test_services_component_evidence_and_rank_history_replaced_by_signal_trend():
    script = textwrap.dedent(
        """
        const fs = require("fs");
        const vm = require("vm");
        global.window = { __MEOWSTREET_TEST__: true };
        global.document = { getElementById: () => null };
        global.fetch = async () => ({ ok: true, status: 200, json: async () => ({ markets: [] }) });
        global.$ = () => ({ textContent: "" });
        global.loadUsRatesLiquidity = async () => {};
        global.loadGdpRelationshipOverview = async () => {};
        global.loadGrowthCycle = async () => {};
        global.loadConsumerSentiment = async () => {};
        global.loadMarketSetup = async () => {};
        process.on("unhandledRejection", () => {});
        global.loadUsRatesLiquidity = async () => {};
        global.loadGdpRelationshipOverview = async () => {};
        global.loadGrowthCycle = async () => {};
        global.loadConsumerSentiment = async () => {};
        global.loadMarketSetup = async () => {};
        process.on("unhandledRejection", () => {});
        vm.runInThisContext(fs.readFileSync("static/macro-dashboard.js", "utf8"));
        const hooks = window.__macroDashboardTestHooks;
        console.log(JSON.stringify({
          hasOldComponentEvidence: typeof hooks.renderServicesComponentEvidence === "function",
          hasOldRankHistory: typeof hooks.renderServicesRankHistory === "function",
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
    assert payload["hasOldComponentEvidence"] is False
    assert payload["hasOldRankHistory"] is False


def test_services_detail_follows_manufacturing_display_structure():
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
          json: async () => ({ markets: [] }),
        });

        vm.runInThisContext(fs.readFileSync("static/macro-dashboard.js", "utf8"));
        const hooks = window.__macroDashboardTestHooks;

        const payload = {
          charts: [],
          signal: {
            state: "supports_growth",
            backlog_confirmation: "confirmed",
            metrics: {
              pmi: { value: 54.0, point_change: 0.2, level: "Expansion", momentum: "Faster" },
              business_activity: { value: 55.4, point_change: 0.9, level: "Expansion", momentum: "Faster" },
              new_orders: { value: 55.1, point_change: 0.3, level: "Expansion", momentum: "Faster" },
              order_backlog: { value: 54.9, point_change: 1.8, level: "Expansion", momentum: "Faster" },
            },
          },
          industries: {
            breadth: { growth_count: 12, total_count: 18, status: "broad" },
            industries: [
              { industry: "Construction", direction: "growth", rank: 1 },
            ],
          },
          industry_analysis: {
            status: "available",
            period: "2026-06-01",
            source_url: "https://www.ismworld.org/example",
            growing_industries: [{ industry: "Construction", rank: 1 }],
            contracting_industries: [],
            industries: [
              {
                industry: "Construction",
                direction: "growth",
                rank: 1,
                direction_change: null,
                rank_change: 0,
                streak: { direction: "growth", months: 3 },
                trend: [],
                component_signals: [],
                component_coverage: { listed_components: 0, available_components: 10 },
                comments: ["Demand strong."],
              },
            ],
          },
          official_report_summary: {
            source_type: "report_extracted",
            report_id: "ism_services_2026_06",
            period: "2026-06-01",
            title: "June 2026 ISM Services PMI Report",
            source_url: "https://www.ismworld.org/example",
            headline: "Services PMI 54.0, +0.2 points from prior month; Growing / Faster.",
            major_changes: ["Prices: 61.2, +1.8 points; Increasing / Faster."],
            respondent_comments: [],
            comment_preview_count: 3,
          },
          rich_evidence: {
            at_a_glance_rows: [
              { series_id: "ism_services_pmi", label: "Services PMI", current_value: 54.0, previous_value: 53.8, point_change: 0.2, direction: "Growing", rate_of_change: "Faster", trend_months: 2 },
              { series_id: "ism_services_business_activity", label: "Business Activity", current_value: 55.4, previous_value: 54.5, point_change: 0.9, direction: "Growing", rate_of_change: "Faster", trend_months: 2 },
              { series_id: "ism_services_new_orders", label: "New Orders", current_value: 55.1, previous_value: 54.8, point_change: 0.3, direction: "Growing", rate_of_change: "Faster", trend_months: 2 },
              { series_id: "ism_services_prices", label: "Prices", current_value: 61.2, previous_value: 59.4, point_change: 1.8, direction: "Increasing", rate_of_change: "Faster", trend_months: 3 },
            ],
            commodities: [{ commodity: "Aluminum", signal_type: "up_in_price", months: 4 }],
            narrative_facts: { consecutive_expansion_months: 24, services_economy_gdp_share_percent: 79, broad_based_expansion_mentioned: true, inflationary_pressure_mentioned: false },
            source: { source_url: "https://www.ismworld.org/example" },
          },
        };

        const body = {
          innerHTML: "",
          querySelector: () => null,
          querySelectorAll: () => [],
        };
        hooks.renderServicesDetailInPanel(body, payload);

        console.log(JSON.stringify({ html: body.innerHTML }));
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
    html = payload["html"]

    assert html.index("Official Report Summary") < html.index("Charts &amp; Heat Maps")
    assert html.index("Charts &amp; Heat Maps") < html.index("Latest Values")
    assert html.index("Latest Values") < html.index("Industry Analysis (6 Month)")
    assert "Full Report Evidence" in html
    assert "Prices increased" in html
    assert "Component Industry Lists" not in html
    assert "Official ISM Report" in html
    assert "AI Evidence" not in html
    assert "up_in_price" not in html
    assert "All Components" in html
    assert "Services PMI" in html
    assert "Business Activity" in html
    assert "New Orders" in html
    assert "Prices" in html
    assert "trend_months" not in html
    assert "54.0" in html
    assert "55.4" in html
    assert "55.1" in html
    assert "+0.2" in html
    assert "+0.9" in html
    assert "2m" in html
    assert "3m" in html
    assert ">1<" in html
    assert "Growing" in html
    assert "Demand strong." in html


def test_services_detail_edge_cases():
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
          json: async () => ({ markets: [] }),
        });

        vm.runInThisContext(fs.readFileSync("static/macro-dashboard.js", "utf8"));
        const hooks = window.__macroDashboardTestHooks;

        function testEmptyEvidence() {
          const html1 = hooks.renderServicesFullEvidence(null);
          if (html1 !== "") throw new Error("null evidence should return empty");

          const html2 = hooks.renderServicesFullEvidence({
            at_a_glance_rows: [],
            component_industries: [],
            respondent_comments: [],
            commodities: [],
            narrative_facts: {},
            source: {},
          });
          if (html2 !== "") throw new Error("empty evidence should return empty");
        }

        function testXssCommodity() {
          const html = hooks.renderServicesFullEvidence({
            at_a_glance_rows: [],
            component_industries: [],
            respondent_comments: [],
            commodities: [{ commodity: '<img src=x onerror=alert(1)>', signal_type: "up_in_price", months: 0 }],
            narrative_facts: {},
            source: {},
          });
          if (html.indexOf("<img") !== -1) throw new Error("raw img tag should be escaped");
          if (html.indexOf("&lt;img") === -1) throw new Error("escaped img tag should be present");
          if (html.indexOf("0 months") === -1) throw new Error("months:0 should be rendered");
        }

        function testUnknownCommoditySignalType() {
          const html = hooks.renderServicesFullEvidence({
            at_a_glance_rows: [],
            component_industries: [],
            respondent_comments: [],
            commodities: [{ commodity: "Widget", signal_type: "unknown_type", months: null }],
            narrative_facts: {},
            source: {},
          });
          if (html.indexOf("unknown_type") !== -1) throw new Error("unknown signal type should not appear");
        }

        function testNarrativeFactsRender() {
          const html = hooks.renderServicesFullEvidence({
            at_a_glance_rows: [],
            commodities: [],
            narrative_facts: { broad_based_expansion_mentioned: true },
            source: {},
          });
          if (html.indexOf("Broad-based expansion") < 0) throw new Error("narrative facts should render");
          if (html.indexOf("Component Industry Lists") >= 0) throw new Error("component industry lists should be absent");
        }

        function testMissingSummaryStillRenders() {
          const payload = {
            charts: [],
            signal: { state: "supports_growth", backlog_confirmation: "confirmed", metrics: {} },
            industries: { breadth: {}, industries: [] },
            official_report_summary: null,
            rich_evidence: null,
          };
          const body = { innerHTML: "", querySelector: () => null, querySelectorAll: () => [] };
          hooks.renderServicesDetailInPanel(body, payload);
          if (body.innerHTML.indexOf("Charts") < 0) throw new Error("Charts should still render");
          if (body.innerHTML.indexOf("Latest") < 0) throw new Error("Latest should still render");
        }

        testEmptyEvidence();
        testXssCommodity();
        testUnknownCommoditySignalType();
        testNarrativeFactsRender();
        testMissingSummaryStillRenders();
        console.log(JSON.stringify({ ok: true }));
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
    assert payload["ok"] is True


def test_services_full_evidence_has_readable_responsive_styles():
    js = (ROOT / "static" / "macro-dashboard.js").read_text(encoding="utf-8")
    css = (ROOT / "static" / "macro-dashboard.css").read_text(encoding="utf-8")

    assert 'class="ism-services-commodity-grid"' in js
    assert 'rel="noopener noreferrer"' in js
    assert ".ism-services-commodity-grid" in css
    assert "repeat(auto-fit, minmax(220px, 1fr))" in css
    assert ".ism-services-commodity-higher" in css
    assert ".ism-services-commodity-lower" in css
    assert ".ism-services-commodity-shortage" in css


def test_services_industry_analysis_renders_ranked_master_detail():
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

        function industry(name, direction, rank, comments = []) {
          return {
            industry: name,
            direction,
            rank,
            direction_change: null,
            rank_change: null,
            streak: { direction, months: 1 },
            trend: [{ period: "2026-06-01", direction, rank }],
            component_signals: name === "Construction"
              ? [{
                  signal_type: "business_activity",
                  label: "Business Activity",
                  direction: "growth",
                  direction_label: "Growth",
                  rank: 3,
                  list_size: 13,
                }]
              : [],
            component_coverage: {
              listed_components: name === "Construction" ? 1 : 0,
              available_components: 10,
              coverage_status: "available",
            },
            comments,
          };
        }

        const analysis = {
          status: "available",
          period: "2026-06-01",
          source_url: "https://example.com/services/june",
          growing_industries: [
            { industry: "Construction", rank: 1 },
            { industry: "Finance & Insurance", rank: 2 },
            { industry: "Utilities", rank: 3 },
            { industry: "Professional Services", rank: 4 },
          ],
          contracting_industries: [
            { industry: "Educational Services", rank: 1 },
            { industry: "Retail Trade", rank: 2 },
            { industry: "Wholesale Trade", rank: 3 },
            { industry: "Arts & Entertainment", rank: 4 },
          ],
          industries: [
            industry("Construction", "growth", 1, ["Construction comment."]),
            industry("Finance & Insurance", "growth", 2),
            industry("Utilities", "growth", 3),
            industry("Professional Services", "growth", 4),
            industry("Educational Services", "contraction", 1),
            industry("Retail Trade", "contraction", 2),
            industry("Wholesale Trade", "contraction", 3),
            industry("Arts & Entertainment", "contraction", 4),
          ],
        };

        const html = hooks.renderServicesIndustryAnalysisSection(analysis);

        console.log(JSON.stringify({
          summaryButtonCount: (html.match(/data-services-industry="/g) || []).length,
          selectorOptionCount: (html.match(/<option value=/g) || []).length,
          hasSelector: html.includes("data-services-industry-select"),
          hasFourthGrowthButton: html.includes('data-services-industry="Professional Services"'),
          hasFourthGrowthOption: html.includes('<option value="Professional Services"'),
          hasFourthContractionButton: html.includes('data-services-industry="Arts &amp; Entertainment"'),
          hasFourthContractionOption: html.includes('<option value="Arts &amp; Entertainment"'),
          hasConstructionSelectedOption: html.includes('<option value="Construction" selected>'),
          hasConstructionComment: html.includes("Construction comment."),
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

    assert payload["summaryButtonCount"] == 6
    assert payload["selectorOptionCount"] == 8
    assert payload["hasSelector"] is True
    assert payload["hasFourthGrowthButton"] is False
    assert payload["hasFourthGrowthOption"] is True
    assert payload["hasFourthContractionButton"] is False
    assert payload["hasFourthContractionOption"] is True
    assert payload["hasConstructionSelectedOption"] is True
    assert payload["hasConstructionComment"] is True


def test_services_industry_selection_scopes_detail_and_comments():
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
          period: "2026-06-01",
          source_url: "https://example.com/services/june",
          growing_industries: [{ industry: "Construction", rank: 1 }],
          contracting_industries: [{ industry: "Educational Services", rank: 1 }],
          industries: [
            {
              industry: "Construction",
              direction: "growth",
              rank: 1,
              direction_change: null,
              rank_change: -3,
              streak: { direction: "growth", months: 2 },
              trend: [],
              component_signals: [],
              component_coverage: { listed_components: 0, available_components: 10 },
              comments: ["Construction comment."],
            },
            {
              industry: "Educational Services",
              direction: "contraction",
              rank: 1,
              direction_change: null,
              rank_change: null,
              streak: { direction: "contraction", months: 1 },
              trend: [],
              component_signals: [],
              component_coverage: { listed_components: 0, available_components: 10 },
              comments: ["Education comment."],
            },
          ],
        };

        function fakeButton(industry) {
          return {
            dataset: { servicesIndustry: industry },
            classList: { toggle: () => {} },
            setAttribute(name, value) { this[name] = value; },
          };
        }
        const detail = { innerHTML: "" };
        const selector = {
          value: "Construction",
          addEventListener(type, handler) {
            this.eventType = type;
            this.handler = handler;
          },
        };
        const buttons = [fakeButton("Construction"), fakeButton("Educational Services")];
        const body = {
          querySelector: (selectorName) => {
            if (selectorName === "[data-services-industry-detail]") return detail;
            if (selectorName === "[data-services-industry-select]") return selector;
            return null;
          },
          querySelectorAll: () => buttons,
        };
        hooks.selectServicesIndustry(body, analysis, "Educational Services");

        console.log(JSON.stringify({
          selected: hooks.state.selectedServicesIndustry,
          growthPressed: buttons[0]["aria-pressed"],
          contractionPressed: buttons[1]["aria-pressed"],
          hasEducationComment: detail.innerHTML.indexOf("Education comment.") !== -1,
          hasConstructionComment: detail.innerHTML.indexOf("Construction comment.") !== -1,
          selectorValue: selector.value,
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

    assert payload["selected"] == "Educational Services"
    assert payload["growthPressed"] == "false"
    assert payload["contractionPressed"] == "true"
    assert payload["hasEducationComment"] is True
    assert payload["hasConstructionComment"] is False
    assert payload["selectorValue"] == "Educational Services"


def test_services_industry_selector_change_updates_detail_and_state():
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
          period: "2026-06-01",
          source_url: "https://example.com/services/june",
          growing_industries: [{ industry: "Construction", rank: 1 }],
          contracting_industries: [{ industry: "Educational Services", rank: 1 }],
          industries: [
            {
              industry: "Construction",
              direction: "growth",
              rank: 1,
              direction_change: null,
              rank_change: -3,
              streak: { direction: "growth", months: 2 },
              trend: [],
              component_signals: [],
              component_coverage: { listed_components: 0, available_components: 10 },
              comments: ["Construction comment."],
            },
            {
              industry: "Educational Services",
              direction: "contraction",
              rank: 1,
              direction_change: null,
              rank_change: null,
              streak: { direction: "contraction", months: 1 },
              trend: [],
              component_signals: [],
              component_coverage: { listed_components: 0, available_components: 10 },
              comments: ["Education comment."],
            },
          ],
        };

        function fakeButton(industry) {
          return {
            dataset: { servicesIndustry: industry },
            classList: { toggle: () => {} },
            setAttribute(name, value) { this[name] = value; },
            addEventListener: () => {},
          };
        }
        const detail = { innerHTML: "" };
        const selector = {
          value: "Construction",
          addEventListener(type, handler) {
            this.eventType = type;
            this.handler = handler;
          },
        };
        const buttons = [fakeButton("Construction"), fakeButton("Educational Services")];
        const body = {
          querySelector: (selectorName) => {
            if (selectorName === "[data-services-industry-detail]") return detail;
            if (selectorName === "[data-services-industry-select]") return selector;
            return null;
          },
          querySelectorAll: () => buttons,
        };

        hooks.bindServicesIndustrySelector(body, analysis);
        selector.value = "Educational Services";
        selector.handler();

        console.log(JSON.stringify({
          hasEducationComment: detail.innerHTML.indexOf("Education comment.") !== -1,
          hasConstructionComment: detail.innerHTML.indexOf("Construction comment.") !== -1,
          selectedServicesIndustry: hooks.state.selectedServicesIndustry,
          button0AriaPressed: buttons[0]["aria-pressed"],
          button1AriaPressed: buttons[1]["aria-pressed"],
          selectorValue: selector.value,
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

    assert payload["hasEducationComment"] is True
    assert payload["hasConstructionComment"] is False
    assert payload["selectedServicesIndustry"] == "Educational Services"
    assert payload["button0AriaPressed"] in ("false", False)
    assert payload["button1AriaPressed"] in ("true", True)
    assert payload["selectorValue"] == "Educational Services"


def test_services_full_evidence_excludes_bulk_industry_content():
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
          at_a_glance_rows: [
            { series_id: "ism_services_pmi", label: "Services PMI", current_value: 54.0, previous_value: 53.8, point_change: 0.2, direction: "Growing", rate_of_change: "Faster", trend_months: 2 },
          ],
          component_industries: [
            { signal_type: "business_activity", direction: "growth", industry: "Construction", rank: 1 },
          ],
          respondent_comments: [
            { industry: "Construction", comment_text: "Bulk report comment." },
          ],
          commodities: [
            { commodity: "Aluminum", signal_type: "up_in_price", months: 4 },
          ],
          narrative_facts: { consecutive_expansion_months: 24 },
          source: {
            report_id: "ism_services_2026_06",
            report_month: "2026-06-01",
            title: "June 2026 ISM Services PMI Report",
            source_url: "https://www.ismworld.org/example",
            source_hash: "abc123",
          },
        };

        const html = hooks.renderServicesFullEvidence(evidence);

        console.log(JSON.stringify({
          hasAllComponents: html.indexOf("All Components") !== -1,
          hasServicesPMI: html.indexOf("Services PMI") !== -1,
          hasPriceIncreased: html.indexOf("Prices increased") !== -1,
          hasNarrativeFacts: html.indexOf("Narrative Facts") !== -1,
          hasOfficialLink: html.indexOf("Official ISM Report") !== -1,
          hasComponentLists: html.indexOf("Component Industry Lists") !== -1,
          hasBulkComment: html.indexOf("Bulk report comment") !== -1,
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

    assert payload["hasAllComponents"] is True
    assert payload["hasServicesPMI"] is True
    assert payload["hasPriceIncreased"] is True
    assert payload["hasNarrativeFacts"] is True
    assert payload["hasOfficialLink"] is True
    assert payload["hasComponentLists"] is False
    assert payload["hasBulkComment"] is False


def test_services_signal_trend_detail_view_replaces_old_sections():
    script = textwrap.dedent(
        """
        const fs = require("fs");
        const vm = require("vm");

        global.window = { __MEOWSTREET_TEST__: true };
        global.document = { getElementById: () => null };
        global.fetch = async () => ({ ok: true, status: 200, json: async () => ({ markets: [] }) });
        global.$ = () => ({ textContent: "" });
        global.loadUsRatesLiquidity = async () => {};
        global.loadGdpRelationshipOverview = async () => {};
        global.loadGrowthCycle = async () => {};
        global.loadConsumerSentiment = async () => {};
        global.loadMarketSetup = async () => {};
        process.on("unhandledRejection", () => {});
        vm.runInThisContext(fs.readFileSync("static/macro-dashboard.js", "utf8"));
        const hooks = window.__macroDashboardTestHooks;

        const industry = {
          industry: "Construction",
          direction: "growth",
          rank: 1,
          direction_change: null,
          rank_change: 0,
          streak: { direction: "growth", months: 2 },
          comments: ["Pipeline remains healthy."],
          signal_trend: [
            {
              period: "2026-06-01",
              overall: { status: "listed", direction: "growth", direction_label: "Growth", rank: 1, list_size: 14 },
              components: {
                business_activity: { status: "listed", direction: "increase", direction_label: "Increase", rank: 2, list_size: 8 },
                new_orders: { status: "unavailable", direction: null, direction_label: "Unavailable", rank: null, list_size: null },
                employment: { status: "unavailable", direction: null, direction_label: "Unavailable", rank: null, list_size: null },
                supplier_deliveries: { status: "unavailable", direction: null, direction_label: "Unavailable", rank: null, list_size: null },
                inventories: { status: "unavailable", direction: null, direction_label: "Unavailable", rank: null, list_size: null },
                inventory_sentiment: { status: "unavailable", direction: null, direction_label: "Unavailable", rank: null, list_size: null },
                prices: { status: "unavailable", direction: null, direction_label: "Unavailable", rank: null, list_size: null },
                backlog: { status: "unavailable", direction: null, direction_label: "Unavailable", rank: null, list_size: null },
                new_export_orders: { status: "unavailable", direction: null, direction_label: "Unavailable", rank: null, list_size: null },
                imports: { status: "unavailable", direction: null, direction_label: "Unavailable", rank: null, list_size: null },
              },
            },
          ],
        };
        const analysis = {
          status: "available",
          period: "2026-06-01",
          source_url: "https://example.com/services/june",
        };

        const html = hooks.renderServicesIndustryDetailView(industry, analysis);
        console.log(JSON.stringify({
          hasSignalTrend: html.indexOf("Signal Trend") !== -1,
          hasGrowth: html.indexOf("Growth") !== -1,
          hasIncrease: html.indexOf("Increase") !== -1,
          hasRank1_14: html.indexOf("#1/14") !== -1,
          hasRank2_8: html.indexOf("#2/8") !== -1,
          hasComments: html.indexOf("Pipeline remains healthy.") !== -1,
          hasSource: html.indexOf("Official ISM Report") !== -1,
          hasComponentEvidence: html.indexOf("Component Evidence") === -1,
          hasRankHistory: html.indexOf("Rank History") === -1,
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
    assert payload["hasSignalTrend"] is True
    assert payload["hasGrowth"] is True
    assert payload["hasIncrease"] is True
    assert payload["hasRank1_14"] is True
    assert payload["hasRank2_8"] is True
    assert payload["hasComments"] is True
    assert payload["hasSource"] is True
    assert payload["hasComponentEvidence"] is True
    assert payload["hasRankHistory"] is True


def test_services_industry_selector_preserves_valid_selection_and_escapes_names():
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

        const industry = {
          industry: 'Health <Care> & "Social"',
          direction: "contraction",
          rank: 1,
          direction_change: null,
          rank_change: null,
          streak: { direction: "contraction", months: 1 },
          trend: [],
          component_signals: [],
          component_coverage: {
            listed_components: 0,
            available_components: null,
            coverage_status: "unavailable",
          },
          comments: [],
        };
        const contractionOnly = {
          status: "available",
          period: "2026-06-01",
          growing_industries: [],
          contracting_industries: [{ industry: industry.industry, rank: 1 }],
          industries: [industry],
        };

        hooks.state.selectedServicesIndustry = "Stale Industry";
        const fallbackHtml = hooks.renderServicesIndustryAnalysisSection(contractionOnly);
        const fallbackSelection = hooks.state.selectedServicesIndustry;

        hooks.state.selectedServicesIndustry = industry.industry;
        const preservedHtml = hooks.renderServicesIndustryAnalysisSection(contractionOnly);

        console.log(JSON.stringify({
          fallbackSelection,
          preservedSelection: hooks.state.selectedServicesIndustry,
          escapedOption: preservedHtml.includes(
            '<option value="Health &lt;Care&gt; &amp; &quot;Social&quot;" selected>'
          ),
          escapedButton: preservedHtml.includes(
            'data-services-industry="Health &lt;Care&gt; &amp; &quot;Social&quot;"'
          ),
          hasEmptyGrowthMessage: fallbackHtml.includes("No growing industries"),
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

    assert payload["fallbackSelection"] == 'Health <Care> & "Social"'
    assert payload["preservedSelection"] == 'Health <Care> & "Social"'
    assert payload["escapedOption"] is True
    assert payload["escapedButton"] is True
    assert payload["hasEmptyGrowthMessage"] is True


def test_macro_dashboard_js_has_consumer_sentiment_loading():
    js = STATIC_JS.read_text()
    assert "loadConsumerSentiment" in js
    assert "renderConsumerSentiment" in js
    assert "consumerSentimentError" in js
    assert 'fetch("/api/macro-dashboard/consumer-sentiment")' in js


def test_macro_dashboard_js_consumer_sentiment_card_has_detail_click():
    js = STATIC_JS.read_text()
    assert "selectedConsumerDetailId" in js
    assert "data-consumer-detail-id" in js
    assert "renderConsumerDetailInPanel" in js
    assert 'fetch("/api/macro-dashboard/consumer-sentiment/detail")' in js


def test_macro_dashboard_js_consumer_sentiment_error_has_retry():
    js = STATIC_JS.read_text()
    assert "data-consumer-retry" in js


def test_macro_dashboard_js_consumer_sentiment_detail_error_has_retry():
    js = STATIC_JS.read_text()
    assert "data-consumer-detail-retry" in js


def test_macro_dashboard_js_consumer_sentiment_error_uses_polite_live_region():
    js = STATIC_JS.read_text()
    assert 'role="status"' in js


def test_consumer_sentiment_js_exposes_required_interfaces():
    js = (ROOT / "static" / "consumer-sentiment.js").read_text()
    assert "renderLoading" in js
    assert "renderCard" in js
    assert "renderDetailInPanel" in js
    assert "window.consumerSentimentUi" in js


def test_consumer_sentiment_js_detail_includes_chart():
    js = (ROOT / "static" / "consumer-sentiment.js").read_text()
    assert "__chartHelpers" in js
    assert "renderRelationshipLineChart" in js


def test_consumer_sentiment_js_does_not_invent_missing_provenance():
    js = (ROOT / "static" / "consumer-sentiment.js").read_text()
    assert '"FRED"' not in js


def test_consumer_sentiment_js_no_status_current_label():
    js = (ROOT / "static" / "consumer-sentiment.js").read_text()
    assert "Status: Current" not in js
    assert ">Status<" not in js


def test_consumer_sentiment_js_has_aligned_period_text():
    js = (ROOT / "static" / "consumer-sentiment.js").read_text()
    assert "card-period" in js or "card-warning" in js


def test_consumer_sentiment_js_no_fomc_policy_context():
    js = (ROOT / "static" / "consumer-sentiment.js").read_text()
    assert "FOMC Policy Context" not in js
    assert "fomc_tone" not in js


def test_consumer_sentiment_js_no_visible_provenance_table():
    js = (ROOT / "static" / "consumer-sentiment.js").read_text()
    assert ">Provenance<" not in js
    assert "Provenance" not in js or all(
        "Provenance" not in line or "provenance" not in line.lower() or "<!--" in line
        for line in js.split("\n")
    )


def test_consumer_sentiment_js_has_capacity_evidence_section():
    js = (ROOT / "static" / "consumer-sentiment.js").read_text()
    assert "Consumer Capacity Evidence" in js
    assert "consumer-capacity-section" in js
    assert "consumer-capacity-headline" in js
    assert "consumer-capacity-drivers" in js


def test_consumer_sentiment_js_has_primary_signal_badge():
    js = (ROOT / "static" / "consumer-sentiment.js").read_text()
    assert "consumer-signal-primary" in js
    assert "Primary" in js
    assert "consumer-signal-primary-badge" in js


def test_consumer_sentiment_js_has_aligned_month_in_summary():
    js = (ROOT / "static" / "consumer-sentiment.js").read_text()
    assert "summary.aligned_month" not in js
    assert "data_status" in js


def test_consumer_sentiment_js_has_combined_chart():
    js = (ROOT / "static" / "consumer-sentiment.js").read_text()
    assert "aggregate" in js
    assert "expectations" in js
    assert "current_conditions" in js
    assert "UMCSI Components" in js
    assert "renderRelationshipLineChart" in js


def test_consumer_sentiment_js_has_raw_values_disclosure():
    js = (ROOT / "static" / "consumer-sentiment.js").read_text()
    assert "Raw capacity observations" in js
    assert "consumer-raw-values" in js
    assert "Real Rate (10Y - CPI)" not in js
    assert "TIPS 10Y" not in js


def test_consumer_sentiment_js_has_household_debt_quarter_note():
    js = (ROOT / "static" / "consumer-sentiment.js").read_text()
    assert "household_debt_gdp_quarter_note" in js
    assert "quarterNote" in js
    assert "consumer-quarter-note" not in js


def test_consumer_sentiment_js_no_standalone_real_rate_chart():
    js = (ROOT / "static" / "consumer-sentiment.js").read_text()
    assert "Real Rate" not in js
    assert "realRate" not in js
    assert "real_rate" not in js


def test_consumer_sentiment_js_driver_cards_show_date():
    js = (ROOT / "static" / "consumer-sentiment.js").read_text()
    assert "consumer-driver-date" in js
    assert "d.latest_date" in js


def test_consumer_sentiment_js_shows_missing_drivers():
    js = (ROOT / "static" / "consumer-sentiment.js").read_text()
    assert "consumer-driver-missing" in js
    assert "Data unavailable" in js


def test_consumer_sentiment_css_has_signal_card_styles():
    css = (ROOT / "static" / "consumer-sentiment.css").read_text()
    assert ".consumer-signal-grid" in css
    assert ".consumer-signal-card" in css
    assert ".consumer-signal-primary" in css
    assert ".consumer-signal-primary-badge" in css


def test_consumer_sentiment_css_has_decision_summary_styles():
    css = (ROOT / "static" / "consumer-sentiment.css").read_text()
    assert ".consumer-v2-summary" in css
    assert ".consumer-primary-read" in css
    assert ".consumer-method-note" in css


def test_consumer_sentiment_css_has_capacity_section_styles():
    css = (ROOT / "static" / "consumer-sentiment.css").read_text()
    assert ".consumer-capacity-section" in css
    assert ".consumer-capacity-headline" in css
    assert ".consumer-capacity-drivers" in css
    assert ".consumer-capacity-driver" in css
    assert ".consumer-driver-context" in css
    assert ".consumer-raw-values" in css


def test_consumer_sentiment_css_has_mobile_styles():
    css = (ROOT / "static" / "consumer-sentiment.css").read_text()
    assert "@media (max-width: 820px)" in css


def test_consumer_sentiment_css_has_panel_layout_styles():
    css = (ROOT / "static" / "consumer-sentiment.css").read_text()
    assert ".macro-shell.panel-open .consumer-signal-grid" in css
    assert ".macro-shell.panel-open.panel-expanded .consumer-signal-grid" in css


def test_consumer_sentiment_css_has_tabular_number_style():
    css = (ROOT / "static" / "consumer-sentiment.css").read_text()
    assert "tabular-nums" in css


def test_consumer_sentiment_js_detail_excludes_buy_sell_gdp_sp():
    js = (ROOT / "static" / "consumer-sentiment.js").read_text()
    assert "buy" not in js.lower()
    assert "sell" not in js.lower()
    lower_js = js.lower()
    assert "gdp" not in lower_js or all(
        "gdp" not in lower_js
        or "household_debt_to_gdp" in js
        or "household_debt_gdp" in js
        for _ in [1]
    )


def test_consumer_sentiment_js_no_method_validation():
    js = (ROOT / "static" / "consumer-sentiment.js").read_text()
    assert "method validation" not in js.lower()


def test_consumer_sentiment_card_renders_v2_compact_rows():
    script = textwrap.dedent(r"""
        const fs = require("fs");
        const vm = require("vm");
        global.window = {};
        global.document = {};
        vm.runInThisContext(
          fs.readFileSync("static/consumer-sentiment.js", "utf8")
        );

        const summary = {
          method_version: 2,
          data_status: "aligned_period",
          aligned_month: "2026-05-01",
          primary_signal: {
            percentile_zone: "depressed",
            momentum: "weakening",
            headline: "Depressed \u00b7 Weakening"
          },
          confirmation: {
            state: "broadly_confirmed",
            aggregate_confirms: true,
            current_conditions_confirms: true
          },
          expectations: {
            value: 44.1,
            percentile_label: "8th percentile",
            percentile_zone: "depressed",
            point_change: -4.0,
            point_change_unit: "index_points",
            momentum: "weakening",
            role: "primary"
          },
          aggregate: {
            value: 44.8,
            percentile_label: "6th percentile",
            percentile_zone: "depressed",
            point_change: -3.5,
            point_change_unit: "index_points",
            momentum: "weakening",
            role: "confirmation",
            confirms_primary: true
          },
          current_conditions: {
            value: 45.8,
            percentile_label: "9th percentile",
            percentile_zone: "depressed",
            point_change: -6.7,
            point_change_unit: "index_points",
            momentum: "weakening",
            role: "confirmation",
            confirms_primary: true
          },
          ability_read: {
            financing: { label: "Financing", state: "easing" },
            leverage: { label: "Leverage", state: "rising" },
            saving: { label: "Saving", state: "unchanged" }
          },
          capacity_as_of: {
            household_debt_to_gdp: "2025-04-01",
            household_debt_service_ratio: "2026-01-01",
            personal_saving_rate: "2026-05-01",
            one_to_four_family_mortgage_liabilities: "2026-01-01"
          },
          capacity_evidence: {
            headline: "This long headline belongs in Detail.",
            explanation: "This long explanation also belongs in Detail."
          }
        };

        const html = window.consumerSentimentUi.renderCard(summary);
        console.log(JSON.stringify({
          hasZoneChip: html.includes('consumer-state-chip consumer-zone-depressed')
            && html.includes(">Depressed</span>"),
          hasMomentumChip: html.includes('consumer-state-chip consumer-momentum-weakening')
            && html.includes(">Weakening</span>"),
          hasNoDuplicateCardTitle: !html.includes('class="ism-card-title">Consumer Sentiment'),
          hasExpectations:
            html.includes("Expectations")
            && html.includes("8th percentile")
            && html.includes("\u2193 4.0 pts")
            && html.includes("Primary"),
          hasAggregate:
            html.includes("Aggregate")
            && html.includes("6th percentile")
            && html.includes("Confirms Expectations"),
          hasCurrent:
            html.includes("Current Conditions")
            && html.includes("9th percentile")
            && html.includes("Confirms Expectations"),
          hasAbilityRows:
            html.includes("Financing")
            && html.includes("Easing")
            && html.includes("Leverage")
            && html.includes("Rising")
            && html.includes("Saving")
            && html.includes("Unchanged"),
          identifiesMixedAbilityDates: html.includes("Household context \u00b7 observation periods vary"),
          noSentimentMonthInCard: !html.includes("Sentiment as of"),
          noSeriesAligned: !html.includes("Series aligned"),
          noLongCopy:
            !html.includes("This long headline")
            && !html.includes("This long explanation"),
          noLegacyCopy:
            !/Bullish|Bearish|Peak|Trough|Ambiguous|method/i.test(html),
          hasTrigger:
            html.includes(
              'data-consumer-detail-id="consumer_sentiment"'
            ),
          accessible:
            html.includes(
              "Consumer Sentiment: Depressed, Weakening, Broadly Confirmed"
            )
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
    assert all(payload.values()), payload


def test_consumer_sentiment_detail_shows_primary_state_once_and_card_has_pointer_cursor():
    script = textwrap.dedent("""
        const fs = require("fs"), vm = require("vm");
        global.window = { __chartHelpers: null };
        global.document = {};
        vm.runInThisContext(fs.readFileSync("static/consumer-sentiment.js", "utf8"));
        const body = { innerHTML: "" };
        window.consumerSentimentUi.renderDetailInPanel(body, {
          summary: {
            method_version: 2,
            primary_signal: { percentile_zone: "depressed", momentum: "improving", headline: "Depressed \\u00b7 Improving" },
            confirmation: { state: "broadly_confirmed" },
            aggregate: {}, expectations: {}, current_conditions: {},
            capacity_evidence: {}
          },
          capacity_interpretations: [], context: {}, history: {}, capacity: {}
        });
        const primaryRead = body.innerHTML.match(/<div class="consumer-primary-read[^>]*>([\\s\\S]*?)<\\/div>\\s*<p class="consumer-confirmation-read"/)[1];
        console.log(JSON.stringify({
          hasHeadline: primaryRead.includes("Depressed \\u00b7 Improving"),
          hasOnePrimaryState: (primaryRead.match(/Depressed/g) || []).length === 1
            && (primaryRead.match(/Improving/g) || []).length === 1,
        }));
    """)
    result = subprocess.run(
        ["node", "-e", script], cwd=ROOT, capture_output=True, check=True, text=True
    )
    payload = json.loads(result.stdout)
    assert payload["hasHeadline"] is True
    assert payload["hasOnePrimaryState"] is True

    css = (ROOT / "static" / "consumer-sentiment.css").read_text()
    assert ".consumer-card-button" in css
    assert "cursor: pointer" in css


def test_consumer_sentiment_detail_explains_percentile_zone_threshold_and_result():
    script = textwrap.dedent("""
        const fs = require("fs"), vm = require("vm");
        global.window = { __chartHelpers: null };
        global.document = {};
        vm.runInThisContext(fs.readFileSync("static/consumer-sentiment.js", "utf8"));
        const body = { innerHTML: "" };
        window.consumerSentimentUi.renderDetailInPanel(body, {
          summary: {
            method_version: 2,
            percentile_method: { lower_boundary: 15, upper_boundary: 85 },
            primary_signal: { percentile_zone: "depressed", momentum: "improving", headline: "Depressed \\u00b7 Improving" },
            confirmation: { state: "broadly_confirmed" },
            aggregate: {},
            expectations: { percentile_rank: 5, percentile_zone: "depressed" },
            current_conditions: {},
            capacity_evidence: {}
          },
          capacity_interpretations: [], context: {}, history: {}, capacity: {}
        });
        console.log(JSON.stringify({
          explainsLowerThreshold: body.innerHTML.includes("at or below the 15th percentile"),
          explainsUpperThreshold: body.innerHTML.includes("at or above the 85th percentile"),
          explainsCurrentResult: body.innerHTML.includes("5.00 percentile rank is Depressed"),
        }));
    """)
    result = subprocess.run(
        ["node", "-e", script], cwd=ROOT, capture_output=True, check=True, text=True
    )
    payload = json.loads(result.stdout)
    assert all(payload.values()), payload


def test_consumer_sentiment_explains_depressed_but_improving_as_early_stabilization():
    script = textwrap.dedent("""
        const fs = require("fs"), vm = require("vm");
        global.window = { __chartHelpers: null };
        global.document = {};
        vm.runInThisContext(fs.readFileSync("static/consumer-sentiment.js", "utf8"));
        const summary = {
          method_version: 2,
          data_status: "aligned_period",
          aligned_month: "2026-06-01",
          percentile_method: { lower_boundary: 15, upper_boundary: 85 },
          primary_signal: { percentile_zone: "depressed", momentum: "improving", headline: "Depressed \\u00b7 Improving" },
          confirmation: { state: "broadly_confirmed" },
          aggregate: { percentile_label: "5th percentile", percentile_zone: "depressed", role: "confirmation", confirms_primary: true },
          expectations: { percentile_rank: 5, percentile_label: "5th percentile", percentile_zone: "depressed", momentum: "improving", point_change: 2.1, role: "primary" },
          current_conditions: { percentile_label: "5th percentile", percentile_zone: "depressed", role: "confirmation", confirms_primary: true },
          ability_read: {}, capacity_evidence: {}
        };
        const body = { innerHTML: "" };
        const card = window.consumerSentimentUi.renderCard(summary);
        window.consumerSentimentUi.renderDetailInPanel(body, {
          summary, capacity_interpretations: [], context: {}, history: {}, capacity: {}
        });
        console.log(JSON.stringify({
          cardExplainsLevelAndChange: card.includes("Consumer expectations remain near a historical low, while the latest monthly reading has improved."),
          detailExplainsInterpretation: body.innerHTML.includes("This indicates early stabilization, not yet a confirmed demand recovery."),
        }));
    """)
    result = subprocess.run(
        ["node", "-e", script], cwd=ROOT, capture_output=True, check=True, text=True
    )
    payload = json.loads(result.stdout)
    assert all(payload.values()), payload


def test_consumer_sentiment_visual_states_use_distinct_zone_and_momentum_styles():
    css = (ROOT / "static" / "consumer-sentiment.css").read_text()

    assert ".consumer-sentiment" in css
    assert ".consumer-state-chip" in css
    assert ".consumer-zone-depressed" in css
    assert ".consumer-momentum-improving" in css
    assert ".consumer-signal-card.consumer-zone-depressed" in css
    assert ".consumer-signal-card.consumer-momentum-improving" in css
    assert ".consumer-group-heading" in css
    assert "white-space: nowrap" in css


def test_consumer_sentiment_card_uses_a_fixed_role_column_for_aligned_rows():
    css = (ROOT / "static" / "consumer-sentiment.css").read_text()

    assert (
        "grid-template-columns: minmax(9rem, 1fr) minmax(13rem, 1.4fr) 7rem 10.5rem"
        in css
    )


def test_consumer_sentiment_card_warns_only_for_mixed_periods():
    script = textwrap.dedent(r"""
        const fs = require("fs");
        const vm = require("vm");
        global.window = {};
        global.document = {};
        vm.runInThisContext(
          fs.readFileSync("static/consumer-sentiment.js", "utf8")
        );
        const metric = {
          value: 50,
          percentile_label: "10th percentile",
          percentile_zone: "depressed",
          point_change: -1,
          point_change_unit: "index_points",
          momentum: "weakening",
          role: "confirmation",
          confirms_primary: null
        };
        const html = window.consumerSentimentUi.renderCard({
          method_version: 2,
          data_status: "mixed_periods",
          aligned_month: null,
          primary_signal: {
            percentile_zone: "depressed",
            momentum: "weakening",
            headline: "Depressed \u00b7 Weakening"
          },
          confirmation: {
            state: "unavailable",
            aggregate_confirms: null,
            current_conditions_confirms: null
          },
          aggregate: metric,
          expectations: {
            ...metric,
            role: "primary",
            confirms_primary: null
          },
          current_conditions: metric,
          ability_read: {
            financing: { label: "Financing", state: "unavailable" },
            leverage: { label: "Leverage", state: "unavailable" },
            saving: { label: "Saving", state: "unavailable" }
          }
        });
        console.log(JSON.stringify({
          hasPeriodWarning: html.includes("Observation periods differ"),
          hasSeriesAligned: html.includes("Series aligned"),
          accessibleInLabel:
            html.match(/aria-label="[^"]*Observation periods differ[^"]*"/)
            !== null
        }));
    """)
    payload = json.loads(
        subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            check=True,
            text=True,
        ).stdout
    )
    assert payload["hasPeriodWarning"] is True
    assert payload["hasSeriesAligned"] is False
    assert payload["accessibleInLabel"] is True


def test_consumer_sentiment_card_responds_to_keyboard():
    script = textwrap.dedent(r"""
        const fs = require("fs");
        const vm = require("vm");
        const elements = {
          dashboardStatus: {},
          marketGrid: { innerHTML: "", querySelectorAll: () => [] },
          marketDetail: { innerHTML: "" },
        };
        global.window = { __MEOWSTREET_TEST__: true };
        global.document = { getElementById: (id) => elements[id] || { innerHTML: "", querySelectorAll: () => [] } };
        global.fetch = async () => ({ ok: true, status: 200, json: async () => ({ markets: [] }) });
        vm.runInThisContext(fs.readFileSync("static/macro-dashboard.js", "utf8"));

        let clicked = 0;
        const listeners = {};
        const element = {
          addEventListener: (type, handler) => { listeners[type] = handler; },
          click: () => { clicked++; },
        };
        window.__macroDashboardTestHooks.bindConsumerSentimentDetailTrigger(element);
        let prevented = 0;
        listeners.keydown({ key: "Enter", preventDefault: () => { prevented++; } });
        listeners.keydown({ key: " ", preventDefault: () => { prevented++; } });
        listeners.keydown({ key: "Tab", preventDefault: () => { prevented++; } });

        console.log(JSON.stringify({
          enterTriggersClick: clicked === 2,
          tabDoesNotTrigger: clicked === 2,
          preventsDefault: prevented === 2,
        }));
        process.exit(0);
    """)

    result = subprocess.run(
        ["node", "-e", script],
        cwd=ROOT,
        capture_output=True,
        check=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    assert payload["enterTriggersClick"] is True
    assert payload["tabDoesNotTrigger"] is True
    assert payload["preventsDefault"] is True


def test_consumer_sentiment_detail_shows_mixed_period_dates():
    script = textwrap.dedent("""
        const fs = require("fs"), vm = require("vm");
        global.window = { __chartHelpers: null };
        global.document = {};
        vm.runInThisContext(fs.readFileSync("static/consumer-sentiment.js", "utf8"));
        const ui = window.consumerSentimentUi, body = { innerHTML: "" };
        const s = {
          method_version: 2, data_status: "mixed_periods", aligned_month: null,
          percentile_method: { version: 2, window_months: 240, lower_boundary: 15, upper_boundary: 85, rank_method: "midrank" },
          primary_signal: { series_id: "umcsi_expectations", percentile_zone: "depressed", momentum: "weakening", headline: "Depressed \\u00b7 Weakening" },
          confirmation: { state: "unavailable", aggregate_confirms: null, current_conditions_confirms: null },
          expectations: { value: 44.1, date: "2026-05-01", point_change: -4, point_change_unit: "index_points", momentum: "weakening", percentile_rank: null, percentile_label: "Unavailable", percentile_zone: "percentile_unavailable", role: "primary" },
          aggregate: { value: 44.8, date: "2026-04-01", point_change: null, point_change_unit: "index_points", momentum: "unavailable", percentile_rank: null, percentile_label: "Unavailable", percentile_zone: "percentile_unavailable", role: "confirmation", confirms_primary: null },
          current_conditions: { value: 45.8, date: "2026-05-01", point_change: null, point_change_unit: "index_points", momentum: "unavailable", percentile_rank: null, percentile_label: "Unavailable", percentile_zone: "percentile_unavailable", role: "confirmation", confirms_primary: null },
          capacity_evidence: { headline: "x", explanation: "x" }
        };
        ui.renderDetailInPanel(body, { summary: s, percentile_windows: {}, capacity_interpretations: [], context: {}, history: {}, capacity: {} });
        const html = body.innerHTML;
        console.log(JSON.stringify({ hasDatesSection: html.includes("consumer-mixed-dates"), listsAggregateDate: html.includes("Aggregate: 2026-04-01"), listsExpectationsDate: html.includes("Expectations: 2026-05-01"), listsCurrentDate: html.includes("Current Conditions: 2026-05-01"), noAlignedDate: !html.includes("aligned") }));
    """)
    result = subprocess.run(
        ["node", "-e", script], cwd=ROOT, capture_output=True, check=True, text=True
    )
    payload = json.loads(result.stdout)
    assert payload["hasDatesSection"] is True
    assert payload["listsAggregateDate"] is True
    assert payload["listsExpectationsDate"] is True
    assert payload["listsCurrentDate"] is True
    assert payload["noAlignedDate"] is True


def test_consumer_sentiment_detail_shows_unavailable_percentile_rank():
    script = textwrap.dedent("""
        const fs = require("fs"), vm = require("vm");
        global.window = { __chartHelpers: null };
        global.document = {};
        vm.runInThisContext(fs.readFileSync("static/consumer-sentiment.js", "utf8"));
        const ui = window.consumerSentimentUi, body = { innerHTML: "" };
        const s = {
          method_version: 2, data_status: "aligned_period", aligned_month: "2026-05-01",
          percentile_method: { version: 2, window_months: 240, lower_boundary: 15, upper_boundary: 85, rank_method: "midrank" },
          primary_signal: { series_id: "umcsi_expectations", percentile_zone: "percentile_unavailable", momentum: "unavailable", headline: "Primary sentiment percentile is unavailable." },
          confirmation: { state: "unavailable", aggregate_confirms: null, current_conditions_confirms: null },
          expectations: { value: 44.1, point_change: -4, point_change_unit: "index_points", momentum: "unavailable", percentile_rank: null, percentile_label: "Unavailable", percentile_zone: "percentile_unavailable", role: "primary" },
          aggregate: { value: 44.8, point_change: null, point_change_unit: "index_points", momentum: "unavailable", percentile_rank: null, percentile_label: "Unavailable", percentile_zone: "percentile_unavailable", role: "confirmation", confirms_primary: null },
          current_conditions: { value: 45.8, point_change: null, point_change_unit: "index_points", momentum: "unavailable", percentile_rank: null, percentile_label: "Unavailable", percentile_zone: "percentile_unavailable", role: "confirmation", confirms_primary: null },
          capacity_evidence: { headline: "x", explanation: "x" }
        };
        ui.renderDetailInPanel(body, { summary: s, percentile_windows: { aggregate: { start: null, end: null, observation_count: 0 }, expectations: { start: null, end: null, observation_count: 0 }, current_conditions: { start: null, end: null, observation_count: 0 } }, capacity_interpretations: [], context: {}, history: {}, capacity: {} });
        const html = body.innerHTML;
        console.log(JSON.stringify({ avoidsZeroPercentile: !html.includes("0.00 percentile") && html.includes("percentile rank unavailable"), headlineUnavailable: html.includes("Primary sentiment percentile is unavailable."), momentumUnavailable: html.includes("unavailable") && !html.includes("0.00") }));
    """)
    result = subprocess.run(
        ["node", "-e", script], cwd=ROOT, capture_output=True, check=True, text=True
    )
    payload = json.loads(result.stdout)
    assert payload["avoidsZeroPercentile"] is True
    assert payload["headlineUnavailable"] is True
    assert payload["momentumUnavailable"] is True


def test_consumer_sentiment_detail_shows_missing_drivers():
    script = textwrap.dedent("""
        const fs = require("fs");
        const vm = require("vm");

        global.window = { __chartHelpers: null };
        global.document = {};

        vm.runInThisContext(fs.readFileSync("static/consumer-sentiment.js", "utf8"));

        const ui = window.consumerSentimentUi;
        const body = { innerHTML: "" };

        const payload = {
          summary: {
            method_version: 2,
            data_status: "missing",
            primary_signal: { series_id: "umcsi_expectations", percentile_zone: "percentile_unavailable", momentum: "unavailable", headline: "Primary sentiment percentile is unavailable." },
            confirmation: { state: "unavailable", aggregate_confirms: null, current_conditions_confirms: null },
            aggregate: { role: "confirmation", confirms_primary: null },
            expectations: { role: "primary" },
            current_conditions: { role: "confirmation", confirms_primary: null },
            capacity_evidence: { headline: "Consumer capacity data is currently unavailable." },
          },
          capacity_interpretations: [
            { series_id: "household_debt_to_gdp", label: "Household Debt/GDP", available: false },
            { series_id: "household_debt_service_ratio", label: "Debt Service Ratio", available: false },
            { series_id: "personal_saving_rate", label: "Personal Saving Rate", available: true, direction: "unchanged", interpretation: "Personal saving rate is unchanged." },
            { series_id: "one_to_four_family_mortgage_liabilities", label: "Mortgage Liabilities", available: false },
            { series_id: "real_10y_rate", label: "Real 10Y Rate", available: true, direction: "unavailable", interpretation: "Single real rate observation \\u2014 direction cannot be determined." },
          ],
          context: {},
          history: {},
          capacity: {},
        };

        ui.renderDetailInPanel(body, payload);
        const html = body.innerHTML;

        const capSection = html.substring(html.indexOf("consumer-capacity-section"));
        const results = {
          driverCount: (capSection.match(/consumer-capacity-driver[">\\s]/g) || []).length,
          unavailableCount: (capSection.match(/Data unavailable/g) || []).length,
          hasDirectionUnavailable: capSection.includes("direction cannot be determined"),
          hasUnchanged: capSection.includes("Personal saving rate is unchanged."),
          labels: Array.from(capSection.matchAll(/class="consumer-driver-label">([^<]+)<\\/span>/g)).map(function (match) { return match[1]; }),
          sample: capSection.substring(0, 800),
        };
        console.log(JSON.stringify(results));
    """)

    result = subprocess.run(
        ["node", "-e", script],
        cwd=ROOT,
        capture_output=True,
        check=True,
        text=True,
    )
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload["driverCount"] == 5, (
        f"Expected 5, got {payload['driverCount']}. Sample: {payload['sample']}"
    )
    assert payload["unavailableCount"] == 3
    assert payload["hasDirectionUnavailable"] is True
    assert payload["hasUnchanged"] is True
    assert payload["labels"] == [
        "Household Debt/GDP",
        "Debt Service Ratio",
        "Personal Saving Rate",
        "Mortgage Liabilities",
        "Real 10Y Rate",
    ]


def test_market_setup_presentation_exposes_consumer_demand_outlook():
    script = textwrap.dedent("""
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

        const payload = {
            expected_growth: {
                state: "aligned_expansion",
                expected_gdp_direction: "rising",
                consumer_demand: {
                    state: "confirms_expansion",
                    percentile_label: "91st percentile",
                    percentile_zone: "elevated",
                    momentum: "improving",
                    observation_period: "2026-06-01",
                    evidence_links: ["consumer_sentiment"],
                },
                consumer_demand_agreement: true,
                consumer_demand_conflict: false,
                evidence_links: ["ism_manufacturing", "ism_services", "consumer_sentiment"],
            },
        };

        const pr = hooks.buildMarketSetupPresentation(payload);
        const html = hooks.renderDetailedReasoning(pr);

        console.log(JSON.stringify({
            hasConsumerDemand: html.indexOf("Consumer Demand") >= 0,
            hasPercentile: html.indexOf("91st percentile") >= 0,
            hasDataEvidenceTarget: html.indexOf('data-evidence-target="consumerSentiment"') >= 0,
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

    assert payload["hasConsumerDemand"] is True
    assert payload["hasPercentile"] is True
    assert payload["hasDataEvidenceTarget"] is True


def test_market_setup_presentation_marks_unavailable_consumer_demand_as_pending():
    script = textwrap.dedent("""
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

        const payload = {
            expected_growth: {
                consumer_demand: { state: "unavailable" },
            },
        };

        const pr = hooks.buildMarketSetupPresentation(payload);
        const html = hooks.renderDetailedReasoning(pr);

        console.log(JSON.stringify({
            hasAwaiting: html.indexOf("Consumer Demand: Awaiting aligned percentile data") >= 0,
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

    assert payload["hasAwaiting"] is True


def test_housing_permits_card_uses_existing_growth_card_and_detail_hooks():
    js = (ROOT / "static" / "housing-permits-ui.js").read_text()
    assert 'data-growth-cycle-detail-id="housing_permits"' in js
    assert "housingPermitsUi" in js


def test_housing_permits_css_reuses_growth_card_tokens():
    css = (ROOT / "static" / "macro-dashboard.css").read_text()
    assert ".housing-permits-card" in css or ".m2-card" in css
    assert "var(--" in css or ".housing-permits-detail" in css


def test_growth_cycle_renders_housing_permits_card_in_dom_when_in_headline():
    script = textwrap.dedent("""
        const fs = require("fs");
        const vm = require("vm");

        const elements = {
          dashboardStatus: {},
          growthCycle: {
            innerHTML: '<div class="relationship-head"><h2>Growth Cycle</h2></div>',
            querySelector: function () {
              return { outerHTML: '<div class="relationship-head"><h2>Growth Cycle</h2></div>' };
            },
            querySelectorAll: function () { return []; },
          },
          marketGrid: { innerHTML: "", querySelectorAll: function () { return []; } },
        };

        global.window = { __MEOWSTREET_TEST__: true };
        global.document = {
          getElementById: function (id) { return elements[id] || {}; },
        };
        global.fetch = async function () { return { ok: true, status: 200, json: async function () { return { markets: [] }; } }; };

        vm.runInThisContext(fs.readFileSync("static/macro-dashboard.js", "utf8"));
        vm.runInThisContext(fs.readFileSync("static/housing-permits-ui.js", "utf8"));
        const hooks = window.__macroDashboardTestHooks;

        hooks.state.growthCycle = {
          headline: [
            { id: "ism_manufacturing", status: "missing" },
            { id: "survey_synthesis", status: "pending_inputs" },
            { id: "housing_permits", status: "unavailable", reason: "building permits observations are missing" },
            { id: "m2_money_supply", status: "missing" },
            { id: "fed_balance_sheet", status: "missing" },
          ],
          sections: [
            { id: "ism_manufacturing", title: "ISM Manufacturing", subtitle: "Growth evidence", cards: ["ism_manufacturing"], status: "missing" },
            { id: "housing_credit", title: "Housing / Credit", subtitle: "Permits evidence", cards: ["housing_permits"], status: "pending_inputs" },
            { id: "m2_liquidity", title: "M2 Liquidity", subtitle: "Liquidity evidence", cards: ["m2_money_supply"], status: "missing" },
            { id: "inflation_context", title: "Inflation Context", subtitle: "Inflation evidence", cards: [], status: "missing" },
            { id: "fomc_context", title: "FOMC", subtitle: "Policy evidence", cards: [], status: "missing" },
          ],
        };

        var sectionHtml = hooks.renderGrowthCycleSections(hooks.state.growthCycle.sections, hooks.state.growthCycle.headline);
        elements.growthCycle.innerHTML = '<div class="relationship-head"><h2>Growth Cycle</h2></div>' + '<div class="growth-section-list">' + sectionHtml + '</div>';

        var html = elements.growthCycle.innerHTML;
            console.log(JSON.stringify({
              hasHousingEvidenceId: html.indexOf('id="evidence-housing-permits"') >= 0,
              hasDataDetailId: html.indexOf('data-growth-cycle-detail-id="housing_permits"') >= 0,
              hasHousingSection: html.indexOf("Housing / Credit") >= 0,
              hasUnavailableReason: html.indexOf("building permits observations are missing") >= 0,
            }));
        """)

    result = subprocess.run(
        ["node", "-e", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)

    assert payload["hasHousingEvidenceId"] is True
    assert payload["hasDataDetailId"] is True
    assert payload["hasHousingSection"] is True
    assert payload["hasUnavailableReason"] is True


def test_housing_permits_renders_card_for_unavailable_state():
    script = textwrap.dedent("""
        const fs = require("fs");
        const vm = require("vm");

        const elements = { marketGrid: { innerHTML: "", querySelectorAll: function () { return []; } } };
        global.window = { __MEOWSTREET_TEST__: true };
        global.document = {
          getElementById: function (id) { return elements[id] || {}; },
        };
        global.fetch = async function () { return { ok: true, status: 200, json: async function () { return { markets: [] }; } }; };

        vm.runInThisContext(fs.readFileSync("static/macro-dashboard.js", "utf8"));
        vm.runInThisContext(fs.readFileSync("static/housing-permits-ui.js", "utf8"));
        const hooks = window.__macroDashboardTestHooks;

        var card = hooks.renderCard({ id: "housing_permits", status: "unavailable", reason: "building permits observations are missing" });

        console.log(JSON.stringify({
          hasEvidenceId: card.indexOf('id="evidence-housing-permits"') >= 0,
          hasReason: card.indexOf("building permits observations are missing") >= 0,
          hasDataDetailId: card.indexOf('data-growth-cycle-detail-id="housing_permits"') >= 0,
        }));
    """)

    result = subprocess.run(
        ["node", "-e", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)

    assert payload["hasEvidenceId"] is True
    assert payload["hasReason"] is True
    assert payload["hasDataDetailId"] is True


def test_housing_permits_card_explains_awaiting_confirmation_against_ism_path():
    script = textwrap.dedent("""
        const fs = require("fs");
        const vm = require("vm");

        global.window = { __MEOWSTREET_TEST__: true };
        global.document = { getElementById: function () { return {}; } };
        global.fetch = async function () { return { ok: true, status: 200, json: async function () { return { markets: [] }; } }; };

        vm.runInThisContext(fs.readFileSync("static/macro-dashboard.js", "utf8"));
        vm.runInThisContext(fs.readFileSync("static/housing-permits-ui.js", "utf8"));
        const hooks = window.__macroDashboardTestHooks;
        const html = hooks.renderCard({
          id: "housing_permits",
          status: "awaiting_confirmation",
          reason: "current monthly change conflicts with the 12-month yoy average",
          observation_period: "2026-06-01",
          latest: {
            permits_saar: 130.5,
            permits_mom_pct: 0.083,
            permits_yoy_pct: 0.0023,
            permits_yoy_12m_average: -0.023,
          },
        });

        console.log(JSON.stringify({
          hasStatus: html.indexOf("Could Not Confirm ISM Path") >= 0,
          hasConclusion: html.indexOf("住房端尚未确认 ISM 指向的增长路径") >= 0,
          hasReason: html.indexOf("current monthly change conflicts with the 12-month yoy average") >= 0,
          hasObservationRow: html.indexOf("Observation") >= 0,
        }));
    """)

    result = subprocess.run(
        ["node", "-e", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)

    assert payload["hasStatus"] is True
    assert payload["hasConclusion"] is True
    assert payload["hasReason"] is True
    assert payload["hasObservationRow"] is False


def test_housing_permits_detail_explains_confirmation_role_without_redundant_basis_block():
    script = textwrap.dedent("""
        const fs = require("fs");
        const vm = require("vm");

        global.window = {};
        global.document = {};
        vm.runInThisContext(fs.readFileSync("static/housing-permits-ui.js", "utf8"));

        const body = { innerHTML: "" };
        window.housingPermitsUi.renderDetail(body, {
          series_id: "building_permits",
          status: "awaiting_confirmation",
          reason: "current monthly change conflicts with the 12-month yoy average",
          observation_period: "2026-06-01",
          latest: { permits_saar: 130.5 },
          cross_validation: {
            survey_synthesis: {
              expected_gdp_direction: "slowing",
              underlying_alignment: "aligned",
            },
            permits: {
              primary_trend: "weakening",
              yoy_12m_average: -0.023,
              previous_yoy_12m_average: -0.0208,
              latest_mom: 0.083,
              latest_yoy: 0.0023,
            },
          },
          charts: [],
        }, {
          escapeHtml: function (value) { return String(value || ""); },
          bilingualLabel: function (value) { return value; },
          bilingualTitle: function (value) { return value; },
          titleCaseToken: function () { return "Building Permits"; },
          statusClass: function () { return "mixed"; },
          fmtNumber: function (value) { return String(value); },
          fmtSignedPctDecimal: function (value) { return (value * 100).toFixed(2) + "%"; },
          fmtMonthYear: function () { return "Jun 2026"; },
          renderGrowthCycleRangeControl: function () { return ""; },
          filterChartForRange: function (chart) { return chart; },
          getSelectedChartRange: function () { return "1y"; },
          renderRatesDetailChart: function () { return ""; },
          bindGrowthCycleRangeControl: function () {},
          attachRatesChartTooltips: function () {},
        });

        console.log(JSON.stringify({
          hasHousingRead: body.innerHTML.indexOf("Housing Read") >= 0,
          hasReadHeadline: body.innerHTML.indexOf("Could Not Confirm ISM Path") >= 0,
          hasReason: body.innerHTML.indexOf("current monthly change conflicts with the 12-month yoy average") >= 0,
          hasOldUseHeading: body.innerHTML.indexOf("How to Use This") >= 0,
          hasOldAssessmentHeading: body.innerHTML.indexOf("Current Assessment") >= 0,
          hasCrossCheck: body.innerHTML.indexOf("Cross-check") >= 0,
          hasIsmPath: body.innerHTML.indexOf("ISM path: <strong>slowing") >= 0,
          hasPermitTrend: body.innerHTML.indexOf("Permit primary trend: <strong>weakening") >= 0,
          hasQualifiedAlignedRead: body.innerHTML.indexOf("Longer-term permit trend aligns with the ISM slowdown path, but the latest monthly rebound conflicts with that trend, so this release cannot confirm the ISM path.") >= 0,
          hasBasisBlock: body.innerHTML.indexOf("Basis for This Judgment") >= 0,
          hasSurveySynthesis: body.innerHTML.indexOf("Survey Synthesis") >= 0,
          hasRepeatedSaar: body.innerHTML.indexOf("SAAR 130.5K") >= 0,
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

    assert payload["hasHousingRead"] is True
    assert payload["hasReadHeadline"] is True
    assert payload["hasReason"] is True
    assert payload["hasOldUseHeading"] is False
    assert payload["hasOldAssessmentHeading"] is False
    assert payload["hasCrossCheck"] is True
    assert payload["hasIsmPath"] is True
    assert payload["hasPermitTrend"] is True
    assert payload["hasQualifiedAlignedRead"] is True
    assert payload["hasBasisBlock"] is False
    assert payload["hasSurveySynthesis"] is False
    assert payload["hasRepeatedSaar"] is False


def test_housing_permits_detail_maps_each_signal_state_to_a_read_tone():
    script = textwrap.dedent("""
        const fs = require("fs");
        const vm = require("vm");

        global.window = {};
        global.document = {};
        vm.runInThisContext(fs.readFileSync("static/housing-permits-ui.js", "utf8"));

        const helpers = {
          escapeHtml: function (value) { return String(value || ""); },
          titleCaseToken: function () { return "Building Permits"; },
          statusClass: function () { return "mixed"; },
          fmtMonthYear: function () { return "Jun 2026"; },
          fmtSignedPctDecimal: function (value) { return String(value); },
          renderGrowthCycleRangeControl: function () { return ""; },
          filterChartForRange: function (chart) { return chart; },
          getSelectedChartRange: function () { return "1y"; },
          renderRatesDetailChart: function () { return ""; },
          bindGrowthCycleRangeControl: function () {},
          attachRatesChartTooltips: function () {},
          bilingualLabel: function (value) { return value; },
        };
        function render(status) {
          const body = { innerHTML: "" };
          window.housingPermitsUi.renderDetail(body, { series_id: "building_permits", status, charts: [] }, helpers);
          return body.innerHTML;
        }
        console.log(JSON.stringify({
          supportive: render("supports_growth_path").includes("housing-permits-assessment supportive"),
          warning: render("challenges_growth_path").includes("housing-permits-assessment warning"),
          mixed: render("awaiting_confirmation").includes("housing-permits-assessment mixed"),
          missing: render("unavailable").includes("housing-permits-assessment missing"),
        }));
    """)

    result = subprocess.run(
        ["node", "-e", script], cwd=ROOT, capture_output=True, check=True, text=True
    )

    assert json.loads(result.stdout) == {
        "supportive": True,
        "warning": True,
        "mixed": True,
        "missing": True,
    }

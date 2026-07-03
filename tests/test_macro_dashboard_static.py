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


def test_macro_dashboard_js_fetches_overview_and_lazy_loads_market_detail():
    js = (ROOT / "static" / "macro-dashboard.js").read_text()

    assert 'fetch("/api/macro-dashboard/market-phase")' in js
    assert (
        "fetch(`/api/macro-dashboard/market-phase/${encodeURIComponent(benchmarkId)}`)"
        in js
    )
    assert "marketDetailsById" in js
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
    assert "PLOT_WIDTH" in js
    assert "PLOT_HEIGHT" in js
    assert "function xAt(" in js
    assert "function yAt(" in js
    assert "function niceTicks(" in js
    assert "function yAxisTicks(" in js
    assert "function renderYAxisAndGrid(" in js
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
    assert "GDP / Market Relationship" in js
    assert "renderGdpRelationshipOverview" in js
    assert "renderGdpRelationshipDetail" in js
    assert "rolling_index_gdp_correlation" in js
    assert "same_direction_pct" in js
    assert "macro_relationship_confidence" in js
    assert "relationship_signal_usability" in js
    assert "portfolio_bias_status" in js
    assert "Index YoY vs GDP YoY" in js
    assert "Rolling correlation" in js
    assert "Quadnomial distribution" in js
    assert "Signal usability" in js
    assert "Mock data" not in js
    assert "Fake data" not in js
    assert "Mock data based on" not in js
    assert "portfolio_bias_status" in js
    assert "Index YoY vs GDP YoY" in js
    assert "Rolling correlation" in js
    assert "Quadnomial distribution" in js
    assert "Signal usability" in js
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
    assert ".gdp-detail" in css
    assert ".relationship-chart" in css
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
    assert payload["xAxisTickCount"] == 10
    assert payload["yAxisTickCount"] == 9
    assert payload["firstX"] == 50
    assert payload["lastX"] == 910
    assert payload["ticks"] == ["2020-01-01", "2020-01-02", "2020-01-03"]
    assert payload["longTickCount"] >= 9
    assert 'class="chart-x-label chart-x-label-last"' not in payload["xAxisMarkup"]
    assert 'text-anchor="middle"' in payload["xAxisMarkup"]
    assert 'x="-18"' not in payload["xAxisMarkup"]
    assert payload["yTicks"][0] <= 79
    assert payload["yTicks"][-1] >= 100


def test_macro_dashboard_js_removes_dot_layer_and_keeps_mouse_tooltip():
    js = (ROOT / "static" / "macro-dashboard.js").read_text()

    assert 'event.key === "Escape"' in js
    assert 'svg.addEventListener("mousemove"' in js
    assert 'svg.addEventListener("mouseleave", hide)' in js
    assert 'event.target.closest(".chart-dot")' not in js
    assert "const currentMarket = selectedMarket();" in js
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

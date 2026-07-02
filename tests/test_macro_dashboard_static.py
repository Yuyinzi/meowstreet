from pathlib import Path


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


def test_macro_dashboard_css_has_overview_and_chart_classes():
    css = (ROOT / "static" / "macro-dashboard.css").read_text()

    assert ".market-grid" in css
    assert ".market-card" in css
    assert ".market-detail" in css
    assert ".market-chart" in css
    assert ".chart-axis" in css
    assert ".chart-grid" in css
    assert ".chart-y-tick" in css

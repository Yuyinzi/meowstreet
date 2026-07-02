(function () {
  const state = {
    markets: [],
    selectedBenchmarkId: null,
  };

  function $(id) {
    return document.getElementById(id);
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function fmtStatus(value) {
    return String(value || "").replace(/_/g, " ");
  }

  function fmtNumber(value) {
    if (value === null || value === undefined) return "n/a";
    return Number(value).toLocaleString(undefined, { maximumFractionDigits: 2 });
  }

  function statusClass(market) {
    return market.latest.market_phase_status === "bear_market" ? "bear" : "bull";
  }

  function selectedMarket() {
    return state.markets.find((market) => market.benchmark_id === state.selectedBenchmarkId)
      || state.markets[0]
      || null;
  }

  function renderOverview() {
    const grid = $("marketGrid");
    grid.innerHTML = state.markets
      .map((market) => {
        const selected = market.benchmark_id === selectedMarket()?.benchmark_id ? " selected" : "";
        return `
          <button class="market-card market-card-${statusClass(market)}${selected}" type="button" data-benchmark-id="${escapeHtml(market.benchmark_id)}">
            <span class="market-region">${escapeHtml(market.region)}</span>
            <strong>${escapeHtml(market.title)}</strong>
            <span class="market-status">${escapeHtml(fmtStatus(market.latest.market_phase_status))}</span>
            <span class="market-meta">Drawdown ${escapeHtml(fmtNumber(market.latest.drawdown_pct))}%</span>
            <span class="market-meta">Through ${escapeHtml(market.data_through)}</span>
          </button>
        `;
      })
      .join("");

    grid.querySelectorAll(".market-card").forEach((button) => {
      button.addEventListener("click", () => {
        state.selectedBenchmarkId = button.dataset.benchmarkId;
        renderOverview();
        renderDetail();
      });
    });
  }

  function chartScale(series) {
    const allValues = series.flatMap((point) => [
      point.close,
      point.bear_market_level,
    ]);
    const min = Math.min(...allValues);
    const max = Math.max(...allValues);
    return { min, range: max - min || 1 };
  }

  function chartSegments(series, width, height, key, scale) {
    const values = series
      .map((point) => point[key])
      .filter((value) => value !== null && value !== undefined);
    if (!values.length) return [];
    const segments = [];
    let current = [];

    series.forEach((point, index) => {
        const value = point[key];
        if (value === null || value === undefined) {
          if (current.length) {
            segments.push(current);
            current = [];
          }
          return;
        }
        const x = series.length === 1 ? width / 2 : (index / (series.length - 1)) * width;
        const y = height - ((value - scale.min) / scale.range) * height;
        current.push(`${x.toFixed(2)},${y.toFixed(2)}`);
    });

    if (current.length) segments.push(current);
    return segments.map((segment) => segment.join(" "));
  }

  function renderChartPolylines(series, width, height, key, className, scale) {
    return chartSegments(series, width, height, key, scale)
      .map((points) => `<polyline class="chart-line ${className}" points="${escapeHtml(points)}"></polyline>`)
      .join("");
  }

  function renderMarketChart(market) {
    const recentSeries = market.series.slice(-900);
    const width = 960;
    const height = 320;
    const scale = chartScale(recentSeries);
    return `
      <svg class="market-chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(market.title)} market phase chart">
        ${renderChartPolylines(recentSeries, width, height, "bear_market_level", "chart-level", scale)}
        ${renderChartPolylines(recentSeries, width, height, "bull_market_index", "chart-bull", scale)}
        ${renderChartPolylines(recentSeries, width, height, "bear_market_index", "chart-bear", scale)}
      </svg>
      <div class="chart-legend">
        <span><i class="legend-bull"></i>Bull segment</span>
        <span><i class="legend-bear"></i>Bear segment</span>
        <span><i class="legend-level"></i>Bear/Bull level</span>
      </div>
    `;
  }

  function renderDetail() {
    const detail = $("marketDetail");
    const market = selectedMarket();
    if (!market) {
      detail.innerHTML = "";
      return;
    }
    const latest = market.latest;
    detail.innerHTML = `
      <div class="detail-head">
        <div>
          <p class="eyebrow">${escapeHtml(market.region)}</p>
          <h2>${escapeHtml(market.title)}</h2>
        </div>
        <span class="phase-pill phase-${statusClass(market)}">${escapeHtml(fmtStatus(latest.market_phase_status))}</span>
      </div>
      <div class="metric-strip">
        <div><span>Close</span><strong>${escapeHtml(fmtNumber(latest.close))}</strong></div>
        <div><span>Rolling High</span><strong>${escapeHtml(fmtNumber(latest.rolling_high))}</strong></div>
        <div><span>Bear/Bull Level</span><strong>${escapeHtml(fmtNumber(latest.bear_market_level))}</strong></div>
        <div><span>Drawdown</span><strong>${escapeHtml(fmtNumber(latest.drawdown_pct))}%</strong></div>
        <div><span>Data Through</span><strong>${escapeHtml(market.data_through)}</strong></div>
      </div>
      ${renderMarketChart(market)}
    `;
  }

  async function loadDashboard() {
    const response = await fetch("/api/macro-dashboard/market-phase");
    if (response.status === 500) {
      $("dashboardStatus").textContent = "Server error loading market data. Ensure scripts/import_benchmark_market_data.py has been run.";
      return;
    }
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const payload = await response.json();
    state.markets = payload.markets || [];
    state.selectedBenchmarkId = state.markets[0]?.benchmark_id || null;
    $("dashboardStatus").textContent = state.markets.length
      ? `${state.markets.length} benchmark markets loaded. Workbook-seeded data may be stale until refresh is added.`
      : "No benchmark market data found. Run scripts/import_benchmark_market_data.py.";
    renderOverview();
    renderDetail();
  }

  loadDashboard().catch((error) => {
    $("dashboardStatus").textContent = "Failed to load market phase data.";
    console.error(error);
  });
})();

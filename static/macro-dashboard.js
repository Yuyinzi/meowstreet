(function () {
  const state = {
    markets: [],
    selectedBenchmarkId: null,
    marketDetailsById: {},
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

  function chartScale(series, height) {
    const allValues = series.flatMap((point) => [
      point.close,
      point.bear_market_level,
    ]);
    const min = Math.min(...allValues);
    const max = Math.max(...allValues);
    return { min, range: max - min || 1, height };
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
        const y = scale.height - ((value - scale.min) / scale.range) * scale.height;
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

  function xAxisTicks(series, width) {
    if (!series.length) return [];
    const desiredTicks = 8;
    const step = Math.max(1, Math.floor((series.length - 1) / (desiredTicks - 1)));
    const ticks = [];
    for (let index = 0; index < series.length; index += step) {
      const point = series[index];
      ticks.push({
        date: point.date,
        x: series.length === 1 ? width / 2 : (index / (series.length - 1)) * width,
      });
    }
    const last = series[series.length - 1];
    if (ticks[ticks.length - 1]?.date !== last.date) {
      ticks.push({ date: last.date, x: width });
    }
    return ticks;
  }

  function fmtTickDate(value) {
    const [year, month, day] = String(value).split("-");
    return `${day}-${month}-${year.slice(2)}`;
  }

  function renderXAxisTicks(series, width, chartHeight) {
    return xAxisTicks(series, width)
      .map((tick) => `
        <g class="chart-tick" transform="translate(${tick.x.toFixed(2)} ${chartHeight})">
          <line y2="8"></line>
          <text y="24">${escapeHtml(fmtTickDate(tick.date))}</text>
        </g>
      `)
      .join("");
  }

  function renderMarketChart(market) {
    const fullSeries = market.series;
    const width = 960;
    const chartHeight = 300;
    const height = 350;
    const scale = chartScale(fullSeries, chartHeight);
    return `
      <svg class="market-chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(market.title)} market phase chart">
        ${renderChartPolylines(fullSeries, width, chartHeight, "bear_market_level", "chart-level", scale)}
        ${renderChartPolylines(fullSeries, width, chartHeight, "bull_market_index", "chart-bull", scale)}
        ${renderChartPolylines(fullSeries, width, chartHeight, "bear_market_index", "chart-bear", scale)}
        ${renderXAxisTicks(fullSeries, width, chartHeight)}
      </svg>
      <div class="chart-legend">
        <span><i class="legend-bull"></i>Bull segment</span>
        <span><i class="legend-bear"></i>Bear segment</span>
        <span><i class="legend-level"></i>Bear/Bull level</span>
      </div>
    `;
  }

  async function loadMarketDetail(benchmarkId) {
    if (state.marketDetailsById[benchmarkId]) {
      return state.marketDetailsById[benchmarkId];
    }
    const response = await fetch(`/api/macro-dashboard/market-phase/${encodeURIComponent(benchmarkId)}`);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const payload = await response.json();
    state.marketDetailsById[benchmarkId] = payload;
    return payload;
  }

  function renderDetail() {
    const detail = $("marketDetail");
    const market = selectedMarket();
    if (!market) {
      detail.innerHTML = "";
      return;
    }

    detail.innerHTML = `
      <div class="detail-head">
        <div>
          <p class="eyebrow">${escapeHtml(market.region)}</p>
          <h2>${escapeHtml(market.title)}</h2>
        </div>
        <span class="phase-pill phase-${statusClass(market)}">${escapeHtml(fmtStatus(market.latest.market_phase_status))}</span>
      </div>
      <p class="status">Loading chart data...</p>
    `;

    loadMarketDetail(market.benchmark_id)
      .then((detailMarket) => {
        if (state.selectedBenchmarkId !== detailMarket.benchmark_id) return;
        const latest = detailMarket.latest;
        detail.innerHTML = `
          <div class="detail-head">
            <div>
              <p class="eyebrow">${escapeHtml(detailMarket.region)}</p>
              <h2>${escapeHtml(detailMarket.title)}</h2>
            </div>
            <span class="phase-pill phase-${statusClass(detailMarket)}">${escapeHtml(fmtStatus(latest.market_phase_status))}</span>
          </div>
          <div class="metric-strip">
            <div><span>Close</span><strong>${escapeHtml(fmtNumber(latest.close))}</strong></div>
            <div><span>Rolling High</span><strong>${escapeHtml(fmtNumber(latest.rolling_high))}</strong></div>
            <div><span>Bear/Bull Level</span><strong>${escapeHtml(fmtNumber(latest.bear_market_level))}</strong></div>
            <div><span>Drawdown</span><strong>${escapeHtml(fmtNumber(latest.drawdown_pct))}%</strong></div>
            <div><span>Data Through</span><strong>${escapeHtml(detailMarket.data_through)}</strong></div>
          </div>
          ${renderMarketChart(detailMarket)}
        `;
      })
      .catch((error) => {
        if (state.selectedBenchmarkId !== market.benchmark_id) return;
        detail.innerHTML = `<p class="status">Failed to load chart data.</p>`;
        console.error(error);
      });
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

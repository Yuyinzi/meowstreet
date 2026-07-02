(function () {
  const state = {
    markets: [],
    selectedBenchmarkId: null,
    marketDetailsById: {},
  };

  const CHART_WIDTH = 960;
  const CHART_HEIGHT = 360;
  const MARGIN_LEFT = 50;
  const MARGIN_BOTTOM = 40;
  const PLOT_WIDTH = CHART_WIDTH - MARGIN_LEFT;
  const PLOT_HEIGHT = CHART_HEIGHT - MARGIN_BOTTOM;

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

  function xAt(index, count) {
    if (count <= 1) return MARGIN_LEFT + PLOT_WIDTH / 2;
    return MARGIN_LEFT + (index / (count - 1)) * PLOT_WIDTH;
  }

  function yAt(value, scale) {
    return scale.height - ((value - scale.min) / scale.range) * scale.height;
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
    return { min, range: max - min || 1, height: PLOT_HEIGHT };
  }

  function niceTicks(min, max, count) {
    const range = max - min || Math.abs(max) || 1;
    const rawStep = range / (count - 1);
    const exponent = Math.floor(Math.log10(rawStep));
    const fraction = rawStep / Math.pow(10, exponent);
    let niceFraction;
    if (fraction <= 1) niceFraction = 1;
    else if (fraction <= 2) niceFraction = 2;
    else if (fraction <= 5) niceFraction = 5;
    else niceFraction = 10;
    const step = niceFraction * Math.pow(10, exponent);
    const niceMin = Math.floor(min / step) * step;
    const niceMax = Math.ceil(max / step) * step;
    const ticks = [];
    const steps = Math.round((niceMax - niceMin) / step);
    for (let i = 0; i <= steps; i++) {
      ticks.push(niceMin + i * step);
    }
    return ticks;
  }

  function yAxisTicks(series, count) {
    const values = series.flatMap((point) => [point.close, point.bear_market_level]);
    return niceTicks(Math.min(...values), Math.max(...values), count);
  }

  function renderYAxisAndGrid(ticks, scale) {
    const gridAndTicks = ticks.map((value) => {
      const y = yAt(value, scale).toFixed(2);
      return `
        <g class="chart-grid">
          <line x1="${MARGIN_LEFT}" y1="${y}" x2="${CHART_WIDTH}" y2="${y}"></line>
        </g>
        <g class="chart-y-tick" transform="translate(${MARGIN_LEFT} ${y})">
          <line x1="-6" y1="0" x2="0" y2="0"></line>
          <text x="-10" y="4">${escapeHtml(fmtNumber(value))}</text>
        </g>
      `;
    }).join("");

    return `
      <g class="chart-axis">
        <line x1="${MARGIN_LEFT}" y1="0" x2="${MARGIN_LEFT}" y2="${PLOT_HEIGHT}"></line>
        <line x1="${MARGIN_LEFT}" y1="${PLOT_HEIGHT}" x2="${CHART_WIDTH}" y2="${PLOT_HEIGHT}"></line>
      </g>
      ${gridAndTicks}
    `;
  }

  function chartSegments(series, key, scale) {
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
      const x = xAt(index, series.length);
      const y = yAt(value, scale);
      current.push(`${x.toFixed(2)},${y.toFixed(2)}`);
    });

    if (current.length) segments.push(current);
    return segments.map((segment) => segment.join(" "));
  }

  function renderChartPolylines(series, key, className, scale) {
    return chartSegments(series, key, scale)
      .map((points) => `<polyline class="chart-line ${className}" points="${escapeHtml(points)}"></polyline>`)
      .join("");
  }

  function renderChartDots(series, scale) {
    return series
      .map((point, index) => {
        const x = xAt(index, series.length).toFixed(2);
        const y = yAt(point.close, scale).toFixed(2);
        const statusClass = point.market_phase_status === "bear_market" ? "chart-dot-bear" : "chart-dot-bull";
        const label = `${point.date}: close ${fmtNumber(point.close)}, ${fmtStatus(point.market_phase_status)}, drawdown ${fmtNumber(point.drawdown_pct)}%, level ${fmtNumber(point.bear_market_level)}`;
        return `<circle class="chart-dot ${statusClass}" cx="${x}" cy="${y}" r="2.5" tabindex="0" role="button" data-index="${index}" aria-label="${escapeHtml(label)}"></circle>`;
      })
      .join("");
  }

  function attachChartTooltip(svg, tooltip, series) {
    if (!svg || !tooltip || !series.length) return;
    const wrap = svg.parentElement;
    let lastIndex = -1;
    let tooltipRect = null;

    function show(index, clientX, clientY) {
      const point = series[index];
      if (index !== lastIndex) {
        tooltip.innerHTML = `
          <div><strong>${escapeHtml(point.date)}</strong></div>
          <div>Close: ${escapeHtml(fmtNumber(point.close))}</div>
          <div>Status: ${escapeHtml(fmtStatus(point.market_phase_status))}</div>
          <div>Drawdown: ${escapeHtml(fmtNumber(point.drawdown_pct))}%</div>
          <div>Bear/Bull Level: ${escapeHtml(fmtNumber(point.bear_market_level))}</div>
        `;
        lastIndex = index;
        tooltip.style.left = "-9999px";
        tooltip.style.top = "-9999px";
        tooltip.classList.add("visible");
        tooltipRect = tooltip.getBoundingClientRect();
      }
      const wrapRect = wrap.getBoundingClientRect();
      let left = clientX - wrapRect.left + 12;
      let top = clientY - wrapRect.top - tooltipRect.height - 12;
      if (left + tooltipRect.width > wrapRect.width) {
        left = wrapRect.width - tooltipRect.width - 8;
      }
      if (left < 0) {
        left = 8;
      }
      if (top < 0) {
        top = clientY - wrapRect.top + 16;
      }
      if (top + tooltipRect.height > wrapRect.height) {
        top = wrapRect.height - tooltipRect.height - 8;
      }
      tooltip.style.left = `${left}px`;
      tooltip.style.top = `${top}px`;
    }

    function hide() {
      tooltip.classList.remove("visible");
      lastIndex = -1;
      tooltipRect = null;
    }

    svg.addEventListener("mousemove", (event) => {
      const rect = svg.getBoundingClientRect();
      const scaleX = CHART_WIDTH / rect.width;
      const x = (event.clientX - rect.left) * scaleX - MARGIN_LEFT;
      const ratio = Math.max(0, Math.min(1, x / PLOT_WIDTH));
      const index = Math.min(
        series.length - 1,
        Math.max(0, Math.round(ratio * (series.length - 1)))
      );
      show(index, event.clientX, event.clientY);
    });

    svg.addEventListener("mouseleave", hide);

    svg.addEventListener("focusin", (event) => {
      const dot = event.target.closest(".chart-dot");
      if (!dot) return;
      const index = Number(dot.dataset.index);
      const rect = dot.getBoundingClientRect();
      show(index, rect.left + rect.width / 2, rect.top);
    });

    svg.addEventListener("focusout", hide);

    svg.addEventListener("keydown", (event) => {
      const dot = event.target.closest(".chart-dot");
      if (!dot) return;
      if (event.key !== "Enter" && event.key !== " ") return;
      event.preventDefault();
      const index = Number(dot.dataset.index);
      const rect = dot.getBoundingClientRect();
      show(index, rect.left + rect.width / 2, rect.top);
    });
  }

  function xAxisTicks(series) {
    if (!series.length) return [];
    const desiredTicks = 6;
    const step = Math.max(1, Math.floor((series.length - 1) / (desiredTicks - 1)));
    const ticks = [];
    for (let index = 0; index < series.length; index += step) {
      ticks.push({
        date: series[index].date,
        x: xAt(index, series.length),
      });
    }
    const last = series[series.length - 1];
    if (ticks[ticks.length - 1]?.date !== last.date) {
      ticks.push({ date: last.date, x: xAt(series.length - 1, series.length) });
    }
    return ticks;
  }

  function fmtMonthYear(value) {
    const date = new Date(`${value}T00:00:00`);
    if (Number.isNaN(date.getTime())) return value;
    return date.toLocaleDateString("en-US", { month: "short", year: "numeric" });
  }

  function renderXAxisTicks(series) {
    const ticks = xAxisTicks(series);
    return ticks
      .map((tick, index) => {
        const isLast = index === ticks.length - 1;
        const anchor = isLast ? "end" : "middle";
        const xOffset = isLast ? -6 : 0;
        return `
          <g class="chart-tick" transform="translate(${tick.x.toFixed(2)} ${PLOT_HEIGHT})">
            <line y2="8"></line>
            <text y="24" text-anchor="${anchor}" x="${xOffset}">${escapeHtml(fmtMonthYear(tick.date))}</text>
          </g>
        `;
      })
      .join("");
  }

  function renderMarketChart(market) {
    if (!market.series || !market.series.length) {
      return `<p class="status">No chart data available.</p>`;
    }
    const fullSeries = market.series;
    const scale = chartScale(fullSeries);
    return `
      <div class="chart-wrap">
        <svg class="market-chart" viewBox="0 0 ${CHART_WIDTH} ${CHART_HEIGHT}" role="img" aria-label="${escapeHtml(market.title)} market phase chart">
          ${renderYAxisAndGrid(yAxisTicks(fullSeries, 5), scale)}
          ${renderChartPolylines(fullSeries, "bear_market_level", "chart-level", scale)}
          ${renderChartPolylines(fullSeries, "bull_market_index", "chart-bull", scale)}
          ${renderChartPolylines(fullSeries, "bear_market_index", "chart-bear", scale)}
          ${renderChartDots(fullSeries, scale)}
          ${renderXAxisTicks(fullSeries)}
        </svg>
        <div class="chart-tooltip" aria-hidden="true"></div>
      </div>
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
        const svg = detail.querySelector(".market-chart");
        const tooltip = detail.querySelector(".chart-tooltip");
        attachChartTooltip(svg, tooltip, detailMarket.series);
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

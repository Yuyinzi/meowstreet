(function () {
  const state = {
    markets: [],
    selectedBenchmarkId: null,
    selectedRelationshipId: null,
    marketDetailsById: {},
    gdpRelationships: [],
    gdpRelationshipDetailsById: {},
  };

  const CHART_WIDTH = 960;
  const CHART_HEIGHT = 360;
  const MARGIN_LEFT = 50;
  const MARGIN_RIGHT = 50;
  const MARGIN_BOTTOM = 58;
  const PLOT_RIGHT = CHART_WIDTH - MARGIN_RIGHT;
  const PLOT_WIDTH = PLOT_RIGHT - MARGIN_LEFT;
  const PLOT_HEIGHT = CHART_HEIGHT - MARGIN_BOTTOM;
  const Y_AXIS_TICK_COUNT = 9;
  const X_AXIS_TICK_COUNT = 10;

  async function loadGdpRelationshipOverview() {
    const response = await fetch("/api/macro-dashboard/gdp-relationships");
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const payload = await response.json();
    state.gdpRelationships = payload.relationships || [];
    state.selectedRelationshipId = state.gdpRelationships[0]?.relationship_id || null;
    renderGdpRelationshipOverview();
  }


  async function loadGdpRelationshipDetail(relationshipId) {
    if (state.gdpRelationshipDetailsById[relationshipId]) {
      return state.gdpRelationshipDetailsById[relationshipId];
    }
    const response = await fetch(`/api/macro-dashboard/gdp-relationships/${encodeURIComponent(relationshipId)}`);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const payload = await response.json();
    state.gdpRelationshipDetailsById[relationshipId] = payload;
    return payload;
  }

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
    return String(value ?? "").replace(/_/g, " ");
  }

  function fmtNumber(value) {
    if (value === null || value === undefined) return "n/a";
    return Number(value).toLocaleString(undefined, { maximumFractionDigits: 2 });
  }

  function fmtPercent(value) {
    if (value === null || value === undefined) return "n/a";
    return `${fmtNumber(value)}%`;
  }

  function statusClass(market) {
    return market.latest.market_phase_status === "bear_market" ? "bear" : "bull";
  }

  function selectedMarket() {
    return state.markets.find((market) => market.benchmark_id === state.selectedBenchmarkId)
      || state.markets[0]
      || null;
  }

  function selectedRelationship() {
    return state.gdpRelationships.find((card) => card.relationship_id === state.selectedRelationshipId)
      || state.gdpRelationships[0]
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
    const currentMarket = selectedMarket();
    grid.innerHTML = state.markets
      .map((market) => {
        const selected = market.benchmark_id === currentMarket?.benchmark_id ? " selected" : "";
        return `
          <button class="market-card market-card-${statusClass(market)}${selected}" type="button" data-benchmark-id="${escapeHtml(market.benchmark_id)}">
            <span class="market-region">${escapeHtml(market.region)}</span>
            <strong>${escapeHtml(market.title)}</strong>
            <span class="market-status">${escapeHtml(fmtStatus(market.latest.market_phase_status))}</span>
            <span class="market-meta">Drawdown ${escapeHtml(fmtNumber(market.latest.drawdown_pct))}%</span>
            <span class="market-meta">Through ${escapeHtml(market.data_through)}</span>
            <span class="market-card-actions">
              <span class="market-refresh" role="button" tabindex="0" data-refresh-benchmark-id="${escapeHtml(market.benchmark_id)}" aria-label="Refresh ${escapeHtml(market.title)}" title="Refresh ${escapeHtml(market.title)}">↻</span>
            </span>
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

    grid.querySelectorAll(".market-refresh").forEach((button) => {
      button.addEventListener("click", (event) => {
        event.stopPropagation();
        refreshMarket(button.dataset.refreshBenchmarkId, button);
      });
      button.addEventListener("keydown", (event) => {
        if (event.key !== "Enter" && event.key !== " ") return;
        event.preventDefault();
        event.stopPropagation();
        refreshMarket(button.dataset.refreshBenchmarkId, button);
      });
    });
  }

  function confidenceClass(relationship) {
    return `confidence-${relationship.macro_relationship_confidence}`;
  }

  function ensureGdpRelationshipRoot() {
    const existing = $("gdpRelationshipSection");
    if (existing) return existing;
    const shell = $("macroDashboardApp");
    if (!shell) return null;
    shell.insertAdjacentHTML(
      "beforeend",
      `<section class="gdp-relationship" id="gdpRelationshipSection" aria-label="GDP market relationship"></section>`
    );
    return $("gdpRelationshipSection");
  }

  function renderGdpRelationshipOverview() {
    const section = ensureGdpRelationshipRoot();
    if (!section) return;
    const current = selectedRelationship();
    if (!state.gdpRelationships.length) {
      section.innerHTML = `
        <div class="relationship-head">
          <div>
            <h2>GDP / Market Relationship</h2>
            <p class="subtitle">Loading GDP relationship data...</p>
          </div>
        </div>
      `;
      return;
    }
    section.innerHTML = `
      <div class="relationship-head">
        <div>
          <p class="eyebrow">Method Video 03 workflow data</p>
          <h2>GDP / Market Relationship</h2>
          <p class="subtitle">GDP, index correlation, and quadnomial context.</p>
        </div>
      </div>
      <div class="gdp-grid">
        ${state.gdpRelationships.map((card) => {
          const selected = card.relationship_id === current?.relationship_id ? " selected" : "";
          return `
            <button class="gdp-card ${confidenceClass(card)}${selected}" type="button" data-relationship-id="${escapeHtml(card.relationship_id)}">
              <span class="market-region">${escapeHtml(card.region)}</span>
              <strong>${escapeHtml(card.title)}</strong>
              <span class="market-meta">${escapeHtml(card.economy)} | ${escapeHtml(card.primary_lag_months)} months lag</span>
              <span class="relationship-case">${escapeHtml(card.latest?.quadnomial_current_case)}</span>
              <span class="market-meta">Primary lag ${escapeHtml(card.primary_lag_months)} months</span>
              <span class="market-meta">Correlation ${escapeHtml(fmtNumber(card.latest?.rolling_index_gdp_correlation))}</span>
              <span class="market-meta">Same direction ${escapeHtml(fmtPercent(card.same_direction_pct))}</span>
              <span class="relationship-bias">${escapeHtml(card.relationship_signal_usability)}</span>
            </button>
          `;
        }).join("")}
      </div>
      <div class="gdp-detail" id="gdpRelationshipDetail"></div>
    `;

    section.querySelectorAll(".gdp-card").forEach((button) => {
      button.addEventListener("click", () => {
        state.selectedRelationshipId = button.dataset.relationshipId;
        renderGdpRelationshipOverview();
      });
    });

    renderGdpRelationshipDetail();
  }

  function chartPoints(series, key, min, max, width, height) {
    const range = max - min || 1;
    return series.map((point, index) => {
      const x = series.length <= 1 ? width / 2 : (index / (series.length - 1)) * width;
      const y = height - ((point[key] - min) / range) * height;
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    }).join(" ");
  }

  function renderMiniLineChart(title, series, keys) {
    const values = series.flatMap((point) => keys.map((key) => point[key]));
    const min = Math.min(...values);
    const max = Math.max(...values);
    const width = 360;
    const height = 150;
    return `
      <div class="relationship-chart">
        <div class="relationship-chart-head">
          <h3>${escapeHtml(title)}</h3>
          <span>${escapeHtml(series[0].label)}-${escapeHtml(series[series.length - 1].label)}</span>
        </div>
        <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(title)}">
          <line class="relationship-zero" x1="0" y1="${(height - ((0 - min) / ((max - min) || 1)) * height).toFixed(2)}" x2="${width}" y2="${(height - ((0 - min) / ((max - min) || 1)) * height).toFixed(2)}"></line>
          ${keys.map((key, index) => `
            <polyline class="relationship-line relationship-line-${index}" points="${escapeHtml(chartPoints(series, key, min, max, width, height))}"></polyline>
          `).join("")}
        </svg>
      </div>
    `;
  }

  function renderQuadBars(relationship) {
    return `
      <div class="relationship-chart">
        <div class="relationship-chart-head">
          <h3>Quadnomial distribution</h3>
          <span>Historical data</span>
        </div>
        <div class="quad-bars">
          ${relationship.quadnomial_distribution.map((item) => `
            <div class="quad-bar-row">
              <span>${escapeHtml(item.label)}</span>
              <strong>${escapeHtml(fmtPercent(item.value))}</strong>
              <i style="width: ${Math.max(4, item.value).toFixed(2)}%"></i>
            </div>
          `).join("")}
        </div>
      </div>
    `;
  }

  function renderLagComparison(relationship) {
    return `
      <div class="relationship-chart">
        <div class="relationship-chart-head">
          <h3>Lag comparison</h3>
          <span>Method primary lag</span>
        </div>
        <div class="lag-table">
          ${relationship.lag_correlations.map((lag) => `
            <div class="lag-row ${lag.method_primary ? "lag-row-primary" : ""}">
              <span>${escapeHtml(lag.label)}</span>
              <strong>${escapeHtml(fmtNumber(lag.value))}</strong>
              ${lag.method_primary ? '<em class="lag-primary-pill">Method primary</em>' : "<em></em>"}
            </div>
          `).join("")}
        </div>
      </div>
    `;
  }

  function renderGdpRelationshipDetail() {
    const detail = $("gdpRelationshipDetail");
    const card = selectedRelationship();
    if (!detail || !card) return;
    detail.innerHTML = `<p class="status">Loading GDP relationship detail...</p>`;

    loadGdpRelationshipDetail(card.relationship_id)
      .then((payload) => {
        if (state.selectedRelationshipId !== card.relationship_id) return;
        const latest = payload.latest || {};
        const indexYoy = latest.index_yoy !== null && latest.index_yoy !== undefined
          ? (latest.index_yoy * 100) : null;
        const gdpYoy = latest.gdp_yoy !== null && latest.gdp_yoy !== undefined
          ? (latest.gdp_yoy * 100) : null;
        detail.innerHTML = `
          <div class="detail-head">
            <div>
              <p class="eyebrow">${escapeHtml(card.economy)}</p>
              <h2>${escapeHtml(card.title)}</h2>
            </div>
            <span class="phase-pill ${confidenceClass(card)}">${escapeHtml(card.macro_relationship_confidence)} confidence</span>
          </div>
          <div class="metric-strip">
            <div><span>Index YoY</span><strong>${escapeHtml(fmtPercent(indexYoy))}</strong></div>
            <div><span>GDP YoY</span><strong>${escapeHtml(fmtPercent(gdpYoy))}</strong></div>
            <div><span>Rolling Correlation</span><strong>${escapeHtml(fmtNumber(latest.rolling_index_gdp_correlation))}</strong></div>
            <div><span>Same Direction</span><strong>${escapeHtml(fmtPercent(payload.same_direction_pct))}</strong></div>
            <div><span>Signal usability</span><strong>${escapeHtml(payload.relationship_signal_usability)}</strong></div>
            <div><span>Portfolio Bias</span><strong>${escapeHtml(payload.portfolio_bias_status)}</strong></div>
          </div>
          <section class="method-note" aria-label="GDP relationship method">
            <h3>Method</h3>
            <ul class="method-formula-list">
              <li>Index YoY vs GDP YoY compares market direction with economic growth direction.</li>
              <li>Rolling correlation checks whether the historical relationship is stable or breaking down.</li>
              <li>Quadnomial distribution buckets both-up, both-down, and opposite-direction cases.</li>
            </ul>
          </section>
          <div class="relationship-chart-grid">
            ${renderMiniLineChart("Index YoY vs GDP YoY", payload.yoy_series, ["index", "gdp"])}
            ${renderMiniLineChart("Rolling correlation", payload.correlation_series, ["value"])}
            ${renderLagComparison(payload)}
            ${renderQuadBars(payload)}
          </div>
        `;
      })
      .catch((error) => {
        if (state.selectedRelationshipId !== card.relationship_id) return;
        detail.innerHTML = `<p class="status">Failed to load GDP relationship detail.</p>`;
        console.error(error);
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
          <line x1="${MARGIN_LEFT}" y1="${y}" x2="${PLOT_RIGHT}" y2="${y}"></line>
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
        <line x1="${MARGIN_LEFT}" y1="${PLOT_HEIGHT}" x2="${PLOT_RIGHT}" y2="${PLOT_HEIGHT}"></line>
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

    svg.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        hide();
      }
    });
  }

  function xAxisTicks(series) {
    if (!series.length) return [];
    const desiredTicks = Math.min(X_AXIS_TICK_COUNT, series.length);
    if (desiredTicks === 1) {
      return [{ date: series[0].date, x: xAt(0, series.length) }];
    }
    const lastIndex = series.length - 1;
    const indexes = Array.from({ length: desiredTicks }, (_, index) => (
      Math.round((index / (desiredTicks - 1)) * lastIndex)
    ));
    return [...new Set(indexes)].map((index) => ({
      date: series[index].date,
      x: xAt(index, series.length),
    }));
  }

  function fmtMonthYear(value) {
    const [year, month, day] = String(value).split("-").map(Number);
    const date = new Date(Date.UTC(year, month - 1, day || 1));
    if (Number.isNaN(date.getTime())) return value;
    return date.toLocaleDateString("en-US", {
      month: "short",
      year: "numeric",
      timeZone: "UTC",
    });
  }

  function renderXAxisTicks(series) {
    const ticks = xAxisTicks(series);
    return ticks
      .map((tick, index) => {
        return `
          <g class="chart-tick" transform="translate(${tick.x.toFixed(2)} ${PLOT_HEIGHT})">
            <line y2="8"></line>
            <text class="chart-x-label" y="22" text-anchor="middle" x="0" transform="rotate(-35 0 22)">${escapeHtml(fmtMonthYear(tick.date))}</text>
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
          ${renderYAxisAndGrid(yAxisTicks(fullSeries, Y_AXIS_TICK_COUNT), scale)}
          ${renderChartPolylines(fullSeries, "bear_market_level", "chart-level", scale)}
          ${renderChartPolylines(fullSeries, "bull_market_index", "chart-bull", scale)}
          ${renderChartPolylines(fullSeries, "bear_market_index", "chart-bear", scale)}
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

  function renderMarketPhaseMethod() {
    return `
      <section class="method-note" aria-label="Market phase method">
        <h3>Method</h3>
        <ul class="method-formula-list">
          <li>Rolling High = highest high seen so far in the series.</li>
          <li>Bear/Bull Level = Rolling High x 80%.</li>
          <li>Drawdown = Close / Rolling High - 1.</li>
        </ul>
        <p>Bull market: Close is above the Bear/Bull Level.</p>
        <p>Bear market: Close is at or below the Bear/Bull Level.</p>
        <p class="method-chart-key">Green line shows bull-market close segments; red line shows bear-market close segments; dashed line is the Bear/Bull Level.</p>
      </section>
    `;
  }

  async function refreshMarket(benchmarkId, button) {
    if (!benchmarkId || button?.dataset.refreshing === "true") return;
    const previousText = button?.textContent;
    if (button) {
      button.dataset.refreshing = "true";
      button.setAttribute("aria-disabled", "true");
      button.textContent = "⟳";
    }
    $("dashboardStatus").textContent = `Refreshing ${benchmarkId}...`;
    try {
      const response = await fetch(`/api/macro-dashboard/market-phase/${encodeURIComponent(benchmarkId)}/refresh`, {
        method: "POST",
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.detail || `HTTP ${response.status}`);
      }
      const result = await response.json();
      delete state.marketDetailsById[benchmarkId];
      const overview = await fetch("/api/macro-dashboard/market-phase");
      if (!overview.ok) throw new Error(`HTTP ${overview.status}`);
      const payload = await overview.json();
      state.markets = payload.markets || [];
      $("dashboardStatus").textContent = `${result.benchmark_id} refreshed from ${result.symbol}: ${result.rows_upserted} rows through ${result.latest_date}.`;
      renderOverview();
      if (state.selectedBenchmarkId === benchmarkId) {
        renderDetail();
      }
    } catch (error) {
      $("dashboardStatus").textContent = `Refresh failed: ${error.message}`;
      console.error(error);
    } finally {
      if (button) {
        button.dataset.refreshing = "false";
        button.setAttribute("aria-disabled", "false");
        button.textContent = previousText || "↻";
      }
    }
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
          ${renderMarketPhaseMethod()}
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
    loadGdpRelationshipOverview().catch((error) => {
      const section = ensureGdpRelationshipRoot();
      if (section) {
        section.innerHTML = `<p class="status">Failed to load GDP relationship data.</p>`;
      }
      console.error(error);
    });
  }

  if (typeof window !== "undefined" && window.__MEOWSTREET_TEST__) {
    window.__macroDashboardTestHooks = {
      X_AXIS_TICK_COUNT,
      Y_AXIS_TICK_COUNT,
      fmtMonthYear,
      niceTicks,
      xAt,
      xAxisTicks,
      renderXAxisTicks,
      yAt,
      yAxisTicks,
    };
  }

  loadDashboard().catch((error) => {
    $("dashboardStatus").textContent = "Failed to load market phase data.";
    console.error(error);
  });
})();

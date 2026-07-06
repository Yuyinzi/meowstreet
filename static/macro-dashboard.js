(function () {
  const state = {
    markets: [],
    selectedBenchmarkId: null,
    selectedRelationshipId: null,
    marketDetailsById: {},
    gdpRelationships: [],
    gdpRelationshipDetailsById: {},
    usRatesLiquidity: null,
    usRatesLiquidityError: null,
    selectedRatesDetailId: null,
    usRatesDetailsById: {},
    selectedNominalCurrentDate: null,
    selectedNominalComparisonDate: null,
    selectedRealCurrentDate: null,
    selectedRealComparisonDate: null,
  };

  const CHART_WIDTH = 960;
  const CHART_HEIGHT = 400;
  const MARGIN_LEFT = 50;
  const MARGIN_RIGHT = 50;
  const MARGIN_TOP = 18;
  const MARGIN_BOTTOM = 84;
  const MARKET_X_LABEL_Y = 32;
  const RELATIONSHIP_X_LABEL_Y = 36;
  const PLOT_RIGHT = CHART_WIDTH - MARGIN_RIGHT;
  const PLOT_WIDTH = PLOT_RIGHT - MARGIN_LEFT;
  const PLOT_BOTTOM = CHART_HEIGHT - MARGIN_BOTTOM;
  const PLOT_HEIGHT = PLOT_BOTTOM - MARGIN_TOP;
  const Y_AXIS_TICK_COUNT = 9;
  const X_AXIS_TICK_COUNT = 12;

  async function loadGdpRelationshipOverview() {
    const response = await fetch("/api/macro-dashboard/gdp-relationships");
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const payload = await response.json();
    state.gdpRelationships = payload.relationships || [];
    state.selectedRelationshipId = null;
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

  function fmtCorrelationPercent(value) {
    if (value === null || value === undefined) return "n/a";
    return fmtPercent(value * 100);
  }

  function fmtDate(value) {
    return value || "n/a";
  }

  function lineLabel(labels, key) {
    const label = labels?.[key] || key;
    const zh = zhLabel(label);
    return zh ? `${label} (${zh})` : label;
  }

  function signalUsabilityMeta(value) {
    const text = String(value ?? "");
    if (text.includes("usable with caution")) {
      return { label: "caution", className: "signal-caution" };
    }
    if (text.includes("usable")) {
      return { label: "usable", className: "signal-usable" };
    }
    if (text.includes("weak")) {
      return { label: "weak", className: "signal-weak" };
    }
    if (!text) {
      return { label: "n/a", className: "signal-neutral" };
    }
    return { label: "not usable", className: "signal-neutral" };
  }

  function portfolioBiasMeta(value) {
    const text = String(value ?? "");
    const normalized = text.toLowerCase();
    if (normalized.includes("long")) {
      return { label: "long bias", className: "signal-usable" };
    }
    if (normalized.includes("short") || normalized.includes("defensive")) {
      return { label: "defensive", className: "signal-weak" };
    }
    if (normalized.includes("forecast")) {
      return { label: "requires GDP forecast", className: "signal-caution" };
    }
    if (!text) {
      return { label: "n/a", className: "signal-neutral" };
    }
    return { label: text, className: "signal-caution" };
  }

  function statusClass(market) {
    return market.latest.market_phase_status === "bear_market" ? "bear" : "bull";
  }

  function selectedMarket() {
    return state.markets.find((market) => market.benchmark_id === state.selectedBenchmarkId)
      || null;
  }

  function visibleMarketPhaseMarkets(markets) {
    return (markets || []).filter((market) => String(market.region ?? "").toUpperCase() === "US");
  }

  function selectedRelationship() {
    return state.gdpRelationships.find((card) => card.relationship_id === state.selectedRelationshipId)
      || null;
  }

  function xAt(index, count) {
    if (count <= 1) return MARGIN_LEFT + PLOT_WIDTH / 2;
    return MARGIN_LEFT + (index / (count - 1)) * PLOT_WIDTH;
  }

  function yAt(value, scale) {
    return MARGIN_TOP + scale.height - ((value - scale.min) / scale.range) * scale.height;
  }

  function yTickLabelY(y) {
    if (y >= PLOT_BOTTOM - 1) return -8;
    if (y <= MARGIN_TOP + 1) return 12;
    return 4;
  }

  function visibleYAxisTicks(ticks, scale) {
    return ticks.filter((value) => yAt(value, scale) < PLOT_BOTTOM - 1);
  }

  function renderOverview() {
    const grid = $("marketGrid");
    const markets = visibleMarketPhaseMarkets(state.markets);
    const currentMarket = markets.find((market) => market.benchmark_id === state.selectedBenchmarkId)
      || null;
    grid.innerHTML = markets
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
        state.selectedBenchmarkId = state.selectedBenchmarkId === button.dataset.benchmarkId
          ? null
          : button.dataset.benchmarkId;
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
          <h2>GDP / Market Relationship</h2>
          <p class="subtitle">GDP, index correlation, and quadnomial context.</p>
        </div>
      </div>
      <div class="gdp-grid">
        ${state.gdpRelationships.map((card) => {
          const selected = card.relationship_id === current?.relationship_id ? " selected" : "";
          const signal = signalUsabilityMeta(card.relationship_signal_usability);
          return `
            <button class="gdp-card${selected}" type="button" data-relationship-id="${escapeHtml(card.relationship_id)}">
              <div class="gdp-card-topline">
                <span class="market-region">${escapeHtml(card.region)}</span>
                <span class="gdp-card-confidence ${confidenceClass(card)}">${escapeHtml(card.macro_relationship_confidence)} confidence</span>
              </div>
              <strong class="gdp-card-title">${escapeHtml(card.title)}</strong>
              <span class="gdp-card-subtitle">${escapeHtml(card.economy)} · primary lag ${escapeHtml(card.primary_lag_months)}M</span>
              <div class="gdp-card-summary">
                <span>
                  <small>Signal</small>
                  <strong class="signal-status ${signal.className}" title="${escapeHtml(card.relationship_signal_usability)}">${escapeHtml(signal.label)}</strong>
                </span>
                <span>
                  <small>Avg 10Y corr</small>
                  <strong>${escapeHtml(fmtCorrelationPercent(card.latest?.average_10y_correlation))}</strong>
                </span>
              </div>
            </button>
          `;
        }).join("")}
      </div>
      ${state.selectedRelationshipId ? `<div class="gdp-detail" id="gdpRelationshipDetail"></div>` : ""}
    `;

    section.querySelectorAll(".gdp-card").forEach((button) => {
      button.addEventListener("click", () => {
        state.selectedRelationshipId = state.selectedRelationshipId === button.dataset.relationshipId
          ? null
          : button.dataset.relationshipId;
        renderGdpRelationshipOverview();
      });
    });

    renderGdpRelationshipDetail();
  }

  function relationshipValues(series, keys) {
    return series.flatMap((point) => keys.map((key) => point[key])).filter((value) => value !== null && value !== undefined);
  }

  function relationshipScale(series, keys, yDomain = null) {
    if (yDomain && yDomain.min !== null && yDomain.min !== undefined && yDomain.max !== null && yDomain.max !== undefined) {
      const min = yDomain.min;
      const max = yDomain.max;
      return { min, max, range: max - min || 1, height: PLOT_HEIGHT };
    }
    const values = relationshipValues(series, keys);
    if (!values.length) return null;
    const min = Math.min(...values);
    const max = Math.max(...values);
    return { min, max, range: max - min || 1, height: PLOT_HEIGHT };
  }

  function relationshipYAxisTicks(series, keys, count, yDomain = null) {
    if (yDomain && yDomain.min !== null && yDomain.min !== undefined && yDomain.max !== null && yDomain.max !== undefined) {
      return niceTicks(yDomain.min, yDomain.max, count);
    }
    const values = relationshipValues(series, keys);
    if (!values.length) return [];
    return niceTicks(Math.min(...values), Math.max(...values), count);
  }

  function relationshipXAxisTicks(series) {
    return xAxisTicks(series);
  }

  function renderRelationshipXAxisTicks(series, options = {}) {
    const ticks = options.categoricalXAxis
      ? series.map((point, index) => ({
        date: point.label || point.date,
        x: xAt(index, series.length),
      }))
      : xAxisTicks(series);
    return ticks
      .map((tick) => `
        <g class="chart-tick relationship-chart-tick" transform="translate(${tick.x.toFixed(2)} ${PLOT_BOTTOM})">
          <line y2="8"></line>
          <text class="chart-x-label" y="${RELATIONSHIP_X_LABEL_Y}" text-anchor="middle" x="0" transform="rotate(-35 0 ${RELATIONSHIP_X_LABEL_Y})">${escapeHtml(options.categoricalXAxis ? tick.date : fmtMonthYear(tick.date))}</text>
        </g>
      `)
      .join("");
  }

  function renderRelationshipYAxisAndGrid(ticks, scale, formatValue = fmtNumber) {
    const gridAndTicks = visibleYAxisTicks(ticks, scale).map((value) => {
      const yValue = yAt(value, scale);
      const y = yValue.toFixed(2);
      return `
        <g class="chart-grid">
          <line x1="${MARGIN_LEFT}" y1="${y}" x2="${PLOT_RIGHT}" y2="${y}"></line>
        </g>
        <g class="chart-y-tick" transform="translate(${MARGIN_LEFT} ${y})">
          <line x1="-6" y1="0" x2="0" y2="0"></line>
          <text x="-10" y="${yTickLabelY(yValue)}">${escapeHtml(formatValue(value))}</text>
        </g>
      `;
    }).join("");

    return `
      <g class="chart-axis">
        <line x1="${MARGIN_LEFT}" y1="${MARGIN_TOP}" x2="${MARGIN_LEFT}" y2="${PLOT_BOTTOM}"></line>
        <line x1="${MARGIN_LEFT}" y1="${PLOT_BOTTOM}" x2="${PLOT_RIGHT}" y2="${PLOT_BOTTOM}"></line>
      </g>
      ${gridAndTicks}
    `;
  }

  function renderRelationshipLineChart(title, series, keys, labels = {}, options = {}) {
    const wideClass = options.wide ? " relationship-chart-wide" : "";
    if (!series || !series.length) {
      return `
        <div class="relationship-chart${wideClass}">
          <div class="relationship-chart-head">
            <h3>${escapeHtml(title)}</h3>
            <span>No data</span>
          </div>
          <p class="status">No chart data available.</p>
        </div>
      `;
    }
    const values = relationshipValues(series, keys);
    if (!values.length) {
      return `
        <div class="relationship-chart${wideClass}">
          <div class="relationship-chart-head">
            <h3>${escapeHtml(title)}</h3>
            <span>No data</span>
          </div>
          <p class="status">No chart data available.</p>
        </div>
      `;
    }
    const scale = relationshipScale(series, keys, options.yDomain);
    const valueFormatter = options.valueFormatter || fmtNumber;
    const firstLabel = series[0].label || series[0].date;
    const lastLabel = series[series.length - 1].label || series[series.length - 1].date;
    return `
      <div class="relationship-chart${wideClass}">
        <div class="relationship-chart-head">
          <h3>${escapeHtml(title)}</h3>
          <span>${escapeHtml(fmtMonthYear(firstLabel))} - ${escapeHtml(fmtMonthYear(lastLabel))}</span>
        </div>
        <div class="relationship-legend">
          ${keys.map((key, index) => `
            <span><i class="relationship-line-key relationship-line-key-${index}"></i>${escapeHtml(lineLabel(labels, key))}</span>
          `).join("")}
        </div>
        <div class="chart-wrap relationship-chart-wrap">
          <svg class="relationship-chart-svg" viewBox="0 0 ${CHART_WIDTH} ${CHART_HEIGHT}" role="img" aria-label="${escapeHtml(title)}">
            ${renderRelationshipYAxisAndGrid(relationshipYAxisTicks(series, keys, Y_AXIS_TICK_COUNT, options.yDomain), scale, valueFormatter)}
            ${scale.min <= 0 && scale.max >= 0 ? `<line class="relationship-zero" x1="${MARGIN_LEFT}" y1="${yAt(0, scale).toFixed(2)}" x2="${PLOT_RIGHT}" y2="${yAt(0, scale).toFixed(2)}"></line>` : ""}
            ${keys.flatMap((key, index) => (
              chartSegments(series, key, scale).map((points) => `<polyline class="relationship-line relationship-line-${index}" points="${escapeHtml(points)}"></polyline>`)
            )).join("")}
            ${options.showDots ? keys.flatMap((key, index) => (
              series
                .filter((point) => point[key] !== null && point[key] !== undefined)
                .map((point) => {
                  const i = series.indexOf(point);
                  return `<circle class="relationship-dot relationship-dot-${index}" cx="${xAt(i, series.length).toFixed(2)}" cy="${yAt(point[key], scale).toFixed(2)}" r="3.5"></circle>`;
                })
            )).join("") : ""}
            ${renderRelationshipXAxisTicks(series, options)}
          </svg>
          <div class="chart-tooltip" aria-hidden="true"></div>
        </div>
      </div>
    `;
  }

  function attachRelationshipChartTooltip(svg, tooltip, series, keys, labels = {}, options = {}) {
    if (!svg || !tooltip || !series.length) return;
    const wrap = svg.parentElement;
    const valueFormatter = options.valueFormatter || fmtNumber;
    let lastIndex = -1;
    let tooltipRect = null;

    function show(index, clientX, clientY) {
      const point = series[index];
      if (index !== lastIndex) {
        const rows = keys.map((key) => {
          const value = point[key];
          const text = value === null || value === undefined ? "n/a" : valueFormatter(value);
          return `
            <div class="chart-tooltip-row">
              <span>${escapeHtml(lineLabel(labels, key))}</span>
              <strong>${escapeHtml(text)}</strong>
            </div>
          `;
        }).join("");
        tooltip.innerHTML = `
          <div><strong>${escapeHtml(fmtMonthYear(point.date))}</strong></div>
          ${rows}
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

  function renderQuadBars(relationship) {
    return `
      <div class="relationship-chart">
        <div class="relationship-chart-head">
          <h3>Quadnomial distribution</h3>
          <span>${escapeHtml(relationship.primary_lag_months)}M lag rate</span>
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
              <strong>${escapeHtml(fmtCorrelationPercent(lag.value))}</strong>
              ${lag.method_primary ? '<em class="lag-primary-pill">Method primary</em>' : "<em></em>"}
            </div>
          `).join("")}
        </div>
      </div>
    `;
  }

  function renderLagCorrelationComparison(payload) {
    const keys = Object.keys(payload.lag_correlation_labels || {});
    return renderRelationshipLineChart(
      "Rolling 10Y correlations by lag",
      payload.lag_correlation_series,
      keys,
      payload.lag_correlation_labels || {},
      {
        wide: true,
        valueFormatter: fmtCorrelationPercent,
      }
    );
  }

  function renderYoyComparison(payload) {
    return renderRelationshipLineChart(
      "Index YoY vs GDP YoY",
      payload.yoy_series,
      ["index", "gdp"],
      { index: "Index YoY", gdp: "GDP YoY" },
      {
        wide: true,
        valueFormatter: (value) => `${fmtNumber(value)}%`,
      }
    );
  }

  function renderPrimaryCorrelationComparison(payload) {
    return renderRelationshipLineChart(
      "Rolling correlation",
      payload.correlation_series,
      ["value"],
      { value: `${payload.primary_lag_months}M lag rolling correlation` },
      {
        wide: true,
        valueFormatter: fmtCorrelationPercent,
      }
    );
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
        const signal = signalUsabilityMeta(payload.relationship_signal_usability);
        const portfolioBias = portfolioBiasMeta(payload.portfolio_bias_status);
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
            <div><span>Index YoY</span><strong>${escapeHtml(fmtPercent(indexYoy))}</strong><small class="metric-context">${escapeHtml(payload.primary_lag_months)}M lag ${escapeHtml(fmtDate(latest.primary_lag_date))}</small></div>
            <div><span>GDP YoY</span><strong>${escapeHtml(fmtPercent(gdpYoy))}</strong><small class="metric-context">${escapeHtml(payload.primary_lag_months)}M lag ${escapeHtml(fmtDate(latest.primary_lag_date))}</small></div>
            <div><span>Average 10Y Correlation</span><strong>${escapeHtml(fmtCorrelationPercent(latest.average_10y_correlation))}</strong><small class="metric-context">${escapeHtml(payload.primary_lag_months)}M lag average</small></div>
            <div><span>Same Direction</span><strong>${escapeHtml(fmtPercent(payload.same_direction_pct))}</strong><small class="metric-context">${escapeHtml(payload.primary_lag_months)}M lag A + B</small></div>
            <div><span>Method Coverage</span><strong>${escapeHtml(fmtPercent(payload.method_explainable_pct))}</strong><small class="metric-context">${escapeHtml(payload.primary_lag_months)}M lag A + B + C</small></div>
            <div><span>Current Case</span><strong>${escapeHtml(latest.quadnomial_current_plain_label || latest.quadnomial_current_case)}</strong><small class="metric-context">Quadnomial ${escapeHtml(latest.quadnomial_period_label || fmtDate(latest.quadnomial_date))}</small></div>
            <div><span>Signal usability</span><strong class="signal-status ${signal.className}" title="${escapeHtml(payload.relationship_signal_usability)}">${escapeHtml(signal.label)}</strong></div>
            <div><span>Portfolio Bias</span><strong class="signal-status ${portfolioBias.className}" title="${escapeHtml(payload.portfolio_bias_status)}">${escapeHtml(portfolioBias.label)}</strong></div>
          </div>
          <div class="relationship-chart-grid relationship-chart-grid-pre-method">
            ${renderQuadBars(payload)}
          </div>
          <section class="method-note" aria-label="GDP relationship method">
            <h3>Method</h3>
            <ul class="method-formula-list">
              <li>Index YoY vs GDP YoY compares market direction with economic growth direction.</li>
              <li>Rolling correlation checks whether the current relationship is stable or breaking down.</li>
              <li>Usability is strong when the primary-lag average 10Y correlation is at least 40% and the same-direction rate is at least 60%. It is caution when correlation is at least 25% and same-direction rate is at least 55%; below those levels, the GDP relationship is weak.</li>
              <li>The confidence badge uses the same evidence: high when both strong thresholds are met, medium when only the caution thresholds are met, and low when the relationship is below those levels or lacks enough data.</li>
              <li>Quadnomial distribution defines A as index down/GDP down, B as index up/GDP up, C as index down/GDP up, and D as index up/GDP down.</li>
              <li>Method coverage combines A, B, and C for the primary 6M lag: same-direction GDP confirmation plus the profit-taking case where GDP rises but the index falls. It is not used as relationship confidence.</li>
            </ul>
          </section>
          <div class="relationship-chart-grid">
            ${renderYoyComparison(payload)}
            ${renderPrimaryCorrelationComparison(payload)}
            ${renderLagCorrelationComparison(payload)}
          </div>
        `;
        const charts = detail.querySelectorAll(".relationship-chart-wrap");
        const chartSeries = [
          {
            series: payload.yoy_series,
            keys: ["index", "gdp"],
            labels: { index: "Index YoY", gdp: "GDP YoY" },
            valueFormatter: (value) => `${fmtNumber(value)}%`,
          },
          {
            series: payload.correlation_series,
            keys: ["value"],
            labels: { value: `${payload.primary_lag_months}M lag rolling correlation` },
            valueFormatter: fmtCorrelationPercent,
          },
          {
            series: payload.lag_correlation_series,
            keys: Object.keys(payload.lag_correlation_labels || {}),
            labels: payload.lag_correlation_labels || {},
            valueFormatter: fmtCorrelationPercent,
          },
        ];
        charts.forEach((wrap, index) => {
          attachRelationshipChartTooltip(
            wrap.querySelector(".relationship-chart-svg"),
            wrap.querySelector(".chart-tooltip"),
            chartSeries[index].series,
            chartSeries[index].keys,
            chartSeries[index].labels,
            { valueFormatter: chartSeries[index].valueFormatter }
          );
        });
      })
      .catch((error) => {
        if (state.selectedRelationshipId !== card.relationship_id) return;
        detail.innerHTML = `<p class="status">Failed to load GDP relationship detail.</p>`;
        console.error(error);
      });
  }

  async function loadUsRatesLiquidity() {
    try {
      const response = await fetch("/api/macro-dashboard/us-rates-liquidity");
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      state.usRatesLiquidity = await response.json();
      state.usRatesLiquidityError = null;
    } catch (error) {
      state.usRatesLiquidity = null;
      state.usRatesLiquidityError = error.message;
    }
    renderUsRatesLiquidity();
  }

  function fmtRate(value) {
    if (value === null || value === undefined) return "n/a";
    return `${Number(value).toFixed(2)}%`;
  }

  function fmtNumber(value) {
    if (value === null || value === undefined) return "n/a";
    return Number(value).toFixed(2);
  }

  const ZH_LABELS = {
    "10-Year Treasury": "10年期国债",
    "2-Year Treasury": "2年期国债",
    "10Y - 2Y Spread": "10Y-2Y利差",
    "10Y Real Rate": "10年期实际利率",
    "CPI Real Rate": "CPI实际利率",
    "Fed Funds": "联邦基金利率",
    "Breakeven": "盈亏平衡通胀率",
    "VIX": "VIX波动率指数",
    "S&P PE": "标普500市盈率",
    "S&P 500 PE": "标普500市盈率",
    "10Y Treasury Minus CPI YoY": "10年期国债减CPI同比",
    "CPI Real Rate vs VIX": "CPI实际利率 vs VIX",
    "CPI Real Rate vs S&P 500 PE": "CPI实际利率 vs 标普500市盈率",
    "Index YoY": "指数同比",
    "GDP YoY": "GDP同比",
    "Index YoY vs GDP YoY": "指数同比 vs GDP同比",
    "No lag": "无滞后",
    "3M lag": "3个月滞后",
    "Real Rate": "实际利率",
    "Comparison": "对比",
  };

  function zhLabel(label) {
    return ZH_LABELS[label] || null;
  }

  function bilingualLabel(label) {
    const zh = zhLabel(label);
    return zh ? `${escapeHtml(label)}<small>${escapeHtml(zh)}</small>` : escapeHtml(label);
  }

  function renderRateCard(card) {
    const selected = state.selectedRatesDetailId === card.id ? " selected" : "";
    return `
      <button class="rates-signal-card${selected}" type="button" data-rates-detail-id="${escapeHtml(card.id)}">
        <span>${bilingualLabel(card.label)}</span>
        <strong>${escapeHtml(fmtRate(card.value))}</strong>
      </button>
    `;
  }

  function renderSupportCard(label, value) {
    return `
      <span class="rates-signal-card">
        <span>${bilingualLabel(label)}</span>
        <strong>${escapeHtml(value)}</strong>
      </span>
    `;
  }

  function ratesDetailCacheKey(detailId) {
    if (detailId === "yield_curve_shape") {
      return `yield_curve_shape|${state.selectedNominalCurrentDate || ""}|${state.selectedNominalComparisonDate || ""}|${state.selectedRealCurrentDate || ""}|${state.selectedRealComparisonDate || ""}`;
    }
    return detailId;
  }

  async function loadUsRatesLiquidityDetail(detailId) {
    const cacheKey = ratesDetailCacheKey(detailId);
    if (state.usRatesDetailsById[cacheKey]) {
      return state.usRatesDetailsById[cacheKey];
    }
    const url = new URL(`/api/macro-dashboard/us-rates-liquidity/${encodeURIComponent(detailId)}`, window.location.origin);
    if (detailId === "yield_curve_shape") {
      if (state.selectedNominalCurrentDate) {
        url.searchParams.set("nominalCurrentDate", state.selectedNominalCurrentDate);
      }
      if (state.selectedNominalComparisonDate) {
        url.searchParams.set("nominalComparisonDate", state.selectedNominalComparisonDate);
      }
      if (state.selectedRealCurrentDate) {
        url.searchParams.set("realCurrentDate", state.selectedRealCurrentDate);
      }
      if (state.selectedRealComparisonDate) {
        url.searchParams.set("realComparisonDate", state.selectedRealComparisonDate);
      }
    }
    const response = await fetch(url.toString());
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const payload = await response.json();
    state.usRatesDetailsById[cacheKey] = payload;
    return payload;
  }

  function renderUsRatesLiquidity() {
    const section = $("usRatesLiquidity");
    if (!section) return;
    const payload = state.usRatesLiquidity;
    if (state.usRatesLiquidityError) {
      section.querySelector(".rates-loading")?.remove();
      section.insertAdjacentHTML(
        "beforeend",
        `<div class="rates-empty">Unable to load US rates data: ${escapeHtml(state.usRatesLiquidityError)}</div>`,
      );
      return;
    }
    if (!payload) return;
    const headline = payload.headline || [];
    section.innerHTML = `
      <div class="relationship-head">
        <div>
          <h2>US Rates / Liquidity</h2>
          <p class="subtitle">Nominal curve, real rates, Fed Funds, CPI Real Rate, and curve-steepness signals from the imported US benchmark-yields workbook.</p>
        </div>
        <span class="mock-pill">${escapeHtml(payload.as_of ? `As of ${fmtDate(payload.as_of)}` : "Import needed")}</span>
      </div>
      ${headline.length ? `<div class="rates-signal-grid">${headline.map(renderRateCard).join("")}${renderSupportCard("Breakeven", fmtRate(payload.derived?.ten_year_breakeven_inflation))}${renderSupportCard("VIX", fmtNumber(payload.derived?.vix))}${renderSupportCard("S&P PE", fmtNumber(payload.derived?.sp500_pe))}</div>` : ""}
      ${state.selectedRatesDetailId ? '<div class="rates-detail gdp-detail" id="usRatesLiquidityDetail"></div>' : ""}
      <div class="rates-interpretation-panel">
        <p class="eyebrow">Interpretation</p>
        <h3>${escapeHtml(fmtStatus(payload.derived?.curve_status || "missing"))}</h3>
        <p>${escapeHtml(payload.derived?.method_interpretation || "")}</p>
      </div>
      <div class="rates-detail gdp-detail" id="usRatesCurveDetail"></div>
    `;
    section.querySelectorAll("[data-rates-detail-id]").forEach((button) => {
      button.addEventListener("click", () => {
        state.selectedRatesDetailId = state.selectedRatesDetailId === button.dataset.ratesDetailId
          ? null
          : button.dataset.ratesDetailId;
        if (state.selectedRatesDetailId !== "yield_curve_shape") {
          state.selectedNominalCurrentDate = null;
          state.selectedNominalComparisonDate = null;
          state.selectedRealCurrentDate = null;
          state.selectedRealComparisonDate = null;
        }
        renderUsRatesLiquidity();
      });
    });
    renderUsRatesLiquidityDetail();
    renderYieldCurveDetail();
  }

  function bilingualTitle(title) {
    const zh = zhLabel(title);
    return zh ? `${title} · ${zh}` : title;
  }

  function renderRatesTimeSeriesChart(chart) {
    return renderRelationshipLineChart(
      bilingualTitle(chart.title),
      chart.series || [],
      chart.keys || ["value"],
      chart.labels || { value: "Value" },
      {
        wide: true,
        valueFormatter: fmtRate,
        yDomain: chart.y_domain,
      }
    );
  }

  function renderRatesCurveComparisonChart(chart, chartIndex) {
    const kind = chartIndex === 0 ? "nominal" : "real";
    const dates = chart.date_options || [];
    const dateControls = dates.length ? `
      <div class="rates-curve-date-controls">
        <label>BLUE LINE
          <select data-curve-date-kind="${kind}" data-curve-date-role="current">
            ${dates.map((date) => `
              <option value="${escapeHtml(date)}" ${date === chart.selected_current_date ? "selected" : ""}>${escapeHtml(date)}</option>
            `).join("")}
          </select>
        </label>
        <label>RED LINE
          <select data-curve-date-kind="${kind}" data-curve-date-role="comparison">
            ${dates.map((date) => `
              <option value="${escapeHtml(date)}" ${date === chart.selected_comparison_date ? "selected" : ""}>${escapeHtml(date)}</option>
            `).join("")}
          </select>
        </label>
      </div>
    ` : "";
    const series = chart.series || [];
    const keys = chart.keys || ["current", "comparison"];
    const labels = chart.labels || { current: "Latest", comparison: "Comparison" };
    return `<div class="rates-curve-combo relationship-chart-wide">
      ${dateControls}
      ${renderRelationshipLineChart(
        chart.title,
        series.map((point) => ({ date: point.label, ...point })),
        keys,
        labels,
        {
          wide: false,
          valueFormatter: fmtRate,
          yDomain: chart.y_domain,
          categoricalXAxis: true,
          showDots: true,
        }
      )}
    </div>`;
  }

  function renderRatesMultiSeriesChart(chart) {
    const primary = chart.series || [];
    const secondary = chart.secondary_series || [];
    const secondaryByDate = new Map(secondary.map((point) => [point.date, point.value]));
    const merged = primary
      .map((point) => ({
        date: point.date,
        real_rate: point.real_rate ?? point.value,
        secondary: secondaryByDate.get(point.date),
      }))
      .filter((point) => point.secondary !== undefined);
    return renderRelationshipLineChart(
      bilingualTitle(chart.title),
      merged,
      ["real_rate", "secondary"],
      {
        real_rate: chart.labels?.real_rate || "Real Rate",
        secondary: chart.labels?.vix || chart.labels?.sp500_pe || "Comparison",
      },
      { wide: true },
    );
  }

  function renderRatesDetailChart(chart, chartIndex) {
    if (chart.kind === "curve_comparison") {
      return renderRatesCurveComparisonChart(chart, chartIndex);
    }
    if (chart.kind === "multi_series") {
      return renderRatesMultiSeriesChart(chart);
    }
    return renderRatesTimeSeriesChart(chart);
  }

  function bindRatesCurveControls(detail, context) {
    detail.querySelectorAll("[data-curve-date-kind]").forEach((select) => {
      select.addEventListener("change", (event) => {
        event.preventDefault();
        const kind = select.dataset.curveDateKind;
        const role = select.dataset.curveDateRole;
        const date = select.value;
        if (kind === "nominal") {
          if (role === "current") state.selectedNominalCurrentDate = date;
          else state.selectedNominalComparisonDate = date;
        } else {
          if (role === "current") state.selectedRealCurrentDate = date;
          else state.selectedRealComparisonDate = date;
        }
        const chartContainer = detail.querySelector(".relationship-chart-grid");
        if (chartContainer) {
          chartContainer.innerHTML = '<p class="status">Loading charts...</p>';
        }
        Object.keys(state.usRatesDetailsById).forEach((key) => {
          if (key.startsWith("yield_curve_shape")) {
            delete state.usRatesDetailsById[key];
          }
        });
        const detailId = context === "yield_curve" ? "yield_curve_shape" : state.selectedRatesDetailId;
        loadUsRatesLiquidityDetail(detailId)
          .then((payload) => {
            if (chartContainer) {
              chartContainer.innerHTML = payload.charts.map(renderRatesDetailChart).join("");
              const charts = chartContainer.querySelectorAll(".relationship-chart-wrap");
              charts.forEach((wrap, index) => {
                const chart = payload.charts[index];
                attachRelationshipChartTooltip(
                  wrap.querySelector(".relationship-chart-svg"),
                  wrap.querySelector(".chart-tooltip"),
                  chart.kind === "curve_comparison"
                    ? (chart.series || []).map((point) => ({ date: point.label, ...point }))
                    : chart.series || [],
                  chart.keys || ["value"],
                  chart.labels || { value: "Value" },
                  { valueFormatter: fmtRate }
                );
              });
            }
          })
          .catch((error) => {
            console.error(error);
          });
      });
    });
  }

  function attachRatesChartTooltips(detail, chartsPayload) {
    const charts = detail.querySelectorAll(".relationship-chart-wrap");
    charts.forEach((wrap, index) => {
      const chart = chartsPayload[index];
      attachRelationshipChartTooltip(
        wrap.querySelector(".relationship-chart-svg"),
        wrap.querySelector(".chart-tooltip"),
        chart.kind === "curve_comparison"
          ? (chart.series || []).map((point) => ({ date: point.label, ...point }))
          : chart.series || [],
        chart.keys || ["value"],
        chart.labels || { value: "Value" },
        { valueFormatter: fmtRate }
      );
    });
  }

  function renderRatesDetailPayload(detail, payload, context) {
    const heading = context === "yield_curve" ? `
      <div class="rates-interpretation-panel">
        <p class="eyebrow">Yield Curve Analysis</p>
        <h3>Nominal & Real Curve Comparison</h3>
        <p>Compare yield curve shape across selected dates for nominal Treasuries and real TIPS rates.</p>
      </div>
    ` : `
      <div class="detail-head">
        <div>
          <h2>${escapeHtml(payload.title)}</h2>
        </div>
      </div>
    `;
    detail.innerHTML = `
      ${heading}
      <div class="relationship-chart-grid">
        ${payload.charts.map((chart, index) => renderRatesDetailChart(chart, index)).join("")}
      </div>
    `;
    bindRatesCurveControls(detail, context);
    attachRatesChartTooltips(detail, payload.charts);
  }

  function bindRatesCurveControls(detail, context) {
    detail.querySelectorAll("[data-curve-date-kind]").forEach((select) => {
      select.addEventListener("change", (event) => {
        event.preventDefault();
        const kind = select.dataset.curveDateKind;
        const role = select.dataset.curveDateRole;
        const date = select.value;
        if (kind === "nominal") {
          if (role === "current") state.selectedNominalCurrentDate = date;
          else state.selectedNominalComparisonDate = date;
        } else {
          if (role === "current") state.selectedRealCurrentDate = date;
          else state.selectedRealComparisonDate = date;
        }
        Object.keys(state.usRatesDetailsById).forEach((key) => {
          if (key.startsWith("yield_curve_shape")) {
            delete state.usRatesDetailsById[key];
          }
        });
        const detailId = context === "yield_curve" ? "yield_curve_shape" : state.selectedRatesDetailId;
        loadUsRatesLiquidityDetail(detailId)
          .then((payload) => {
            renderRatesDetailPayload(detail, payload, context);
          })
          .catch((error) => {
            console.error(error);
          });
      });
    });
  }

  function renderUsRatesLiquidityDetail() {
    const detail = $("usRatesLiquidityDetail");
    const detailId = state.selectedRatesDetailId;
    if (!detail || !detailId) return;
    detail.innerHTML = '<p class="status">Loading US rates detail...</p>';
    loadUsRatesLiquidityDetail(detailId)
      .then((payload) => {
        if (state.selectedRatesDetailId !== payload.detail_id) return;
        renderRatesDetailPayload(detail, payload, "card");
      })
      .catch((error) => {
        if (state.selectedRatesDetailId !== detailId) return;
        detail.innerHTML = '<p class="status">Failed to load US rates detail.</p>';
        console.error(error);
      });
  }

  function renderYieldCurveDetail() {
    const detail = $("usRatesCurveDetail");
    if (!detail) return;
    detail.innerHTML = '<p class="status">Loading yield curve comparison...</p>';
    loadUsRatesLiquidityDetail("yield_curve_shape")
      .then((payload) => {
        renderRatesDetailPayload(detail, payload, "yield_curve");
      })
      .catch((error) => {
        detail.innerHTML = '<p class="status">Failed to load yield curve comparison.</p>';
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
    const gridAndTicks = visibleYAxisTicks(ticks, scale).map((value) => {
      const yValue = yAt(value, scale);
      const y = yValue.toFixed(2);
      return `
        <g class="chart-grid">
          <line x1="${MARGIN_LEFT}" y1="${y}" x2="${PLOT_RIGHT}" y2="${y}"></line>
        </g>
        <g class="chart-y-tick" transform="translate(${MARGIN_LEFT} ${y})">
          <line x1="-6" y1="0" x2="0" y2="0"></line>
          <text x="-10" y="${yTickLabelY(yValue)}">${escapeHtml(fmtNumber(value))}</text>
        </g>
      `;
    }).join("");

    return `
      <g class="chart-axis">
        <line x1="${MARGIN_LEFT}" y1="${MARGIN_TOP}" x2="${MARGIN_LEFT}" y2="${PLOT_BOTTOM}"></line>
        <line x1="${MARGIN_LEFT}" y1="${PLOT_BOTTOM}" x2="${PLOT_RIGHT}" y2="${PLOT_BOTTOM}"></line>
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
          <g class="chart-tick" transform="translate(${tick.x.toFixed(2)} ${PLOT_BOTTOM})">
            <line y2="8"></line>
            <text class="chart-x-label" y="${MARKET_X_LABEL_Y}" text-anchor="middle" x="0" transform="rotate(-35 0 ${MARKET_X_LABEL_Y})">${escapeHtml(fmtMonthYear(tick.date))}</text>
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
      state.markets = visibleMarketPhaseMarkets(payload.markets || []);
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
      detail.hidden = true;
      return;
    }
    detail.hidden = false;

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
    state.markets = visibleMarketPhaseMarkets(payload.markets || []);
    state.selectedBenchmarkId = null;
    $("dashboardStatus").textContent = state.markets.length
      ? `${state.markets.length} benchmark markets loaded. Workbook-seeded data may be stale until refresh is added.`
      : "No benchmark market data found. Run scripts/import_benchmark_market_data.py.";
    renderOverview();
    renderDetail();
    loadUsRatesLiquidity().catch((error) => {
      const section = $("usRatesLiquidity");
      if (section) {
        section.querySelector(".rates-loading")?.remove();
        section.insertAdjacentHTML(
          "beforeend",
          `<div class="rates-empty">Failed to load US rates data.</div>`,
        );
      }
      console.error(error);
    });
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
      attachRelationshipChartTooltip,
      fmtMonthYear,
      niceTicks,
      relationshipXAxisTicks,
      relationshipYAxisTicks,
      renderRelationshipLineChart,
      renderRelationshipXAxisTicks,
      renderRelationshipYAxisAndGrid,
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

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
    growthCycle: null,
    growthCycleError: null,
    selectedGrowthCycleDetailId: null,
    selectedGrowthCycleChartRange: "10y",
    growthCycleDetailsById: {},
    selectedNominalCurrentDate: null,
    selectedNominalComparisonDate: null,
    selectedRealCurrentDate: null,
    selectedRealComparisonDate: null,
    isDetailPanelExpanded: false,
  };

  const DETAIL_PANEL_EXPAND_LABEL = "Expand detail panel";
  const DETAIL_PANEL_COLLAPSE_LABEL = "Collapse detail panel";

  function syncDetailPanelWidthClass() {
    const shell = $("macroDashboardApp");
    if (!shell) return;
    shell.classList.toggle("panel-expanded", Boolean(state.isDetailPanelExpanded));
  }

  function toggleDetailPanelExpanded() {
    state.isDetailPanelExpanded = !state.isDetailPanelExpanded;
    syncDetailPanelWidthClass();
    renderDetailPanel();
  }

  function closeDetailPanel() {
    state.selectedBenchmarkId = null;
    state.selectedRelationshipId = null;
    state.selectedRatesDetailId = null;
    state.selectedGrowthCycleDetailId = null;
    state.selectedNominalCurrentDate = null;
    state.selectedNominalComparisonDate = null;
    state.selectedRealCurrentDate = null;
    state.selectedRealComparisonDate = null;
    $("macroDashboardApp").classList.remove("panel-open");
    syncDetailPanelWidthClass();
    $("detailPanel").innerHTML = "";
  }

  function renderDetailPanel() {
    const shell = $("macroDashboardApp");
    const panel = $("detailPanel");
    if (!panel) return;

    const anySelected = state.selectedBenchmarkId || state.selectedRelationshipId || state.selectedRatesDetailId || state.selectedGrowthCycleDetailId;
    if (!anySelected) {
      shell.classList.remove("panel-open");
      syncDetailPanelWidthClass();
      panel.innerHTML = "";
      return;
    }

    shell.classList.add("panel-open");
    syncDetailPanelWidthClass();

    let title = "";
    if (state.selectedBenchmarkId) {
      const market = selectedMarket();
      title = market ? market.title : "Market Detail";
    } else if (state.selectedRelationshipId) {
      const rel = selectedRelationship();
      title = rel ? rel.title : "GDP Relationship Detail";
    } else if (state.selectedRatesDetailId) {
      const rates = state.usRatesLiquidity;
      const card = (rates?.headline || []).find((c) => c.id === state.selectedRatesDetailId || state.selectedRatesDetailId === `yield_curve_shape` || CREDIT_DETAIL_MAP[c.id] === state.selectedRatesDetailId);
      title = card ? card.label : "US Rates Detail";
      if (state.selectedRatesDetailId === "yield_curve_shape") {
        title = "Yield Curve Analysis";
      }
    } else if (state.selectedGrowthCycleDetailId) {
      if (state.selectedGrowthCycleDetailId === "ism_manufacturing") {
        title = "ISM Manufacturing";
      } else {
        title = "M2 Money Supply";
      }
    }

    const expandLabel = state.isDetailPanelExpanded ? DETAIL_PANEL_COLLAPSE_LABEL : DETAIL_PANEL_EXPAND_LABEL;
    const expandIcon = state.isDetailPanelExpanded ? "\u2039" : "\u203A";

    panel.innerHTML = `
      <div class="detail-panel-head">
        <button class="detail-panel-expand" type="button" aria-label="${expandLabel}" title="${expandLabel}">${expandIcon}</button>
        <h2>${escapeHtml(title)}</h2>
        <button class="detail-panel-close" aria-label="Close detail panel">\u00d7</button>
      </div>
      <div class="detail-panel-body">
        <p class="status">Loading...</p>
      </div>
    `;

    panel.querySelector(".detail-panel-close").addEventListener("click", (event) => {
      event.stopPropagation();
      closeDetailPanel();
      renderOverview();
      renderGdpRelationshipOverview();
      renderUsRatesLiquidity();
    });

    panel.querySelector(".detail-panel-expand").addEventListener("click", (event) => {
      event.stopPropagation();
      toggleDetailPanelExpanded();
    });

    const body = panel.querySelector(".detail-panel-body");

    if (state.selectedBenchmarkId) {
      renderDetailInPanel(body);
    } else if (state.selectedRatesDetailId) {
      renderRatesDetailInPanel(body);
    } else if (state.selectedRelationshipId) {
      renderGdpDetailInPanel(body);
    } else if (state.selectedGrowthCycleDetailId) {
      renderGrowthCycleDetailInPanel(body);
    }
  }

  function renderDetailInPanel(body) {
    const market = selectedMarket();
    if (!market) return;

    loadMarketDetail(market.benchmark_id)
      .then((detailMarket) => {
        if (state.selectedBenchmarkId !== detailMarket.benchmark_id) return;
        const latest = detailMarket.latest;
        body.innerHTML = `
          <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px;">
            <span class="phase-pill phase-${statusClass(detailMarket)}">${escapeHtml(fmtStatus(latest.market_phase_status))}</span>
            <small style="color: #8B7E74; font-size: 12px;">${escapeHtml(detailMarket.region)}</small>
          </div>
          <div class="metric-strip">
            <div><span>${bilingualLabel("Close")}</span><strong>${escapeHtml(fmtNumber(latest.close))}</strong></div>
            <div><span>${bilingualLabel("Rolling High")}</span><strong>${escapeHtml(fmtNumber(latest.rolling_high))}</strong></div>
            <div><span>${bilingualLabel("Bear/Bull Level")}</span><strong>${escapeHtml(fmtNumber(latest.bear_market_level))}</strong></div>
            <div><span>${bilingualLabel("Drawdown")}</span><strong>${escapeHtml(fmtNumber(latest.drawdown_pct))}%</strong></div>
            <div><span>${bilingualLabel("Data Through")}</span><strong>${escapeHtml(detailMarket.data_through)}</strong></div>
          </div>
          ${renderMarketPhaseMethod()}
          ${renderMarketChart(detailMarket)}
        `;
        const svg = body.querySelector(".market-chart");
        const tooltip = body.querySelector(".chart-tooltip");
        attachChartTooltip(svg, tooltip, detailMarket.series);
      })
      .catch((error) => {
        if (state.selectedBenchmarkId !== market.benchmark_id) return;
        body.innerHTML = `<p class="status">Failed to load chart data.</p>`;
        console.error(error);
      });
  }

  function renderGdpDetailInPanel(body) {
    const card = selectedRelationship();
    if (!card) return;
    body.innerHTML = `<p class="status">Loading GDP relationship detail...</p>`;

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
        body.innerHTML = `
          <div class="metric-strip">
            <div><span>${bilingualTitle("Index YoY")}</span><strong>${escapeHtml(fmtPercent(indexYoy))}</strong><small class="metric-context">${escapeHtml(payload.primary_lag_months)}M lag ${escapeHtml(fmtDate(latest.primary_lag_date))}</small></div>
            <div><span>${bilingualTitle("GDP YoY")}</span><strong>${escapeHtml(fmtPercent(gdpYoy))}</strong><small class="metric-context">${escapeHtml(payload.primary_lag_months)}M lag ${escapeHtml(fmtDate(latest.primary_lag_date))}</small></div>
            <div><span>${bilingualTitle("Average 10Y Correlation")}</span><strong>${escapeHtml(fmtCorrelationPercent(latest.average_10y_correlation))}</strong><small class="metric-context">${escapeHtml(payload.primary_lag_months)}M lag average</small></div>
            <div><span>${bilingualTitle("Same Direction")}</span><strong>${escapeHtml(fmtPercent(payload.same_direction_pct))}</strong><small class="metric-context">${escapeHtml(payload.primary_lag_months)}M lag A + B</small></div>
            <div><span>${bilingualTitle("Method Coverage")}</span><strong>${escapeHtml(fmtPercent(payload.method_explainable_pct))}</strong><small class="metric-context">${escapeHtml(payload.primary_lag_months)}M lag A + B + C</small></div>
            <div><span>${bilingualTitle("Current Case")}</span><strong>${escapeHtml(latest.quadnomial_current_plain_label || latest.quadnomial_current_case)}</strong><small class="metric-context">Quadnomial ${escapeHtml(latest.quadnomial_period_label || fmtDate(latest.quadnomial_date))}</small></div>
            <div><span>${bilingualTitle("Signal usability")}</span><strong class="signal-status ${signal.className}" title="${escapeHtml(payload.relationship_signal_usability)}">${escapeHtml(signal.label)}</strong></div>
            <div><span>${bilingualTitle("Portfolio Bias")}</span><strong class="signal-status ${portfolioBias.className}" title="${escapeHtml(payload.portfolio_bias_status)}">${escapeHtml(portfolioBias.label)}</strong></div>
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
        const charts = body.querySelectorAll(".relationship-chart-wrap");
        const chartSeries = [
          { series: payload.yoy_series, keys: ["index", "gdp"], labels: { index: "Index YoY", gdp: "GDP YoY" }, valueFormatter: (value) => `${fmtNumber(value)}%` },
          { series: payload.correlation_series, keys: ["value"], labels: { value: `${payload.primary_lag_months}M lag rolling correlation` }, valueFormatter: fmtCorrelationPercent },
          { series: payload.lag_correlation_series, keys: Object.keys(payload.lag_correlation_labels || {}), labels: payload.lag_correlation_labels || {}, valueFormatter: fmtCorrelationPercent },
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
        body.innerHTML = `<p class="status">Failed to load GDP relationship detail.</p>`;
        console.error(error);
      });
  }

  function renderRatesDetailInPanel(body) {
    const detailId = state.selectedRatesDetailId;
    if (!detailId) return;

    if (detailId === "yield_curve_shape") {
      loadUsRatesLiquidityDetail(detailId)
        .then((payload) => {
          if (state.selectedRatesDetailId !== "yield_curve_shape") return;
        body.innerHTML = `
          <div class="relationship-chart-grid">
            ${payload.charts.map((chart, index) => renderRatesDetailChart(chart, index)).join("")}
          </div>
        `;
          bindRatesCurveControls(body, "yield_curve");
          attachRatesChartTooltips(body, payload.charts);
        })
        .catch((error) => {
          if (state.selectedRatesDetailId !== detailId) return;
          body.innerHTML = `<p class="status">Failed to load yield curve detail.</p>`;
          console.error(error);
        });
      return;
    }

    loadUsRatesLiquidityDetail(detailId)
      .then((payload) => {
        if (state.selectedRatesDetailId !== payload.detail_id) return;
        body.innerHTML = `
          <div class="relationship-chart-grid">
            ${payload.charts.map((chart, index) => renderRatesDetailChart(chart, index)).join("")}
          </div>
        `;
        bindRatesCurveControls(body, "card");
        attachRatesChartTooltips(body, payload.charts);
      })
      .catch((error) => {
        if (state.selectedRatesDetailId !== detailId) return;
        body.innerHTML = `<p class="status">Failed to load US rates detail.</p>`;
        console.error(error);
      });
  }

  const CHART_RANGE_OPTIONS = [
    { id: "1y", label: "1Y", years: 1 },
    { id: "5y", label: "5Y", years: 5 },
    { id: "10y", label: "10Y", years: 10 },
    { id: "20y", label: "20Y", years: 20 },
    { id: "max", label: "Max", years: null },
  ];

  function parseUtcDate(value) {
    const date = new Date(`${value}T00:00:00Z`);
    return Number.isNaN(date.getTime()) ? null : date;
  }

  function cutoffDateForRange(series, rangeId) {
    const option = CHART_RANGE_OPTIONS.find((item) => item.id === rangeId)
      || CHART_RANGE_OPTIONS.find((item) => item.id === "10y");
    if (!option || option.years === null || !series.length) return null;
    const lastPoint = series[series.length - 1];
    const lastDate = parseUtcDate(lastPoint.date);
    if (!lastDate) return null;
    const cutoff = new Date(lastDate.getTime());
    cutoff.setUTCFullYear(cutoff.getUTCFullYear() - option.years);
    return cutoff.toISOString().slice(0, 10);
  }

  function filterSeriesForRange(series, rangeId) {
    const rows = series || [];
    const cutoff = cutoffDateForRange(rows, rangeId);
    if (!cutoff) return rows.slice();
    return rows.filter((point) => point.date >= cutoff);
  }

  function filterEventsForRange(events, filteredSeries) {
    const dateSet = new Set((filteredSeries || []).map((point) => point.date));
    return (events || []).filter((event) => dateSet.has(event.date));
  }

  function filterChartForRange(chart, rangeId) {
    const series = filterSeriesForRange(chart.series || [], rangeId);
    return {
      ...chart,
      series,
      events: rangeId === "max" ? [] : filterEventsForRange(chart.events || [], series),
    };
  }

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
    const label = String(value ?? "").replace(/_/g, " ");
    const zh = zhLabel(label);
    return zh ? `${label} / ${zh}` : label;
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

  function bilingualLineLabel(labels, key) {
    const label = labels?.[key] || key;
    const zh = zhLabel(label);
    return zh ? `${escapeHtml(label)}<br><small>${escapeHtml(zh)}</small>` : escapeHtml(label);
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
            <span class="market-meta">
              <span class="market-meta-label"><span class="meta-en">Drawdown</span><span class="meta-zh">回撤</span></span>
              <strong class="market-meta-value">${escapeHtml(fmtNumber(market.latest.drawdown_pct))}%</strong>
            </span>
            <span class="market-meta">
              <span class="market-meta-label"><span class="meta-en">Through</span><span class="meta-zh">截至</span></span>
              <strong class="market-meta-value">${escapeHtml(market.data_through)}</strong>
            </span>
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
        state.selectedRelationshipId = null;
        state.selectedRatesDetailId = null;
        renderOverview();
        renderGdpRelationshipOverview();
        renderUsRatesLiquidity();
        renderDetailPanel();
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
              </div>
              <span class="gdp-card-confidence ${confidenceClass(card)}">
                <span class="confidence-level">${escapeHtml(card.macro_relationship_confidence)} ${escapeHtml("confidence")}</span>
                <span>${escapeHtml(zhLabel("confidence"))} ${escapeHtml(zhLabel(card.macro_relationship_confidence))}</span>
              </span>
              <strong class="gdp-card-title">${escapeHtml(card.title)}</strong>
              <span class="gdp-card-subtitle">
                <span class="subtitle-en">${escapeHtml(card.economy)} · primary lag ${escapeHtml(card.primary_lag_months)}M</span>
                <span class="subtitle-zh">${escapeHtml(zhLabel("primary lag"))} ${escapeHtml(card.primary_lag_months)}M</span>
              </span>
              <div class="gdp-card-summary">
                <span>
                  <small>${bilingualLabel("Signal")}</small>
                  <strong class="signal-status ${signal.className}" title="${escapeHtml(card.relationship_signal_usability)}">${escapeHtml(signal.label)}</strong>
                </span>
                <span>
                  <small>${bilingualLabel("Avg 10Y corr")}</small>
                  <strong>${escapeHtml(fmtCorrelationPercent(card.latest?.average_10y_correlation))}</strong>
                </span>
              </div>
            </button>
          `;
        }).join("")}
      </div>
    `;

    section.querySelectorAll(".gdp-card").forEach((button) => {
      button.addEventListener("click", () => {
        state.selectedRelationshipId = state.selectedRelationshipId === button.dataset.relationshipId
          ? null
          : button.dataset.relationshipId;
        state.selectedBenchmarkId = null;
        state.selectedRatesDetailId = null;
        renderOverview();
        renderGdpRelationshipOverview();
        renderUsRatesLiquidity();
        renderDetailPanel();
      });
    });
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

  function relationshipYearlyXAxisTicks(series) {
    const byYear = new Map();
    (series || []).forEach((point, index) => {
      const year = String(point.date || "").slice(0, 4);
      const month = String(point.date || "").slice(5, 7);
      if (!year || month !== "01") return;
      if (!byYear.has(year)) {
        byYear.set(year, { date: point.date, index });
      }
    });
    const years = [...byYear.keys()].sort();
    const step = Math.max(1, Math.ceil(years.length / X_AXIS_TICK_COUNT));
    return years
      .filter((year, index) => index % step === 0)
      .map((year) => {
        const point = byYear.get(year);
        return {
          date: point.date,
          x: xAt(point.index, series.length),
        };
      });
  }

  function fmtYear(value) {
    return String(value || "").slice(0, 4);
  }

  function renderRelationshipXAxisTicks(series, options = {}) {
    const ticks = options.categoricalXAxis
      ? series.map((point, index) => ({
        date: point.label || point.date,
        x: xAt(index, series.length),
      }))
      : options.xTickMode === "yearly"
        ? relationshipYearlyXAxisTicks(series)
        : xAxisTicks(series);
    return ticks
      .map((tick) => `
        <g class="chart-tick relationship-chart-tick" transform="translate(${tick.x.toFixed(2)} ${PLOT_BOTTOM})">
          <line y2="8"></line>
          <text class="chart-x-label" y="${RELATIONSHIP_X_LABEL_Y}" text-anchor="middle" x="0" transform="rotate(-35 0 ${RELATIONSHIP_X_LABEL_Y})">${escapeHtml(options.categoricalXAxis ? tick.date : options.xTickMode === "yearly" ? fmtYear(tick.date) : fmtMonthYear(tick.date))}</text>
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

  function renderRelationshipReferenceLines(lines, scale, formatValue = fmtNumber) {
    return (lines || [])
      .filter((line) => line.value !== null && line.value !== undefined)
      .map((line) => {
        const y = yAt(line.value, scale).toFixed(2);
        return `
          <g class="relationship-reference-line">
            <line x1="${MARGIN_LEFT}" y1="${y}" x2="${PLOT_RIGHT}" y2="${y}"></line>
            <text x="${PLOT_RIGHT - 6}" y="${Number(y) - 6}" text-anchor="end">${escapeHtml(line.label || formatValue(line.value))}</text>
          </g>
        `;
      })
      .join("");
  }

  function renderRelationshipLineChart(title, series, keys, labels = {}, options = {}) {
    const wideClass = options.wide ? " relationship-chart-wide" : "";
    const titleHtml = options.rawTitle ? title : escapeHtml(title);
    const hideHead = options.hideHead || false;
    if (!series || !series.length) {
      if (hideHead) return `<p class="status">No chart data available.</p>`;
      return `
        <div class="relationship-chart${wideClass}">
          <div class="relationship-chart-head">
            <h3>${titleHtml}</h3>
            <span>No data</span>
          </div>
          <p class="status">No chart data available.</p>
        </div>
      `;
    }
    const values = relationshipValues(series, keys);
    if (!values.length) {
      if (hideHead) return `<p class="status">No chart data available.</p>`;
      return `
        <div class="relationship-chart${wideClass}">
          <div class="relationship-chart-head">
            <h3>${titleHtml}</h3>
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
        ${hideHead ? "" : `
        <div class="relationship-chart-head">
          <h3>${titleHtml}</h3>
          <span>${escapeHtml(fmtMonthYear(firstLabel))} - ${escapeHtml(fmtMonthYear(lastLabel))}</span>
        </div>
        <div class="relationship-legend">
          ${keys.map((key, index) => `
            <span><i class="relationship-line-key relationship-line-key-${index}"></i>${options.rawLabels ? bilingualLineLabel(labels, key) : escapeHtml(lineLabel(labels, key))}</span>
          `).join("")}
          ${options.policyTrack ? `
            <span><i class="policy-legend-circle"></i>${bilingualLabel("Statement")}</span>
            <span><i class="policy-legend-triangle"></i>${bilingualLabel("Minutes")}</span>
            <span><i class="policy-color-swatch policy-color-hawkish"></i>${bilingualLabel("Hawkish")}</span>
            <span><i class="policy-color-swatch policy-color-dovish"></i>${bilingualLabel("Dovish")}</span>
            <span><i class="policy-color-swatch policy-color-mixed"></i>${bilingualLabel("Mixed")}</span>
            <span><i class="policy-color-swatch policy-color-neutral"></i>${bilingualLabel("Neutral")}</span>
          ` : ""}
        </div>
        `}
        <div class="chart-wrap relationship-chart-wrap">
          <svg class="relationship-chart-svg" viewBox="0 0 ${CHART_WIDTH} ${CHART_HEIGHT}" role="img" aria-label="${titleHtml}">
            ${renderRelationshipYAxisAndGrid(relationshipYAxisTicks(series, keys, Y_AXIS_TICK_COUNT, options.yDomain), scale, valueFormatter)}
            ${scale.min <= 0 && scale.max >= 0 ? `<line class="relationship-zero" x1="${MARGIN_LEFT}" y1="${yAt(0, scale).toFixed(2)}" x2="${PLOT_RIGHT}" y2="${yAt(0, scale).toFixed(2)}"></line>` : ""}
            ${renderRelationshipReferenceLines(options.referenceLines || [], scale, valueFormatter)}
            ${options.policyTrack ? "" : renderRelationshipEventMarkers(series, keys, scale, options.events || [])}
            ${keys.flatMap((key, index) => (
              chartSegments(series, key, scale, { lineShape: options.lineShape }).map((points) => `<polyline class="relationship-line relationship-line-${index}" points="${escapeHtml(points)}"></polyline>`)
            )).join("")}
            ${options.showDots ? keys.flatMap((key, index) => (
              series
                .filter((point) => point[key] !== null && point[key] !== undefined)
                .map((point) => {
                  const i = series.indexOf(point);
                  return `<circle class="relationship-dot relationship-dot-${index}" cx="${xAt(i, series.length).toFixed(2)}" cy="${yAt(point[key], scale).toFixed(2)}" r="3.5"></circle>`;
                })
            )).join("") : ""}
            ${options.showXAxis === false ? "" : renderRelationshipXAxisTicks(series, options)}
            ${options.policyTrack ? renderRelationshipPolicyTrack(series, options.events || [], scale) : ""}
          </svg>
          <div class="chart-tooltip" aria-hidden="true"></div>
        </div>
      </div>
    `;
  }

  function eventToneClass(event) {
    const tone = String(event?.marker_tone || event?.policy_tone || "unknown").toLowerCase();
    if (["dovish", "easing"].includes(tone)) return "dovish";
    if (["hawkish", "tightening"].includes(tone)) return "hawkish";
    if (tone === "mixed") return "mixed";
    return "unknown";
  }

  function eventMarkerTopY(point, keys, scale) {
    const values = keys
      .map((key) => point?.[key])
      .filter((value) => value !== null && value !== undefined && Number.isFinite(Number(value)))
      .map((value) => Number(value));
    if (!values.length) return MARGIN_TOP;
    return yAt(Math.max(...values), scale);
  }

  function eventMarkerBottomY(scale) {
    if (scale.min <= 0 && scale.max >= 0) return yAt(0, scale);
    return PLOT_BOTTOM;
  }

  function renderRelationshipEventMarkers(series, keys, scale, events = []) {
    if (!events.length) return "";
    const dateToIndex = new Map(series.map((point, index) => [point.date, index]));
    const bars = events
      .filter((event) => dateToIndex.has(event.date))
      .map((event) => {
        const index = dateToIndex.get(event.date);
        const barWidth = 8;
        const x = xAt(index, series.length) - barWidth / 2;
        const topY = eventMarkerTopY(series[index], keys, scale);
        const bottomY = eventMarkerBottomY(scale);
        const y = Math.min(topY, bottomY);
        const height = Math.max(Math.abs(bottomY - topY), 8);
        return `
          <g class="relationship-event-marker relationship-event-marker-${escapeHtml(eventToneClass(event))}">
            <rect class="relationship-event-bar" x="${x.toFixed(2)}" y="${y.toFixed(2)}" width="${barWidth}" height="${height.toFixed(2)}" rx="2"></rect>
          </g>
        `;
      })
      .join("");
    if (!bars) return "";
    return `
      <g class="relationship-event-rail">
        ${bars}
      </g>
    `;
  }

  function policyTrackEvents(events = []) {
    const rows = [];
    events.forEach((event) => {
      rows.push({
        ...event,
        policy_event_type: "statement",
        policy_track_date: event.date,
        policy_track_tone: event.policy_tone || event.statement_tone || "unknown",
      });
      if (event.minutes_status === "available") {
        rows.push({
          ...event,
          policy_event_type: "minutes",
          policy_track_date: event.minutes_display_month || event.date,
          policy_track_tone: minutesPolicyToneClass(event),
        });
      }
    });
    return rows;
  }

  function minutesPolicyToneClass(event) {
    const confirmation = String(event?.minutes_confirmation || "unknown").toLowerCase();
    const conviction = String(event?.policy_conviction || "unknown").toLowerCase();
    const riskBias = String(event?.risk_bias || event?.minutes_tone || "unknown").toLowerCase();
    if (["confirmed_but_divided", "weakened", "mixed", "contradicted"].includes(confirmation) || conviction === "divided") {
      return "mixed";
    }
    if (riskBias.includes("hawkish")) return "hawkish";
    if (riskBias.includes("dovish")) return "dovish";
    return "unknown";
  }

  function policyToneFill(tone) {
    if (tone === "hawkish") return "#B94B4B";
    if (tone === "dovish") return "#5C9C73";
    if (tone === "mixed") return "#D1A54F";
    return "#9A9288";
  }

  function renderRelationshipPolicyTrack(series, events = [], scale = null) {
    if (!series.length || !events.length) return "";
    const byDate = new Map(series.map((row, index) => [row.date, index]));
    const trackEvents = policyTrackEvents(events).filter((event) =>
      byDate.has(event.policy_track_date || event.date)
    );
    if (!trackEvents.length) return "";
    const hasZero = scale && scale.min <= 0 && scale.max >= 0;
    const baseY = hasZero ? yAt(0, scale) : PLOT_BOTTOM + 20;
    const statY = baseY - 6;
    const minsY = baseY + 6;
    const statementMarkers = trackEvents
      .filter((e) => e.policy_event_type === "statement")
      .map((e) => {
        const index = byDate.get(e.policy_track_date || e.date);
        const x = xAt(index, series.length);
        const fill = policyToneFill(eventToneClass(e));
        return `<g transform="translate(${x.toFixed(2)} ${statY})"><circle r="4" fill="${fill}" stroke="#FFFFFF" stroke-width="1.5"></circle></g>`;
      }).join("");
    const minutesMarkers = trackEvents
      .filter((e) => e.policy_event_type === "minutes")
      .map((e) => {
        const index = byDate.get(e.policy_track_date || e.date);
        const x = xAt(index, series.length);
        const fill = policyToneFill(minutesPolicyToneClass(e));
        return `<g transform="translate(${x.toFixed(2)} ${minsY})"><path d="M0 -5 L5 5 L-5 5 Z" fill="${fill}" stroke="#FFFFFF" stroke-width="1.5"></path></g>`;
      }).join("");
    return `
      <g class="relationship-policy-track" aria-label="FOMC policy track">
        <line class="relationship-policy-axis" x1="${MARGIN_LEFT}" y1="${statY}" x2="${CHART_WIDTH - MARGIN_RIGHT}" y2="${statY}"></line>
        <line class="relationship-policy-axis" x1="${MARGIN_LEFT}" y1="${minsY}" x2="${CHART_WIDTH - MARGIN_RIGHT}" y2="${minsY}"></line>
        ${statementMarkers}
        ${minutesMarkers}
      </g>`;
  }

  function attachRelationshipChartTooltip(svg, tooltip, series, keys, labels = {}, options = {}) {
    if (!svg || !tooltip || !series.length) return;
    const wrap = svg.parentElement;
    const valueFormatter = options.valueFormatter || fmtNumber;
    const eventsByDate = new Map((options.events || []).map((event) => [event.date, event]));
    let lastIndex = -1;
    let tooltipRect = null;

    function _extraFormatter(value, fmt) {
      if (value === null || value === undefined) return "n/a";
      if (fmt === "percent") return fmtRate(value);
      return fmtNumber(value);
    }

    function positionRelationshipTooltip(index) {
      const wrapRect = wrap.getBoundingClientRect();
      const left = index < series.length / 2 ? wrapRect.width - tooltipRect.width - 12 : 12;
      tooltip.style.left = `${Math.max(8, left)}px`;
      tooltip.style.top = "12px";
      tooltip.classList.add("relationship-tooltip-pinned");
    }

    function show(index, clientX, clientY) {
      const point = series[index];
      if (index !== lastIndex) {
        const rows = keys.map((key) => {
          const value = point[key];
          const text = value === null || value === undefined ? "n/a" : valueFormatter(value);
          return `
            <div class="chart-tooltip-row">
              <span>${options.rawLabels ? bilingualLineLabel(labels, key) : escapeHtml(lineLabel(labels, key))}</span>
              <strong>${escapeHtml(text)}</strong>
            </div>
          `;
        }).join("");
        const extraRows = (options.tooltipExtra || []).map((extra) => {
          const value = point[extra.key];
          return `
            <div class="chart-tooltip-row">
              <span>${escapeHtml(lineLabel({ [extra.key]: extra.label }, extra.key))}</span>
              <strong>${escapeHtml(_extraFormatter(value, extra.format))}</strong>
            </div>
          `;
        }).join("");
        const event = eventsByDate.get(point.date);
        const eventRows = event ? `
          <div class="chart-tooltip-row">
            <span>${escapeHtml(event.label || "FOMC")}</span>
            <strong>${escapeHtml(event.event_date || event.date)}</strong>
          </div>
          <div class="chart-tooltip-row">
            <span>Statement tone</span>
            <strong>${escapeHtml(event.statement_tone || event.policy_tone || "unknown")}</strong>
          </div>
          <div class="chart-tooltip-row">
            <span>Tone change</span>
            <strong>${escapeHtml(event.tone_change || "unknown")}</strong>
          </div>
          <div class="chart-tooltip-row">
            <span>Confidence</span>
            <strong>${escapeHtml(event.confidence || "n/a")}</strong>
          </div>
        ` : "";
        tooltip.innerHTML = `
          <div><strong>${escapeHtml(fmtMonthYear(point.date))}</strong></div>
          ${rows}
          ${extraRows}
          ${eventRows}
        `;
        lastIndex = index;
        tooltip.style.left = "-9999px";
        tooltip.style.top = "-9999px";
        tooltip.classList.add("visible");
        tooltipRect = tooltip.getBoundingClientRect();
      }
      positionRelationshipTooltip(index);
    }

    function hide() {
      tooltip.classList.remove("visible");
      tooltip.classList.remove("relationship-tooltip-pinned");
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
          <h3>${bilingualTitle("Quadnomial distribution")}</h3>
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
          <h3>${bilingualTitle("Lag comparison")}</h3>
          <span>${bilingualLabel("Method primary")} lag</span>
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
      bilingualTitle("Rolling 10Y correlations by lag"),
      payload.lag_correlation_series,
      keys,
      payload.lag_correlation_labels || {},
      {
        wide: true,
        rawTitle: true,
        rawLabels: true,
        valueFormatter: fmtCorrelationPercent,
      }
    );
  }

  function renderYoyComparison(payload) {
    return renderRelationshipLineChart(
      bilingualTitle("Index YoY vs GDP YoY"),
      payload.yoy_series,
      ["index", "gdp"],
      { index: "Index YoY", gdp: "GDP YoY" },
      {
        wide: true,
        rawTitle: true,
        rawLabels: true,
        valueFormatter: (value) => `${fmtNumber(value)}%`,
      }
    );
  }

  function renderPrimaryCorrelationComparison(payload) {
    return renderRelationshipLineChart(
      bilingualTitle("Rolling correlation"),
      payload.correlation_series,
      ["value"],
      { value: `${payload.primary_lag_months}M lag rolling correlation` },
      {
        wide: true,
        rawTitle: true,
        rawLabels: true,
        valueFormatter: fmtCorrelationPercent,
      }
    );
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

  function fmtUsdMillions(value) {
    if (value === null || value === undefined) return "n/a";
    const absValue = Math.abs(value);
    const sign = value < 0 ? "-" : "";
    if (absValue >= 1000000) return `${sign}$${fmtNumber(absValue / 1000000)}T`;
    if (absValue >= 1000) return `${sign}$${fmtNumber(absValue / 1000)}B`;
    return `${sign}$${fmtNumber(absValue)}M`;
  }

  function fmtSignedUsdMillions(value) {
    if (value === null || value === undefined) return "n/a";
    const formatted = fmtUsdMillions(value);
    return value > 0 ? `+${formatted}` : formatted;
  }

  function fmtNumber(value) {
    if (value === null || value === undefined) return "n/a";
    return Number(value).toFixed(2);
  }

  function fmtPctDecimal(value) {
    if (value === null || value === undefined) return "n/a";
    return `${(Number(value) * 100).toFixed(2)}%`;
  }

  function trendArrow(value) {
    if (value === null || value === undefined) return "";
    const numericValue = Number(value);
    if (numericValue > 0) return "↑ ";
    if (numericValue < 0) return "↓ ";
    return "→ ";
  }

  function fmtSignedPctDecimal(value) {
    if (value === null || value === undefined) return "n/a";
    const numericValue = Number(value);
    const sign = numericValue > 0 ? "+" : "";
    return `${sign}${(numericValue * 100).toFixed(2)}%`;
  }

  function fmtDirectionalPct(value) {
    if (value === null || value === undefined) return "n/a";
    return `${trendArrow(value)}${fmtSignedPctDecimal(value)}`;
  }

  function fmtPercentRank(value) {
    if (value === null || value === undefined) return "n/a";
    const rank = Math.round(Number(value) * 100);
    const lastTwoDigits = rank % 100;
    if (lastTwoDigits >= 11 && lastTwoDigits <= 13) return `${rank}th`;
    const lastDigit = rank % 10;
    if (lastDigit === 1) return `${rank}st`;
    if (lastDigit === 2) return `${rank}nd`;
    if (lastDigit === 3) return `${rank}rd`;
    return `${rank}th`;
  }

  function fmtDirectionalPercentRank(value, directionValue) {
    if (value === null || value === undefined) return "n/a";
    return `${trendArrow(directionValue)}${fmtPercentRank(value)}`;
  }

  const ZH_LABELS = {
    // US Rates
    "10-Year Treasury": "10年期国债",
    "2-Year Treasury": "2年期国债",
    "10Y - 2Y Spread": "10Y-2Y利差",
    "10Y Real Rate": "10年期实际利率",
    "CPI Real Rate": "CPI实际利率",
    "Fed Funds": "联邦基金利率",
    "Breakeven": "盈亏平衡通胀率",
    "VIX": "VIX波动率指数",
    "10Y Treasury Minus CPI YoY": "10年期国债减CPI同比",
    "CPI Real Rate vs VIX": "CPI实际利率 vs VIX",
    "Real Rate": "实际利率",
    "Comparison": "对比",
    "Interpretation": "解读",
    "Yield Curve Analysis": "收益率曲线分析",
    "US Yield Curve - Comparative Analysis": "美国收益率曲线对比分析",
    "US Real Yield Curve (TIPS) - Comparative Analysis": "美国实际收益率曲线(TIPS)对比分析",
    // GDP Relationships
    "Index YoY": "指数同比",
    "GDP YoY": "GDP同比",
    "Index YoY vs GDP YoY": "指数同比 vs GDP同比",
    "No lag": "无滞后",
    "3M lag": "3个月滞后",
    "Rolling 10Y correlations by lag": "按滞后期的10年滚动相关性",
    "Lag comparison": "滞后比较",
    "Quadnomial distribution": "四分区分布",
    "Rolling correlation": "滚动相关性",
    "Signal": "信号",
    "Signal usability": "信号可用性",
    "Portfolio Bias": "组合偏向",
    "Avg 10Y corr": "10年平均相关性",
    "Average 10Y Correlation": "10年平均相关性",
    "Same Direction": "同向率",
    "Method Coverage": "课程覆盖",
    "Current Case": "当前案例",
    "confidence": "置信度",
    "High": "高",
    "Medium": "中",
    "Low": "低",
    "high": "高",
    "medium": "中",
    "low": "低",
    "primary lag": "滞后期",
    "usable": "可用",
    "caution": "谨慎",
    "weak": "弱",
    "not usable": "不可用",
    "long bias": "多头偏向",
    "defensive": "防御性",
    "requires GDP forecast": "需要GDP预测",
    "Method primary lag": "课程主要滞后",
    "Method primary": "课程主要滞后",
    // Market Phase
    "Drawdown": "回撤",
    "Through": "截至",
    "Close": "收盘价",
    "Rolling High": "滚动高点",
    "Bear/Bull Level": "熊/牛市分界线",
    "Data Through": "数据截至",
    "Bull segment": "牛市区间",
    "Bear segment": "熊市区间",
    "Bear/Bull level": "熊/牛市分界线",
    "bear market": "熊市",
    "bull market": "牛市",
    // Chart defaults
    "Value": "数值",
    "Latest": "最新",
    // Credit Conditions
    "Credit Conditions": "信用环境",
    "Credit Conditions Diagnostics": "信用环境诊断",
    "BBB Credit Spread": "BBB信用利差",
    "CCC Credit Spread": "CCC信用利差",
    "CCC vs BBB Quality Spread": "CCC与BBB质量利差",
    "Data Coverage": "数据覆盖",
    "Data Gap": "数据缺口",
    "No Interpolation": "不插值",
    "BBB - 10Y": "BBB - 10年",
    "CCC - 10Y": "CCC - 10年",
    "CCC - BBB": "CCC - BBB",
    "Overall Credit Risk": "整体信用风险",
    "Quality Dispersion": "信用质量分化",
    "Healthy": "健康",
    "Weak Credit Warning": "弱信用预警",
    "Risk Rising": "风险上升",
    "Crisis Stress": "危机压力",
    "Mixed": "混合",
    "Missing": "缺失",
    "Overall": "整体",
    "Weak Credit": "弱信用",
    "Level Zone": "水平区间",
    "Full-History Percentile": "全样本历史分位",
    "1M Trend": "1个月趋势",
    "3M Trend": "3个月趋势",
    "Acceleration": "加速",
    "Very Low": "很低",
    "Normal": "正常",
    "Tightening": "开始紧张",
    "Stressed": "承压",
    "Crisis": "危机",
    "Low Dispersion": "分化很小",
    "Weak Credit Pressure": "弱信用承压",
    "Serious Deterioration": "明显恶化",
    "Elevated": "偏高",
    "Rising": "上升",
    "Falling": "下降",
    "Stable": "稳定",
    "Accelerating Up": "加速上升",
    "Accelerating Down": "加速下降",
    "No Acceleration": "未加速",
    // Growth Cycle
    "State": "状态",
    "Change": "变化",
    "Shock": "冲击",
    "YoY Growth": "同比增长",
    "3M Change": "3个月变化",
    "MoM Shock": "月度冲击",
    "M2 Level": "M2总量",
    "M2 Money Supply": "M2货币供应",
    "M2 YoY Growth": "M2同比增长",
    "M2 3M Change": "M2三个月变化",
    "M2 MoM Shock Events": "M2月度冲击事件",
    "Shock Signal": "冲击信号",
    "Extreme Injection": "极端注入",
    "Strong Injection": "较强注入",
    "Strong Contraction": "较强收缩",
    "Extreme Contraction": "极端收缩",
    // ISM Manufacturing
    "ISM Business Cycle": "商业周期",
    "ISM Growth Drivers": "增长驱动力",
    "ISM Inflation & Supply": "通胀与供应",
    "ISM Industry Breadth": "行业广度",
    "Business Cycle": "商业周期",
    "Growth Drivers": "增长驱动力",
    "Inflation & Supply": "通胀与供应",
    "Industry Breadth": "行业广度",
    "Pending": "待完成",
    "PMI": "采购经理指数",
    "Above 50": "高于50",
    "Available drivers": "可用指标数",
    // ISM Industries
    "Computer & Electronic Products": "计算机与电子产品",
    "Wood Products": "木制品",
    "Furniture & Related Products": "家具及相关产品",
    "Machinery": "机械设备",
    "Transportation Equipment": "运输设备",
    "Food, Beverage & Tobacco Products": "食品、饮料与烟草",
    "Textile Mills": "纺织业",
    "Apparel, Leather & Allied Products": "服装、皮革及相关产品",
    "Paper Products": "造纸业",
    "Printing & Related Support Activities": "印刷及相关支持",
    "Petroleum & Coal Products": "石油与煤炭产品",
    "Chemical Products": "化工产品",
    "Plastics & Rubber Products": "塑料与橡胶制品",
    "Nonmetallic Mineral Products": "非金属矿物制品",
    "Primary Metals": "基础金属",
    "Fabricated Metal Products": "金属制品",
    "Electrical Equipment, Appliances & Components": "电气设备、家电及组件",
    "Miscellaneous Manufacturing": "其他制造业",
    // Inflation Context
    "Growth Cycle": "增长周期",
    "Inflation Context": "通胀环境",
    "Core PCE YoY": "核心PCE同比",
    "Gap vs Fed 2% Target": "相对美联储2%目标",
    "Fed 2% Target": "美联储2%目标",
    "Fed Target (since 2012)": "美联储目标（2012年起）",
    "Fed Target": "美联储目标",
    "GDP Expectations": "GDP预期",
    "Pending Inputs": "待输入",
    "Expected Direction": "预期方向",
    "Required Inputs": "所需输入",
    "Supporting Context": "辅助背景",
    "Not Ready": "未就绪",
    "Fed Balance Sheet": "美联储资产负债表",
    "Liquidity Context": "流动性背景",
    "Total Assets": "总资产",
    "Total Assets 13W Net Change": "总资产13周净变化",
    "Treasury 13W Net Change": "美债持仓13周净变化",
    "MBS 13W Net Change": "MBS持仓13周净变化",
    "Treasury 13W Change": "美债持仓13周净变化",
    "MBS 13W Change": "MBS持仓13周净变化",
    "Fed Total Assets YoY": "美联储总资产同比",
    "Fed Balance Sheet 13W Composition": "美联储资产负债表13周构成",
    "Above Target": "高于目标",
    "Near Target": "接近目标",
    "Below Target": "低于目标",
    "FOMC Calendar": "FOMC日历",
    "Policy Timing": "政策时点",
    "Next Meeting": "下次会议",
    "FOMC Tone": "FOMC倾向",
    "Policy Track": "政策轨道",
    "Statement": "声明",
    "Minutes": "纪要",
    "Latest Tone": "最新倾向",
    "Next FOMC Meeting": "下次FOMC会议",
    "Latest FOMC Tone": "最近FOMC倾向",
    "Next Meeting Date": "下次会议日期",
    "Action": "政策动作",
    "Guidance": "前瞻指引",
    "Language": "声明语气",
    "Bias": "综合倾向",
    "Change": "较上次",
    "Hold": "维持",
    "Cut": "降息",
    "Hike": "加息",
    "Neutral": "中性",
    "Hawkish": "偏鹰",
    "Dovish": "偏鸽",
    "Mixed": "混合",
    "Mild Hawkish": "温和偏鹰",
    "Mild Dovish": "温和偏鸽",
    "More Hawkish vs previous": "较上次更偏鹰",
    "More Dovish vs previous": "较上次更偏鸽",
    "Unchanged": "未变化",
    "Less Hawkish vs previous": "较上次偏鹰减弱",
    "Less Dovish vs previous": "较上次偏鸽减弱",
    "Policy meeting": "政策会议",
    "Includes SEP": "包含经济预测摘要",
    "No scheduled meeting": "暂无已安排会议",
    "Tone unavailable": "暂无倾向",
    "Pending review": "等待审核",
    "FOMC Policy Read": "FOMC政策解读",
    "Statement Bias": "声明基调",
    "Minutes Confirmation": "纪要确认",
    "Risk Focus": "风险焦点",
    "Policy Conviction": "政策坚定度",
    "Confirmed": "确认",
    "Confirmed But Divided": "确认但有分歧",
    "Weakened": "削弱",
    "Stronger Underneath": "内部更强",
    "Contradicted": "矛盾",
    "Inflation": "通胀",
    "Growth Labor": "增长/就业",
    "Financial Stability": "金融稳定",
    "Balanced": "平衡",
    "Moderate": "中等",
    "Divided": "分歧",
    "Pending": "待处理",
  };

  function zhLabel(label) {
    return ZH_LABELS[label] || null;
  }

  function bilingualLabel(label) {
    const zh = zhLabel(label);
    return zh ? `${escapeHtml(label)}<small>${escapeHtml(zh)}</small>` : escapeHtml(label);
  }

  const CREDIT_DETAIL_MAP = {};

  const CREDIT_STATUS_META = {
    healthy: { label: "Healthy", zh: "健康" },
    weak_credit_warning: { label: "Weak Credit Warning", zh: "弱信用预警" },
    risk_rising: { label: "Risk Rising", zh: "风险上升" },
    crisis_stress: { label: "Crisis Stress", zh: "危机压力" },
    mixed: { label: "Mixed", zh: "混合" },
    missing: { label: "Missing", zh: "缺失" },
  };

  const CREDIT_REGIME_VISIBLE_POINTS = 126;

  function creditStatusMeta(status) {
    return CREDIT_STATUS_META[status] || CREDIT_STATUS_META.missing;
  }

  function creditDiagnosticInterpretation(status) {
    const messages = {
      healthy: {
        text: "Overall credit risk is low and quality dispersion is contained. Credit conditions are supportive for risk appetite.",
        zh: "整体信用风险较低，信用质量分化受控。信用环境对风险偏好较友好。",
      },
      weak_credit_warning: {
        text: "Overall credit risk is low, but CCC-BBB quality dispersion is elevated. The market is not broadly stressed, but weak borrowers are still under pressure.",
        zh: "整体信用风险不高，但CCC-BBB质量利差偏高。市场并非全面承压，但弱信用主体仍被要求更高风险补偿。",
      },
      risk_rising: {
        text: "Credit spreads are rising or moving into stressed zones. Risk is being repriced across credit markets.",
        zh: "信用利差正在上升，或已进入承压区间。信用市场正在重新定价风险。",
      },
      crisis_stress: {
        text: "Credit stress is broad and severe. Treat this as a high-risk credit regime until spreads stop accelerating.",
        zh: "信用压力广泛且严重。在利差停止加速前，应视为高风险信用环境。",
      },
      mixed: {
        text: "Credit signals are mixed. Read level, percentile, and trend together before drawing a directional conclusion.",
        zh: "信用信号不一致。需要结合水平、历史分位和趋势一起判断。",
      },
      missing: {
        text: "Credit condition data is incomplete. Refresh the credit series before interpreting this section.",
        zh: "信用环境数据不完整。解读前需要先刷新信用数据。",
      },
    };
    return messages[status] || messages.missing;
  }

  function renderRateCard(card) {
    const detailId = card.id === "credit_conditions"
      ? "credit_conditions_diagnostics"
      : CREDIT_DETAIL_MAP[card.id] || card.id;
    const selected = state.selectedRatesDetailId === detailId ? " selected" : "";
    if (card.id === "credit_conditions") {
      const currentValue = card.value || "missing";
      const meta = creditStatusMeta(currentValue);
      return `
        <button class="rates-signal-card rates-signal-card-wide${selected}" type="button" data-rates-detail-id="${escapeHtml(detailId)}">
          <span>${bilingualLabel(card.label)}</span>
          <strong>${escapeHtml(meta.label)}<br><small>${escapeHtml(meta.zh)}</small></strong>
        </button>
      `;
    }
    return `
      <button class="rates-signal-card${selected}" type="button" data-rates-detail-id="${escapeHtml(detailId)}">
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

  function renderCurveStatusCard(curveStatus, interpretation) {
    const colorClass = `rates-signal-card-${curveStatus || "missing"}`;
    const label = (curveStatus || "missing").toUpperCase();
    return `
      <span class="rates-signal-card rates-signal-card-wide ${colorClass}">
        <span>${bilingualLabel("Curve Status")}</span>
        <strong>${escapeHtml(fmtStatus(label))}</strong>
        <span class="rates-interpretation-text">${escapeHtml(interpretation || "")}</span>
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
    const creditIds = new Set([
      "bbb_credit_spread",
      "ccc_credit_spread",
      "ccc_bbb_quality_spread",
      "credit_conditions",
    ]);
    const rateCards = headline.filter((card) => !creditIds.has(card.id));
    const creditCards = headline.filter((card) => creditIds.has(card.id));
    const curveStatus = payload.derived?.curve_status || "missing";
    const interpretation = payload.derived?.method_interpretation || "";
    const creditStatus = payload.derived?.credit_conditions_status || "missing";
    section.innerHTML = `
      <div class="relationship-head">
        <div>
          <h2>US Rates & Credit</h2>
        </div>
        <span class="mock-pill">${escapeHtml(payload.as_of ? `As of ${fmtDate(payload.as_of)}` : "Import needed")}</span>
      </div>
      ${rateCards.length ? `<div class="rates-signal-grid">${rateCards.map(renderRateCard).join("")}${renderSupportCard("Breakeven", fmtRate(payload.derived?.ten_year_breakeven_inflation))}${renderSupportCard("VIX", fmtNumber(payload.derived?.vix))}${renderCurveStatusCard(curveStatus, interpretation)}</div>` : ""}
      ${creditCards.length ? `
        <div class="rates-detail gdp-detail">
          <div class="rates-chart-subtitle">
            <div class="credit-conditions-head">
              <p class="eyebrow">${bilingualLabel("Credit Conditions")}</p>
              ${payload.credit_as_of ? `<span class="mock-pill">Data as of ${escapeHtml(payload.credit_as_of)}</span>` : ""}
            </div>
            <p>Credit spreads and quality spreads across rating tiers.<br><small>各评级层的信用利差和质量利差</small></p>
          </div>
          <div class="rates-signal-grid">${creditCards.map(renderRateCard).join("")}</div>
        </div>
      ` : ""}
    `;
    section.querySelectorAll("[data-rates-detail-id]").forEach((button) => {
      button.addEventListener("click", () => {
        state.selectedRatesDetailId = state.selectedRatesDetailId === button.dataset.ratesDetailId
          ? null
          : button.dataset.ratesDetailId;
        state.selectedBenchmarkId = null;
        state.selectedRelationshipId = null;
        if (state.selectedRatesDetailId !== "yield_curve_shape") {
          state.selectedNominalCurrentDate = null;
          state.selectedNominalComparisonDate = null;
          state.selectedRealCurrentDate = null;
          state.selectedRealComparisonDate = null;
        }
        renderOverview();
        renderGdpRelationshipOverview();
        renderUsRatesLiquidity();
        renderDetailPanel();
      });
    });
  }

  async function loadGrowthCycle() {
    try {
      const response = await fetch("/api/macro-dashboard/growth-cycle");
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      state.growthCycle = await response.json();
      state.growthCycleError = null;
    } catch (error) {
      state.growthCycle = null;
      state.growthCycleError = error.message;
    }
    renderGrowthCycle();
  }

  function growthCycleCardsById(cards) {
    const result = {};
    for (const card of cards || []) {
      result[card.id] = card;
    }
    return result;
  }

  function growthCycleStatusLabel(status) {
    const labels = {
      available: "Available",
      missing: "Missing",
      pending_inputs: "Pending Inputs",
    };
    return labels[status] || fmtStatus(status || "unknown");
  }

  function renderGrowthCycleStatusPanel(section) {
    const period = section.period ? `<small>${escapeHtml(fmtDate(section.period))}</small>` : "";
    return `
      <div class="growth-section-status growth-section-status-${escapeHtml(section.status || "missing")}">
        <strong>${escapeHtml(growthCycleStatusLabel(section.status))}</strong>
        ${period}
      </div>
    `;
  }

  function renderGrowthCycleSection(section, cardsById) {
    const cardIds = section.cards || [];
    const cards = cardIds.map((cardId) => cardsById[cardId]).filter(Boolean);
    const cardHtml = cards.map((card) => {
      if (card.id === "fomc_calendar" || card.id === "fomc_tone") {
        return renderFomcCard(card);
      }
      return renderCard(card);
    }).join("");
    return `
      <section class="growth-section growth-section-${escapeHtml(section.id || "unknown")}">
        <div class="growth-section-head">
          <div>
            <h3>${escapeHtml(section.title || "")}</h3>
            <p>${escapeHtml(section.subtitle || "")}</p>
          </div>
          ${section.period ? `<span class="mock-pill">Data as of ${escapeHtml(fmtDate(section.period))}</span>` : ""}
        </div>
        ${cardHtml ? `<div class="growth-section-card-grid">${cardHtml}</div>` : renderGrowthCycleStatusPanel(section)}
      </section>
    `;
  }

  function renderGrowthCycleSections(sections, cards) {
    const cardsById = growthCycleCardsById(cards);
    return (sections || [])
      .map((section) => renderGrowthCycleSection(section, cardsById))
      .join("");
  }

  function renderGrowthCycle() {
    const section = $("growthCycle");
    if (!section) return;
    const head = section.querySelector(".relationship-head");
    if (state.growthCycleError) {
      section.innerHTML = `${head.outerHTML}<p class="growth-empty">Failed to load growth cycle data.</p>`;
      return;
    }
    if (!state.growthCycle) {
      section.innerHTML = `${head.outerHTML}<div class="growth-loading">Loading growth cycle data...</div>`;
      return;
    }
    if (state.growthCycle.missing) {
      section.innerHTML = `${head.outerHTML}<p class="growth-empty">${escapeHtml(state.growthCycle.missing)}</p>`;
      return;
    }
    const cards = state.growthCycle.headline || [];
    const sections = state.growthCycle.sections || [];
    const sectionHtml = renderGrowthCycleSections(sections, cards);
    section.innerHTML = `
      ${head.outerHTML}
      ${sectionHtml ? `
        <div class="rates-detail gdp-detail">
          <div class="growth-section-list">
            ${sectionHtml}
          </div>
        </div>
      ` : ""}
    `;
    section.querySelectorAll("[data-growth-cycle-detail-id]").forEach((button) => {
      button.addEventListener("click", () => {
        state.selectedGrowthCycleDetailId = state.selectedGrowthCycleDetailId === button.dataset.growthCycleDetailId
          ? null
          : button.dataset.growthCycleDetailId;
        state.selectedBenchmarkId = null;
        state.selectedRelationshipId = null;
        state.selectedRatesDetailId = null;
        renderOverview();
        renderGdpRelationshipOverview();
        renderUsRatesLiquidity();
        renderGrowthCycle();
        renderDetailPanel();
      });
    });
  }

  async function loadGrowthCycleDetail(detailId) {
    if (state.growthCycleDetailsById[detailId]) {
      return state.growthCycleDetailsById[detailId];
    }
    const response = await fetch(`/api/macro-dashboard/growth-cycle/${encodeURIComponent(detailId)}`);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const payload = await response.json();
    state.growthCycleDetailsById[detailId] = payload;
    return payload;
  }

  function renderIsmRelationshipContext(context) {
    if (!context) return "";
    return `
      <div class="ism-relationship-context ism-relationship-context-${escapeHtml(context.state || "mixed")}">
        <strong class="ism-relationship-context-state">${escapeHtml(context.label || "Mixed")}</strong>
        <span>${escapeHtml(context.description || "")}</span>
      </div>
    `;
  }

  function fmtIsmSmallMultipleValue(value, unit) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return "n/a";
    if (unit === "percent") return `${Number(value).toFixed(1)}%`;
    return Number(value).toFixed(1);
  }

  function rebaseVisibleSmallMultipleSeries(chart) {
    const series = (chart.series || []).map((point) => ({ ...point }));
    const basePoint = series.find((point) => point.sp500_close !== null && point.sp500_close !== undefined);
    const base = basePoint?.sp500_close;
    if (!base) return series;
    return series.map((point) => ({
      ...point,
      sp500_index: point.sp500_close === null || point.sp500_close === undefined
        ? null
        : Number(((point.sp500_close / base) * 100).toFixed(4)),
    }));
  }

  function rebaseVisibleSmallMultipleChart(chart) {
    return {
      ...chart,
      series: rebaseVisibleSmallMultipleSeries(chart),
    };
  }

  function ismSparklineValues(series, key, referenceLines = []) {
    return [
      ...series.map((point) => point[key]),
      ...referenceLines.map((line) => line.value),
    ].filter((value) => value !== null && value !== undefined && Number.isFinite(Number(value)));
  }

  function ismSparklineScale(series, key, referenceLines = []) {
    const values = ismSparklineValues(series, key, referenceLines);
    if (!values.length) return null;
    const min = Math.min(...values);
    const max = Math.max(...values);
    const padding = Math.max((max - min) * 0.12, Math.abs(max || min || 1) * 0.02, 0.5);
    return {
      min: min - padding,
      max: max + padding,
      range: max - min + padding * 2 || 1,
    };
  }

  function ismSparklineXAt(index, count) {
    if (count <= 1) return 48 + 850 / 2;
    return 48 + (index / (count - 1)) * 850;
  }

  function ismSparklineYAt(value, scale) {
    return 10 + ((scale.max - value) / scale.range) * 42;
  }

  function ismSparklineSegments(series, key, scale, lineShape) {
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
      const x = ismSparklineXAt(index, series.length);
      const y = ismSparklineYAt(value, scale);
      if (lineShape === "step_after" && current.length) {
        const previous = current[current.length - 1];
        const previousY = previous.split(",")[1];
        current.push(`${x.toFixed(2)},${previousY}`);
      }
      current.push(`${x.toFixed(2)},${y.toFixed(2)}`);
    });
    if (current.length) segments.push(current);
    return segments.map((segment) => segment.join(" "));
  }

  function ismSparklineYearTicks(series) {
    const byYear = new Map();
    series.forEach((point, index) => {
      const year = String(point.date || "").slice(0, 4);
      const month = String(point.date || "").slice(5, 7);
      if (!year || month !== "01") return;
      if (!byYear.has(year)) {
        byYear.set(year, { date: point.date, index });
      }
    });
    const years = [...byYear.keys()].sort();
    const step = Math.max(1, Math.ceil(years.length / 8));
    return years
      .filter((year, index) => index % step === 0)
      .map((year) => ({
        year,
        x: ismSparklineXAt(byYear.get(year).index, series.length),
      }));
  }

  function renderIsmSparklineReferenceLines(panel, scale) {
    return (panel.reference_lines || [])
      .filter((line) => line.value !== null && line.value !== undefined)
      .map((line) => {
        const y = ismSparklineYAt(line.value, scale);
        return `
          <g class="ism-sparkline-reference">
            <line x1="48" y1="${y.toFixed(2)}" x2="898" y2="${y.toFixed(2)}"></line>
            <text x="892" y="${Math.max(12, y - 5).toFixed(2)}" text-anchor="end">${escapeHtml(line.label || "")}</text>
          </g>
        `;
      })
      .join("");
  }

  function renderIsmSparklineAxis(series, showXAxis) {
    if (!showXAxis) return "";
    return ismSparklineYearTicks(series)
      .map((tick) => `
        <g class="ism-sparkline-x-tick" transform="translate(${tick.x.toFixed(2)} 60)">
          <line y2="4"></line>
          <text y="15" text-anchor="middle">${escapeHtml(tick.year)}</text>
        </g>
      `)
      .join("");
  }

  function renderIsmSparklineSvg(series, panel, unit, showXAxis) {
    const key = panel.key;
    const scale = ismSparklineScale(series, key, panel.reference_lines || []);
    if (!scale) return `<p class="status">No chart data available.</p>`;
    const segments = ismSparklineSegments(series, key, scale, panel.line_shape);
    const latest = [...series].reverse().find((point) => point[key] !== null && point[key] !== undefined);
    return `
      <div class="ism-sparkline-plot">
        <svg class="relationship-chart-svg ism-sparkline-svg" viewBox="0 0 960 76" role="img" aria-label="${escapeHtml(panel.title || key)}">
          <line class="ism-sparkline-axis" x1="48" y1="60" x2="898" y2="60"></line>
          ${scale.min <= 0 && scale.max >= 0 ? `<line class="ism-sparkline-zero" x1="48" y1="${ismSparklineYAt(0, scale).toFixed(2)}" x2="898" y2="${ismSparklineYAt(0, scale).toFixed(2)}"></line>` : ""}
          ${renderIsmSparklineReferenceLines(panel, scale)}
          ${segments.map((points) => `<polyline class="relationship-line relationship-line-0 ism-sparkline-line" points="${escapeHtml(points)}"></polyline>`).join("")}
          ${latest ? `<text class="ism-sparkline-latest" x="930" y="${ismSparklineYAt(latest[key], scale).toFixed(2)}" text-anchor="end">${escapeHtml(fmtIsmSmallMultipleValue(latest[key], unit))}</text>` : ""}
          ${renderIsmSparklineAxis(series, showXAxis)}
        </svg>
      </div>
    `;
  }

  function renderIsmSmallMultiplePanel(chart, panel, panelIndex) {
    const series = chart.series || [];
    const key = panel.key;
    const title = panel.title || key;
    const unit = panel.unit || "raw";
    const panelSeries = series.map((point) => ({
      date: point.date,
      gdp_period: point.gdp_period,
      [key]: point[key],
    }));
    const showXAxis = panelIndex === (chart.panels || []).length - 1;
    return `
      <div class="ism-small-panel" data-ism-panel-key="${escapeHtml(key)}">
        <div class="ism-small-panel-meta">
          <strong>${escapeHtml(title)}</strong>
          <span>${escapeHtml(panel.subtitle || panel.cadence || unit)}</span>
        </div>
        ${renderIsmSparklineSvg(panelSeries, panel, unit, showXAxis)}
      </div>
    `;
  }

  function renderIsmSmallMultiples(chart) {
    const visibleChart = rebaseVisibleSmallMultipleChart(chart);
    return `
      <article class="relationship-chart-card ism-small-multiples">
        <div class="chart-card-head">
          <h4>${escapeHtml(chart.title || "")}</h4>
        </div>
        <div class="ism-relationship-context-list">
          ${(chart.contexts || []).map((context) => renderIsmRelationshipContext(context)).join("")}
        </div>
        <div class="chart-tooltip ism-shared-tooltip" aria-hidden="true"></div>
        <div class="ism-small-panel-list">
          ${(visibleChart.panels || []).map((panel, index) => renderIsmSmallMultiplePanel(visibleChart, panel, index)).join("")}
        </div>
      </article>
    `;
  }

  function renderIsmDetailChart(chart, chartIndex, _focusedChartId) {
    if (chart.kind === "heat_map") {
      return `
        <article class="relationship-chart-card ism-detail-card">
          <div class="chart-card-head">
            <h4>${escapeHtml(chart.title || "")}</h4>
          </div>
          ${renderIsmHeatMap(chart)}
        </article>
      `;
    }
    if (chart.kind === "small_multiples") {
      return renderIsmSmallMultiples(chart);
    }
    return `
      <article class="ism-relationship-chart-card">
        ${chart.contexts ? `
          <div class="ism-relationship-context-list">
            ${(chart.contexts || []).map((context) => renderIsmRelationshipContext(context)).join("")}
          </div>
        ` : renderIsmRelationshipContext(chart.context)}
        ${renderRatesDetailChart(chart, chartIndex)}
      </article>
    `;
  }

  function attachIsmSharedTooltip(body, chart) {
    const container = body.querySelector(".ism-small-multiples");
    if (!container) return;
    const tooltip = container.querySelector(".ism-shared-tooltip");
    if (!tooltip) return;
    const series = chart.series || [];
    const panels = chart.panels || [];
    const svgs = container.querySelectorAll(".ism-small-panel .relationship-chart-svg");

    function showTooltip(index) {
      const point = series[index];
      if (!point) return;
      const date = fmtMonthYear(point.date);
      const rows = panels.map((panel) => {
        const value = point[panel.key];
        const formattedValue = fmtIsmSmallMultipleValue(value, panel.unit);
        const text = panel.key === "gdp_growth" && point.gdp_period
          ? `${formattedValue} (${point.gdp_period})`
          : formattedValue;
        return `
          <div class="chart-tooltip-row">
            <span>${escapeHtml(panel.title || panel.key)}</span>
            <strong>${escapeHtml(text)}</strong>
          </div>
        `;
      }).join("");
      tooltip.innerHTML = `<div><strong>${escapeHtml(date)}</strong></div>${rows}`;
      tooltip.classList.add("visible");
    }

    function hideTooltip() {
      tooltip.classList.remove("visible");
    }

    function positionTooltip(e, containerRect) {
      const tooltipRect = tooltip.getBoundingClientRect();
      const left = e.clientX - containerRect.left - tooltipRect.width / 2;
      const top = e.clientY - containerRect.top - tooltipRect.height - 10;
      tooltip.style.left = `${Math.max(0, Math.min(containerRect.width - tooltipRect.width, left))}px`;
      tooltip.style.top = `${Math.max(0, top)}px`;
    }

    svgs.forEach((svg) => {
      const wrap = svg.parentElement;
      svg.addEventListener("mousemove", (e) => {
        const wrapRect = wrap.getBoundingClientRect();
        const containerRect = container.getBoundingClientRect();
        const mouseX = e.clientX - wrapRect.left;
        const index = Math.round((mouseX / wrapRect.width) * (series.length - 1));
        const clamped = Math.max(0, Math.min(series.length - 1, index));
        showTooltip(clamped);
        positionTooltip(e, containerRect);
      });
      svg.addEventListener("mouseleave", hideTooltip);
    });

    const scrollParent = body.closest(".detail-scroll");
    if (scrollParent) {
      scrollParent.addEventListener("scroll", hideTooltip);
    }
  }

  function renderIsmDetailInPanel(body, payload) {
    const charts = (payload.charts || []).map((chart) => (
      filterChartForRange(chart, state.selectedGrowthCycleChartRange)
    ));
    const lineCharts = charts.filter((chart) => (
      chart.kind !== "heat_map" && chart.kind !== "small_multiples"
    ));
    const renderedCharts = charts.map((chart, index) => (
      renderIsmDetailChart(chart, index, null)
    ));
    const latest = payload.latest || {};
    const latestMetadata = payload.latest_metadata || {};
    const latestGroups = payload.detail_groups || [];
    body.innerHTML = `
      ${renderGrowthCycleRangeControl()}
      <div class="relationship-chart-grid ism-detail-grid">
        ${renderedCharts.join("")}
      </div>
      ${latestGroups.length ? `<div class="ism-detail-latest">
        <h4>${bilingualLabel("Latest Values")}</h4>
        ${latestGroups.map((group) => {
          if (group.industry_breadth || group.label === "Industry Breadth") {
            return renderIsmIndustryBreadthGroup(group);
          }
          return `
          <div class="ism-latest-group">
            <strong class="ism-latest-group-label">${escapeHtml(group.label || "")}</strong>
            ${group.required_inputs ? `
              <div class="gdp-expectations-context">
                <ul>${group.required_inputs.map((input) => `<li>${escapeHtml(input)}</li>`).join("")}</ul>
              </div>
            ` : `
              <div class="ism-latest-group-rows">
                ${group.keys.map((key) => `
                  <div class="ism-metric-row">
                    <span>${escapeHtml((charts[0]?.labels || {})[key] || key)}</span>
                    <strong>${escapeHtml(fmtIsmIndex(latest[key]))}</strong>
                    ${latestMetadata[key] ? renderIsmTrendChip(latestMetadata[key]) : ""}
                  </div>
                `).join("")}
              </div>
            `}
          </div>
        `}).join("")}
      </div>` : ""}
    `;
    bindGrowthCycleRangeControl(body);
    attachRatesChartTooltips(body, lineCharts);
    const multiChart = charts.find((c) => c.kind === "small_multiples");
    if (multiChart) attachIsmSharedTooltip(body, rebaseVisibleSmallMultipleChart(multiChart));
  }

  function renderGrowthCycleDetailInPanel(body) {
    const detailId = state.selectedGrowthCycleDetailId;
    if (!detailId) return;
    body.innerHTML = `<p class="status">Loading growth cycle detail...</p>`;
    loadGrowthCycleDetail(detailId)
      .then((payload) => {
        if (state.selectedGrowthCycleDetailId !== payload.detail_id) return;
        if (payload.detail_id === "ism_manufacturing") {
          renderIsmDetailInPanel(body, payload);
          return;
        }
        const filteredCharts = payload.charts.map((chart) => (
          filterChartForRange(chart, state.selectedGrowthCycleChartRange)
        ));
        body.innerHTML = `
          ${renderGrowthCycleRangeControl()}
          <div class="relationship-chart-grid">
            ${filteredCharts.map((chart, index) => renderRatesDetailChart(chart, index)).join("")}
          </div>
          ${renderMacroAiInterpretation(payload.m2_ai_interpretation)}
        `;
        bindGrowthCycleRangeControl(body);
        attachRatesChartTooltips(body, filteredCharts);
      })
      .catch((error) => {
        if (state.selectedGrowthCycleDetailId !== detailId) return;
        body.innerHTML = `<p class="status">Failed to load growth cycle detail.</p>`;
        console.error(error);
      });
  }

  function rerenderGrowthCycleDetailBodyPreservingScroll() {
    const body = $("detailPanel")?.querySelector(".detail-panel-body");
    if (!body || !state.selectedGrowthCycleDetailId) {
      renderDetailPanel();
      return;
    }
    const payload = state.growthCycleDetailsById[state.selectedGrowthCycleDetailId];
    if (!payload) {
      renderGrowthCycleDetailInPanel(body);
      return;
    }
    const scrollTop = body.scrollTop;
    if (payload.detail_id === "ism_manufacturing") {
      renderIsmDetailInPanel(body, payload);
    } else {
      const filteredCharts = payload.charts.map((chart) => (
        filterChartForRange(chart, state.selectedGrowthCycleChartRange)
      ));
      body.innerHTML = `
        ${renderGrowthCycleRangeControl()}
        <div class="relationship-chart-grid">
          ${filteredCharts.map((chart, index) => renderRatesDetailChart(chart, index)).join("")}
        </div>
        ${renderMacroAiInterpretation(payload.m2_ai_interpretation)}
      `;
      bindGrowthCycleRangeControl(body);
      attachRatesChartTooltips(body, filteredCharts);
    }
    body.scrollTop = scrollTop;
  }

  function fmtIsmIndex(value) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return "n/a";
    return Number(value).toFixed(1);
  }

  function ismBadgeClass(status) {
    if (["expansion", "supportive", "neutral", "available"].includes(status)) return "supportive";
    if (["contraction", "warning", "inflation_pressure", "supply_pressure"].includes(status)) return "warning";
    if (["missing", "pending_inputs"].includes(status)) return "missing";
    return "mixed";
  }

  function ismHeatMapCellClass(value) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return "ism-heat-cell-missing";
    if (numeric >= 62) return "ism-heat-cell-very-strong";
    if (numeric >= 55) return "ism-heat-cell-strong";
    if (numeric >= 50) return "ism-heat-cell-expansion";
    if (numeric >= 45) return "ism-heat-cell-soft";
    if (numeric >= 40) return "ism-heat-cell-weak";
    return "ism-heat-cell-contraction";
  }

  function renderIsmHeatMap(chart) {
    const rows = (chart.series || []).slice().reverse();
    if (!rows.length) return `<p class="status">No ISM history available.</p>`;
    const keys = chart.keys || [];
    const labels = chart.labels || {};
    return `
      <div class="ism-detail-heat-map" style="--ism-heat-metrics: ${keys.length}">
        <div class="ism-heat-header">Date</div>
        ${keys.map((key) => `<div class="ism-heat-header">${escapeHtml(labels[key] || key)}</div>`).join("")}
        ${rows.map((row) => `
          <div class="ism-heat-date">${escapeHtml(fmtDate(row.date))}</div>
          ${keys.map((key) => `
            <div class="ism-heat-cell ${ismHeatMapCellClass(row[key])}">
              ${escapeHtml(fmtIsmIndex(row[key]))}
            </div>
          `).join("")}
        `).join("")}
      </div>
    `;
  }

  function fmtIsmPointChange(value) {
    if (value === null || value === undefined) return "\u2014";
    const sign = value > 0 ? "+" : "";
    return `${sign}${value.toFixed(1)}`;
  }

  function renderIsmTrendChip(trend) {
    if (!trend) return "";
    const tone = trend.tone || "muted";
    const formatted = fmtIsmPointChange(trend.point_change);
    return `
      <span class="ism-trend-chip ism-trend-chip-${escapeHtml(tone)}">
        <strong>${escapeHtml(formatted)}</strong>
        <span>${escapeHtml(trend.direction)} / ${escapeHtml(trend.rate_of_change)} · ${escapeHtml(String(trend.trend_months))}m</span>
      </span>
    `;
  }

  function renderIsmMetricRow(label, value) {
    return `
      <div class="ism-metric-row">
        <span>${bilingualLabel(label)}</span>
        <strong>${escapeHtml(fmtIsmIndex(value))}</strong>
      </div>
    `;
  }

  function fmtIsmBreadthCount(value) {
    if (value === null || value === undefined) return "\u2014";
    return String(value);
  }

  function renderIsmIndustryBreadthSegment(segment) {
    if (!segment || segment.status !== "available") {
      return `
        <strong>\u2014</strong>
        <small>Pending<br><small>${escapeHtml(zhLabel("Pending") || "\u5F85\u5B8C\u6210")}</small></small>
      `;
    }
    return `
      <strong>${escapeHtml(fmtIsmBreadthCount(segment.growth_count))}/${escapeHtml(fmtIsmBreadthCount(segment.total_count))}</strong>
      <small>Growing<br><small>${escapeHtml(zhLabel("Growing") || "\u6269\u5F20\u884C\u4E1A")}</small></small>
    `;
  }

  const MEDALS = ["\uD83E\uDD47", "\uD83E\uDD48", "\uD83E\uDD49"];

  function renderIsmIndustryList(items, type, emptyLabel) {
    const rows = (items || []).map((item, i) => {
      const prefix = type === "growth" ? MEDALS[i] || "" : "\uD83D\uDD3B";
      return `
      <li>
        <span>${prefix} ${escapeHtml(item.industry || "")}</span>
        <small class="ism-industry-zh">${escapeHtml(zhLabel(item.industry) || "")}</small>
      </li>
    `;
    }).join("");
    return rows || `<li><span>${escapeHtml(emptyLabel)}</span></li>`;
  }

  function renderIsmIndustryBreadthGroup(group) {
    const summary = group.industry_breadth;
    if (!summary) {
      const requiredInputs = (group.required_inputs || [])
        .map((input) => `<li>${escapeHtml(input)}</li>`)
        .join("");
      return `
        <section class="ism-detail-group ism-industry-ranking">
          <h4>${bilingualLabel(group.label || "Industry Breadth")}</h4>
          <div class="gdp-expectations-context">
            <strong>${bilingualLabel("Required Inputs")}</strong>
            <ul>${requiredInputs}</ul>
          </div>
        </section>
      `;
    }
    return `
      <section class="ism-detail-group ism-industry-ranking">
        <h4>${escapeHtml(group.label || "Industry Breadth")}</h4>
        <div class="ism-industry-counts">
          <span><strong>${escapeHtml(fmtIsmBreadthCount(summary.growth_count))}</strong> Growing</span>
          <span><strong>${escapeHtml(fmtIsmBreadthCount(summary.contraction_count))}</strong> Contracting</span>
          <span><strong>${escapeHtml(fmtIsmBreadthCount(summary.total_count))}</strong> Total</span>
        </div>
        <div class="ism-industry-columns">
          <div>
            <h5>${bilingualLabel("Growing Industries")}</h5>
            <ul class="ism-industry-list">${renderIsmIndustryList(summary.top_growth, "growth", "No growth industries")}</ul>
          </div>
          <div>
            <h5>${bilingualLabel("Contracting Industries")}</h5>
            <ul class="ism-industry-list">${renderIsmIndustryList(summary.top_contraction, "contraction", "No contracting industries")}</ul>
          </div>
        </div>
      </section>
    `;
  }

  function renderIsmManufacturingCard(card) {
    const segments = card.segments || {};
    const bc = segments.business_cycle || {};
    const gd = segments.growth_drivers || {};
    const inf = segments.inflation_supply || {};
    const ib = segments.industry_breadth || {};
    const selected = state.selectedGrowthCycleDetailId === "ism_manufacturing";
    return `
      <button class="m2-card ism-card ism-card-button ism-card-${escapeHtml(ismBadgeClass(card.status))}${selected ? " selected" : ""}" type="button" data-growth-cycle-detail-id="ism_manufacturing">
        <div class="ism-metric-band">
          <div>
            <span>Business Cycle<br><small>${escapeHtml(zhLabel("Business Cycle") || "商业周期")}</small></span>
            <strong>${escapeHtml(fmtIsmIndex(bc.pmi))}</strong>
            <small>PMI<br><small>${escapeHtml(zhLabel("PMI") || "采购经理指数")}</small> · ${escapeHtml(bc.phase_label || "Missing")}</small>
            ${bc.trend ? renderIsmTrendChip(bc.trend) : ""}
          </div>
          <div>
            <span>Growth Drivers<br><small>${escapeHtml(zhLabel("Growth Drivers") || "增长驱动力")}</small></span>
            <strong>${escapeHtml(String(gd.above_50_count ?? 0))}/${escapeHtml(String(gd.available_count ?? 0))}</strong>
            <small>Above 50<br><small>${escapeHtml(zhLabel("Above 50") || "高于50")}</small></small>
          </div>
          <div>
            <span>Inflation & Supply<br><small>${escapeHtml(zhLabel("Inflation & Supply") || "通胀与供应")}</small></span>
            <strong>${escapeHtml(fmtIsmIndex(inf.prices))}</strong>
            <small>Prices<br><small>${escapeHtml(zhLabel("Prices") || "价格")}</small></small>
          </div>
          <div>
            <span>Industry Breadth<br><small>${escapeHtml(zhLabel("Industry Breadth") || "行业广度")}</small></span>
            ${renderIsmIndustryBreadthSegment(ib)}
          </div>
        </div>
      </button>
    `;
  }

  function renderIsmIndustryBreadthCard(card) {
    const requiredInputs = (card.required_inputs || [])
      .map((input) => `<li>${escapeHtml(input)}</li>`)
      .join("");
    return `
      <article class="m2-card ism-card ism-card-missing">
        <div class="m2-card-head">
          <span>${escapeHtml(card.label || "ISM Industry Breadth")}<br><small>${escapeHtml(zhLabel(card.label) || "ISM行业广度")}</small></span>
          <strong class="inflation-status-badge">${escapeHtml(card.status_label || "Pending Inputs")}</strong>
        </div>
        <div class="gdp-expectations-context">
          <strong>${bilingualLabel("Required Inputs")}</strong>
          <ul>${requiredInputs}</ul>
        </div>
        <p class="m2-card-footnote">${escapeHtml(card.description || "")}</p>
      </article>
    `;
  }

  function renderInflationContextCard(card) {
    return `
      <div class="m2-card m2-card-${escapeHtml(card.status || "missing")}">
        <div class="m2-card-head">
          <span>${escapeHtml(card.label || "Inflation Context")}<br><small>${escapeHtml(zhLabel(card.label) || "通胀环境")}</small></span>
          <strong class="inflation-status-badge">${escapeHtml(card.status_label || "Missing")}</strong>
        </div>
        <div class="m2-metric-band">
          <div>
            <span>${bilingualLabel("Core PCE YoY")}</span>
            <strong>${escapeHtml(fmtDirectionalPct(card.core_pce_yoy))}</strong>
            <small>Core PCE year-over-year<br><span>核心PCE同比</span></small>
          </div>
          <div>
            <span>${bilingualLabel("Gap vs Fed 2% Target")}</span>
            <strong>${escapeHtml(fmtDirectionalPct(card.gap))}</strong>
            <small>Fed Target<span>美联储目标</span></small>
          </div>
          <div>
            <span>${bilingualLabel("Fed Target")}</span>
            <strong>${escapeHtml(fmtRate(card.target * 100))}</strong>
            <small>FOMC longer-run goal<br><span>FOMC长期目标</span></small>
          </div>
        </div>
        <p class="m2-card-footnote">${escapeHtml(card.description || "")}</p>
      </div>
    `;
  }

  function renderGdpExpectationsCard(card) {
    const requiredInputs = (card.required_inputs || [])
      .map((input) => `<li>${escapeHtml(input)}</li>`)
      .join("");
    return `
      <div class="m2-card m2-card-${escapeHtml(card.status || "pending_inputs")} gdp-expectations-card">
        <div class="m2-card-head">
          <span>${escapeHtml(card.label || "GDP Expectations")}<br><small>${escapeHtml(zhLabel(card.label) || "GDP预期")}</small></span>
          <strong class="inflation-status-badge">${bilingualLabel(card.status_label || "Pending Inputs")}</strong>
        </div>
        <div class="m2-metric-band">
          <div>
            <span>${bilingualLabel("Expected Direction")}</span>
            <strong>${bilingualLabel("Not Ready")}</strong>
            <small>Wait for leading indicators<br><span>等待领先指标</span></small>
          </div>
        </div>
        <div class="gdp-expectations-context">
          <strong>${bilingualLabel("Required Inputs")}</strong>
          <ul>${requiredInputs}</ul>
        </div>
        <p class="m2-card-footnote">${escapeHtml(card.description || "")}</p>
        <p class="m2-card-footnote gdp-expectations-support">${escapeHtml(card.supporting_context || "")}</p>
      </div>
    `;
  }

  function renderFedBalanceSheetCard(card) {
    return `
      <div class="m2-card fed-balance-sheet-card">
        <div class="m2-card-head">
          <span>${escapeHtml(card.label || "Fed Balance Sheet")}<br><small>${escapeHtml(zhLabel(card.label) || "美联储资产负债表")}</small></span>
          <strong class="inflation-status-badge">${escapeHtml(card.status_label || "Liquidity Context")}</strong>
        </div>
        <div class="m2-metric-band">
          <div>
            <span>${bilingualLabel("Total Assets")}</span>
            <strong>${escapeHtml(fmtUsdMillions(card.total_assets))}</strong>
            <small>Fed H.4.1 total assets<br><span>美联储H.4.1总资产</span></small>
          </div>
          <div>
            <span>${bilingualLabel("YoY Growth")}</span>
            <strong>${escapeHtml(fmtDirectionalPct(card.total_assets_yoy))}</strong>
            <small>vs same week last year<br><span>较去年同期</span></small>
          </div>
          <div>
            <span>${bilingualLabel("Total Assets 13W Net Change")}</span>
            <strong>${escapeHtml(fmtSignedUsdMillions(card.total_assets_13w_change))}</strong>
            <small>Positive = expansion, negative = runoff<br><span>正值=扩表，负值=缩表</span></small>
          </div>
        </div>
        <div class="m2-level-row">
          <span>${bilingualLabel("Treasury 13W Net Change")}</span>
          <strong>${escapeHtml(fmtSignedUsdMillions(card.treasury_13w_change))}</strong>
        </div>
        <div class="m2-level-row">
          <span>${bilingualLabel("MBS 13W Net Change")}</span>
          <strong>${escapeHtml(fmtSignedUsdMillions(card.mbs_13w_change))}</strong>
        </div>
        <p class="m2-card-footnote">${escapeHtml(card.description || "")}</p>
      </div>
    `;
  }

  function renderGrowthCycleRangeControl() {
    return `
      <div class="chart-range-control chart-range-control-sticky" role="group" aria-label="Chart range">
        ${CHART_RANGE_OPTIONS.map((option) => `
          <button
            type="button"
            class="${option.id === state.selectedGrowthCycleChartRange ? "active" : ""}"
            data-growth-cycle-chart-range="${escapeHtml(option.id)}"
          >${escapeHtml(option.label)}</button>
        `).join("")}
      </div>
    `;
  }

  function bindGrowthCycleRangeControl(body) {
    body.querySelectorAll("[data-growth-cycle-chart-range]").forEach((button) => {
      button.addEventListener("click", () => {
        const range = button.dataset.growthCycleChartRange;
        if (!range || range === state.selectedGrowthCycleChartRange) return;
        state.selectedGrowthCycleChartRange = range;
        rerenderGrowthCycleDetailBodyPreservingScroll();
      });
    });
  }

  function renderFomcCalendarCard(card) {
    const meeting = card.next_meeting || {};
    const hasMeeting = meeting.start_date != null;
    if (!hasMeeting) {
      return `
        <article class="m2-card m2-card-missing fomc-card">
          <div class="m2-card-head">
            <span>${bilingualTitle("Next FOMC Meeting")}<br><small>${escapeHtml(zhLabel("Next FOMC Meeting") || "")}</small></span>
          </div>
          <p class="m2-card-context">${bilingualLabel("No scheduled meeting")}</p>
        </article>
      `;
    }
    const dateRange = meeting.end_date && meeting.end_date !== meeting.start_date
      ? `${meeting.start_date} - ${meeting.end_date}`
      : meeting.start_date;
    return `
      <article class="m2-card m2-card-mixed fomc-card fomc-calendar-card">
        <div class="m2-card-head">
          <div>
            <span>${bilingualTitle("Next FOMC Meeting")}</span>
          </div>
        </div>
        <div class="m2-level-row">
          <span>${bilingualTitle("Next Meeting Date")}<small>${escapeHtml(dateRange || "n/a")}</small></span>
          <strong>${meeting.has_sep ? "SEP" : "Regular"}</strong>
        </div>
      </article>
    `;
  }

  function renderFomcToneCard(card) {
    const tone = card.latest_tone || {};
    const hasTone = tone.marker_tone != null;
    const cardLabel = card.label || "FOMC Policy Read";
    if (!hasTone) {
      return `
        <article class="m2-card m2-card-missing fomc-card">
          <div class="m2-card-head">
            <span>${bilingualTitle(cardLabel)}</span>
          </div>
          <p class="m2-card-context">${bilingualLabel("Tone unavailable")}</p>
        </article>
      `;
    }
    const toneLabel = formatToneValue(tone.marker_tone);
    const toneBadge = toneBadgeClass(tone.marker_tone);
    const dateStr = tone.end_date && tone.end_date !== tone.start_date
      ? `${tone.start_date} \u2013 ${tone.end_date}`
      : tone.start_date;
    const minutesAvailable = tone.minutes_status === "available";
    const minutesRows = minutesAvailable
      ? `
          <div class="m2-level-row"><span>${bilingualLabel("Minutes Confirmation")}</span><strong>${bilingualLabel(formatMinutesConfirmation(tone.minutes_confirmation))}</strong></div>
          <div class="m2-level-row"><span>${bilingualLabel("Risk Focus")}</span><strong>${bilingualLabel(formatRiskFocus(tone.risk_focus))}</strong></div>
          <div class="m2-level-row"><span>${bilingualLabel("Policy Conviction")}</span><strong>${bilingualLabel(formatPolicyConviction(tone.policy_conviction))}</strong></div>`
      : `
          <div class="m2-level-row"><span>${bilingualLabel("Minutes Confirmation")}</span><strong>${bilingualLabel("Pending")}</strong></div>`;
    return `
      <article class="m2-card m2-card-context fomc-card fomc-tone-card">
        <div class="m2-card-head">
          <div>
            <span>${bilingualTitle(cardLabel)}</span>
            <small class="fomc-tone-date">${escapeHtml(dateStr || "")}</small>
          </div>
          <strong class="fomc-tone-badge ${escapeHtml(toneBadge)}">${bilingualLabel(toneLabel)}</strong>
        </div>
        <div class="m2-detail-rows">
          <div class="m2-level-row"><span>${bilingualLabel("Action")}</span><strong>${bilingualLabel(formatPolicyAction(tone.policy_action))}</strong></div>
          <div class="m2-level-row"><span>${bilingualLabel("Guidance")}</span><strong>${bilingualLabel(formatToneValue(tone.guidance_bias))}</strong></div>
          <div class="m2-level-row"><span>${bilingualLabel("Language")}</span><strong>${bilingualLabel(formatToneValue(tone.language_tone))}</strong></div>
          <div class="m2-level-row"><span>${bilingualLabel("Bias")}</span><strong>${bilingualLabel(formatOverallBias(tone.overall_bias))}</strong></div>
          <div class="m2-level-row"><span>${bilingualLabel("Change")}</span><strong>${bilingualLabel(formatToneChange(tone.tone_change))}</strong></div>
          ${minutesRows}
        </div>
      </article>
    `;
  }

  function renderCard(card) {
    if (card.id === "ism_manufacturing") return renderIsmManufacturingCard(card);
    if (card.id === "m2_money_supply") return renderM2MoneySupplyCard(card);
    if (card.id === "inflation_context") return renderInflationContextCard(card);
    if (card.id === "gdp_expectations") return renderGdpExpectationsCard(card);
    if (card.id === "fed_balance_sheet") return renderFedBalanceSheetCard(card);
    return "";
  }

  function renderFomcCard(card) {
    if (card.id === "fomc_calendar") return renderFomcCalendarCard(card);
    if (card.id === "fomc_tone") return renderFomcToneCard(card);
    return "";
  }

  function renderM2MoneySupplyCard(card) {
    return `
      <button class="m2-card m2-card-button m2-card-${escapeHtml(card.status || "missing")}${state.selectedGrowthCycleDetailId === card.id ? " selected" : ""}" type="button" data-growth-cycle-detail-id="${escapeHtml(card.id)}">
        <div class="m2-metric-band">
          <div>
            <span>${bilingualLabel("YoY Growth")}</span>
            <strong>${escapeHtml(fmtDirectionalPct(card.state?.m2_yoy_pct_change))}</strong>
            <small>YoY growth vs same month last year · ${escapeHtml(fmtPercentRank(card.state?.m2_yoy_percent_rank))} percentile of history<span>同比增速：较去年同月 · 历史第${escapeHtml(fmtPercentRank(card.state?.m2_yoy_percent_rank))}百分位</span></small>
          </div>
          <div>
            <span>${bilingualLabel("3M Change")}</span>
            <strong>${escapeHtml(fmtDirectionalPct(card.change?.m2_3m_momentum))}</strong>
            <small>latest level vs 3 months ago<span>最新水平较3个月前</span></small>
          </div>
          <div>
            <span>${bilingualLabel("MoM Shock")}</span>
            <strong>${escapeHtml(fmtDirectionalPercentRank(card.shock?.m2_mom_percent_rank, card.shock?.m2_mom_pct_change))} percentile</strong>
            <small>latest MoM growth ${escapeHtml(fmtSignedPctDecimal(card.shock?.m2_mom_pct_change))}<span>最新月环比增长 ${escapeHtml(fmtSignedPctDecimal(card.shock?.m2_mom_pct_change))}</span></small>
          </div>
        </div>
        <div class="m2-level-row">
          <span>${bilingualLabel("M2 Level")}</span>
          <strong>$${escapeHtml(fmtNumber(card.state?.m2_money_stock))}B</strong>
        </div>
      </button>
    `;
  }

  function bilingualTitle(title) {
    const zh = zhLabel(title);
    return zh ? `${escapeHtml(title)}<br><small>${escapeHtml(zh)}</small>` : escapeHtml(title);
  }

  function titleCaseToken(value) {
    return String(value || "missing")
      .split("_")
      .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
      .join(" ");
  }

  function formatPolicyAction(value) {
    const map = {
      hold: "Hold",
      cut: "Cut",
      hike: "Hike",
    };
    return map[value] || titleCaseToken(value);
  }

  function formatToneValue(value) {
    const map = {
      hawkish: "Hawkish",
      dovish: "Dovish",
      neutral: "Neutral",
      mixed: "Mixed",
    };
    return map[value] || titleCaseToken(value);
  }

  function formatOverallBias(value) {
    const map = {
      mild_hawkish: "Mild Hawkish",
      mild_dovish: "Mild Dovish",
      hawkish: "Hawkish",
      dovish: "Dovish",
      neutral: "Neutral",
      mixed: "Mixed",
    };
    return map[value] || titleCaseToken(value);
  }

  function formatToneChange(value) {
    const map = {
      more_hawkish: "More Hawkish vs previous",
      more_dovish: "More Dovish vs previous",
      unchanged: "Unchanged",
      less_hawkish: "Less Hawkish vs previous",
      less_dovish: "Less Dovish vs previous",
    };
    return map[value] || titleCaseToken(value);
  }

  function formatMinutesConfirmation(value) {
    return formatToneValue(value || "pending");
  }

  function formatRiskFocus(value) {
    return formatToneValue(value || "unknown");
  }

  function formatPolicyConviction(value) {
    return formatToneValue(value || "unknown");
  }

  function toneBadgeClass(tone) {
    const t = String(tone || "unknown").toLowerCase();
    if (["dovish", "mild_dovish"].includes(t)) return "tone-dovish";
    if (["hawkish", "mild_hawkish"].includes(t)) return "tone-hawkish";
    if (t === "neutral") return "tone-neutral";
    return "tone-unknown";
  }

  function trendGlyph(value) {
    return { rising: "↑", falling: "↓", stable: "→" }[value] || "";
  }

  function accelerationGlyph(value) {
    return { accelerating_up: "↑↑", accelerating_down: "↓↓" }[value] || "";
  }

  function accelerationLabel(value) {
    return value === "none" ? "No Acceleration" : titleCaseToken(value);
  }

  function formatPercentile(value) {
    return value === null || value === undefined ? "n/a" : `${value}%`;
  }

  function renderRatesTimeSeriesChart(chart) {
    const valueFormatter = chart.unit === "raw" ? fmtNumber : fmtRate;
    return renderRelationshipLineChart(
      bilingualTitle(chart.title),
      chart.series || [],
      chart.keys || ["value"],
      chart.labels || { value: "Value" },
      {
        wide: true,
        rawTitle: true,
        valueFormatter,
        yDomain: chart.y_domain,
        events: chart.events || [],
        policyTrack: chart.title === "M2 YoY Growth vs Inflation Constraint",
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
        bilingualTitle(chart.title),
        series.map((point) => ({ date: point.label, ...point })),
        keys,
        labels,
        {
          wide: false,
          rawTitle: true,
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
        secondary: chart.labels?.vix || "Comparison",
      },
      { wide: true, rawTitle: true },
    );
  }

  function renderRatesDetailChart(chart, chartIndex) {
    if (chart.kind === "curve_comparison") {
      return renderRatesCurveComparisonChart(chart, chartIndex);
    }
    if (chart.kind === "multi_series") {
      return renderRatesMultiSeriesChart(chart);
    }
    if (chart.kind === "credit_diagnostics") {
      return renderCreditDiagnosticsChart(chart);
    }
    if (chart.kind === "credit_regime") {
      return renderCreditRegimeChart(chart);
    }
    return renderRatesTimeSeriesChart(chart);
  }

  function renderCreditDiagnosticMetric(title, metric = {}) {
    return `
      <div class="credit-diagnostic-metric">
        <h4>${bilingualLabel(title)}</h4>
        <strong>${escapeHtml(fmtRate(metric.value))}</strong>
        <dl>
          <div><dt>${bilingualLabel("Level Zone")}</dt><dd>${bilingualLabel(titleCaseToken(metric.zone))}</dd></div>
          <div><dt>${bilingualLabel("Full-History Percentile")}</dt><dd>${escapeHtml(formatPercentile(metric.percentile))}</dd></div>
          <div><dt>${bilingualLabel("1M Trend")}</dt><dd>${trendGlyph(metric.trend_1m)} ${bilingualLabel(titleCaseToken(metric.trend_1m))}</dd></div>
          <div><dt>${bilingualLabel("3M Trend")}</dt><dd>${trendGlyph(metric.trend_3m)} ${bilingualLabel(titleCaseToken(metric.trend_3m))}</dd></div>
          <div><dt>${bilingualLabel("Acceleration")}</dt><dd>${accelerationGlyph(metric.acceleration)} ${bilingualLabel(accelerationLabel(metric.acceleration))}</dd></div>
        </dl>
      </div>
    `;
  }

  function renderCreditAiInterpretation(ai) {
    if (!ai) return "";
    return `
      <div class="credit-ai-interpretation">
        <strong>CaiCai<small>财财解读</small></strong>
        <p>${escapeHtml(ai.text_en)}<small>${escapeHtml(ai.text_zh)}</small></p>
        <span>${escapeHtml(ai.as_of || "")} · ${escapeHtml(ai.prompt_version || "")} · ${escapeHtml(ai.model || "")}</span>
      </div>
    `;
  }

  function renderMacroAiInterpretation(ai) {
    if (!ai) return "";
    return `
      <div class="macro-ai-interpretation">
        <strong>CaiCai<small>财财解读</small></strong>
        <p>${escapeHtml(ai.text_en)}<small>${escapeHtml(ai.text_zh)}</small></p>
        <span>${escapeHtml(ai.as_of || "")} · ${escapeHtml(ai.prompt_version || "")} · ${escapeHtml(ai.model || "")}</span>
      </div>
    `;
  }

  function renderCreditCoverageNote(coverage) {
    if (!coverage) return "";
    const hasGap = coverage.has_gap && coverage.gap_start && coverage.gap_end;
    const gapText = hasGap
      ? `Data Gap: ${coverage.gap_start} - ${coverage.gap_end}`
      : "No detected data gap";
    const gapZh = hasGap
      ? `数据缺口：${coverage.gap_start} - ${coverage.gap_end}`
      : "未检测到数据缺口";
    const sourceNote = coverage.source_note || "P05 workbook history is merged with latest FRED ICE/BofA observations. Missing dates are shown as a data gap and are not interpolated.";
    return `
      <div class="credit-data-gap-note ${hasGap ? "has-gap" : ""}">
        <strong>${escapeHtml(gapText)}<small>${escapeHtml(gapZh)}</small></strong>
        <p>${escapeHtml(sourceNote)}<small>P05工作簿历史数据与最新FRED ICE/BofA观测值合并；缺失区间显示为数据缺口，不进行插值。</small></p>
      </div>
    `;
  }

  function renderCreditDiagnosticsChart(chart) {
    const metrics = chart.metrics || {};
    const status = chart.status || "missing";
    const meta = creditStatusMeta(status);
    const message = creditDiagnosticInterpretation(status);
    const rows = [
      ["bbb_credit_spread", "Overall Credit Risk"],
      ["ccc_credit_spread", "CCC Credit Spread"],
      ["ccc_bbb_quality_spread", "Quality Dispersion"],
    ];
    return `
      <div class="relationship-chart relationship-chart-wide credit-diagnostics-chart">
        <div class="credit-diagnostics-grid">
          ${rows.map(([key, title]) => renderCreditDiagnosticMetric(title, metrics[key])).join("")}
        </div>
        <div class="credit-interpretation-strip credit-interpretation-${escapeHtml(status.replaceAll("_", "-"))}">
          <strong>${escapeHtml(meta.label)}<small>${escapeHtml(meta.zh)}</small></strong>
          <p>${escapeHtml(message.text)}<small>${escapeHtml(message.zh)}</small></p>
        </div>
        ${renderCreditAiInterpretation(state.usRatesLiquidity?.credit_ai_interpretation)}
        ${renderCreditCoverageNote(state.usRatesLiquidity?.credit_coverage)}
      </div>
    `;
  }

  function renderCreditRegimeChart(chart) {
    const series = (chart.series || []).slice(-CREDIT_REGIME_VISIBLE_POINTS);
    const current = chart.current;
    const thresholds = chart.thresholds || {};
    const xThreshold = thresholds[chart.x_key] || 2.0;
    const yThreshold = thresholds[chart.y_key] || 4.0;

    const allX = series.map((p) => p[chart.x_key]);
    const allY = series.map((p) => p[chart.y_key]);
    const xMin = Math.min(0, ...allX);
    const xMax = Math.max(xThreshold * 1.5, ...allX) * 1.1;
    const yMin = Math.min(0, ...allY);
    const yMax = Math.max(yThreshold * 1.5, ...allY) * 1.1;

    const width = 480;
    const height = 360;
    const margin = { top: 30, right: 30, bottom: 50, left: 60 };
    const plotW = width - margin.left - margin.right;
    const plotH = height - margin.top - margin.bottom;

    function xScale(v) {
      return margin.left + ((v - xMin) / (xMax - xMin)) * plotW;
    }
    function yScale(v) {
      return margin.top + plotH - ((v - yMin) / (yMax - yMin)) * plotH;
    }

    const thresholdX = xScale(xThreshold);
    const thresholdY = yScale(yThreshold);

    const regimeLabels = {
      low_risk_low_dispersion: { label: "Benign Credit", detail: "Low Risk / Low Dispersion", x: margin.left + plotW * 0.25, y: margin.top + plotH * 0.75 },
      low_risk_high_dispersion: { label: "Weak Credit Warning", detail: "Low Risk / High Dispersion", x: margin.left + plotW * 0.25, y: margin.top + plotH * 0.25 },
      high_risk_high_dispersion: { label: "Risk Off", detail: "High Risk / High Dispersion", x: margin.left + plotW * 0.75, y: margin.top + plotH * 0.25 },
      high_risk_low_dispersion: { label: "Broad Stress", detail: "High Risk / Low Dispersion", x: margin.left + plotW * 0.75, y: margin.top + plotH * 0.75 },
    };

    const dots = series.map((p) => {
      const cx = xScale(p[chart.x_key]);
      const cy = yScale(p[chart.y_key]);
      const isCurrent = current && p.date === current.date;
      const r = isCurrent ? 6 : 3;
      const opacity = isCurrent ? 1 : 0.3;
      return `<circle cx="${cx}" cy="${cy}" r="${r}" fill="#3B3530" opacity="${opacity}" data-date="${escapeHtml(p.date)}" data-x="${p[chart.x_key]}" data-y="${p[chart.y_key]}" data-regime="${escapeHtml(p.regime || "")}"/>`;
    }).join("");

    const currentMarker = current ? `
      <circle cx="${xScale(current[chart.x_key])}" cy="${yScale(current[chart.y_key])}" r="8" fill="none" stroke="#E07B3F" stroke-width="2.5"/>
      <circle cx="${xScale(current[chart.x_key])}" cy="${yScale(current[chart.y_key])}" r="3" fill="#E07B3F"/>
    ` : "";

    const quadrantLabels = Object.values(regimeLabels).map((r) => {
      const labelZh = zhLabel(r.label);
      const detailZh = zhLabel(r.detail);
      return `
        <text x="${r.x}" y="${r.y - 11}" text-anchor="middle" fill="#8B7E74" font-size="12" font-weight="700">${escapeHtml(r.label)}</text>
        ${labelZh ? `<text x="${r.x}" y="${r.y + 4}" text-anchor="middle" fill="#8B7E74" font-size="11" font-weight="600">${escapeHtml(labelZh)}</text>` : ""}
        <text x="${r.x}" y="${r.y + 19}" text-anchor="middle" fill="#B0A597" font-size="10">${escapeHtml(detailZh || r.detail)}</text>
      `;
    }).join("");

    const xTicks = niceTicks(xMin, xMax, 5);
    const yTicks = niceTicks(yMin, yMax, 5);

    const xTickMarks = xTicks.map((v) => {
      const x = xScale(v);
      return `
        <line x1="${x}" y1="${margin.top + plotH}" x2="${x}" y2="${margin.top + plotH + 5}" stroke="#C8BFB6"/>
        <text x="${x}" y="${margin.top + plotH + 20}" text-anchor="middle" fill="#8B7E74" font-size="10">${fmtNumber(v)}</text>
      `;
    }).join("");

    const yTickMarks = yTicks.map((v) => {
      const y = yScale(v);
      return `
        <line x1="${margin.left - 5}" y1="${y}" x2="${margin.left}" y2="${y}" stroke="#C8BFB6"/>
        <text x="${margin.left - 10}" y="${y + 3}" text-anchor="end" fill="#8B7E74" font-size="10">${fmtNumber(v)}</text>
      `;
    }).join("");

    return `
      <div class="relationship-chart relationship-chart-wide relationship-chart-wrap credit-regime-chart" data-chart-kind="credit_regime">
        <div class="relationship-chart-head">
          <h3>${bilingualTitle(chart.title)}</h3>
          ${current ? `<span>${escapeHtml(current.date)} | ${escapeHtml(creditRegimeMeta(current.regime).label)}</span>` : ""}
        </div>
        <svg class="relationship-chart-svg" viewBox="0 0 ${width} ${height}" width="100%" preserveAspectRatio="xMidYMid meet">
          <rect x="${margin.left}" y="${margin.top}" width="${plotW}" height="${plotH}" fill="#FDFAF7" stroke="#E8E0D6"/>
          <line x1="${thresholdX}" y1="${margin.top}" x2="${thresholdX}" y2="${margin.top + plotH}" stroke="#E0BCBC" stroke-width="1" stroke-dasharray="4,3"/>
          <line x1="${margin.left}" y1="${thresholdY}" x2="${margin.left + plotW}" y2="${thresholdY}" stroke="#E0BCBC" stroke-width="1" stroke-dasharray="4,3"/>
          ${xTickMarks}
          ${yTickMarks}
          ${dots}
          ${currentMarker}
          ${quadrantLabels}
          <text x="${margin.left + plotW / 2}" y="${height - 5}" text-anchor="middle" fill="#8B7E74" font-size="11">${escapeHtml(lineLabel({ [chart.x_key]: chart.x_label }, chart.x_key))}</text>
          <text x="15" y="${margin.top + plotH / 2}" text-anchor="middle" fill="#8B7E74" font-size="11" transform="rotate(-90, 15, ${margin.top + plotH / 2})">${escapeHtml(lineLabel({ [chart.y_key]: chart.y_label }, chart.y_key))}</text>
        </svg>
        <div class="chart-tooltip" aria-hidden="true"></div>
      </div>
    `;
  }

  function attachCreditRegimeChartTooltip(svg, tooltip, chart) {
    const series = (chart.series || []).slice(-CREDIT_REGIME_VISIBLE_POINTS);
    if (!svg || !tooltip || !series.length) return;
    const wrap = svg.parentElement;
    const thresholds = chart.thresholds || {};
    const xThreshold = thresholds[chart.x_key] || 2.0;
    const yThreshold = thresholds[chart.y_key] || 4.0;
    const allX = series.map((p) => p[chart.x_key]);
    const allY = series.map((p) => p[chart.y_key]);
    const xMin = Math.min(0, ...allX);
    const xMax = Math.max(xThreshold * 1.5, ...allX) * 1.1;
    const yMin = Math.min(0, ...allY);
    const yMax = Math.max(yThreshold * 1.5, ...allY) * 1.1;
    const width = 480;
    const height = 360;
    const margin = { top: 30, right: 30, bottom: 50, left: 60 };
    const plotW = width - margin.left - margin.right;
    const plotH = height - margin.top - margin.bottom;
    let lastIndex = -1;
    let tooltipRect = null;

    function xScale(v) {
      return margin.left + ((v - xMin) / (xMax - xMin)) * plotW;
    }

    function yScale(v) {
      return margin.top + plotH - ((v - yMin) / (yMax - yMin)) * plotH;
    }

    function show(index, clientX, clientY) {
      const point = series[index];
      if (index !== lastIndex) {
        const meta = creditRegimeMeta(point.regime);
        tooltip.innerHTML = `
          <div><strong>${escapeHtml(fmtMonthYear(point.date))}</strong></div>
          <div class="chart-tooltip-row"><span>${bilingualLabel("Overall Credit Risk")}</span><strong>${escapeHtml(fmtRate(point[chart.x_key]))}</strong></div>
          <div class="chart-tooltip-row"><span>${bilingualLabel("Quality Dispersion")}</span><strong>${escapeHtml(fmtRate(point[chart.y_key]))}</strong></div>
          <div class="chart-tooltip-row"><span>${bilingualLabel("Credit Conditions")}</span><strong>${escapeHtml(meta.label)}</strong></div>
          <div class="credit-tooltip-zh">${escapeHtml(meta.zh)} · ${escapeHtml(meta.note)}</div>
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
      const scaleX = width / rect.width;
      const scaleY = height / rect.height;
      const mouseX = (event.clientX - rect.left) * scaleX;
      const mouseY = (event.clientY - rect.top) * scaleY;
      let nearestIndex = 0;
      let nearestDistance = Infinity;
      series.forEach((point, index) => {
        const dx = xScale(point[chart.x_key]) - mouseX;
        const dy = yScale(point[chart.y_key]) - mouseY;
        const distance = dx * dx + dy * dy;
        if (distance < nearestDistance) {
          nearestDistance = distance;
          nearestIndex = index;
        }
      });
      show(nearestIndex, event.clientX, event.clientY);
    });

    svg.addEventListener("mouseleave", hide);
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
      if (!chart) return;
      if (chart.kind === "credit_regime") {
        attachCreditRegimeChartTooltip(
          wrap.querySelector(".relationship-chart-svg"),
          wrap.querySelector(".chart-tooltip"),
          chart,
        );
        return;
      }
      const valueFormatter = chart.unit === "raw" ? fmtNumber : fmtRate;
      attachRelationshipChartTooltip(
        wrap.querySelector(".relationship-chart-svg"),
        wrap.querySelector(".chart-tooltip"),
        chart.kind === "curve_comparison"
          ? (chart.series || []).map((point) => ({ date: point.label, ...point }))
          : chart.series || [],
        chart.keys || ["value"],
        chart.labels || { value: "Value" },
        { valueFormatter, tooltipExtra: chart.tooltip_extra, events: chart.events || [] }
      );
    });
  }

  function renderRatesDetailPayload(detail, payload, context) {
    const heading = context === "yield_curve" ? `
      <div class="rates-chart-subtitle">
        <p class="eyebrow">${bilingualLabel("Yield Curve Analysis")}</p>
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

  function chartSegments(series, key, scale, options = {}) {
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
      if (options.lineShape === "step_after" && current.length) {
        const previous = current[current.length - 1];
        const previousY = previous.split(",")[1];
        current.push(`${x.toFixed(2)},${previousY}`);
      }
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
          <div>${bilingualLabel("Close")}: ${escapeHtml(fmtNumber(point.close))}</div>
          <div>${bilingualLabel("Drawdown")}: ${escapeHtml(fmtNumber(point.drawdown_pct))}%</div>
          <div>${bilingualLabel("Bear/Bull Level")}: ${escapeHtml(fmtNumber(point.bear_market_level))}</div>
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
        <span><i class="legend-bull"></i>${bilingualLabel("Bull segment")}</span>
        <span><i class="legend-bear"></i>${bilingualLabel("Bear segment")}</span>
        <span><i class="legend-level"></i>${bilingualLabel("Bear/Bull level")}</span>
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
        renderDetailPanel();
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
      MARGIN_TOP,
      PLOT_BOTTOM,
      attachRelationshipChartTooltip,
      filterChartForRange,
      fmtMonthYear,
      niceTicks,
      policyTrackEvents,
      minutesPolicyToneClass,
      relationshipXAxisTicks,
      relationshipYAxisTicks,
      renderRelationshipLineChart,
      renderRelationshipPolicyTrack,
      renderRelationshipXAxisTicks,
      renderRelationshipYAxisAndGrid,
      state,
      renderDetailPanel,
      renderIsmTrendChip,
      fmtIsmPointChange,
      toggleDetailPanelExpanded,
      xAt,
      xAxisTicks,
      renderXAxisTicks,
      yAt,
      yAxisTicks,
    };
  }

  loadGrowthCycle();

  loadDashboard().catch((error) => {
    $("dashboardStatus").textContent = "Failed to load market phase data.";
    console.error(error);
  });
})();

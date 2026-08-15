import { state } from "../state.js";
import { $, escapeHtml, fmtStatus, fmtNumber, bilingualLabel, visibleMarketPhaseMarkets, statusClass, selectedMarket } from "../utils.js";
import { renderMarketChart, attachChartTooltip } from "../charts.js";
import { refreshMarket, loadMarketDetail } from "../api.js";
import { renderDetailPanel } from "../detail-panel.js";
import { renderUsRatesLiquidity } from "./us-rates-liquidity.js";

export function renderOverview() {
    const grid = $("marketGrid");
    const markets = visibleMarketPhaseMarkets(state.markets);
    const currentMarket = markets.find((market) => market.benchmark_id === state.selectedBenchmarkId)
      || null;
    grid.innerHTML = markets
      .map((market) => {
        const selected = market.benchmark_id === currentMarket?.benchmark_id ? " selected" : "";
        const targetId = market.benchmark_id === "us_sp500" ? "evidence-market-phase" : "";
        return `
          <button class="market-card market-card-${statusClass(market)}${selected}${targetId ? " evidence-target" : ""}" type="button" data-benchmark-id="${escapeHtml(market.benchmark_id)}"${targetId ? ` id="${escapeHtml(targetId)}"` : ""}>
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
        state.selectedRatesDetailId = null;
        renderOverview();
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


export function renderDetailInPanel(body) {
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


export function renderMarketPhaseMethod() {
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


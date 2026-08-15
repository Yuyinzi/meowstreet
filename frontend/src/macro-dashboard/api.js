import { state } from "./state.js";
import { $, visibleMarketPhaseMarkets } from "./utils.js";
import { renderOverview } from "./sections/benchmark-grid.js";
import { renderUsRatesLiquidity } from "./sections/us-rates-liquidity.js";
import { renderGrowthCycle } from "./sections/growth-cycle.js";
import { renderSurveySynthesis } from "./sections/survey-synthesis.js";
import { renderConsumerSentiment } from "./sections/consumer-sentiment.js";
import { renderEconomicConfirmation } from "./sections/economic-confirmation.js";
import { renderMarketSetup, announceStatus } from "./sections/market-setup.js";
import { renderDetailPanel } from "./detail-panel.js";

export function ratesDetailCacheKey(detailId) {
    if (detailId === "yield_curve_shape") {
      return `yield_curve_shape|${state.selectedNominalCurrentDate || ""}|${state.selectedNominalComparisonDate || ""}|${state.selectedRealCurrentDate || ""}|${state.selectedRealComparisonDate || ""}`;
    }
    return detailId;
  }


export async function loadUsRatesLiquidity() {
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


export async function loadUsRatesLiquidityDetail(detailId) {
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


export async function loadGrowthCycle() {
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
    renderSurveySynthesis();
  }


export async function loadGrowthCycleDetail(detailId) {
    const response = await fetch(`/api/macro-dashboard/growth-cycle/${encodeURIComponent(detailId)}`);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const payload = await response.json();
    state.growthCycleDetailsById[detailId] = payload;
    return payload;
  }


export async function loadMarketSetup() {
    state.marketSetupLoading = true;
    state.marketSetupError = null;
    renderMarketSetup();
    announceStatus("Loading market setup");
    try {
      const response = await fetch("/api/macro-dashboard/market-setup");
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      state.marketSetup = await response.json();
    } catch (error) {
      state.marketSetup = null;
      state.marketSetupError = error.message;
    } finally {
      state.marketSetupLoading = false;
      renderMarketSetup();
    }
  }


export async function loadConsumerSentiment() {
    try {
      const response = await fetch("/api/macro-dashboard/consumer-sentiment");
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      state.consumerSentiment = await response.json();
      state.consumerSentimentError = null;
    } catch (error) {
      state.consumerSentiment = null;
      state.consumerSentimentError = error.message;
    }
    renderConsumerSentiment();
  }


export async function loadConsumerSentimentDetail() {
    const response = await fetch("/api/macro-dashboard/consumer-sentiment/detail");
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return await response.json();
  }


export async function loadEconomicConfirmation() {
    try {
      const response = await fetch("/api/macro-dashboard/economic-confirmation");
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      state.economicConfirmation = await response.json();
      state.economicConfirmationError = null;
    } catch (error) {
      state.economicConfirmation = null;
      state.economicConfirmationError = error.message;
    }
    renderEconomicConfirmation();
  }


export async function loadEconomicConfirmationDetail() {
    const response = await fetch("/api/macro-dashboard/economic-confirmation/detail");
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return await response.json();
  }


export async function loadDashboard() {
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
  }


export async function loadMarketDetail(benchmarkId) {
    if (state.marketDetailsById[benchmarkId]) {
      return state.marketDetailsById[benchmarkId];
    }
    const response = await fetch(`/api/macro-dashboard/market-phase/${encodeURIComponent(benchmarkId)}`);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const payload = await response.json();
    state.marketDetailsById[benchmarkId] = payload;
    return payload;
  }




export async function refreshMarket(benchmarkId, button) {
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


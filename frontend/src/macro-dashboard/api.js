import { state } from "./state.js";
import { visibleMarketPhaseMarkets } from "./utils.js";

export function ratesDetailCacheKey(detailId) {
    if (detailId === "yield_curve_shape") {
      return `yield_curve_shape|${state.selectedNominalCurrentDate || ""}|${state.selectedNominalComparisonDate || ""}|${state.selectedRealCurrentDate || ""}|${state.selectedRealComparisonDate || ""}`;
    }
    return detailId;
  }


export async function fetchUsRatesLiquidity() {
    try {
      const response = await fetch("/api/macro-dashboard/us-rates-liquidity");
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      state.usRatesLiquidity = await response.json();
      state.usRatesLiquidityError = null;
    } catch (error) {
      state.usRatesLiquidity = null;
      state.usRatesLiquidityError = error.message;
    }
    return state.usRatesLiquidity;
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


export async function fetchGrowthCycle() {
    try {
      const response = await fetch("/api/macro-dashboard/growth-cycle");
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      state.growthCycle = await response.json();
      state.growthCycleError = null;
    } catch (error) {
      state.growthCycle = null;
      state.growthCycleError = error.message;
    }
    return state.growthCycle;
  }


export async function loadGrowthCycleDetail(detailId) {
    const response = await fetch(`/api/macro-dashboard/growth-cycle/${encodeURIComponent(detailId)}`);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const payload = await response.json();
    state.growthCycleDetailsById[detailId] = payload;
    return payload;
  }


export async function fetchMarketSetup() {
    try {
      const response = await fetch("/api/macro-dashboard/market-setup");
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      state.marketSetup = await response.json();
      state.marketSetupError = null;
    } catch (error) {
      state.marketSetup = null;
      state.marketSetupError = error.message;
    }
    return state.marketSetup;
  }


export async function fetchConsumerSentiment() {
    try {
      const response = await fetch("/api/macro-dashboard/consumer-sentiment");
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      state.consumerSentiment = await response.json();
      state.consumerSentimentError = null;
    } catch (error) {
      state.consumerSentiment = null;
      state.consumerSentimentError = error.message;
    }
    return state.consumerSentiment;
  }


export async function loadConsumerSentimentDetail() {
    const response = await fetch("/api/macro-dashboard/consumer-sentiment/detail");
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return await response.json();
  }


export async function fetchEconomicConfirmation() {
    try {
      const response = await fetch("/api/macro-dashboard/economic-confirmation");
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      state.economicConfirmation = await response.json();
      state.economicConfirmationError = null;
    } catch (error) {
      state.economicConfirmation = null;
      state.economicConfirmationError = error.message;
    }
    return state.economicConfirmation;
  }


export async function loadEconomicConfirmationDetail() {
    const response = await fetch("/api/macro-dashboard/economic-confirmation/detail");
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return await response.json();
  }


export async function fetchMarketPhase() {
    const response = await fetch("/api/macro-dashboard/market-phase");
    if (response.status === 500) {
      return null;
    }
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const payload = await response.json();
    state.markets = visibleMarketPhaseMarkets(payload.markets || []);
    state.selectedBenchmarkId = null;
    return payload;
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


export async function refreshMarketData(benchmarkId) {
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
    return result;
  }

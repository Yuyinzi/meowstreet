import { state, closeDetailPanel, syncDetailPanelWidthClass } from "./state.js";
import { $, escapeHtml, CREDIT_DETAIL_MAP, selectedMarket } from "./utils.js";
import { renderOverview, renderDetailInPanel } from "./sections/benchmark-grid.js";
import { renderUsRatesLiquidity, renderRatesDetailInPanel } from "./sections/us-rates-liquidity.js";
import { renderConsumerDetailInPanel } from "./sections/consumer-sentiment.js";
import { renderEconomicConfirmationDetailInPanel } from "./sections/economic-confirmation.js";
import { renderGrowthCycleDetailInPanel } from "./sections/growth-cycle.js";

export const DETAIL_PANEL_EXPAND_LABEL = "Expand detail panel";

export const DETAIL_PANEL_COLLAPSE_LABEL = "Collapse detail panel";


export function toggleDetailPanelExpanded() {
    state.isDetailPanelExpanded = !state.isDetailPanelExpanded;
    syncDetailPanelWidthClass();
    renderDetailPanel();
  }


export function renderDetailPanel() {
    const shell = $("macroDashboardApp");
    const panel = $("detailPanel");
    if (!panel) return;

    const anySelected = state.selectedBenchmarkId || state.selectedRatesDetailId || state.selectedGrowthCycleDetailId || state.selectedConsumerDetailId || state.selectedEconomicConfirmationDetailId;
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
    } else if (state.selectedRatesDetailId) {
      const rates = state.usRatesLiquidity;
      const card = (rates?.headline || []).find((c) => c.id === state.selectedRatesDetailId || state.selectedRatesDetailId === `yield_curve_shape` || CREDIT_DETAIL_MAP[c.id] === state.selectedRatesDetailId);
      title = card ? card.label : "US Rates Detail";
      if (state.selectedRatesDetailId === "yield_curve_shape") {
        title = "Yield Curve Analysis";
      }
    } else if (state.selectedConsumerDetailId) {
      title = "Consumer Sentiment";
    } else if (state.selectedEconomicConfirmationDetailId) {
      title = "Economic Confirmation";
    } else if (state.selectedGrowthCycleDetailId) {
      if (state.selectedGrowthCycleDetailId === "ism_manufacturing") {
        title = "ISM Manufacturing";
      } else if (state.selectedGrowthCycleDetailId === "ism_services") {
        title = "ISM Services";
      } else if (state.selectedGrowthCycleDetailId === "housing_permits") {
        title = "Building Permits";
      } else if (state.selectedGrowthCycleDetailId === "nfib_sbo") {
        title = "NFIB Small Business";
      } else if (state.selectedGrowthCycleDetailId === "cyclical_commodities") {
        title = "Cyclical Commodities & USD";
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
    } else if (state.selectedConsumerDetailId) {
      renderConsumerDetailInPanel(body);
    } else if (state.selectedEconomicConfirmationDetailId) {
      renderEconomicConfirmationDetailInPanel(body);
    } else if (state.selectedGrowthCycleDetailId) {
      renderGrowthCycleDetailInPanel(body);
    }
  }


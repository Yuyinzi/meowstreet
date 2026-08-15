import { $ } from "./utils.js";

export const state = {
    markets: [],
    selectedBenchmarkId: null,
    marketDetailsById: {},
    usRatesLiquidity: null,
    usRatesLiquidityError: null,
    selectedRatesDetailId: null,
    usRatesDetailsById: {},
    growthCycle: null,
    growthCycleError: null,
    consumerSentiment: null,
    consumerSentimentError: null,
    selectedConsumerDetailId: null,
    economicConfirmation: null,
    economicConfirmationError: null,
    selectedEconomicConfirmationDetailId: null,
    marketSetup: null,
    marketSetupError: null,
    selectedGrowthCycleSectionId: null,
    selectedGrowthCycleDetailId: null,
    selectedGrowthCycleChartRange: "1y",
    growthCycleDetailsById: {},
    marketSetupLoading: false,
    selectedIsmIndustry: null,
    selectedNominalCurrentDate: null,
    selectedNominalComparisonDate: null,
    selectedRealCurrentDate: null,
    selectedRealComparisonDate: null,
    isDetailPanelExpanded: false,
  };


export function syncDetailPanelWidthClass() {
    const shell = $("macroDashboardApp");
    if (!shell) return;
    shell.classList.toggle("panel-expanded", Boolean(state.isDetailPanelExpanded));
  }


export function closeDetailPanel() {
    state.selectedBenchmarkId = null;
    state.selectedRatesDetailId = null;
    state.selectedGrowthCycleDetailId = null;
    state.selectedConsumerDetailId = null;
    state.selectedEconomicConfirmationDetailId = null;
    state.selectedIsmIndustry = null;
    state.selectedNominalCurrentDate = null;
    state.selectedNominalComparisonDate = null;
    state.selectedRealCurrentDate = null;
    state.selectedRealComparisonDate = null;
    $("macroDashboardApp").classList.remove("panel-open");
    syncDetailPanelWidthClass();
    $("detailPanel").innerHTML = "";
  }


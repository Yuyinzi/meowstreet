import { state } from "./state.js";
import {
  $,
  fmtIsmPointChange,
  fmtMonthYear,
  fmtCorrelationPercent,
  formatPressureValue,
  formatBiasValue,
  formatBiasComponentValue,
  componentLabel,
  componentStatusBadge,
  formatComponentDirection,
  formatComponentLabel,
} from "./utils.js";
import {
  X_AXIS_TICK_COUNT,
  Y_AXIS_TICK_COUNT,
  MARGIN_TOP,
  PLOT_BOTTOM,
  attachRelationshipChartTooltip,
  filterChartForRange,
  niceTicks,
  policyTrackEvents,
  minutesPolicyToneClass,
  relationshipXAxisTicks,
  relationshipYAxisTicks,
  renderRelationshipLineChart,
  renderRelationshipPolicyTrack,
  renderRelationshipXAxisTicks,
  renderRelationshipYAxisAndGrid,
  xAt,
  xAxisTicks,
  renderXAxisTicks,
  yAt,
  yAxisTicks,
} from "./charts.js";
import { renderDetailPanel, toggleDetailPanelExpanded } from "./detail-panel.js";
import { loadEconomicConfirmationDetail } from "./api.js";
import { loadDashboard } from "./sections/benchmark-grid.js";
import { loadGrowthCycle } from "./sections/growth-cycle.js";
import { loadConsumerSentiment } from "./sections/consumer-sentiment.js";
import { loadEconomicConfirmation } from "./sections/economic-confirmation.js";
import { loadMarketSetup } from "./sections/market-setup.js";
import {
  renderIsmTrendChip,
  renderIsmDetailInPanel,
  renderServicesDetailInPanel,
  servicesStateLabel,
  renderServicesLegacyLatestTable,
  renderServicesLatestValues,
  ismScoreLabelClass,
  ismScoreLabelDisplay,
  ismSignalBadgeClass,
  ismSignalRowClass,
  ismSignalLabel,
  ismOverallTrendLabel,
  renderIsmSignalBadge,
  renderIsmRankText,
  renderIsmIndustryAnalysisSection,
  renderIsmIndustryDetailView,
  renderIsmCoreSignalRow,
  renderIsmScoreComponentDetail,
  renderIsmEvidenceDetail,
  renderIsmMacroContext,
  renderServicesCommodityGroups,
  renderServicesNarrativeFacts,
  renderServicesFullEvidence,
  renderServicesIndustryOptions,
  renderServicesIndustryAnalysisSection,
  renderServicesIndustryDetailView,
  renderServicesSignalTrend,
  renderSignalTrendCell,
  selectServicesIndustry,
  bindServicesIndustrySelector,
  renderIsmIndustryTrend,
  renderIsmScoreTrendSvg,
  renderIsmIndustryList,
  updateIsmIndustryDetail,
  bindIsmIndustrySelector,
  renderIsmPolicyPressure,
  renderFomcToneCard,
  renderHousingPermitsCard,
  renderGrowthCycleSections,
  selectGrowthCycleSection,
  renderGrowthCycleTabs,
  bindGrowthCycleTabs,
  renderCard,
} from "./sections/growth-cycle.js";
import {
  buildMarketSetupPresentation,
  stateSentimentClass,
  renderStateCell,
  renderDecisionHero,
  renderDetailedReasoning,
  renderEvidenceLayers,
  renderDecisionPath,
  evidenceTargetId,
  renderEvidenceLink,
  renderMarketSetupLoading,
  renderMarketSetupError,
  renderMarketSetup,
  bindEvidenceLinks,
} from "./sections/market-setup.js";
import { renderSurveySynthesisCard, surveySynthesisHeadline, renderSurveySynthesis } from "./sections/survey-synthesis.js";
import { bindConsumerSentimentDetailTrigger } from "./sections/consumer-sentiment.js";
import { renderEconomicConfirmation } from "./sections/economic-confirmation.js";

import "./styles/main.css";

async function init() {
  loadGrowthCycle();
  loadConsumerSentiment();
  loadEconomicConfirmation();
  loadMarketSetup();

  try {
    await loadDashboard();
  } catch (error) {
    $("dashboardStatus").textContent = "Failed to load market phase data.";
    console.error(error);
  }
}

if (typeof window !== "undefined") {
  window.__chartHelpers = { renderRelationshipLineChart, attachRelationshipChartTooltip };
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
    fmtCorrelationPercent,
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
    renderIsmDetailInPanel,
    renderServicesDetailInPanel,
    servicesStateLabel,
    renderServicesLegacyLatestTable,
    renderServicesLatestValues,
    fmtIsmPointChange,
    toggleDetailPanelExpanded,
    xAt,
    xAxisTicks,
    renderXAxisTicks,
    yAt,
    yAxisTicks,
    ismScoreLabelClass,
    ismScoreLabelDisplay,
    ismSignalBadgeClass,
    ismSignalRowClass,
    ismSignalLabel,
    ismOverallTrendLabel,
    renderIsmSignalBadge,
    renderIsmRankText,
    renderIsmIndustryAnalysisSection,
    renderIsmIndustryDetailView,
    renderIsmCoreSignalRow,
    renderIsmScoreComponentDetail,
    renderIsmEvidenceDetail,
    renderIsmMacroContext,
    renderServicesCommodityGroups,
    renderServicesNarrativeFacts,
    renderServicesFullEvidence,
    renderServicesIndustryOptions,
    renderServicesIndustryAnalysisSection,
    renderServicesIndustryDetailView,
    renderServicesSignalTrend,
    renderSignalTrendCell,
    selectServicesIndustry,
    bindServicesIndustrySelector,
    renderIsmIndustryTrend,
    renderIsmScoreTrendSvg,
    renderIsmIndustryList,
    updateIsmIndustryDetail,
    bindIsmIndustrySelector,
    formatPressureValue,
    formatBiasValue,
    formatBiasComponentValue,
    componentLabel,
    componentStatusBadge,
    formatComponentDirection,
    formatComponentLabel,
    renderIsmPolicyPressure,
    renderSurveySynthesisCard,
    surveySynthesisHeadline,
    renderSurveySynthesis,
    renderFomcToneCard,
    renderHousingPermitsCard,
    renderGrowthCycleSections,
    selectGrowthCycleSection,
    renderGrowthCycleTabs,
    bindGrowthCycleTabs,
    renderCard,
    buildMarketSetupPresentation,
    stateSentimentClass,
    renderStateCell,
    renderDecisionHero,
    renderDetailedReasoning,
    renderEvidenceLayers,
    renderDecisionPath,
    evidenceTargetId,
    renderEvidenceLink,
    renderMarketSetupLoading,
    renderMarketSetupError,
    renderMarketSetup,
    bindEvidenceLinks,
    bindConsumerSentimentDetailTrigger,
    renderEconomicConfirmation,
    loadEconomicConfirmationDetail,
  };
}

init();

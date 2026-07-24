(function () {
  function renderCard(card, helpers) {
    const escapeHtml = helpers.escapeHtml;
    const formatIndex = helpers.formatIndex;
    const segments = card.segments || {};
    const cycle = segments.services_cycle || {};
    const activity = segments.business_activity || {};
    const orders = segments.new_orders || {};
    const breadth = segments.industry_breadth || {};
    const state = cycle.state || "pending";
    const compConf = cycle.component_confirmation || {};
    const compStatus = compConf.status || null;
    const stateLabels = {
      supports_growth: "Growth",
      supports_contraction: "Contraction",
      neutral: "Neutral",
      pending_inputs: "Pending",
      stale_periods: "Stale",
    };
    const stateLabel = stateLabels[state] || "Unknown";
    const compLabel = compStatus === "aligned" ? "Aligned" : compStatus === "mixed" ? "Mixed" : null;
    const compHtml = compLabel
      ? `<small class="ism-components-label">Components: ${escapeHtml(compLabel)}</small>`
      : "";
    return `
      <button class="m2-card ism-card ism-services-card ism-card-button evidence-target ism-state-${escapeHtml(state)}"
              type="button" id="evidence-ism-services" data-growth-cycle-detail-id="ism_services" aria-label="ISM Services: ${escapeHtml(stateLabel)}">
        <div class="ism-card-header">
          <span class="ism-state-badge ism-state-badge-${escapeHtml(state)}">${escapeHtml(stateLabel)}</span>
        </div>
        <div class="ism-metric-band">
          <div><span>Services Cycle</span><strong>${escapeHtml(formatIndex(cycle.value))}</strong><small>${escapeHtml(cycle.label || "Missing")}${compHtml}</small></div>
          <div><span>Business Activity</span><strong>${escapeHtml(formatIndex(activity.value))}</strong><small>${escapeHtml(activity.trend || "Unavailable")}</small></div>
          <div><span>New Orders</span><strong>${escapeHtml(formatIndex(orders.value))}</strong><small>${escapeHtml(orders.trend || "Unavailable")}</small></div>
          <div><span>Industry Breadth</span><strong>${escapeHtml(String(breadth.growth_count ?? 0))}/${escapeHtml(String(breadth.total_count ?? 0))}</strong><small>Growing</small></div>
        </div>
      </button>
    `;
  }

  function renderDetail(body, payload, helpers) {
    helpers.renderServicesDetail(body, payload);
  }

  function bindDetail() {}

  window.ismServicesUi = { renderCard, renderDetail, bindDetail };
})();

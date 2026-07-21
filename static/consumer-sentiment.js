(function () {
  function renderCard(summary, helpers) {
    const escapeHtml = helpers.escapeHtml;
    const fmt = helpers.formatIndex;
    const evidence = summary.evidence_state || "insufficient_data";
    const dataStatus = summary.data_status || "missing";
    const agg = summary.aggregate || {};
    const exp = summary.expectations || {};
    const cur = summary.current_conditions || {};
    const decline = summary.large_expectations_decline;
    const capacity = summary.capacity_completeness || "missing";

    const evidenceLabels = {
      supportive: "Supportive",
      adverse: "Adverse",
      conflicting: "Conflicting",
      ambiguous: "Ambiguous",
      insufficient_data: "Insufficient Data",
    };
    const evidenceLabel = evidenceLabels[evidence] || "Unknown";

    const zoneLabels = {
      bullish: "Bullish",
      benign: "Benign",
      bearish: "Bearish",
      ambiguous: "Ambiguous",
      peak: "Peak",
      steady_growth: "Steady Growth",
      trough: "Trough",
    };

    return `
      <button class="m2-card ism-card consumer-card consumer-card-button consumer-state-${escapeHtml(evidence)}"
              type="button" data-consumer-detail-id="consumer_sentiment"
              aria-label="Consumer Sentiment: ${escapeHtml(evidenceLabel)}">
        <div class="ism-card-header">
          <span class="ism-card-title">Consumer Sentiment</span>
          <span class="ism-state-badge consumer-state-badge-${escapeHtml(evidence)}">${escapeHtml(evidenceLabel)}</span>
        </div>
        <div class="ism-metric-band">
          <div>
            <span>Aggregate</span>
            <strong>${escapeHtml(fmt(agg.value))}</strong>
            <small>${escapeHtml(zoneLabels[agg.zone] || "Unavailable")}</small>
          </div>
          <div>
            <span>Expectations</span>
            <strong>${escapeHtml(fmt(exp.value))}</strong>
            <small>${escapeHtml(exp.point_change != null ? (exp.point_change > 0 ? "+" : "") + exp.point_change : "N/A")} ${escapeHtml(zoneLabels[exp.zone] || "")}</small>
          </div>
          <div>
            <span>Current Conditions</span>
            <strong>${escapeHtml(fmt(cur.value))}</strong>
            <small>${escapeHtml(cur.date ? cur.date.slice(0, 7) : "Missing")}</small>
          </div>
          <div>
            <span>Status</span>
            <strong>${escapeHtml(dataStatus === "current" ? "Current" : dataStatus === "mixed_periods" ? "Mixed" : "Missing")}</strong>
            <small>${escapeHtml(capacity === "complete" ? "All data" : capacity === "partial" ? "Partial" : "No capacity")}</small>
          </div>
        </div>
        ${decline ? '<div class="consumer-decline-warning">Large expectations decline</div>' : ""}
      </button>
    `;
  }

  function renderDetail(body, payload, helpers) {
    helpers.renderConsumerDetail(body, payload);
  }

  function bindDetail() {}

  window.consumerSentimentUi = { renderCard, renderDetail, bindDetail };
})();

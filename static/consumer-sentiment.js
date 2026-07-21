(function () {
  function fmtMonthYear(dateStr) {
    if (!dateStr) return "";
    try {
      const d = new Date(dateStr + "T00:00:00Z");
      return new Intl.DateTimeFormat("en-US", { year: "numeric", month: "short", timeZone: "UTC" }).format(d);
    } catch {
      return dateStr.slice(0, 7);
    }
  }

  const evidenceLabels = {
    supportive: "Supportive",
    adverse: "Adverse",
    conflicting: "Conflicting",
    ambiguous: "Ambiguous",
    insufficient_data: "Insufficient Data",
  };

  const zoneLabels = {
    bullish: "Bullish",
    benign: "Benign",
    bearish: "Bearish",
    ambiguous: "Ambiguous",
    peak: "Peak",
    steady_growth: "Steady Growth",
    trough: "Trough",
  };

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
    const evidenceLabel = evidenceLabels[evidence] || "Unknown";

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
            <small>${escapeHtml(cur.date ? fmtMonthYear(cur.date) : "Missing")}</small>
          </div>
          <div>
            <span>Data</span>
            <strong>${escapeHtml(dataStatus === "current" ? "Current" : dataStatus === "mixed_periods" ? "Mixed" : "Missing")}</strong>
            <small>${escapeHtml(capacity === "complete" ? "All data" : capacity === "partial" ? "Partial" : "No capacity")}</small>
          </div>
        </div>
        ${decline ? '<div class="consumer-decline-warning">Large expectations decline</div>' : ""}
      </button>
    `;
  }

  function renderDetailInPanel(body, detailPayload) {
    const summary = detailPayload.summary || {};
    const context = detailPayload.context || {};
    const agg = summary.aggregate || {};
    const exp = summary.expectations || {};
    const cur = summary.current_conditions || {};
    const evidence = summary.evidence_state || "insufficient_data";
    const dataStatus = summary.data_status || "missing";
    const evidenceLabel = evidenceLabels[evidence] || "Unknown";
    const reasons = summary.reasons || [];
    const capacity = detailPayload.capacity || {};
    const history = detailPayload.history || {};
    const pointChanges = detailPayload.point_changes || {};
    const fmc = context.fomc_tone || {};

    const tableRow = (label, value) => `<tr><td>${label}</td><td>${value != null ? value : "—"}</td></tr>`;

    let capacityHtml = "";
    for (const [sid, pts] of Object.entries(capacity)) {
      const last = pts.length ? pts[pts.length - 1] : null;
      capacityHtml += `<tr><td>${sid}</td><td>${last ? last.value : "—"}</td><td>${last ? last.date : ""}</td></tr>`;
    }

    const fomcHtml = fmc.statement_marker_tone
      ? `<h4>Fed Policy</h4>
         <table class="ism-latest-table"><tbody>
           ${tableRow("Tone", fmc.statement_marker_tone)}
           ${tableRow("Policy Action", fmc.statement_policy_action)}
           ${tableRow("Guidance", fmc.statement_guidance_bias)}
           ${tableRow("Confidence", fmc.statement_confidence)}
         </tbody></table>`
      : "";

    body.innerHTML = `
      <div class="ism-detail-sections">
        <h3>Consumer Sentiment Detail</h3>
        <div class="consumer-summary-strip">
          <span class="ism-state-badge consumer-state-badge-${escapeHtml(evidence)}">${escapeHtml(evidenceLabel)}</span>
          <span>As of: ${escapeHtml(summary.as_of ? fmtMonthYear(summary.as_of) : "N/A")}</span>
          <span>Status: ${escapeHtml(dataStatus)}</span>
        </div>
        <table class="ism-latest-table">
          <thead><tr><th>Metric</th><th>Value</th><th>Change</th><th>Zone</th><th>Date</th></tr></thead>
          <tbody>
            <tr><td>UMCSI Aggregate</td><td>${escapeHtml(agg.value != null ? agg.value : "—")}</td><td>${escapeHtml(agg.point_change != null ? agg.point_change : "—")}</td><td>${escapeHtml(zoneLabels[agg.zone] || "—")}</td><td>${escapeHtml(agg.date ? fmtMonthYear(agg.date) : "—")}</td></tr>
            <tr><td>Expectations</td><td>${escapeHtml(exp.value != null ? exp.value : "—")}</td><td>${escapeHtml(exp.point_change != null ? exp.point_change : "—")}</td><td>${escapeHtml(zoneLabels[exp.zone] || "—")}</td><td>${escapeHtml(exp.date ? fmtMonthYear(exp.date) : "—")}</td></tr>
            <tr><td>Current Conditions</td><td>${escapeHtml(cur.value != null ? cur.value : "—")}</td><td>—</td><td>—</td><td>${escapeHtml(cur.date ? fmtMonthYear(cur.date) : "—")}</td></tr>
          </tbody>
        </table>
        ${reasons.length ? `<h4>Notes</h4><ul>${reasons.map(r => `<li>${escapeHtml(r)}</li>`).join("")}</ul>` : ""}
        <h4>Capacity</h4>
        <table class="ism-latest-table">
          <thead><tr><th>Series</th><th>Latest Value</th><th>Date</th></tr></thead>
          <tbody>${capacityHtml}</tbody>
        </table>
        ${fomcHtml}
        ${context.real_rate != null ? `<h4>Real Rate (10Y - CPI YoY)</h4><p>${escapeHtml(context.real_rate)}%</p>` : ""}
        <h4>Provenance</h4>
        <p>Aggregate: University of Michigan Table 1</p>
        <p>Components: University of Michigan Table 5</p>
        <p>Capacity: FRED (HDTGPDUSQ163N, TDSP, PSAVERT, HHMSDODNS)</p>
      </div>
    `;
  }

  function renderDetail(body, payload, helpers) {
    renderDetailInPanel(body, payload);
  }

  function bindDetail() {}

  window.consumerSentimentUi = { renderCard, renderDetail, bindDetail, renderDetailInPanel };
})();

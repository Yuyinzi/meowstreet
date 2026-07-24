(function () {
  function fmtMonthYear(dateStr) {
    if (!dateStr) return "";
    try {
      const date = new Date(dateStr + "T00:00:00Z");
      return new Intl.DateTimeFormat("en-US", {
        year: "numeric",
        month: "short",
        timeZone: "UTC",
      }).format(date);
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

  function renderLoading() {
    return '<div class="consumer-loading" aria-busy="true">Loading consumer sentiment data\u2026</div>';
  }

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

  function renderDetailInPanel(body, payload) {
    const s = payload.summary || {};
    const escapeHtml = function (value) {
      return String(value ?? "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
    };
    const fmt = function (value) {
      if (value === null || value === undefined) return "n/a";
      return Number(value).toFixed(2);
    };
    const fmtPct = function (value) {
      if (value === null || value === undefined) return "n/a";
      return fmt(value) + "%";
    };
    const badgeClass = function (state) {
      return "consumer-state-badge-" + (state || "insufficient_data");
    };
    const zoneLabels = {
      bullish: "Bullish", benign: "Benign", bearish: "Bearish", ambiguous: "Ambiguous",
      peak: "Peak", steady_growth: "Steady Growth", trough: "Trough",
    };
    const evidenceLabels = {
      supportive: "Supportive", adverse: "Adverse", conflicting: "Conflicting",
      ambiguous: "Ambiguous", insufficient_data: "Insufficient Data",
    };

    const agg = s.aggregate || {};
    const exp = s.expectations || {};
    const cur = s.current_conditions || {};
    const ctx = payload.context || {};
    const fomc = ctx.fomc_tone;
    const history = payload.history || {};
    const cap = payload.capacity || {};

    var html = "";

    html += '<div class="ism-detail-sections">';
    html += '<h3>Consumer Sentiment Detail</h3>';

    html += '<table class="consumer-detail-table">';
    html += "<thead><tr><th>Metric</th><th>Value</th><th>Zone</th><th>Change</th><th>Date</th></tr></thead>";
    html += "<tbody>";
    html += "<tr><td>Aggregate</td><td>" + escapeHtml(fmt(agg.value)) + "</td><td><span class='" + escapeHtml(badgeClass(s.evidence_state)) + "'>" + escapeHtml(zoneLabels[agg.zone] || "N/A") + "</span></td><td>" + escapeHtml(agg.point_change != null ? (agg.point_change > 0 ? "+" : "") + agg.point_change : "N/A") + "</td><td>" + escapeHtml(agg.date || "N/A") + "</td></tr>";
    html += "<tr><td>Expectations</td><td>" + escapeHtml(fmt(exp.value)) + "</td><td><span class='" + escapeHtml(badgeClass(s.evidence_state)) + "'>" + escapeHtml(zoneLabels[exp.zone] || "N/A") + "</span></td><td>" + escapeHtml(exp.point_change != null ? (exp.point_change > 0 ? "+" : "") + exp.point_change : "N/A") + "</td><td>" + escapeHtml(exp.date || "N/A") + "</td></tr>";
    html += "<tr><td>Current Conditions</td><td>" + escapeHtml(fmt(cur.value)) + "</td><td>N/A</td><td>N/A</td><td>" + escapeHtml(cur.date || "N/A") + "</td></tr>";
    html += "<tr><td>Evidence</td><td colspan='4'><span class='" + escapeHtml(badgeClass(s.evidence_state)) + "'>" + escapeHtml(evidenceLabels[s.evidence_state] || "Unknown") + "</span></td></tr>";
    html += "<tr><td>Data Status</td><td colspan='4'>" + escapeHtml(s.data_status || "missing") + "</td></tr>";
    html += "</tbody></table>";

    var capRows = [
      { label: "Household Debt/GDP", key: "household_debt_to_gdp", unit: "%" },
      { label: "Debt Service Ratio", key: "household_debt_service_ratio", unit: "%" },
      { label: "Personal Saving Rate", key: "personal_saving_rate", unit: "%" },
      { label: "Mortgage Liabilities", key: "one_to_four_family_mortgage_liabilities", unit: "M" },
    ];
    html += '<h4>Consumer Capacity Context</h4>';
    html += '<table class="consumer-detail-table">';
    html += "<thead><tr><th>Series</th><th>Latest</th><th>Date</th></tr></thead>";
    html += "<tbody>";
    capRows.forEach(function (row) {
      var pts = cap[row.key] || [];
      var latest = pts.length ? pts[pts.length - 1] : null;
      var val = latest ? (row.unit === "M" ? fmt(latest.value) : fmtPct(latest.value)) : "N/A";
      html += "<tr><td>" + escapeHtml(row.label) + "</td><td>" + escapeHtml(val) + "</td><td>" + escapeHtml(latest ? latest.date : "N/A") + "</td></tr>";
    });
    html += "</tbody></table>";

    if (fomc) {
      html += '<h4>FOMC Policy Context</h4>';
      html += '<table class="consumer-detail-table">';
      html += "<thead><tr><th>Attribute</th><th>Value</th></tr></thead>";
      html += "<tbody>";
      html += "<tr><td>Meeting</td><td>" + escapeHtml(fomc.title || "N/A") + " (" + escapeHtml(fomc.display_month || "N/A") + ")</td></tr>";
      html += "<tr><td>Statement Tone</td><td>" + escapeHtml(fomc.statement_marker_tone || "unknown") + "</td></tr>";
      html += "<tr><td>Policy Action</td><td>" + escapeHtml(fomc.statement_policy_action || "unknown") + "</td></tr>";
      html += "<tr><td>Guidance Bias</td><td>" + escapeHtml(fomc.statement_guidance_bias || "unknown") + "</td></tr>";
      html += "<tr><td>Overall Bias</td><td>" + escapeHtml(fomc.statement_overall_bias || "unknown") + "</td></tr>";
      html += "<tr><td>Tone Change</td><td>" + escapeHtml(fomc.statement_tone_change || "unknown") + "</td></tr>";
      html += "</tbody></table>";
    }

    html += '<h4>Bond Context</h4>';
    html += '<table class="consumer-detail-table">';
    html += "<thead><tr><th>Series</th><th>Latest</th><th>Date</th></tr></thead>";
    html += "<tbody>";
    var treasuryPts = ctx.treasury_10y || [];
    var tipsPts = ctx.tips_10y || [];
    var cpiPts = ctx.cpi_yoy || [];
    var realRatePts = ctx.real_rate || [];
    html += "<tr><td>Treasury 10Y</td><td>" + escapeHtml(treasuryPts.length ? fmtPct(treasuryPts[treasuryPts.length - 1].value) : "N/A") + "</td><td>" + escapeHtml(treasuryPts.length ? treasuryPts[treasuryPts.length - 1].date : "N/A") + "</td></tr>";
    html += "<tr><td>TIPS 10Y</td><td>" + escapeHtml(tipsPts.length ? fmtPct(tipsPts[tipsPts.length - 1].value) : "N/A") + "</td><td>" + escapeHtml(tipsPts.length ? tipsPts[tipsPts.length - 1].date : "N/A") + "</td></tr>";
    html += "<tr><td>CPI YoY</td><td>" + escapeHtml(cpiPts.length ? fmtPct(cpiPts[cpiPts.length - 1].value) : "N/A") + "</td><td>" + escapeHtml(cpiPts.length ? cpiPts[cpiPts.length - 1].date : "N/A") + "</td></tr>";
    html += "<tr><td>Real Rate (10Y - CPI)</td><td>" + escapeHtml(realRatePts.length ? fmtPct(realRatePts[realRatePts.length - 1].value) : "N/A") + "</td><td>" + escapeHtml(realRatePts.length ? realRatePts[realRatePts.length - 1].date : "N/A") + "</td></tr>";
    html += "</tbody></table>";

    html += '<h4>Provenance</h4>';
    html += '<table class="consumer-detail-table">';
    html += "<thead><tr><th>Series</th><th>Source</th></tr></thead>";
    html += "<tbody>";
    html += "<tr><td>Aggregate</td><td>" + escapeHtml(agg.source || "N/A") + "</td></tr>";
    html += "<tr><td>Expectations</td><td>" + escapeHtml(exp.source || "N/A") + "</td></tr>";
    html += "<tr><td>Current Conditions</td><td>" + escapeHtml(cur.source || "N/A") + "</td></tr>";
    capRows.forEach(function (row) {
      var pts = cap[row.key] || [];
      var latest = pts.length ? pts[pts.length - 1] : null;
      var source = latest ? latest.source : "N/A";
      html += "<tr><td>" + escapeHtml(row.label) + "</td><td>" + escapeHtml(source) + "</td></tr>";
    });
    html += "<tr><td>Treasury 10Y</td><td>" + escapeHtml(treasuryPts.length ? treasuryPts[treasuryPts.length - 1].source || "N/A" : "N/A") + "</td></tr>";
    html += "<tr><td>TIPS 10Y</td><td>" + escapeHtml(tipsPts.length ? tipsPts[tipsPts.length - 1].source || "N/A" : "N/A") + "</td></tr>";
    html += "<tr><td>CPI YoY</td><td>" + escapeHtml(cpiPts.length ? cpiPts[cpiPts.length - 1].source || "N/A" : "N/A") + "</td></tr>";
    html += "</tbody></table>";

    html += "</div>";

    var chartHelpers = window.__chartHelpers;
    var chartSeries = [
      { key: "umcsi_aggregate", title: "UMCSI Aggregate" },
      { key: "umcsi_expectations", title: "UMCSI Expectations" },
      { key: "umcsi_current_conditions", title: "UMCSI Current Conditions" },
    ];
    if (chartHelpers) {
      chartSeries.forEach(function (cs) {
        var pts = history[cs.key] || [];
        if (pts.length < 2) return;
        var series = pts.map(function (p) { return {date: p.date, value: p.value}; });
        var values = pts.map(function (p) { return p.value; });
        var lastChange = pts.length > 1 ? (pts[pts.length - 1].value - pts[pts.length - 2].value >= 0 ? "+" : "") + (pts[pts.length - 1].value - pts[pts.length - 2].value).toFixed(1) : "";
        var chartHtml = chartHelpers.renderRelationshipLineChart(
          cs.title, series, ["value"], {value: cs.title}, {hideHead: true}
        );
        html += '<div class="relationship-chart">';
        html += '<div class="relationship-chart-head">';
        html += "<h4>" + escapeHtml(cs.title) + "</h4>";
        html += "<span>Latest: " + escapeHtml(fmt(values[values.length - 1])) + " " + escapeHtml(lastChange) + "</span>";
        html += "</div>";
        html += chartHtml;
        html += "</div>";
      });
    }

    body.innerHTML = html;
  }

  window.consumerSentimentUi = { renderLoading, renderCard, renderDetailInPanel };
})();

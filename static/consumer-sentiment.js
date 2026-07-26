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

  function fmtDate(dateStr) {
    if (!dateStr) return "";
    try {
      const date = new Date(dateStr + "T00:00:00Z");
      return new Intl.DateTimeFormat("en-US", {
        year: "numeric",
        month: "short",
        day: "numeric",
        timeZone: "UTC",
      }).format(date);
    } catch {
      return dateStr;
    }
  }

  function fmtChange(change) {
    if (change === null || change === undefined) return "N/A";
    return (change > 0 ? "+" : "") + change;
  }

  function fmtIndex(value) {
    if (value === null || value === undefined) return "n/a";
    return Number(value).toFixed(1);
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function titleLabel(value) {
    if (!value) return "Unavailable";
    return String(value)
      .split("_")
      .map(function (part) {
        return part.charAt(0).toUpperCase() + part.slice(1);
      })
      .join(" ");
  }

  function pointChangeLabel(metric) {
    var change = metric.point_change;
    if (change === null || change === undefined) return "Change unavailable";
    if (change === 0) return "0.0 pts";
    var arrow = change > 0 ? "\u2191" : "\u2193";
    return arrow + " " + Math.abs(Number(change)).toFixed(1) + " pts";
  }

  function stateClass(kind, value) {
    return "consumer-" + kind + "-" + String(value || "unavailable")
      .replace(/[^a-z_]/g, "");
  }

  function renderStateChip(kind, value) {
    return '<span class="consumer-state-chip ' + stateClass(kind, value) + '">'
      + escapeHtml(titleLabel(value)) + '</span>';
  }

  function confirmationLabel(metric) {
    return metric.confirms_primary === true ? "Confirms Expectations" : "";
  }

  function confirmationDetailLabel(confirmation) {
    var labels = {
      broadly_confirmed:
        "Aggregate and Current Conditions confirm the Expectations zone.",
      aggregate_confirms:
        "Aggregate confirms the Expectations zone; Current Conditions differ.",
      current_conditions_confirms:
        "Current Conditions confirm the Expectations zone; Aggregate differs.",
      divergent:
        "Aggregate and Current Conditions differ from the Expectations zone.",
      unavailable:
        "Confirmation is unavailable because inputs or observation periods differ.",
    };
    return labels[confirmation.state] || labels.unavailable;
  }

  function percentileZoneExplanation(metric, percentileMethod) {
    var lowerBoundary = Number(percentileMethod.lower_boundary);
    var upperBoundary = Number(percentileMethod.upper_boundary);
    if (!Number.isFinite(lowerBoundary) || !Number.isFinite(upperBoundary)) return "";
    var explanation = "Zone rule: at or below the " + lowerBoundary
      + "th percentile is Depressed; at or above the " + upperBoundary
      + "th percentile is Elevated; values between are Typical.";
    if (metric.percentile_rank === null || metric.percentile_rank === undefined) {
      return explanation;
    }
    return explanation + " Current Expectations: "
      + Number(metric.percentile_rank).toFixed(2) + " percentile rank is "
      + titleLabel(metric.percentile_zone) + ".";
  }

  function sentimentMeaning(zone, momentum, includeInterpretation) {
    var level = {
      depressed: "Consumer expectations remain near a historical low",
      elevated: "Consumer expectations remain near a historical high",
      typical: "Consumer expectations are within their typical historical range",
    }[zone];
    var change = {
      improving: "while the latest monthly reading has improved.",
      weakening: "while the latest monthly reading has weakened.",
      unchanged: "and the latest monthly reading is unchanged.",
    }[momentum];
    if (!level || !change) return "";
    var meaning = level + ", " + change;
    if (includeInterpretation && zone === "depressed" && momentum === "improving") {
      meaning += " This indicates early stabilization, not yet a confirmed demand recovery.";
    }
    return meaning;
  }

  function renderLoading() {
    return '<div class="consumer-loading" aria-busy="true">Loading consumer sentiment data\u2026</div>';
  }

  function renderSentimentRow(label, metric) {
    var roleText = metric.role === "primary" ? "Primary"
      : confirmationLabel(metric);
    var changeText = metric.role === "primary" ? pointChangeLabel(metric) : "";
    return '<tr class="consumer-status-row '
      + stateClass("zone", metric.percentile_zone) + " "
      + stateClass("momentum", metric.momentum) + '">'
      + '<td class="consumer-row-label">' + escapeHtml(label) + '</td>'
      + '<td class="consumer-row-value">'
      + escapeHtml(metric.percentile_label || "Unavailable")
      + " \u00b7 " + escapeHtml(titleLabel(metric.percentile_zone))
      + '</td>'
      + '<td class="consumer-row-change">' + escapeHtml(changeText) + '</td>'
      + '<td class="consumer-row-role">' + escapeHtml(roleText) + '</td>'
      + '</tr>';
  }

  function renderAbilityRow(item) {
    return '<tr class="consumer-status-row">'
      + '<td class="consumer-row-label">' + escapeHtml(item.label) + '</td>'
      + '<td class="consumer-row-value">' + escapeHtml(titleLabel(item.state)) + '</td>'
      + '<td class="consumer-row-change"></td>'
      + '<td class="consumer-row-role"></td>'
      + '</tr>';
  }

  function abilityPeriodLabel(capacityAsOf) {
    var dates = Object.keys(capacityAsOf || {})
      .map(function (seriesId) { return capacityAsOf[seriesId]; })
      .filter(function (date) { return Boolean(date); });
    var uniqueDates = Array.from(new Set(dates));
    if (uniqueDates.length === 0) return "Household capacity context";
    if (uniqueDates.length === 1) {
      return "Household context \u00b7 " + fmtMonthYear(uniqueDates[0]);
    }
    return "Household context \u00b7 observation periods vary";
  }

  function renderCard(summary) {
    var dataStatus = summary.data_status || "missing";
    var alignedMonth = summary.aligned_month;
    var primary = summary.primary_signal || {};
    var confirmation = summary.confirmation || {};
    var ability = summary.ability_read || {};
    var abilityPeriod = abilityPeriodLabel(summary.capacity_as_of);
    var willingnessMeaning = sentimentMeaning(
      primary.percentile_zone, primary.momentum, false
    );

    var accessibleName = "Consumer Sentiment: "
      + titleLabel(primary.percentile_zone)
      + ", " + titleLabel(primary.momentum)
      + ", " + titleLabel(confirmation.state);
    if (dataStatus === "mixed_periods") {
      accessibleName += " - Observation periods differ";
    }

    var periodLine = "";
    if (dataStatus === "mixed_periods") {
      periodLine = '<div class="consumer-card-warning">Observation periods differ</div>';
    } else if (alignedMonth) {
      periodLine = '<div class="consumer-card-period">Sentiment as of ' + escapeHtml(fmtMonthYear(alignedMonth)) + '</div>';
    }

    return '\n'
      + '<div class="m2-card ism-card consumer-card consumer-card-button" '
      + 'role="button" tabindex="0" '
      + 'data-consumer-detail-id="consumer_sentiment" '
      + 'aria-label="' + escapeHtml(accessibleName) + '">\n'
      + '  <div class="consumer-card-statuses">\n'
      + renderStateChip("zone", primary.percentile_zone)
      + renderStateChip("momentum", primary.momentum)
      + '  </div>\n'
      + '  <div class="consumer-card-groups">\n'
      + '    <div class="consumer-status-group">\n'
      + '      <div class="consumer-group-heading"><span>Willingness</span><small>Sentiment position and trend</small></div>\n'
      + '      <table class="consumer-status-table"><tbody>\n'
      + renderSentimentRow("Expectations", summary.expectations || {})
      + renderSentimentRow("Aggregate", summary.aggregate || {})
      + renderSentimentRow("Current Conditions", summary.current_conditions || {})
      + '      </tbody></table>\n'
      + (willingnessMeaning
        ? '      <p class="consumer-card-meaning">' + escapeHtml(willingnessMeaning) + '</p>\n'
        : "")
      + '    </div>\n'
      + '    <div class="consumer-status-group">\n'
      + '      <div class="consumer-group-heading"><span>Ability</span><small>' + escapeHtml(abilityPeriod) + '</small></div>\n'
      + '      <table class="consumer-status-table"><tbody>\n'
      + renderAbilityRow(ability.financing || { label: "Financing", state: "unavailable" })
      + renderAbilityRow(ability.leverage || { label: "Leverage", state: "unavailable" })
      + renderAbilityRow(ability.saving || { label: "Saving", state: "unavailable" })
      + '      </tbody></table>\n'
      + '    </div>\n'
      + periodLine
      + '  </div>\n'
      + '</div>';
  }

  function renderDetailSignal(label, metric) {
    var confirmation = metric.confirms_primary === true
      ? '<span class="consumer-signal-primary-badge">Confirms Expectations</span>'
      : "";
    var role = metric.role === "primary"
      ? '<span class="consumer-signal-primary-badge">Primary</span>'
      : confirmation;
    return '<div class="consumer-signal-card '
      + stateClass("zone", metric.percentile_zone) + " "
      + stateClass("momentum", metric.momentum) + '">'
      + '<span class="consumer-signal-label">' + escapeHtml(label) + role + '</span>'
      + '<span class="consumer-signal-value">' + escapeHtml(fmtIndex(metric.value)) + '</span>'
      + '<span class="consumer-signal-zone">'
      + escapeHtml(metric.percentile_label || "Unavailable")
      + " \u00b7 " + escapeHtml(titleLabel(metric.percentile_zone))
      + '</span>'
      + '<span class="consumer-signal-change">'
      + escapeHtml(pointChangeLabel(metric))
      + " \u00b7 " + escapeHtml(titleLabel(metric.momentum))
      + '</span>'
      + '</div>';
  }

  function renderDetailInPanel(body, payload) {
    var s = payload.summary || {};
    var history = payload.history || {};
    var cap = payload.capacity || {};
    var caps = payload.capacity_interpretations || [];

    var agg = s.aggregate || {};
    var exp = s.expectations || {};
    var cur = s.current_conditions || {};

    var primary = s.primary_signal || {};
    var confirmation = s.confirmation || {};
    var capacityRead = s.capacity_evidence || {};
    var zoneExplanation = percentileZoneExplanation(exp, s.percentile_method || {});
    var detailedMeaning = sentimentMeaning(
      primary.percentile_zone, primary.momentum, true
    );

    var html = "";

    html += '<div class="consumer-detail">';
    html += '<h3>Consumer Sentiment Detail</h3>';

    html += '<div class="consumer-section consumer-v2-summary">';
    html += '<h4>Sentiment Read</h4>';
    html += '<div class="consumer-primary-read '
      + stateClass("zone", primary.percentile_zone) + " "
      + stateClass("momentum", primary.momentum) + '">';
    html += '<span class="consumer-brief-label">Primary Signal</span>';
    html += '<strong>' + escapeHtml(primary.headline) + '</strong>';
    html += '<p>Expectations are at a '
      + (exp.percentile_rank !== null && exp.percentile_rank !== undefined
        ? escapeHtml(Number(exp.percentile_rank).toFixed(2)) + ' percentile rank and are '
        : 'percentile rank unavailable and are ')
      + escapeHtml(titleLabel(exp.momentum).toLowerCase()) + '.</p>';
    if (exp.point_change !== null && exp.point_change !== undefined) {
      html += '<p>Month-over-month change: ' + escapeHtml(Number(exp.point_change).toFixed(1)) + ' index points</p>';
    }
    if (zoneExplanation) {
      html += '<p class="consumer-zone-logic">' + escapeHtml(zoneExplanation) + '</p>';
    }
    if (detailedMeaning) {
      html += '<p class="consumer-sentiment-meaning">' + escapeHtml(detailedMeaning) + '</p>';
    }
    html += '</div>';
    html += '<p class="consumer-confirmation-read">' + escapeHtml(confirmationDetailLabel(confirmation)) + '</p>';
    if (s.data_status === "mixed_periods") {
      html += '<div class="consumer-mixed-dates">';
      html += '<p>Component observation months differ:</p>';
      html += '<ul>'
        + '<li>Aggregate: ' + escapeHtml(agg.date || "unavailable") + '</li>'
        + '<li>Expectations: ' + escapeHtml(exp.date || "unavailable") + '</li>'
        + '<li>Current Conditions: ' + escapeHtml(cur.date || "unavailable") + '</li>'
        + '</ul>';
      html += '</div>';
    }
    html += '<p class="consumer-method-note">'
      + 'Percentiles use a 240-month rolling window and mid-rank ties. '
      + 'Zones are relative sentiment levels, not economic forecasts.'
      + '</p>';
    html += '</div>';

    html += '<div class="consumer-section consumer-signal-read">';
    html += '<h4>Signal Read</h4>';
    html += '<div class="consumer-signal-grid">';
    html += renderDetailSignal("Aggregate", agg);
    html += renderDetailSignal("Expectations", exp);
    html += renderDetailSignal("Current Conditions", cur);
    html += '</div>';
    html += '</div>';

    var chartHelpers = window.__chartHelpers;
    var chartData = null;
    if (chartHelpers && history.umcsi_aggregate && history.umcsi_expectations && history.umcsi_current_conditions) {
      var aggSeries = (history.umcsi_aggregate || []).map(function (p) { return { date: p.date, aggregate: p.value }; });
      var expSeries = (history.umcsi_expectations || []).map(function (p) { return { date: p.date, expectations: p.value }; });
      var curSeries = (history.umcsi_current_conditions || []).map(function (p) { return { date: p.date, current_conditions: p.value }; });
      var dateMap = {};
      aggSeries.forEach(function (p) { dateMap[p.date] = dateMap[p.date] || {}; dateMap[p.date].aggregate = p.aggregate; });
      expSeries.forEach(function (p) { dateMap[p.date] = dateMap[p.date] || {}; dateMap[p.date].expectations = p.expectations; });
      curSeries.forEach(function (p) { dateMap[p.date] = dateMap[p.date] || {}; dateMap[p.date].current_conditions = p.current_conditions; });
      var sortedDates = Object.keys(dateMap).sort();
      var combined = sortedDates.map(function (d) {
        return { date: d, aggregate: dateMap[d].aggregate, expectations: dateMap[d].expectations, current_conditions: dateMap[d].current_conditions };
      });
      var chartKeys = ["aggregate", "expectations", "current_conditions"];
      var chartLabels = { aggregate: "Aggregate", expectations: "Expectations", current_conditions: "Current Conditions" };
      if (combined.length >= 2) {
        chartData = { combined: combined, keys: chartKeys, labels: chartLabels };
        html += '<div class="consumer-section consumer-chart-section">';
        html += chartHelpers.renderRelationshipLineChart("UMCSI Components", combined, chartKeys, chartLabels, {});
        html += '</div>';
      }
    }

    html += '<div class="consumer-section consumer-capacity-section">';
    html += '<h4>Consumer Capacity Evidence</h4>';
    var capExplanation = capacityRead.explanation || capacityRead.headline || "";
    if (capExplanation) {
      html += '<div class="consumer-capacity-headline">' + escapeHtml(capExplanation) + '</div>';
    }
    html += '<div class="consumer-capacity-drivers">';
    caps.forEach(function (d) {
      var driverDate = "";
      var quarterNote = payload.household_debt_gdp_quarter_note;
      if (d.series_id === "household_debt_to_gdp" && d.available && d.latest_date) {
        driverDate = "Observed: " + d.latest_date;
      } else if (d.available && d.latest_date) {
        driverDate = fmtMonthYear(d.latest_date);
      }
      html += '<div class="consumer-capacity-driver">';
      html += '<span class="consumer-driver-label">' + escapeHtml(d.label) + '</span>';
      if (d.available) {
        html += '<span class="consumer-driver-interp">' + escapeHtml(d.interpretation) + '</span>';
      } else {
        html += '<span class="consumer-driver-interp consumer-driver-missing">Data unavailable</span>';
      }
      if (d.series_id === "one_to_four_family_mortgage_liabilities" && d.context_interpretation) {
        html += '<span class="consumer-driver-context">' + escapeHtml(d.context_interpretation) + '</span>';
      }
      if (driverDate) {
        html += '<span class="consumer-driver-date">' + escapeHtml(driverDate) + '</span>';
      }
      if (d.series_id === "household_debt_to_gdp" && quarterNote && d.available) {
        html += '<span class="consumer-driver-date">' + escapeHtml(quarterNote) + '</span>';
      }
      html += '</div>';
    });
    html += '</div>';

    html += '<details class="consumer-raw-values">';
    html += '<summary>Raw capacity observations</summary>';
    html += '<table class="consumer-detail-table">';
    html += '<thead><tr><th>Series</th><th>Latest</th><th>Date</th><th>Source</th></tr></thead>';
    html += '<tbody>';
    var capRows = [
      { label: "Household Debt/GDP", key: "household_debt_to_gdp", unit: "%" },
      { label: "Debt Service Ratio", key: "household_debt_service_ratio", unit: "%" },
      { label: "Personal Saving Rate", key: "personal_saving_rate", unit: "%" },
      { label: "Mortgage Liabilities", key: "one_to_four_family_mortgage_liabilities", unit: "M" },
    ];
    capRows.forEach(function (row) {
      var pts = cap[row.key] || [];
      var latest = pts.length ? pts[pts.length - 1] : null;
      var val = latest ? (row.unit === "M" ? Number(latest.value).toFixed(2) : Number(latest.value).toFixed(2) + "%") : "N/A";
      var src = latest ? latest.source : "N/A";
      html += "<tr><td>" + escapeHtml(row.label) + "</td><td>" + escapeHtml(val) + "</td><td>" + escapeHtml(latest ? latest.date : "N/A") + "</td><td>" + escapeHtml(src) + "</td></tr>";
    });
    html += "</tbody></table>";
    html += '</details>';

    html += '</div>';
    html += '</div>';

    body.innerHTML = html;

    if (chartHelpers && chartData && chartHelpers.attachRelationshipChartTooltip) {
      var chartSvg = body.querySelector(".relationship-chart-svg");
      var tooltip = body.querySelector(".chart-tooltip");
      if (chartSvg && tooltip) {
        chartHelpers.attachRelationshipChartTooltip(chartSvg, tooltip, chartData.combined, chartData.keys, chartData.labels);
      }
    }
  }

  window.consumerSentimentUi = { renderLoading, renderCard, renderDetailInPanel };
})();

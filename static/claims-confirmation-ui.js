(function () {
  function titleCaseToken(value) {
    return String(value || "missing")
      .split("_")
      .map(function (part) {
        return part.charAt(0).toUpperCase() + part.slice(1);
      })
      .join(" ");
  }

  function statusMeta(status) {
    return {
      confirming: { badge: "Confirming", tone: "expanding" },
      partial: { badge: "Partial", tone: "mixed" },
      conflicting: { badge: "Conflicting", tone: "contracting" },
      not_confirming: { badge: "Not Confirming", tone: "mixed" },
      unavailable: { badge: "Unavailable", tone: "missing" },
    }[status] || { badge: "Unavailable", tone: "missing" };
  }

  function statusCopy(status) {
    return {
      confirming: {
        en: "Available evidence clearly supports the growth thesis.",
        zh: "现有证据明确支持增长论点。",
      },
      partial: {
        en: "Some evidence supports the growth thesis while other evidence is neutral or unavailable.",
        zh: "部分证据支持增长论点，其他证据为中性或暂不可用。",
      },
      conflicting: {
        en: "Available evidence points in the direction opposite the growth thesis.",
        zh: "现有证据指向与增长论点相反的方向。",
      },
      not_confirming: {
        en: "Evidence is available but has not changed enough in either direction to support or oppose the thesis.",
        zh: "证据可用，但尚不足以在任一方向上支持或反对该论点。",
      },
      unavailable: {
        en: "The module cannot calculate a relation state.",
        zh: "该模块无法计算关联状态。",
      },
    }[status] || {
      en: "Confirmation is unavailable.",
      zh: "确认暂时不可用。",
    };
  }

  function reasonCopy(reason) {
    return {
      data_missing: {
        en: "Confirmation is unavailable because no claims data is available.",
        zh: "由于没有可用的申领数据，确认暂时不可用。",
      },
      release_not_yet_available: {
        en: "Confirmation is unavailable because the latest required claims week has not been officially released.",
        zh: "由于最新所需的申领周尚未正式发布，确认暂时不可用。",
      },
      insufficient_history: {
        en: "Confirmation is unavailable because there is insufficient claims observation history.",
        zh: "由于申领观察历史不足，确认暂时不可用。",
      },
      stale_data: {
        en: "Confirmation is unavailable because the latest claims observation is stale.",
        zh: "由于最新申领数据已过时，确认暂时不可用。",
      },
      calculation_error: {
        en: "Confirmation is unavailable because of a calculation error.",
        zh: "由于计算错误，确认暂时不可用。",
      },
      method_not_approved: {
        en: "Confirmation is unavailable because the method is not approved.",
        zh: "由于该方法尚未获批，确认暂时不可用。",
      },
      macro_growth_thesis_not_directional: {
        en: "Confirmation is unavailable because the macro growth thesis is not directional.",
        zh: "由于宏观增长论点不具方向性，确认暂时不可用。",
      },
    }[reason] || {
      en: "Confirmation is unavailable.",
      zh: "确认暂时不可用。",
    };
  }

  function coverageLabel(value) {
    if (value === "claims_only") return "Claims only";
    return titleCaseToken(value);
  }

  function overallLabel(value) {
    if (value === "limited_coverage") return "Limited coverage";
    return titleCaseToken(value);
  }

  function renderCard(payload, helpers) {
    var h = helpers;
    var claims = payload.claims_confirmation || {};
    var overall = payload.economic_confirmation || {};
    var status = claims.confirmation_status || "unavailable";
    var meta = statusMeta(status);
    var initial = claims.initial_claims || {};
    var continuing = claims.continuing_claims || {};
    var selected = h.isSelectedEconomicConfirmationDetailId
      && h.isSelectedEconomicConfirmationDetailId("economic_confirmation");

    var html = '<button class="m2-card m2-card-button economic-confirmation-card m2-card-'
      + h.escapeHtml(meta.tone) + '"';
    html += selected ? " selected" : "";
    html += ' type="button" data-economic-confirmation-detail-id="economic_confirmation">';
    html += '<div class="m2-card-head">';
    html += '<span>' + h.bilingualTitle("Claims-Based Labor Confirmation") + '</span>';
    html += '<strong class="inflation-status-badge">' + h.escapeHtml(meta.badge) + '</strong>';
    html += '</div>';
    html += '<div class="claims-confirmation-trends">';
    html += '<span>' + h.bilingualLabel("Initial Claims") + ': <strong>'
      + h.escapeHtml(titleCaseToken(initial.classification || "unavailable")) + '</strong></span>';
    html += '<span>' + h.bilingualLabel("Continuing Claims") + ': <strong>'
      + h.escapeHtml(titleCaseToken(continuing.classification || "unavailable")) + '</strong></span>';
    html += '</div>';
    if (claims.explanation) {
      html += '<p class="claims-confirmation-explanation">' + h.escapeHtml(claims.explanation) + '</p>';
    }
    html += '<div class="claims-confirmation-coverage">';
    html += '<span>' + h.bilingualLabel("Coverage") + ': ' + h.escapeHtml(coverageLabel(overall.coverage)) + '</span>';
    html += '<span>' + h.bilingualLabel("Overall Economic Confirmation") + ': '
      + h.escapeHtml(overallLabel(overall.status)) + '</span>';
    html += '</div>';
    html += '</button>';
    return html;
  }

  function renderTrendRecord(record, label, helpers) {
    var h = helpers;
    var classification = (record || {}).classification || "unavailable";
    var html = '<div class="claims-trend-card">';
    html += '<h4>' + h.bilingualLabel(label) + '</h4>';
    html += '<div class="claims-trend-row"><span>' + h.bilingualLabel("Classification")
      + '</span><strong>' + h.escapeHtml(titleCaseToken(classification)) + '</strong></div>';
    if (classification === "unavailable" && record.unavailable_reason) {
      var reason = reasonCopy(record.unavailable_reason);
      html += '<div class="claims-trend-row"><span>' + h.bilingualLabel("Reason")
        + '</span><strong>' + h.escapeHtml(reason.en) + '</strong></div>';
    }
    if (record.observation_period) {
      html += '<div class="claims-trend-row"><span>' + h.bilingualLabel("Observation Period")
        + '</span><strong>' + h.escapeHtml(record.observation_period) + '</strong></div>';
    }
    if (record.latest_4w_mean !== null && record.latest_4w_mean !== undefined) {
      html += '<div class="claims-trend-row"><span>' + h.bilingualLabel("Latest 4W Mean")
        + '</span><strong>' + h.escapeHtml(h.fmtNumber(record.latest_4w_mean)) + '</strong></div>';
    }
    if (record.comparison_4w_mean !== null && record.comparison_4w_mean !== undefined) {
      html += '<div class="claims-trend-row"><span>' + h.bilingualLabel("Comparison 4W Mean")
        + '</span><strong>' + h.escapeHtml(h.fmtNumber(record.comparison_4w_mean)) + '</strong></div>';
    }
    html += '</div>';
    return html;
  }

  function renderVintages(vintages, helpers) {
    var h = helpers;
    var rows = vintages || [];
    if (!rows.length) return "";
    var seriesLabels = {
      initial_claims_sa: "Initial Claims",
      continuing_claims_sa: "Continuing Claims",
    };
    var bySeries = {};
    var sourceUrls = {};
    rows.forEach(function (row) {
      var seriesId = row.series_id || "unknown";
      if (!bySeries[seriesId]) bySeries[seriesId] = [];
      bySeries[seriesId].push(row);
      if (row.source_url) sourceUrls[row.source_url] = true;
    });
    var html = '<details class="claims-vintage-details">';
    html += '<summary>' + h.bilingualLabel("Vintages") + '</summary>';
    Object.keys(bySeries).forEach(function (seriesId) {
      var label = seriesLabels[seriesId] || titleCaseToken(seriesId);
      html += '<h4 class="claims-metric-label">' + h.bilingualLabel(label) + '</h4>';
      html += '<table class="claims-vintage-table"><thead><tr>';
      html += '<th>' + h.escapeHtml("Period") + '</th>';
      html += '<th>' + h.escapeHtml("Value (person/\u4eba)") + '</th>';
      html += '<th>' + h.escapeHtml("Release") + '</th>';
      html += '</tr></thead><tbody>';
      bySeries[seriesId].forEach(function (row) {
        html += '<tr>';
        html += '<td>' + h.escapeHtml(row.reference_period || "\u2014") + '</td>';
        html += '<td>' + h.escapeHtml(h.fmtInteger(row.value)) + '</td>';
        html += '<td>' + h.escapeHtml(row.release_date || "\u2014") + '</td>';
        html += '</tr>';
      });
      html += '</tbody></table>';
    });
    var sources = Object.keys(sourceUrls);
    if (sources.length) {
      html += '<p class="claims-provenance">' + h.bilingualLabel("Source") + ': ';
      html += sources.map(function (url) {
        return '<a href="' + h.escapeHtml(url) + '" target="_blank" rel="noopener noreferrer">'
          + h.escapeHtml(url) + '</a>';
      }).join(' ');
      html += '</p>';
    }
    html += '</details>';
    return html;
  }

  function renderMetric(snapshot, label, helpers) {
    var h = helpers;
    if (!snapshot) return "";
    var html = '<div class="claims-metric-card">';
    html += '<span class="claims-metric-label">' + h.bilingualLabel(label) + '</span>';
    html += '<span class="claims-metric-value">' + h.escapeHtml(h.fmtNumber(snapshot.value)) + '</span>';
    if (snapshot.reference_period) {
      html += '<span class="claims-metric-meta">' + h.bilingualLabel("Reference Period")
        + ': ' + h.escapeHtml(snapshot.reference_period) + '</span>';
    }
    html += '</div>';
    return html;
  }

  function renderLaborContext(labor, helpers) {
    var h = helpers;
    var html = '<section class="claims-detail-section claims-context-section">';
    html += '<h3>' + h.bilingualTitle("Labor Context") + '</h3>';
    if (labor.data_status === "available") {
      var metrics = labor.metrics || {};
      var releaseDates = {};
      var sourceUrls = {};
      Object.keys(metrics).forEach(function (key) {
        var snapshot = metrics[key];
        if (snapshot.release_date) releaseDates[snapshot.release_date] = true;
        if (snapshot.source_url) sourceUrls[snapshot.source_url] = true;
      });
      (labor.payroll_revisions || []).forEach(function (row) {
        if (row.source_url) sourceUrls[row.source_url] = true;
      });
      var releaseDatesList = Object.keys(releaseDates);
      var asOf = releaseDatesList.length === 1 ? releaseDatesList[0]
        : (releaseDatesList.length ? releaseDatesList.sort().pop() : null);
      var sources = Object.keys(sourceUrls);
      if (asOf) {
        html += '<div class="claims-context-header">';
        html += '<span class="claims-context-asof">' + h.bilingualLabel("As Of")
          + ': ' + h.escapeHtml(asOf) + '</span>';
        html += '</div>';
      }
      html += '<div class="claims-metric-grid">';
      html += renderMetric(metrics.nonfarm_payrolls_change, "Nonfarm Payrolls Change", h);
      html += renderMetric(metrics.payrolls_3m_average_change, "Payrolls 3M Avg Change", h);
      html += renderMetric(metrics.unemployment_rate, "Unemployment Rate", h);
      html += renderMetric(metrics.average_weekly_hours, "Average Weekly Hours", h);
      html += renderMetric(metrics.average_hourly_earnings, "Average Hourly Earnings", h);
      html += '</div>';
      if (labor.payroll_revisions && labor.payroll_revisions.length) {
        html += '<h4 class="claims-metric-label">' + h.bilingualLabel("Payroll Revisions") + '</h4>';
        html += '<table class="claims-vintage-table"><thead><tr>';
        html += '<th>' + h.escapeHtml("Period") + '</th>';
        html += '<th>' + h.escapeHtml("At Release (person/\u4eba)") + '</th>';
        html += '<th>' + h.escapeHtml("Latest (person/\u4eba)") + '</th>';
        html += '<th>' + h.escapeHtml("Release") + '</th>';
        html += '</tr></thead><tbody>';
        labor.payroll_revisions.forEach(function (row) {
          html += '<tr>';
          html += '<td>' + h.escapeHtml(row.reference_period || "\u2014") + '</td>';
          html += '<td>' + h.escapeHtml(h.fmtInteger(row.value_at_release * 1000)) + '</td>';
          html += '<td>' + h.escapeHtml(h.fmtInteger(row.latest_revised_value * 1000)) + '</td>';
          html += '<td>' + h.escapeHtml(row.release_date || "\u2014") + '</td>';
          html += '</tr>';
        });
        html += '</tbody></table>';
      }
      if (sources.length) {
        html += '<p class="claims-provenance">' + h.bilingualLabel("Source") + ': ';
        html += sources.map(function (url) {
          return '<a href="' + h.escapeHtml(url) + '" target="_blank" rel="noopener noreferrer">'
            + h.escapeHtml(url) + '</a>';
        }).join(' ');
        html += '</p>';
      }
    } else {
      html += '<p class="claims-pending-note">'
        + h.bilingualLabel("Labor context data is not yet available.") + '</p>';
    }
    html += '</section>';
    return html;
  }

  function renderRealActivity(realActivity, helpers) {
    var h = helpers;
    var html = '<section class="claims-detail-section">';
    html += '<h3>' + h.bilingualTitle("Real Activity") + '</h3>';
    if (realActivity.data_status === "available") {
      var metrics = realActivity.metrics || {};
      html += '<div class="claims-metric-grid">';
      html += renderMetric(metrics.manufacturing_production, "Manufacturing Production", h);
      html += renderMetric(metrics.total_industrial_production, "Total Industrial Production", h);
      html += renderMetric(metrics.capacity_utilization, "Capacity Utilization", h);
      html += '</div>';
      html += '<p class="claims-pending-note">'
        + h.bilingualLabel("Data collected. Method pending approval \u2014 shown as context only.") + '</p>';
    } else {
      html += '<p class="claims-pending-note">'
        + h.bilingualLabel("No Real Activity data has been collected yet. Method pending approval.") + '</p>';
    }
    html += '<div class="claims-trend-row"><span>' + h.bilingualLabel("Method Status")
      + '</span><strong>' + h.escapeHtml(titleCaseToken(realActivity.method_status || "pending_approval"))
      + '</strong></div>';
    html += '<span class="claims-reason-code">' + h.escapeHtml(realActivity.unavailable_reason || "method_not_approved")
      + '</span>';
    html += '</section>';
    return html;
  }

  function renderEventRisk(eventRisk, helpers) {
    var h = helpers;
    var nextEvent = eventRisk.next_event || {};
    var html = '<section class="claims-detail-section">';
    html += '<h3>' + h.bilingualTitle("Upcoming Event") + '</h3>';
    html += '<div class="claims-trend-row"><span>' + h.bilingualLabel("Direction")
      + '</span><strong>' + h.escapeHtml(titleCaseToken(eventRisk.direction || "unknown"))
      + '</strong></div>';
    if (eventRisk.high_volatility_warning) {
      html += '<p class="claims-conflict-note">' + h.escapeHtml(eventRisk.high_volatility_warning) + '</p>';
    }
    if (nextEvent.scheduled_at) {
      html += '<div class="claims-trend-row"><span>' + h.bilingualLabel("Next Event")
        + '</span><strong>' + h.escapeHtml(nextEvent.scheduled_at) + '</strong></div>';
      if (nextEvent.source_url) {
        html += '<div class="claims-trend-row"><span>' + h.bilingualLabel("Source")
          + '</span><strong><a href="' + h.escapeHtml(nextEvent.source_url)
          + '" target="_blank" rel="noopener noreferrer">' + h.bilingualLabel("Open")
          + ' &rarr;</a></strong></div>';
      }
    } else {
      html += '<p class="claims-pending-note">'
        + h.bilingualLabel("No upcoming Employment Situation event is scheduled.") + '</p>';
    }
    html += '</section>';
    return html;
  }

  function renderOverall(overall, helpers) {
    var h = helpers;
    var html = '<section class="claims-detail-section">';
    html += '<h3>' + h.bilingualTitle("Overall Economic Confirmation") + '</h3>';
    html += '<div class="claims-coverage-line"><span>' + h.bilingualLabel("Coverage")
      + '</span><strong>' + h.escapeHtml(coverageLabel(overall.coverage)) + '</strong></div>';
    html += '<div class="claims-coverage-line"><span>' + h.bilingualLabel("Status")
      + '</span><strong>' + h.escapeHtml(overallLabel(overall.status)) + '</strong></div>';
    html += '<div class="claims-coverage-line"><span>' + h.bilingualLabel("Based On")
      + '</span><strong>' + h.escapeHtml((overall.based_on || []).join(", ")) + '</strong></div>';
    (overall.excluded_modules || []).forEach(function (mod) {
      html += '<div class="claims-coverage-line"><span>'
        + h.escapeHtml(titleCaseToken(mod.module)) + '</span><strong>'
        + h.escapeHtml(titleCaseToken(mod.reason)) + '</strong></div>';
    });
    html += '</section>';
    return html;
  }

  function renderDetail(body, payload, helpers) {
    var h = helpers;
    var claims = payload.claims_confirmation || {};
    var labor = payload.labor_context || {};
    var realActivity = payload.real_activity || {};
    var eventRisk = payload.event_risk || {};
    var overall = payload.economic_confirmation || {};
    var status = claims.confirmation_status || "unavailable";
    var meta = statusMeta(status);
    var statusRead = statusCopy(status);
    var reason = claims.unavailable_reason;

    var html = '<section class="claims-confirmation-detail">';
    html += '<h2>' + h.bilingualTitle("Economic Confirmation") + '</h2>';

    html += '<section class="claims-detail-section claims-detail-section-' + h.escapeHtml(meta.tone) + '">';
    html += '<h3>' + h.bilingualLabel("Claims-Based Labor Confirmation") + '</h3>';
    html += '<div class="claims-status-line"><strong class="inflation-status-badge">'
      + h.escapeHtml(meta.badge) + '</strong></div>';
    html += '<p class="claims-pending-note">' + h.escapeHtml(statusRead.en)
      + '<br><span lang="zh">' + h.escapeHtml(statusRead.zh) + '</span></p>';
    if (status === "unavailable" && reason) {
      var reasonRead = reasonCopy(reason);
      html += '<p class="claims-pending-note">' + h.escapeHtml(reasonRead.en)
        + '<br><span lang="zh">' + h.escapeHtml(reasonRead.zh) + '</span></p>';
      html += '<span class="claims-reason-code">' + h.escapeHtml(reason) + '</span>';
    }
    if (claims.explanation) {
      html += '<p class="claims-pending-note">' + h.escapeHtml(claims.explanation) + '</p>';
    }
    if (claims.claims_direction) {
      html += '<div class="claims-trend-row"><span>' + h.bilingualLabel("Claims Direction")
        + '</span><strong>' + h.escapeHtml(titleCaseToken(claims.claims_direction)) + '</strong></div>';
    }
    if (claims.macro_growth_regime) {
      html += '<div class="claims-trend-row"><span>' + h.bilingualLabel("Macro Growth Regime")
        + '</span><strong>' + h.escapeHtml(titleCaseToken(claims.macro_growth_regime)) + '</strong></div>';
    }
    html += '<div class="claims-trend-grid">';
    html += renderTrendRecord(claims.initial_claims, "Initial Claims", h);
    html += renderTrendRecord(claims.continuing_claims, "Continuing Claims", h);
    html += '</div>';
    html += renderVintages(claims.vintages, h);
    if (claims.method_version) {
      html += '<div class="claims-trend-row"><span>' + h.bilingualLabel("Method Version")
        + '</span><strong>' + h.escapeHtml(claims.method_version) + '</strong></div>';
    }
    html += '</section>';

    html += renderLaborContext(labor, h);
    html += renderRealActivity(realActivity, h);
    html += renderEventRisk(eventRisk, h);
    html += renderOverall(overall, h);

    html += '</section>';
    body.innerHTML = html;
  }

  window.claimsConfirmationUi = {
    renderCard: renderCard,
    renderDetail: renderDetail,
  };
})();

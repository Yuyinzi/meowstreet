(function () {
  window.housingPermitsUi = {
    renderCard: function (card, helpers) {
      var h = helpers;
      var l = card.latest || {};
      var status = card.status || "unavailable";
      var selected = h.isSelectedGrowthCycleDetailId && h.isSelectedGrowthCycleDetailId("housing_permits");
      var presentation = {
        supports_growth_path: {
          badge: "Confirms ISM Path",
          conclusion: "Housing evidence confirms the ISM-implied growth path.",
          conclusionZh: "住房端正在确认 ISM 指向的增长路径。",
          tone: "expanding",
        },
        challenges_growth_path: {
          badge: "Challenges ISM Path",
          conclusion: "Housing evidence does not confirm the ISM-implied growth path.",
          conclusionZh: "住房端与 ISM 指向的增长路径不一致。",
          tone: "contracting",
        },
        awaiting_confirmation: {
          badge: "Could Not Confirm ISM Path",
          conclusion: "Housing evidence has not yet confirmed the ISM-implied growth path.",
          conclusionZh: "住房端尚未确认 ISM 指向的增长路径。",
          tone: "mixed",
        },
        unavailable: {
          badge: "Data Unavailable",
          conclusion: "Housing evidence cannot yet assess the ISM-implied growth path.",
          conclusionZh: "住房端数据暂不足以核验 ISM 指向的增长路径。",
          tone: "missing",
        },
      }[status] || {
        badge: "Awaiting Confirmation",
        conclusion: "Housing evidence has not yet confirmed the ISM-implied growth path.",
        conclusionZh: "住房端尚未确认 ISM 指向的增长路径。",
        tone: "mixed",
      };

      var html = '<button class="m2-card m2-card-button evidence-target m2-card-' + h.escapeHtml(presentation.tone) + '"';
      html += selected ? " selected" : "";
      html += ' id="evidence-housing-permits" type="button" data-growth-cycle-detail-id="housing_permits">';
      html += '<div class="m2-card-head">';
      html += '<span>' + h.bilingualTitle("Building Permits") + '</span>';
      html += '<strong class="inflation-status-badge">' + h.escapeHtml(presentation.badge) + '</strong>';
      html += '</div>';

      if (status !== "unavailable" && l.permits_saar != null) {
        html += '<div class="m2-metric-band">';
        html += '<div><span>' + h.bilingualLabel("SAAR") + '</span><strong>' + h.escapeHtml(h.fmtNumber(l.permits_saar)) + 'K</strong></div>';
        html += '<div><span>' + h.bilingualLabel("MoM") + '</span><strong>' + h.escapeHtml(h.fmtSignedPctDecimal(l.permits_mom_pct)) + '</strong></div>';
        html += '<div><span>' + h.bilingualLabel("YoY") + '</span><strong>' + h.escapeHtml(h.fmtSignedPctDecimal(l.permits_yoy_pct)) + '</strong></div>';
        if (l.permits_yoy_12m_average != null) {
          html += '<div><span>' + h.bilingualLabel("12M Avg YoY") + '</span><strong>' + h.escapeHtml(h.fmtSignedPctDecimal(l.permits_yoy_12m_average)) + '</strong></div>';
        }
        html += '</div>';
      }

      html += '<div class="m2-card-footnote">';
      html += '<strong>' + h.escapeHtml(presentation.conclusion) + '</strong>';
      html += '<br><span lang="zh">' + h.escapeHtml(presentation.conclusionZh) + '</span>';
      if (card.reason) {
        html += '<br><small>Reason / 原因: ' + h.escapeHtml(card.reason) + '</small>';
      }
      html += '</div>';

      html += '</button>';
      return html;
    },

    renderDetail: function (body, payload, helpers) {
      var h = helpers;
      var statusClass = {
        supports_growth_path: "supportive",
        challenges_growth_path: "warning",
        awaiting_confirmation: "mixed",
        unavailable: "missing",
      }[payload.status] || "mixed";
      var crossValidation = payload.cross_validation || {};
      var survey = crossValidation.survey_synthesis || {};
      var permits = crossValidation.permits || {};
      var read = {
        supports_growth_path: {
          headline: "Confirms ISM Path",
          text: "Housing evidence confirms the ISM-implied growth path.",
          textZh: "住房端正在确认 ISM 指向的增长路径。",
        },
        challenges_growth_path: {
          headline: "Challenges ISM Path",
          text: "Housing evidence does not confirm the ISM-implied growth path.",
          textZh: "住房端与 ISM 指向的增长路径不一致。",
        },
        awaiting_confirmation: {
          headline: "Could Not Confirm ISM Path",
          text: "Housing evidence has not yet confirmed the ISM-implied growth path.",
          textZh: "住房端尚未确认 ISM 指向的增长路径。",
        },
        unavailable: {
          headline: "Data Unavailable",
          text: "Housing evidence cannot yet assess the ISM-implied growth path.",
          textZh: "住房端数据暂不足以核验 ISM 指向的增长路径。",
        },
      }[payload.status] || {
        headline: "Could Not Confirm ISM Path",
        text: "Housing evidence has not yet confirmed the ISM-implied growth path.",
        textZh: "住房端尚未确认 ISM 指向的增长路径。",
      };

      var html = '<section class="housing-permits-detail">';
      html += '<h2>' + h.escapeHtml(h.titleCaseToken(payload.series_id)) + '</h2>';
      html += '<section class="housing-permits-assessment ' + h.escapeHtml(statusClass) + '">';
      html += '<h3>Housing Read</h3>';
      html += '<div class="housing-permits-primary-read">';
      html += '<strong>' + h.escapeHtml(read.headline) + '</strong>';
      html += '<p>' + h.escapeHtml(read.text) + '</p>';
      html += '<p lang="zh">' + h.escapeHtml(read.textZh) + '</p>';
      if (payload.reason) {
        html += '<p>' + h.escapeHtml(payload.reason) + '</p>';
      }
      html += '</div>';
      html += '</section>';

      if (survey.expected_gdp_direction || permits.primary_trend) {
        html += '<section class="housing-permits-cross-check">';
        html += '<h3>Cross-check</h3>';
        if (survey.expected_gdp_direction) {
          html += '<p>ISM path: <strong>' + h.escapeHtml(survey.expected_gdp_direction) + '</strong></p>';
        }
        if (permits.primary_trend) {
          html += '<p>Permit primary trend: <strong>' + h.escapeHtml(permits.primary_trend) + '</strong></p>';
        }
        if (permits.yoy_12m_average != null && permits.previous_yoy_12m_average != null) {
          html += '<p>12M Avg YoY: <strong>' + h.escapeHtml(h.fmtSignedPctDecimal(permits.yoy_12m_average)) + '</strong> from ' + h.escapeHtml(h.fmtSignedPctDecimal(permits.previous_yoy_12m_average)) + '</p>';
        }
        if (permits.latest_mom != null && permits.latest_yoy != null) {
          html += '<p>Latest check: MoM ' + h.escapeHtml(h.fmtSignedPctDecimal(permits.latest_mom)) + ', YoY ' + h.escapeHtml(h.fmtSignedPctDecimal(permits.latest_yoy)) + '</p>';
        }
        if (survey.underlying_alignment === "aligned") {
          html += '<p class="housing-permits-cross-result">Longer-term permit trend aligns with the ISM slowdown path, but the latest monthly rebound conflicts with that trend, so this release cannot confirm the ISM path.</p>';
        } else if (survey.underlying_alignment === "conflicting") {
          html += '<p class="housing-permits-cross-result">Underlying permit trend conflicts with the ISM path.</p>';
        }
        html += '</section>';
      }

      if (payload.observation_period) {
        html += '<p class="housing-permits-period">' + h.escapeHtml(h.fmtMonthYear(payload.observation_period)) + '</p>';
      }

      html += h.renderGrowthCycleRangeControl();
      html += '<div class="relationship-chart-grid">';
      (payload.charts || []).forEach(function (chart, index) {
        var filtered = h.filterChartForRange(chart, h.getSelectedChartRange());
        html += h.renderRatesDetailChart(filtered, index);
      });
      html += '</div>';

      html += '<div class="housing-permits-definitions">';
      html += '<p>' + h.escapeHtml(h.bilingualLabel("Source")) + ' (<span lang="zh">\u6765\u6E90</span>): U.S. Census Bureau, New Residential Construction, Seasonally Adjusted Annual Rate (SAAR)';
      html += '</p></div>';

      html += '</section>';
      body.innerHTML = html;
      h.bindGrowthCycleRangeControl(body);
      h.attachRatesChartTooltips(body, payload.charts.map(function (chart) {
        return h.filterChartForRange(chart, h.getSelectedChartRange());
      }));
    },
  };
})();

(function () {
  window.housingPermitsUi = {
    renderCard: function (card, helpers) {
      var h = helpers;
      var l = card.latest || {};
      var status = card.status || "unavailable";
      var selected = h.isSelectedGrowthCycleDetailId && h.isSelectedGrowthCycleDetailId("housing_permits");
      var statusClass = h.statusClass(status);
      var zhStatus = {
        supports_growth_path: "\u4F4F\u623F\u8BC1\u636E\u652F\u6301\u5F53\u524D\u589E\u957F\u8DEF\u5F84",
        challenges_growth_path: "\u4F4F\u623F\u8BC1\u636E\u4E0D\u652F\u6301\u5F53\u524D\u589E\u957F\u8DEF\u5F84",
        awaiting_confirmation: "\u4F4F\u623F\u8BC1\u636E\u5F85\u786E\u8BA4",
        unavailable: "\u4F4F\u623F\u6570\u636E\u6682\u4E0D\u53EF\u7528",
      }[status] || "";

      var html = '<button class="m2-card m2-card-button evidence-target m2-card-' + h.escapeHtml(statusClass) + '"';
      html += selected ? " selected" : "";
      html += ' id="evidence-housing-permits" type="button" data-growth-cycle-detail-id="housing_permits">';
      html += '<div class="m2-card-title-row">';
      html += '<span class="m2-card-title">' + h.bilingualLabel("Building Permits") + '</span>';
      if (status !== "unavailable") {
        html += '<span class="ism-card-badge ism-badge-' + h.escapeHtml(statusClass) + '">' + h.escapeHtml(zhStatus) + '</span>';
      }
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
      } else if (status === "unavailable") {
        html += '<p class="m2-card-reason">' + h.escapeHtml(card.reason || "\u4F4F\u623F\u6570\u636E\u6682\u4E0D\u53EF\u7528") + '</p>';
      }

      if (card.observation_period) {
        html += '<div class="m2-level-row"><span>' + h.bilingualLabel("Observation") + '</span><strong>' + h.escapeHtml(h.fmtMonthYear(card.observation_period)) + '</strong></div>';
      }

      html += '</button>';
      return html;
    },

    renderDetail: function (body, payload, helpers) {
      var h = helpers;
      var l = payload.latest || {};
      var statusClass = h.statusClass(payload.status);

      var html = '<section class="housing-permits-detail">';
      html += '<h2>' + h.escapeHtml(h.titleCaseToken(payload.series_id)) + '</h2>';
      html += '<p class="housing-permits-status ' + h.escapeHtml(statusClass) + '">' + h.escapeHtml(payload.reason || "") + '</p>';

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

      html += '<div class="housing-permits-source">';
      html += '<h3>' + h.escapeHtml(h.bilingualLabel("Basis for This Judgment")) + ' (<span lang="zh">\u672C\u6B21\u5224\u65AD\u53C2\u7167</span>)</h3>';
      html += '<ul><li>' + h.bilingualTitle("Survey Synthesis") + ' \u2192 ' + h.escapeHtml(payload.status || "") + '</li>';
      html += '<li>' + h.bilingualTitle("Building Permits") + ' \u2192 SAAR ' + h.escapeHtml(h.fmtNumber(l.permits_saar)) + 'K</li></ul>';
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

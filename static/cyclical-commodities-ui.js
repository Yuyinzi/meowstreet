(function () {
  window.CyclicalCommoditiesUi = {
    renderCard: function (card, helpers) {
      var h = helpers;
      var status = card.status || "partial_official_evidence";
      var selected = h.isSelectedGrowthCycleDetailId && h.isSelectedGrowthCycleDetailId("cyclical_commodities");

      var html = '<button class="m2-card m2-card-button evidence-target m2-card-mixed"';
      html += selected ? " selected" : "";
      html += ' id="evidence-cyclical-commodities" type="button" data-growth-cycle-detail-id="cyclical_commodities">';
      html += '<div class="m2-card-head">';
      html += '<span>' + h.bilingualTitle("Cyclical Commodities & USD") + '</span>';
      html += '<strong class="inflation-status-badge">Partial Official Evidence</strong>';
      html += '</div>';
      html += '<div class="m2-card-footnote">';
      html += '<strong>Official evidence is partial / 官方证据不完整</strong>';
      if (card.reason) {
        html += '<br><small>Reason / 原因: ' + h.escapeHtml(card.reason) + '</small>';
      }
      if (card.available_evidence && card.available_evidence.length) {
        html += '<br><small>Available / 可用的: ' + h.escapeHtml(card.available_evidence.join(", ")) + '</small>';
      }
      html += '</div>';
      html += '</button>';
      return html;
    },

    renderDetail: function (body, payload, helpers) {
      var h = helpers;
      var steps = payload.steps || [];

      function renderValue(val) {
        if (val == null) return "--";
        if (typeof val === "number") return h.fmtSignedPctDecimal(val);
        return h.escapeHtml(String(val));
      }

      function renderCOTRow(commodity) {
        var norm = commodity.normalized_manager_net_position;
        var normStr = norm != null ? norm.toFixed(4) : "--";
        var flipStr = commodity.flip || "--";
        var noteHtml = "";
        if (commodity.contract_note) {
          noteHtml = '<p class="contract-note">' + h.escapeHtml(commodity.contract_note) + '</p>';
        }
        return '<div class="workflow-row">'
          + '<div class="workflow-label">' + h.escapeHtml(commodity.display_name || commodity.commodity_id) + '</div>'
          + noteHtml
          + '<div class="workflow-metrics">'
          + '<span>Longs: ' + h.escapeHtml(String(commodity.manager_longs || "--")) + '</span>'
          + '<span>Shorts: ' + h.escapeHtml(String(commodity.manager_shorts || "--")) + '</span>'
          + '<span>OI: ' + h.escapeHtml(String(commodity.open_interest || "--")) + '</span>'
          + '<span>Normalized: ' + h.escapeHtml(normStr) + '</span>'
          + '<span>Flip: <strong>' + h.escapeHtml(flipStr) + '</strong></span>'
          + '</div>'
          + '</div>';
      }

      function renderUSDRow(series) {
        return '<div class="workflow-row">'
          + '<div class="workflow-label">' + h.escapeHtml(series.display_name || series.series_id) + '</div>'
          + '<div class="workflow-metrics">'
          + '<span>Latest: ' + h.escapeHtml(h.fmtNumber(series.latest_value)) + '</span>'
          + '<span>Daily: ' + renderValue(series.daily_return) + '</span>'
          + '<span>Weekly: ' + renderValue(series.weekly_return) + '</span>'
          + '</div>'
          + '</div>';
      }

      function renderInflationRow(series) {
        return '<div class="workflow-row">'
          + '<div class="workflow-label">' + h.escapeHtml(series.display_name || series.series_id) + '</div>'
          + '<div class="workflow-metrics">'
          + '<span>Latest: ' + h.escapeHtml(h.fmtNumber(series.latest_value)) + '</span>'
          + '<span>MoM: ' + renderValue(series.mom_pct) + '</span>'
          + '<span>YoY: ' + renderValue(series.yoy_pct) + '</span>'
          + '</div>'
          + '</div>';
      }

      var html = '<section class="cyclical-commodities-detail">';
      html += '<h2>' + h.bilingualTitle("Cyclical Commodities & USD Evidence") + '</h2>';

      for (var i = 0; i < steps.length; i++) {
        var step = steps[i];
        var isAvailable = step.status === "available";
        html += '<section class="step-section">';
        html += '<h3>Step ' + step.step + ': ' + h.escapeHtml(step.title) + '</h3>';

        if (step.step === 3 && isAvailable) {
          html += '<p><em>' + h.escapeHtml(step.method) + '</em></p>';
          html += '<p class="note">' + h.escapeHtml(step.note) + '</p>';
          for (var c = 0; c < step.commodities.length; c++) {
            html += renderCOTRow(step.commodities[c]);
          }
        } else if (step.step === 4 && isAvailable) {
          html += '<p class="note">' + h.escapeHtml(step.note) + '</p>';
          for (var u = 0; u < step.series.length; u++) {
            html += renderUSDRow(step.series[u]);
          }
        } else if (step.step === 5 && isAvailable) {
          html += '<p class="note">' + h.escapeHtml(step.note) + '</p>';
          for (var inf = 0; inf < step.series.length; inf++) {
            html += renderInflationRow(step.series[inf]);
          }
        } else if (!isAvailable) {
          html += '<p class="unavailable">Status: ' + h.escapeHtml(step.status) + ' — ' + h.escapeHtml(step.reason || "Not configured") + '</p>';
        }

        html += '</section>';
      }

      if (payload.freshness && Object.keys(payload.freshness).length) {
        html += '<section class="step-section">';
        html += '<h3>Freshness / 数据时效</h3>';
        html += '<p>Observation dates — exact dates only; no age-based stale classification is applied.</p>';
        var f = payload.freshness;
        if (f.cftc_latest_report_date) html += '<p>CFTC COT latest report date: <strong>' + h.escapeHtml(f.cftc_latest_report_date) + '</strong></p>';
        if (f.usd_latest_observation_date) html += '<p>USD latest observation date: <strong>' + h.escapeHtml(f.usd_latest_observation_date) + '</strong></p>';
        if (f.inflation_latest_observation_date) html += '<p>CPI/PPI latest observation date: <strong>' + h.escapeHtml(f.inflation_latest_observation_date) + '</strong></p>';
        html += '</section>';
      }

      html += '<section class="step-section">';
      html += '<h3>Extreme & Distribution Status</h3>';
      html += '<p><strong>Extreme detection not configured</strong> — COT extreme, z-score, and percentile conclusions await an approved method specification.</p>';
      html += '<p><strong>Distribution status not configured</strong> — USD and CPI/PPI normal/abnormal status await an approved distribution specification.</p>';
      html += '</section>';

      html += '<section class="step-section">';
      html += '<h3>Important Notice / 重要提示</h3>';
      html += '<p>This module provides Cyclical Commodities and USD evidence only. It does not make buy/sell recommendations. '
        + 'Commodity attribution (prices, demand, supply, inventory sources) is not yet configured and cannot be substituted by COT or USD evidence.</p>';
      html += '</section>';

      html += '</section>';
      body.innerHTML = html;
    },
  };
})();

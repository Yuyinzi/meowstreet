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

      function detail(number) {
        for (var index = 0; index < steps.length; index++) {
          if (steps[index].step === number) return steps[index];
        }
        return { status: "unavailable", reason: "not configured" };
      }

      function unavailable(reason) {
        return '<p class="unavailable">' + h.escapeHtml(reason || "Not configured") + '</p>';
      }

      var observation = detail(1);
      var attribution = detail(2);
      var cot = detail(3);
      var usd = detail(4);
      var inflation = detail(5);
      var freshness = payload.freshness || {};
      var html = '<section class="cyclical-commodities-detail">';
      html += '<header class="detail-head">';
      html += '<div><p class="eyebrow">Growth Cycle Evidence</p><h2>' + h.bilingualTitle("Cyclical Commodities & USD") + '</h2>';
      html += '<p>This module corroborates a macro narrative; it does not issue buy or sell instructions.</p></div>';
      html += '<span class="inflation-status-badge">Official Evidence</span></header>';

      html += '<section class="evidence-section">';
      html += '<h3>Commodity Observation</h3>';
      html += '<p class="section-intro">Price moves require demand, supply, and inventory attribution before they can support a macro narrative.</p>';
      html += '<div class="evidence-empty"><strong>Awaiting commodity price and attribution sources</strong><span>'
        + h.escapeHtml(attribution.reason || observation.reason || "not configured") + '</span></div>';
      html += '</section>';

      html += '<section class="evidence-section">';
      html += '<h3>Market Corroboration</h3>';
      html += '<div class="evidence-grid">';
      html += '<article class="evidence-card"><h4>CFTC COT Positioning</h4>';
      if (freshness.cftc_latest_report_date) html += '<p class="source-date">As of ' + h.escapeHtml(freshness.cftc_latest_report_date) + '</p>';
      if (cot.status === "available") {
        html += '<p class="note">' + h.escapeHtml(cot.method) + '</p>';
        for (var c = 0; c < cot.commodities.length; c++) html += renderCOTRow(cot.commodities[c]);
      } else html += unavailable(cot.reason);
      html += '</article>';
      html += '<article class="evidence-card"><h4>Trade-Weighted USD</h4>';
      if (freshness.usd_latest_observation_date) html += '<p class="source-date">As of ' + h.escapeHtml(freshness.usd_latest_observation_date) + '</p>';
      if (usd.status === "available") {
        for (var u = 0; u < usd.series.length; u++) html += renderUSDRow(usd.series[u]);
      } else html += unavailable(usd.reason);
      html += '</article>';
      html += '<article class="evidence-card"><h4>CPI / PPI Confirmation</h4>';
      if (freshness.inflation_latest_observation_date) html += '<p class="source-date">As of ' + h.escapeHtml(freshness.inflation_latest_observation_date) + '</p>';
      if (inflation.status === "available") {
        for (var inf = 0; inf < inflation.series.length; inf++) html += renderInflationRow(inflation.series[inf]);
      } else html += unavailable(inflation.reason);
      html += '</article></div></section>';

      html += '<section class="evidence-section boundaries"><h3>Method Boundaries</h3>';
      html += '<p>Commodity price attribution, COT extreme detection, and USD/CPI/PPI distribution classifications are not configured. These gaps remain pending rather than being converted into a trading conclusion.</p>';
      html += '</section>';

      html += '</section>';
      body.innerHTML = html;
    },
  };
})();

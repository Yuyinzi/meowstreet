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
      var oilObservation = payload.oil_observation || {};
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

      function reasonLabel(attrObj) {
        return attrObj.review_label || attrObj.reason || "Attribution inputs not available";
      }

      function _oilDisplayName(seriesId) {
        var names = {
          "oil_wti_spot": "WTI Spot",
          "oil_brent_spot": "Brent Spot",
        };
        return names[seriesId] || seriesId;
      }

      function renderOilBenchmarkSummary(benchmarks) {
        var ids = Object.keys(benchmarks || {}).sort();
        var html = "";
        for (var i = 0; i < ids.length; i++) {
          var b = benchmarks[ids[i]];
          if (b.status !== "available") {
            html += '<div class="workflow-row">'
              + '<div class="workflow-label">' + h.escapeHtml(_oilDisplayName(ids[i])) + '</div>'
              + '<div class="workflow-metrics"><span>Not available</span></div>'
              + '</div>';
            continue;
          }
          html += '<div class="workflow-row">'
            + '<div class="workflow-label">' + h.escapeHtml(_oilDisplayName(ids[i])) + '</div>'
            + '<div class="workflow-metrics">'
            + '<span>Value: ' + h.escapeHtml(h.fmtNumber(b.latest_value)) + ' $/BBL</span>'
            + '<span>Daily: ' + renderValue(b.daily_return) + '</span>'
            + '<span>Weekly: ' + renderValue(b.weekly_return) + '</span>'
            + '<span class="source-date">As of: ' + h.escapeHtml(b.latest_date || "") + '</span>'
            + '<span>Source: ' + h.escapeHtml(b.source_identifier || b.source_url || "") + '</span>'
            + '</div>'
            + '</div>';
        }
        return html;
      }

      function renderAttributionRows(metrics) {
        var html = "";
        for (var i = 0; i < (metrics || []).length; i++) {
          var m = metrics[i];
          var roleLabel = "";
          if (m.role === "inventory") roleLabel = "Inventory";
          else if (m.role === "supply_context") roleLabel = "Supply context";
          else if (m.role === "processing_activity") roleLabel = "Processing activity";
          else if (m.role === "demand_proxy") roleLabel = "Demand proxy";
          else roleLabel = m.role;
          html += '<div class="workflow-row">'
            + '<div class="workflow-label">' + h.escapeHtml(m.display_name || m.series_id) + '</div>'
            + '<div class="workflow-metrics">';
          if (m.status === "available") {
            html += '<span>' + h.escapeHtml(roleLabel) + '</span>'
              + '<span>Value: ' + h.escapeHtml(h.fmtNumber(m.latest_value)) + '</span>'
              + '<span class="source-date">' + h.escapeHtml(m.latest_date || "") + '</span>';
            if (m.source_identifier) {
              html += '<span>Source: ' + h.escapeHtml(m.source_identifier) + '</span>';
            }
          } else {
            html += '<span>Not available</span>';
          }
          html += '</div></div>';
        }
        return html;
      }

      var read = payload.process_read || {};
      var attr = payload.commodity_attribution || {};
      var freshness = payload.freshness || {};

      var html = '<section class="cyclical-commodities-detail">';

      html += '<section class="process-read">';
      html += '<p class="eyebrow">Process Read</p>';
      html += '<h3>' + h.escapeHtml(read.label || "Evidence unavailable") + '</h3>';
      html += '<p>' + h.escapeHtml(read.reason || "") + '</p>';
      html += '<p class="next-action">Next: ' + h.escapeHtml(read.next_action || "") + '</p>';
      html += '</section>';

      html += '<section class="evidence-section">';
      html += '<h3>Oil Observation</h3>';
      html += '<p class="section-intro">WTI and Brent describe the observed price move. Distribution status is not configured.</p>';
      html += renderOilBenchmarkSummary(oilObservation.benchmarks || {});
      html += '<h4>Attribution inputs</h4>';
      html += '<p class="summary-stat">' + h.escapeHtml(attr.review_label || reasonLabel(attr)) + '</p>';
      html += renderAttributionRows(attr.metrics || []);
      html += '</section>';

      html += '<section class="evidence-section">';
      html += '<h3>Market Corroboration</h3>';
      html += '<div class="evidence-grid">';

      var cot = detail(5);
      var usd = detail(6);
      var inflation = detail(7);
      var corr = payload.corroboration || {};
      var cotCorr = corr.cot || {};
      var usdCorr = corr.usd || {};
      var infCorr = corr.inflation || {};

      html += '<article class="evidence-card"><h4>CFTC COT Positioning</h4>';
      if (cotCorr.available_contract_count != null) {
        html += '<p class="summary-stat">' + h.escapeHtml(String(cotCorr.available_contract_count)) + ' contracts available';
        if (cotCorr.positive_flip_count) html += ', ' + h.escapeHtml(String(cotCorr.positive_flip_count)) + ' positive flips';
        if (cotCorr.negative_flip_count) html += ', ' + h.escapeHtml(String(cotCorr.negative_flip_count)) + ' negative flips';
        html += '</p>';
      }
      if (freshness.cftc_latest_report_date) html += '<p class="source-date">As of ' + h.escapeHtml(freshness.cftc_latest_report_date) + '</p>';
      if (cot.status === "available") {
        html += '<details class="raw-evidence">';
        html += '<summary>View raw evidence</summary>';
        for (var c = 0; c < (cot.commodities || []).length; c++) html += renderCOTRow(cot.commodities[c]);
        html += '</details>';
      }
      html += '</article>';

      html += '<article class="evidence-card"><h4>Trade-Weighted USD</h4>';
      if (usdCorr.available_series_count != null) {
        html += '<p class="summary-stat">' + h.escapeHtml(String(usdCorr.available_series_count)) + ' series — daily: '
          + h.escapeHtml(usdCorr.daily_direction || "unavailable") + ', weekly: '
          + h.escapeHtml(usdCorr.weekly_direction || "unavailable") + '</p>';
      }
      if (freshness.usd_latest_observation_date) html += '<p class="source-date">As of ' + h.escapeHtml(freshness.usd_latest_observation_date) + '</p>';
      if (usd.status === "available") {
        html += '<details class="raw-evidence">';
        html += '<summary>View raw evidence</summary>';
        for (var u = 0; u < (usd.series || []).length; u++) html += renderUSDRow(usd.series[u]);
        html += '</details>';
      }
      html += '</article>';

      html += '<article class="evidence-card"><h4>CPI / PPI Confirmation</h4>';
      if (infCorr.available_series_count != null) {
        html += '<p class="summary-stat">' + h.escapeHtml(String(infCorr.available_series_count)) + ' series — confirmation context</p>';
      }
      if (freshness.inflation_latest_observation_date) html += '<p class="source-date">As of ' + h.escapeHtml(freshness.inflation_latest_observation_date) + '</p>';
      if (inflation.status === "available") {
        html += '<details class="raw-evidence">';
        html += '<summary>View raw evidence</summary>';
        for (var inf = 0; inf < (inflation.series || []).length; inf++) html += renderInflationRow(inflation.series[inf]);
        html += '</details>';
      }
      html += '</article></div></section>';

      html += '<section class="evidence-section boundaries"><h3>Method Boundaries</h3>';
      html += '<p>Commodity price attribution, COT extreme detection, and USD/CPI/PPI distribution classifications are not configured. These gaps remain pending rather than being converted into a trading conclusion.</p>';
      html += '</section>';

      html += '</section>';
      body.innerHTML = html;
    },
  };
})();

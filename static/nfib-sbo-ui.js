(function () {
  window.nfibSboUi = {
    renderCard: function (card, helpers) {
      var h = helpers;
      var l = card.latest || {};
      var status = card.status || "unavailable";
      var selected = h.isSelectedGrowthCycleDetailId && h.isSelectedGrowthCycleDetailId("nfib_sbo");
      var presentation = {
        supports_growth_path: {
          badge: "Supports Growth Path",
          conclusion: "NFIB evidence supports the ISM-implied growth path.",
          conclusionZh: "NFIB 数据支持 ISM 指向的增长路径。",
          tone: "expanding",
        },
        challenges_growth_path: {
          badge: "Challenges Growth Path",
          conclusion: "NFIB evidence challenges the ISM-implied growth path.",
          conclusionZh: "NFIB 数据与 ISM 指向的增长路径不一致。",
          tone: "contracting",
        },
        awaiting_confirmation: {
          badge: "Awaiting Confirmation",
          conclusion: "NFIB evidence has not yet confirmed the ISM-implied growth path.",
          conclusionZh: "NFIB 数据尚未确认 ISM 指向的增长路径。",
          tone: "mixed",
        },
        unavailable: {
          badge: "Data Unavailable",
          conclusion: "NFIB evidence cannot yet assess the ISM-implied growth path.",
          conclusionZh: "NFIB 数据暂不足以核验 ISM 指向的增长路径。",
          tone: "missing",
        },
      }[status] || {
        badge: "Awaiting Confirmation",
        conclusion: "NFIB evidence has not yet confirmed the ISM-implied growth path.",
        conclusionZh: "NFIB 数据尚未确认 ISM 指向的增长路径。",
        tone: "mixed",
      };

      var html = '<button class="m2-card m2-card-button evidence-target m2-card-' + h.escapeHtml(presentation.tone) + '"';
      html += selected ? " selected" : "";
      html += ' id="evidence-nfib-sbo" type="button" data-growth-cycle-detail-id="nfib_sbo">';
      html += '<div class="m2-card-head">';
      html += '<span>' + h.bilingualTitle("NFIB Small Business") + '</span>';
      html += '<strong class="inflation-status-badge">' + h.escapeHtml(presentation.badge) + '</strong>';
      html += '</div>';

      if (status !== "unavailable" && l.leading_index != null) {
        html += '<div class="m2-metric-band">';
        html += '<div><span>' + h.bilingualLabel("Leading Index") + '</span><strong>' + h.escapeHtml(h.fmtNumber(l.leading_index)) + '</strong></div>';
        if (l.leading_index_4m_average != null) {
          html += '<div><span>' + h.bilingualLabel("4M Avg") + '</span><strong>' + h.escapeHtml(h.fmtNumber(l.leading_index_4m_average)) + '</strong></div>';
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
      var signal = payload.latest_signal || {};
      var components = payload.components || {};
      var optimism = payload.optimism || {};
      var detailSeries = payload.detail_series || [];
      var statusClass = {
        supports_growth_path: "supportive",
        challenges_growth_path: "warning",
        awaiting_confirmation: "mixed",
        unavailable: "missing",
      }[payload.status] || "mixed";

      var html = '<section class="nfib-sbo-detail">';
      html += '<h2>' + h.escapeHtml(h.bilingualTitle("NFIB Small Business Outlook")) + '</h2>';

      if (signal.leading_index != null) {
        html += '<section class="nfib-sbo-signal nfib-sbo-signal-' + h.escapeHtml(statusClass) + '">';
        html += '<h3>' + h.escapeHtml(h.bilingualLabel("Leading Index")) + '</h3>';
        html += '<div class="nfib-sbo-signal-metrics">';
        html += '<div><span>' + h.escapeHtml(h.bilingualLabel("Current")) + '</span><strong>' + h.escapeHtml(h.fmtNumber(signal.leading_index)) + '</strong></div>';
        if (signal.leading_index_4m_average != null) {
          html += '<div><span>' + h.escapeHtml(h.bilingualLabel("4M Average")) + '</span><strong>' + h.escapeHtml(h.fmtNumber(signal.leading_index_4m_average)) + '</strong></div>';
        }
        if (signal.leading_index_4m_change != null) {
          html += '<div><span>' + h.escapeHtml(h.bilingualLabel("4M Change")) + '</span><strong>' + (signal.leading_index_4m_change >= 0 ? "+" : "") + h.escapeHtml(h.fmtNumber(signal.leading_index_4m_change)) + '</strong></div>';
        }
        html += '</div>';
        if (payload.reason) {
          html += '<p>' + h.escapeHtml(payload.reason) + '</p>';
        }
        html += '</section>';
      }

      html += '<section class="nfib-sbo-components">';
      html += '<h3>' + h.escapeHtml(h.bilingualLabel("Five Components")) + '</h3>';
      html += '<div class="nfib-sbo-component-grid">';

      var componentMeta = {
        nfib_sbo_employment_plans: { label: "Employment Plans", labelZh: "就业计划" },
        nfib_sbo_expansion_outlook: { label: "Expansion Outlook", labelZh: "扩张前景" },
        nfib_sbo_inventory_plans: { label: "Inventory Plans", labelZh: "库存计划" },
        nfib_sbo_economic_expectations: { label: "Economic Expectations", labelZh: "经济预期" },
        nfib_sbo_real_sales_expectations: { label: "Real Sales Expectations", labelZh: "实际销售预期" },
      };

      for (var sid in componentMeta) {
        if (componentMeta.hasOwnProperty(sid)) {
          var comp = components[sid];
          var meta = componentMeta[sid];
          html += '<div class="nfib-sbo-component-row">';
          html += '<span>' + h.escapeHtml(h.bilingualLabel(meta.label)) + '</span>';
          html += '<strong>' + (comp ? h.escapeHtml(h.fmtNumber(comp.latest)) : "\u2014") + '</strong>';
          html += '</div>';
        }
      }
      html += '</div>';
      html += '</section>';

      if (optimism && optimism.latest != null) {
        html += '<section class="nfib-sbo-optimism">';
        html += '<h3>' + h.escapeHtml(h.bilingualLabel("Optimism Index")) + '</h3>';
        html += '<p><strong>' + h.escapeHtml(h.fmtNumber(optimism.latest)) + '</strong></p>';
        html += '</section>';
      }

      html += h.renderGrowthCycleRangeControl();
      if (detailSeries.length) {
        html += '<div class="relationship-chart-grid">';
        var chart = { series: detailSeries, title: "NFIB Leading Index", keys: ["leading_index", "leading_index_4m_average"] };
        var filtered = h.filterChartForRange(chart, h.getSelectedChartRange());
        html += h.renderRatesDetailChart(filtered, 0);
        html += '</div>';
      }

      if (payload.signal_version) {
        html += '<p class="nfib-sbo-version">' + h.escapeHtml(h.bilingualLabel("Signal Version")) + ': ' + h.escapeHtml(payload.signal_version) + '</p>';
      }

      var provItems = [];
      if (payload.source_url) provItems.push('<a href="' + h.escapeHtml(payload.source_url) + '" target="_blank" rel="noopener noreferrer">' + h.escapeHtml(h.bilingualLabel("Official Report")) + ' &rarr;</a>');
      if (payload.release_date) provItems.push(h.escapeHtml(h.bilingualLabel("Release Date")) + ': ' + h.escapeHtml(payload.release_date));
      if (payload.source_hash) provItems.push(h.escapeHtml(h.bilingualLabel("SHA-256")) + ': <code>' + h.escapeHtml(payload.source_hash.slice(0, 16)) + '&hellip;</code>');
      if (provItems.length) {
        html += '<div class="nfib-sbo-provenance">' + provItems.join('<br>') + '</div>';
      }

      html += '</section>';
      body.innerHTML = html;
      h.bindGrowthCycleRangeControl(body);
      if (detailSeries.length) {
        h.attachRatesChartTooltips(body, [{ series: detailSeries, title: "NFIB Leading Index", keys: ["leading_index", "leading_index_4m_average"] }]);
      }
    },
  };
})();

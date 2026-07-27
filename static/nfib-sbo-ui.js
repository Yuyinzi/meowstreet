(function () {
  function readCopy(status, trend, latest, helpers) {
    var growthPath = {
      supports_growth_path: {
        en: "NFIB confirms the ISM-implied growth path.",
        zh: "NFIB 数据确认 ISM 指向的增长路径。",
      },
      challenges_growth_path: {
        en: "NFIB does not support the ISM-implied growth path.",
        zh: "NFIB 数据不支持 ISM 指向的增长路径。",
      },
      awaiting_confirmation: {
        en: "Could Not Confirm ISM Path",
        zh: "未能确认 ISM 指向的增长路径。",
      },
      unavailable: {
        en: "NFIB cannot yet assess the ISM-implied growth path.",
        zh: "NFIB 数据暂不足以核验 ISM 指向的增长路径。",
      },
    }[status] || {
      en: "NFIB has not yet confirmed the ISM-implied growth path.",
      zh: "NFIB 数据尚未确认 ISM 指向的增长路径。",
    };

    var outlook = {
      en: "Small-business outlook is mixed.",
      zh: "小企业前景分化。",
    };
    if (status === "unavailable") {
      outlook = {
        en: "Small-business outlook cannot be assessed from available data.",
        zh: "现有数据不足以判断小企业前景。",
      };
    } else if (trend === "weakening" && latest.leading_index_1m_change > 0) {
      outlook = {
        en: "The medium-term small-business outlook is weakening, while the latest month improved.",
        zh: "中期小企业前景仍在走弱，但最新一个月出现改善。",
      };
    } else if (trend === "improving" && latest.leading_index_1m_change < 0) {
      outlook = {
        en: "The medium-term small-business outlook is improving, while the latest month weakened.",
        zh: "中期小企业前景正在改善，但最新一个月转弱。",
      };
    } else if (trend === "weakening") {
      outlook = {
        en: "The medium-term small-business outlook is weakening.",
        zh: "中期小企业前景正在走弱。",
      };
    } else if (trend === "improving") {
      outlook = {
        en: "The medium-term small-business outlook is improving.",
        zh: "中期小企业前景正在改善。",
      };
    }

    var evidence = { en: "No completed comparison is available.", zh: "暂无完整的可比数据。" };
    if (latest.previous_leading_index != null && latest.leading_index != null) {
      var direction = latest.leading_index_1m_change >= 0 ? "rose" : "fell";
      var directionZh = latest.leading_index_1m_change >= 0 ? "上升" : "下降";
      evidence = {
        en: "The leading index " + direction + " from " + helpers.fmtNumber(latest.previous_leading_index) + " to " + helpers.fmtNumber(latest.leading_index) + " in the latest month.",
        zh: "最新一个月领先指数由 " + helpers.fmtNumber(latest.previous_leading_index) + " " + directionZh + "至 " + helpers.fmtNumber(latest.leading_index) + "。",
      };
    }

    return { growthPath: growthPath, outlook: outlook, evidence: evidence };
  }

  window.nfibSboUi = {
    renderCard: function (card, helpers) {
      var h = helpers;
      var l = card.latest || {};
      var status = card.status || "unavailable";
      var selected = h.isSelectedGrowthCycleDetailId && h.isSelectedGrowthCycleDetailId("nfib_sbo");
      var presentation = {
        supports_growth_path: {
          badge: "Supports Growth Path",
          tone: "expanding",
        },
        challenges_growth_path: {
          badge: "Challenges Growth Path",
          tone: "contracting",
        },
        awaiting_confirmation: {
          badge: "Could Not Confirm ISM Path",
          tone: "mixed",
        },
        unavailable: {
          badge: "Data Unavailable",
          tone: "missing",
        },
      }[status] || {
        badge: "Could Not Confirm ISM Path",
        tone: "mixed",
      };
      var reads = readCopy(status, card.trend, l, h);

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
      html += '<strong>' + h.escapeHtml(reads.growthPath.en) + '</strong>';
      html += '<br><span lang="zh">' + h.escapeHtml(reads.growthPath.zh) + '</span>';
      html += '<br><span>' + h.escapeHtml(reads.outlook.en) + '</span>';
      html += '<br><span lang="zh">' + h.escapeHtml(reads.outlook.zh) + '</span>';
      html += '<br><small>' + h.escapeHtml(reads.evidence.en) + '</small>';
      html += '</div>';

      html += '</button>';
      return html;
    },

    renderDetail: function (body, payload, helpers) {
      var h = helpers;
      var signal = payload.latest_signal || {};
      var leadingComponents = payload.leading_components || {};
      var contextComponents = payload.context_components || {};
      var optimism = payload.optimism || {};
      var detailSeries = payload.detail_series || [];
      var reads = readCopy(payload.status, payload.trend, signal, h);
      var statusClass = {
        supports_growth_path: "supportive",
        challenges_growth_path: "warning",
        awaiting_confirmation: "mixed",
        unavailable: "missing",
      }[payload.status] || "mixed";

      var html = '<section class="nfib-sbo-detail">';
      html += '<h2>' + h.bilingualTitle("NFIB Small Business Outlook") + '</h2>';

      if (signal.leading_index != null) {
        html += '<section class="nfib-sbo-signal nfib-sbo-signal-' + h.escapeHtml(statusClass) + '">';
        html += '<h3>' + h.bilingualLabel("Leading Index") + '</h3>';
        html += '<div class="nfib-sbo-signal-metrics">';
        html += '<div><span>' + h.bilingualLabel("Current") + '</span><strong>' + h.escapeHtml(h.fmtNumber(signal.leading_index)) + '</strong></div>';
        if (signal.leading_index_4m_average != null) {
          html += '<div><span>' + h.bilingualLabel("4M Average") + '</span><strong>' + h.escapeHtml(h.fmtNumber(signal.leading_index_4m_average)) + '</strong></div>';
        }
        if (signal.leading_index_4m_change != null) {
          html += '<div><span>' + h.bilingualLabel("4M Change") + '</span><strong>' + (signal.leading_index_4m_change >= 0 ? "+" : "") + h.escapeHtml(h.fmtNumber(signal.leading_index_4m_change)) + '</strong></div>';
        }
        html += '</div>';
        html += '<h3>' + h.bilingualLabel("Trading Read") + '</h3>';
        html += '<p><strong>' + h.escapeHtml(reads.growthPath.en) + '</strong><br><span lang="zh">' + h.escapeHtml(reads.growthPath.zh) + '</span></p>';
        html += '<h3>' + h.bilingualLabel("Small-Business Outlook") + '</h3>';
        html += '<p>' + h.escapeHtml(reads.outlook.en) + '<br><span lang="zh">' + h.escapeHtml(reads.outlook.zh) + '</span></p>';
        html += '<h3>' + h.bilingualLabel("Evidence") + '</h3>';
        html += '<p>' + h.escapeHtml(reads.evidence.en) + '<br><span lang="zh">' + h.escapeHtml(reads.evidence.zh) + '</span></p>';
        html += '</section>';
      }

      html += '<section class="nfib-sbo-components">';
      html += '<h3>' + h.bilingualLabel("Leading Index Inputs") + '</h3>';
      html += '<div class="nfib-sbo-component-grid">';

      var leadingMeta = {
        nfib_sbo_employment_plans: { label: "Employment Plans", labelZh: "就业计划" },
        nfib_sbo_expansion_outlook: { label: "Expansion Outlook", labelZh: "扩张前景" },
        nfib_sbo_inventory_plans: { label: "Inventory Plans", labelZh: "库存计划" },
        nfib_sbo_economic_expectations: { label: "Economic Expectations", labelZh: "经济预期" },
        nfib_sbo_real_sales_expectations: { label: "Real Sales Expectations", labelZh: "实际销售预期" },
      };

      for (var sid in leadingMeta) {
        if (leadingMeta.hasOwnProperty(sid)) {
          var comp = leadingComponents[sid];
          var meta = leadingMeta[sid];
          html += '<div class="nfib-sbo-component-row">';
          html += '<span>' + h.bilingualLabel(meta.label) + '</span>';
          html += '<strong>' + (comp ? h.escapeHtml(h.fmtNumber(comp.latest)) : "\u2014") + '</strong>';
          html += '</div>';
        }
      }
      html += '</div>';
      html += '</section>';

      html += '<section class="nfib-sbo-context-components">';
      html += '<h3>' + h.bilingualLabel("Official Context Components") + '</h3>';
      html += '<p class="nfib-sbo-context-note">' + h.bilingualLabel("Context only — does not change the NFIB leading signal") + '</p>';
      html += '<div class="nfib-sbo-component-grid nfib-sbo-context-grid">';

      var contextMeta = {
        nfib_sbo_capital_outlay_plans: { label: "Capital Expenditure Plans", labelZh: "资本支出计划" },
        nfib_sbo_current_inventory_low: { label: "Current Inventory Too Low", labelZh: "当前库存过低" },
        nfib_sbo_job_openings: { label: "Current Job Openings", labelZh: "当前职位空缺" },
        nfib_sbo_credit_conditions_expectations: { label: "Credit Conditions Expectation", labelZh: "信贷条件预期" },
        nfib_sbo_earnings_trends: { label: "Earnings Trends", labelZh: "盈利趋势" },
      };

      for (var cid in contextMeta) {
        if (contextMeta.hasOwnProperty(cid)) {
          var ctx = contextComponents[cid];
          var ctxMeta = contextMeta[cid];
          html += '<div class="nfib-sbo-component-row nfib-sbo-context-row">';
          html += '<span class="nfib-sbo-context-label">' + h.bilingualLabel(ctxMeta.label) + '</span>';
          html += '<strong class="nfib-sbo-context-value">' + (ctx ? h.escapeHtml(h.fmtNumber(ctx.latest)) : "\u2014") + '</strong>';
          if (ctx && ctx.change != null) {
            html += '<span class="nfib-sbo-context-change">' + (ctx.change >= 0 ? "+" : "") + h.escapeHtml(h.fmtNumber(ctx.change)) + '</span>';
          } else {
            html += '<span class="nfib-sbo-context-change">\u2014</span>';
          }
          html += '<span class="nfib-sbo-context-units">net%</span>';
          html += '</div>';
        }
      }
      html += '</div>';
      html += '</section>';

      if (optimism && optimism.latest != null) {
        html += '<section class="nfib-sbo-optimism nfib-sbo-section">';
        html += '<h3>' + h.bilingualLabel("Optimism Index") + '</h3>';
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
        html += '<p class="nfib-sbo-version">' + h.bilingualLabel("Signal Version") + ': ' + h.escapeHtml(payload.signal_version) + '</p>';
      }

      var provItems = [];
      if (payload.source_url) provItems.push('<a href="' + h.escapeHtml(payload.source_url) + '" target="_blank" rel="noopener noreferrer">' + h.bilingualLabel("Official Report") + ' &rarr;</a>');
      if (payload.release_date) provItems.push(h.bilingualLabel("Release Date") + ': ' + h.escapeHtml(payload.release_date));

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

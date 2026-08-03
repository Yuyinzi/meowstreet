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

      function renderState(value, state, label) {
        var st = state || "unavailable";
        return '<span class="state state-' + h.escapeHtml(st) + '">'
          + h.escapeHtml(label + ': ' + value + ' (' + st + ')')
          + '</span>';
      }

      function renderDistribution(distribution, label) {
        if (!distribution || distribution.classification === "unavailable") {
          return '<span class="state state-unavailable">'
            + h.escapeHtml(label + ': Unavailable')
            + '</span>';
        }
        var textMap = {
          normal: "Within 1σ, Normal",
          abnormal_1sigma: "1\u03c3 abnormal",
          abnormal_2sigma: "2\u03c3 abnormal",
          abnormal_3sigma: "3\u03c3 abnormal",
        };
        var text = textMap[distribution.classification] || distribution.classification;
        var className = distribution.classification === "normal"
          ? "state state-flat"
          : "state oil-distribution-abnormal";
        return '<span class="' + h.escapeHtml(className) + '">'
          + h.escapeHtml(label + ': ' + text)
          + '</span>';
      }

      function renderOilDistributionSummary(summary) {
        if (!summary) return "";
        return '<div class="oil-distribution-summary oil-distribution-summary-'
          + h.escapeHtml(summary.status || "incomplete") + '">'
          + '<strong>' + h.escapeHtml(summary.label || "Oil price distribution is incomplete; review the available benchmark evidence.") + '</strong>'
          + '<span>' + h.escapeHtml(summary.detail || "") + '</span>'
          + '</div>';
      }

      function renderDistributionReviewNote(series) {
        if (series.review_status !== "review_required") return "";
        return '<div class="distribution-review-note">'
          + h.escapeHtml(series.review_label || "")
          + '</div>';
      }

      function renderNonOilReviewStatus(series) {
        var labels = {
          observation_available: "Normal observation",
          review_required: "Review required",
          unavailable: "Insufficient history",
        };
        var status = series.review_status || "unavailable";
        var modifier = status === "review_required"
          ? "review"
          : status === "observation_available"
            ? "normal"
            : "unavailable";
        return '<span class="market-status market-status-' + h.escapeHtml(modifier) + '">'
          + h.escapeHtml(labels[status] || labels.unavailable)
          + '</span>';
      }

      function renderNonOilRowStatusClass(series) {
        var status = series.review_status || "unavailable";
        if (status === "review_required") return "market-row-review";
        if (status === "observation_available") return "market-row-normal";
        return "market-row-unavailable";
      }

      function renderNonOilAttributionEvidence(series, evidence) {
        if (series.review_status !== "review_required") return "";
        if (!evidence) return "";
        if (evidence.status === "available") {
          var facts = evidence.facts || [];
          if (!facts.length) return "";
          var html = '<details class="raw-evidence attribution-evidence">';
          html += '<summary>View attribution evidence</summary>';
          for (var i = 0; i < facts.length; i++) {
            var fact = facts[i];
            html += '<div class="workflow-row evidence-fact">';
            html += '<div class="workflow-label">' + h.escapeHtml(fact.source_name)
              + '<span class="workflow-role">' + h.escapeHtml(fact.metric_name) + '</span></div>';
            html += '<div class="workflow-metrics">';
            html += '<span>Factor: ' + h.escapeHtml(fact.factor_category) + '</span>';
            html += '<span>Geography: ' + h.escapeHtml(fact.geography) + '</span>';
            html += '<span>Value: ' + h.escapeHtml(h.fmtNumber(fact.value)) + ' ' + h.escapeHtml(fact.units) + '</span>';
            if (fact.observation_date) {
              html += '<span>Observation: ' + h.escapeHtml(fact.observation_date) + '</span>';
            }
            if (fact.publication_date) {
              html += '<span>Published: ' + h.escapeHtml(fact.publication_date) + '</span>';
            }
            if (fact.source_url) {
              html += '<span><a class="source-link" href="' + h.escapeHtml(fact.source_url) + '" target="_blank" rel="noopener noreferrer">' + h.escapeHtml(fact.source_url) + '</a></span>';
            }
            html += '</div></div>';
          }
          html += '</details>';
          return html;
        }
        if (evidence.status === "unavailable") {
          var html = '<div class="evidence-unavailable">';
          html += '<div class="workflow-label">Attribution evidence unavailable</div>';
          if (evidence.reason) {
            html += '<p class="summary-stat">' + h.escapeHtml(evidence.reason) + '</p>';
          }
          if (evidence.next_action) {
            html += '<p class="summary-stat">Next: ' + h.escapeHtml(evidence.next_action) + '</p>';
          }
          var resources = evidence.manual_review_resources || [];
          if (resources.length) {
            html += '<details class="raw-evidence evidence-manual">';
            html += '<summary>View manual review resources</summary>';
            for (var j = 0; j < resources.length; j++) {
              var resource = resources[j];
              html += '<div class="workflow-row attribution-review-row">';
              html += '<div class="workflow-label">' + h.escapeHtml(resource.source_name) + '</div>';
              html += '<div class="workflow-metrics">';
              html += '<span>Factors: ' + h.escapeHtml((resource.factor_categories || []).join(", ")) + '</span>';
              html += '<span>Geography: ' + h.escapeHtml(resource.geography) + '</span>';
              html += '<span>Frequency: ' + h.escapeHtml(resource.frequency) + '</span>';
              html += '<span>Units: ' + h.escapeHtml(resource.units) + '</span>';
              html += '<span>Access: ' + h.escapeHtml(resource.access_method) + '</span>';
              html += '<span><a class="source-link" href="' + h.escapeHtml(resource.source_url) + '" target="_blank" rel="noopener noreferrer">' + h.escapeHtml(resource.source_url) + '</a></span>';
              html += '</div></div>';
            }
            html += '</details>';
          }
          html += '</div>';
          return html;
        }
        return "";
      }

      function renderAttributionReviewResources(resources) {
        if (!resources || !resources.length) return "";
        var html = '<div class="attribution-review-resources">';
        html += '<details class="raw-evidence">';
        html += '<summary>View attribution review resources</summary>';
        for (var i = 0; i < resources.length; i++) {
          var resource = resources[i];
          html += '<div class="workflow-row attribution-review-row">';
          html += '<div class="workflow-label">' + h.escapeHtml(resource.source_name) + '</div>';
          html += '<div class="workflow-metrics">';
          html += '<span>Coverage: ' + h.escapeHtml((resource.coverage || []).join(", ")) + '</span>';
          html += '<span>Status: ' + h.escapeHtml(resource.status || "cataloged") + '</span>';
          html += '<span><a class="source-link" href="' + h.escapeHtml(resource.source_url) + '" target="_blank" rel="noopener noreferrer">' + h.escapeHtml(resource.source_url) + '</a></span>';
          html += '</div></div>';
        }
        html += '</details></div>';
        return html;
      }

      function renderNonOilRow(series, reviewResourcesByCommodity, evidenceByCommodity) {
        var reviewResources = reviewResourcesByCommodity[series.commodity_id] || [];
        var evidence = evidenceByCommodity[series.commodity_id] || null;
        if (series.status !== "available") {
          var unavailableLine = series.review_label
            || (series.source_class === "official_exchange"
              ? "Not available — SHFE official data not yet imported"
              : "Not available — commodity market data not yet fetched");
          return '<div class="workflow-row ' + renderNonOilRowStatusClass(series) + '">'
            + '<div class="workflow-label">' + h.escapeHtml(series.display_name) + renderNonOilReviewStatus(series) + '</div>'
            + '<div class="workflow-metrics"><span>' + h.escapeHtml(unavailableLine) + '</span></div>'
            + '</div>';
        }
        if (series.source_class === "official_exchange") {
          var auditLine = "";
          if (series.contract_roll && series.unadjusted_continuous_return != null) {
            auditLine = ' Unadjusted (audit only): '
              + h.escapeHtml(h.fmtSignedPctDecimal(series.unadjusted_continuous_return)) + '.';
          }
          var rollLine = "";
          if (series.contract_roll) {
            rollLine = '<div class="shfe-roll-note">Contract changed '
              + h.escapeHtml(series.roll_from) + " \u2192 " + h.escapeHtml(series.roll_to)
              + '. The displayed daily return uses ' + h.escapeHtml(series.selected_contract)
              + "'s own prior close; the unadjusted price gap is shown for audit only."
              + auditLine + '</div>';
          }
          return '<div class="workflow-row ' + renderNonOilRowStatusClass(series) + '">'
            + '<div class="workflow-label">' + h.escapeHtml(series.display_name)
            + renderNonOilReviewStatus(series)
            + '<span class="workflow-role">' + h.escapeHtml(series.selected_contract) + '</span></div>'
            + '<div class="workflow-metrics">'
            + '<span>Value: ' + h.escapeHtml(h.fmtNumber(series.latest_value)) + ' ' + h.escapeHtml(series.units || "CNY/tonne") + '</span>'
            + '<span>' + renderState(h.fmtSignedPctDecimal(series.daily_return), series.daily_return_state, "Daily") + '</span>'
            + renderDistribution(series.daily_distribution, "Daily")
            + '<span>' + renderState(h.fmtSignedPctDecimal(series.weekly_return), series.weekly_return_state, "Weekly") + '</span>'
            + renderDistribution(series.weekly_distribution, "Weekly")
            + '<span>Source: SHFE official data via AKShare</span>'
            + (series.latest_date ? '<span>As of ' + h.escapeHtml(series.latest_date) + '</span>' : '')
            + '</div>'
            + renderDistributionReviewNote(series)
            + renderNonOilAttributionEvidence(series, evidence)
            + renderAttributionReviewResources(reviewResources)
            + rollLine
            + '</div>';
        }
        var transitionNote = "";
        if (series.return_transition_blocked) {
          transitionNote = '<div class="shfe-roll-note">Source changed on '
            + h.escapeHtml(series.source_cutover_date)
            + '; return is withheld until same-source history is available.</div>';
        }
        return '<div class="workflow-row ' + renderNonOilRowStatusClass(series) + '">'
          + '<div class="workflow-label">' + h.escapeHtml(series.display_name) + renderNonOilReviewStatus(series) + '</div>'
          + '<div class="workflow-metrics">'
          + '<span>Value: ' + h.escapeHtml(h.fmtNumber(series.latest_value)) + '</span>'
          + '<span>' + renderState(h.fmtSignedPctDecimal(series.daily_return), series.daily_return_state, "Daily") + '</span>'
          + renderDistribution(series.daily_distribution, "Daily")
          + '<span>' + renderState(h.fmtSignedPctDecimal(series.weekly_return), series.weekly_return_state, "Weekly") + '</span>'
          + renderDistribution(series.weekly_distribution, "Weekly")
          + '<span>Source: ' + h.escapeHtml(series.source_label) + '</span>'
          + (series.latest_date ? '<span>As of ' + h.escapeHtml(series.latest_date) + '</span>' : '')
          + '</div>'
          + renderDistributionReviewNote(series)
          + renderNonOilAttributionEvidence(series, evidence)
          + renderAttributionReviewResources(reviewResources)
          + transitionNote
          + '</div>';
      }

      function renderValue(val) {
        if (val == null) return "--";
        if (typeof val === "number") return h.fmtSignedPctDecimal(val);
        return h.escapeHtml(String(val));
      }

      function renderChange(val) {
        if (val == null) return "--";
        return (val > 0 ? "+" : "") + h.fmtNumber(val);
      }

      function renderCOTHistoricalExtreme(extreme) {
        if (!extreme) return "";
        var status = extreme.status;
        if (status === "historical_high" || status === "historical_low") {
          var title = status === "historical_high"
            ? "Managed Money Net Position: Historical High"
            : "Managed Money Net Position: Historical Low";
          var html = '<div class="cot-extreme-review">';
          html += '<div class="workflow-label">' + h.escapeHtml(title)
            + '<span class="market-status market-status-review">Review required</span></div>';
          html += '<div class="workflow-metrics">';
          html += '<span>Net: ' + h.escapeHtml(String(extreme.latest_net_position)) + ' contracts</span>';
          html += '<span>History: ' + h.escapeHtml(extreme.history_start_date) + " \u2192 "
            + h.escapeHtml(extreme.history_end_date) + ' (' + h.escapeHtml(String(extreme.valid_observation_count))
            + ' reports, gaps: ' + h.escapeHtml(extreme.history_has_gaps ? "yes" : "no") + ')</span>';
          html += '<span>As of: ' + h.escapeHtml(extreme.latest_report_date) + '</span>';
          html += '</div>';
          html += '<p class="summary-stat">A historical extreme can precede a reversal; review demand, supply, and inventory. A repeated extreme may reflect persistent crowding rather than a new record.</p>';
          html += '<p class="summary-stat">Review-only evidence. No automatic attribution, directional conclusion, or trade recommendation is made.</p>';
          html += '<details class="raw-evidence"><summary>View raw evidence</summary>';
          html += '<div class="workflow-metrics">';
          html += '<span>Method: ' + h.escapeHtml(extreme.method_version) + '</span>';
          html += '<span>Contract: ' + h.escapeHtml(extreme.cftc_contract_market_code) + '</span>';
          html += '<span>Report: ' + h.escapeHtml(extreme.report_type) + ' / ' + h.escapeHtml(extreme.position_category) + '</span>';
          html += '<span>Latest net ties: ' + h.escapeHtml(String(extreme.latest_net_tie_count)) + '</span>';
          html += '</div></details></div>';
          return html;
        }
        if (status === "not_extreme") {
          return '<div class="cot-extreme-normal">'
            + '<span class="market-status market-status-normal">Normal</span>'
            + '<span>Net position is not at a historical high or low within the imported history.</span>'
            + '</div>';
        }
        var reasonLabels = {
          unsupported_contract: "Contract not supported by the versioned allowlist",
          insufficient_history: "Insufficient history — 260 valid reports over 5 calendar years required",
          missing_latest_report: "No current CFTC report available",
          missing_manager_positions: "Latest report lacks manager positions",
          stale_latest_report: "Latest report is more than 14 days old",
          contract_discontinuity: "Contract identity is discontinuous",
          report_definition_changed: "Report definition changed",
          zero_range_history: "Net position has zero range across history",
        };
        var label = reasonLabels[extreme.reason_code] || "Historical extreme review unavailable";
        return '<div class="cot-extreme-unavailable">'
          + '<span class="market-status market-status-unavailable">Unavailable</span>'
          + '<span>' + h.escapeHtml(label) + '</span>'
          + '</div>';
      }

      function renderCOTRow(commodity) {
        var norm = commodity.normalized_manager_net_position;
        var normStr = norm != null ? norm.toFixed(4) : "--";
        var flipStr = commodity.flip || "--";
        var noteHtml = "";
        if (commodity.contract_note) {
          noteHtml = '<p class="contract-note">' + h.escapeHtml(commodity.contract_note) + '</p>';
        }
        var extreme = commodity.review_evidence && commodity.review_evidence.cot_historical_extreme;
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
          + renderCOTHistoricalExtreme(extreme)
          + '</div>';
      }

      function renderUSDRow(series) {
        var reasonHtml = "";
        if (series.review_status === "unavailable" && series.review_label) {
          reasonHtml = '<span class="state-unavailable">'
            + h.escapeHtml(series.review_label)
            + '</span>';
        }
        var reviewNote = "";
        if (series.review_status === "review_required") {
          reviewNote = '<div class="distribution-review-note">'
            + h.escapeHtml(series.review_label || "")
            + '</div>';
        }
        return '<div class="workflow-row">'
          + '<div class="workflow-label">' + h.escapeHtml(series.display_name || series.series_id) + '</div>'
          + '<div class="workflow-metrics">'
          + '<span>Latest: ' + h.escapeHtml(h.fmtNumber(series.latest_value)) + '</span>'
          + '<span>Daily: ' + renderValue(series.daily_return) + '</span>'
          + renderDistribution(series.daily_distribution, "Daily")
          + '<span>Weekly: ' + renderValue(series.weekly_return) + '</span>'
          + renderDistribution(series.weekly_distribution, "Weekly")
          + reasonHtml
          + '</div>'
          + reviewNote
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
            html += '<div class="workflow-row oil-benchmark">'
              + '<div class="oil-price-line"><strong>' + h.escapeHtml(_oilDisplayName(ids[i])) + '</strong><span class="oil-price">Not available</span></div>'
              + '<div class="oil-distribution-line">'
              + renderDistribution(b.daily_distribution, "Daily")
              + renderDistribution(b.weekly_distribution, "Weekly")
              + '</div>'
              + '</div>';
            continue;
          }
          var unitStr = b.units || "$/BBL";
          html += '<div class="workflow-row oil-benchmark">'
            + '<div class="oil-price-line"><strong>' + h.escapeHtml(_oilDisplayName(ids[i])) + '</strong><span class="oil-price">'
            + h.escapeHtml(h.fmtNumber(b.latest_value)) + ' ' + h.escapeHtml(unitStr) + '</span></div>'
            + '<div class="oil-distribution-line">'
            + renderState(h.fmtSignedPctDecimal(b.daily_return), b.daily_return_state, "Daily")
            + renderDistribution(b.daily_distribution, "Daily")
            + renderState(h.fmtSignedPctDecimal(b.weekly_return), b.weekly_return_state, "Weekly")
            + renderDistribution(b.weekly_distribution, "Weekly")
            + '</div>'
            + '</div>';
        }
        return html;
      }

      function renderAttributionRows(metrics) {
        var groups = [
          {
            title: "Supply & inventory",
            roles: ["inventory", "supply_context"],
          },
          {
            title: "Demand & processing",
            roles: ["demand_proxy", "processing_activity"],
          },
        ];
        var roleLabels = {
          inventory: "Inventory",
          supply_context: "Supply context",
          processing_activity: "Processing activity",
          demand_proxy: "Demand proxy",
        };
        var html = "";
        for (var groupIndex = 0; groupIndex < groups.length; groupIndex++) {
          var group = groups[groupIndex];
          var groupMetrics = (metrics || []).filter(function (metric) {
            return group.roles.indexOf(metric.role) !== -1;
          });
          if (!groupMetrics.length) continue;
          html += '<div class="attribution-group">'
            + '<h5>' + h.escapeHtml(group.title) + '</h5>';
          for (var i = 0; i < groupMetrics.length; i++) {
            var m = groupMetrics[i];
            var roleLabel = roleLabels[m.role] || m.role;
          html += '<div class="workflow-row">'
            + '<div class="workflow-label">' + h.escapeHtml(m.display_name || m.series_id)
            + '<span class="workflow-role">' + h.escapeHtml(roleLabel) + '</span></div>'
            + '<div class="workflow-metrics">';
          if (m.status === "available") {
            var unitStr = m.units || "";
            html += '<span>Value: ' + h.escapeHtml(h.fmtNumber(m.latest_value)) + ' ' + h.escapeHtml(unitStr) + '</span>'
              + '<span>' + renderState(renderChange(m.weekly_change), m.weekly_change_state, "WoW") + '</span>';
            if (m.source_identifier) {
              html += '<span>Source: ' + h.escapeHtml(m.source_identifier) + '</span>';
            }
          } else {
            html += '<span>Not available</span>';
          }
          html += '</div></div>';
        }
          html += '</div>';
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
      html += '<p class="section-intro">WTI and Brent show observed price moves and their statistical distribution status.</p>';
      html += renderOilDistributionSummary(payload.oil_price_distribution_summary);
      if (freshness.oil_latest_observation_date) {
        html += '<p class="source-date">Latest oil observation: ' + h.escapeHtml(freshness.oil_latest_observation_date) + '</p>';
      }
      html += renderOilBenchmarkSummary(oilObservation.benchmarks || {});
      var review = payload.oil_attribution_review;
      if (review && review.status === "review_required") {
        html += '<div class="workflow-row market-row-review oil-attribution-review">';
        html += '<div class="workflow-label">Attribution inputs'
          + '<span class="market-status market-status-review">Review required</span>'
          + '</div>';
        html += '<p class="summary-stat">' + h.escapeHtml(review.label || attr.review_label || reasonLabel(attr)) + ' — WoW changes are raw context for review; no automatic attribution is made.</p>';
        html += renderAttributionRows(attr.metrics || []);
        html += '</div>';
      }
      html += '</section>';

      html += '<section class="evidence-section">';
      html += '<h3>Commodity Market Data</h3>';
      var methodData = payload.non_oil_observation || {};
      var reviewResourcesByCommodity = {};
      var attributionResources = payload.attribution_review_resources || [];
      for (var ari = 0; ari < attributionResources.length; ari++) {
        var attributionResource = attributionResources[ari];
        var commodityResources = reviewResourcesByCommodity[attributionResource.commodity_id] || [];
        commodityResources.push(attributionResource);
        reviewResourcesByCommodity[attributionResource.commodity_id] = commodityResources;
      }
      var evidenceByCommodity = payload.non_oil_attribution_evidence || {};
      var methodIds = Object.keys(methodData).sort();
      for (var ci = 0; ci < methodIds.length; ci++) {
        html += renderNonOilRow(methodData[methodIds[ci]], reviewResourcesByCommodity, evidenceByCommodity);
      }
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
      html += '<p>Commodity price attribution and USD/CPI/PPI distribution classifications are not configured. These gaps remain pending rather than being converted into a trading conclusion.</p>';
      html += '</section>';

      html += '</section>';
      body.innerHTML = html;
    },
  };
})();

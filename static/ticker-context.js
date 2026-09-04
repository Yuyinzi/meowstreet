(function () {
  var form = document.getElementById("lookupForm");
  var region = document.getElementById("resultRegion");
  var pairRegion = document.getElementById("pairRegion");
  var quantRegion = document.getElementById("quantRegion");
  var industriesPromise = null;

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function loadIndustries() {
    if (!industriesPromise) {
      industriesPromise = fetch("/api/ticker-context/industries")
        .then(function (response) {
          if (!response.ok) {
            throw new Error("industries request failed");
          }
          return response.json();
        })
        .then(function (payload) {
          return payload.industries || [];
        });
    }
    return industriesPromise;
  }

  function tagChip(cycleTag) {
    if (!cycleTag) {
      return "";
    }
    var label =
      cycleTag === "cyclical"
        ? "Cyclical"
        : cycleTag === "defensive"
          ? "Defensive"
          : "Both";
    return (
      '<span class="tag-chip tag-chip-' + escapeHtml(cycleTag) + '">' + label + "</span>"
    );
  }

  function industryPath(payload) {
    var parts = [payload.sector, payload.industry_group, payload.industry].filter(
      function (part) {
        return part;
      }
    );
    if (!parts.length) {
      return "";
    }
    var html = '<div class="result-path">' + parts.map(escapeHtml).join(" › ");
    if (payload.official_industry && payload.official_industry !== payload.industry) {
      html +=
        '<span class="official-rename">Current GICS name: ' +
        escapeHtml(payload.official_industry) +
        "</span>";
    }
    return html + "</div>";
  }

  function regimeBlock(payload) {
    var note = payload.regime_note
      ? '<div class="regime-note">' + escapeHtml(payload.regime_note) + "</div>"
      : "";
    var source =
      payload.regime_source && payload.regime_source.source_period
        ? '<span class="regime-source">Survey period ' +
          escapeHtml(payload.regime_source.source_period) +
          "</span>"
        : "";
    return (
      '<div class="regime-block">' +
      '<span class="regime-label">Regime bias: ' +
      escapeHtml(payload.regime_bias) +
      "</span>" +
      source +
      note +
      "</div>"
    );
  }

  function providerLine(payload) {
    if (!payload.provider_industry && !payload.provider_sector) {
      return "";
    }
    var parts = [];
    if (payload.provider_sector) {
      parts.push(payload.provider_sector);
    }
    if (payload.provider_industry) {
      parts.push(payload.provider_industry);
    }
    return (
      '<div class="provider-line">Provider (' +
      escapeHtml(payload.provider || "unknown") +
      "): " +
      parts.map(escapeHtml).join(" › ") +
      "</div>"
    );
  }

  function manualOverrideBlock(symbol) {
    return (
      '<div class="manual-override">' +
      '<div class="manual-override-title">Set GICS industry manually</div>' +
      '<div class="manual-override-row">' +
      '<label class="field"><span>Industry</span>' +
      '<select id="industryOverride"><option value="">Loading industries…</option></select></label>' +
      '<button type="button" class="primary-button" id="industryOverrideApply">Use this industry</button>' +
      "</div></div>"
    );
  }

  function wireManualOverride(symbol) {
    var select = document.getElementById("industryOverride");
    var apply = document.getElementById("industryOverrideApply");
    if (!select || !apply) {
      return;
    }
    loadIndustries()
      .then(function (industries) {
        var options = ['<option value="">Select an industry…</option>'].concat(
          industries.map(function (row) {
            return (
              '<option value="' +
              escapeHtml(row.industry) +
              '">' +
              escapeHtml(row.industry) +
              " (" +
              escapeHtml(row.sector) +
              ")</option>"
            );
          })
        );
        select.innerHTML = options.join("");
      })
      .catch(function () {
        select.innerHTML = '<option value="">Industry list unavailable</option>';
      });
    apply.addEventListener("click", function () {
      if (select.value) {
        lookup(symbol, select.value);
      }
    });
  }

  function renderResolved(payload) {
    region.innerHTML =
      '<div class="result-card">' +
      '<div class="result-company">' +
      escapeHtml(payload.company_name) +
      " (" +
      escapeHtml(payload.symbol) +
      ")</div>" +
      industryPath(payload) +
      tagChip(payload.cycle_tag) +
      regimeBlock(payload) +
      providerLine(payload) +
      "</div>";
  }

  function renderUnresolved(payload) {
    var warning =
      payload.status === "unmapped_industry"
        ? "Industry tag unmapped: the provider industry has no GICS mapping yet."
        : "No industry classification available from the provider.";
    region.innerHTML =
      '<div class="result-card">' +
      '<div class="result-company">' +
      escapeHtml(payload.company_name) +
      " (" +
      escapeHtml(payload.symbol) +
      ")</div>" +
      '<div class="status-warning">' +
      warning +
      "</div>" +
      providerLine(payload) +
      manualOverrideBlock(payload.symbol) +
      "</div>";
    wireManualOverride(payload.symbol);
  }

  function renderError(symbol, message) {
    region.innerHTML =
      '<div class="result-card">' +
      '<div class="result-company">' +
      escapeHtml(symbol) +
      "</div>" +
      '<div class="status-error">' +
      escapeHtml(message) +
      "</div>" +
      manualOverrideBlock(symbol) +
      "</div>";
    wireManualOverride(symbol);
  }

  function lookup(symbol, industryOverride) {
    region.innerHTML = '<div class="lookup-loading">Looking up ' + escapeHtml(symbol) + "…</div>";
    var url = "/api/ticker-context/" + encodeURIComponent(symbol);
    if (industryOverride) {
      url += "?industry=" + encodeURIComponent(industryOverride);
    }
    fetch(url)
      .then(function (response) {
        return response.json().then(function (body) {
          return { ok: response.ok, body: body };
        });
      })
      .then(function (result) {
        if (!result.ok) {
          renderError(symbol, result.body.detail || "Lookup failed.");
          return;
        }
        if (result.body.status === "resolved") {
          renderResolved(result.body);
        } else {
          renderUnresolved(result.body);
        }
      })
      .catch(function () {
        renderError(symbol, "Lookup request failed.");
      });
  }

  function fmtPct(value) {
    if (value == null) {
      return "—";
    }
    var pct = value * 100;
    var sign = pct >= 0 ? "+" : "";
    return sign + pct.toFixed(1) + "%";
  }

  function pairTypeLabel(pairType) {
    if (pairType === "intra_sector_constituent") {
      return "Intra-sector constituent";
    }
    if (pairType === "cross_sector_constituent") {
      return "Cross-sector constituent";
    }
    return "Unclassifiable";
  }

  function ratioChartSvg(dates, ratios) {
    if (!ratios.length) {
      return "";
    }
    var width = 960;
    var height = 320;
    var margin = { left: 64, right: 16, top: 16, bottom: 32 };
    var plotWidth = width - margin.left - margin.right;
    var plotHeight = height - margin.top - margin.bottom;
    var min = Math.min.apply(null, ratios);
    var max = Math.max.apply(null, ratios);
    var pad = (max - min) * 0.08 || Math.abs(max) * 0.02 || 0.01;
    min -= pad;
    max += pad;
    function xAt(index) {
      if (ratios.length === 1) {
        return margin.left + plotWidth / 2;
      }
      return margin.left + (index / (ratios.length - 1)) * plotWidth;
    }
    function yAt(value) {
      return margin.top + plotHeight - ((value - min) / (max - min)) * plotHeight;
    }
    var gridlines = "";
    for (var i = 0; i <= 4; i += 1) {
      var value = min + ((max - min) * i) / 4;
      var y = yAt(value);
      gridlines +=
        '<line class="ratio-chart-grid" x1="' + margin.left + '" y1="' + y.toFixed(1) +
        '" x2="' + (width - margin.right) + '" y2="' + y.toFixed(1) + '"></line>' +
        '<text class="ratio-chart-axis-label" x="' + (margin.left - 8) +
        '" y="' + (y + 4).toFixed(1) + '" text-anchor="end">' +
        value.toFixed(2) + "</text>";
    }
    var points = ratios
      .map(function (ratio, index) {
        return xAt(index).toFixed(1) + "," + yAt(ratio).toFixed(1);
      })
      .join(" ");
    var refY = yAt(ratios[0]);
    var dateLabels =
      '<text class="ratio-chart-axis-label" x="' + margin.left + '" y="' +
      (height - 8) + '" text-anchor="start">' + escapeHtml(dates[0]) + "</text>" +
      '<text class="ratio-chart-axis-label" x="' + (width - margin.right) + '" y="' +
      (height - 8) + '" text-anchor="end">' + escapeHtml(dates[dates.length - 1]) + "</text>";
    return (
      '<svg class="ratio-chart" viewBox="0 0 ' + width + " " + height +
      '" role="img" aria-label="Long/short price ratio chart">' +
      gridlines +
      '<line class="ratio-chart-reference" x1="' + margin.left + '" y1="' + refY.toFixed(1) +
      '" x2="' + (width - margin.right) + '" y2="' + refY.toFixed(1) + '"></line>' +
      '<polyline class="ratio-chart-line" points="' + points + '"></polyline>' +
      dateLabels +
      "</svg>"
    );
  }

  function pairLegRow(ctx, leg) {
    var path = [ctx.sector, ctx.industry_group, ctx.industry]
      .filter(function (part) {
        return part;
      })
      .join(" › ");
    var pathHtml;
    if (path) {
      pathHtml = escapeHtml(path);
    } else if (ctx.provider_industry) {
      pathHtml =
        escapeHtml(ctx.provider_industry) +
        ' <span class="pair-leg-unmapped">(provider industry, unmapped)</span>';
    } else {
      pathHtml = '<span class="pair-leg-unmapped">industry unresolved</span>';
    }
    return (
      '<div class="pair-leg-row">' +
      '<span class="pair-leg-symbol">' + escapeHtml(ctx.symbol) +
      ' <span class="pair-leg-side">' + leg + "</span></span>" +
      '<span class="pair-leg-path">' + pathHtml + "</span>" +
      tagChip(ctx.cycle_tag) +
      "</div>"
    );
  }

  function renderPair(payload) {
    var longCtx = payload.long;
    var shortCtx = payload.short;
    var pair = payload.pair;
    var out = payload.outperformance;
    var outClass = out.outperformance >= 0 ? "positive" : "negative";
    var riskChips = pair.retained_risks
      .map(function (risk) {
        return '<span class="risk-chip">' + escapeHtml(risk) + " risk</span>";
      })
      .join("");
    var missingNote = pair.missing && pair.missing.length
      ? '<div class="status-warning">Industry context unresolved for ' +
        pair.missing.map(escapeHtml).join(", ") +
        " — set the industry manually to classify this pair.</div>"
      : "";
    pairRegion.innerHTML =
      '<div class="pair-card">' +
      '<div class="pair-head">' +
      escapeHtml(longCtx.symbol) + " (long)" +
      '<span class="pair-vs">vs</span>' +
      escapeHtml(shortCtx.symbol) + " (short)" +
      "</div>" +
      '<div class="pair-legs">' +
      pairLegRow(longCtx, "long") +
      pairLegRow(shortCtx, "short") +
      "</div>" +
      '<div class="pair-badges">' +
      '<span class="pair-type-chip pair-type-' + escapeHtml(pair.pair_type) + '">' +
      pairTypeLabel(pair.pair_type) + "</span>" +
      riskChips +
      "</div>" +
      missingNote +
      '<div class="pair-outperformance">' +
      "Long " + fmtPct(out.long_return) +
      " vs short " + fmtPct(out.short_return) +
      ' → <span class="' + outClass + '">outperformance ' + fmtPct(out.outperformance) +
      "</span></div>" +
      '<div class="pair-window-note">Equal-weight over ' + out.sessions +
      " trading sessions, " + escapeHtml(out.start_date) + " → " + escapeHtml(out.end_date) +
      "</div>" +
      ratioChartSvg(payload.series.dates, payload.series.ratio) +
      '<div class="ratio-chart-caption">Ratio = long price ÷ short price, over the last ' +
      out.sessions + " trading sessions.</div>" +
      '<div class="ratio-chart-caption">Dashed line = ratio at window start; upward slope = long outperforming.</div>' +
      "</div>";
  }

  function renderPairError(message) {
    pairRegion.innerHTML =
      '<div class="pair-card"><div class="status-error">' +
      escapeHtml(message) +
      "</div></div>";
  }

  function fmtNum(value, digits) {
    if (value == null) {
      return "—";
    }
    return Number(value).toFixed(digits == null ? 2 : digits);
  }

  function fmtDollarsCompact(value) {
    if (value == null) {
      return "—";
    }
    var num = Number(value);
    if (num >= 1e12) {
      return "$" + (num / 1e12).toFixed(2) + "T";
    }
    if (num >= 1e9) {
      return "$" + (num / 1e9).toFixed(2) + "B";
    }
    if (num >= 1e6) {
      return "$" + (num / 1e6).toFixed(2) + "M";
    }
    return "$" + num.toLocaleString("en-US", { maximumFractionDigits: 0 });
  }

  function quantStatusChip(status) {
    var tone = status || "insufficient_data";
    return '<span class="quant-chip quant-chip-' + escapeHtml(tone) + '">' + escapeHtml(tone.replace(/_/g, " ")) + "</span>";
  }

  function fiscalYearLabel(fiscalYearEnd) {
    if (!fiscalYearEnd) {
      return "";
    }
    return "FY" + String(fiscalYearEnd).split("-")[0];
  }

  function _estimateConsensusText(consensus) {
    if (!consensus || consensus.status !== "ok") {
      return "insufficient data";
    }
    return fiscalYearLabel(consensus.fiscal_year_end) + ", " + consensus.analyst_count +
      " analysts with EPS estimates, avg " + fmtNum(consensus.avg) + ", range " + fmtNum(consensus.low) +
      "–" + fmtNum(consensus.high) + ", " + consensus.skew + " skew";
  }

  function _estimateRevisionText(trend) {
    if (!trend) {
      return "accumulating";
    }
    if (trend.status === "accumulating") {
      return "accumulating (" + trend.sample_snapshots + " snapshots)";
    }
    if (trend.status === "ok") {
      return trend.increases + " up / " + trend.decreases + " down (" + trend.window_days + "d)";
    }
    return "unavailable";
  }

  function quantToneChip(label, tone) {
    return '<span class="quant-chip quant-chip-' + escapeHtml(tone) + '">' + escapeHtml(label) + "</span>";
  }

  function skewChip(skew) {
    var tone = skew === "positive" ? "within" : (skew === "negative" ? "warning" : "info");
    return quantToneChip((skew || "unknown") + " skew", tone);
  }

  function revisionChip(trend) {
    if (!trend || trend.status === "accumulating") {
      return quantToneChip("revisions accumulating", "insufficient_data");
    }
    if (trend.status !== "ok") {
      return quantToneChip("revisions unavailable", "insufficient_data");
    }
    var tone = trend.direction === "up" ? "within" : (trend.direction === "down" ? "warning" : "info");
    return quantToneChip(
      "revisions " + trend.direction + " (" + trend.increases + " up / " + trend.decreases + " down, " + trend.window_days + "d)",
      tone
    );
  }

  function estimateConsensusLineHtml(payload) {
    var consensus = payload.estimate_consensus || {};
    if (consensus.status !== "ok") {
      return "";
    }
    var trend = payload.estimate_revision_trend || {};
    return (
      '<div class="quant-conclusion">' +
      '<div class="quant-conclusion-head">' +
      '<span class="quant-conclusion-title">Estimate Consensus — ' + escapeHtml(fiscalYearLabel(consensus.fiscal_year_end)) + "</span>" +
      '<span class="quant-conclusion-chips">' + skewChip(consensus.skew) + revisionChip(trend) + "</span>" +
      "</div>" +
      '<div class="quant-grid">' +
      '<div class="quant-stat"><div class="quant-stat-value">' + escapeHtml(consensus.analyst_count) +
      '</div><div class="quant-stat-label">Analysts with EPS estimates</div></div>' +
      '<div class="quant-stat"><div class="quant-stat-value">' + fmtNum(consensus.avg) +
      '</div><div class="quant-stat-label">Avg EPS estimate</div></div>' +
      '<div class="quant-stat"><div class="quant-stat-value">' + fmtNum(consensus.low) + "–" + fmtNum(consensus.high) +
      '</div><div class="quant-stat-label">Estimate range</div></div>' +
      "</div>" +
      "</div>"
    );
  }

  function quantValuationHtml(payload) {
    var valuation = payload.valuation || {};
    return (
      '<div class="quant-grid">' +
      '<div class="quant-stat"><div class="quant-stat-value">' + fmtNum(valuation.forward_pe) +
      '</div><div class="quant-stat-label">Forward PE</div></div>' +
      '<div class="quant-stat"><div class="quant-stat-value">' + fmtNum(valuation.forward_eps) +
      '</div><div class="quant-stat-label">Forward EPS</div></div>' +
      '<div class="quant-stat"><div class="quant-stat-value">' + fmtNum(valuation.trailing_eps) +
      '</div><div class="quant-stat-label">Trailing EPS</div></div>' +
      '<div class="quant-stat"><div class="quant-stat-value">' + fmtDollarsCompact(valuation.market_cap) +
      '</div><div class="quant-stat-label">Market Cap</div></div>' +
      "</div>" +
      estimateConsensusLineHtml(payload)
    );
  }

  function _ratioValueByKey(payload, key) {
    var ratios = (payload.backward_ratios && payload.backward_ratios.ratios) || [];
    for (var i = 0; i < ratios.length; i++) {
      if (ratios[i].key === key) {
        return ratios[i].value;
      }
    }
    return null;
  }

  var peerCompareCache = null;
  var latestQuantPayload = null;
  var quantRequestId = 0;

  function _peerCompareRows(payload) {
    var peer = payload.peer || {};
    var valuation = payload.valuation || {};
    var shortChecks = payload.short_checks || {};
    return [
      { label: "Forward PE", main: valuation.forward_pe, peer: peer.forward_pe },
      { label: "Forward EPS", main: valuation.forward_eps, peer: peer.forward_eps },
      { label: "Trailing EPS", main: valuation.trailing_eps, peer: peer.trailing_eps },
      { label: "Market cap", main: valuation.market_cap, peer: peer.market_cap, fmt: fmtDollarsCompact },
      { label: "Short % of float", main: shortChecks.short_percent_of_float, peer: peer.short_percent_of_float, fmt: fmtPct },
      { label: "Dividend yield", main: shortChecks.dividend && shortChecks.dividend.yield, peer: peer.dividend_yield, fmt: fmtPct },
      { label: "Debt / equity", main: _ratioValueByKey(payload, "debt_to_equity"), peer: peer.debt_to_equity == null ? null : peer.debt_to_equity / 100 },
      { label: "Current ratio", main: _ratioValueByKey(payload, "current_ratio"), peer: peer.current_ratio },
    ];
  }

  function _compareCell(value, fmt, compareClass, arrow) {
    var text = value == null ? "—" : (fmt || fmtNum)(value);
    return '<td class="num ' + compareClass + '">' + text + (arrow || "") + "</td>";
  }

  function peerCompareTableHtml(payload) {
    var peer = payload.peer || {};
    var diff = peer.pe_differential;
    var diffText = "—";
    if (diff != null) {
      var premiumPct = Math.round((diff - 1) * 100);
      diffText = fmtNum(diff) + "× (" + (premiumPct >= 0 ? "+" : "") + premiumPct + "%)";
    }
    var body = "";
    _peerCompareRows(payload).forEach(function (row, index) {
      var peerClass = "";
      var arrow = "";
      if (typeof row.main === "number" && typeof row.peer === "number" && row.main !== row.peer) {
        peerClass = row.peer > row.main ? "peer-up" : "peer-down";
        arrow = row.peer > row.main ? " ▲" : " ▼";
      }
      body +=
        "<tr><td>" + escapeHtml(row.label) + "</td>" +
        _compareCell(row.main, row.fmt, "") +
        _compareCell(row.peer, row.fmt, peerClass, arrow) +
        "</tr>";
      if (index === 0) {
        body +=
          "<tr><td>PE differential</td>" +
          '<td class="num">—</td>' +
          '<td class="num">' + diffText + "</td></tr>";
      }
    });
    return (
      '<table class="quant-table"><thead><tr>' +
      "<th>Metric</th>" +
      '<th class="num">' + escapeHtml(payload.symbol) + "</th>" +
      '<th class="num">' + escapeHtml(peer.symbol || "") + "</th>" +
      "</tr></thead><tbody>" + body + "</tbody></table>"
    );
  }

  function closePeerComparePanel() {
    var shell = document.querySelector(".workflow-shell");
    var panel = document.getElementById("peerComparePanel");
    if (shell) {
      shell.classList.remove("panel-open");
    }
    if (panel) {
      panel.innerHTML = "";
    }
  }

  function openPeerComparePanel(payload) {
    var shell = document.querySelector(".workflow-shell");
    var panel = document.getElementById("peerComparePanel");
    if (!shell || !panel) {
      return;
    }
    var peer = payload.peer || {};
    panel.innerHTML =
      '<div class="detail-panel-head">' +
      '<h2 class="detail-panel-title">' + escapeHtml(payload.symbol) +
      " vs " + escapeHtml(peer.symbol || "") + "</h2>" +
      '<button type="button" class="detail-panel-close" id="peerCompareClose" aria-label="Close comparison">×</button>' +
      "</div>" +
      '<div class="detail-panel-body">' +
      peerCompareTableHtml(payload) +
      "</div>";
    shell.classList.add("panel-open");
    var closeButton = document.getElementById("peerCompareClose");
    if (closeButton) {
      closeButton.addEventListener("click", closePeerComparePanel);
    }
  }

  function quantShortChecksHtml(shortChecks) {
    var days = shortChecks.days_to_cover || {};
    var dividend = shortChecks.dividend || {};
    var dividendNote = dividend.yield == null && dividend.note
      ? '<div class="quant-inline-note">' + escapeHtml(dividend.note) + "</div>"
      : "";
    var dividendValue = dividend.yield == null ? "Not reported" : fmtPct(dividend.yield);
    return (
      '<div class="quant-grid">' +
      '<div class="quant-stat"><div class="quant-stat-value">' + fmtPct(shortChecks.short_percent_of_float) +
      '</div><div class="quant-stat-label">Short % of float</div></div>' +
      '<div class="quant-stat"><div class="quant-stat-value">' + fmtNum(days.value) +
      ' ' + quantStatusChip(days.status) +
      '</div><div class="quant-stat-label">Days to cover</div></div>' +
      '<div class="quant-stat"><div class="quant-stat-value">' + dividendValue +
      dividendNote + '</div><div class="quant-stat-label">Dividend yield</div></div>' +
      "</div>"
    );
  }

  function quantRatioLabel(key) {
    var labels = {
      debt_to_equity: "Debt / equity",
      current_ratio: "Current ratio",
      interest_coverage: "Interest coverage",
      working_capital_to_total_assets: "Working capital / assets",
      quick_ratio: "Quick ratio",
      return_on_equity: "Return on equity",
      return_on_assets: "Return on assets",
      book_value: "Book value",
      fcf_yield: "FCF yield",
      price_to_fcf: "Price / FCF",
      ev_to_ebitda: "EV / EBITDA",
      ev_to_ebit: "EV / EBIT",
    };
    return labels[key] || key.replace(/_/g, " ");
  }

  function quantBackwardRatiosHtml(backwardRatios) {
    var ratios = backwardRatios.ratios || [];
    var rows = ratios.map(function (ratio) {
      var note = ratio.value == null && ratio.note
        ? '<div class="quant-inline-note">' + escapeHtml(ratio.note) + "</div>"
        : "";
      var valueCell = ratio.value == null
        ? '<td class="muted-cell">—' + note + "</td>"
        : '<td class="num">' + fmtNum(ratio.value) + "</td>";
      return (
        "<tr><td>" + escapeHtml(quantRatioLabel(ratio.key)) + "</td>" +
        valueCell +
        "<td>" + quantStatusChip(ratio.status) + "</td></tr>"
      );
    }).join("");
    return (
      '<table class="quant-table"><thead><tr>' +
      "<th>Ratio</th><th class=\"num\">Value</th><th>Status</th>" +
      "</tr></thead><tbody>" + rows + "</tbody></table>"
    );
  }

  function analystRatingsHtml(ratings) {
    if (!ratings || ratings.status !== "ok") {
      return '<p class="section-note">Analyst ratings insufficient data.</p>';
    }
    var dist = ratings.distribution || {};
    var target = ratings.price_target || {};
    var pvt = ratings.price_vs_target;
    var targetText = target.avg == null ? "—" : "$" + fmtNum(target.avg);
    var upsideText = "—";
    if (pvt && pvt.upside_pct != null) {
      var pct = Math.round(pvt.upside_pct);
      upsideText = (pct >= 0 ? "+" : "") + pct + "% vs price $" + fmtNum(pvt.price);
    }
    var trend = ratings.monthly_trend || [];
    var trendRows = trend.slice(-6).map(function (entry) {
      return (
        "<tr><td>" + escapeHtml(entry.date) + "</td>" +
        '<td class="num">' + escapeHtml(entry.buy_total) + "</td>" +
        '<td class="num">' + escapeHtml(entry.hold) + "</td>" +
        '<td class="num">' + escapeHtml(entry.sell_total) + "</td>" +
        '<td class="num">' + escapeHtml(entry.total == null ? "—" : entry.total) + "</td></tr>"
      );
    }).join("");
    var trendTable = trendRows
      ? '<table class="quant-table"><thead><tr>' +
        "<th>Month</th><th class=\"num\">Buy</th><th class=\"num\">Hold</th>" +
        "<th class=\"num\">Sell</th><th class=\"num\">Total</th>" +
        "</tr></thead><tbody>" + trendRows + "</tbody></table>"
      : "";
    return (
      '<div class="quant-grid">' +
      '<div class="quant-stat"><div class="quant-stat-value">' + escapeHtml(ratings.consensus || "—") +
      '</div><div class="quant-stat-label">Consensus (' + escapeHtml(ratings.analyst_count) + " analysts)</div></div>" +
      '<div class="quant-stat"><div class="quant-stat-value">' +
      escapeHtml(ratings.buy_total) + " / " + escapeHtml(ratings.distribution.hold) + " / " + escapeHtml(ratings.sell_total) +
      '</div><div class="quant-stat-label">Buy / Hold / Sell</div></div>' +
      '<div class="quant-stat"><div class="quant-stat-value">' + targetText +
      '</div><div class="quant-stat-label">Avg price target (' + escapeHtml(target.count == null ? "—" : target.count) + ")</div></div>" +
      '<div class="quant-stat"><div class="quant-stat-value">' + escapeHtml(upsideText) +
      '</div><div class="quant-stat-label">Target vs current price</div></div>' +
      "</div>" +
      '<div class="quant-line">Upgrade room: ' + quantStatusChip(ratings.upgrade_room) +
      " · Downgrade room: " + quantStatusChip(ratings.downgrade_room) + "</div>" +
      (trendTable ? '<div class="quant-section-title">Ratings trend (recent months)</div>' + trendTable : "")
    );
  }

  function _calWeekdayIndex(dateStr) {
    var parts = dateStr.split("-");
    var dow = new Date(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2])).getDay();
    return (dow + 6) % 7;
  }

  function _calCellHtml(day, filings, center, sigma) {
    var ret = day["return"];
    var absSigma = sigma > 0 ? Math.abs(ret - center) / sigma : 0;
    var tone = "";
    if (absSigma >= 2) {
      tone = ret >= 0 ? " cal-up-strong" : " cal-down-strong";
    } else if (absSigma >= 1) {
      tone = ret >= 0 ? " cal-up" : " cal-down";
    }
    var filing = filings[day.date] ? " cal-filing" : "";
    var retText = (ret >= 0 ? "+" : "") + (ret * 100).toFixed(1) + "%";
    return (
      '<div class="cal-cell' + tone + filing + '" title="' + escapeHtml(day.date) + '">' +
      '<span class="cal-day">' + escapeHtml(day.date.slice(8)) + "</span>" +
      '<span class="cal-ret">' + retText + "</span></div>"
    );
  }

  function _calMonthHtml(monthKey, days, filings, center, sigma) {
    var cells = "";
    var offset = _calWeekdayIndex(days[0].date);
    for (var i = 0; i < offset; i++) {
      cells += '<div class="cal-cell cal-empty"></div>';
    }
    days.forEach(function (day) {
      cells += _calCellHtml(day, filings, center, sigma);
    });
    return (
      '<div class="cal-month"><div class="cal-month-title">' + escapeHtml(monthKey) + "</div>" +
      '<div class="cal-weekdays"><span>M</span><span>T</span><span>W</span><span>T</span><span>F</span></div>' +
      '<div class="cal-grid">' + cells + "</div></div>"
    );
  }

  var catalystCalendarData = null;

  function _calIsoShift(iso, deltaDays) {
    var parts = iso.split("-");
    var d = new Date(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2]));
    d.setDate(d.getDate() + deltaDays);
    var month = d.getMonth() + 1;
    var day = d.getDate();
    return (
      d.getFullYear() + "-" +
      (month < 10 ? "0" : "") + month + "-" +
      (day < 10 ? "0" : "") + day
    );
  }

  function _calDayDiff(start, end) {
    return Math.round((new Date(end + "T00:00:00") - new Date(start + "T00:00:00")) / 86400000);
  }

  function _calRangeHtml(calendar, start, end) {
    var filings = {};
    (calendar.filing_dates || []).forEach(function (filingDate) {
      filings[filingDate] = true;
    });
    var center = calendar.mean_return || 0;
    var sigma = calendar.stdev || 0;
    var days = (calendar.days || []).filter(function (day) {
      return day.date >= start && day.date <= end;
    });
    if (!days.length) {
      return '<p class="section-note">No trading days in this range.</p>';
    }
    var byMonth = {};
    var monthOrder = [];
    days.forEach(function (day) {
      var monthKey = day.date.slice(0, 7);
      if (!byMonth[monthKey]) {
        byMonth[monthKey] = [];
        monthOrder.push(monthKey);
      }
      byMonth[monthKey].push(day);
    });
    var html = "";
    var currentYear = null;
    monthOrder.forEach(function (monthKey) {
      var year = monthKey.slice(0, 4);
      if (year !== currentYear) {
        currentYear = year;
        html += '<div class="cal-year-title">' + escapeHtml(year) + "</div>";
      }
      html += _calMonthHtml(monthKey, byMonth[monthKey], filings, center, sigma);
    });
    return html;
  }

  function catalystCalendarHtml(calendar) {
    if (!calendar || !(calendar.days || []).length) {
      return "";
    }
    catalystCalendarData = calendar;
    return (
      '<div class="cal-controls">' +
      '<input type="date" id="calRangeStart" aria-label="Calendar range start">' +
      '<span class="cal-controls-sep">→</span>' +
      '<input type="date" id="calRangeEnd" aria-label="Calendar range end">' +
      '<span class="cal-controls-note">max 1 year</span>' +
      "</div>" +
      '<div class="cal-legend">Red up / green down · darker = ≥1σ / ≥2σ move · bordered day = 8-K filing</div>' +
      '<div id="catalystCalRange"></div>'
    );
  }

  function wireCatalystCalendar() {
    var container = document.getElementById("catalystCalRange");
    var startInput = document.getElementById("calRangeStart");
    var endInput = document.getElementById("calRangeEnd");
    if (!catalystCalendarData || !container || !startInput || !endInput) {
      return;
    }
    var days = catalystCalendarData.days.slice().sort(function (a, b) {
      return a.date < b.date ? -1 : 1;
    });
    var minDate = days[0].date;
    var maxDate = days[days.length - 1].date;
    startInput.min = minDate;
    startInput.max = maxDate;
    endInput.min = minDate;
    endInput.max = maxDate;
    endInput.value = maxDate;
    var defaultStart = _calIsoShift(maxDate, -30);
    startInput.value = defaultStart < minDate ? minDate : defaultStart;
    function renderRange() {
      var start = startInput.value;
      var end = endInput.value;
      if (!start || !end || start > end) {
        container.innerHTML = "";
        return;
      }
      container.innerHTML = _calRangeHtml(catalystCalendarData, start, end);
    }
    startInput.addEventListener("change", function () {
      if (startInput.value && endInput.value && _calDayDiff(startInput.value, endInput.value) > 365) {
        endInput.value = _calIsoShift(startInput.value, 365);
        if (endInput.value > maxDate) {
          endInput.value = maxDate;
        }
      }
      renderRange();
    });
    endInput.addEventListener("change", function () {
      if (startInput.value && endInput.value && _calDayDiff(startInput.value, endInput.value) > 365) {
        startInput.value = _calIsoShift(endInput.value, -365);
        if (startInput.value < minDate) {
          startInput.value = minDate;
        }
      }
      renderRange();
    });
    renderRange();
  }

  function loadCatalystAsync(symbol) {
    var region = document.getElementById("catalystAsyncRegion");
    if (!region) {
      return;
    }
    fetch("/api/ticker-quant/" + encodeURIComponent(symbol) + "/catalyst")
      .then(function (response) {
        if (!response.ok) {
          throw new Error("catalyst request failed");
        }
        return response.json();
      })
      .then(function (activity) {
        if (!latestQuantPayload || latestQuantPayload.symbol !== symbol) {
          return;
        }
        region.innerHTML = catalystActivityHtml(activity);
        wireCatalystCalendar();
        latestQuantPayload.catalyst_activity = activity;
      })
      .catch(function () {
        if (!latestQuantPayload || latestQuantPayload.symbol !== symbol) {
          return;
        }
        region.innerHTML = '<p class="section-note">Catalyst activity unavailable.</p>';
      });
  }

  function catalystActivityHtml(activity) {
    catalystCalendarData = null;
    if (!activity || activity.status !== "ok") {
      return '<p class="section-note">Catalyst activity insufficient data.</p>';
    }
    var freq = activity.filing_frequency || {};
    var moves = activity.large_moves || {};
    var freqHtml = "";
    if (freq.status === "ok") {
      freqHtml =
        '<div class="quant-grid">' +
        '<div class="quant-stat"><div class="quant-stat-value">' + escapeHtml(freq.total) +
        '</div><div class="quant-stat-label">8-K filings (' + escapeHtml(freq.window_months) + " mo)</div></div>" +
        '<div class="quant-stat"><div class="quant-stat-value">' + escapeHtml(freq.per_month) +
        '</div><div class="quant-stat-label">Filings / month</div></div>' +
        '<div class="quant-stat"><div class="quant-stat-value">' +
        escapeHtml(freq.earnings) + " / " + escapeHtml(freq.non_earnings) +
        '</div><div class="quant-stat-label">Earnings / non-earnings</div></div>' +
        '<div class="quant-stat"><div class="quant-stat-value">' +
        (freq.non_earnings_per_month == null ? "—" : escapeHtml(freq.non_earnings_per_month)) +
        '</div><div class="quant-stat-label">Non-earnings / month</div></div>' +
        "</div>";
    }
    var movesHtml = "";
    if (moves.status === "ok") {
      movesHtml =
        '<div class="quant-line">&gt;1σ move days: ' + escapeHtml((moves.moves || []).length) +
        " of " + escapeHtml(moves.sample_days) + " (σ = " + fmtPct(moves.stdev) + ")</div>" +
        catalystCalendarHtml(activity.calendar);
    }
    return freqHtml + movesHtml;
  }

  function quantPeerInputHtml() {
    return (
      '<span class="quant-peer-compact">' +
      '<input type="text" id="quantPeerInput" class="quant-peer-input" placeholder="Peer e.g. AMD" autocomplete="off" aria-label="Peer symbol" />' +
      '<button type="button" class="primary-button quant-peer-apply" id="quantPeerApply">Compare peer</button>' +
      "</span>"
    );
  }

  function wireQuantPeer(symbol) {
    var input = document.getElementById("quantPeerInput");
    var apply = document.getElementById("quantPeerApply");
    if (!input || !apply) {
      return;
    }
    apply.addEventListener("click", function () {
      var peer = input.value.trim();
      if (!peer) {
        return;
      }
      var peerRequestId = quantRequestId;
      apply.disabled = true;
      apply.textContent = "Comparing…";
      var url = "/api/ticker-quant/" + encodeURIComponent(symbol) + "?peer=" + encodeURIComponent(peer);
      fetch(url)
        .then(function (response) {
          return response.json().then(function (body) {
            return { ok: response.ok, body: body };
          });
        })
        .then(function (result) {
          if (peerRequestId !== quantRequestId) {
            return;
          }
          apply.disabled = false;
          apply.textContent = "Compare peer";
          var resultRegion = document.getElementById("quantPeerResult");
          if (!resultRegion) {
            return;
          }
          if (!result.ok) {
            resultRegion.innerHTML =
              '<div class="status-error">' +
              escapeHtml(result.body.detail || "Peer comparison failed.") +
              "</div>";
            return;
          }
          if (result.body.peer && result.body.peer.error) {
            resultRegion.innerHTML =
              '<div class="status-warning">Peer: ' + escapeHtml(result.body.peer.error) + "</div>";
            return;
          }
          peerCompareCache = result.body;
          openPeerComparePanel(result.body);
          resultRegion.innerHTML =
            '<div class="quant-peer-summary">Comparing with <strong>' +
            escapeHtml((result.body.peer && result.body.peer.symbol) || peer) +
            "</strong> — details in the right panel." +
            '<button type="button" class="quant-peer-reopen" id="quantPeerReopen">Reopen comparison</button></div>';
          var reopen = document.getElementById("quantPeerReopen");
          if (reopen) {
            reopen.addEventListener("click", function () {
              if (peerCompareCache) {
                openPeerComparePanel(peerCompareCache);
              }
            });
          }
        })
        .catch(function () {
          if (peerRequestId !== quantRequestId) {
            return;
          }
          apply.disabled = false;
          apply.textContent = "Compare peer";
          var resultRegion = document.getElementById("quantPeerResult");
          if (resultRegion) {
            resultRegion.innerHTML =
              '<div class="status-error">Peer comparison request failed.</div>';
          }
        });
    });
  }

  function renderQuant(payload) {
    closePeerComparePanel();
    peerCompareCache = null;
    latestQuantPayload = payload;
    var cacheLine = payload.cache
      ? '<div class="quant-sub">Provider: ' + escapeHtml(payload.provider) +
        " · " + escapeHtml(payload.cache) +
        (payload.fetched_at ? " · " + escapeHtml(payload.fetched_at) : "") +
        "</div>"
      : "";
    quantRegion.innerHTML =
      '<div class="quant-card">' +
      '<div class="quant-head"><span>Quant Context — ' + escapeHtml(payload.symbol) + '</span>' +
      '<span class="quant-head-actions">' +
      quantPeerInputHtml() +
      '<button type="button" class="quant-ai-button" id="quantRefresh" aria-label="Refresh quant context">Refresh</button>' +
      '<button type="button" class="quant-ai-button" id="quantAiInterpret" aria-label="Ask AI to interpret this quant context">' +
      '<img src="/static/cat-icon.svg" alt="" aria-hidden="true" /> Ask AI</button>' +
      "</span></div>" +
      cacheLine +
      '<div id="quantRefreshStatus"></div>' +
      '<div id="quantPeerResult"></div>' +
      '<div class="quant-section"><div class="quant-section-title">Valuation</div>' +
      quantValuationHtml(payload) +
      "</div>" +
      '<div class="quant-section"><div class="quant-section-title">Short checks</div>' +
      quantShortChecksHtml(payload.short_checks) +
      "</div>" +
      '<div class="quant-section"><div class="quant-section-title">Backward ratios</div>' +
      quantBackwardRatiosHtml(payload.backward_ratios) +
      "</div>" +
      '<div class="quant-section"><div class="quant-section-title">Analyst ratings</div>' +
      analystRatingsHtml(payload.analyst_ratings) +
      "</div>" +
      '<div class="quant-section"><div class="quant-section-title">Catalyst activity (8-K filings)</div>' +
      '<div id="catalystAsyncRegion"><p class="section-note">Loading catalyst activity…</p></div>' +
      "</div>" +
      "</div>";
    wireQuantRefresh(payload.symbol);
    wireQuantPeer(payload.symbol);
    loadCatalystAsync(payload.symbol);
    var aiButton = document.getElementById("quantAiInterpret");
    if (aiButton) {
      aiButton.addEventListener("click", function () {
        if (latestQuantPayload) {
          askAssistant(latestQuantPayload);
        }
      });
    }
  }

  function renderQuantError(message) {
    closePeerComparePanel();
    peerCompareCache = null;
    latestQuantPayload = null;
    quantRegion.innerHTML =
      '<div class="quant-card"><div class="status-error">' + escapeHtml(message) + "</div></div>";
  }

  function wireQuantRefresh(symbol) {
    var button = document.getElementById("quantRefresh");
    var status = document.getElementById("quantRefreshStatus");
    var peerApply = document.getElementById("quantPeerApply");
    if (!button) {
      return;
    }
    button.addEventListener("click", function () {
      var requestId = ++quantRequestId;
      button.disabled = true;
      button.textContent = "Refreshing…";
      if (peerApply) {
        peerApply.disabled = true;
      }
      if (status) {
        status.innerHTML = "";
      }
      fetch("/api/ticker-quant/" + encodeURIComponent(symbol) + "?refresh=true")
        .then(function (response) {
          return response.json().then(function (body) {
            return { ok: response.ok, body: body };
          });
        })
        .then(function (result) {
          if (requestId !== quantRequestId) {
            return;
          }
          if (!result.ok) {
            throw new Error(result.body.detail || "Quant context refresh failed.");
          }
          renderQuant(result.body);
        })
        .catch(function (error) {
          if (requestId !== quantRequestId) {
            return;
          }
          button.disabled = false;
          button.textContent = "Refresh";
          if (peerApply) {
            peerApply.disabled = false;
          }
          if (status) {
            status.innerHTML = '<div class="status-error">' + escapeHtml(error.message) + "</div>";
          }
        });
    });
  }

  function quantContextText(payload) {
    var valuation = payload.valuation || {};
    var shortChecks = payload.short_checks || {};
    var days = shortChecks.days_to_cover || {};
    var dividend = shortChecks.dividend || {};
    var lines = [
      "The user is viewing a ticker quant context result on the Meowstreet ticker context page. Explain the deterministic data without making a trade decision:",
      "Symbol: " + payload.symbol,
      "Valuation: forward PE " + fmtNum(valuation.forward_pe) +
        ", forward EPS " + fmtNum(valuation.forward_eps) +
        ", trailing EPS " + fmtNum(valuation.trailing_eps) +
        ", market cap " + fmtDollarsCompact(valuation.market_cap),
      "Estimate consensus: " + _estimateConsensusText(payload.estimate_consensus) +
        "; revision trend: " + _estimateRevisionText(payload.estimate_revision_trend),
      "Short checks: short % of float " + fmtPct(shortChecks.short_percent_of_float) +
        ", days to cover " + fmtNum(days.value) + " (" + (days.status || "insufficient_data") +
        "), dividend yield " + fmtPct(dividend.yield),
    ];
    if (payload.peer) {
      lines.push("Peer: " + (payload.peer.symbol || "unknown") +
        ", forward PE " + fmtNum(payload.peer.forward_pe) +
        ", PE differential " + (payload.peer.pe_differential == null ? "—" : fmtNum(payload.peer.pe_differential) + "×"));
    }
    lines.push("Backward ratios:");
    (payload.backward_ratios && payload.backward_ratios.ratios || []).forEach(function (ratio) {
      lines.push("- " + quantRatioLabel(ratio.key) + ": " +
        (ratio.value == null ? "—" : fmtNum(ratio.value)) +
        " (" + (ratio.status || "insufficient_data") + ")");
    });
    var missing = payload.backward_ratios && payload.backward_ratios.missing_inputs || [];
    if (missing.length) {
      lines.push("Missing inputs: " + missing.join(", "));
    }
    return lines.join("\n");
  }

  function askAssistant(payload) {
    if (
      window.marketAssistant &&
      typeof window.marketAssistant.openWithContext === "function"
    ) {
      window.marketAssistant.openWithContext({
        seedText: quantContextText(payload),
        question: "解读一下 " + payload.symbol + " 的量化体检结果",
      });
    }
  }

  function lookupQuant(symbol, peer) {
    var requestId = ++quantRequestId;
    quantRegion.innerHTML = '<div class="lookup-loading">Loading quant context for ' + escapeHtml(symbol) + "…</div>";
    var url = "/api/ticker-quant/" + encodeURIComponent(symbol);
    if (peer) {
      url += "?peer=" + encodeURIComponent(peer);
    }
    fetch(url)
      .then(function (response) {
        return response.json().then(function (body) {
          return { ok: response.ok, body: body };
        });
      })
      .then(function (result) {
        if (requestId !== quantRequestId) {
          return;
        }
        if (!result.ok) {
          renderQuantError(result.body.detail || "Quant context lookup failed.");
          return;
        }
        renderQuant(result.body);
      })
      .catch(function () {
        if (requestId !== quantRequestId) {
          return;
        }
        renderQuantError("Quant context request failed.");
      });
  }

  function lookupPair(longSymbol, shortSymbol) {
    pairRegion.innerHTML =
      '<div class="lookup-loading">Analyzing pair ' + escapeHtml(longSymbol) +
      " / " + escapeHtml(shortSymbol) + "…</div>";
    fetch(
      "/api/pair-analysis/" + encodeURIComponent(longSymbol) +
        "/" + encodeURIComponent(shortSymbol)
    )
      .then(function (response) {
        return response.json().then(function (body) {
          return { ok: response.ok, body: body };
        });
      })
      .then(function (result) {
        if (!result.ok) {
          renderPairError(result.body.detail || "Pair analysis failed.");
          return;
        }
        renderPair(result.body);
      })
      .catch(function () {
        renderPairError("Pair analysis request failed.");
      });
  }

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    var symbol = form.elements.symbol.value.trim();
    var shortSymbol = form.elements.shortSymbol.value.trim();
    pairRegion.innerHTML = "";
    quantRegion.innerHTML = "";
    closePeerComparePanel();
    peerCompareCache = null;
    latestQuantPayload = null;
    if (!symbol) {
      return;
    }
    lookup(symbol);
    lookupQuant(symbol);
    if (shortSymbol && shortSymbol.toUpperCase() !== symbol.toUpperCase()) {
      lookupPair(symbol, shortSymbol);
    }
  });

  var initialSymbol = new URLSearchParams(window.location.search).get("symbol");
  if (initialSymbol) {
    form.elements.symbol.value = initialSymbol.trim().toUpperCase();
    form.dispatchEvent(new Event("submit", { cancelable: true }));
  }
})();

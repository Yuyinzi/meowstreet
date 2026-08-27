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
    return (
      '<div class="regime-block">' +
      '<span class="regime-label">Regime bias: ' +
      escapeHtml(payload.regime_bias) +
      "</span>" +
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

  function quantValuationHtml(valuation) {
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
      "</div>"
    );
  }

  function quantPeerHtml(peer) {
    if (!peer) {
      return "";
    }
    if (peer.error) {
      return '<div class="status-warning">Peer: ' + escapeHtml(peer.error) + "</div>";
    }
    var diff = peer.pe_differential;
    var diffText = "—";
    if (diff != null) {
      var premiumPct = Math.round((diff - 1) * 100);
      diffText = fmtNum(diff) + "× (" + (premiumPct >= 0 ? "+" : "") + premiumPct + "%)";
    }
    return (
      '<div class="quant-grid">' +
      '<div class="quant-stat"><div class="quant-stat-value">' + escapeHtml(peer.symbol) +
      '</div><div class="quant-stat-label">Peer symbol</div></div>' +
      '<div class="quant-stat"><div class="quant-stat-value">' + fmtNum(peer.forward_pe) +
      '</div><div class="quant-stat-label">Peer forward PE</div></div>' +
      '<div class="quant-stat"><div class="quant-stat-value">' + diffText +
      '</div><div class="quant-stat-label">PE differential</div></div>' +
      "</div>"
    );
  }

  function quantShortChecksHtml(shortChecks) {
    var days = shortChecks.days_to_cover || {};
    var questions = (shortChecks.dividend && shortChecks.dividend.review_questions) || [];
    var questionList = questions.length
      ? '<ul class="quant-question-list">' +
        questions.map(function (question) {
          return "<li>" + escapeHtml(question) + "</li>";
        }).join("") +
        "</ul>"
      : "";
    return (
      '<div class="quant-grid">' +
      '<div class="quant-stat"><div class="quant-stat-value">' + fmtPct(shortChecks.short_percent_of_float) +
      '</div><div class="quant-stat-label">Short % of float</div></div>' +
      '<div class="quant-stat"><div class="quant-stat-value">' + fmtNum(days.value) +
      ' ' + quantStatusChip(days.status) +
      '</div><div class="quant-stat-label">Days to cover</div></div>' +
      '<div class="quant-stat"><div class="quant-stat-value">' + fmtPct(shortChecks.dividend && shortChecks.dividend.yield) +
      '</div><div class="quant-stat-label">Dividend yield</div></div>' +
      "</div>" +
      (questionList ? '<div class="quant-section-title">Dividend review questions</div>' + questionList : "")
    );
  }

  function quantRatioLabel(key) {
    var labels = {
      debt_to_equity: "Debt / equity",
      current_ratio: "Current ratio",
      quick_ratio: "Quick ratio",
      return_on_equity: "Return on equity",
      return_on_assets: "Return on assets",
      book_value: "Book value",
      fcf_yield: "FCF yield",
      price_to_fcf: "Price / FCF",
      ev_to_ebitda: "EV / EBITDA",
    };
    return labels[key] || key.replace(/_/g, " ");
  }

  function quantBackwardRatiosHtml(backwardRatios) {
    var ratios = backwardRatios.ratios || [];
    var missing = backwardRatios.missing_inputs || [];
    var rows = ratios.map(function (ratio) {
      var valueCell = ratio.value == null
        ? '<td class="muted-cell">—</td>'
        : '<td class="num">' + fmtNum(ratio.value) + "</td>";
      return (
        "<tr><td>" + escapeHtml(quantRatioLabel(ratio.key)) + "</td>" +
        valueCell +
        "<td>" + quantStatusChip(ratio.status) + "</td>" +
        "<td>" + (ratio.note ? escapeHtml(ratio.note) : "") + "</td></tr>"
      );
    }).join("");
    var missingList = missing.length
      ? '<ul class="quant-missing-list"><li>' + missing.map(escapeHtml).join("</li><li>") + "</li></ul>"
      : '<p class="section-note">No missing backward ratio inputs.</p>';
    return (
      '<table class="quant-table"><thead><tr>' +
      "<th>Ratio</th><th class=\"num\">Value</th><th>Status</th><th>Note</th>" +
      "</tr></thead><tbody>" + rows + "</tbody></table>" +
      '<div class="quant-section-title">Missing inputs</div>' +
      missingList
    );
  }

  function quantPeerInputHtml(symbol) {
    return (
      '<div class="quant-peer-row">' +
      '<label class="field"><span>Peer symbol (optional)</span>' +
      '<input type="text" id="quantPeerInput" placeholder="AMD" autocomplete="off" /></label>' +
      '<button type="button" class="primary-button" id="quantPeerApply">Compare peer</button>' +
      "</div>"
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
      if (peer) {
        lookupQuant(symbol, peer);
      }
    });
  }

  function renderQuant(payload) {
    var cacheLine = payload.cache
      ? '<div class="quant-sub">Provider: ' + escapeHtml(payload.provider) +
        " · " + escapeHtml(payload.cache) +
        (payload.fetched_at ? " · " + escapeHtml(payload.fetched_at) : "") +
        "</div>"
      : "";
    quantRegion.innerHTML =
      '<div class="quant-card">' +
      '<div class="quant-head">Quant Context — ' + escapeHtml(payload.symbol) + "</div>" +
      cacheLine +
      '<div class="quant-section"><div class="quant-section-title">Valuation</div>' +
      quantValuationHtml(payload.valuation) +
      quantPeerInputHtml(payload.symbol) +
      quantPeerHtml(payload.peer) +
      "</div>" +
      '<div class="quant-section"><div class="quant-section-title">Short checks</div>' +
      quantShortChecksHtml(payload.short_checks) +
      "</div>" +
      '<div class="quant-section"><div class="quant-section-title">Backward ratios</div>' +
      quantBackwardRatiosHtml(payload.backward_ratios) +
      "</div>" +
      "</div>";
    wireQuantPeer(payload.symbol);
  }

  function renderQuantError(message) {
    quantRegion.innerHTML =
      '<div class="quant-card"><div class="status-error">' + escapeHtml(message) + "</div></div>";
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
        if (!result.ok) {
          renderQuantError(result.body.detail || "Quant context lookup failed.");
          return;
        }
        renderQuant(result.body);
        askAssistant(result.body);
      })
      .catch(function () {
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

(function () {
  var form = document.getElementById("lookupForm");
  var region = document.getElementById("resultRegion");
  var pairRegion = document.getElementById("pairRegion");
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
    if (!symbol) {
      return;
    }
    lookup(symbol);
    if (shortSymbol && shortSymbol.toUpperCase() !== symbol.toUpperCase()) {
      lookupPair(symbol, shortSymbol);
    }
  });
})();

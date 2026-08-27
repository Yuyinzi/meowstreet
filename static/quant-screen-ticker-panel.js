(function () {
  var app = document.getElementById("quantScreenApp");
  var panel = document.getElementById("tickerDetailPanel");
  var activeSymbol = null;
  var activeContext = null;

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function fmtNum(value, digits) {
    if (value == null) {
      return "—";
    }
    return Number(value).toFixed(digits == null ? 2 : digits);
  }

  function fmtPct(value, digits) {
    if (value == null) {
      return "—";
    }
    return (Number(value) * 100).toFixed(digits == null ? 1 : digits) + "%";
  }

  function fmtDollarsCompact(value) {
    if (value == null) {
      return "—";
    }
    var number = Number(value);
    if (number >= 1e12) {
      return "$" + (number / 1e12).toFixed(2) + "T";
    }
    if (number >= 1e9) {
      return "$" + (number / 1e9).toFixed(2) + "B";
    }
    if (number >= 1e6) {
      return "$" + (number / 1e6).toFixed(2) + "M";
    }
    return "$" + number.toLocaleString("en-US", { maximumFractionDigits: 0 });
  }

  function statusTone(status) {
    if (status === "within" || status === "ok" || status === "positive") {
      return "chip-positive";
    }
    if (status === "warning" || status === "review") {
      return "chip-warning";
    }
    if (status === "dangerous" || status === "officially_dangerous" || status === "negative") {
      return "chip-negative";
    }
    return "chip-muted";
  }

  function statusChip(status) {
    var label = status || "insufficient_data";
    return '<span class="tag-chip ' + statusTone(status) + '">' +
      escapeHtml(label.replace(/_/g, " ")) + "</span>";
  }

  function fetchJson(url) {
    return fetch(url).then(function (response) {
      return response.json().then(function (body) {
        if (!response.ok) {
          throw new Error(body.detail || "Ticker lookup failed.");
        }
        return body;
      });
    });
  }

  function panelHead(symbol) {
    return (
      '<div class="ticker-detail-head">' +
      '<h2 class="ticker-detail-title">' + escapeHtml(symbol) + "</h2>" +
      '<button type="button" class="ticker-detail-close" id="tickerDetailClose" aria-label="Close ticker detail">×</button>' +
      "</div>"
    );
  }

  function industryPath(payload) {
    var parts = [payload.sector, payload.industry_group, payload.industry].filter(function (part) {
      return part;
    });
    if (!parts.length && payload.provider_industry) {
      return escapeHtml(payload.provider_industry) + " (provider industry)";
    }
    return parts.map(escapeHtml).join(" › ") || "Industry unavailable";
  }

  function cycleTag(payload) {
    if (!payload.cycle_tag) {
      return statusChip("insufficient_data");
    }
    var tone = payload.cycle_tag === "cyclical" ? "chip-positive" :
      payload.cycle_tag === "defensive" ? "chip-warning" : "chip-muted";
    return '<span class="tag-chip ' + tone + '">' +
      escapeHtml(payload.cycle_tag) + "</span>";
  }

  function contextSection(payload) {
    var unresolved = payload.status && payload.status !== "resolved"
      ? '<div class="status-warning">Industry context is unresolved; treat the industry tag as incomplete.</div>'
      : "";
    return (
      '<section class="ticker-detail-section">' +
      '<div class="ticker-detail-company">' + escapeHtml(payload.company_name || payload.symbol) +
      " (" + escapeHtml(payload.symbol) + ")</div>" +
      '<div class="ticker-detail-path">' + industryPath(payload) + "</div>" +
      '<div class="ticker-detail-meta">Cycle tag: ' + cycleTag(payload) + "</div>" +
      unresolved +
      "</section>"
    );
  }

  function stat(label, value) {
    return (
      '<div class="stat"><div class="stat-value">' + value +
      '</div><div class="stat-label">' + escapeHtml(label) + "</div></div>"
    );
  }

  function valuationSection(payload) {
    var valuation = payload.valuation || {};
    return (
      '<section class="ticker-detail-section">' +
      '<div class="ticker-detail-section-title">Valuation</div>' +
      '<div class="stat-grid ticker-detail-panel-grid">' +
      stat("Forward PE", fmtNum(valuation.forward_pe)) +
      stat("Forward EPS", fmtNum(valuation.forward_eps)) +
      stat("Trailing EPS", fmtNum(valuation.trailing_eps)) +
      stat("Market Cap", fmtDollarsCompact(valuation.market_cap)) +
      "</div>" +
      peerForm() +
      peerLine(payload.peer) +
      "</section>"
    );
  }

  function peerForm() {
    return (
      '<div class="ticker-detail-peer-form">' +
      '<label class="field"><span>Peer symbol (optional)</span>' +
      '<input type="text" id="tickerDetailPeerInput" placeholder="AMD" autocomplete="off" /></label>' +
      '<button type="button" class="primary-button" id="tickerDetailPeerApply">Apply</button>' +
      "</div>"
    );
  }

  function peerLine(peer) {
    if (!peer) {
      return "";
    }
    if (peer.error) {
      return '<div class="status-warning">Peer: ' + escapeHtml(peer.error) + "</div>";
    }
    var differential = peer.pe_differential == null ? "—" : fmtNum(peer.pe_differential) + "×";
    return '<div class="ticker-detail-peer">Peer ' + escapeHtml(peer.symbol) +
      " · Forward PE " + fmtNum(peer.forward_pe) +
      " · PE differential " + differential + "</div>";
  }

  function shortChecksSection(payload) {
    var checks = payload.short_checks || {};
    var days = checks.days_to_cover || {};
    var dividend = checks.dividend || {};
    var questions = dividend.review_questions || [];
    var questionList = questions.length
      ? '<ul class="quant-missing-list">' + questions.map(function (question) {
        return "<li>" + escapeHtml(question) + "</li>";
      }).join("") + "</ul>"
      : "";
    return (
      '<section class="ticker-detail-section">' +
      '<div class="ticker-detail-section-title">Short checks</div>' +
      '<div class="stat-grid ticker-detail-panel-grid">' +
      stat("Short % of float", fmtPct(checks.short_percent_of_float)) +
      stat("Days to cover", fmtNum(days.value) + " " + statusChip(days.status)) +
      stat("Dividend yield", fmtPct(dividend.yield)) +
      "</div>" +
      (questionList ? '<div class="ticker-detail-meta">Dividend review questions</div>' + questionList : "") +
      "</section>"
    );
  }

  function ratioValue(ratio) {
    if (ratio.value == null) {
      return "—";
    }
    if (ratio.key === "return_on_equity" || ratio.key === "return_on_assets" || ratio.key === "fcf_yield") {
      return fmtPct(ratio.value);
    }
    return fmtNum(ratio.value);
  }

  function ratioLabel(key) {
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
    return labels[key] || String(key || "ratio").replace(/_/g, " ");
  }

  function backwardRatiosSection(payload) {
    var backward = payload.backward_ratios || {};
    var ratios = backward.ratios || [];
    var missing = backward.missing_inputs || [];
    var rows = ratios.map(function (ratio) {
      return (
        "<tr><td>" + escapeHtml(ratioLabel(ratio.key)) + "</td>" +
        '<td class="num">' + ratioValue(ratio) + "</td>" +
        "<td>" + statusChip(ratio.status) + "</td>" +
        "<td>" + escapeHtml(ratio.note || "") + "</td></tr>"
      );
    }).join("");
    var missingNote = missing.length
      ? '<div class="status-warning">Missing inputs: ' + missing.map(escapeHtml).join(", ") + "</div>"
      : '<div class="ticker-detail-meta">No missing backward ratio inputs.</div>';
    return (
      '<section class="ticker-detail-section">' +
      '<div class="ticker-detail-section-title">Backward ratios</div>' +
      '<div class="table-wrap"><table class="data-table ticker-detail-table"><thead><tr>' +
      "<th>Ratio</th><th class=\"num\">Value</th><th>Status</th><th>Note</th>" +
      "</tr></thead><tbody>" + rows + "</tbody></table></div>" +
      missingNote +
      "</section>"
    );
  }

  function tickerQuantContextText(contextPayload, quantPayload) {
    var valuation = quantPayload.valuation || {};
    var shortChecks = quantPayload.short_checks || {};
    var days = shortChecks.days_to_cover || {};
    var dividend = shortChecks.dividend || {};
    var lines = [
      "The user is viewing a Quant Screen ticker detail panel. Explain the deterministic context and quantitative checks without making a trade decision:",
      "Symbol: " + quantPayload.symbol,
      "Company: " + (contextPayload.company_name || quantPayload.symbol),
      "Industry path: " + industryPath(contextPayload),
      "Cycle tag: " + (contextPayload.cycle_tag || "insufficient_data"),
      "Valuation: forward PE " + fmtNum(valuation.forward_pe) +
        ", forward EPS " + fmtNum(valuation.forward_eps) +
        ", trailing EPS " + fmtNum(valuation.trailing_eps) +
        ", market cap " + fmtDollarsCompact(valuation.market_cap),
      "Short checks: short % of float " + fmtPct(shortChecks.short_percent_of_float) +
        ", days to cover " + fmtNum(days.value) + " (" + (days.status || "insufficient_data") +
        "), dividend yield " + fmtPct(dividend.yield),
    ];
    if (quantPayload.peer) {
      lines.push("Peer: " + (quantPayload.peer.symbol || "unknown") +
        ", forward PE " + fmtNum(quantPayload.peer.forward_pe) +
        ", PE differential " + (quantPayload.peer.pe_differential == null ? "—" : fmtNum(quantPayload.peer.pe_differential) + "×"));
    }
    lines.push("Backward ratios:");
    (quantPayload.backward_ratios && quantPayload.backward_ratios.ratios || []).forEach(function (ratio) {
      lines.push("- " + ratioLabel(ratio.key) + ": " + ratioValue(ratio) +
        " (" + (ratio.status || "insufficient_data") + ")");
    });
    var missing = quantPayload.backward_ratios && quantPayload.backward_ratios.missing_inputs || [];
    if (missing.length) {
      lines.push("Missing inputs: " + missing.join(", "));
    }
    return lines.join("\n");
  }

  function askAssistant(contextPayload, quantPayload) {
    if (
      window.marketAssistant &&
      typeof window.marketAssistant.openWithContext === "function"
    ) {
      window.marketAssistant.openWithContext({
        seedText: tickerQuantContextText(contextPayload, quantPayload),
        question: "解读一下 " + quantPayload.symbol + " 的这份量化体检和行业背景",
      });
    }
  }

  function renderQuantSection(quantPayload) {
    var region = panel.querySelector("#tickerDetailQuantRegion");
    if (!region) {
      return;
    }
    region.innerHTML =
      valuationSection(quantPayload) +
      shortChecksSection(quantPayload) +
      backwardRatiosSection(quantPayload);
    wirePeer(quantPayload.symbol);
    askAssistant(activeContext, quantPayload);
  }

  function wirePeer(symbol) {
    var input = panel.querySelector("#tickerDetailPeerInput");
    var apply = panel.querySelector("#tickerDetailPeerApply");
    if (!input || !apply) {
      return;
    }
    apply.addEventListener("click", function () {
      var peer = input.value.trim();
      if (!peer) {
        return;
      }
      var region = panel.querySelector("#tickerDetailQuantRegion");
      region.innerHTML = '<div class="lookup-loading">Loading peer comparison…</div>';
      fetchJson("/api/ticker-quant/" + encodeURIComponent(symbol) + "?peer=" + encodeURIComponent(peer))
        .then(function (payload) {
          if (activeSymbol !== symbol) {
            return;
          }
          renderQuantSection(payload);
        })
        .catch(function (error) {
          if (activeSymbol === symbol) {
            region.innerHTML = '<div class="status-error">' + escapeHtml(error.message) + "</div>";
          }
        });
    });
  }

  function closeTickerPanel() {
    activeSymbol = null;
    activeContext = null;
    app.classList.remove("panel-open");
    panel.innerHTML = "";
  }

  function openTickerPanel(symbol) {
    var normalized = String(symbol || "").trim().toUpperCase();
    if (!normalized) {
      return;
    }
    activeSymbol = normalized;
    app.classList.add("panel-open");
    panel.innerHTML = panelHead(normalized) +
      '<div class="detail-panel-body">' +
      '<div class="lookup-loading">Loading ticker context…</div>' +
      "</div>";
    panel.querySelector("#tickerDetailClose").addEventListener("click", closeTickerPanel);
    Promise.all([
      fetchJson("/api/ticker-context/" + encodeURIComponent(normalized)),
      fetchJson("/api/ticker-quant/" + encodeURIComponent(normalized)),
    ])
      .then(function (payloads) {
        if (activeSymbol !== normalized) {
          return;
        }
        activeContext = payloads[0];
        panel.querySelector(".detail-panel-body").innerHTML =
          contextSection(payloads[0]) + '<div id="tickerDetailQuantRegion"></div>';
        renderQuantSection(payloads[1]);
      })
      .catch(function (error) {
        if (activeSymbol !== normalized) {
          return;
        }
        panel.querySelector(".detail-panel-body").innerHTML =
          '<div class="status-error">' + escapeHtml(error.message) + "</div>";
      });
  }

  if (!app || !panel) {
    return;
  }

  window.QuantScreenTickerPanel = {
    open: openTickerPanel,
    close: closeTickerPanel,
  };
})();

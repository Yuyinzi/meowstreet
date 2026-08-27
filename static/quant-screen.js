(function () {
  var form = document.getElementById("screenForm");
  var region = document.getElementById("screenRegion");
  var autoForm = document.getElementById("autoForm");
  var autoRegion = document.getElementById("autoRegion");
  var autoSelect = autoForm.elements.industry;
  var autoSubmit = document.getElementById("autoSubmit");
  var autoLog = document.getElementById("autoLog");

  var PAGE_SIZE = 10;
  var pageStates = new Map();
  var industriesByName = {};

  var STEP_META = {
    pe_premium_both_periods: {
      label: "PE premium",
      title: "Forward PE above the sector mean in both FY1 and FY2",
    },
    eg_above_sector_both_periods: {
      label: "EG above sector",
      title: "Earnings growth above the sector mean in both FY1 and FY2",
    },
    market_cap_mid_tier: {
      label: "Mid cap",
      title: "Market cap in the mid tier ($3B–$10B)",
    },
    peg1_above_1: {
      label: "PEG1 > 1",
      title: "FY1 PEG above 1",
    },
    pe_discount_both_periods: {
      label: "PE discount",
      title: "Forward PE below the sector mean in both FY1 and FY2",
    },
    eg_below_sector_and_declining: {
      label: "EG below & falling",
      title: "Earnings growth below the sector mean in both FY1 and FY2, and declining (FY2 < FY1)",
    },
    market_cap_large: {
      label: "Large cap",
      title: "Market cap at least $20B",
    },
  };

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
    return (value * 100).toFixed(digits == null ? 1 : digits) + "%";
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

  function tierBadge(tier) {
    if (!tier) {
      return '<span class="tag-chip chip-muted">unknown</span>';
    }
    return '<span class="tag-chip chip-positive">' + escapeHtml(tier) + "</span>";
  }

  function egCaseBadge(egCase) {
    if (egCase == null || egCase === "unclassified") {
      return '<span class="tag-chip chip-muted">unclassified</span>';
    }
    return '<span class="tag-chip chip-positive">case ' + escapeHtml(egCase) + "</span>";
  }

  function stepDetailLines(step) {
    var detail = step.detail || {};
    var lines = [];
    if ("pe1" in detail && "mean_pe1" in detail) {
      lines.push("PE1 " + fmtNum(detail.pe1) + " vs sector mean " + fmtNum(detail.mean_pe1));
    }
    if ("pe2" in detail && "mean_pe2" in detail) {
      lines.push("PE2 " + fmtNum(detail.pe2) + " vs sector mean " + fmtNum(detail.mean_pe2));
    }
    if ("eg1" in detail && "mean_eg1" in detail) {
      lines.push("EG1 " + fmtPct(detail.eg1) + " vs sector mean " + fmtPct(detail.mean_eg1));
    }
    if ("eg2" in detail && "mean_eg2" in detail) {
      lines.push("EG2 " + fmtPct(detail.eg2) + " vs sector mean " + fmtPct(detail.mean_eg2));
    }
    if ("accelerating" in detail && detail.accelerating != null) {
      lines.push("Growth accelerating (FY2 > FY1): " + (detail.accelerating ? "yes" : "no"));
    }
    if ("peg1" in detail) {
      lines.push("PEG1 " + fmtNum(detail.peg1));
    }
    if ("tier" in detail) {
      lines.push("Market cap tier: " + (detail.tier || "unknown"));
    }
    if ("market_cap" in detail) {
      lines.push("Market cap: " + fmtDollarsCompact(detail.market_cap));
    }
    return lines;
  }

  function stepTipText(step, meta) {
    var verdict = step.passed === true ? "passed" : step.passed === false ? "failed" : "no data";
    var lines = [meta.title, ""].concat(stepDetailLines(step));
    lines.push("Result: " + verdict);
    return lines.join("\n");
  }

  function stepChips(filter) {
    if (!filter || !filter.steps) {
      return "";
    }
    var chips = filter.steps.map(function (step) {
      var tone = step.passed === true ? "step-chip-passed" : step.passed === false ? "step-chip-failed" : "step-chip-null";
      var marker = step.passed === true ? "✓ " : step.passed === false ? "✗ " : "— ";
      var meta = STEP_META[step.name] || { label: step.name.replace(/_/g, " "), title: step.name.replace(/_/g, " ") };
      return '<span class="gate-chip ' + tone + '" data-tip="' + escapeHtml(stepTipText(step, meta)) + '">' +
        marker + escapeHtml(meta.label) + "</span>";
    });
    return '<div class="gate-chips">' + chips.join("") + "</div>";
  }

  var chipTooltip = null;

  function hideChipTooltip() {
    if (chipTooltip) {
      chipTooltip.remove();
      chipTooltip = null;
    }
  }

  function showChipTooltip(chip) {
    hideChipTooltip();
    chipTooltip = document.createElement("div");
    chipTooltip.className = "chip-tooltip";
    chipTooltip.textContent = chip.getAttribute("data-tip");
    document.body.appendChild(chipTooltip);
    var rect = chip.getBoundingClientRect();
    var left = Math.min(rect.left, window.innerWidth - chipTooltip.offsetWidth - 8);
    var top = rect.bottom + 6;
    if (top + chipTooltip.offsetHeight > window.innerHeight - 8) {
      top = rect.top - chipTooltip.offsetHeight - 6;
    }
    chipTooltip.style.left = Math.max(8, left) + "px";
    chipTooltip.style.top = top + "px";
  }

  function flagsBadges(flags) {
    if (!flags || !flags.length) {
      return "";
    }
    var chips = flags.map(function (flag) {
      return '<span class="tag-chip chip-warning">' + escapeHtml(flag.replace(/_/g, " ")) + "</span>";
    });
    return '<div class="gate-chips">' + chips.join("") + "</div>";
  }

  function sectorMeansHtml(sector) {
    return (
      '<div class="stat-grid">' +
      '<div class="stat"><div class="stat-value">' + fmtNum(sector.mean_pe1) +
      '</div><div class="stat-label">Mean PE1</div></div>' +
      '<div class="stat"><div class="stat-value">' + fmtNum(sector.mean_pe2) +
      '</div><div class="stat-label">Mean PE2</div></div>' +
      '<div class="stat"><div class="stat-value">' + fmtPct(sector.mean_eg1) +
      '</div><div class="stat-label">Mean EG1</div></div>' +
      '<div class="stat"><div class="stat-value">' + fmtPct(sector.mean_eg2) +
      '</div><div class="stat-label">Mean EG2</div></div>' +
      '</div>' +
      '<div class="section-note">Mean method: ' + escapeHtml(sector.mean_method) + "</div>"
    );
  }

  function rowHtml(row, contributions) {
    return (
      "<tr>" +
      "<td>" + escapeHtml(row.symbol) + "</td>" +
      '<td class="num">' + fmtNum(row.price) + "</td>" +
      '<td class="num">' + fmtDollarsCompact(row.market_cap) + " " + tierBadge(row.market_cap_tier) + "</td>" +
      '<td class="num">' + fmtNum(row.eps_fy0) + "</td>" +
      '<td class="num">' + fmtNum(row.eps_fy1) + "</td>" +
      '<td class="num">' + fmtNum(row.eps_fy2) + "</td>" +
      '<td class="num">' + fmtPct(row.eg1) + "</td>" +
      '<td class="num">' + fmtPct(row.eg2) + "</td>" +
      '<td class="num">' + fmtNum(row.pe1) + "</td>" +
      '<td class="num">' + fmtNum(row.pe2) + "</td>" +
      '<td class="num">' + fmtNum(contributions[row.symbol], 4) + "</td>" +
      '<td class="num">' + fmtNum(row.peg1) + "</td>" +
      '<td class="num">' + fmtNum(row.peg2) + "</td>" +
      "<td>" + egCaseBadge(row.eg_case) + "</td>" +
      "<td>" + stepChips(row.long_filter) + "</td>" +
      "<td>" + stepChips(row.short_filter) + "</td>" +
      "<td>" + flagsBadges(row.flags) + "</td>" +
      "</tr>"
    );
  }

  function rowsHtml(rows, contributions) {
    var head =
      "<tr>" +
      "<th>Symbol</th>" +
      '<th class="num">Price</th>' +
      '<th class="num">Market Cap</th>' +
      '<th class="num">EPS FY0</th>' +
      '<th class="num">EPS FY1</th>' +
      '<th class="num">EPS FY2</th>' +
      '<th class="num">EG1</th>' +
      '<th class="num">EG2</th>' +
      '<th class="num">PE1</th>' +
      '<th class="num">PE2</th>' +
      '<th class="num" title="Leave-one-out stress test: how much the sector mean PE1 moves when this stock is removed">PE1 Contr.</th>' +
      '<th class="num">PEG1</th>' +
      '<th class="num">PEG2</th>' +
      "<th>EG Case</th>" +
      "<th>Long filter</th>" +
      "<th>Short filter</th>" +
      "<th>Flags</th>" +
      "</tr>";
    var body = rows.map(function (row) { return rowHtml(row, contributions); }).join("");
    return (
      '<div class="table-wrap"><table class="data-table"><thead>' +
      head + "</thead><tbody>" + body + "</tbody></table></div>"
    );
  }

  function leaveOneOutMap(leaveOneOut) {
    var map = {};
    (leaveOneOut || []).forEach(function (item) {
      map[item.symbol] = item.contribution;
    });
    return map;
  }

  function rowErrorsHtml(rowErrors) {
    if (!rowErrors || !rowErrors.length) {
      return "";
    }
    var items = rowErrors
      .map(function (error) {
        var label = error.symbol ? escapeHtml(error.symbol) : "Line " + escapeHtml(error.line);
        return "<li>" + label + ": " + escapeHtml(error.reason) + "</li>";
      })
      .join("");
    return (
      '<div class="section-block"><div class="section-title">Row errors (' +
      rowErrors.length + ')</div>' +
      '<ul class="error-list">' + items + "</ul></div>"
    );
  }

  function detailsHtml(payload) {
    if (!payload.row_errors || !payload.row_errors.length) {
      return "";
    }
    return (
      '<details class="details-panel">' +
      '<summary>Diagnostics: row errors</summary>' +
      rowErrorsHtml(payload.row_errors) +
      "</details>"
    );
  }

  function candidateChipsHtml(rows, side) {
    var key = side === "long" ? "long_filter" : "short_filter";
    var tone = side === "long" ? "chip-positive" : "chip-negative";
    var passing = rows.filter(function (row) {
      return row[key] && row[key].passes === true;
    });
    var chips = passing.map(function (row) {
      return '<a class="tag-chip candidate-link ' + tone + '" href="/ticker-context.html?symbol=' +
        encodeURIComponent(row.symbol) + '" title="Passed all ' + side +
        ' head-checks — open in Ticker Context">' + escapeHtml(row.symbol) + "</a>";
    }).join("");
    return (
      '<div class="candidate-group">' +
      '<span class="candidate-label">' + (side === "long" ? "Long" : "Short") +
      " (" + passing.length + ")</span>" +
      (chips || '<span class="section-note">None — no stock passed all ' + side + " head-checks.</span>") +
      "</div>"
    );
  }

  function candidatesHtml(rows) {
    return (
      '<div class="section-block"><div class="section-title">Candidates</div>' +
      candidateChipsHtml(rows, "long") +
      candidateChipsHtml(rows, "short") +
      '<div class="section-note">A candidate passed every head-check on its side. This narrows research focus — it is not a trade signal.</div>' +
      "</div>"
    );
  }

  function sourceLineHtml(source) {
    if (!source || source.mode !== "auto") {
      return "";
    }
    var note = source.estimate_failures > 0
      ? " · " + source.estimate_failures + " estimates unavailable"
      : "";
    return (
      '<div class="result-sub">Auto · ' + escapeHtml(source.provider) +
      ' · ' + escapeHtml(source.industry) +
      ' · ' + source.stock_count + ' stocks' + note + "</div>"
    );
  }

  function pagerHtml(page, totalPages, rowCount) {
    if (rowCount <= PAGE_SIZE) {
      return "";
    }
    return (
      '<div class="pager">' +
      '<button type="button" class="pager-button" data-page-dir="-1"' + (page === 0 ? " disabled" : "") + ">Prev</button>" +
      '<span class="pager-status">Page ' + (page + 1) + " of " + totalPages + " · " + rowCount + " rows</span>" +
      '<button type="button" class="pager-button" data-page-dir="1"' + (page >= totalPages - 1 ? " disabled" : "") + ">Next</button>" +
      "</div>"
    );
  }

  function renderResultsPage(host, page) {
    var state = pageStates.get(host);
    var rows = state.payload.rows || [];
    var totalPages = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
    var clamped = Math.min(Math.max(page, 0), totalPages - 1);
    state.page = clamped;
    var slice = rows.slice(clamped * PAGE_SIZE, clamped * PAGE_SIZE + PAGE_SIZE);
    host.innerHTML =
      rowsHtml(slice, state.contributions) +
      pagerHtml(clamped, totalPages, rows.length) +
      '<div class="section-note">Each chip is one head-check: ✓ passed · ✗ failed · — no data. Hover a chip for the rule and the actual numbers.</div>';
  }

  function renderScreen(targetRegion, payload) {
    var oldHost = targetRegion.querySelector(".results-host");
    if (oldHost) {
      pageStates.delete(oldHost);
    }
    targetRegion.innerHTML =
      '<div class="result-card">' +
      sourceLineHtml(payload.source) +
      '<div class="disclaimer">' + escapeHtml(payload.disclaimer) + "</div>" +
      '<div class="result-company">Sector averages</div>' +
      sectorMeansHtml(payload.sector) +
      candidatesHtml(payload.rows || []) +
      '<details class="details-panel results-panel">' +
      '<summary>Full results (' + escapeHtml(payload.row_count) + " rows)</summary>" +
      '<div class="results-host"></div>' +
      "</details>" +
      detailsHtml(payload) +
      "</div>";
    var host = targetRegion.querySelector(".results-host");
    pageStates.set(host, {
      payload: payload,
      page: 0,
      contributions: leaveOneOutMap(payload.sector && payload.sector.leave_one_out),
    });
    renderResultsPage(host, 0);
  }

  function renderError(targetRegion, message) {
    targetRegion.innerHTML = '<div class="result-card"><div class="status-error">' + escapeHtml(message) + "</div></div>";
  }

  function runScreen() {
    var tableText = form.elements.tableText.value;
    region.innerHTML = '<div class="lookup-loading">Running screen…</div>';
    fetch("/api/quant-screen", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ table_text: tableText }),
    })
      .then(function (response) {
        return response.json().then(function (body) {
          return { ok: response.ok, body: body };
        });
      })
      .then(function (result) {
        if (!result.ok) {
          renderError(region, result.body.detail || "Screen failed.");
          return;
        }
        renderScreen(region, result.body);
      })
      .catch(function () {
        renderError(region, "Screen request failed.");
      });
  }

  function logLine(message) {
    autoLog.hidden = false;
    var line = document.createElement("div");
    line.className = "fetch-log-line";
    var time = new Date().toLocaleTimeString("en-GB", { hour12: false });
    var stamp = document.createElement("span");
    stamp.className = "fetch-log-time";
    stamp.textContent = time;
    line.appendChild(stamp);
    line.appendChild(document.createTextNode(message));
    autoLog.appendChild(line);
    return line;
  }

  function resetLog() {
    autoLog.innerHTML = "";
    autoLog.hidden = true;
  }

  function startElapsedLine(message) {
    var line = logLine(message + " 0s");
    var textNode = line.lastChild;
    var startedAt = Date.now();
    var timer = setInterval(function () {
      var elapsed = Math.floor((Date.now() - startedAt) / 1000);
      textNode.textContent = message + " " + elapsed + "s";
    }, 1000);
    return {
      finish: function (finalMessage) {
        clearInterval(timer);
        var elapsed = ((Date.now() - startedAt) / 1000).toFixed(1);
        textNode.textContent = finalMessage + " (" + elapsed + "s)";
      },
    };
  }

  function setAutoLoading(isLoading) {
    autoSubmit.disabled = isLoading;
    autoSubmit.textContent = isLoading ? "Running…" : "Run auto screen";
  }

  function loadIndustries() {
    resetLog();
    var pending = startElapsedLine("Loading industry list…");
    fetch("/api/quant-screen/industries")
      .then(function (response) {
        return response.json().then(function (body) {
          return { ok: response.ok, body: body };
        });
      })
      .then(function (result) {
        if (!result.ok) {
          pending.finish("Industry list failed: " + (result.body.detail || "unknown error"));
          autoSelect.innerHTML = '<option value="">' +
            escapeHtml(result.body.detail || "Unable to load industries") + "</option>";
          return;
        }
        var industries = result.body.industries || [];
        if (!industries.length) {
          pending.finish("Industry list is empty");
          autoSelect.innerHTML = '<option value="">No industries available</option>';
          return;
        }
        industriesByName = {};
        industries.forEach(function (item) {
          industriesByName[item.industry] = item.stock_count;
        });
        pending.finish(industries.length + " industries loaded");
        autoSelect.innerHTML = industries.map(function (item) {
          return '<option value="' + escapeHtml(item.industry) + '">' +
            escapeHtml(item.industry) + "（" + item.stock_count + " stocks）</option>";
        }).join("");
        autoSelect.disabled = false;
        autoSubmit.disabled = false;
      })
      .catch(function () {
        pending.finish("Industry list request failed");
        autoSelect.innerHTML = '<option value="">Unable to load industries</option>';
      });
  }

  function runAutoScreen() {
    var industry = autoSelect.value;
    if (!industry) {
      renderError(autoRegion, "Please select an industry.");
      return;
    }
    setAutoLoading(true);
    autoRegion.innerHTML = "";
    var stockCount = industriesByName[industry];
    logLine("Running screen for " + industry +
      (stockCount ? " (" + stockCount + " stocks)" : "") + "…");
    var pending = startElapsedLine("Fetching price and EPS estimates per stock…");
    fetch("/api/quant-screen/auto", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ industry: industry }),
    })
      .then(function (response) {
        return response.json().then(function (body) {
          return { ok: response.ok, body: body };
        });
      })
      .then(function (result) {
        setAutoLoading(false);
        if (!result.ok) {
          pending.finish("Screen failed: " + (result.body.detail || "unknown error"));
          renderError(autoRegion, result.body.detail || "Auto screen failed.");
          return;
        }
        var failures = result.body.source && result.body.source.estimate_failures;
        pending.finish(
          "Screen complete: " + result.body.row_count + " rows" +
          (failures ? ", " + failures + " estimates unavailable" : "")
        );
        renderScreen(autoRegion, result.body);
      })
      .catch(function () {
        setAutoLoading(false);
        pending.finish("Screen request failed");
        renderError(autoRegion, "Auto screen request failed.");
      });
  }

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    runScreen();
  });

  autoForm.addEventListener("submit", function (event) {
    event.preventDefault();
    runAutoScreen();
  });

  document.addEventListener("click", function (event) {
    var button = event.target.closest("[data-page-dir]");
    if (!button || button.disabled) {
      return;
    }
    var host = button.closest(".results-host");
    if (!host || !pageStates.has(host)) {
      return;
    }
    var state = pageStates.get(host);
    renderResultsPage(host, state.page + Number(button.getAttribute("data-page-dir")));
  });

  document.addEventListener("mouseover", function (event) {
    var chip = event.target.closest(".gate-chip");
    if (chip && chip.getAttribute("data-tip")) {
      showChipTooltip(chip);
    } else {
      hideChipTooltip();
    }
  });

  document.addEventListener("scroll", hideChipTooltip, true);

  loadIndustries();
})();

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
    if (status === "within" || status === "ok" || status === "positive" || status === "available") {
      return "chip-positive";
    }
    if (status === "warning" || status === "review" || status === "none") {
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

  function estimateConsensusLine(payload) {
    var consensus = payload.estimate_consensus || {};
    if (consensus.status !== "ok") {
      return "";
    }
    var trend = payload.estimate_revision_trend || {};
    var skewTone = consensus.skew === "positive" ? "chip-positive" : (consensus.skew === "negative" ? "chip-warning" : "chip-muted");
    var trendChip;
    if (trend.status === "ok") {
      var trendTone = trend.direction === "up" ? "chip-positive" : (trend.direction === "down" ? "chip-warning" : "chip-muted");
      trendChip = '<span class="tag-chip ' + trendTone + '">' +
        escapeHtml("revisions " + trend.direction + " (" + trend.increases + " up / " + trend.decreases + " down, " + trend.window_days + "d)") +
        "</span>";
    } else {
      trendChip = '<span class="tag-chip chip-muted">revisions accumulating</span>';
    }
    return (
      '<div class="ticker-detail-conclusion">' +
      '<div class="ticker-detail-conclusion-head">' +
      '<span class="ticker-detail-section-title">Estimate Consensus — ' + escapeHtml(fiscalYearLabel(consensus.fiscal_year_end)) + "</span>" +
      '<span class="ticker-detail-conclusion-chips">' +
      '<span class="tag-chip ' + skewTone + '">' + escapeHtml(consensus.skew) + " skew</span>" +
      trendChip +
      "</span>" +
      "</div>" +
      '<div class="stat-grid ticker-detail-panel-grid">' +
      stat("Analysts with EPS estimates", escapeHtml(consensus.analyst_count)) +
      stat("Avg EPS estimate", fmtNum(consensus.avg)) +
      stat("Estimate range", fmtNum(consensus.low) + "–" + fmtNum(consensus.high)) +
      "</div>" +
      "</div>"
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
      estimateConsensusLine(payload) +
      peerForm() +
      '<div id="tickerDetailPeerResult">' +
      peerLine(payload.peer, payload) +
      "</div>" +
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

  function _ratioValueByKey(payload, key) {
    var ratios = (payload.backward_ratios && payload.backward_ratios.ratios) || [];
    for (var i = 0; i < ratios.length; i++) {
      if (ratios[i].key === key) {
        return ratios[i].value;
      }
    }
    return null;
  }

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

  function peerLine(peer, payload) {
    if (!peer) {
      return "";
    }
    if (peer.error) {
      return '<div class="status-warning">Peer: ' + escapeHtml(peer.error) + "</div>";
    }
    var differential = "—";
    if (peer.pe_differential != null) {
      var premiumPct = Math.round((peer.pe_differential - 1) * 100);
      differential = fmtNum(peer.pe_differential) + "× (" + (premiumPct >= 0 ? "+" : "") + premiumPct + "%)";
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
          '<td class="num">' + differential + "</td></tr>";
      }
    });
    return (
      '<div class="table-wrap"><table class="data-table ticker-detail-table"><thead><tr>' +
      "<th>Metric</th>" +
      '<th class="num">' + escapeHtml(payload.symbol) + "</th>" +
      '<th class="num">' + escapeHtml(peer.symbol || "") + "</th>" +
      "</tr></thead><tbody>" + body + "</tbody></table></div>"
    );
  }

  function shortChecksSection(payload) {
    var checks = payload.short_checks || {};
    var days = checks.days_to_cover || {};
    var dividend = checks.dividend || {};
    var dividendNote = dividend.yield == null && dividend.note
      ? '<div class="quant-inline-note">' + escapeHtml(dividend.note) + "</div>"
      : "";
    var dividendValue = dividend.yield == null ? "Not reported" : fmtPct(dividend.yield);
    return (
      '<section class="ticker-detail-section">' +
      '<div class="ticker-detail-section-title">Short checks</div>' +
      '<div class="stat-grid ticker-detail-panel-grid">' +
      stat("Short % of float", fmtPct(checks.short_percent_of_float)) +
      stat("Days to cover", fmtNum(days.value) + " " + statusChip(days.status)) +
      stat("Dividend yield", dividendValue + dividendNote) +
      "</div>" +
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
    return labels[key] || String(key || "ratio").replace(/_/g, " ");
  }

  function backwardRatiosSection(payload) {
    var backward = payload.backward_ratios || {};
    var ratios = backward.ratios || [];
    var rows = ratios.map(function (ratio) {
      var note = ratio.value == null && ratio.note
        ? '<div class="quant-inline-note">' + escapeHtml(ratio.note) + "</div>"
        : "";
      return (
        "<tr><td>" + escapeHtml(ratioLabel(ratio.key)) + "</td>" +
        '<td class="num">' + ratioValue(ratio) + note + "</td>" +
        "<td>" + statusChip(ratio.status) + "</td></tr>"
      );
    }).join("");
    return (
      '<section class="ticker-detail-section">' +
      '<div class="ticker-detail-section-title">Backward ratios</div>' +
      '<div class="table-wrap"><table class="data-table ticker-detail-table"><thead><tr>' +
      "<th>Ratio</th><th class=\"num\">Value</th><th>Status</th>" +
      "</tr></thead><tbody>" + rows + "</tbody></table></div>" +
      "</section>"
    );
  }

  function analystRatingsSection(payload) {
    var ratings = payload.analyst_ratings || {};
    if (ratings.status !== "ok") {
      return (
        '<section class="ticker-detail-section">' +
        '<div class="ticker-detail-section-title">Analyst ratings</div>' +
        '<div class="ticker-detail-meta">Analyst ratings insufficient data.</div>' +
        "</section>"
      );
    }
    var target = ratings.price_target || {};
    var pvt = ratings.price_vs_target;
    var upsideText = "—";
    if (pvt && pvt.upside_pct != null) {
      var pct = Math.round(pvt.upside_pct);
      upsideText = (pct >= 0 ? "+" : "") + pct + "% vs $" + fmtNum(pvt.price);
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
    return (
      '<section class="ticker-detail-section">' +
      '<div class="ticker-detail-section-title">Analyst ratings</div>' +
      '<div class="stat-grid ticker-detail-panel-grid">' +
      stat("Consensus", escapeHtml(ratings.consensus || "—") + " (" + escapeHtml(ratings.analyst_count) + ")") +
      stat("Buy / Hold / Sell", escapeHtml(ratings.buy_total) + " / " + escapeHtml(ratings.distribution.hold) + " / " + escapeHtml(ratings.sell_total)) +
      stat("Avg price target", target.avg == null ? "—" : "$" + fmtNum(target.avg)) +
      stat("Target vs price", upsideText) +
      "</div>" +
      '<div class="ticker-detail-meta">Upgrade room: ' + statusChip(ratings.upgrade_room) +
      " · Downgrade room: " + statusChip(ratings.downgrade_room) + "</div>" +
      (trendRows
        ? '<div class="table-wrap"><table class="data-table ticker-detail-table"><thead><tr>' +
          "<th>Month</th><th class=\"num\">Buy</th><th class=\"num\">Hold</th>" +
          "<th class=\"num\">Sell</th><th class=\"num\">Total</th>" +
          "</tr></thead><tbody>" + trendRows + "</tbody></table></div>"
        : "") +
      "</section>"
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
      return '<div class="ticker-detail-meta">No trading days in this range.</div>';
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
    var container = panel.querySelector("#catalystCalRange");
    var startInput = panel.querySelector("#calRangeStart");
    var endInput = panel.querySelector("#calRangeEnd");
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

  function catalystActivityBodyHtml(activity) {
    catalystCalendarData = null;
    activity = activity || {};
    if (activity.status !== "ok") {
      return '<div class="ticker-detail-meta">Catalyst activity insufficient data.</div>';
    }
    var freq = activity.filing_frequency || {};
    var moves = activity.large_moves || {};
    var freqHtml = "";
    if (freq.status === "ok") {
      freqHtml =
        '<div class="stat-grid ticker-detail-panel-grid">' +
        stat("8-K filings", escapeHtml(freq.total) + " (" + escapeHtml(freq.window_months) + " mo)") +
        stat("Filings / month", fmtNum(freq.per_month)) +
        stat("Earnings / non-earnings", escapeHtml(freq.earnings) + " / " + escapeHtml(freq.non_earnings)) +
        stat("Non-earnings / month", freq.non_earnings_per_month == null ? "—" : fmtNum(freq.non_earnings_per_month)) +
        "</div>";
    }
    var movesHtml = "";
    if (moves.status === "ok") {
      movesHtml =
        '<div class="ticker-detail-meta">&gt;1σ move days: ' + escapeHtml((moves.moves || []).length) +
        " of " + escapeHtml(moves.sample_days) + " (σ = " + fmtPct(moves.stdev) + ")</div>" +
        catalystCalendarHtml(activity.calendar);
    }
    return freqHtml + movesHtml;
  }

  function catalystActivitySection(payload) {
    var body = payload.catalyst_activity === undefined
      ? '<div class="ticker-detail-meta">Loading catalyst activity…</div>'
      : catalystActivityBodyHtml(payload.catalyst_activity);
    return (
      '<section class="ticker-detail-section">' +
      '<div class="ticker-detail-section-title">Catalyst activity (8-K filings)</div>' +
      '<div id="tickerDetailCatalystBody">' + body + "</div>" +
      "</section>"
    );
  }

  function loadCatalystAsync(symbol) {
    var body = panel.querySelector("#tickerDetailCatalystBody");
    if (!body) {
      return;
    }
    fetchJson("/api/ticker-quant/" + encodeURIComponent(symbol) + "/catalyst")
      .then(function (activity) {
        if (activeSymbol !== symbol) {
          return;
        }
        body.innerHTML = catalystActivityBodyHtml(activity);
        wireCatalystCalendar();
      })
      .catch(function () {
        if (activeSymbol !== symbol) {
          return;
        }
        body.innerHTML = '<div class="ticker-detail-meta">Catalyst activity unavailable.</div>';
      });
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
      "Estimate consensus: " + _estimateConsensusText(payload.estimate_consensus) +
        "; revision trend: " + _estimateRevisionText(payload.estimate_revision_trend),
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
      backwardRatiosSection(quantPayload) +
      analystRatingsSection(quantPayload) +
      catalystActivitySection(quantPayload);
    wirePeer(quantPayload.symbol);
    loadCatalystAsync(quantPayload.symbol);
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
      apply.disabled = true;
      apply.textContent = "Comparing…";
      fetchJson("/api/ticker-quant/" + encodeURIComponent(symbol) + "?peer=" + encodeURIComponent(peer))
        .then(function (payload) {
          if (activeSymbol !== symbol) {
            return;
          }
          apply.disabled = false;
          apply.textContent = "Apply";
          var resultRegion = panel.querySelector("#tickerDetailPeerResult");
          if (resultRegion) {
            resultRegion.innerHTML = peerLine(payload.peer, payload);
          }
        })
        .catch(function (error) {
          if (activeSymbol === symbol) {
            apply.disabled = false;
            apply.textContent = "Apply";
            var resultRegion = panel.querySelector("#tickerDetailPeerResult");
            if (resultRegion) {
              resultRegion.innerHTML =
                '<div class="status-error">' + escapeHtml(error.message) + "</div>";
            }
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

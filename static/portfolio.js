(function () {
  var riskForm = document.getElementById("riskForm");
  var riskRegion = document.getElementById("riskRegion");
  var portfolioForm = document.getElementById("portfolioForm");
  var portfolioRegion = document.getElementById("portfolioRegion");
  var positionRows = document.getElementById("positionRows");
  var addPosition = document.getElementById("addPosition");

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function fmtPct(value, digits) {
    if (value == null) {
      return "—";
    }
    return (value * 100).toFixed(digits == null ? 1 : digits) + "%";
  }

  function fmtSignedPct(value, digits) {
    if (value == null) {
      return "—";
    }
    var pct = value * 100;
    return (pct >= 0 ? "+" : "") + pct.toFixed(digits == null ? 1 : digits) + "%";
  }

  function fmtNum(value, digits) {
    if (value == null) {
      return "—";
    }
    return Number(value).toFixed(digits == null ? 2 : digits);
  }

  function fmtDollars(value) {
    if (value == null) {
      return "—";
    }
    return "$" + Number(value).toLocaleString("en-US", { maximumFractionDigits: 0 });
  }

  function sideLabel(side) {
    return side === 1 || side === "long" ? "Long" : "Short";
  }

  function betaChartSvg(points) {
    if (!points.length) {
      return "";
    }
    var width = 960;
    var height = 300;
    var margin = { left: 56, right: 16, top: 16, bottom: 32 };
    var plotWidth = width - margin.left - margin.right;
    var plotHeight = height - margin.top - margin.bottom;
    var values = points.map(function (point) {
      return point.beta;
    });
    var min = Math.min.apply(null, values.concat([1]));
    var max = Math.max.apply(null, values.concat([1]));
    var pad = (max - min) * 0.08 || 0.05;
    min -= pad;
    max += pad;
    function xAt(index) {
      if (points.length === 1) {
        return margin.left + plotWidth / 2;
      }
      return margin.left + (index / (points.length - 1)) * plotWidth;
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
    var polyline = points
      .map(function (point, index) {
        return xAt(index).toFixed(1) + "," + yAt(point.beta).toFixed(1);
      })
      .join(" ");
    var refY = yAt(1);
    var dateLabels =
      '<text class="ratio-chart-axis-label" x="' + margin.left + '" y="' +
      (height - 8) + '" text-anchor="start">' + escapeHtml(points[0].end_date) + "</text>" +
      '<text class="ratio-chart-axis-label" x="' + (width - margin.right) + '" y="' +
      (height - 8) + '" text-anchor="end">' + escapeHtml(points[points.length - 1].end_date) + "</text>";
    return (
      '<svg class="ratio-chart" viewBox="0 0 ' + width + " " + height +
      '" role="img" aria-label="Rolling beta chart">' +
      gridlines +
      '<line class="ratio-chart-reference" x1="' + margin.left + '" y1="' + refY.toFixed(1) +
      '" x2="' + (width - margin.right) + '" y2="' + refY.toFixed(1) + '"></line>' +
      '<polyline class="ratio-chart-line" points="' + polyline + '"></polyline>' +
      dateLabels +
      "</svg>"
    );
  }

  function betaWindowsTable(windows) {
    var rows = windows
      .map(function (entry) {
        if (entry.status !== "ok") {
          return (
            "<tr><td>" + escapeHtml(entry.label) + "</td>" +
            '<td class="num muted-cell" colspan="2">insufficient data (n=' +
            escapeHtml(entry.sample_size) + ")</td>" +
            '<td class="num muted-cell">' + escapeHtml(entry.sample_size) + "</td></tr>"
          );
        }
        return (
          "<tr><td>" + escapeHtml(entry.label) + "</td>" +
          '<td class="num">' + fmtNum(entry.beta) + "</td>" +
          '<td class="num">' + fmtNum(entry.standard_error) + "</td>" +
          '<td class="num">' + escapeHtml(entry.sample_size) + "</td></tr>"
        );
      })
      .join("");
    return (
      '<table class="data-table"><thead><tr>' +
      "<th>Window</th><th class=\"num\">Beta</th><th class=\"num\">Std error</th><th class=\"num\">Samples</th>" +
      "</tr></thead><tbody>" + rows + "</tbody></table>"
    );
  }

  function realizedVolTable(report) {
    var horizons = [
      ["daily", "1D"],
      ["weekly", "1W"],
      ["monthly_21d", "1M (21d)"],
      ["quarterly_63d", "1Q (63d)"],
    ];
    var rows = horizons
      .map(function (horizon) {
        var entry = report[horizon[0]];
        if (!entry) {
          return "";
        }
        if (entry.status === "insufficient_data") {
          return (
            "<tr><td>" + horizon[1] + "</td>" +
            '<td class="num muted-cell" colspan="2">insufficient data (n=' +
            escapeHtml(entry.sample_size) + ", needs " + escapeHtml(entry.required) + ")</td>" +
            '<td class="num muted-cell">' + escapeHtml(entry.sample_size) + "</td></tr>"
          );
        }
        return (
          "<tr><td>" + horizon[1] + "</td>" +
          '<td class="num">' + fmtPct(entry.stdev) + "</td>" +
          '<td class="num">' + fmtPct(entry.annualized) + "</td>" +
          '<td class="num">' + escapeHtml(entry.sample_size) + "</td></tr>"
        );
      })
      .join("");
    return (
      '<table class="data-table"><thead><tr>' +
      "<th>Horizon</th><th class=\"num\">Stdev</th><th class=\"num\">Annualized</th><th class=\"num\">Samples</th>" +
      "</tr></thead><tbody>" + rows + "</tbody></table>"
    );
  }

  var riskSeedText = null;
  var analysisSeedText = null;

  function riskContextText(payload) {
    var lines = [
      "The user is viewing this ticker risk profile on the Meowstreet portfolio page. Explain or answer questions about it when asked:",
      "Symbol: " + payload.symbol + " | Benchmark: " + payload.benchmark,
      "Weekly data range: " + payload.data.weekly_start + " to " + payload.data.weekly_end +
        " (" + payload.data.weekly_count + " weeks)",
      "Beta windows:",
    ];
    (payload.beta.windows || []).forEach(function (entry) {
      if (entry.status === "ok") {
        lines.push(
          "- " + entry.label + ": beta " + fmtNum(entry.beta) +
          ", SE " + fmtNum(entry.standard_error) + ", n=" + entry.sample_size
        );
      } else {
        lines.push("- " + entry.label + ": insufficient data (n=" + entry.sample_size + ")");
      }
    });
    lines.push("Realized volatility (annualized):");
    var horizons = [
      ["daily", "1D"],
      ["weekly", "1W"],
      ["monthly_21d", "1M (21d)"],
      ["quarterly_63d", "1Q (63d)"],
    ];
    horizons.forEach(function (horizon) {
      var entry = payload.realized_volatility[horizon[0]];
      if (!entry) {
        return;
      }
      if (entry.status === "insufficient_data") {
        lines.push("- " + horizon[1] + ": insufficient data (n=" + entry.sample_size + ")");
      } else {
        lines.push(
          "- " + horizon[1] + ": " + fmtPct(entry.annualized) + " annualized" +
          " (stdev " + fmtPct(entry.stdev) + ", n=" + entry.sample_size + ")"
        );
      }
    });
    return lines.join("\n");
  }

  function renderRisk(payload) {
    var rolling = (payload.beta && payload.beta.rolling_beta) || [];
    var chart = betaChartSvg(rolling);
    riskSeedText = riskContextText(payload);
    riskRegion.innerHTML =
      '<div class="result-card">' +
      '<div class="result-company">' + escapeHtml(payload.symbol) + "</div>" +
      '<div class="result-sub">Beta vs ' + escapeHtml(payload.benchmark) +
      " · weekly data " + escapeHtml(payload.data.weekly_start) + " → " +
      escapeHtml(payload.data.weekly_end) + " (" + escapeHtml(payload.data.weekly_count) +
      " weeks)</div>" +
      '<div class="section-block">' +
      '<div class="section-title">Beta windows</div>' +
      betaWindowsTable(payload.beta.windows) +
      "</div>" +
      (chart
        ? '<div class="section-block">' +
          '<div class="section-title">Rolling 2y beta</div>' +
          chart +
          '<div class="ratio-chart-caption">Dashed line = β 1.0 (moves with the benchmark).</div>' +
          "</div>"
        : "") +
      '<div class="section-block">' +
      '<div class="section-title">Realized volatility</div>' +
      realizedVolTable(payload.realized_volatility) +
      "</div>" +
      assistantActionsHtml() +
      "</div>";
  }

  function renderRiskError(symbol, message) {
    riskSeedText = null;
    riskRegion.innerHTML =
      '<div class="result-card">' +
      '<div class="result-company">' + escapeHtml(symbol) + "</div>" +
      '<div class="status-error">' + escapeHtml(message) + "</div>" +
      "</div>";
  }

  function lookupRisk(symbol) {
    riskRegion.innerHTML =
      '<div class="lookup-loading">Loading risk profile for ' + escapeHtml(symbol) + "…</div>";
    fetch("/api/ticker-risk/" + encodeURIComponent(symbol))
      .then(function (response) {
        return response.json().then(function (body) {
          return { ok: response.ok, body: body };
        });
      })
      .then(function (result) {
        if (!result.ok) {
          renderRiskError(symbol, result.body.detail || "Risk profile lookup failed.");
          return;
        }
        renderRisk(result.body);
        askAssistant(riskSeedText, "结合当前市场环境，解读一下 " + result.body.symbol + " 的这份风险结果");
      })
      .catch(function () {
        renderRiskError(symbol, "Risk profile request failed.");
      });
  }

  function assistantActionsHtml() {
    return (
      '<div class="assistant-actions">' +
      '<button type="button" class="ghost-button assistant-ask-button">' +
      "Ask the assistant about these results</button>" +
      "</div>"
    );
  }

  function gateChip(label, tone, title) {
    return (
      '<span class="gate-chip chip-' + tone + '"' +
      (title ? ' title="' + escapeHtml(title) + '"' : "") +
      ">" + label + "</span>"
    );
  }

  function toneForStatus(status) {
    if (status === "within" || status === "aligned" || status === "valid") {
      return "positive";
    }
    if (status === "unknown") {
      return "muted";
    }
    return "warning";
  }

  function gateValueClass(gate, withinTone) {
    if (!gate || !gate.status) {
      return "";
    }
    var tone = gate.status === "within" && withinTone === false ? "warning" : toneForStatus(gate.status);
    return " value-" + tone;
  }

  function volatilitySection(section, gate) {
    if (section.status !== "ok") {
      return (
        '<div class="section-block"><div class="section-title">Volatility</div>' +
        '<div class="status-warning">Insufficient data: ' +
        escapeHtml(section.reason || "unavailable") + "</div></div>"
      );
    }
    var countCheck = section.position_count_check;
    var countChip = "";
    if (countCheck && !countCheck.within_range) {
      countChip =
        '<div class="status-warning">Position count ' + escapeHtml(countCheck.count) +
        " is outside the 8–12 guideline (" +
        escapeHtml(countCheck.warning === "under_diversified" ? "under-diversified" : "over-diversified") +
        ").</div>";
    }
    var volToneClass = gateValueClass(gate, gate && gate.realistic_band);
    var weightRows = section.positions
      .map(function (position) {
        return (
          "<tr><td>" + escapeHtml(position.symbol) + "</td>" +
          "<td>" + sideLabel(position.allocation >= 0 ? 1 : -1) + "</td>" +
          '<td class="num">' + fmtDollars(Math.abs(position.allocation)) + "</td>" +
          '<td class="num">' + fmtSignedPct(position.signed_weight) + "</td></tr>"
        );
      })
      .join("");
    var sharpeRows = section.sharpe_scenarios
      .map(function (scenario) {
        return (
          "<tr><td>" + fmtNum(scenario.sharpe, 1) + "</td>" +
          '<td class="num">' + fmtPct(scenario.expected_annual_return) + "</td></tr>"
        );
      })
      .join("");
    return (
      '<div class="section-block"><div class="section-title">Volatility</div>' +
      '<div class="stat-grid">' +
      '<div class="stat"><div class="stat-value' + volToneClass + '">' + fmtPct(section.annualized_stdev) +
      '</div><div class="stat-label">Portfolio annualized vol</div></div>' +
      '<div class="stat"><div class="stat-value">' + fmtPct(section.weekly_stdev) +
      '</div><div class="stat-label">Portfolio weekly vol</div></div>' +
      '<div class="stat"><div class="stat-value">' + fmtPct(section.average_asset_annualized_stdev) +
      '</div><div class="stat-label">Avg asset annualized vol</div></div>' +
      '<div class="stat"><div class="stat-value">' + fmtDollars(section.gross_exposure) +
      '</div><div class="stat-label">Gross exposure</div></div>' +
      "</div>" +
      countChip +
      '<table class="data-table"><thead><tr>' +
      "<th>Symbol</th><th>Side</th><th class=\"num\">Allocation</th><th class=\"num\">Signed weight</th>" +
      "</tr></thead><tbody>" + weightRows + "</tbody></table>" +
      '<div class="section-title">Sharpe scenarios</div>' +
      '<table class="data-table"><thead><tr>' +
      "<th>Sharpe</th><th class=\"num\">Expected annual return</th>" +
      "</tr></thead><tbody>" + sharpeRows + "</tbody></table>" +
      "</div>"
    );
  }

  function corrColor(value) {
    var intensity = Math.min(Math.abs(value), 1) * 0.3 + 0.04;
    if (value > 0) {
      return "rgba(154, 59, 46, " + intensity.toFixed(2) + ")";
    }
    if (value < 0) {
      return "rgba(45, 122, 74, " + intensity.toFixed(2) + ")";
    }
    return "transparent";
  }

  function correlationSection(section, gate) {
    if (section.status !== "ok") {
      return (
        '<div class="section-block"><div class="section-title">Correlation</div>' +
        '<div class="status-warning">Insufficient data: ' +
        escapeHtml(section.reason || "unavailable") + "</div></div>"
      );
    }
    var avgRows = section.symbols
      .map(function (symbol, index) {
        return (
          "<tr><td>" + escapeHtml(symbol) + "</td>" +
          "<td>" + sideLabel(section.sides[index]) + "</td>" +
          '<td class="num">' + fmtNum(section.per_position_average[index]) + "</td></tr>"
        );
      })
      .join("");
    var matrix = "";
    if (section.symbols.length <= 12) {
      var head =
        "<tr><th></th>" +
        section.symbols
          .map(function (symbol) {
            return "<th>" + escapeHtml(symbol) + "</th>";
          })
          .join("") +
        "</tr>";
      var body = section.symbols
        .map(function (symbol, row) {
          var cells = section.matrix[row]
            .map(function (value, col) {
              if (value == null) {
                return '<td class="matrix-blank"></td>';
              }
              return (
                '<td style="background:' + corrColor(value) + '">' +
                fmtNum(value) + "</td>"
              );
            })
            .join("");
          return "<tr><th>" + escapeHtml(symbol) + "</th>" + cells + "</tr>";
        })
        .join("");
      matrix =
        '<div class="section-title">Signed correlation matrix</div>' +
        '<table class="matrix-table"><thead>' + head + "</thead><tbody>" + body +
        "</tbody></table>";
    }
    return (
      '<div class="section-block"><div class="section-title">Correlation</div>' +
      '<div class="stat-grid">' +
      '<div class="stat"><div class="stat-value' + gateValueClass(gate) + '">' + fmtNum(section.overall_average) +
      '</div><div class="stat-label">Overall avg signed correlation</div></div>' +
      "</div>" +
      '<table class="data-table"><thead><tr>' +
      "<th>Symbol</th><th>Side</th><th class=\"num\">Avg signed correlation</th>" +
      "</tr></thead><tbody>" + avgRows + "</tbody></table>" +
      matrix +
      '<div class="section-note">' + escapeHtml(section.disclaimer) +
      ". Negative signed correlation = diversifying for the long/short book.</div>" +
      "</div>"
    );
  }

  function betaSection(section, gate) {
    if (section.status !== "ok" && !section.per_position) {
      return (
        '<div class="section-block"><div class="section-title">Beta</div>' +
        '<div class="status-warning">Insufficient data: ' +
        escapeHtml(section.reason || "unavailable") + "</div></div>"
      );
    }
    var perPositionRows = section.per_position
      .map(function (entry) {
        var betaCell =
          entry.status === "ok"
            ? '<td class="num">' + fmtNum(entry.beta) + "</td>" +
              '<td class="num">' + fmtNum(entry.standard_error) + "</td>"
            : '<td class="num muted-cell" colspan="2">insufficient data (n=' +
              escapeHtml(entry.sample_size) + ")</td>";
        return (
          "<tr><td>" + escapeHtml(entry.symbol) + "</td>" +
          "<td>" + sideLabel(entry.side) + "</td>" +
          betaCell + "</tr>"
        );
      })
      .join("");
    var html =
      '<div class="section-block"><div class="section-title">Beta (2y window)</div>';
    if (section.portfolio) {
      var portfolioRows = section.portfolio.positions
        .map(function (position) {
          return (
            "<tr><td>" + escapeHtml(position.symbol) + "</td>" +
            "<td>" + sideLabel(position.side) + "</td>" +
            '<td class="num">' + fmtNum(position.beta) + "</td>" +
            '<td class="num">' + fmtSignedPct(position.net_weight) + "</td>" +
            '<td class="num">' + fmtNum(position.net_weighted_beta) + "</td></tr>"
          );
        })
        .join("");
      html +=
        '<div class="stat-grid">' +
        '<div class="stat"><div class="stat-value' + gateValueClass(gate) + '">' + fmtNum(section.portfolio.portfolio_beta) +
        '</div><div class="stat-label">Portfolio beta (net)</div></div>' +
        '<div class="stat"><div class="stat-value">' + fmtSignedPct(section.portfolio.net_weight) +
        '</div><div class="stat-label">Net weight</div></div>' +
        '<div class="stat"><div class="stat-value">' + fmtDollars(section.portfolio.gross_exposure) +
        '</div><div class="stat-label">Gross exposure</div></div>' +
        "</div>" +
        '<table class="data-table"><thead><tr>' +
        "<th>Symbol</th><th>Side</th><th class=\"num\">Beta</th><th class=\"num\">Net weight</th><th class=\"num\">Net weighted beta</th>" +
        "</tr></thead><tbody>" + portfolioRows + "</tbody></table>";
      if (section.excluded_from_portfolio && section.excluded_from_portfolio.length) {
        html +=
          '<div class="section-note">Excluded from portfolio beta (insufficient data): ' +
          section.excluded_from_portfolio.map(escapeHtml).join(", ") + ".</div>";
      }
    } else {
      html +=
        '<div class="status-warning">Insufficient data: ' +
        escapeHtml(section.reason || "portfolio beta unavailable") + "</div>";
    }
    html +=
      '<div class="section-title">Per-position beta</div>' +
      '<table class="data-table"><thead><tr>' +
      "<th>Symbol</th><th>Side</th><th class=\"num\">Beta</th><th class=\"num\">Std error</th>" +
      "</tr></thead><tbody>" + perPositionRows + "</tbody></table>";
    if (section.sizing) {
      if (section.sizing.status === "skipped") {
        html +=
          '<div class="status-warning">Sizing scenarios skipped: ' +
          escapeHtml(section.sizing.reason) + "</div>";
      } else {
        var scenarios = [
          ["equal_weight", "Equal weight"],
          ["risk_parity", "Risk parity"],
          ["beta_parity", "Beta parity"],
        ];
        var symbols = section.sizing.equal_weight.positions.map(function (position) {
          return position.symbol;
        });
        var sizingHead =
          "<tr><th>Symbol</th>" +
          scenarios
            .map(function (scenario) {
              return (
                '<th class="num">' + scenario[1] + ' wt</th><th class="num">' +
                scenario[1] + " shares</th>"
              );
            })
            .join("") +
          "</tr>";
        var sizingBody = symbols
          .map(function (symbol, index) {
            var cells = scenarios
              .map(function (scenario) {
                var position = section.sizing[scenario[0]].positions[index];
                return (
                  '<td class="num">' + fmtPct(position.weight) + "</td>" +
                  '<td class="num">' + escapeHtml(position.shares) + "</td>"
                );
              })
              .join("");
            return "<tr><td>" + escapeHtml(symbol) + "</td>" + cells + "</tr>";
          })
          .join("");
        html +=
          '<div class="section-title">Sizing scenarios</div>' +
          '<table class="data-table"><thead>' + sizingHead + "</thead><tbody>" +
          sizingBody + "</tbody></table>" +
          '<div class="section-note">' + escapeHtml(section.sizing.equal_weight.note) + ".</div>";
      }
    }
    return html + "</div>";
  }

  function gatesSection(gates) {
    var chips = [];
    var vol = gates.volatility;
    if (vol) {
      if (vol.status === "unknown") {
        chips.push(gateChip("Volatility gate — unknown", "muted", vol.reason));
      } else {
        var volLabel =
          "Volatility " + fmtPct(vol.annual_vol) + " — " + vol.status + " target 15–30%";
        if (vol.status === "within" && !vol.realistic_band) {
          volLabel += " (above realistic 22.5%)";
        }
        var volTone = vol.status === "within" && vol.realistic_band ? "positive" : "warning";
        chips.push(gateChip(volLabel, volTone, "Target 15–30%, realistic 15–22.5%"));
      }
    }
    var corr = gates.correlation;
    if (corr) {
      if (corr.status === "unknown") {
        chips.push(gateChip("Correlation gate — unknown", "muted", corr.reason));
      } else {
        chips.push(
          gateChip(
            "Avg correlation " + fmtNum(corr.avg_correlation) + " — " + corr.status + " ±0.3",
            toneForStatus(corr.status)
          )
        );
      }
    }
    var netBeta = gates.net_beta;
    if (netBeta) {
      if (netBeta.status === "unknown") {
        chips.push(gateChip("Net beta gate — unknown", "muted", netBeta.reason));
      } else {
        chips.push(
          gateChip(
            "Net beta " + fmtNum(netBeta.portfolio_beta) + " — " + netBeta.status + " ±30%",
            toneForStatus(netBeta.status)
          )
        );
      }
    }
    var count = gates.position_count;
    if (count) {
      if (count.status === "unknown") {
        chips.push(
          gateChip("Position count — unknown", "muted", count.reason || "capital outside tiers")
        );
      } else {
        var tierLabel =
          count.tier
            ? count.tier.min_positions + "–" + count.tier.max_positions
            : "n/a";
        chips.push(
          gateChip(
            "Positions " + count.position_count + " of " + tierLabel + " — " + count.status,
            toneForStatus(count.status),
            "Tier for " + fmtDollars(count.margin_capital) + " margin capital"
          )
        );
      }
    }
    var alignment = gates.beta_macro_alignment;
    if (alignment) {
      if (alignment.status === "unknown") {
        chips.push(gateChip("Beta vs declared bias — unknown", "muted", alignment.reason));
      } else {
        chips.push(
          gateChip(
            "Beta vs " + alignment.declared_bias + " bias — " + alignment.status,
            toneForStatus(alignment.status),
            "Portfolio beta " + fmtNum(alignment.portfolio_beta)
          )
        );
      }
    }
    var targets = gates.return_targets;
    if (targets) {
      if (targets.status === "unknown") {
        chips.push(gateChip("Return target — unknown", "muted", targets.reason));
      } else {
        chips.push(
          gateChip(
            "Min expected return ≥ " + fmtPct(targets.expected_return) +
              " (" + escapeHtml(targets.instrument) + ", Sharpe " + fmtNum(targets.min_sharpe, 1) + ")",
            "muted",
            "Min Sharpe × annualized vol"
          )
        );
      }
    }
    if (!chips.length) {
      return "";
    }
    return (
      '<div class="section-block"><div class="section-title">Gates</div>' +
      '<div class="gate-chips">' + chips.join("") + "</div></div>"
    );
  }

  function outperformanceSection(section) {
    if (!section) {
      return "";
    }
    var tone = section.status === "valid" ? "positive" : "warning";
    var text;
    if (section.status === "valid") {
      text = section.conclusion;
    } else if (section.status === "invalid_unequal_gross_weights") {
      text =
        section.conclusion +
        " (gross long " + fmtDollars(section.gross_long) +
        " vs gross short " + fmtDollars(section.gross_short) + ")";
    } else {
      text = "Outperformance inference unavailable: " + (section.reason || "insufficient data");
    }
    return (
      '<div class="section-block"><div class="section-title">Outperformance inference</div>' +
      '<span class="tag-chip chip-' + tone + '">' + escapeHtml(section.status) + "</span>" +
      '<div class="section-note">' + escapeHtml(text) + ".</div></div>"
    );
  }

  function analysisContextText(payload) {
    var lines = [
      "The user is viewing this portfolio analysis on the Meowstreet portfolio page. Explain or answer questions about it when asked:",
    ];
    var volatility = payload.volatility;
    if (volatility && volatility.status === "ok") {
      lines.push(
        "Positions: " +
          volatility.positions
            .map(function (position) {
              return (
                position.symbol + " " +
                sideLabel(position.allocation >= 0 ? 1 : -1).toLowerCase() + " " +
                fmtDollars(Math.abs(position.allocation))
              );
            })
            .join("; ")
      );
      if (payload.window) {
        lines.push(
          "Window: " + payload.window.start_date + " to " + payload.window.end_date +
          " (" + payload.window.weekly_count + " weeks)"
        );
      }
      lines.push(
        "Portfolio annualized vol " + fmtPct(volatility.annualized_stdev) +
        ", weekly vol " + fmtPct(volatility.weekly_stdev) +
        ", avg asset annualized vol " + fmtPct(volatility.average_asset_annualized_stdev) +
        ", gross exposure " + fmtDollars(volatility.gross_exposure)
      );
    } else if (volatility) {
      lines.push("Volatility: insufficient data (" + (volatility.reason || "unavailable") + ")");
    }
    var correlation = payload.correlation;
    if (correlation && correlation.status === "ok") {
      lines.push("Overall avg signed correlation: " + fmtNum(correlation.overall_average));
    }
    var beta = payload.beta;
    if (beta && beta.portfolio) {
      lines.push(
        "Portfolio beta (net): " + fmtNum(beta.portfolio.portfolio_beta) +
        ", net weight " + fmtSignedPct(beta.portfolio.net_weight) +
        ", gross exposure " + fmtDollars(beta.portfolio.gross_exposure)
      );
      if (beta.excluded_from_portfolio && beta.excluded_from_portfolio.length) {
        lines.push(
          "Excluded from portfolio beta (insufficient data): " +
          beta.excluded_from_portfolio.join(", ")
        );
      }
    } else if (beta) {
      lines.push("Portfolio beta: insufficient data (" + (beta.reason || "unavailable") + ")");
    }
    var gates = payload.gates || {};
    var gateNames = {
      volatility: "Volatility",
      correlation: "Correlation",
      net_beta: "Net beta",
      position_count: "Position count",
      beta_macro_alignment: "Beta vs declared bias",
      return_targets: "Return target",
    };
    var gateLines = [];
    Object.keys(gateNames).forEach(function (key) {
      var gate = gates[key];
      if (gate) {
        gateLines.push(gateNames[key] + " " + gate.status);
      }
    });
    if (gateLines.length) {
      lines.push("Gates: " + gateLines.join("; "));
    }
    if (payload.missing_inputs && payload.missing_inputs.length) {
      lines.push(
        "Missing inputs: " +
          payload.missing_inputs
            .map(function (item) {
              return item.symbol + " (" + item.reason + ")";
            })
            .join("; ")
      );
    }
    var inference = payload.outperformance_inference;
    if (inference) {
      if (inference.conclusion) {
        lines.push("Outperformance inference (" + inference.status + "): " + inference.conclusion);
      } else {
        lines.push(
          "Outperformance inference unavailable: " + (inference.reason || "insufficient data")
        );
      }
    }
    return lines.join("\n");
  }

  function renderAnalysis(payload) {
    var windowLine = payload.window
      ? '<div class="result-sub">Common weekly window ' +
        escapeHtml(payload.window.start_date) + " → " + escapeHtml(payload.window.end_date) +
        " (" + escapeHtml(payload.window.weekly_count) + " weeks)</div>"
      : '<div class="result-sub">No common weekly window across positions.</div>';
    var missing = "";
    if (payload.missing_inputs && payload.missing_inputs.length) {
      missing =
        '<div class="status-warning">Missing inputs:<div class="missing-list">' +
        payload.missing_inputs
          .map(function (item) {
            return escapeHtml(item.symbol) + " — " + escapeHtml(item.reason);
          })
          .join("<br>") +
        "</div></div>";
    }
    analysisSeedText = analysisContextText(payload);
    portfolioRegion.innerHTML =
      '<div class="result-card">' +
      '<div class="result-company">Portfolio analysis</div>' +
      windowLine +
      missing +
      gatesSection(payload.gates || {}) +
      volatilitySection(payload.volatility, (payload.gates || {}).volatility) +
      correlationSection(payload.correlation, (payload.gates || {}).correlation) +
      betaSection(payload.beta, (payload.gates || {}).net_beta) +
      outperformanceSection(payload.outperformance_inference) +
      assistantActionsHtml() +
      "</div>";
  }

  function renderAnalysisError(message) {
    analysisSeedText = null;
    portfolioRegion.innerHTML =
      '<div class="result-card"><div class="status-error">' +
      escapeHtml(message) + "</div></div>";
  }

  function positionRowHtml() {
    return (
      '<div class="position-row">' +
      '<input type="text" class="pos-symbol" placeholder="NVDA" autocomplete="off" />' +
      '<select class="pos-side">' +
      '<option value="long">Long</option>' +
      '<option value="short">Short</option>' +
      "</select>" +
      '<input type="number" class="pos-allocation" min="0" step="any" placeholder="10000" autocomplete="off" />' +
      '<button type="button" class="remove-row" aria-label="Remove position">&times;</button>' +
      "</div>"
    );
  }

  function addRow() {
    positionRows.insertAdjacentHTML("beforeend", positionRowHtml());
  }

  function collectPositions() {
    var rows = positionRows.querySelectorAll(".position-row");
    var positions = [];
    var error = null;
    Array.prototype.forEach.call(rows, function (row) {
      var symbol = row.querySelector(".pos-symbol").value.trim();
      var side = row.querySelector(".pos-side").value;
      var allocationRaw = row.querySelector(".pos-allocation").value.trim();
      if (!symbol && !allocationRaw) {
        return;
      }
      if (!symbol || !allocationRaw) {
        error = "Each filled row needs both a symbol and an allocation.";
        return;
      }
      var allocation = Number(allocationRaw);
      if (!isFinite(allocation) || allocation <= 0) {
        error = "Allocation for " + symbol.toUpperCase() + " must be a positive number.";
        return;
      }
      positions.push({
        symbol: symbol.toUpperCase(),
        side: side,
        allocation: allocation,
      });
    });
    if (!error && !positions.length) {
      error = "Add at least one position with a symbol and allocation.";
    }
    return { positions: positions, error: error };
  }

  function analyzePortfolio() {
    var collected = collectPositions();
    if (collected.error) {
      renderAnalysisError(collected.error);
      return;
    }
    var payload = { positions: collected.positions };
    var marginRaw = portfolioForm.elements.marginCapital.value.trim();
    if (marginRaw) {
      var margin = Number(marginRaw);
      if (!isFinite(margin) || margin <= 0) {
        renderAnalysisError("Margin capital must be a positive number.");
        return;
      }
      payload.margin_capital = margin;
    }
    var declaredBias = portfolioForm.elements.declaredBias.value;
    if (declaredBias) {
      payload.declared_bias = declaredBias;
    }
    var instrument = portfolioForm.elements.instrument.value;
    if (instrument) {
      payload.instrument = instrument;
    }
    portfolioRegion.innerHTML =
      '<div class="lookup-loading">Analyzing ' + payload.positions.length + " positions…</div>";
    fetch("/api/portfolio-analysis", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    })
      .then(function (response) {
        return response.json().then(function (body) {
          return { ok: response.ok, body: body };
        });
      })
      .then(function (result) {
        if (!result.ok) {
          renderAnalysisError(result.body.detail || "Portfolio analysis failed.");
          return;
        }
        renderAnalysis(result.body);
        askAssistant(analysisSeedText, "结合当前市场环境，解读一下这个组合的分析结果");
      })
      .catch(function () {
        renderAnalysisError("Portfolio analysis request failed.");
      });
  }

  addPosition.addEventListener("click", addRow);

  positionRows.addEventListener("click", function (event) {
    var button = event.target.closest(".remove-row");
    if (button) {
      button.closest(".position-row").remove();
    }
  });

  riskForm.addEventListener("submit", function (event) {
    event.preventDefault();
    var symbol = riskForm.elements.symbol.value.trim();
    if (symbol) {
      lookupRisk(symbol);
    }
  });

  portfolioForm.addEventListener("submit", function (event) {
    event.preventDefault();
    analyzePortfolio();
  });

  function askAssistant(seedText, question) {
    if (
      seedText &&
      window.marketAssistant &&
      typeof window.marketAssistant.openWithContext === "function"
    ) {
      var options = { seedText: seedText };
      if (question) {
        options.question = question;
      }
      window.marketAssistant.openWithContext(options);
    }
  }

  riskRegion.addEventListener("click", function (event) {
    if (event.target.closest(".assistant-ask-button")) {
      askAssistant(riskSeedText);
    }
  });

  portfolioRegion.addEventListener("click", function (event) {
    if (event.target.closest(".assistant-ask-button")) {
      askAssistant(analysisSeedText);
    }
  });

  for (var i = 0; i < 4; i += 1) {
    addRow();
  }
})();

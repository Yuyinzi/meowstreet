(function () {
  var form = document.getElementById("lookupForm");
  var region = document.getElementById("resultRegion");
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

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    var symbol = form.elements.symbol.value.trim();
    if (symbol) {
      lookup(symbol);
    }
  });
})();

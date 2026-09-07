(function () {
  var CHANNELS = [
    { key: "press_releases", label: "Press Releases" },
    { key: "events_presentations", label: "Events &amp; Presentations" },
  ];

  var STATUS_LABELS = {
    complete: "Complete coverage",
    partial: "Partial coverage",
    missing: "No source",
    unsupported: "Unsupported archive",
    failed: "Extraction failed",
    discovery_required: "Discovery required",
    unknown: "Coverage unknown",
  };

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function requireOkJson(response) {
    if (!response.ok) {
      throw new Error("catalyst research request failed");
    }
    return response.json();
  }

  function fmt(value) {
    if (value == null) {
      return "—";
    }
    return Number(value).toFixed(2);
  }

  function statusChip(status) {
    var tone = status || "unknown";
    var label = STATUS_LABELS[tone] || String(tone).replace(/_/g, " ");
    return (
      '<span class="catalyst-research-chip catalyst-research-chip-' +
      escapeHtml(tone) + '">' + escapeHtml(label) + "</span>"
    );
  }

  function notResearchedHtml(payload) {
    var actions = (payload && payload.next_actions) || [];
    var actionHtml = actions.length
      ? '<div class="catalyst-research-next">Next step: <code>' +
        escapeHtml(actions[0]) + "</code></div>"
      : "";
    return (
      '<div class="catalyst-research-note">No IR communication research has been run for this ticker yet.</div>' +
      actionHtml
    );
  }

  function row(label, value) {
    return (
      '<div class="catalyst-research-row"><span class="catalyst-research-row-label">' +
      escapeHtml(label) + '</span><span class="catalyst-research-row-value">' +
      value + "</span></div>"
    );
  }

  function channelHtml(label, channel) {
    var title = '<div class="catalyst-research-channel-title">' + label + "</div>";
    if (!channel || typeof channel !== "object") {
      return (
        '<div class="catalyst-research-channel">' +
        '<div class="catalyst-research-channel-head">' + title + "</div>" +
        '<div class="catalyst-research-note">Channel data unavailable.</div>' +
        "</div>"
      );
    }
    var rows = "";
    if (channel.total != null) {
      rows += row("Total", escapeHtml(channel.total));
    }
    if (channel.earnings != null) {
      rows += row("Earnings", escapeHtml(channel.earnings));
    }
    if (channel.non_earnings != null) {
      rows += row("Non-earnings", escapeHtml(channel.non_earnings));
    }
    if (channel.ambiguous != null) {
      rows += row("Ambiguous", escapeHtml(channel.ambiguous));
    }
    var frequency = "";
    if (channel.per_month != null) {
      frequency = fmt(channel.per_month) + " / month";
    } else if (channel.per_quarter != null) {
      frequency = fmt(channel.per_quarter) + " / quarter";
    } else if (channel.per_year != null) {
      frequency = fmt(channel.per_year) + " / year";
    }
    if (frequency) {
      rows += row("Frequency", escapeHtml(frequency));
    } else {
      rows += row(
        "Frequency",
        '<span class="catalyst-research-muted">not estimable for the observed window</span>'
      );
    }
    var notes = "";
    if (channel.status === "partial") {
      notes +=
        '<div class="catalyst-research-note catalyst-research-note-partial">Partial coverage: counts reflect only the observed window, not the full requested window.</div>';
    } else if (channel.status === "unsupported") {
      notes +=
        '<div class="catalyst-research-note">This channel archive is unsupported; no valid counts are reported.</div>';
    } else if (channel.status === "missing" || channel.status === "failed" || channel.status === "discovery_required") {
      notes +=
        '<div class="catalyst-research-note">Coverage for this channel is unavailable (' +
        escapeHtml(String(channel.status).replace(/_/g, " ")) + ").</div>";
    }
    if (channel.ambiguous > 0) {
      notes +=
        '<div class="catalyst-research-note">' + escapeHtml(channel.ambiguous) +
        " record(s) have ambiguous earnings classification; non-earnings frequency is withheld.</div>";
    }
    return (
      '<div class="catalyst-research-channel">' +
      '<div class="catalyst-research-channel-head">' + title + statusChip(channel.status) + "</div>" +
      '<div class="catalyst-research-rows">' + rows + "</div>" +
      notes +
      "</div>"
    );
  }

  function channelLabel(sourceType) {
    for (var i = 0; i < CHANNELS.length; i += 1) {
      if (CHANNELS[i].key === sourceType) {
        return CHANNELS[i].label;
      }
    }
    return escapeHtml(String(sourceType || "source").replace(/_/g, " "));
  }

  function sourceHtml(source) {
    var details = [];
    if (source.coverage_start && source.coverage_end) {
      details.push("coverage " + source.coverage_start + " → " + source.coverage_end);
    }
    if (source.observation_count != null) {
      details.push(source.observation_count + " observations");
    }
    if (source.execution_path) {
      details.push("path: " + source.execution_path);
    }
    if (source.discovery_provider) {
      details.push("discovered via " + source.discovery_provider);
    }
    var url = source.url
      ? '<a class="catalyst-research-source-url" href="' + escapeHtml(source.url) +
        '" target="_blank" rel="noopener noreferrer">' + escapeHtml(source.url) + "</a>"
      : "";
    var truncation = source.truncation_reason
      ? '<div class="catalyst-research-note">Truncated: ' +
        escapeHtml(String(source.truncation_reason).replace(/_/g, " ")) + ".</div>"
      : "";
    return (
      '<div class="catalyst-research-source">' +
      '<div class="catalyst-research-source-head">' +
      '<span class="catalyst-research-source-name">' + channelLabel(source.source_type) + "</span>" +
      statusChip(source.extraction_status) +
      "</div>" +
      url +
      '<div class="catalyst-research-source-meta">' + escapeHtml(details.join(" · ")) + "</div>" +
      truncation +
      "</div>"
    );
  }

  function sourcesHtml(sources) {
    if (!sources || !sources.length) {
      return "";
    }
    return (
      '<div class="catalyst-research-sources">' +
      sources.map(sourceHtml).join("") +
      "</div>"
    );
  }

  function warningsHtml(warnings) {
    if (!warnings || !warnings.length) {
      return "";
    }
    var usedFallback = warnings.some(function (warning) {
      return String(warning).indexOf("fallback") !== -1;
    });
    var items = warnings
      .map(function (warning) {
        return "<li>" + escapeHtml(String(warning).replace(/_/g, " ")) + "</li>";
      })
      .join("");
    return (
      '<div class="catalyst-research-warnings">' +
      (usedFallback
        ? '<div class="catalyst-research-warnings-note">This result was completed through a fallback provider; the fallback provenance is retained.</div>'
        : "") +
      "<ul>" + items + "</ul>" +
      "</div>"
    );
  }

  function render(payload) {
    if (!payload || payload.status === "not_researched") {
      return notResearchedHtml(payload);
    }
    var statistics = payload.statistics || {};
    var meta = [];
    if (payload.as_of) {
      meta.push("as of " + payload.as_of);
    }
    if (payload.requested_window && payload.requested_window.years != null) {
      meta.push(payload.requested_window.years + "-year requested window");
    }
    if (payload.completed_at) {
      meta.push("researched " + payload.completed_at);
    }
    if (payload.status === "completed_partial") {
      meta.push("partial result");
    }
    if (payload.latest_job_id && payload.latest_job_id !== payload.job_id && payload.latest_job_status) {
      meta.push("latest job: " + payload.latest_job_status);
    }
    var nextActions = (payload.next_actions || []).length
      ? '<div class="catalyst-research-next">Next: ' +
        escapeHtml(payload.next_actions.join("; ")) + "</div>"
      : "";
    return (
      '<div class="catalyst-research">' +
      '<div class="catalyst-research-meta">' + escapeHtml(meta.join(" · ")) + "</div>" +
      '<div class="catalyst-research-grid">' +
      channelHtml("Press Releases", statistics.press_releases) +
      channelHtml("Events &amp; Presentations", statistics.events_presentations) +
      "</div>" +
      sourcesHtml(payload.sources) +
      warningsHtml(payload.warnings) +
      nextActions +
      "</div>"
    );
  }

  function load(symbol, options) {
    options = options || {};
    return fetch("/api/ticker-quant/" + encodeURIComponent(symbol) + "/catalyst-research")
      .then(requireOkJson)
      .then(function (payload) {
        if (options.isCurrent && options.onResult && options.isCurrent(symbol)) {
          options.onResult(payload, render(payload));
        }
        return payload;
      });
  }

  window.CatalystResearch = { load: load, render: render };
})();

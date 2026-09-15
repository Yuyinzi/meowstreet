(function () {
  var CHANNELS = [
    { key: "press_releases", label: "Press Releases" },
    { key: "events_presentations", label: "Events &amp; Presentations" },
  ];

  var STATUS_LABELS = {
    complete: "Complete coverage",
    partial: "Partial coverage",
    observed_partial: "Observed partial history",
    missing: "No source",
    unsupported: "Unsupported archive",
    failed: "Extraction failed",
    discovery_required: "Discovery required",
    unknown: "Coverage unknown",
  };

  var ACTIVITY_STATE_LABELS = {
    earnings: "Earnings",
    non_earnings: "News / Event",
    ambiguous: "Ambiguous",
  };

  var ACTIVITY_CHANNEL_LABELS = {
    press_releases: "Press release",
    events_presentations: "Event / presentation",
    earnings_results: "Earnings",
  };

  var PROVIDER_LABELS = {
    feed_metadata: "Feed metadata",
    direct_http: "Direct fetch",
    firecrawl: "Firecrawl",
    manual: "Manual",
  };

  var CATALYST_TYPE_LABELS = {
    earnings_results: "Earnings results",
    guidance_outlook: "Guidance / outlook",
    product_launch: "Product launch",
    partnership_contract: "Partnership / contract",
    corporate_restructuring: "Restructuring / M&A",
    management_change: "Management change",
    capital_markets: "Capital markets",
    regulatory_government: "Regulatory / government",
    investor_event: "Investor event",
    operational_milestone: "Operational milestone",
    pr_other: "Other PR",
    ambiguous: "Ambiguous",
  };

  var MEANINGFUL_LABELS = {
    meaningful: "Meaningful",
    non_meaningful: "Non-meaningful",
    ambiguous: "Ambiguous",
  };

  var POLL_INTERVAL_MS = 10000;
  var POLL_TIMEOUT_MS = 30 * 60 * 1000;
  var START_WINDOW_MS = 60000;
  var triggered = {};

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

  function cliActionHtml(payload) {
    var actions = (payload && payload.next_actions) || [];
    return actions.length
      ? '<div class="catalyst-research-next">Next step: <code>' +
        escapeHtml(actions[0]) + "</code></div>"
      : "";
  }

  function notResearchedHtml(payload) {
    return (
      '<div class="catalyst-research-note">No IR communication research has been run for this ticker yet.</div>' +
      cliActionHtml(payload)
    );
  }

  function researchingHtml(payload) {
    var ticker = payload && payload.ticker ? String(payload.ticker) : "this ticker";
    return (
      '<div class="catalyst-research-progress">' +
      '<span class="catalyst-research-spinner" aria-hidden="true"></span>' +
      "<span>Researching IR communication history for " + escapeHtml(ticker) +
      ". This usually takes a few minutes; this section will refresh on its own.</span>" +
      "</div>"
    );
  }

  function failedHtml(payload) {
    return (
      '<div class="catalyst-research-note">IR communication research did not complete.</div>' +
      cliActionHtml(payload)
    );
  }

  function timeoutHtml(payload) {
    return (
      '<div class="catalyst-research-note">Research is taking longer than expected; reload this page later to see the result.</div>' +
      cliActionHtml(payload)
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
    var coverageStatus = channel.coverage_status || channel.status;
    var observedPartial = coverageStatus === "observed_partial";
    var total = channel.observed_total == null ? channel.total : channel.observed_total;
    var earnings = channel.observed_earnings == null ? channel.earnings : channel.observed_earnings;
    var nonEarnings = channel.observed_non_earnings == null ? channel.non_earnings : channel.observed_non_earnings;
    var ambiguous = channel.observed_ambiguous == null ? channel.ambiguous : channel.observed_ambiguous;
    var rows = "";
    var totalLabel = observedPartial ? "Observed communications" : "Total";
    if (observedPartial && total === 0) {
      rows += row(
        totalLabel,
        '<span class="catalyst-research-muted">none observed in the sampled window</span>'
      );
    } else if (total != null) {
      rows += row(totalLabel, escapeHtml(total));
    }
    if (earnings != null) {
      rows += row("Earnings", escapeHtml(earnings));
    }
    if (nonEarnings != null) {
      rows += row("Non-earnings", escapeHtml(nonEarnings));
    }
    if (ambiguous != null) {
      rows += row("Ambiguous", escapeHtml(ambiguous));
    }
    var perMonth = channel.observed_non_earnings_per_month == null ? channel.per_month : channel.observed_non_earnings_per_month;
    var perQuarter = channel.observed_non_earnings_per_quarter == null ? channel.per_quarter : channel.observed_non_earnings_per_quarter;
    var perYear = channel.observed_non_earnings_per_year == null ? channel.per_year : channel.observed_non_earnings_per_year;
    var observedFrequency =
      channel.observed_non_earnings_per_month != null ||
      channel.observed_non_earnings_per_quarter != null ||
      channel.observed_non_earnings_per_year != null;
    var frequencyLabel = observedFrequency ? "Observed non-earnings frequency" : "Frequency";
    var frequency = "";
    if (perMonth != null) {
      frequency = fmt(perMonth) + " / month";
    } else if (perQuarter != null) {
      frequency = fmt(perQuarter) + " / quarter";
    } else if (perYear != null) {
      frequency = fmt(perYear) + " / year";
    }
    if (frequency) {
      rows += row(frequencyLabel, escapeHtml(frequency));
    } else {
      rows += row(
        frequencyLabel,
        '<span class="catalyst-research-muted">not estimable for the observed window</span>'
      );
    }
    if (channel.median_days_between_observed_non_earnings != null) {
      rows += row(
        "Median gap between non-earnings",
        escapeHtml(channel.median_days_between_observed_non_earnings) + " days"
      );
    }
    var typeCounts = channel.catalyst_type_counts;
    if (typeCounts && typeof typeCounts === "object") {
      var typeParts = [];
      for (var typeKey in typeCounts) {
        if (Object.prototype.hasOwnProperty.call(typeCounts, typeKey)) {
          typeParts.push((CATALYST_TYPE_LABELS[typeKey] || String(typeKey).replace(/_/g, " ")) + " " + typeCounts[typeKey]);
        }
      }
      if (typeParts.length) {
        rows += row("Catalyst types", escapeHtml(typeParts.join(" · ")));
      }
    }
    var meaningfulCounts = channel.meaningful_counts;
    if (meaningfulCounts && typeof meaningfulCounts === "object") {
      var meaningfulParts = [];
      for (var meaningfulKey in meaningfulCounts) {
        if (Object.prototype.hasOwnProperty.call(meaningfulCounts, meaningfulKey)) {
          meaningfulParts.push((MEANINGFUL_LABELS[meaningfulKey] || meaningfulKey) + " " + meaningfulCounts[meaningfulKey]);
        }
      }
      if (meaningfulParts.length) {
        rows += row("Meaningfulness", escapeHtml(meaningfulParts.join(" · ")));
      }
    }
    var notes = "";
    if (observedPartial) {
      notes +=
        '<div class="catalyst-research-note catalyst-research-note-partial">' +
        escapeHtml(channel.coverage_warning || "Observed history may omit official records; an empty sample is not proof of zero history.") +
        "</div>";
    } else if (coverageStatus === "partial") {
      notes +=
        '<div class="catalyst-research-note catalyst-research-note-partial">Partial coverage: counts reflect only the observed window, not the full requested window.</div>';
    } else if (coverageStatus === "unsupported") {
      notes +=
        '<div class="catalyst-research-note">This channel archive is unsupported; no valid counts are reported.</div>';
    } else if (coverageStatus === "missing" || coverageStatus === "failed" || coverageStatus === "discovery_required") {
      notes +=
        '<div class="catalyst-research-note">Coverage for this channel is unavailable (' +
        escapeHtml(String(coverageStatus).replace(/_/g, " ")) + ").</div>";
    }
    if (ambiguous > 0) {
      notes +=
        '<div class="catalyst-research-note">' + escapeHtml(ambiguous) +
        " record(s) have ambiguous earnings classification; non-earnings frequency is withheld.</div>";
    }
    return (
      '<div class="catalyst-research-channel">' +
      '<div class="catalyst-research-channel-head">' + title + statusChip(coverageStatus) + "</div>" +
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

  function sourceHtml(source, endpoints) {
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
    var endpoint = null;
    if (source.endpoint_id && endpoints && endpoints.length) {
      for (var index = 0; index < endpoints.length; index += 1) {
        if (endpoints[index].endpoint_id === source.endpoint_id) {
          endpoint = endpoints[index];
          break;
        }
      }
    }
    if (endpoint) {
      details.push("endpoint status: " + endpoint.status);
      details.push("confidence: " + endpoint.confidence);
    }
    var safeUrl = typeof source.url === "string" && /^https:\/\//i.test(source.url) ? source.url : null;
    var url = source.url
      ? safeUrl
        ? '<a class="catalyst-research-source-url" href="' + escapeHtml(safeUrl) +
          '" target="_blank" rel="noopener noreferrer">' + escapeHtml(source.url) + "</a>"
        : '<span class="catalyst-research-source-url">' + escapeHtml(source.url) + "</span>"
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

  function sourcesHtml(sources, endpoints) {
    if (!sources || !sources.length) {
      return "";
    }
    return (
      '<details class="catalyst-research-sources-details">' +
      "<summary>View source provenance (" + sources.length + ")</summary>" +
      '<div class="catalyst-research-sources">' +
      sources.map(function (source) {
        return sourceHtml(source, endpoints);
      }).join("") +
      "</div></details>"
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

  function activityDotClass(event) {
    var meaningfulState = event && event.meaningful_state;
    if (meaningfulState === "meaningful") {
      return "cal-dot cal-dot-meaningful";
    }
    if (meaningfulState === "non_meaningful") {
      return "cal-dot cal-dot-non-meaningful";
    }
    if (meaningfulState === "ambiguous") {
      return "cal-dot cal-dot-ambiguous";
    }
    var earningsState = event && event.earnings_state;
    if (earningsState === "earnings") {
      return "cal-dot cal-dot-earnings";
    }
    if (earningsState === "non_earnings") {
      return "cal-dot cal-dot-news";
    }
    return "cal-dot cal-dot-ambiguous";
  }

  function groupActivityByDate(events) {
    var byDate = {};
    events.forEach(function (event) {
      if (!event || !event.count_date) {
        return;
      }
      if (!byDate[event.count_date]) {
        byDate[event.count_date] = [];
      }
      byDate[event.count_date].push(event);
    });
    return byDate;
  }

  function dotsHtml(events) {
    var dots = "";
    var shown = Math.min(events.length, 3);
    for (var index = 0; index < shown; index += 1) {
      dots += '<span class="' + activityDotClass(events[index]) + '"></span>';
    }
    if (events.length > shown) {
      dots += '<span class="cal-ir-more">+' + (events.length - shown) + "</span>";
    }
    return dots;
  }

  function eventsHtml(events) {
    return (events || []).map(function (event) {
      var metaParts = [
        "channel: " + (ACTIVITY_CHANNEL_LABELS[event.source_type] || String(event.source_type || "").replace(/_/g, " ")),
        "class: " + (ACTIVITY_STATE_LABELS[event.earnings_state] || "Ambiguous"),
      ];
      var provider = PROVIDER_LABELS[event.extraction_provider] || event.extraction_provider;
      if (provider) {
        metaParts.push("via: " + provider);
      }
      metaParts.push("content: " + (event.has_content ? "Full text archived" : "Metadata only"));
      var meta = metaParts.join(" · ");
      var chips = "";
      if (event.catalyst_type) {
        chips +=
          ' <span class="catalyst-research-chip catalyst-research-chip-type">' +
          escapeHtml(CATALYST_TYPE_LABELS[event.catalyst_type] || String(event.catalyst_type).replace(/_/g, " ")) +
          "</span>";
      }
      if (event.meaningful_state) {
        chips +=
          ' <span class="catalyst-research-chip catalyst-research-chip-' +
          escapeHtml(String(event.meaningful_state).replace(/_/g, "-")) + '">' +
          escapeHtml(MEANINGFUL_LABELS[event.meaningful_state] || event.meaningful_state) +
          "</span>";
      }
      var safeUrl = typeof event.url === "string" && /^https:\/\//i.test(event.url) ? event.url : null;
      var link = safeUrl
        ? ' · <a href="' + escapeHtml(safeUrl) + '" target="_blank" rel="noopener noreferrer">Open source ↗</a>'
        : "";
      return (
        '<div class="cal-ir-event">' +
        '<span class="' + activityDotClass(event) + '"></span>' +
        '<span class="cal-ir-event-body">' +
        '<span class="cal-ir-event-title">' + escapeHtml(event.title || "Untitled") + "</span>" +
        '<span class="cal-ir-event-meta">' + escapeHtml(meta) + chips + link + "</span>" +
        "</span></div>"
      );
    }).join("");
  }

  function loadActivity(symbol) {
    var events = [];
    function fetchPage(cursor) {
      var url =
        "/api/ticker-quant/" + encodeURIComponent(symbol) + "/catalyst-research/activity?limit=200" +
        (cursor ? "&cursor=" + encodeURIComponent(cursor) : "");
      return fetch(url).then(requireOkJson).then(function (page) {
        if (!page || page.status === "not_researched") {
          return events;
        }
        events = events.concat(page.events || []);
        if (page.next_cursor) {
          return fetchPage(page.next_cursor);
        }
        return events;
      });
    }
    return fetchPage(null);
  }

  function render(payload) {
    if (!payload || payload.status === "not_researched") {
      return notResearchedHtml(payload);
    }
    if (payload.status === "researching") {
      return researchingHtml(payload);
    }
    var statistics = payload.channels || payload.statistics || {};
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
    var earningsCard = statistics.earnings_results
      ? channelHtml("Earnings Results", statistics.earnings_results)
      : "";
    return (
      '<div class="catalyst-research">' +
      '<div class="catalyst-research-meta">' + escapeHtml(meta.join(" · ")) + "</div>" +
      '<div class="catalyst-research-grid">' +
      channelHtml("Press Releases", statistics.press_releases) +
      channelHtml("Events &amp; Presentations", statistics.events_presentations) +
      earningsCard +
      "</div>" +
      sourcesHtml(payload.sources, payload.endpoints) +
      warningsHtml(payload.warnings) +
      nextActions +
      "</div>"
    );
  }

  function fetchSummary(symbol) {
    return fetch("/api/ticker-quant/" + encodeURIComponent(symbol) + "/catalyst-research").then(requireOkJson);
  }

  function runResearch(symbol) {
    return fetch(
      "/api/ticker-quant/" + encodeURIComponent(symbol) + "/catalyst-research/run",
      { method: "POST" }
    ).then(requireOkJson);
  }

  function notifySettled(symbol, options, payload) {
    if (options.onSettled) {
      options.onSettled(payload);
    }
  }

  function settleTimeout(symbol, options) {
    fetchSummary(symbol)
      .then(function (payload) {
        if (!options.isCurrent || !options.isCurrent(symbol)) {
          return;
        }
        if (payload && payload.status !== "researching" && payload.status !== "not_researched") {
          options.onResult(payload, render(payload));
        } else {
          options.onResult(payload, timeoutHtml(payload));
        }
        notifySettled(symbol, options, payload);
      })
      .catch(function () {});
  }

  function pollUntilDone(symbol, options, startedAt) {
    if (Date.now() - startedAt > POLL_TIMEOUT_MS) {
      settleTimeout(symbol, options);
      return;
    }
    setTimeout(function () {
      if (!options.isCurrent || !options.isCurrent(symbol)) {
        return;
      }
      fetchSummary(symbol)
        .then(function (payload) {
          if (!options.isCurrent(symbol)) {
            return;
          }
          if (payload && payload.status === "researching") {
            pollUntilDone(symbol, options, startedAt);
            return;
          }
          if (payload && payload.status === "not_researched" && Date.now() - startedAt < START_WINDOW_MS) {
            pollUntilDone(symbol, options, startedAt);
            return;
          }
          if (payload && payload.status !== "not_researched") {
            options.onResult(payload, render(payload));
          } else {
            options.onResult(payload, failedHtml(payload));
          }
          notifySettled(symbol, options, payload);
        })
        .catch(function () {
          pollUntilDone(symbol, options, startedAt);
        });
    }, POLL_INTERVAL_MS);
  }

  function load(symbol, options) {
    options = options || {};
    return fetchSummary(symbol).then(function (payload) {
      if (!options.isCurrent || !options.onResult || !options.isCurrent(symbol)) {
        return payload;
      }
      if (payload && payload.status === "researching") {
        options.onResult(payload, render(payload));
        pollUntilDone(symbol, options, Date.now());
        return payload;
      }
      if (payload && payload.status === "not_researched" && options.autoRun && !triggered[symbol]) {
        triggered[symbol] = true;
        options.onResult(payload, researchingHtml(payload));
        runResearch(symbol)
          .then(function (runResult) {
            if (!options.isCurrent(symbol)) {
              return;
            }
            if (runResult && runResult.run_status === "already_researched") {
              fetchSummary(symbol)
                .then(function (fresh) {
                  if (options.isCurrent(symbol)) {
                    options.onResult(fresh, render(fresh));
                  }
                })
                .catch(function () {});
              return;
            }
            if (runResult && (runResult.run_status === "started" || runResult.run_status === "already_running")) {
              pollUntilDone(symbol, options, Date.now());
              return;
            }
            options.onResult(payload, notResearchedHtml(payload));
          })
          .catch(function () {
            if (options.isCurrent(symbol)) {
              options.onResult(payload, notResearchedHtml(payload));
            }
          });
        return payload;
      }
      options.onResult(payload, render(payload));
      return payload;
    });
  }

  window.CatalystResearch = {
    load: load,
    render: render,
    loadActivity: loadActivity,
    groupActivityByDate: groupActivityByDate,
    dotsHtml: dotsHtml,
    eventsHtml: eventsHtml,
  };
})();

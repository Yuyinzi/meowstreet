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

  var MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
  ];

  var WEEKDAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

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
      '<div class="catalyst-research-sources">' +
      sources.map(function (source) {
        return sourceHtml(source, endpoints);
      }).join("") +
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

  function activityDotClass(earningsState) {
    if (earningsState === "earnings") {
      return "catalyst-research-dot catalyst-research-dot-earnings";
    }
    if (earningsState === "non_earnings") {
      return "catalyst-research-dot catalyst-research-dot-news";
    }
    return "catalyst-research-dot catalyst-research-dot-ambiguous";
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

  function pad2(value) {
    return value < 10 ? "0" + value : String(value);
  }

  function monthKey(year, monthIndex) {
    return year * 12 + monthIndex;
  }

  function shiftMonth(month, delta) {
    var key = monthKey(month.year, month.month) + delta;
    return { year: Math.floor(key / 12), month: ((key % 12) + 12) % 12 };
  }

  function activityMonthRange(events) {
    var now = new Date();
    var minKey = monthKey(now.getFullYear(), now.getMonth());
    var maxKey = minKey;
    events.forEach(function (event) {
      if (!event || typeof event.count_date !== "string") {
        return;
      }
      var parts = event.count_date.split("-");
      if (parts.length < 2) {
        return;
      }
      var key = monthKey(Number(parts[0]), Number(parts[1]) - 1);
      if (key < minKey) {
        minKey = key;
      }
      if (key > maxKey) {
        maxKey = key;
      }
    });
    return { min: minKey, max: maxKey };
  }

  function activityDotsHtml(events) {
    var dots = "";
    var shown = Math.min(events.length, 3);
    for (var index = 0; index < shown; index += 1) {
      dots += '<span class="' + activityDotClass(events[index].earnings_state) + '"></span>';
    }
    if (events.length > shown) {
      dots += '<span class="catalyst-research-cal-more">+' + (events.length - shown) + "</span>";
    }
    return dots;
  }

  function calendarGridHtml(state, byDate) {
    var year = state.month.year;
    var monthIndex = state.month.month;
    var firstWeekday = (new Date(year, monthIndex, 1).getDay() + 6) % 7;
    var daysInMonth = new Date(year, monthIndex + 1, 0).getDate();
    var cells = WEEKDAY_LABELS.map(function (label) {
      return '<div class="catalyst-research-cal-weekday">' + label + "</div>";
    }).join("");
    for (var blank = 0; blank < firstWeekday; blank += 1) {
      cells += '<div class="catalyst-research-cal-day catalyst-research-cal-day-empty"></div>';
    }
    for (var day = 1; day <= daysInMonth; day += 1) {
      var dateKey = year + "-" + pad2(monthIndex + 1) + "-" + pad2(day);
      var dayEvents = byDate[dateKey] || [];
      if (!dayEvents.length) {
        cells += '<div class="catalyst-research-cal-day"><span class="catalyst-research-cal-day-num">' + day + "</span></div>";
        continue;
      }
      var selected = state.selectedDate === dateKey ? " catalyst-research-cal-day-selected" : "";
      cells +=
        '<button type="button" class="catalyst-research-cal-day catalyst-research-cal-day-has-events' + selected +
        '" data-cr-action="select-day" data-cr-date="' + dateKey + '">' +
        '<span class="catalyst-research-cal-day-num">' + day + "</span>" +
        '<span class="catalyst-research-cal-dots">' + activityDotsHtml(dayEvents) + "</span>" +
        "</button>";
    }
    return cells;
  }

  function activityEventDetailHtml(event) {
    var details = [];
    details.push(row("Event date", escapeHtml(event.count_date || "—")));
    details.push(row("Classification", escapeHtml(ACTIVITY_STATE_LABELS[event.earnings_state] || "Ambiguous")));
    details.push(row(
      "Extraction",
      escapeHtml(PROVIDER_LABELS[event.extraction_provider] || event.extraction_provider || "unknown")
    ));
    details.push(row(
      "Content",
      event.has_content
        ? "Full text archived"
        : '<span class="catalyst-research-muted">Metadata only</span>'
    ));
    var safeUrl = typeof event.url === "string" && /^https:\/\//i.test(event.url) ? event.url : null;
    var link = safeUrl
      ? '<a class="catalyst-research-source-url" href="' + escapeHtml(safeUrl) +
        '" target="_blank" rel="noopener noreferrer">Open source ↗</a>'
      : "";
    return '<div class="catalyst-research-event-detail">' + details.join("") + link + "</div>";
  }

  function activityPanelHtml(state, byDate) {
    if (!state.selectedDate || !(byDate[state.selectedDate] || []).length) {
      return (
        '<div class="catalyst-research-panel-title">Day detail</div>' +
        '<div class="catalyst-research-note">Select a marked day to review its events.</div>'
      );
    }
    var dayEvents = byDate[state.selectedDate];
    var items = dayEvents.map(function (event, index) {
      var key = state.selectedDate + "#" + index;
      var expanded = state.expandedKey === key;
      return (
        '<div class="catalyst-research-event-block">' +
        '<button type="button" class="catalyst-research-event" data-cr-action="toggle-event" data-cr-key="' + escapeHtml(key) + '">' +
        '<span class="' + activityDotClass(event.earnings_state) + '"></span>' +
        '<span class="catalyst-research-event-body">' +
        '<span class="catalyst-research-event-title">' + escapeHtml(event.title || "Untitled") + "</span>" +
        '<span class="catalyst-research-event-meta">' +
        escapeHtml(ACTIVITY_CHANNEL_LABELS[event.source_type] || String(event.source_type || "").replace(/_/g, " ")) +
        " · " + escapeHtml(ACTIVITY_STATE_LABELS[event.earnings_state] || "Ambiguous") +
        "</span></span></button>" +
        (expanded ? activityEventDetailHtml(event) : "") +
        "</div>"
      );
    }).join("");
    return (
      '<div class="catalyst-research-panel-title">' + escapeHtml(state.selectedDate) + "</div>" +
      items
    );
  }

  function drawActivity(root, state) {
    if (state.error) {
      root.innerHTML =
        '<div class="catalyst-research-activity">' +
        '<div class="catalyst-research-activity-title">Catalyst activity calendar</div>' +
        '<div class="catalyst-research-note">Activity calendar unavailable.</div></div>';
      return;
    }
    if (!state.events.length && state.loading) {
      root.innerHTML =
        '<div class="catalyst-research-activity">' +
        '<div class="catalyst-research-activity-title">Catalyst activity calendar</div>' +
        '<div class="catalyst-research-note">Loading activity…</div></div>';
      return;
    }
    if (!state.events.length) {
      root.innerHTML = "";
      return;
    }
    var byDate = groupActivityByDate(state.events);
    if (!state.month) {
      var latest = state.events[0].count_date.split("-");
      state.month = { year: Number(latest[0]), month: Number(latest[1]) - 1 };
    }
    var range = activityMonthRange(state.events);
    var currentKey = monthKey(state.month.year, state.month.month);
    if (!state.nextCursor && currentKey < range.min) {
      state.month = shiftMonth(state.month, range.min - currentKey);
      currentKey = range.min;
    }
    var legend =
      '<div class="catalyst-research-legend">' +
      '<span><span class="catalyst-research-dot catalyst-research-dot-earnings"></span> Earnings</span>' +
      '<span><span class="catalyst-research-dot catalyst-research-dot-news"></span> News / Events</span>' +
      '<span><span class="catalyst-research-dot catalyst-research-dot-ambiguous"></span> Ambiguous</span>' +
      "</div>";
    var nav =
      '<div class="catalyst-research-cal-nav">' +
      '<button type="button" data-cr-action="prev-month"' + (currentKey <= range.min && !state.nextCursor ? " disabled" : "") + '>‹</button>' +
      '<span class="catalyst-research-cal-month">' + MONTH_NAMES[state.month.month] + " " + state.month.year + "</span>" +
      '<button type="button" data-cr-action="next-month"' + (currentKey >= range.max ? " disabled" : "") + '>›</button>' +
      "</div>";
    var loadMore = state.nextCursor
      ? '<button type="button" class="catalyst-research-load-more" data-cr-action="load-more"' +
        (state.loading ? " disabled" : "") + ">" +
        (state.loading ? "Loading…" : "Load earlier activity") + "</button>"
      : "";
    root.innerHTML =
      '<div class="catalyst-research-activity">' +
      '<div class="catalyst-research-activity-title">Catalyst activity calendar</div>' +
      legend +
      '<div class="catalyst-research-activity-layout">' +
      '<div class="catalyst-research-cal">' + nav +
      '<div class="catalyst-research-cal-grid">' + calendarGridHtml(state, byDate) + "</div>" +
      loadMore +
      "</div>" +
      '<div class="catalyst-research-panel">' + activityPanelHtml(state, byDate) + "</div>" +
      "</div></div>";
  }

  function mountActivity(symbol, options) {
    if (!options.container || typeof options.container.querySelector !== "function") {
      return;
    }
    var root = options.container.querySelector("[data-cr-activity-root]");
    if (!root || typeof options.isCurrent !== "function") {
      return;
    }
    var state = {
      events: [],
      nextCursor: null,
      month: null,
      selectedDate: null,
      expandedKey: null,
      loading: false,
      error: false,
    };
    root.addEventListener("click", function (event) {
      var target = event.target && event.target.closest ? event.target.closest("[data-cr-action]") : null;
      if (!target || !root.contains(target)) {
        return;
      }
      var action = target.getAttribute("data-cr-action");
      if (action === "prev-month" || action === "next-month") {
        state.month = shiftMonth(state.month, action === "prev-month" ? -1 : 1);
      } else if (action === "select-day") {
        state.selectedDate = target.getAttribute("data-cr-date");
        state.expandedKey = null;
      } else if (action === "toggle-event") {
        var key = target.getAttribute("data-cr-key");
        state.expandedKey = state.expandedKey === key ? null : key;
      } else if (action === "load-more") {
        loadMore();
        return;
      } else {
        return;
      }
      drawActivity(root, state);
    });
    function loadMore() {
      if (state.loading) {
        return;
      }
      state.loading = true;
      drawActivity(root, state);
      var url =
        "/api/ticker-quant/" + encodeURIComponent(symbol) + "/catalyst-research/activity?limit=200" +
        (state.nextCursor ? "&cursor=" + encodeURIComponent(state.nextCursor) : "");
      fetch(url)
        .then(requireOkJson)
        .then(function (page) {
          state.loading = false;
          if (!options.isCurrent(symbol)) {
            return;
          }
          if (!page || page.status === "not_researched") {
            state.nextCursor = null;
          } else {
            state.events = state.events.concat(page.events || []);
            state.nextCursor = page.next_cursor || null;
          }
          drawActivity(root, state);
        })
        .catch(function () {
          state.loading = false;
          state.error = true;
          if (options.isCurrent(symbol)) {
            drawActivity(root, state);
          }
        });
    }
    loadMore();
  }

  function render(payload) {
    if (!payload || payload.status === "not_researched") {
      return notResearchedHtml(payload);
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
    return (
      '<div class="catalyst-research">' +
      '<div class="catalyst-research-meta">' + escapeHtml(meta.join(" · ")) + "</div>" +
      '<div class="catalyst-research-grid">' +
      channelHtml("Press Releases", statistics.press_releases) +
      channelHtml("Events &amp; Presentations", statistics.events_presentations) +
      "</div>" +
      sourcesHtml(payload.sources, payload.endpoints) +
      warningsHtml(payload.warnings) +
      nextActions +
      '<div data-cr-activity-root></div>' +
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
          mountActivity(symbol, options);
        }
        return payload;
      });
  }

  window.CatalystResearch = { load: load, render: render };
})();

import {
  escapeHtml, fmtNumber, fmtRate, lineLabel, bilingualLineLabel, bilingualLabel,
  fmtMonthYear, fmtYear,
} from "./utils.js";

export const CHART_RANGE_OPTIONS = [
    { id: "1y", label: "1Y", years: 1 },
    { id: "5y", label: "5Y", years: 5 },
    { id: "10y", label: "10Y", years: 10 },
    { id: "20y", label: "20Y", years: 20 },
    { id: "max", label: "Max", years: null },
  ];


export function parseUtcDate(value) {
    const date = new Date(`${value}T00:00:00Z`);
    return Number.isNaN(date.getTime()) ? null : date;
  }


export function cutoffDateForRange(series, rangeId) {
    const option = CHART_RANGE_OPTIONS.find((item) => item.id === rangeId)
      || CHART_RANGE_OPTIONS.find((item) => item.id === "1y");
    if (!option || option.years === null || !series.length) return null;
    const lastPoint = series[series.length - 1];
    const lastDate = parseUtcDate(lastPoint.date);
    if (!lastDate) return null;
    const cutoff = new Date(lastDate.getTime());
    cutoff.setUTCFullYear(cutoff.getUTCFullYear() - option.years);
    return cutoff.toISOString().slice(0, 10);
  }


export function filterSeriesForRange(series, rangeId) {
    const rows = series || [];
    const cutoff = cutoffDateForRange(rows, rangeId);
    if (!cutoff) return rows.slice();
    return rows.filter((point) => point.date >= cutoff);
  }


export function filterEventsForRange(events, filteredSeries) {
    const dateSet = new Set((filteredSeries || []).map((point) => point.date));
    return (events || []).filter((event) => dateSet.has(event.date));
  }


export function filterChartForRange(chart, rangeId) {
    const series = filterSeriesForRange(chart.series || [], rangeId);
    return {
      ...chart,
      series,
      events: rangeId === "max" ? [] : filterEventsForRange(chart.events || [], series),
    };
  }


export const CHART_WIDTH = 960;

export const CHART_HEIGHT = 400;

export const MARGIN_LEFT = 50;

export const MARGIN_RIGHT = 50;

export const MARGIN_TOP = 18;

export const MARGIN_BOTTOM = 84;

export const MARKET_X_LABEL_Y = 32;

export const RELATIONSHIP_X_LABEL_Y = 36;

export const PLOT_RIGHT = CHART_WIDTH - MARGIN_RIGHT;

export const PLOT_WIDTH = PLOT_RIGHT - MARGIN_LEFT;

export const PLOT_BOTTOM = CHART_HEIGHT - MARGIN_BOTTOM;

export const PLOT_HEIGHT = PLOT_BOTTOM - MARGIN_TOP;

export const Y_AXIS_TICK_COUNT = 9;

export const X_AXIS_TICK_COUNT = 12;


export function xAt(index, count) {
    if (count <= 1) return MARGIN_LEFT + PLOT_WIDTH / 2;
    return MARGIN_LEFT + (index / (count - 1)) * PLOT_WIDTH;
  }


export function yAt(value, scale) {
    return MARGIN_TOP + scale.height - ((value - scale.min) / scale.range) * scale.height;
  }


export function yTickLabelY(y) {
    if (y >= PLOT_BOTTOM - 1) return -8;
    if (y <= MARGIN_TOP + 1) return 12;
    return 4;
  }


export function visibleYAxisTicks(ticks, scale) {
    return ticks.filter((value) => yAt(value, scale) < PLOT_BOTTOM - 1);
  }


export function relationshipValues(series, keys) {
    return series.flatMap((point) => keys.map((key) => point[key])).filter((value) => value !== null && value !== undefined);
  }


export function relationshipScale(series, keys, yDomain = null) {
    if (yDomain && yDomain.min !== null && yDomain.min !== undefined && yDomain.max !== null && yDomain.max !== undefined) {
      const min = yDomain.min;
      const max = yDomain.max;
      return { min, max, range: max - min || 1, height: PLOT_HEIGHT };
    }
    const values = relationshipValues(series, keys);
    if (!values.length) return null;
    const min = Math.min(...values);
    const max = Math.max(...values);
    return { min, max, range: max - min || 1, height: PLOT_HEIGHT };
  }


export function relationshipYAxisTicks(series, keys, count, yDomain = null) {
    if (yDomain && yDomain.min !== null && yDomain.min !== undefined && yDomain.max !== null && yDomain.max !== undefined) {
      return niceTicks(yDomain.min, yDomain.max, count);
    }
    const values = relationshipValues(series, keys);
    if (!values.length) return [];
    return niceTicks(Math.min(...values), Math.max(...values), count);
  }


export function relationshipXAxisTicks(series) {
    return xAxisTicks(series);
  }


export function relationshipYearlyXAxisTicks(series) {
    const byYear = new Map();
    (series || []).forEach((point, index) => {
      const year = String(point.date || "").slice(0, 4);
      const month = String(point.date || "").slice(5, 7);
      if (!year || month !== "01") return;
      if (!byYear.has(year)) {
        byYear.set(year, { date: point.date, index });
      }
    });
    const years = [...byYear.keys()].sort();
    const step = Math.max(1, Math.ceil(years.length / X_AXIS_TICK_COUNT));
    return years
      .filter((year, index) => index % step === 0)
      .map((year) => {
        const point = byYear.get(year);
        return {
          date: point.date,
          x: xAt(point.index, series.length),
        };
      });
  }


export function renderRelationshipXAxisTicks(series, options = {}) {
    const ticks = options.categoricalXAxis
      ? series.map((point, index) => ({
        date: point.label || point.date,
        x: xAt(index, series.length),
      }))
      : options.xTickMode === "yearly"
        ? relationshipYearlyXAxisTicks(series)
        : xAxisTicks(series);
    return ticks
      .map((tick) => `
        <g class="chart-tick relationship-chart-tick" transform="translate(${tick.x.toFixed(2)} ${PLOT_BOTTOM})">
          <line y2="8"></line>
          <text class="chart-x-label" y="${RELATIONSHIP_X_LABEL_Y}" text-anchor="middle" x="0" transform="rotate(-35 0 ${RELATIONSHIP_X_LABEL_Y})">${escapeHtml(options.categoricalXAxis ? tick.date : options.xTickMode === "yearly" ? fmtYear(tick.date) : fmtMonthYear(tick.date))}</text>
        </g>
      `)
      .join("");
  }


export function renderRelationshipYAxisAndGrid(ticks, scale, formatValue = fmtNumber) {
    const gridAndTicks = visibleYAxisTicks(ticks, scale).map((value) => {
      const yValue = yAt(value, scale);
      const y = yValue.toFixed(2);
      return `
        <g class="chart-grid">
          <line x1="${MARGIN_LEFT}" y1="${y}" x2="${PLOT_RIGHT}" y2="${y}"></line>
        </g>
        <g class="chart-y-tick" transform="translate(${MARGIN_LEFT} ${y})">
          <line x1="-6" y1="0" x2="0" y2="0"></line>
          <text x="-10" y="${yTickLabelY(yValue)}">${escapeHtml(formatValue(value))}</text>
        </g>
      `;
    }).join("");

    return `
      <g class="chart-axis">
        <line x1="${MARGIN_LEFT}" y1="${MARGIN_TOP}" x2="${MARGIN_LEFT}" y2="${PLOT_BOTTOM}"></line>
        <line x1="${MARGIN_LEFT}" y1="${PLOT_BOTTOM}" x2="${PLOT_RIGHT}" y2="${PLOT_BOTTOM}"></line>
      </g>
      ${gridAndTicks}
    `;
  }


export function renderRelationshipReferenceLines(lines, scale, formatValue = fmtNumber) {
    return (lines || [])
      .filter((line) => line.value !== null && line.value !== undefined)
      .map((line) => {
        const y = yAt(line.value, scale).toFixed(2);
        return `
          <g class="relationship-reference-line">
            <line x1="${MARGIN_LEFT}" y1="${y}" x2="${PLOT_RIGHT}" y2="${y}"></line>
            <text x="${PLOT_RIGHT - 6}" y="${Number(y) - 6}" text-anchor="end">${escapeHtml(line.label || formatValue(line.value))}</text>
          </g>
        `;
      })
      .join("");
  }


export function renderRelationshipLineChart(title, series, keys, labels = {}, options = {}) {
    const wideClass = options.wide ? " relationship-chart-wide" : "";
    const titleHtml = options.rawTitle ? title : escapeHtml(title);
    const hideHead = options.hideHead || false;
    if (!series || !series.length) {
      if (hideHead) return `<p class="status">No chart data available.</p>`;
      return `
        <div class="relationship-chart${wideClass}">
          <div class="relationship-chart-head">
            <h3>${titleHtml}</h3>
            <span>No data</span>
          </div>
          <p class="status">No chart data available.</p>
        </div>
      `;
    }
    const values = relationshipValues(series, keys);
    if (!values.length) {
      if (hideHead) return `<p class="status">No chart data available.</p>`;
      return `
        <div class="relationship-chart${wideClass}">
          <div class="relationship-chart-head">
            <h3>${titleHtml}</h3>
            <span>No data</span>
          </div>
          <p class="status">No chart data available.</p>
        </div>
      `;
    }
    const scale = relationshipScale(series, keys, options.yDomain);
    const valueFormatter = options.valueFormatter || fmtNumber;
    const firstLabel = series[0].label || series[0].date;
    const lastLabel = series[series.length - 1].label || series[series.length - 1].date;
    return `
      <div class="relationship-chart${wideClass}">
        ${hideHead ? "" : `
        <div class="relationship-chart-head">
          <h3>${titleHtml}</h3>
          <span>${escapeHtml(fmtMonthYear(firstLabel))} - ${escapeHtml(fmtMonthYear(lastLabel))}</span>
        </div>
        <div class="relationship-legend">
          ${keys.map((key, index) => `
            <span><i class="relationship-line-key relationship-line-key-${index}"></i>${options.rawLabels ? bilingualLineLabel(labels, key) : escapeHtml(lineLabel(labels, key))}</span>
          `).join("")}
          ${options.policyTrack ? `
            <span><i class="policy-legend-circle"></i>${bilingualLabel("Statement")}</span>
            <span><i class="policy-legend-triangle"></i>${bilingualLabel("Minutes")}</span>
            <span><i class="policy-color-swatch policy-color-hawkish"></i>${bilingualLabel("Hawkish")}</span>
            <span><i class="policy-color-swatch policy-color-dovish"></i>${bilingualLabel("Dovish")}</span>
            <span><i class="policy-color-swatch policy-color-mixed"></i>${bilingualLabel("Mixed")}</span>
            <span><i class="policy-color-swatch policy-color-neutral"></i>${bilingualLabel("Neutral")}</span>
          ` : ""}
        </div>
        `}
        <div class="chart-wrap relationship-chart-wrap">
          <svg class="relationship-chart-svg" viewBox="0 0 ${CHART_WIDTH} ${CHART_HEIGHT}" role="img" aria-label="${titleHtml}">
            ${renderRelationshipYAxisAndGrid(relationshipYAxisTicks(series, keys, Y_AXIS_TICK_COUNT, options.yDomain), scale, valueFormatter)}
            ${scale.min <= 0 && scale.max >= 0 ? `<line class="relationship-zero" x1="${MARGIN_LEFT}" y1="${yAt(0, scale).toFixed(2)}" x2="${PLOT_RIGHT}" y2="${yAt(0, scale).toFixed(2)}"></line>` : ""}
            ${renderRelationshipReferenceLines(options.referenceLines || [], scale, valueFormatter)}
            ${options.policyTrack ? "" : renderRelationshipEventMarkers(series, keys, scale, options.events || [])}
            ${keys.flatMap((key, index) => (
              chartSegments(series, key, scale, { lineShape: options.lineShape }).map((points) => `<polyline class="relationship-line relationship-line-${index}" points="${escapeHtml(points)}"></polyline>`)
            )).join("")}
            ${options.showDots ? keys.flatMap((key, index) => (
              series
                .filter((point) => point[key] !== null && point[key] !== undefined)
                .map((point) => {
                  const i = series.indexOf(point);
                  return `<circle class="relationship-dot relationship-dot-${index}" cx="${xAt(i, series.length).toFixed(2)}" cy="${yAt(point[key], scale).toFixed(2)}" r="3.5"></circle>`;
                })
            )).join("") : ""}
            ${options.showXAxis === false ? "" : renderRelationshipXAxisTicks(series, options)}
            ${options.policyTrack ? renderRelationshipPolicyTrack(series, options.events || [], scale) : ""}
          </svg>
          <div class="chart-tooltip" aria-hidden="true"></div>
        </div>
      </div>
    `;
  }


export function eventToneClass(event) {
    const tone = String(event?.marker_tone || event?.policy_tone || "unknown").toLowerCase();
    if (["dovish", "easing"].includes(tone)) return "dovish";
    if (["hawkish", "tightening"].includes(tone)) return "hawkish";
    if (tone === "mixed") return "mixed";
    return "unknown";
  }


export function eventMarkerTopY(point, keys, scale) {
    const values = keys
      .map((key) => point?.[key])
      .filter((value) => value !== null && value !== undefined && Number.isFinite(Number(value)))
      .map((value) => Number(value));
    if (!values.length) return MARGIN_TOP;
    return yAt(Math.max(...values), scale);
  }


export function eventMarkerBottomY(scale) {
    if (scale.min <= 0 && scale.max >= 0) return yAt(0, scale);
    return PLOT_BOTTOM;
  }


export function renderRelationshipEventMarkers(series, keys, scale, events = []) {
    if (!events.length) return "";
    const dateToIndex = new Map(series.map((point, index) => [point.date, index]));
    const bars = events
      .filter((event) => dateToIndex.has(event.date))
      .map((event) => {
        const index = dateToIndex.get(event.date);
        const barWidth = 8;
        const x = xAt(index, series.length) - barWidth / 2;
        const topY = eventMarkerTopY(series[index], keys, scale);
        const bottomY = eventMarkerBottomY(scale);
        const y = Math.min(topY, bottomY);
        const height = Math.max(Math.abs(bottomY - topY), 8);
        return `
          <g class="relationship-event-marker relationship-event-marker-${escapeHtml(eventToneClass(event))}">
            <rect class="relationship-event-bar" x="${x.toFixed(2)}" y="${y.toFixed(2)}" width="${barWidth}" height="${height.toFixed(2)}" rx="2"></rect>
          </g>
        `;
      })
      .join("");
    if (!bars) return "";
    return `
      <g class="relationship-event-rail">
        ${bars}
      </g>
    `;
  }


export function policyTrackEvents(events = []) {
    const rows = [];
    events.forEach((event) => {
      rows.push({
        ...event,
        policy_event_type: "statement",
        policy_track_date: event.date,
        policy_track_tone: event.policy_tone || event.statement_tone || "unknown",
      });
      if (event.minutes_status === "available") {
        rows.push({
          ...event,
          policy_event_type: "minutes",
          policy_track_date: event.minutes_display_month || event.date,
          policy_track_tone: minutesPolicyToneClass(event),
        });
      }
    });
    return rows;
  }


export function minutesPolicyToneClass(event) {
    const confirmation = String(event?.minutes_confirmation || "unknown").toLowerCase();
    const conviction = String(event?.policy_conviction || "unknown").toLowerCase();
    const riskBias = String(event?.risk_bias || event?.minutes_tone || "unknown").toLowerCase();
    if (["confirmed_but_divided", "weakened", "mixed", "contradicted"].includes(confirmation) || conviction === "divided") {
      return "mixed";
    }
    if (riskBias.includes("hawkish")) return "hawkish";
    if (riskBias.includes("dovish")) return "dovish";
    return "unknown";
  }


export function policyToneFill(tone) {
    if (tone === "hawkish") return "#B94B4B";
    if (tone === "dovish") return "#5C9C73";
    if (tone === "mixed") return "#D1A54F";
    return "#9A9288";
  }


export function renderRelationshipPolicyTrack(series, events = [], scale = null) {
    if (!series.length || !events.length) return "";
    const byDate = new Map(series.map((row, index) => [row.date, index]));
    const trackEvents = policyTrackEvents(events).filter((event) =>
      byDate.has(event.policy_track_date || event.date)
    );
    if (!trackEvents.length) return "";
    const hasZero = scale && scale.min <= 0 && scale.max >= 0;
    const baseY = hasZero ? yAt(0, scale) : PLOT_BOTTOM + 20;
    const statY = baseY - 6;
    const minsY = baseY + 6;
    const statementMarkers = trackEvents
      .filter((e) => e.policy_event_type === "statement")
      .map((e) => {
        const index = byDate.get(e.policy_track_date || e.date);
        const x = xAt(index, series.length);
        const fill = policyToneFill(eventToneClass(e));
        return `<g transform="translate(${x.toFixed(2)} ${statY})"><circle r="4" fill="${fill}" stroke="#FFFFFF" stroke-width="1.5"></circle></g>`;
      }).join("");
    const minutesMarkers = trackEvents
      .filter((e) => e.policy_event_type === "minutes")
      .map((e) => {
        const index = byDate.get(e.policy_track_date || e.date);
        const x = xAt(index, series.length);
        const fill = policyToneFill(minutesPolicyToneClass(e));
        return `<g transform="translate(${x.toFixed(2)} ${minsY})"><path d="M0 -5 L5 5 L-5 5 Z" fill="${fill}" stroke="#FFFFFF" stroke-width="1.5"></path></g>`;
      }).join("");
    return `
      <g class="relationship-policy-track" aria-label="FOMC policy track">
        <line class="relationship-policy-axis" x1="${MARGIN_LEFT}" y1="${statY}" x2="${CHART_WIDTH - MARGIN_RIGHT}" y2="${statY}"></line>
        <line class="relationship-policy-axis" x1="${MARGIN_LEFT}" y1="${minsY}" x2="${CHART_WIDTH - MARGIN_RIGHT}" y2="${minsY}"></line>
        ${statementMarkers}
        ${minutesMarkers}
      </g>`;
  }


export function attachRelationshipChartTooltip(svg, tooltip, series, keys, labels = {}, options = {}) {
    if (!svg || !tooltip || !series.length) return;
    const wrap = svg.parentElement;
    const valueFormatter = options.valueFormatter || fmtNumber;
    const eventsByDate = new Map((options.events || []).map((event) => [event.date, event]));
    let lastIndex = -1;
    let tooltipRect = null;

    function _extraFormatter(value, fmt) {
      if (value === null || value === undefined) return "n/a";
      if (fmt === "percent") return fmtRate(value);
      return fmtNumber(value);
    }

    function positionRelationshipTooltip(index) {
      const wrapRect = wrap.getBoundingClientRect();
      const left = index < series.length / 2 ? wrapRect.width - tooltipRect.width - 12 : 12;
      tooltip.style.left = `${Math.max(8, left)}px`;
      tooltip.style.top = "12px";
      tooltip.classList.add("relationship-tooltip-pinned");
    }

    function show(index, clientX, clientY) {
      const point = series[index];
      if (index !== lastIndex) {
        const rows = keys.map((key) => {
          const value = point[key];
          const text = value === null || value === undefined ? "n/a" : valueFormatter(value);
          return `
            <div class="chart-tooltip-row">
              <span>${options.rawLabels ? bilingualLineLabel(labels, key) : escapeHtml(lineLabel(labels, key))}</span>
              <strong>${escapeHtml(text)}</strong>
            </div>
          `;
        }).join("");
        const extraRows = (options.tooltipExtra || []).map((extra) => {
          const value = point[extra.key];
          return `
            <div class="chart-tooltip-row">
              <span>${escapeHtml(lineLabel({ [extra.key]: extra.label }, extra.key))}</span>
              <strong>${escapeHtml(_extraFormatter(value, extra.format))}</strong>
            </div>
          `;
        }).join("");
        const event = eventsByDate.get(point.date);
        const eventRows = event ? `
          <div class="chart-tooltip-row">
            <span>${escapeHtml(event.label || "FOMC")}</span>
            <strong>${escapeHtml(event.event_date || event.date)}</strong>
          </div>
          <div class="chart-tooltip-row">
            <span>Statement tone</span>
            <strong>${escapeHtml(event.statement_tone || event.policy_tone || "unknown")}</strong>
          </div>
          <div class="chart-tooltip-row">
            <span>Tone change</span>
            <strong>${escapeHtml(event.tone_change || "unknown")}</strong>
          </div>
          <div class="chart-tooltip-row">
            <span>Confidence</span>
            <strong>${escapeHtml(event.confidence || "n/a")}</strong>
          </div>
        ` : "";
        tooltip.innerHTML = `
          <div><strong>${escapeHtml(fmtMonthYear(point.date))}</strong></div>
          ${rows}
          ${extraRows}
          ${eventRows}
        `;
        lastIndex = index;
        tooltip.style.left = "-9999px";
        tooltip.style.top = "-9999px";
        tooltip.classList.add("visible");
        tooltipRect = tooltip.getBoundingClientRect();
      }
      positionRelationshipTooltip(index);
    }

    function hide() {
      tooltip.classList.remove("visible");
      tooltip.classList.remove("relationship-tooltip-pinned");
      lastIndex = -1;
      tooltipRect = null;
    }

    svg.addEventListener("mousemove", (event) => {
      const rect = svg.getBoundingClientRect();
      const scaleX = CHART_WIDTH / rect.width;
      const x = (event.clientX - rect.left) * scaleX - MARGIN_LEFT;
      const ratio = Math.max(0, Math.min(1, x / PLOT_WIDTH));
      const index = Math.min(
        series.length - 1,
        Math.max(0, Math.round(ratio * (series.length - 1)))
      );
      show(index, event.clientX, event.clientY);
    });

    svg.addEventListener("mouseleave", hide);

    svg.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        hide();
      }
    });
  }




export function chartScale(series) {
    const allValues = series.flatMap((point) => [
      point.close,
      point.bear_market_level,
    ]);
    const min = Math.min(...allValues);
    const max = Math.max(...allValues);
    return { min, range: max - min || 1, height: PLOT_HEIGHT };
  }


export function niceTicks(min, max, count) {
    const range = max - min || Math.abs(max) || 1;
    const rawStep = range / (count - 1);
    const exponent = Math.floor(Math.log10(rawStep));
    const fraction = rawStep / Math.pow(10, exponent);
    let niceFraction;
    if (fraction <= 1) niceFraction = 1;
    else if (fraction <= 2) niceFraction = 2;
    else if (fraction <= 5) niceFraction = 5;
    else niceFraction = 10;
    const step = niceFraction * Math.pow(10, exponent);
    const niceMin = Math.floor(min / step) * step;
    const niceMax = Math.ceil(max / step) * step;
    const ticks = [];
    const steps = Math.round((niceMax - niceMin) / step);
    for (let i = 0; i <= steps; i++) {
      ticks.push(niceMin + i * step);
    }
    return ticks;
  }


export function yAxisTicks(series, count) {
    const values = series.flatMap((point) => [point.close, point.bear_market_level]);
    return niceTicks(Math.min(...values), Math.max(...values), count);
  }


export function renderYAxisAndGrid(ticks, scale) {
    const gridAndTicks = visibleYAxisTicks(ticks, scale).map((value) => {
      const yValue = yAt(value, scale);
      const y = yValue.toFixed(2);
      return `
        <g class="chart-grid">
          <line x1="${MARGIN_LEFT}" y1="${y}" x2="${PLOT_RIGHT}" y2="${y}"></line>
        </g>
        <g class="chart-y-tick" transform="translate(${MARGIN_LEFT} ${y})">
          <line x1="-6" y1="0" x2="0" y2="0"></line>
          <text x="-10" y="${yTickLabelY(yValue)}">${escapeHtml(fmtNumber(value))}</text>
        </g>
      `;
    }).join("");

    return `
      <g class="chart-axis">
        <line x1="${MARGIN_LEFT}" y1="${MARGIN_TOP}" x2="${MARGIN_LEFT}" y2="${PLOT_BOTTOM}"></line>
        <line x1="${MARGIN_LEFT}" y1="${PLOT_BOTTOM}" x2="${PLOT_RIGHT}" y2="${PLOT_BOTTOM}"></line>
      </g>
      ${gridAndTicks}
    `;
  }


export function chartSegments(series, key, scale, options = {}) {
    const values = series
      .map((point) => point[key])
      .filter((value) => value !== null && value !== undefined);
    if (!values.length) return [];
    const segments = [];
    let current = [];

    series.forEach((point, index) => {
      const value = point[key];
      if (value === null || value === undefined) {
        if (current.length) {
          segments.push(current);
          current = [];
        }
        return;
      }
      const x = xAt(index, series.length);
      const y = yAt(value, scale);
      if (options.lineShape === "step_after" && current.length) {
        const previous = current[current.length - 1];
        const previousY = previous.split(",")[1];
        current.push(`${x.toFixed(2)},${previousY}`);
      }
      current.push(`${x.toFixed(2)},${y.toFixed(2)}`);
    });

    if (current.length) segments.push(current);
    return segments.map((segment) => segment.join(" "));
  }


export function renderChartPolylines(series, key, className, scale) {
    return chartSegments(series, key, scale)
      .map((points) => `<polyline class="chart-line ${className}" points="${escapeHtml(points)}"></polyline>`)
      .join("");
  }


export function attachChartTooltip(svg, tooltip, series) {
    if (!svg || !tooltip || !series.length) return;
    const wrap = svg.parentElement;
    let lastIndex = -1;
    let tooltipRect = null;

    function show(index, clientX, clientY) {
      const point = series[index];
      if (index !== lastIndex) {
        tooltip.innerHTML = `
          <div><strong>${escapeHtml(point.date)}</strong></div>
          <div>${bilingualLabel("Close")}: ${escapeHtml(fmtNumber(point.close))}</div>
          <div>${bilingualLabel("Drawdown")}: ${escapeHtml(fmtNumber(point.drawdown_pct))}%</div>
          <div>${bilingualLabel("Bear/Bull Level")}: ${escapeHtml(fmtNumber(point.bear_market_level))}</div>
        `;
        lastIndex = index;
        tooltip.style.left = "-9999px";
        tooltip.style.top = "-9999px";
        tooltip.classList.add("visible");
        tooltipRect = tooltip.getBoundingClientRect();
      }
      const wrapRect = wrap.getBoundingClientRect();
      let left = clientX - wrapRect.left + 12;
      let top = clientY - wrapRect.top - tooltipRect.height - 12;
      if (left + tooltipRect.width > wrapRect.width) {
        left = wrapRect.width - tooltipRect.width - 8;
      }
      if (left < 0) {
        left = 8;
      }
      if (top < 0) {
        top = clientY - wrapRect.top + 16;
      }
      if (top + tooltipRect.height > wrapRect.height) {
        top = wrapRect.height - tooltipRect.height - 8;
      }
      tooltip.style.left = `${left}px`;
      tooltip.style.top = `${top}px`;
    }

    function hide() {
      tooltip.classList.remove("visible");
      lastIndex = -1;
      tooltipRect = null;
    }

    svg.addEventListener("mousemove", (event) => {
      const rect = svg.getBoundingClientRect();
      const scaleX = CHART_WIDTH / rect.width;
      const x = (event.clientX - rect.left) * scaleX - MARGIN_LEFT;
      const ratio = Math.max(0, Math.min(1, x / PLOT_WIDTH));
      const index = Math.min(
        series.length - 1,
        Math.max(0, Math.round(ratio * (series.length - 1)))
      );
      show(index, event.clientX, event.clientY);
    });

    svg.addEventListener("mouseleave", hide);

    svg.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        hide();
      }
    });
  }


export function xAxisTicks(series) {
    if (!series.length) return [];
    const n = series.length;
    if (n <= X_AXIS_TICK_COUNT) {
      return series.map((point, i) => ({ date: point.date, x: xAt(i, n) }));
    }
    const step = Math.max(1, Math.round(n / X_AXIS_TICK_COUNT));
    const indexes = [0];
    for (let i = step; i < n - 1; i += step) {
      indexes.push(i);
    }
    if (indexes[indexes.length - 1] !== n - 1) {
      indexes.push(n - 1);
    }
    return indexes.map((i) => ({ date: series[i].date, x: xAt(i, n) }));
  }


export function renderXAxisTicks(series) {
    const ticks = xAxisTicks(series);
    return ticks
      .map((tick, index) => {
        return `
          <g class="chart-tick" transform="translate(${tick.x.toFixed(2)} ${PLOT_BOTTOM})">
            <line y2="8"></line>
            <text class="chart-x-label" y="${MARKET_X_LABEL_Y}" text-anchor="middle" x="0" transform="rotate(-35 0 ${MARKET_X_LABEL_Y})">${escapeHtml(fmtMonthYear(tick.date))}</text>
          </g>
        `;
      })
      .join("");
  }


export function renderMarketChart(market) {
    if (!market.series || !market.series.length) {
      return `<p class="status">No chart data available.</p>`;
    }
    const fullSeries = market.series;
    const scale = chartScale(fullSeries);
    return `
      <div class="chart-wrap">
        <svg class="market-chart" viewBox="0 0 ${CHART_WIDTH} ${CHART_HEIGHT}" role="img" aria-label="${escapeHtml(market.title)} market phase chart">
          ${renderYAxisAndGrid(yAxisTicks(fullSeries, Y_AXIS_TICK_COUNT), scale)}
          ${renderChartPolylines(fullSeries, "bear_market_level", "chart-level", scale)}
          ${renderChartPolylines(fullSeries, "bull_market_index", "chart-bull", scale)}
          ${renderChartPolylines(fullSeries, "bear_market_index", "chart-bear", scale)}
          ${renderXAxisTicks(fullSeries)}
        </svg>
        <div class="chart-tooltip" aria-hidden="true"></div>
      </div>
      <div class="chart-legend">
        <span><i class="legend-bull"></i>${bilingualLabel("Bull segment")}</span>
        <span><i class="legend-bear"></i>${bilingualLabel("Bear segment")}</span>
        <span><i class="legend-level"></i>${bilingualLabel("Bear/Bull level")}</span>
      </div>
    `;
  }


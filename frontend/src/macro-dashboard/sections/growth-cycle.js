import { state } from "../state.js";
import {
  $, escapeHtml, fmtDate, fmtNumber, fmtIsmIndex, fmtMonthYear, fmtIsmPointChange,
  ismBadgeClass, zhLabel, bilingualLabel, bilingualTitle, titleCaseToken,
  fmtSignedPctDecimal, fmtDirectionalPct, fmtPercentRank, fmtDirectionalPercentRank,
  fmtSignedUsdMillions, fmtUsdMillions, fmtRate, fmtStatus, fmtIsmBreadthCount,
  formatPressureValue, formatToneValue, toneBadgeClass,
  formatMinutesConfirmation, formatRiskFocus, formatPolicyConviction,
  formatPolicyAction, formatOverallBias, formatToneChange,
} from "../utils.js";
import { loadGrowthCycleDetail, fetchGrowthCycle } from "../api.js";
import { filterChartForRange, CHART_RANGE_OPTIONS } from "../charts.js";
import { renderRatesDetailChart, attachRatesChartTooltips, renderMacroAiInterpretation, renderUsRatesLiquidity } from "./us-rates-liquidity.js";
import { renderDetailPanel } from "../detail-panel.js";
import { renderOverview } from "./benchmark-grid.js";
import { renderSurveySynthesis, renderSurveySynthesisCard } from "./survey-synthesis.js";

export async function loadGrowthCycle() {
    await fetchGrowthCycle();
    renderGrowthCycle();
    renderSurveySynthesis();
  }


export function growthCycleCardsById(cards) {
    const result = {};
    for (const card of cards || []) {
      result[card.id] = card;
    }
    return result;
  }


export function selectGrowthCycleSection(sections) {
    const availableSections = sections || [];
    if (!availableSections.length) return null;
    const current = availableSections.find((section) => section.id === state.selectedGrowthCycleSectionId);
    if (current) return current;
    const manufacturing = availableSections.find((section) => section.id === "ism_manufacturing");
    const next = manufacturing || availableSections[0];
    state.selectedGrowthCycleSectionId = next.id;
    return next;
  }


export function growthCycleStatusLabel(status) {
    const labels = {
      available: "Available",
      missing: "Missing",
      pending_inputs: "Pending Inputs",
    };
    return labels[status] || fmtStatus(status || "unknown");
  }


export function renderGrowthCycleStatusPanel(section) {
    const period = section.period ? `<small>${escapeHtml(fmtDate(section.period))}</small>` : "";
    return `
      <div class="growth-section-status growth-section-status-${escapeHtml(section.status || "missing")}">
        <strong>${escapeHtml(growthCycleStatusLabel(section.status))}</strong>
        ${period}
      </div>
    `;
  }


export function renderGrowthCycleSection(section, cardsById) {
    const cardIds = section.cards || [];
    const cards = cardIds.map((cardId) => cardsById[cardId]).filter(Boolean);
    const cardHtml = cards.map((card) => {
      if (card.id === "fomc_calendar" || card.id === "fomc_tone") {
        return renderFomcCard(card);
      }
      return renderCard(card);
    }).join("");
    return `
      <section class="growth-section growth-section-${escapeHtml(section.id || "unknown")}">
        <div class="growth-section-head">
          <div>
            <h3>${escapeHtml(section.title || "")}</h3>
            <p>${escapeHtml(section.subtitle || "")}</p>
          </div>
          ${section.period ? `<span class="mock-pill">Data as of ${escapeHtml(fmtDate(section.period))}</span>` : ""}
        </div>
        ${cardHtml ? `<div class="growth-section-card-grid">${cardHtml}</div>` : renderGrowthCycleStatusPanel(section)}
      </section>
    `;
  }


export function renderGrowthCycleSections(sections, cards) {
    const cardsById = growthCycleCardsById(cards);
    return (sections || [])
      .map((section) => renderGrowthCycleSection(section, cardsById))
      .join("");
  }


export function renderGrowthCycleTabs(sections, cards) {
    const activeSection = selectGrowthCycleSection(sections);
    if (!activeSection) return "";
    const cardsById = growthCycleCardsById(cards);
    return `
      <div class="growth-cycle-tabs" role="tablist" aria-label="Growth Cycle sections">
        ${sections.map((section) => {
          const active = section.id === activeSection.id;
          return `<button
            class="growth-cycle-tab${active ? " active" : ""}"
            id="growth-cycle-tab-${escapeHtml(section.id)}"
            type="button"
            role="tab"
            data-growth-cycle-section-id="${escapeHtml(section.id)}"
            aria-selected="${active}"
            aria-controls="growth-cycle-panel-${escapeHtml(section.id)}"
            tabindex="${active ? "0" : "-1"}"
          >${escapeHtml(section.title || "Growth Cycle")}</button>`;
        }).join("")}
      </div>
      <div
        id="growth-cycle-panel-${escapeHtml(activeSection.id)}"
        class="growth-cycle-tab-panel"
        role="tabpanel"
        aria-labelledby="growth-cycle-tab-${escapeHtml(activeSection.id)}"
      >${renderGrowthCycleSection(activeSection, cardsById)}</div>
    `;
  }


export function bindGrowthCycleTabs(container, sections) {
    const buttons = container.querySelectorAll("[data-growth-cycle-section-id]");
    function activate(sectionId, focus) {
      state.selectedGrowthCycleSectionId = sectionId;
      renderGrowthCycle();
      if (focus) {
        const btn = container.querySelector(`[data-growth-cycle-section-id="${sectionId}"]`);
        if (btn) btn.focus();
      }
    }
    buttons.forEach((button) => {
      button.addEventListener("click", () => {
        activate(button.dataset.growthCycleSectionId, false);
      });
      button.addEventListener("keydown", (event) => {
        const index = Array.prototype.indexOf.call(buttons, event.currentTarget);
        let nextIndex = null;
        if (event.key === "ArrowRight") nextIndex = (index + 1) % buttons.length;
        if (event.key === "ArrowLeft") nextIndex = (index - 1 + buttons.length) % buttons.length;
        if (event.key === "Home") nextIndex = 0;
        if (event.key === "End") nextIndex = buttons.length - 1;
        if (nextIndex === null) return;
        event.preventDefault();
        activate(buttons[nextIndex].dataset.growthCycleSectionId, true);
      });
    });
  }


export function renderGrowthCycle() {
    const section = $("growthCycle");
    if (!section) return;
    const head = section.querySelector(".relationship-head");
    if (state.growthCycleError) {
      section.innerHTML = `${head.outerHTML}<p class="growth-empty">Failed to load growth cycle data.</p>`;
      return;
    }
    if (!state.growthCycle) {
      section.innerHTML = `${head.outerHTML}<div class="growth-loading">Loading growth cycle data...</div>`;
      return;
    }
    if (state.growthCycle.missing) {
      section.innerHTML = `${head.outerHTML}<p class="growth-empty">${escapeHtml(state.growthCycle.missing)}</p>`;
      return;
    }
    const cards = state.growthCycle.headline || [];
    const sections = state.growthCycle.sections || [];
    const tabsHtml = renderGrowthCycleTabs(sections, cards);
    section.innerHTML = `
      ${head.outerHTML}
      ${tabsHtml ? `
        <div class="rates-detail gdp-detail">
          ${tabsHtml}
        </div>
      ` : ""}
    `;
    bindGrowthCycleTabs(section, sections);
    section.querySelectorAll("[data-growth-cycle-detail-id]").forEach((button) => {
      button.addEventListener("click", () => {
        state.selectedGrowthCycleDetailId = state.selectedGrowthCycleDetailId === button.dataset.growthCycleDetailId
          ? null
          : button.dataset.growthCycleDetailId;
        state.selectedBenchmarkId = null;
        state.selectedRatesDetailId = null;
        renderOverview();
        renderUsRatesLiquidity();
        renderGrowthCycle();
        renderDetailPanel();
      });
    });
  }


export function renderIsmRelationshipContext(context) {
    if (!context) return "";
    return `
      <div class="ism-relationship-context ism-relationship-context-${escapeHtml(context.state || "mixed")}">
        <strong class="ism-relationship-context-state">${escapeHtml(context.label || "Mixed")}</strong>
        <span>${escapeHtml(context.description || "")}</span>
      </div>
    `;
  }


export function fmtIsmSmallMultipleValue(value, unit) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return "n/a";
    if (unit === "percent") return `${Number(value).toFixed(1)}%`;
    return Number(value).toFixed(1);
  }


export function rebaseVisibleSmallMultipleSeries(chart) {
    const series = (chart.series || []).map((point) => ({ ...point }));
    const basePoint = series.find((point) => point.sp500_close !== null && point.sp500_close !== undefined);
    const base = basePoint?.sp500_close;
    if (!base) return series;
    return series.map((point) => ({
      ...point,
      sp500_index: point.sp500_close === null || point.sp500_close === undefined
        ? null
        : Number(((point.sp500_close / base) * 100).toFixed(4)),
    }));
  }


export function rebaseVisibleSmallMultipleChart(chart) {
    return {
      ...chart,
      series: rebaseVisibleSmallMultipleSeries(chart),
    };
  }


export function ismSparklineValues(series, key, referenceLines = []) {
    return [
      ...series.map((point) => point[key]),
      ...referenceLines.map((line) => line.value),
    ].filter((value) => value !== null && value !== undefined && Number.isFinite(Number(value)));
  }


export function ismSparklineScale(series, key, referenceLines = []) {
    const values = ismSparklineValues(series, key, referenceLines);
    if (!values.length) return null;
    const min = Math.min(...values);
    const max = Math.max(...values);
    const padding = Math.max((max - min) * 0.12, Math.abs(max || min || 1) * 0.02, 0.5);
    return {
      min: min - padding,
      max: max + padding,
      range: max - min + padding * 2 || 1,
    };
  }


export function ismSparklineXAt(index, count) {
    if (count <= 1) return 48 + 850 / 2;
    return 48 + (index / (count - 1)) * 850;
  }


export function ismSparklineYAt(value, scale) {
    return 10 + ((scale.max - value) / scale.range) * 42;
  }


export function ismSparklineSegments(series, key, scale, lineShape) {
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
      const x = ismSparklineXAt(index, series.length);
      const y = ismSparklineYAt(value, scale);
      if (lineShape === "step_after" && current.length) {
        const previous = current[current.length - 1];
        const previousY = previous.split(",")[1];
        current.push(`${x.toFixed(2)},${previousY}`);
      }
      current.push(`${x.toFixed(2)},${y.toFixed(2)}`);
    });
    if (current.length) segments.push(current);
    return segments.map((segment) => segment.join(" "));
  }


export function ismSparklineYearTicks(series) {
    const byYear = new Map();
    series.forEach((point, index) => {
      const year = String(point.date || "").slice(0, 4);
      const month = String(point.date || "").slice(5, 7);
      if (!year || month !== "01") return;
      if (!byYear.has(year)) {
        byYear.set(year, { date: point.date, index });
      }
    });
    const years = [...byYear.keys()].sort();
    const step = Math.max(1, Math.ceil(years.length / 8));
    return years
      .filter((year, index) => index % step === 0)
      .map((year) => ({
        year,
        x: ismSparklineXAt(byYear.get(year).index, series.length),
      }));
  }


export function renderIsmSparklineReferenceLines(panel, scale) {
    return (panel.reference_lines || [])
      .filter((line) => line.value !== null && line.value !== undefined)
      .map((line) => {
        const y = ismSparklineYAt(line.value, scale);
        return `
          <g class="ism-sparkline-reference">
            <line x1="48" y1="${y.toFixed(2)}" x2="898" y2="${y.toFixed(2)}"></line>
            <text x="892" y="${Math.max(12, y - 5).toFixed(2)}" text-anchor="end">${escapeHtml(line.label || "")}</text>
          </g>
        `;
      })
      .join("");
  }


export function renderIsmSparklineAxis(series, showXAxis) {
    if (!showXAxis) return "";
    return ismSparklineYearTicks(series)
      .map((tick) => `
        <g class="ism-sparkline-x-tick" transform="translate(${tick.x.toFixed(2)} 60)">
          <line y2="4"></line>
          <text y="15" text-anchor="middle">${escapeHtml(tick.year)}</text>
        </g>
      `)
      .join("");
  }


export function renderIsmSparklineSvg(series, panel, unit, showXAxis) {
    const key = panel.key;
    const scale = ismSparklineScale(series, key, panel.reference_lines || []);
    if (!scale) return `<p class="status">No chart data available.</p>`;
    const segments = ismSparklineSegments(series, key, scale, panel.line_shape);
    const latest = [...series].reverse().find((point) => point[key] !== null && point[key] !== undefined);
    return `
      <div class="ism-sparkline-plot">
        <svg class="relationship-chart-svg ism-sparkline-svg" viewBox="0 0 960 76" role="img" aria-label="${escapeHtml(panel.title || key)}">
          <line class="ism-sparkline-axis" x1="48" y1="60" x2="898" y2="60"></line>
          ${scale.min <= 0 && scale.max >= 0 ? `<line class="ism-sparkline-zero" x1="48" y1="${ismSparklineYAt(0, scale).toFixed(2)}" x2="898" y2="${ismSparklineYAt(0, scale).toFixed(2)}"></line>` : ""}
          ${renderIsmSparklineReferenceLines(panel, scale)}
          ${segments.map((points) => `<polyline class="relationship-line relationship-line-0 ism-sparkline-line" points="${escapeHtml(points)}"></polyline>`).join("")}
          ${latest ? `<text class="ism-sparkline-latest" x="930" y="${ismSparklineYAt(latest[key], scale).toFixed(2)}" text-anchor="end">${escapeHtml(fmtIsmSmallMultipleValue(latest[key], unit))}</text>` : ""}
          ${renderIsmSparklineAxis(series, showXAxis)}
        </svg>
      </div>
    `;
  }


export function renderIsmSmallMultiplePanel(chart, panel, panelIndex) {
    const series = chart.series || [];
    const key = panel.key;
    const title = panel.title || key;
    const unit = panel.unit || "raw";
    const panelSeries = series.map((point) => ({
      date: point.date,
      gdp_period: point.gdp_period,
      [key]: point[key],
    }));
    const showXAxis = panelIndex === (chart.panels || []).length - 1;
    return `
      <div class="ism-small-panel" data-ism-panel-key="${escapeHtml(key)}">
        <div class="ism-small-panel-meta">
          <strong>${escapeHtml(title)}</strong>
          <span>${escapeHtml(panel.subtitle || panel.cadence || unit)}</span>
        </div>
        ${renderIsmSparklineSvg(panelSeries, panel, unit, showXAxis)}
      </div>
    `;
  }


export function renderIsmSmallMultiples(chart) {
    const visibleChart = rebaseVisibleSmallMultipleChart(chart);
    return `
      <article class="relationship-chart-card ism-small-multiples">
        <div class="chart-card-head">
          <h4>${escapeHtml(chart.title || "")}</h4>
        </div>
        <div class="ism-relationship-context-list">
          ${(chart.contexts || []).map((context) => renderIsmRelationshipContext(context)).join("")}
        </div>
        <div class="chart-tooltip ism-shared-tooltip" aria-hidden="true"></div>
        <div class="ism-small-panel-list">
          ${(visibleChart.panels || []).map((panel, index) => renderIsmSmallMultiplePanel(visibleChart, panel, index)).join("")}
        </div>
      </article>
    `;
  }


export function renderIsmDetailChart(chart, chartIndex, _focusedChartId) {
    if (chart.kind === "heat_map") {
      return `
        <article class="relationship-chart-card ism-detail-card">
          <div class="chart-card-head">
            <h4>${escapeHtml(chart.title || "")}</h4>
          </div>
          ${renderIsmHeatMap(chart)}
        </article>
      `;
    }
    if (chart.kind === "small_multiples") {
      return renderIsmSmallMultiples(chart);
    }
    return `
      <article class="ism-relationship-chart-card">
        ${chart.contexts ? `
          <div class="ism-relationship-context-list">
            ${(chart.contexts || []).map((context) => renderIsmRelationshipContext(context)).join("")}
          </div>
        ` : renderIsmRelationshipContext(chart.context)}
        ${renderRatesDetailChart(chart, chartIndex)}
      </article>
    `;
  }


export function renderIsmOfficialReportSummary(summary) {
    if (!summary) return "";
    const changes = (summary.major_changes || [])
      .map((item) => `<div class="ism-official-major-change">${escapeHtml(item)}</div>`)
      .join("");
    const commentsData = summary.respondent_comments || [];
    const commentPreviewCount = summary.comment_preview_count || 3;
    const hiddenCommentCount = Math.max(0, commentsData.length - commentPreviewCount);
    const comments = commentsData
      .map((comment, index) => `
        <div class="ism-official-comment-row${index >= commentPreviewCount ? " ism-official-comment-row-extra" : ""}">
          <span class="ism-official-comment-industry">${escapeHtml(comment.industry || "")}</span>
          <p class="ism-official-comment-text">${escapeHtml(comment.comment_text || "")}</p>
        </div>
      `)
      .join("");
    return `
      <section class="relationship-chart-card ism-official-summary">
        <div class="chart-card-head">
          <h4>${bilingualLabel("Official Report Summary")}</h4>
        </div>
        <div class="ism-official-summary-row">
          <span class="ism-official-summary-label">${bilingualLabel("Headline")}</span>
          <p class="ism-official-summary-value">${escapeHtml(summary.headline || "")}</p>
        </div>
        ${changes ? `
          <div class="ism-official-summary-row">
            <span class="ism-official-summary-label">${bilingualLabel("Major Changes")}</span>
            <div class="ism-official-summary-value ism-official-major-change-list">${changes}</div>
          </div>
        ` : ""}
        ${comments ? `
          <div class="ism-official-summary-row">
            <span class="ism-official-summary-label">${bilingualLabel("Respondent Comments")}</span>
            <div class="ism-official-summary-value">
              <div class="ism-official-comment-list">${comments}</div>
              ${hiddenCommentCount ? `
                <button type="button" class="ism-official-comment-toggle" data-ism-comment-toggle>
                  ${bilingualLabel(`Show all ${commentsData.length} comments`)}
                </button>
              ` : ""}
            </div>
          </div>
        ` : ""}
        <div class="ism-official-summary-footer">
          <span>${escapeHtml(summary.title || "")}</span>
          ${summary.source_url ? `<a href="${escapeHtml(summary.source_url)}" target="_blank" rel="noopener noreferrer">${bilingualLabel("Official ISM Report")} &rarr;</a>` : ""}
        </div>
      </section>
    `;
  }


export function attachIsmOfficialSummaryHandlers(body) {
    body.querySelectorAll("[data-ism-comment-toggle]").forEach((button) => {
      button.addEventListener("click", () => {
        const row = button.closest(".ism-official-summary-row");
        const list = row ? row.querySelector(".ism-official-comment-list") : null;
        if (!list) return;
        const expanded = list.classList.toggle("expanded");
        button.textContent = expanded
          ? bilingualLabel("Show fewer comments")
          : bilingualLabel(`Show all ${list.querySelectorAll(".ism-official-comment-row").length} comments`);
      });
    });
  }


export function attachIsmSharedTooltip(body, chart) {
    const container = body.querySelector(".ism-small-multiples");
    if (!container) return;
    const tooltip = container.querySelector(".ism-shared-tooltip");
    if (!tooltip) return;
    const series = chart.series || [];
    const panels = chart.panels || [];
    const svgs = container.querySelectorAll(".ism-small-panel .relationship-chart-svg");

    function showTooltip(index) {
      const point = series[index];
      if (!point) return;
      const date = fmtMonthYear(point.date);
      const rows = panels.map((panel) => {
        const value = point[panel.key];
        const formattedValue = fmtIsmSmallMultipleValue(value, panel.unit);
        const text = panel.key === "gdp_growth" && point.gdp_period
          ? `${formattedValue} (${point.gdp_period})`
          : formattedValue;
        return `
          <div class="chart-tooltip-row">
            <span>${escapeHtml(panel.title || panel.key)}</span>
            <strong>${escapeHtml(text)}</strong>
          </div>
        `;
      }).join("");
      tooltip.innerHTML = `<div><strong>${escapeHtml(date)}</strong></div>${rows}`;
      tooltip.classList.add("visible");
    }

    function hideTooltip() {
      tooltip.classList.remove("visible");
    }

    function positionTooltip(e, containerRect) {
      const tooltipRect = tooltip.getBoundingClientRect();
      const left = e.clientX - containerRect.left - tooltipRect.width / 2;
      const top = e.clientY - containerRect.top - tooltipRect.height - 10;
      tooltip.style.left = `${Math.max(0, Math.min(containerRect.width - tooltipRect.width, left))}px`;
      tooltip.style.top = `${Math.max(0, top)}px`;
    }

    svgs.forEach((svg) => {
      const wrap = svg.parentElement;
      svg.addEventListener("mousemove", (e) => {
        const wrapRect = wrap.getBoundingClientRect();
        const containerRect = container.getBoundingClientRect();
        const mouseX = e.clientX - wrapRect.left;
        const index = Math.round((mouseX / wrapRect.width) * (series.length - 1));
        const clamped = Math.max(0, Math.min(series.length - 1, index));
        showTooltip(clamped);
        positionTooltip(e, containerRect);
      });
      svg.addEventListener("mouseleave", hideTooltip);
    });

    const scrollParent = body.closest(".detail-scroll");
    if (scrollParent) {
      scrollParent.addEventListener("scroll", hideTooltip);
    }
  }


export function renderIsmDetailInPanel(body, payload) {
    const charts = (payload.charts || []).map((chart) => (
      filterChartForRange(chart, state.selectedGrowthCycleChartRange)
    ));
    const lineCharts = charts.filter((chart) => (
      chart.kind !== "heat_map" && chart.kind !== "small_multiples"
    ));
    const renderedCharts = charts.map((chart, index) => (
      renderIsmDetailChart(chart, index, null)
    ));
    const latest = payload.latest || {};
    const latestMetadata = payload.latest_metadata || {};
    const latestGroups = payload.detail_groups || [];

    const industryAnalysis = payload.industry_analysis;
    let selectedIndustryData = null;
    if (industryAnalysis && industryAnalysis.status !== "unavailable" && industryAnalysis.industries && industryAnalysis.industries.length) {
      if (!state.selectedIsmIndustry || !industryAnalysis.industries.some((ind) => ind.industry === state.selectedIsmIndustry)) {
        state.selectedIsmIndustry = industryAnalysis.industries[0].industry;
      }
      selectedIndustryData = industryAnalysis.industries.find((ind) => ind.industry === state.selectedIsmIndustry) || industryAnalysis.industries[0];
    } else {
      state.selectedIsmIndustry = null;
    }

    body.innerHTML = `
      ${renderGrowthCycleRangeControl()}
      ${renderIsmOfficialReportSummary(payload.official_report_summary)}
      <details class="ism-section-collapse"${renderedCharts.length ? "" : ""}>
        <summary>${bilingualLabel("Charts & Heat Maps")}</summary>
        <div class="relationship-chart-grid ism-detail-grid">
          ${renderedCharts.join("")}
        </div>
      </details>
      ${latestGroups.length ? `<details class="ism-section-collapse" open>
        <summary>${bilingualLabel("Latest Values")}</summary>
        <div class="ism-detail-latest ism-detail-latest-collapsible">
        ${latestGroups.map((group) => {
          if (group.industry_breadth || group.label === "Industry Breadth") {
            return renderIsmIndustryBreadthGroup(group);
          }
          return `
          <div class="ism-latest-group">
            <strong class="ism-latest-group-label">${escapeHtml(group.label || "")}</strong>
            ${group.required_inputs ? `
              <div class="gdp-expectations-context">
                <ul>${group.required_inputs.map((input) => `<li>${escapeHtml(input)}</li>`).join("")}</ul>
              </div>
            ` : `
              <div class="ism-latest-group-rows">
                ${group.keys.map((key) => `
                  <div class="ism-metric-row">
                    <span>${escapeHtml((charts[0]?.labels || {})[key] || key)}</span>
                    <div class="ism-metric-value">
                      <strong>${escapeHtml(fmtIsmIndex(latest[key]))}</strong>
                      ${latestMetadata[key] ? renderIsmTrendChip(latestMetadata[key]) : ""}
                    </div>
                  </div>
                `).join("")}
              </div>
            `}
          </div>
        `}).join("")}
        </div>
      </details>` : ""}
      <details class="ism-section-collapse" open>
        <summary>${bilingualLabel("Industry Analysis (6 Month)")}</summary>
        ${renderIsmIndustryAnalysisSection(industryAnalysis, selectedIndustryData)}
      </details>
    `;
    bindGrowthCycleRangeControl(body);
    attachIsmOfficialSummaryHandlers(body);
    attachRatesChartTooltips(body, lineCharts);
    const multiChart = charts.find((c) => c.kind === "small_multiples");
    if (multiChart) attachIsmSharedTooltip(body, rebaseVisibleSmallMultipleChart(multiChart));
    if (industryAnalysis && industryAnalysis.status !== "unavailable" && industryAnalysis.industries && industryAnalysis.industries.length) {
      bindIsmIndustrySelector(body, industryAnalysis);
    }
  }


export const SERVICES_COMMODITY_GROUPS = Object.freeze([
    { signalType: "up_in_price", label: "Prices increased", tone: "higher" },
    { signalType: "down_in_price", label: "Prices decreased", tone: "lower" },
    { signalType: "short_supply", label: "In short supply", tone: "shortage" },
  ]);


export function renderServicesCommodityGroups(commodities) {
    return SERVICES_COMMODITY_GROUPS.map((group) => {
      const items = (commodities || []).filter((item) => item.signal_type === group.signalType);
      if (!items.length) return "";
      return `
        <div class="ism-services-commodity-group ism-services-commodity-${escapeHtml(group.tone)}">
          <h6>${escapeHtml(group.label)}</h6>
          <ul>${items.map((item) => `
            <li><strong>${escapeHtml(item.commodity || "")}</strong>${item.months != null ? ` <span>${escapeHtml(String(item.months))} months</span>` : ""}</li>
          `).join("")}</ul>
        </div>
      `;
    }).join("");
  }


export function renderServicesNarrativeFacts(facts) {
    if (!facts || !Object.keys(facts).length) return "";
    const rows = [];
    if (facts.consecutive_expansion_months != null) {
      rows.push(`Services activity expanded for ${escapeHtml(String(facts.consecutive_expansion_months))} consecutive months.`);
    }
    if (facts.services_economy_gdp_share_percent != null) {
      rows.push(`Services industries represent ${escapeHtml(String(facts.services_economy_gdp_share_percent))}% of U.S. GDP.`);
    }
    rows.push(facts.broad_based_expansion_mentioned
      ? "Broad-based expansion was mentioned in the report."
      : "Broad-based expansion was not mentioned in the report.");
    rows.push(facts.inflationary_pressure_mentioned
      ? "Inflationary pressure was mentioned in the report."
      : "Inflationary pressure was not mentioned in the report.");
    return `<ul class="ism-services-narrative-list">${rows.map((row) => `<li>${row}</li>`).join("")}</ul>`;
  }


export const SERVICES_COMPONENT_LABELS = Object.freeze({
    business_activity: "Business Activity",
    new_orders: "New Orders",
    employment: "Employment",
    supplier_deliveries: "Supplier Deliveries",
    inventories: "Inventories",
    inventory_sentiment: "Inventory Sentiment",
    prices: "Prices",
    backlog: "Order Backlog",
    new_export_orders: "New Export Orders",
    imports: "Imports",
  });


export function readableServicesDirection(direction) {
    return String(direction || "")
      .replaceAll("_", " ")
      .replace(/^./, (character) => character.toUpperCase());
  }


export function renderServicesRankedIndustryList(items, direction, emptyLabel) {
    const rows = (items || []).map((item, index) => {
      const prefix = direction === "growth" ? MEDALS[index] || "" : "\uD83D\uDD3B";
      const selected = state.selectedServicesIndustry === item.industry;
      return `
        <button type="button" class="ism-industry-list-button${selected ? " ism-industry-button-selected" : ""}" data-services-industry="${escapeHtml(item.industry)}" aria-pressed="${selected ? "true" : "false"}">
          <span class="ism-industry-list-text">${prefix} ${escapeHtml(item.industry)}</span>
          <small class="ism-industry-zh">#${escapeHtml(String(item.rank))}</small>
        </button>
      `;
    }).join("");
    return rows || `<p class="ism-industry-empty">${escapeHtml(emptyLabel)}</p>`;
  }


export function renderServicesSignalTrend(signalTrend) {
    if (!signalTrend || !signalTrend.length) return "";
    const sorted = [...signalTrend].sort((a, b) => a.period.localeCompare(b.period));
    const headers = [
      "Period", "Overall",
      "Business Activity", "New Orders", "Employment",
      "Supplier Deliveries", "Inventories", "Inventory Sentiment",
      "Prices", "Order Backlog", "New Export Orders", "Imports",
    ];
    const componentKeys = [
      "business_activity", "new_orders", "employment",
      "supplier_deliveries", "inventories", "inventory_sentiment",
      "prices", "backlog", "new_export_orders", "imports",
    ];
    const rows = sorted.map((point) => {
      const cells = [fmtMonthYear(point.period), renderSignalTrendCell(point.overall)];
      componentKeys.forEach((key) => {
        const cell = (point.components || {})[key];
        cells.push(renderSignalTrendCell(cell));
      });
      return `<tr>${cells.map((c) => `<td>${c}</td>`).join("")}</tr>`;
    }).join("");
    return `
      <div class="ism-industry-trend">
        <h6>${bilingualLabel("Signal Trend")}</h6>
        <div class="ism-trend-table-wrap">
          <table class="ism-trend-table">
            <thead><tr>${headers.map((h) => `<th>${escapeHtml(h)}</th>`).join("")}</tr></thead>
            <tbody>${rows}</tbody>
          </table>
        </div>
      </div>
    `;
  }


export function renderSignalTrendCell(cell) {
    if (!cell) return "\u2014";
    if (cell.status === "listed") {
      const rankText = cell.list_size != null
        ? `#${cell.rank}/${cell.list_size}`
        : cell.rank != null ? `#${cell.rank}` : "";
      return `${escapeHtml(cell.direction_label || "")} ${escapeHtml(rankText)}`;
    }
    if (cell.status === "conflicting" || cell.status === "not_listed" || cell.status === "unavailable") {
      return escapeHtml(cell.direction_label || "");
    }
    return "\u2014";
  }


export function renderServicesSelectedComments(comments) {
    return `
      <div class="ism-industry-comments">
        <h6>${bilingualLabel("Respondent Comments")}</h6>
        ${(comments || []).length
          ? comments.map((text) => `<p class="ism-industry-comment-text">${escapeHtml(text)}</p>`).join("")
          : `<p class="ism-industry-no-comment">${bilingualLabel("No respondent comment in this report")}</p>`}
      </div>
    `;
  }


export function servicesIndustryByName(analysis, industryName) {
    return (analysis.industries || []).find((row) => row.industry === industryName) || null;
  }


export function renderServicesIndustryOptions(industries) {
    return (industries || []).map((industry) => {
      const selected = industry.industry === state.selectedServicesIndustry ? " selected" : "";
      return `<option value="${escapeHtml(industry.industry)}"${selected}>${escapeHtml(industry.industry)}</option>`;
    }).join("");
  }


export function renderServicesIndustryDetailView(industry, analysis) {
    if (!industry) return `<p class="ism-industry-unavailable">Industry analysis unavailable</p>`;
    const streak = industry.streak || {};
    const directionChange = industry.direction_change
      ? readableServicesDirection(industry.direction_change)
      : "\u2014";
    const rankChange = industry.rank_change != null
      ? `${industry.rank_change > 0 ? "+" : ""}${industry.rank_change}`
      : "\u2014";
    return `
      <div class="ism-industry-header">
        <h5>${escapeHtml(industry.industry)}</h5>
        <span class="ism-industry-period">${escapeHtml(fmtMonthYear(analysis.period || ""))}</span>
      </div>
      <div class="ism-industry-meta">
        <span>${bilingualLabel("Direction")}: ${escapeHtml(readableServicesDirection(industry.direction))}</span>
        <span>${bilingualLabel("Rank")}: #${escapeHtml(String(industry.rank))}</span>
        <span>${bilingualLabel("Rank Change")}: ${escapeHtml(rankChange)}</span>
        <span>${bilingualLabel("Direction Change")}: ${escapeHtml(directionChange)}</span>
        <span>${bilingualLabel("Streak")}: ${escapeHtml(String(streak.months || 0))} months ${escapeHtml(readableServicesDirection(streak.direction))}</span>
      </div>
      ${renderServicesSelectedComments(industry.comments)}
      ${renderServicesSignalTrend(industry.signal_trend)}
      ${analysis.source_url ? `<div class="ism-industry-source"><a href="${escapeHtml(analysis.source_url)}" target="_blank" rel="noopener noreferrer">${bilingualLabel("Official ISM Report")} &rarr;</a></div>` : ""}
    `;
  }


export function renderServicesIndustryAnalysisSection(analysis) {
    if (!analysis || analysis.status !== "available") {
      return `<section class="ism-detail-group ism-industry-analysis"><p class="ism-industry-unavailable">${escapeHtml((analysis && analysis.reason) || "Industry analysis unavailable")}</p></section>`;
    }
    const defaultIndustry = (analysis.growing_industries || [])[0] ||
      (analysis.contracting_industries || [])[0] || null;
    if (!state.selectedServicesIndustry || !servicesIndustryByName(analysis, state.selectedServicesIndustry)) {
      state.selectedServicesIndustry = defaultIndustry ? defaultIndustry.industry : null;
    }
    const selected = servicesIndustryByName(analysis, state.selectedServicesIndustry);
    const topGrowing = (analysis.growing_industries || []).slice(0, 3);
    const topContracting = (analysis.contracting_industries || []).slice(0, 3);
    const selectorOptions = renderServicesIndustryOptions(analysis.industries);
    return `
      <section class="ism-detail-group ism-industry-ranking">
        <div class="ism-industry-counts">
          <span><strong>${escapeHtml(String((analysis.growing_industries || []).length))}</strong> Growing</span>
          <span><strong>${escapeHtml(String((analysis.contracting_industries || []).length))}</strong> Contracting</span>
          <span><strong>${escapeHtml(String((analysis.industries || []).length))}</strong> Total</span>
        </div>
        <div class="ism-industry-columns">
          <div><h5>${bilingualLabel("Growing Industries")}</h5><div class="ism-industry-list">${renderServicesRankedIndustryList(topGrowing, "growth", "No growing industries")}</div></div>
          <div><h5>${bilingualLabel("Contracting Industries")}</h5><div class="ism-industry-list">${renderServicesRankedIndustryList(topContracting, "contraction", "No contracting industries")}</div></div>
        </div>
        <div class="ism-industry-selector-wrap">
          <label for="ism-services-industry-select">${bilingualLabel("Select Industry")}</label>
          <select id="ism-services-industry-select" class="ism-industry-select" data-services-industry-select>
            ${selectorOptions}
          </select>
        </div>
      </section>
      <section class="ism-detail-group ism-industry-analysis">
        <div class="ism-industry-detail" data-services-industry-detail>
          ${renderServicesIndustryDetailView(selected, analysis)}
        </div>
      </section>
    `;
  }


export function renderServicesFullEvidence(richEvidence) {
    if (!richEvidence) return "";
    const glance = richEvidence.at_a_glance_rows || [];
    const commodities = richEvidence.commodities || [];
    const narrative = richEvidence.narrative_facts || {};
    const sourceUrl = (richEvidence.source || {}).source_url || "";
    const hasData = glance.length || commodities.length ||
      Object.keys(narrative).length || sourceUrl;
    if (!hasData) return "";
    return `
      <details class="ism-section-collapse ism-services-full-evidence">
        <summary>${bilingualLabel("Full Report Evidence")}</summary>
        ${glance.length ? `
        <section class="ism-detail-group">
          <h5>${bilingualLabel("All Components")}</h5>
          <table class="ism-latest-table">
            <thead><tr><th>Component</th><th>Current</th><th>Previous</th><th>Change</th><th>Direction</th><th>Rate</th><th>Trend</th></tr></thead>
            <tbody>${glance.map((row) => `
              <tr>
                <td>${escapeHtml(row.label || row.series_id || "")}</td>
                <td>${escapeHtml(row.current_value != null ? row.current_value.toFixed(1) : "")}</td>
                <td>${escapeHtml(row.previous_value != null ? row.previous_value.toFixed(1) : "")}</td>
                <td>${escapeHtml(row.point_change != null ? (row.point_change > 0 ? "+" : "") + row.point_change.toFixed(1) : "")}</td>
                <td>${escapeHtml(row.direction || "")}</td>
                <td>${escapeHtml(row.rate_of_change || "")}</td>
                <td>${escapeHtml(row.trend_months != null ? String(row.trend_months) + "m" : "")}</td>
              </tr>
            `).join("")}</tbody>
          </table>
        </section>
        ` : ""}
        <section class="ism-detail-group">
          <h5>${bilingualLabel("Commodities")}</h5>
          <div class="ism-services-commodity-grid">${renderServicesCommodityGroups(commodities)}</div>
        </section>
        <section class="ism-detail-group">
          <h5>${bilingualLabel("Narrative Facts")}</h5>
          ${renderServicesNarrativeFacts(narrative)}
        </section>
        ${sourceUrl ? `<div class="ism-industry-source"><a href="${escapeHtml(sourceUrl)}" target="_blank" rel="noopener noreferrer">${bilingualLabel("Official ISM Report")} &rarr;</a></div>` : ""}
      </details>
    `;
  }


export function servicesStateLabel(state) {
    const labels = {
      supports_growth: "Growth",
      growth_caution: "Caution",
      supports_contraction: "Contraction",
      contraction_easing: "Easing",
      mixed: "Mixed",
      pending_inputs: "Pending",
      stale_periods: "Stale",
    };
    return labels[state] || state || "Unknown";
  }


export function renderServicesLegacyLatestTable(signal) {
    const metrics = signal.metrics || {};
    function metricDetail(key, label) {
      const m = metrics[key];
      if (!m) return "";
      const value = m.value != null ? m.value.toFixed(1) : "n/a";
      const change = m.point_change != null ? (m.point_change > 0 ? "+" : "") + m.point_change.toFixed(1) : "n/a";
      return `<tr><td>${escapeHtml(label)}</td><td>${escapeHtml(value)}</td><td>${escapeHtml(m.level || "")}</td><td>${escapeHtml(change)}</td><td>${escapeHtml(m.momentum || "")}</td></tr>`;
    }
    return `
      <table class="ism-latest-table">
        <thead><tr><th>Metric</th><th>Value</th><th>Level</th><th>Change</th><th>Momentum</th></tr></thead>
        <tbody>
          ${metricDetail("pmi", "Services PMI")}
          ${metricDetail("business_activity", "Business Activity")}
          ${metricDetail("new_orders", "New Orders")}
          ${signal.backlog_confirmation === "unavailable" ? "" : metricDetail("order_backlog", "Order Backlog")}
        </tbody>
      </table>
    `;
  }


export function renderServicesLatestValues(payload) {
    const latest = payload.latest || {};
    const metadata = payload.latest_metadata || {};
    const groups = payload.detail_groups || [];
    const signal = payload.signal || {};
    const summary = `
      <div class="ism-industry-meta">
        <span class="ism-signal-badge ism-signal-${escapeHtml(signal.state || "unknown")}">${escapeHtml(servicesStateLabel(signal.state))}</span>
        <span>Backlog: ${escapeHtml(signal.backlog_confirmation || "unavailable")}</span>
      </div>
    `;
    if (!groups.length) return `${summary}${renderServicesLegacyLatestTable(signal)}`;
    return `${summary}${groups.map((group) => `
      <div class="ism-latest-group">
        <strong class="ism-latest-group-label">${escapeHtml(group.label || "")}</strong>
        <div class="ism-latest-group-rows">
          ${(group.keys || []).map((key) => `
            <div class="ism-metric-row">
              <span>${escapeHtml(metadata[key]?.label || key)}</span>
              <div class="ism-metric-value">
                <strong>${escapeHtml(fmtIsmIndex(latest[key]))}</strong>
                ${metadata[key] ? renderIsmTrendChip(metadata[key]) : ""}
              </div>
            </div>
          `).join("")}
        </div>
      </div>
    `).join("")}`;
  }


export function renderServicesDetailInPanel(body, payload) {
    const charts = (payload.charts || []).map((chart) => (
      filterChartForRange(chart, state.selectedGrowthCycleChartRange)
    ));
    const lineCharts = charts.filter((chart) => (
      chart.kind !== "heat_map" && chart.kind !== "small_multiples"
    ));
    const renderedCharts = charts.map((chart, index) => (
      renderIsmDetailChart(chart, index, null)
    ));
    const industryAnalysis = payload.industry_analysis || null;

    body.innerHTML = `
      ${renderGrowthCycleRangeControl()}
      ${renderIsmOfficialReportSummary(payload.official_report_summary)}
      <details class="ism-section-collapse">
        <summary>${bilingualLabel("Charts & Heat Maps")}</summary>
        <div class="relationship-chart-grid ism-detail-grid">${renderedCharts.join("")}</div>
      </details>
      <details class="ism-section-collapse" open>
        <summary>${bilingualLabel("Latest Values")}</summary>
        <div class="ism-detail-latest ism-detail-latest-collapsible">
          ${renderServicesLatestValues(payload)}
        </div>
      </details>
      <details class="ism-section-collapse" open>
        <summary>${bilingualLabel("Industry Analysis (6 Month)")}</summary>
        ${renderServicesIndustryAnalysisSection(industryAnalysis)}
      </details>
      ${renderServicesFullEvidence(payload.rich_evidence)}
    `;
    bindGrowthCycleRangeControl(body);
    attachIsmOfficialSummaryHandlers(body);
    attachRatesChartTooltips(body, lineCharts);
    bindServicesIndustrySelector(body, industryAnalysis);
  }


export function selectServicesIndustry(body, analysis, industryName) {
    const selected = servicesIndustryByName(analysis, industryName);
    if (!selected) return;
    state.selectedServicesIndustry = industryName;
    body.querySelectorAll("[data-services-industry]").forEach((button) => {
      const isSelected = button.dataset.servicesIndustry === industryName;
      button.classList.toggle("ism-industry-button-selected", isSelected);
      button.setAttribute("aria-pressed", isSelected ? "true" : "false");
    });
    const detail = body.querySelector("[data-services-industry-detail]");
    if (detail) detail.innerHTML = renderServicesIndustryDetailView(selected, analysis);
    const selector = body.querySelector("[data-services-industry-select]");
    if (selector) selector.value = industryName;
  }


export function bindServicesIndustrySelector(body, analysis) {
    body.querySelectorAll("[data-services-industry]").forEach((button) => {
      button.addEventListener("click", () => {
        selectServicesIndustry(body, analysis, button.dataset.servicesIndustry);
      });
    });
    const selector = body.querySelector("[data-services-industry-select]");
    if (selector) {
      selector.addEventListener("change", () => {
        selectServicesIndustry(body, analysis, selector.value);
      });
    }
  }


export function renderGrowthCycleDetailInPanel(body) {
    const detailId = state.selectedGrowthCycleDetailId;
    if (!detailId) return;
    body.innerHTML = `<p class="status">Loading growth cycle detail...</p>`;
    loadGrowthCycleDetail(detailId)
      .then((payload) => {
        if (state.selectedGrowthCycleDetailId !== payload.detail_id) return;
        if (payload.detail_id === "ism_manufacturing") {
          renderIsmDetailInPanel(body, payload);
          return;
        }
        if (payload.detail_id === "ism_services") {
          window.ismServicesUi.renderDetail(body, payload, { renderServicesDetail: renderServicesDetailInPanel });
          return;
        }
        if (payload.detail_id === "housing_permits" && window.housingPermitsUi && window.housingPermitsUi.renderDetail) {
          window.housingPermitsUi.renderDetail(body, payload, {
            escapeHtml: escapeHtml,
            bilingualLabel: bilingualLabel,
            bilingualTitle: bilingualTitle,
            titleCaseToken: titleCaseToken,
            fmtNumber: fmtNumber,
            fmtSignedPctDecimal: fmtSignedPctDecimal,
            fmtMonthYear: fmtMonthYear,
            statusClass: ismBadgeClass,
            renderGrowthCycleRangeControl: renderGrowthCycleRangeControl,
            filterChartForRange: filterChartForRange,
            renderRatesDetailChart: renderRatesDetailChart,
            getSelectedChartRange: function () { return state.selectedGrowthCycleChartRange; },
            bindGrowthCycleRangeControl: bindGrowthCycleRangeControl,
            attachRatesChartTooltips: attachRatesChartTooltips,
          });
          return;
        }
        if (payload.detail_id === "cyclical_commodities" && window.CyclicalCommoditiesUi && window.CyclicalCommoditiesUi.renderDetail) {
          window.CyclicalCommoditiesUi.renderDetail(body, payload, {
            escapeHtml: escapeHtml,
            bilingualLabel: bilingualLabel,
            bilingualTitle: bilingualTitle,
            titleCaseToken: titleCaseToken,
            fmtNumber: fmtNumber,
            fmtSignedPctDecimal: fmtSignedPctDecimal,
            fmtMonthYear: fmtMonthYear,
            statusClass: ismBadgeClass,
          });
          return;
        }
        if (payload.detail_id === "nfib_sbo" && window.nfibSboUi && window.nfibSboUi.renderDetail) {
          window.nfibSboUi.renderDetail(body, payload, {
            escapeHtml: escapeHtml,
            bilingualLabel: bilingualLabel,
            bilingualTitle: bilingualTitle,
            titleCaseToken: titleCaseToken,
            fmtNumber: fmtNumber,
            fmtSignedPctDecimal: fmtSignedPctDecimal,
            fmtMonthYear: fmtMonthYear,
            statusClass: ismBadgeClass,
            renderGrowthCycleRangeControl: renderGrowthCycleRangeControl,
            filterChartForRange: filterChartForRange,
            renderRatesDetailChart: renderRatesDetailChart,
            getSelectedChartRange: function () { return state.selectedGrowthCycleChartRange; },
            bindGrowthCycleRangeControl: bindGrowthCycleRangeControl,
            attachRatesChartTooltips: attachRatesChartTooltips,
          });
          return;
        }
        const filteredCharts = payload.charts.map((chart) => (
          filterChartForRange(chart, state.selectedGrowthCycleChartRange)
        ));
        body.innerHTML = `
          ${renderGrowthCycleRangeControl()}
          <div class="relationship-chart-grid">
            ${filteredCharts.map((chart, index) => renderRatesDetailChart(chart, index)).join("")}
          </div>
          ${renderMacroAiInterpretation(payload.m2_ai_interpretation)}
        `;
        bindGrowthCycleRangeControl(body);
        attachRatesChartTooltips(body, filteredCharts);
      })
      .catch((error) => {
        if (state.selectedGrowthCycleDetailId !== detailId) return;
        body.innerHTML = `<p class="status">Failed to load growth cycle detail.</p>`;
        console.error(error);
      });
  }


export function rerenderGrowthCycleDetailBodyPreservingScroll() {
    const body = $("detailPanel")?.querySelector(".detail-panel-body");
    if (!body || !state.selectedGrowthCycleDetailId) {
      renderDetailPanel();
      return;
    }
    const payload = state.growthCycleDetailsById[state.selectedGrowthCycleDetailId];
    if (!payload) {
      renderGrowthCycleDetailInPanel(body);
      return;
    }
    const scrollTop = body.scrollTop;
    if (payload.detail_id === "ism_manufacturing") {
      renderIsmDetailInPanel(body, payload);
    } else if (payload.detail_id === "ism_services") {
      window.ismServicesUi.renderDetail(body, payload, { renderServicesDetail: renderServicesDetailInPanel });
    } else if (payload.detail_id === "housing_permits" && window.housingPermitsUi && window.housingPermitsUi.renderDetail) {
      window.housingPermitsUi.renderDetail(body, payload, {
        escapeHtml: escapeHtml,
        bilingualLabel: bilingualLabel,
        bilingualTitle: bilingualTitle,
        titleCaseToken: titleCaseToken,
        fmtNumber: fmtNumber,
        fmtSignedPctDecimal: fmtSignedPctDecimal,
        fmtMonthYear: fmtMonthYear,
        statusClass: ismBadgeClass,
        renderGrowthCycleRangeControl: renderGrowthCycleRangeControl,
        filterChartForRange: filterChartForRange,
        renderRatesDetailChart: renderRatesDetailChart,
        getSelectedChartRange: function () { return state.selectedGrowthCycleChartRange; },
        bindGrowthCycleRangeControl: bindGrowthCycleRangeControl,
        attachRatesChartTooltips: attachRatesChartTooltips,
      });
    } else if (payload.detail_id === "cyclical_commodities" && window.CyclicalCommoditiesUi && window.CyclicalCommoditiesUi.renderDetail) {
      window.CyclicalCommoditiesUi.renderDetail(body, payload, {
        escapeHtml: escapeHtml,
        bilingualLabel: bilingualLabel,
        bilingualTitle: bilingualTitle,
        titleCaseToken: titleCaseToken,
        fmtNumber: fmtNumber,
        fmtSignedPctDecimal: fmtSignedPctDecimal,
        fmtMonthYear: fmtMonthYear,
        statusClass: ismBadgeClass,
      });
    } else if (payload.detail_id === "nfib_sbo" && window.nfibSboUi && window.nfibSboUi.renderDetail) {
      window.nfibSboUi.renderDetail(body, payload, {
        escapeHtml: escapeHtml,
        bilingualLabel: bilingualLabel,
        bilingualTitle: bilingualTitle,
        titleCaseToken: titleCaseToken,
        fmtNumber: fmtNumber,
        fmtSignedPctDecimal: fmtSignedPctDecimal,
        fmtMonthYear: fmtMonthYear,
        statusClass: ismBadgeClass,
        renderGrowthCycleRangeControl: renderGrowthCycleRangeControl,
        filterChartForRange: filterChartForRange,
        renderRatesDetailChart: renderRatesDetailChart,
        getSelectedChartRange: function () { return state.selectedGrowthCycleChartRange; },
        bindGrowthCycleRangeControl: bindGrowthCycleRangeControl,
        attachRatesChartTooltips: attachRatesChartTooltips,
      });
    } else {
      const filteredCharts = payload.charts.map((chart) => (
        filterChartForRange(chart, state.selectedGrowthCycleChartRange)
      ));
      body.innerHTML = `
        ${renderGrowthCycleRangeControl()}
        <div class="relationship-chart-grid">
          ${filteredCharts.map((chart, index) => renderRatesDetailChart(chart, index)).join("")}
        </div>
        ${renderMacroAiInterpretation(payload.m2_ai_interpretation)}
      `;
      bindGrowthCycleRangeControl(body);
      attachRatesChartTooltips(body, filteredCharts);
    }
    body.scrollTop = scrollTop;
  }


export function renderIsmHeatMap(chart) {
    const rows = (chart.series || []).slice().reverse();
    if (!rows.length) return `<p class="status">No ISM history available.</p>`;
    const keys = chart.keys || [];
    const labels = chart.labels || {};
    return `
      <div class="ism-detail-heat-map" style="--ism-heat-metrics: ${keys.length}">
        <div class="ism-heat-header">Date</div>
        ${keys.map((key) => `<div class="ism-heat-header">${escapeHtml(labels[key] || key)}</div>`).join("")}
        ${rows.map((row) => `
          <div class="ism-heat-date">${escapeHtml(fmtDate(row.date))}</div>
          ${keys.map((key) => `
            <div class="ism-heat-cell ${ismHeatMapCellClass(row[key])}">
              ${escapeHtml(fmtIsmIndex(row[key]))}
            </div>
          `).join("")}
        `).join("")}
      </div>
    `;
  }


export function ismHeatMapCellClass(value) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return "ism-heat-cell-missing";
    if (numeric >= 62) return "ism-heat-cell-very-strong";
    if (numeric >= 55) return "ism-heat-cell-strong";
    if (numeric >= 50) return "ism-heat-cell-expansion";
    if (numeric >= 45) return "ism-heat-cell-soft";
    if (numeric >= 40) return "ism-heat-cell-weak";
    return "ism-heat-cell-contraction";
  }


export function renderIsmTrendChip(trend) {
    if (!trend) return "";
    const tone = trend.tone || "muted";
    const formatted = fmtIsmPointChange(trend.point_change);
    return `
      <span class="ism-trend-chip ism-trend-chip-${escapeHtml(tone)}">
        <strong>${escapeHtml(formatted)}</strong>
        <span>${escapeHtml(trend.direction)} / ${escapeHtml(trend.rate_of_change)} · ${escapeHtml(String(trend.trend_months))}m</span>
      </span>
    `;
  }


export function renderIsmMetricRow(label, value) {
    return `
      <div class="ism-metric-row">
        <span>${bilingualLabel(label)}</span>
        <strong>${escapeHtml(fmtIsmIndex(value))}</strong>
      </div>
    `;
  }


export function renderIsmIndustryBreadthSegment(segment) {
    if (!segment || segment.status !== "available") {
      return `
        <strong>\u2014</strong>
        <small>Pending<br><small>${escapeHtml(zhLabel("Pending") || "\u5F85\u5B8C\u6210")}</small></small>
      `;
    }
    return `
      <strong>${escapeHtml(fmtIsmBreadthCount(segment.growth_count))}/${escapeHtml(fmtIsmBreadthCount(segment.total_count))}</strong>
      <small>Growing<br><small>${escapeHtml(zhLabel("Growing") || "\u6269\u5F20\u884C\u4E1A")}</small></small>
    `;
  }


export const MEDALS = ["\uD83E\uDD47", "\uD83E\uDD48", "\uD83E\uDD49"];


export function renderIsmIndustryList(items, type, emptyLabel) {
    const rows = (items || []).map((item, i) => {
      const prefix = type === "growth" ? MEDALS[i] || "" : "\uD83D\uDD3B";
      const selected = state.selectedIsmIndustry === item.industry ? " ism-industry-button-selected" : "";
      return `
      <button type="button" class="ism-industry-list-button${selected}" data-ism-industry="${escapeHtml(item.industry)}">
        <span class="ism-industry-list-text">${prefix} ${escapeHtml(item.industry || "")}</span>
        <small class="ism-industry-zh">${escapeHtml(zhLabel(item.industry) || "")}</small>
      </button>
    `;
    }).join("");
    return rows || `<p class="ism-industry-empty">${escapeHtml(emptyLabel)}</p>`;
  }


export function renderIsmIndustryBreadthGroup(group) {
    const summary = group.industry_breadth;
    if (!summary) {
      const requiredInputs = (group.required_inputs || [])
        .map((input) => `<li>${escapeHtml(input)}</li>`)
        .join("");
      return `
        <section class="ism-detail-group ism-industry-ranking">
          <h4>${bilingualLabel(group.label || "Industry Breadth")}</h4>
          <div class="gdp-expectations-context">
            <strong>${bilingualLabel("Required Inputs")}</strong>
            <ul>${requiredInputs}</ul>
          </div>
        </section>
      `;
    }
    return `
      <section class="ism-detail-group ism-industry-ranking">
        <h4>${escapeHtml(group.label || "Industry Breadth")}</h4>
        <div class="ism-industry-counts">
          <span><strong>${escapeHtml(fmtIsmBreadthCount(summary.growth_count))}</strong> Growing</span>
          <span><strong>${escapeHtml(fmtIsmBreadthCount(summary.contraction_count))}</strong> Contracting</span>
          <span><strong>${escapeHtml(fmtIsmBreadthCount(summary.total_count))}</strong> Total</span>
        </div>
        <div class="ism-industry-columns">
          <div>
            <h5>${bilingualLabel("Growing Industries")}</h5>
            <div class="ism-industry-list">${renderIsmIndustryList(summary.top_growth, "growth", "No growth industries")}</div>
          </div>
          <div>
            <h5>${bilingualLabel("Contracting Industries")}</h5>
            <div class="ism-industry-list">${renderIsmIndustryList(summary.top_contraction, "contraction", "No contracting industries")}</div>
          </div>
        </div>
      </section>
    `;
  }


export function ismScoreLabelClass(label) {
    const classes = {
      strong: "ism-score-strong",
      improving: "ism-score-improving",
      mixed: "ism-score-mixed",
      weakening: "ism-score-weakening",
      weak: "ism-score-weak",
      unavailable: "ism-score-unavailable",
    };
    return classes[label] || "ism-score-unavailable";
  }


export function ismSignalBadgeClass(status) {
    const classes = {
      positive: "ism-signal-positive",
      negative: "ism-signal-negative",
      not_reported: "ism-signal-not-reported",
      unavailable: "ism-signal-unavailable",
    };
    return classes[status] || "ism-signal-unavailable";
  }


export function ismSignalRowClass(status) {
    const classes = {
      positive: "ism-signal-row-positive",
      negative: "ism-signal-row-negative",
      not_reported: "ism-signal-row-not-reported",
      unavailable: "ism-signal-row-unavailable",
    };
    return classes[status] || "ism-signal-row-unavailable";
  }


export function ismScoreLabelDisplay(label) {
    const labels = {
      strong: "Strong",
      improving: "Improving",
      mixed: "Mixed",
      weakening: "Weakening",
      weak: "Weak",
      unavailable: "Unavailable",
    };
    return labels[label] || "Unavailable";
  }


export function ismSignalLabel(status) {
    const labels = {
      positive: "Positive",
      negative: "Negative",
      not_reported: "Not listed",
      unavailable: "Unavailable",
    };
    return labels[status] || "Unavailable";
  }


export function ismOverallTrendLabel(point) {
    if (point.overall_status === "positive") return "Growth";
    if (point.overall_status === "negative") return "Contraction";
    if (point.overall_status === "not_reported") return "Not listed";
    return "Unavailable";
  }


export function ismRankedSignalLabel(signalKey, signal) {
    const status = signal && signal.status ? signal.status : "unavailable";
    const first = signal && signal.rank === 1;
    if (status === "positive" && signalKey === "backlog") return first ? "Largest backlog increase" : "Backlogs higher";
    if (status === "negative" && signalKey === "backlog") return first ? "Largest backlog decrease" : "Backlogs lower";
    if (status === "positive" && signalKey === "overall") return first ? "Strongest overall growth" : "Growth";
    if (status === "negative" && signalKey === "overall") return first ? "Strongest contraction" : "Contraction";
    if (status === "positive") return first ? "Strongest growth" : "Growth";
    if (status === "negative") return first ? "Strongest decline" : "Decline";
    return ismSignalLabel(status);
  }


export function ismRankedSignalDescription(signalKey, signal) {
    const rank = signal ? signal.rank : null;
    const listSize = signal ? signal.list_size : null;
    const status = signal && signal.status ? signal.status : "unavailable";
    if (rank == null || listSize == null) return "\u2014";
    if (signalKey === "backlog" && status === "positive") return `#${rank} of ${listSize} industries with higher backlogs`;
    if (signalKey === "backlog" && status === "negative") return `#${rank} of ${listSize} industries with lower backlogs`;
    if (status === "positive") return `#${rank} of ${listSize} growing industries`;
    if (status === "negative") return `#${rank} of ${listSize} declining industries`;
    return `#${rank} of ${listSize}`;
  }


export function ismCoreTrendLabel(signalKey, status) {
    if (signalKey === "backlog" && status === "positive") return "Higher";
    if (signalKey === "backlog" && status === "negative") return "Lower";
    if (status === "positive") return "Growth";
    if (status === "negative") return "Decline";
    return ismSignalLabel(status);
  }


export function renderIsmSignalBadge(signal, signalKey = "") {
    const status = signal && signal.status ? signal.status : "unavailable";
    return `<span class="ism-signal-badge ${escapeHtml(ismSignalBadgeClass(status))}">${escapeHtml(ismRankedSignalLabel(signalKey, signal))}</span>`;
  }


export function renderIsmRankText(listSize, rank) {
    if (rank != null && listSize != null) return `#${rank} of ${listSize}`;
    return "\u2014";
  }


export function renderIsmIndustryAnalysisSection(analysis, selectedIndustryData) {
    if (!analysis || analysis.status === "unavailable") {
      if (analysis && analysis.status === "unavailable") {
        return `
          <section class="ism-detail-group ism-industry-analysis">
            <p class="ism-industry-unavailable">${escapeHtml(analysis.reason || "Industry analysis unavailable")}</p>
          </section>
        `;
      }
      return "";
    }

    const industries = analysis.industries || [];
    const selectedIndustry = selectedIndustryData || industries[0];
    if (!selectedIndustry) return "";

    const coverageSummary = analysis.coverage_summary || {};
    const period = analysis.period || "";
    const formattedPeriod = fmtMonthYear(period);
    const sourceUrl = analysis.source_url || "";
    const scoreVersion = analysis.score_version || "";
    const macroContext = analysis.macro_context || {};

    const totalComponents = (coverageSummary.complete_components ?? 0) + (coverageSummary.unavailable_components ?? 0);
    const noneUnavailable = (coverageSummary.unavailable_components ?? 0) === 0;
    const coverageText = noneUnavailable
      ? `Data Coverage: Complete`
      : `Data Coverage: ${escapeHtml(String(coverageSummary.complete_components ?? 0))}/${escapeHtml(String(totalComponents))} components, ${escapeHtml(String(coverageSummary.unavailable_components ?? 0))} unavailable`;

    const selectorOptions = industries.map((ind) => {
      const score = ind.score != null ? ` (Score: ${ind.score.toFixed(1)})` : "";
      const selected = ind.industry === state.selectedIsmIndustry ? " selected" : "";
      return `<option value="${escapeHtml(ind.industry)}"${selected}>${escapeHtml(ind.industry + score)}</option>`;
    }).join("");

    const macroHtml = renderIsmMacroContext(macroContext);
    const detailHtml = renderIsmIndustryDetailView(selectedIndustry, analysis);

    return `
      <section class="ism-detail-group ism-industry-analysis">
        <p class="ism-industry-score-explanation">ISM signal configuration, not an investment recommendation. <small>${escapeHtml(scoreVersion)}</small></p>
        <div class="ism-industry-meta">
          <span>${bilingualLabel("Report")}: ${escapeHtml(formattedPeriod)}</span>
          <span>${coverageText}</span>
          ${sourceUrl ? `<span><a href="${escapeHtml(sourceUrl)}" target="_blank" rel="noopener noreferrer">${bilingualLabel("Source")}</a></span>` : ""}
        </div>
        ${macroHtml}
        <div class="ism-industry-selector-wrap">
          <label for="ism-industry-select">${bilingualLabel("Select Industry")}</label>
          <select id="ism-industry-select" class="ism-industry-select" data-ism-industry-select>${selectorOptions}</select>
        </div>
        ${detailHtml}
      </section>
    `;
  }


export function renderIsmIndustryDetailView(industryData, analysis) {
    const overallSignal = industryData.overall_signal || {};
    const coreSignals = industryData.core_signals || {};
    const comments = industryData.comments || [];
    const trend = industryData.trend || [];
    const summary = industryData.summary;

    const score = industryData.score;
    const scoreCoverage = industryData.score_coverage;
    const scoreLabel = industryData.score_label || "unavailable";
    const scoreDisplay = score != null ? score.toFixed(1) : "n/a";
    const coverageDisplay = scoreCoverage != null ? `${scoreCoverage.toFixed(1)}% ${bilingualLabel("coverage")}` : "";
    const labelClass = ismScoreLabelClass(scoreLabel);
    const labelDisplay = ismScoreLabelDisplay(scoreLabel);

    const weights = analysis.score_weights || {};
    const period = analysis.period || "";
    const sourceUrl = analysis.source_url || "";

    const signalConfig = [
      ["new_orders", "New Orders"],
      ["production", "Production"],
      ["backlog", "Backlog"],
    ];

    const signalRowsHtml = signalConfig.map(([key, label]) => {
      const sig = coreSignals[key] || {};
      return renderIsmCoreSignalRow(key, sig, label);
    }).join("");

    const overallRowClass = ismSignalRowClass(overallSignal.status);
    const overallBadge = renderIsmSignalBadge(overallSignal, "overall");
    const overallRankText = ismRankedSignalDescription("overall", overallSignal);
    const overallScore = overallSignal.component_score;
    const overallScoreText = overallScore != null ? overallScore.toFixed(1) : "\u2014";

    const summaryHtml = summary ? `<p class="ism-industry-summary">${escapeHtml(summary)}</p>` : "";

    return `
      <div class="ism-industry-detail" data-ism-industry-detail>
        <div class="ism-industry-header">
          <h5>${escapeHtml(industryData.industry)}</h5>
          <span class="ism-industry-period">${escapeHtml(fmtMonthYear(period))}</span>
        </div>
        ${summaryHtml}
        <div class="ism-industry-score-band">
          <div class="ism-industry-main-score">
            <span class="ism-score-value">${escapeHtml(scoreDisplay)}</span>
            <span class="ism-score-label ${escapeHtml(labelClass)}">${escapeHtml(labelDisplay)}</span>
          </div>
          <span class="ism-industry-score-coverage">${coverageDisplay}</span>
        </div>
        <div class="ism-industry-signals">
          ${signalRowsHtml}
          <div class="ism-industry-signal-row ism-industry-signal-row-overall ${escapeHtml(overallRowClass)}">
            <span class="ism-signal-name">Overall</span>
            ${overallBadge}
            <span class="ism-signal-rank">${escapeHtml(overallRankText)}</span>
            <span class="ism-signal-component-score">${escapeHtml(overallScoreText)}</span>
          </div>
        </div>
        ${renderIsmScoreComponentDetail(coreSignals, overallSignal, weights)}
        ${renderIsmEvidenceDetail(coreSignals)}
        <div class="ism-industry-comments">
          <h6>${bilingualLabel("Respondent Comments")}</h6>
          ${comments && comments.length ? comments.map((text) => `<p class="ism-industry-comment-text">${escapeHtml(text)}</p>`).join("") : `<p class="ism-industry-no-comment">${bilingualLabel("No respondent comment in this report")}</p>`}
        </div>
        ${renderIsmIndustryTrend(trend, industryData.trend_summary)}
        ${sourceUrl ? `<div class="ism-industry-source"><a href="${escapeHtml(sourceUrl)}" target="_blank" rel="noopener noreferrer">${bilingualLabel("Official ISM Report")} &rarr;</a></div>` : ""}
      </div>
    `;
  }


export function renderIsmCoreSignalRow(signalKey, signal, label) {
    const status = signal && signal.status ? signal.status : "unavailable";
    const rowClass = ismSignalRowClass(status);
    const badge = renderIsmSignalBadge(signal, signalKey);
    const rankText = ismRankedSignalDescription(signalKey, signal);
    const componentScore = signal ? signal.component_score : null;
    const scoreText = componentScore != null ? componentScore.toFixed(1) : "\u2014";
    return `
      <div class="ism-industry-signal-row ${escapeHtml(rowClass)}">
        <span class="ism-signal-name">${escapeHtml(label)}</span>
        ${badge}
        <span class="ism-signal-rank">${escapeHtml(rankText)}</span>
        <span class="ism-signal-component-score">${escapeHtml(scoreText)}</span>
      </div>
    `;
  }


export function renderIsmScoreComponentDetail(coreSignals, overallSignal, weights) {
    const entries = [
      ["new_orders", "New Orders", coreSignals.new_orders, weights.new_orders],
      ["production", "Production", coreSignals.production, weights.production],
      ["backlog", "Backlog", coreSignals.backlog, weights.backlog],
      ["overall", "Overall Rank", overallSignal, weights.overall],
    ];

    const rows = entries.map(([key, label, signal, weight]) => {
      const score = signal ? signal.component_score : null;
      const scoreText = score != null ? score.toFixed(1) : "\u2014";
      const weightPct = weight != null ? (weight * 100).toFixed(0) : "0";
      return `
        <div class="ism-component-row">
          <span class="ism-component-label">${escapeHtml(label)}</span>
          <div class="ism-component-bar-wrap"><span class="ism-component-bar" style="width: ${escapeHtml(weightPct)}%"></span></div>
          <span class="ism-component-pct">${escapeHtml(weightPct)}%</span>
          <span class="ism-component-score-val">${escapeHtml(scoreText)}</span>
        </div>
      `;
    }).join("");

    return `
      <details class="ism-industry-components">
        <summary>${bilingualLabel("Score Components")}</summary>
        <div class="ism-component-rows">${rows}</div>
      </details>
    `;
  }


export function renderIsmEvidenceDetail(coreSignals) {
    const signalConfig = [
      ["new_orders", "New Orders"],
      ["production", "Production"],
      ["backlog", "Backlog"],
    ];
    const rows = signalConfig.map(([key, label]) => {
      const sig = coreSignals[key] || {};
      const evidence = sig.evidence_text;
      if (!evidence) return "";
      return `
        <div class="ism-macro-row">
          <span>${escapeHtml(label)}</span>
          <span>${escapeHtml(evidence)}</span>
        </div>
      `;
    }).filter(Boolean).join("");
    if (!rows) return "";
    return `
      <details class="ism-industry-macro-context">
        <summary>${bilingualLabel("Source Evidence")}</summary>
        <div class="ism-macro-rows">${rows}</div>
      </details>
    `;
  }


export function renderIsmMacroContext(macroContext) {
    const keys = [
      ["new_orders", "New Orders"],
      ["production", "Production"],
      ["backlog", "Backlog"],
      ["inventories", "Inventories"],
      ["customer_inventories", "Customers' Inventories"],
    ];

    const rows = keys.map(([key, label]) => {
      const ctx = macroContext[key];
      if (!ctx) return "";
      const chip = ctx.tone && ctx.point_change != null ? renderIsmTrendChip({
        tone: ctx.tone,
        point_change: ctx.point_change,
        direction: ctx.direction || "",
        rate_of_change: ctx.rate_of_change || "",
        trend_months: ctx.trend_months || 0,
      }) : "";
      return `
        <div class="ism-demand-row">
          <span class="ism-demand-label">${escapeHtml(label)}</span>
          <div class="ism-demand-right">
            <strong class="ism-demand-value">${escapeHtml(fmtIsmIndex(ctx.value))}</strong>
            ${chip}
          </div>
        </div>
      `;
    }).filter(Boolean).join("");

    if (!rows) return "";

    return `
      <div class="ism-demand-wrap">
        <h6 class="ism-demand-heading">${bilingualLabel("Macro Demand Context")}</h6>
        <div class="ism-demand-rows">
          ${rows}
        </div>
      </div>
    `;
  }


export function renderIsmScoreTrendSvg(sorted) {
    const pointCount = sorted.length;
    const labelSkip = pointCount > 6 ? Math.ceil(pointCount / 6) : 1;
    const minWidth = Math.max(280, pointCount * 40);
    const width = Math.min(minWidth, 600);
    const height = 100;
    const padLeft = 28;
    const padRight = 8;
    const padTop = 6;
    const padBottom = 18;
    const plotW = width - padLeft - padRight;
    const plotH = height - padTop - padBottom;
    const yMin = 0;
    const yMax = 100;
    const neutralY = padTop + plotH * (1 - 50 / (yMax - yMin));

    const validPoints = sorted.map((p, i) => ({ ...p, index: i }));

    const yScale = (v) => padTop + plotH * (1 - (v - yMin) / (yMax - yMin));
    const xScale = (i) => padLeft + (validPoints.length > 1 ? (i / (validPoints.length - 1)) * plotW : plotW / 2);

    const segments = [];
    let currentSeg = [];
    for (const p of validPoints) {
      if (p.score != null) {
        currentSeg.push(p);
      } else {
        if (currentSeg.length > 1) segments.push(currentSeg);
        currentSeg = [];
      }
    }
    if (currentSeg.length > 1) segments.push(currentSeg);

    const lines = segments.map((seg) => {
      const points = seg.map((p) => `${xScale(p.index).toFixed(1)},${yScale(p.score).toFixed(1)}`);
      return `<polyline fill="none" stroke="#5D7FA8" stroke-width="1.5" points="${points.join(" ")}"/>`;
    }).join("");

    const lastIndex = validPoints.length - 1;
    const circles = validPoints.map((p) => {
      if (p.score == null) return "";
      const cx = xScale(p.index).toFixed(1);
      const cy = yScale(p.score).toFixed(1);
      const period = fmtMonthYear(p.period);
      const rank = p.overall_rank != null ? `${bilingualLabel("Rank")}: ${p.overall_rank}` : "";
      const dir = p.overall_direction || "";
      const cov = p.score_coverage != null ? `${bilingualLabel("Cov")}: ${p.score_coverage.toFixed(0)}%` : "";
      const noStatus = p.new_orders ? ismCoreTrendLabel("new_orders", p.new_orders.status) : "";
      const noRank = p.new_orders && p.new_orders.rank != null ? `#${p.new_orders.rank}` : "";
      const prodStatus = p.production ? ismCoreTrendLabel("production", p.production.status) : "";
      const prodRank = p.production && p.production.rank != null ? `#${p.production.rank}` : "";
      const blStatus = p.backlog ? ismCoreTrendLabel("backlog", p.backlog.status) : "";
      const blRank = p.backlog && p.backlog.rank != null ? `#${p.backlog.rank}` : "";
      const detail = `${bilingualLabel("Period")}: ${escapeHtml(period)}, ${bilingualLabel("Score")}: ${p.score.toFixed(1)}${cov ? `, ${cov}` : ""}${rank ? `, ${rank}` : ""}${dir ? `, ${escapeHtml(dir)}` : ""} | New Orders: ${escapeHtml(noStatus)}${noRank ? ` ${escapeHtml(noRank)}` : ""}; Production: ${escapeHtml(prodStatus)}${prodRank ? ` ${escapeHtml(prodRank)}` : ""}; Order Backlogs: ${escapeHtml(blStatus)}${blRank ? ` ${escapeHtml(blRank)}` : ""}`;
      return `<circle tabindex="0" cx="${cx}" cy="${cy}" r="3" fill="#5D7FA8" aria-label="${detail}"><title>${detail}</title></circle>`;
    }).join("");

    const xLabels = validPoints.map((p) => {
      if (p.index !== lastIndex && p.index % labelSkip !== 0) return "";
      const x = xScale(p.index).toFixed(1);
      return `<text x="${x}" y="${height - 2}" text-anchor="middle" font-size="7" fill="#8B7E74">${escapeHtml(fmtMonthYear(p.period))}</text>`;
    }).join("");

    return `
      <svg width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" style="display:block;" role="img" aria-label="${bilingualLabel("Score trend chart")}">
        <line x1="${padLeft}" y1="${neutralY.toFixed(1)}" x2="${width - padRight}" y2="${neutralY.toFixed(1)}" stroke="#E0D6C8" stroke-width="1" stroke-dasharray="3,2"/>
        <text x="${padLeft - 2}" y="${neutralY - 2}" text-anchor="end" font-size="6" fill="#A89B91">50</text>
        <text x="${padLeft - 2}" y="${padTop + 6}" text-anchor="end" font-size="6" fill="#A89B91">100</text>
        <text x="${padLeft - 2}" y="${height - padBottom + 2}" text-anchor="end" font-size="6" fill="#A89B91">0</text>
        ${lines}
        ${circles}
        ${xLabels}
      </svg>
    `;
  }


export function renderIsmIndustryTrend(trend, trendSummary) {
    const allNull = trend && trend.length && trend.every((p) => p.score == null);
    if (!trend || !trend.length || allNull) {
      return `
        <div class="ism-industry-trend">
          <h6>${bilingualLabel("Signal Trend")}</h6>
          <p class="ism-trend-empty">${bilingualLabel("Historical coverage unavailable")}</p>
        </div>
      `;
    }

    const sorted = [...trend].sort((a, b) => a.period.localeCompare(b.period));
    const svgChart = renderIsmScoreTrendSvg(sorted);

    const summary = trendSummary || {};
    const scoreChange = summary.latest_score_change;
    const streak = summary.positive_month_streak || 0;
    const broadStreak = summary.broad_confirmation_streak || 0;
    const confirmed = summary.latest_positive_confirmation_count || 0;
    const changeText = scoreChange != null
      ? `${bilingualLabel("Score change")}: ${escapeHtml(scoreChange >= 0 ? "+" : "")}${escapeHtml(scoreChange.toFixed(1))}`
      : "";

    let assessment = "No broad improvement is confirmed in the latest month.";
    if (confirmed === 3 && broadStreak >= 2) {
      assessment = `Broad and persistent improvement: New Orders, Production, and Order Backlogs have all been positive for ${broadStreak} consecutive months.`;
    } else if (confirmed === 3) {
      assessment = "Broad improvement: New Orders, Production, and Order Backlogs are all positive, but currently this is only a one-month signal.";
    } else if (confirmed === 2) {
      assessment = "Improvement is partially confirmed by 2 of 3 core signals: New Orders, Production, and Order Backlogs.";
    } else if (confirmed === 1) {
      assessment = "Improvement is narrow: only 1 of New Orders, Production, and Order Backlogs is positive.";
    }

    const trendMeta = [changeText, `${bilingualLabel("Overall growth streak")}: ${escapeHtml(String(streak))} ${bilingualLabel("mo")}`, `Positive core signals: ${escapeHtml(String(confirmed))}/3`].filter(Boolean).join(" &middot; ");

    const headers = [
      "Period",
      "Score",
      "Coverage",
      "Overall Industry",
      "New Orders",
      "Production",
      "Order Backlogs",
    ];

    const rows = sorted.map((point) => {
      const period = fmtMonthYear(point.period);
      const score = point.score != null ? point.score.toFixed(1) : "\u2014";
      const cov = point.score_coverage != null ? point.score_coverage.toFixed(0) : "\u2014";
      const overallStatus = point.overall_status || (
        point.overall_direction === "growth"
          ? "positive"
          : point.overall_direction === "contraction"
            ? "negative"
            : point.score != null
              ? "not_reported"
              : "unavailable"
      );
      const overallLabel = ismOverallTrendLabel({ ...point, overall_status: overallStatus });

      const noStatus = point.new_orders ? point.new_orders.status : null;
      const prodStatus = point.production ? point.production.status : null;
      const blStatus = point.backlog ? point.backlog.status : null;

      return `
        <tr>
          <td>${escapeHtml(period)}</td>
          <td>${escapeHtml(score)}</td>
          <td>${escapeHtml(cov)}</td>
          <td class="${escapeHtml(ismSignalBadgeClass(overallStatus))}">${escapeHtml(overallLabel)}</td>
          <td class="${escapeHtml(ismSignalBadgeClass(noStatus))}">${escapeHtml(ismCoreTrendLabel("new_orders", noStatus))}</td>
          <td class="${escapeHtml(ismSignalBadgeClass(prodStatus))}">${escapeHtml(ismCoreTrendLabel("production", prodStatus))}</td>
          <td class="${escapeHtml(ismSignalBadgeClass(blStatus))}">${escapeHtml(ismCoreTrendLabel("backlog", blStatus))}</td>
        </tr>
      `;
    }).join("");

    return `
      <div class="ism-industry-trend">
        <h6>${bilingualLabel("Signal Trend")}</h6>
        <p class="ism-trend-assessment">${escapeHtml(assessment)}</p>
        ${trendMeta ? `<p class="ism-trend-meta">${trendMeta}</p>` : ""}
        <div class="ism-score-trend-svg-wrap">${svgChart}</div>
        <div class="ism-trend-table-wrap">
          <table class="ism-trend-table">
            <thead><tr>${headers.map((h) => `<th>${h}</th>`).join("")}</tr></thead>
            <tbody>${rows}</tbody>
          </table>
        </div>
      </div>
    `;
  }


export function updateIsmIndustryDetail(body, industryName, analysis) {
    const detailContainer = body.querySelector("[data-ism-industry-detail]");
    if (!detailContainer) return;
    const industryData = analysis.industries.find((ind) => ind.industry === industryName);
    if (!industryData) return;
    state.selectedIsmIndustry = industryName;
    detailContainer.outerHTML = renderIsmIndustryDetailView(industryData, analysis);
    body.querySelectorAll("[data-ism-industry]").forEach((btn) => {
      btn.classList.toggle("ism-industry-button-selected", btn.dataset.ismIndustry === industryName);
    });
    if (body.querySelector("[data-ism-industry-select]")) {
      body.querySelector("[data-ism-industry-select]").value = industryName;
    }
  }


export function bindIsmIndustrySelector(body, analysis) {
    body._ismIndustryAnalysis = analysis;
    if (body.dataset.ismIndustryBound === "true") return;
    body.dataset.ismIndustryBound = "true";
    body.addEventListener("change", (event) => {
      const select = event.target.closest("[data-ism-industry-select]");
      if (select) updateIsmIndustryDetail(body, select.value, body._ismIndustryAnalysis);
    });
    body.addEventListener("click", (event) => {
      const button = event.target.closest("[data-ism-industry]");
      if (button) updateIsmIndustryDetail(body, button.dataset.ismIndustry, body._ismIndustryAnalysis);
    });
  }


export function renderIsmPolicyPressure(context) {
    if (!context) return "";
    return `
      <div class="ism-policy-pressure">
        <div class="ism-policy-pressure-head">
          <span>${bilingualTitle("Policy Pressure")}</span>
        </div>
        <div class="ism-policy-pressure-grid">
          <div class="m2-level-row"><span>${bilingualLabel("Combined Pressure")}</span><strong>${bilingualLabel(formatPressureValue(context.combined_pressure))}</strong></div>
          <div class="m2-level-row"><span>${bilingualLabel("Growth Pressure")}</span><strong>${bilingualLabel(formatPressureValue(context.growth_pressure))}</strong></div>
          <div class="m2-level-row"><span>${bilingualLabel("Inflation Pressure")}</span><strong>${bilingualLabel(formatPressureValue(context.inflation_pressure))}</strong></div>
          <div class="m2-level-row"><span>${bilingualLabel("Supply Pressure")}</span><strong>${bilingualLabel(formatPressureValue(context.supply_pressure))}</strong></div>
        </div>
      </div>
    `;
  }


export function renderIsmManufacturingCard(card) {
    const segments = card.segments || {};
    const bc = segments.business_cycle || {};
    const gd = segments.growth_drivers || {};
    const inf = segments.inflation_supply || {};
    const ib = segments.industry_breadth || {};
    const selected = state.selectedGrowthCycleDetailId === "ism_manufacturing";
    return `
      <button class="m2-card ism-card ism-card-button evidence-target ism-card-${escapeHtml(ismBadgeClass(card.status))}${selected ? " selected" : ""}" id="evidence-ism-manufacturing" type="button" data-growth-cycle-detail-id="ism_manufacturing">
        <div class="ism-metric-band">
          <div>
            <span>Business Cycle<br><small>${escapeHtml(zhLabel("Business Cycle") || "商业周期")}</small></span>
            <strong>${escapeHtml(fmtIsmIndex(bc.pmi))}</strong>
            <small>PMI<br><small>${escapeHtml(zhLabel("PMI") || "采购经理指数")}</small> · ${escapeHtml(bc.phase_label || "Missing")}</small>
            ${bc.trend ? renderIsmTrendChip(bc.trend) : ""}
          </div>
          <div>
            <span>Growth Drivers<br><small>${escapeHtml(zhLabel("Growth Drivers") || "增长驱动力")}</small></span>
            <strong>${escapeHtml(String(gd.above_50_count ?? 0))}/${escapeHtml(String(gd.available_count ?? 0))}</strong>
            <small>Above 50<br><small>${escapeHtml(zhLabel("Above 50") || "高于50")}</small></small>
          </div>
          <div>
            <span>Inflation & Supply<br><small>${escapeHtml(zhLabel("Inflation & Supply") || "通胀与供应")}</small></span>
            <strong>${escapeHtml(fmtIsmIndex(inf.prices))}</strong>
            <small>Prices<br><small>${escapeHtml(zhLabel("Prices") || "价格")}</small></small>
          </div>
          <div>
            <span>Industry Breadth<br><small>${escapeHtml(zhLabel("Industry Breadth") || "行业广度")}</small></span>
            ${renderIsmIndustryBreadthSegment(ib)}
          </div>
        </div>
        ${renderIsmPolicyPressure(card.policy_context)}
      </button>
    `;
  }


export function renderIsmIndustryBreadthCard(card) {
    const requiredInputs = (card.required_inputs || [])
      .map((input) => `<li>${escapeHtml(input)}</li>`)
      .join("");
    return `
      <article class="m2-card ism-card ism-card-missing">
        <div class="m2-card-head">
          <span>${escapeHtml(card.label || "ISM Industry Breadth")}<br><small>${escapeHtml(zhLabel(card.label) || "ISM行业广度")}</small></span>
          <strong class="inflation-status-badge">${escapeHtml(card.status_label || "Pending Inputs")}</strong>
        </div>
        <div class="gdp-expectations-context">
          <strong>${bilingualLabel("Required Inputs")}</strong>
          <ul>${requiredInputs}</ul>
        </div>
        <p class="m2-card-footnote">${escapeHtml(card.description || "")}</p>
      </article>
    `;
  }


export function renderInflationContextCard(card) {
    return `
      <div class="m2-card m2-card-${escapeHtml(card.status || "missing")}">
        <div class="m2-card-head">
          <span>${escapeHtml(card.label || "Inflation Context")}<br><small>${escapeHtml(zhLabel(card.label) || "通胀环境")}</small></span>
          <strong class="inflation-status-badge">${escapeHtml(card.status_label || "Missing")}</strong>
        </div>
        <div class="m2-metric-band">
          <div>
            <span>${bilingualLabel("Core PCE YoY")}</span>
            <strong>${escapeHtml(fmtDirectionalPct(card.core_pce_yoy))}</strong>
            <small>Core PCE year-over-year<br><span>核心PCE同比</span></small>
          </div>
          <div>
            <span>${bilingualLabel("Gap vs Fed 2% Target")}</span>
            <strong>${escapeHtml(fmtDirectionalPct(card.gap))}</strong>
            <small>Fed Target<span>美联储目标</span></small>
          </div>
          <div>
            <span>${bilingualLabel("Fed Target")}</span>
            <strong>${escapeHtml(fmtRate(card.target * 100))}</strong>
            <small>FOMC longer-run goal<br><span>FOMC长期目标</span></small>
          </div>
        </div>
        <p class="m2-card-footnote">${escapeHtml(card.description || "")}</p>
      </div>
    `;
  }


export function renderHousingPermitsCard(card) {
    if (window.housingPermitsUi && window.housingPermitsUi.renderCard) {
      return window.housingPermitsUi.renderCard(card, {
        escapeHtml: escapeHtml,
        bilingualLabel: bilingualLabel,
        bilingualTitle: bilingualTitle,
        titleCaseToken: titleCaseToken,
        fmtNumber: fmtNumber,
        fmtSignedPctDecimal: fmtSignedPctDecimal,
        fmtMonthYear: fmtMonthYear,
        statusClass: ismBadgeClass,
        isSelectedGrowthCycleDetailId: function (id) {
          return state.selectedGrowthCycleDetailId === id;
        },
      });
    }
    return "";
  }


export function renderCyclicalCommoditiesCard(card) {
    if (window.CyclicalCommoditiesUi && window.CyclicalCommoditiesUi.renderCard) {
      return window.CyclicalCommoditiesUi.renderCard(card, {
        escapeHtml: escapeHtml,
        bilingualLabel: bilingualLabel,
        bilingualTitle: bilingualTitle,
        titleCaseToken: titleCaseToken,
        fmtNumber: fmtNumber,
        fmtSignedPctDecimal: fmtSignedPctDecimal,
        fmtMonthYear: fmtMonthYear,
        statusClass: ismBadgeClass,
        isSelectedGrowthCycleDetailId: function (id) {
          return state.selectedGrowthCycleDetailId === id;
        },
      });
    }
    return "";
  }


export function renderNfibSboCard(card) {
    if (window.nfibSboUi && window.nfibSboUi.renderCard) {
      return window.nfibSboUi.renderCard(card, {
        escapeHtml: escapeHtml,
        bilingualLabel: bilingualLabel,
        bilingualTitle: bilingualTitle,
        titleCaseToken: titleCaseToken,
        fmtNumber: fmtNumber,
        fmtSignedPctDecimal: fmtSignedPctDecimal,
        fmtMonthYear: fmtMonthYear,
        statusClass: ismBadgeClass,
        isSelectedGrowthCycleDetailId: function (id) {
          return state.selectedGrowthCycleDetailId === id;
        },
      });
    }
    return "";
  }


export function renderFedBalanceSheetCard(card) {
    return `
      <div class="m2-card fed-balance-sheet-card">
        <div class="m2-card-head">
          <span>${escapeHtml(card.label || "Fed Balance Sheet")}<br><small>${escapeHtml(zhLabel(card.label) || "美联储资产负债表")}</small></span>
          <strong class="inflation-status-badge">${escapeHtml(card.status_label || "Liquidity Context")}</strong>
        </div>
        <div class="m2-metric-band">
          <div>
            <span>${bilingualLabel("Total Assets")}</span>
            <strong>${escapeHtml(fmtUsdMillions(card.total_assets))}</strong>
            <small>Fed H.4.1 total assets<br><span>美联储H.4.1总资产</span></small>
          </div>
          <div>
            <span>${bilingualLabel("YoY Growth")}</span>
            <strong>${escapeHtml(fmtDirectionalPct(card.total_assets_yoy))}</strong>
            <small>vs same week last year<br><span>较去年同期</span></small>
          </div>
          <div>
            <span>${bilingualLabel("Total Assets 13W Net Change")}</span>
            <strong>${escapeHtml(fmtSignedUsdMillions(card.total_assets_13w_change))}</strong>
            <small>Positive = expansion, negative = runoff<br><span>正值=扩表，负值=缩表</span></small>
          </div>
        </div>
        <div class="m2-level-row">
          <span>${bilingualLabel("Treasury 13W Net Change")}</span>
          <strong>${escapeHtml(fmtSignedUsdMillions(card.treasury_13w_change))}</strong>
        </div>
        <div class="m2-level-row">
          <span>${bilingualLabel("MBS 13W Net Change")}</span>
          <strong>${escapeHtml(fmtSignedUsdMillions(card.mbs_13w_change))}</strong>
        </div>
        <p class="m2-card-footnote">${escapeHtml(card.description || "")}</p>
      </div>
    `;
  }


export function renderGrowthCycleRangeControl() {
    return `
      <div class="chart-range-control chart-range-control-sticky" role="group" aria-label="Chart range">
        ${CHART_RANGE_OPTIONS.map((option) => `
          <button
            type="button"
            class="${option.id === state.selectedGrowthCycleChartRange ? "active" : ""}"
            data-growth-cycle-chart-range="${escapeHtml(option.id)}"
          >${escapeHtml(option.label)}</button>
        `).join("")}
      </div>
    `;
  }


export function bindGrowthCycleRangeControl(body) {
    body.querySelectorAll("[data-growth-cycle-chart-range]").forEach((button) => {
      button.addEventListener("click", () => {
        const range = button.dataset.growthCycleChartRange;
        if (!range || range === state.selectedGrowthCycleChartRange) return;
        state.selectedGrowthCycleChartRange = range;
        rerenderGrowthCycleDetailBodyPreservingScroll();
      });
    });
  }


export function renderFomcCalendarCard(card) {
    const meeting = card.next_meeting || {};
    const hasMeeting = meeting.start_date != null;
    if (!hasMeeting) {
      return `
        <article class="m2-card m2-card-missing fomc-card">
          <div class="m2-card-head">
            <span>${bilingualTitle("Next FOMC Meeting")}<br><small>${escapeHtml(zhLabel("Next FOMC Meeting") || "")}</small></span>
          </div>
          <p class="m2-card-context">${bilingualLabel("No scheduled meeting")}</p>
        </article>
      `;
    }
    const dateRange = meeting.end_date && meeting.end_date !== meeting.start_date
      ? `${meeting.start_date} - ${meeting.end_date}`
      : meeting.start_date;
    return `
      <article class="m2-card m2-card-mixed fomc-card fomc-calendar-card">
        <div class="m2-card-head">
          <div>
            <span>${bilingualTitle("Next FOMC Meeting")}</span>
          </div>
        </div>
        <div class="m2-level-row">
          <span>${bilingualTitle("Next Meeting Date")}<small>${escapeHtml(dateRange || "n/a")}</small></span>
          <strong>${meeting.has_sep ? "SEP" : "Regular"}</strong>
        </div>
      </article>
    `;
  }


export function renderFomcToneCard(card) {
    const tone = card.latest_tone || {};
    const hasTone = tone.marker_tone != null;
    const cardLabel = card.label || "FOMC Policy Read";
    if (!hasTone) {
      return `
        <article class="m2-card m2-card-missing fomc-card evidence-target" id="evidence-fomc-policy">
          <div class="m2-card-head">
            <span>${bilingualTitle(cardLabel)}</span>
          </div>
          <p class="m2-card-context">${bilingualLabel("Tone unavailable")}</p>
        </article>
      `;
    }
    const toneLabel = formatToneValue(tone.marker_tone);
    const toneBadge = toneBadgeClass(tone.marker_tone);
    const dateStr = tone.end_date && tone.end_date !== tone.start_date
      ? `${tone.start_date} \u2013 ${tone.end_date}`
      : tone.start_date;
    const minutesAvailable = tone.minutes_status === "available";
    const minutesRows = minutesAvailable
      ? `
          <div class="m2-level-row"><span>${bilingualLabel("Minutes Confirmation")}</span><strong>${bilingualLabel(formatMinutesConfirmation(tone.minutes_confirmation))}</strong></div>
          <div class="m2-level-row"><span>${bilingualLabel("Risk Focus")}</span><strong>${bilingualLabel(formatRiskFocus(tone.risk_focus))}</strong></div>
          <div class="m2-level-row"><span>${bilingualLabel("Policy Conviction")}</span><strong>${bilingualLabel(formatPolicyConviction(tone.policy_conviction))}</strong></div>`
      : `
          <div class="m2-level-row"><span>${bilingualLabel("Minutes Confirmation")}</span><strong>${bilingualLabel("Pending")}</strong></div>`;
    return `
      <article class="m2-card m2-card-context fomc-card fomc-tone-card evidence-target" id="evidence-fomc-policy">
        <div class="m2-card-head">
          <div>
            <span>${bilingualTitle(cardLabel)}</span>
            <small class="fomc-tone-date">${escapeHtml(dateStr || "")}</small>
          </div>
          <strong class="fomc-tone-badge ${escapeHtml(toneBadge)}">${bilingualLabel(toneLabel)}</strong>
        </div>
        <div class="m2-detail-rows">
          <div class="m2-level-row"><span>${bilingualLabel("Action")}</span><strong>${bilingualLabel(formatPolicyAction(tone.policy_action))}</strong></div>
          <div class="m2-level-row"><span>${bilingualLabel("Guidance")}</span><strong>${bilingualLabel(formatToneValue(tone.guidance_bias))}</strong></div>
          <div class="m2-level-row"><span>${bilingualLabel("Language")}</span><strong>${bilingualLabel(formatToneValue(tone.language_tone))}</strong></div>
          <div class="m2-level-row"><span>${bilingualLabel("Bias")}</span><strong>${bilingualLabel(formatOverallBias(tone.overall_bias))}</strong></div>
          <div class="m2-level-row"><span>${bilingualLabel("Change")}</span><strong>${bilingualLabel(formatToneChange(tone.tone_change))}</strong></div>
          ${minutesRows}
        </div>
      </article>
    `;
  }


export function renderCard(card) {
    if (card.id === "ism_manufacturing") return renderIsmManufacturingCard(card);
    if (card.id === "ism_services") return window.ismServicesUi.renderCard(card, { escapeHtml, formatIndex: fmtIsmIndex });
    if (card.id === "m2_money_supply") return renderM2MoneySupplyCard(card);
    if (card.id === "inflation_context") return renderInflationContextCard(card);
    if (card.id === "survey_synthesis") return renderSurveySynthesisCard(card);
    if (card.id === "fed_balance_sheet") return renderFedBalanceSheetCard(card);
    if (card.id === "housing_permits") return renderHousingPermitsCard(card);
    if (card.id === "nfib_sbo") return renderNfibSboCard(card);
    if (card.id === "cyclical_commodities") return renderCyclicalCommoditiesCard(card);
    return "";
  }


export function renderFomcCard(card) {
    if (card.id === "fomc_calendar") return renderFomcCalendarCard(card);
    if (card.id === "fomc_tone") return renderFomcToneCard(card);
    return "";
  }


export function renderM2MoneySupplyCard(card) {
    return `
      <button class="m2-card m2-card-button evidence-target m2-card-${escapeHtml(card.status || "missing")}${state.selectedGrowthCycleDetailId === card.id ? " selected" : ""}" id="evidence-m2-money-supply" type="button" data-growth-cycle-detail-id="${escapeHtml(card.id)}">
        <div class="m2-metric-band">
          <div>
            <span>${bilingualLabel("YoY Growth")}</span>
            <strong>${escapeHtml(fmtDirectionalPct(card.state?.m2_yoy_pct_change))}</strong>
            <small>YoY growth vs same month last year · ${escapeHtml(fmtPercentRank(card.state?.m2_yoy_percent_rank))} percentile of history<span>同比增速：较去年同月 · 历史第${escapeHtml(fmtPercentRank(card.state?.m2_yoy_percent_rank))}百分位</span></small>
          </div>
          <div>
            <span>${bilingualLabel("3M Change")}</span>
            <strong>${escapeHtml(fmtDirectionalPct(card.change?.m2_3m_momentum))}</strong>
            <small>latest level vs 3 months ago<span>最新水平较3个月前</span></small>
          </div>
          <div>
            <span>${bilingualLabel("MoM Shock")}</span>
            <strong>${escapeHtml(fmtDirectionalPercentRank(card.shock?.m2_mom_percent_rank, card.shock?.m2_mom_pct_change))} percentile</strong>
            <small>latest MoM growth ${escapeHtml(fmtSignedPctDecimal(card.shock?.m2_mom_pct_change))}<span>最新月环比增长 ${escapeHtml(fmtSignedPctDecimal(card.shock?.m2_mom_pct_change))}</span></small>
          </div>
        </div>
        <div class="m2-level-row">
          <span>${bilingualLabel("M2 Level")}</span>
          <strong>$${escapeHtml(fmtNumber(card.state?.m2_money_stock))}B</strong>
        </div>
      </button>
    `;
  }


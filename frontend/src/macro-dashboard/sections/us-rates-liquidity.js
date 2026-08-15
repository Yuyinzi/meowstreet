import { state } from "../state.js";
import {
  $, escapeHtml, fmtDate, fmtNumber, fmtRate, bilingualLabel, bilingualTitle,
  creditStatusMeta, creditDiagnosticInterpretation, formatPercentile, trendGlyph,
  accelerationGlyph, accelerationLabel, titleCaseToken, lineLabel, zhLabel,
  CREDIT_DETAIL_MAP, CREDIT_REGIME_VISIBLE_POINTS, fmtMonthYear, fmtStatus,
} from "../utils.js";
import { ratesDetailCacheKey, loadUsRatesLiquidityDetail, fetchUsRatesLiquidity } from "../api.js";
import { renderRelationshipLineChart, attachRelationshipChartTooltip, niceTicks } from "../charts.js";
import { renderOverview } from "./benchmark-grid.js";
import { renderDetailPanel } from "../detail-panel.js";

export async function loadUsRatesLiquidity() {
    await fetchUsRatesLiquidity();
    renderUsRatesLiquidity();
  }


export function renderUsRatesLiquidity() {
    const section = $("usRatesLiquidity");
    if (!section) return;
    const payload = state.usRatesLiquidity;
    if (state.usRatesLiquidityError) {
      section.querySelector(".rates-loading")?.remove();
      section.insertAdjacentHTML(
        "beforeend",
        `<div class="rates-empty">Unable to load US rates data: ${escapeHtml(state.usRatesLiquidityError)}</div>`,
      );
      return;
    }
    if (!payload) return;
    const headline = payload.headline || [];
    const creditIds = new Set([
      "bbb_credit_spread",
      "ccc_credit_spread",
      "ccc_bbb_quality_spread",
      "credit_conditions",
    ]);
    const rateCards = headline.filter((card) => !creditIds.has(card.id));
    const creditCards = headline.filter((card) => creditIds.has(card.id));
    const curveStatus = payload.derived?.curve_status || "missing";
    const interpretation = payload.derived?.method_interpretation || "";
    const creditStatus = payload.derived?.credit_conditions_status || "missing";
    section.innerHTML = `
      <div class="relationship-head">
        <div>
          <h2>US Rates & Credit</h2>
        </div>
      </div>
      <div class="rates-content">
        <div class="rates-content-head">
          <span class="mock-pill">${escapeHtml(payload.as_of ? `As of ${fmtDate(payload.as_of)}` : "Import needed")}</span>
        </div>
        ${rateCards.length ? `<div class="rates-signal-grid">${rateCards.map(renderRateCard).join("")}${renderSupportCard("Breakeven", fmtRate(payload.derived?.ten_year_breakeven_inflation))}${renderSupportCard("VIX", fmtNumber(payload.derived?.vix), "evidence-vix")}${renderCurveStatusCard(curveStatus, interpretation)}</div>` : ""}
        ${creditCards.length ? `
          <div class="rates-detail gdp-detail">
            <div class="rates-chart-subtitle">
              <div class="credit-conditions-head">
                <p class="eyebrow">${bilingualLabel("Credit Conditions")}</p>
                ${payload.credit_as_of ? `<span class="mock-pill">Data as of ${escapeHtml(payload.credit_as_of)}</span>` : ""}
              </div>
              <p>Credit spreads and quality spreads across rating tiers.<br><small>各评级层的信用利差和质量利差</small></p>
            </div>
            <div class="rates-signal-grid">${creditCards.map(renderRateCard).join("")}</div>
          </div>
        ` : ""}
      </div>
    `;
    section.querySelectorAll("[data-rates-detail-id]").forEach((button) => {
      button.addEventListener("click", () => {
        state.selectedRatesDetailId = state.selectedRatesDetailId === button.dataset.ratesDetailId
          ? null
          : button.dataset.ratesDetailId;
        state.selectedBenchmarkId = null;
        if (state.selectedRatesDetailId !== "yield_curve_shape") {
          state.selectedNominalCurrentDate = null;
          state.selectedNominalComparisonDate = null;
          state.selectedRealCurrentDate = null;
          state.selectedRealComparisonDate = null;
        }
        renderOverview();
        renderUsRatesLiquidity();
        renderDetailPanel();
      });
    });
  }


export function renderRatesDetailInPanel(body) {
    const detailId = state.selectedRatesDetailId;
    if (!detailId) return;

    if (detailId === "yield_curve_shape") {
      loadUsRatesLiquidityDetail(detailId)
        .then((payload) => {
          if (state.selectedRatesDetailId !== "yield_curve_shape") return;
        body.innerHTML = `
          <div class="relationship-chart-grid">
            ${payload.charts.map((chart, index) => renderRatesDetailChart(chart, index)).join("")}
          </div>
        `;
          bindRatesCurveControls(body, "yield_curve");
          attachRatesChartTooltips(body, payload.charts);
        })
        .catch((error) => {
          if (state.selectedRatesDetailId !== detailId) return;
          body.innerHTML = `<p class="status">Failed to load yield curve detail.</p>`;
          console.error(error);
        });
      return;
    }

    loadUsRatesLiquidityDetail(detailId)
      .then((payload) => {
        if (state.selectedRatesDetailId !== payload.detail_id) return;
        body.innerHTML = `
          <div class="relationship-chart-grid">
            ${payload.charts.map((chart, index) => renderRatesDetailChart(chart, index)).join("")}
          </div>
        `;
        bindRatesCurveControls(body, "card");
        attachRatesChartTooltips(body, payload.charts);
      })
      .catch((error) => {
        if (state.selectedRatesDetailId !== detailId) return;
        body.innerHTML = `<p class="status">Failed to load US rates detail.</p>`;
        console.error(error);
      });
  }


export function renderRateCard(card) {
    const detailId = card.id === "credit_conditions"
      ? "credit_conditions_diagnostics"
      : CREDIT_DETAIL_MAP[card.id] || card.id;
    const selected = state.selectedRatesDetailId === detailId ? " selected" : "";
    const targetId = card.id === "credit_conditions"
      ? "evidence-credit-conditions"
      : card.id === "tips_10y" ? "evidence-real-rate-risk" : "";
    if (card.id === "credit_conditions") {
      const currentValue = card.value || "missing";
      const meta = creditStatusMeta(currentValue);
      return `
        <button class="rates-signal-card rates-signal-card-wide${selected}${targetId ? " evidence-target" : ""}" type="button" data-rates-detail-id="${escapeHtml(detailId)}"${targetId ? ` id="${escapeHtml(targetId)}"` : ""}>
          <span>${bilingualLabel(card.label)}</span>
          <strong>${escapeHtml(meta.label)}<br><small>${escapeHtml(meta.zh)}</small></strong>
        </button>
      `;
    }
    return `
      <button class="rates-signal-card${selected}${targetId ? " evidence-target" : ""}" type="button" data-rates-detail-id="${escapeHtml(detailId)}"${targetId ? ` id="${escapeHtml(targetId)}"` : ""}>
        <span>${bilingualLabel(card.label)}</span>
        <strong>${escapeHtml(fmtRate(card.value))}</strong>
      </button>
    `;
  }


export function renderSupportCard(label, value, targetId = "") {
    return `
      <span class="rates-signal-card${targetId ? " evidence-target" : ""}"${targetId ? ` id="${escapeHtml(targetId)}"` : ""}>
        <span>${bilingualLabel(label)}</span>
        <strong>${escapeHtml(value)}</strong>
      </span>
    `;
  }


export function renderCurveStatusCard(curveStatus, interpretation) {
    const colorClass = `rates-signal-card-${curveStatus || "missing"}`;
    const label = (curveStatus || "missing").toUpperCase();
    return `
      <span class="rates-signal-card rates-signal-card-wide evidence-target ${colorClass}" id="evidence-yield-curve">
        <span>${bilingualLabel("Curve Status")}</span>
        <strong>${escapeHtml(fmtStatus(label))}</strong>
        <span class="rates-interpretation-text">${escapeHtml(interpretation || "")}</span>
      </span>
    `;
  }


export function renderRatesTimeSeriesChart(chart) {
    const valueFormatter = chart.unit === "raw" ? fmtNumber : fmtRate;
    return renderRelationshipLineChart(
      bilingualTitle(chart.title),
      chart.series || [],
      chart.keys || ["value"],
      chart.labels || { value: "Value" },
      {
        wide: true,
        rawTitle: true,
        valueFormatter,
        yDomain: chart.y_domain,
        events: chart.events || [],
        policyTrack: chart.title === "M2 YoY Growth vs Inflation Constraint",
      }
    );
  }


export function renderRatesCurveComparisonChart(chart, chartIndex) {
    const kind = chartIndex === 0 ? "nominal" : "real";
    const dates = chart.date_options || [];
    const dateControls = dates.length ? `
      <div class="rates-curve-date-controls">
        <label>BLUE LINE
          <select data-curve-date-kind="${kind}" data-curve-date-role="current">
            ${dates.map((date) => `
              <option value="${escapeHtml(date)}" ${date === chart.selected_current_date ? "selected" : ""}>${escapeHtml(date)}</option>
            `).join("")}
          </select>
        </label>
        <label>RED LINE
          <select data-curve-date-kind="${kind}" data-curve-date-role="comparison">
            ${dates.map((date) => `
              <option value="${escapeHtml(date)}" ${date === chart.selected_comparison_date ? "selected" : ""}>${escapeHtml(date)}</option>
            `).join("")}
          </select>
        </label>
      </div>
    ` : "";
    const series = chart.series || [];
    const keys = chart.keys || ["current", "comparison"];
    const labels = chart.labels || { current: "Latest", comparison: "Comparison" };
    return `<div class="rates-curve-combo relationship-chart-wide">
      ${dateControls}
      ${renderRelationshipLineChart(
        bilingualTitle(chart.title),
        series.map((point) => ({ date: point.label, ...point })),
        keys,
        labels,
        {
          wide: false,
          rawTitle: true,
          valueFormatter: fmtRate,
          yDomain: chart.y_domain,
          categoricalXAxis: true,
          showDots: true,
        }
      )}
    </div>`;
  }


export function renderRatesMultiSeriesChart(chart) {
    const primary = chart.series || [];
    const secondary = chart.secondary_series || [];
    const secondaryByDate = new Map(secondary.map((point) => [point.date, point.value]));
    const merged = primary
      .map((point) => ({
        date: point.date,
        real_rate: point.real_rate ?? point.value,
        secondary: secondaryByDate.get(point.date),
      }))
      .filter((point) => point.secondary !== undefined);
    return renderRelationshipLineChart(
      bilingualTitle(chart.title),
      merged,
      ["real_rate", "secondary"],
      {
        real_rate: chart.labels?.real_rate || "Real Rate",
        secondary: chart.labels?.vix || "Comparison",
      },
      { wide: true, rawTitle: true },
    );
  }


export function renderRatesDetailChart(chart, chartIndex) {
    if (chart.kind === "curve_comparison") {
      return renderRatesCurveComparisonChart(chart, chartIndex);
    }
    if (chart.kind === "multi_series") {
      return renderRatesMultiSeriesChart(chart);
    }
    if (chart.kind === "credit_diagnostics") {
      return renderCreditDiagnosticsChart(chart);
    }
    if (chart.kind === "credit_regime") {
      return renderCreditRegimeChart(chart);
    }
    return renderRatesTimeSeriesChart(chart);
  }


export function renderCreditDiagnosticMetric(title, metric = {}) {
    return `
      <div class="credit-diagnostic-metric">
        <h4>${bilingualLabel(title)}</h4>
        <strong>${escapeHtml(fmtRate(metric.value))}</strong>
        <dl>
          <div><dt>${bilingualLabel("Level Zone")}</dt><dd>${bilingualLabel(titleCaseToken(metric.zone))}</dd></div>
          <div><dt>${bilingualLabel("Full-History Percentile")}</dt><dd>${escapeHtml(formatPercentile(metric.percentile))}</dd></div>
          <div><dt>${bilingualLabel("1M Trend")}</dt><dd>${trendGlyph(metric.trend_1m)} ${bilingualLabel(titleCaseToken(metric.trend_1m))}</dd></div>
          <div><dt>${bilingualLabel("3M Trend")}</dt><dd>${trendGlyph(metric.trend_3m)} ${bilingualLabel(titleCaseToken(metric.trend_3m))}</dd></div>
          <div><dt>${bilingualLabel("Acceleration")}</dt><dd>${accelerationGlyph(metric.acceleration)} ${bilingualLabel(accelerationLabel(metric.acceleration))}</dd></div>
        </dl>
      </div>
    `;
  }


export function renderCreditAiInterpretation(ai) {
    if (!ai) return "";
    return `
      <div class="credit-ai-interpretation">
        <strong>CaiCai<small>财财解读</small></strong>
        <p>${escapeHtml(ai.text_en)}<small>${escapeHtml(ai.text_zh)}</small></p>
        <span>${escapeHtml(ai.as_of || "")} · ${escapeHtml(ai.prompt_version || "")} · ${escapeHtml(ai.model || "")}</span>
      </div>
    `;
  }


export function renderMacroAiInterpretation(ai) {
    if (!ai) return "";
    return `
      <div class="macro-ai-interpretation">
        <strong>CaiCai<small>财财解读</small></strong>
        <p>${escapeHtml(ai.text_en)}<small>${escapeHtml(ai.text_zh)}</small></p>
        <span>${escapeHtml(ai.as_of || "")} · ${escapeHtml(ai.prompt_version || "")} · ${escapeHtml(ai.model || "")}</span>
      </div>
    `;
  }


export function renderCreditCoverageNote(coverage) {
    if (!coverage) return "";
    const hasGap = coverage.has_gap && coverage.gap_start && coverage.gap_end;
    const gapText = hasGap
      ? `Data Gap: ${coverage.gap_start} - ${coverage.gap_end}`
      : "No detected data gap";
    const gapZh = hasGap
      ? `数据缺口：${coverage.gap_start} - ${coverage.gap_end}`
      : "未检测到数据缺口";
    const sourceNote = coverage.source_note || "P05 workbook history is merged with latest FRED ICE/BofA observations. Missing dates are shown as a data gap and are not interpolated.";
    return `
      <div class="credit-data-gap-note ${hasGap ? "has-gap" : ""}">
        <strong>${escapeHtml(gapText)}<small>${escapeHtml(gapZh)}</small></strong>
        <p>${escapeHtml(sourceNote)}<small>P05工作簿历史数据与最新FRED ICE/BofA观测值合并；缺失区间显示为数据缺口，不进行插值。</small></p>
      </div>
    `;
  }


export function renderCreditDiagnosticsChart(chart) {
    const metrics = chart.metrics || {};
    const status = chart.status || "missing";
    const meta = creditStatusMeta(status);
    const message = creditDiagnosticInterpretation(status);
    const rows = [
      ["bbb_credit_spread", "Overall Credit Risk"],
      ["ccc_credit_spread", "CCC Credit Spread"],
      ["ccc_bbb_quality_spread", "Quality Dispersion"],
    ];
    return `
      <div class="relationship-chart relationship-chart-wide credit-diagnostics-chart">
        <div class="credit-diagnostics-grid">
          ${rows.map(([key, title]) => renderCreditDiagnosticMetric(title, metrics[key])).join("")}
        </div>
        <div class="credit-interpretation-strip credit-interpretation-${escapeHtml(status.replaceAll("_", "-"))}">
          <strong>${escapeHtml(meta.label)}<small>${escapeHtml(meta.zh)}</small></strong>
          <p>${escapeHtml(message.text)}<small>${escapeHtml(message.zh)}</small></p>
        </div>
        ${renderCreditAiInterpretation(state.usRatesLiquidity?.credit_ai_interpretation)}
        ${renderCreditCoverageNote(state.usRatesLiquidity?.credit_coverage)}
      </div>
    `;
  }


export function renderCreditRegimeChart(chart) {
    const series = (chart.series || []).slice(-CREDIT_REGIME_VISIBLE_POINTS);
    const current = chart.current;
    const thresholds = chart.thresholds || {};
    const xThreshold = thresholds[chart.x_key] || 2.0;
    const yThreshold = thresholds[chart.y_key] || 4.0;

    const allX = series.map((p) => p[chart.x_key]);
    const allY = series.map((p) => p[chart.y_key]);
    const xMin = Math.min(0, ...allX);
    const xMax = Math.max(xThreshold * 1.5, ...allX) * 1.1;
    const yMin = Math.min(0, ...allY);
    const yMax = Math.max(yThreshold * 1.5, ...allY) * 1.1;

    const width = 480;
    const height = 360;
    const margin = { top: 30, right: 30, bottom: 50, left: 60 };
    const plotW = width - margin.left - margin.right;
    const plotH = height - margin.top - margin.bottom;

    function xScale(v) {
      return margin.left + ((v - xMin) / (xMax - xMin)) * plotW;
    }
    function yScale(v) {
      return margin.top + plotH - ((v - yMin) / (yMax - yMin)) * plotH;
    }

    const thresholdX = xScale(xThreshold);
    const thresholdY = yScale(yThreshold);

    const regimeLabels = {
      low_risk_low_dispersion: { label: "Benign Credit", detail: "Low Risk / Low Dispersion", x: margin.left + plotW * 0.25, y: margin.top + plotH * 0.75 },
      low_risk_high_dispersion: { label: "Weak Credit Warning", detail: "Low Risk / High Dispersion", x: margin.left + plotW * 0.25, y: margin.top + plotH * 0.25 },
      high_risk_high_dispersion: { label: "Risk Off", detail: "High Risk / High Dispersion", x: margin.left + plotW * 0.75, y: margin.top + plotH * 0.25 },
      high_risk_low_dispersion: { label: "Broad Stress", detail: "High Risk / Low Dispersion", x: margin.left + plotW * 0.75, y: margin.top + plotH * 0.75 },
    };

    const dots = series.map((p) => {
      const cx = xScale(p[chart.x_key]);
      const cy = yScale(p[chart.y_key]);
      const isCurrent = current && p.date === current.date;
      const r = isCurrent ? 6 : 3;
      const opacity = isCurrent ? 1 : 0.3;
      return `<circle cx="${cx}" cy="${cy}" r="${r}" fill="#3B3530" opacity="${opacity}" data-date="${escapeHtml(p.date)}" data-x="${p[chart.x_key]}" data-y="${p[chart.y_key]}" data-regime="${escapeHtml(p.regime || "")}"/>`;
    }).join("");

    const currentMarker = current ? `
      <circle cx="${xScale(current[chart.x_key])}" cy="${yScale(current[chart.y_key])}" r="8" fill="none" stroke="#E07B3F" stroke-width="2.5"/>
      <circle cx="${xScale(current[chart.x_key])}" cy="${yScale(current[chart.y_key])}" r="3" fill="#E07B3F"/>
    ` : "";

    const quadrantLabels = Object.values(regimeLabels).map((r) => {
      const labelZh = zhLabel(r.label);
      const detailZh = zhLabel(r.detail);
      return `
        <text x="${r.x}" y="${r.y - 11}" text-anchor="middle" fill="#8B7E74" font-size="12" font-weight="700">${escapeHtml(r.label)}</text>
        ${labelZh ? `<text x="${r.x}" y="${r.y + 4}" text-anchor="middle" fill="#8B7E74" font-size="11" font-weight="600">${escapeHtml(labelZh)}</text>` : ""}
        <text x="${r.x}" y="${r.y + 19}" text-anchor="middle" fill="#B0A597" font-size="10">${escapeHtml(detailZh || r.detail)}</text>
      `;
    }).join("");

    const xTicks = niceTicks(xMin, xMax, 5);
    const yTicks = niceTicks(yMin, yMax, 5);

    const xTickMarks = xTicks.map((v) => {
      const x = xScale(v);
      return `
        <line x1="${x}" y1="${margin.top + plotH}" x2="${x}" y2="${margin.top + plotH + 5}" stroke="#C8BFB6"/>
        <text x="${x}" y="${margin.top + plotH + 20}" text-anchor="middle" fill="#8B7E74" font-size="10">${fmtNumber(v)}</text>
      `;
    }).join("");

    const yTickMarks = yTicks.map((v) => {
      const y = yScale(v);
      return `
        <line x1="${margin.left - 5}" y1="${y}" x2="${margin.left}" y2="${y}" stroke="#C8BFB6"/>
        <text x="${margin.left - 10}" y="${y + 3}" text-anchor="end" fill="#8B7E74" font-size="10">${fmtNumber(v)}</text>
      `;
    }).join("");

    return `
      <div class="relationship-chart relationship-chart-wide relationship-chart-wrap credit-regime-chart" data-chart-kind="credit_regime">
        <div class="relationship-chart-head">
          <h3>${bilingualTitle(chart.title)}</h3>
          ${current ? `<span>${escapeHtml(current.date)} | ${escapeHtml(creditRegimeMeta(current.regime).label)}</span>` : ""}
        </div>
        <svg class="relationship-chart-svg" viewBox="0 0 ${width} ${height}" width="100%" preserveAspectRatio="xMidYMid meet">
          <rect x="${margin.left}" y="${margin.top}" width="${plotW}" height="${plotH}" fill="#FDFAF7" stroke="#E8E0D6"/>
          <line x1="${thresholdX}" y1="${margin.top}" x2="${thresholdX}" y2="${margin.top + plotH}" stroke="#E0BCBC" stroke-width="1" stroke-dasharray="4,3"/>
          <line x1="${margin.left}" y1="${thresholdY}" x2="${margin.left + plotW}" y2="${thresholdY}" stroke="#E0BCBC" stroke-width="1" stroke-dasharray="4,3"/>
          ${xTickMarks}
          ${yTickMarks}
          ${dots}
          ${currentMarker}
          ${quadrantLabels}
          <text x="${margin.left + plotW / 2}" y="${height - 5}" text-anchor="middle" fill="#8B7E74" font-size="11">${escapeHtml(lineLabel({ [chart.x_key]: chart.x_label }, chart.x_key))}</text>
          <text x="15" y="${margin.top + plotH / 2}" text-anchor="middle" fill="#8B7E74" font-size="11" transform="rotate(-90, 15, ${margin.top + plotH / 2})">${escapeHtml(lineLabel({ [chart.y_key]: chart.y_label }, chart.y_key))}</text>
        </svg>
        <div class="chart-tooltip" aria-hidden="true"></div>
      </div>
    `;
  }


export function attachCreditRegimeChartTooltip(svg, tooltip, chart) {
    const series = (chart.series || []).slice(-CREDIT_REGIME_VISIBLE_POINTS);
    if (!svg || !tooltip || !series.length) return;
    const wrap = svg.parentElement;
    const thresholds = chart.thresholds || {};
    const xThreshold = thresholds[chart.x_key] || 2.0;
    const yThreshold = thresholds[chart.y_key] || 4.0;
    const allX = series.map((p) => p[chart.x_key]);
    const allY = series.map((p) => p[chart.y_key]);
    const xMin = Math.min(0, ...allX);
    const xMax = Math.max(xThreshold * 1.5, ...allX) * 1.1;
    const yMin = Math.min(0, ...allY);
    const yMax = Math.max(yThreshold * 1.5, ...allY) * 1.1;
    const width = 480;
    const height = 360;
    const margin = { top: 30, right: 30, bottom: 50, left: 60 };
    const plotW = width - margin.left - margin.right;
    const plotH = height - margin.top - margin.bottom;
    let lastIndex = -1;
    let tooltipRect = null;

    function xScale(v) {
      return margin.left + ((v - xMin) / (xMax - xMin)) * plotW;
    }

    function yScale(v) {
      return margin.top + plotH - ((v - yMin) / (yMax - yMin)) * plotH;
    }

    function show(index, clientX, clientY) {
      const point = series[index];
      if (index !== lastIndex) {
        const meta = creditRegimeMeta(point.regime);
        tooltip.innerHTML = `
          <div><strong>${escapeHtml(fmtMonthYear(point.date))}</strong></div>
          <div class="chart-tooltip-row"><span>${bilingualLabel("Overall Credit Risk")}</span><strong>${escapeHtml(fmtRate(point[chart.x_key]))}</strong></div>
          <div class="chart-tooltip-row"><span>${bilingualLabel("Quality Dispersion")}</span><strong>${escapeHtml(fmtRate(point[chart.y_key]))}</strong></div>
          <div class="chart-tooltip-row"><span>${bilingualLabel("Credit Conditions")}</span><strong>${escapeHtml(meta.label)}</strong></div>
          <div class="credit-tooltip-zh">${escapeHtml(meta.zh)} · ${escapeHtml(meta.note)}</div>
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
      const scaleX = width / rect.width;
      const scaleY = height / rect.height;
      const mouseX = (event.clientX - rect.left) * scaleX;
      const mouseY = (event.clientY - rect.top) * scaleY;
      let nearestIndex = 0;
      let nearestDistance = Infinity;
      series.forEach((point, index) => {
        const dx = xScale(point[chart.x_key]) - mouseX;
        const dy = yScale(point[chart.y_key]) - mouseY;
        const distance = dx * dx + dy * dy;
        if (distance < nearestDistance) {
          nearestDistance = distance;
          nearestIndex = index;
        }
      });
      show(nearestIndex, event.clientX, event.clientY);
    });

    svg.addEventListener("mouseleave", hide);
  }


export function bindRatesCurveControls(detail, context) {
    detail.querySelectorAll("[data-curve-date-kind]").forEach((select) => {
      select.addEventListener("change", (event) => {
        event.preventDefault();
        const kind = select.dataset.curveDateKind;
        const role = select.dataset.curveDateRole;
        const date = select.value;
        if (kind === "nominal") {
          if (role === "current") state.selectedNominalCurrentDate = date;
          else state.selectedNominalComparisonDate = date;
        } else {
          if (role === "current") state.selectedRealCurrentDate = date;
          else state.selectedRealComparisonDate = date;
        }
        Object.keys(state.usRatesDetailsById).forEach((key) => {
          if (key.startsWith("yield_curve_shape")) {
            delete state.usRatesDetailsById[key];
          }
        });
        const detailId = context === "yield_curve" ? "yield_curve_shape" : state.selectedRatesDetailId;
        loadUsRatesLiquidityDetail(detailId)
          .then((payload) => {
            renderRatesDetailPayload(detail, payload, context);
          })
          .catch((error) => {
            console.error(error);
          });
      });
    });
  }




export function attachRatesChartTooltips(detail, chartsPayload) {
    const charts = detail.querySelectorAll(".relationship-chart-wrap");
    charts.forEach((wrap, index) => {
      const chart = chartsPayload[index];
      if (!chart) return;
      if (chart.kind === "credit_regime") {
        attachCreditRegimeChartTooltip(
          wrap.querySelector(".relationship-chart-svg"),
          wrap.querySelector(".chart-tooltip"),
          chart,
        );
        return;
      }
      const valueFormatter = chart.unit === "raw" ? fmtNumber : fmtRate;
      attachRelationshipChartTooltip(
        wrap.querySelector(".relationship-chart-svg"),
        wrap.querySelector(".chart-tooltip"),
        chart.kind === "curve_comparison"
          ? (chart.series || []).map((point) => ({ date: point.label, ...point }))
          : chart.series || [],
        chart.keys || ["value"],
        chart.labels || { value: "Value" },
        { valueFormatter, tooltipExtra: chart.tooltip_extra, events: chart.events || [] }
      );
    });
  }


export function renderRatesDetailPayload(detail, payload, context) {
    const heading = context === "yield_curve" ? `
      <div class="rates-chart-subtitle">
        <p class="eyebrow">${bilingualLabel("Yield Curve Analysis")}</p>
        <p>Compare yield curve shape across selected dates for nominal Treasuries and real TIPS rates.</p>
      </div>
    ` : `
      <div class="detail-head">
        <div>
          <h2>${escapeHtml(payload.title)}</h2>
        </div>
      </div>
    `;
    detail.innerHTML = `
      ${heading}
      <div class="relationship-chart-grid">
        ${payload.charts.map((chart, index) => renderRatesDetailChart(chart, index)).join("")}
      </div>
    `;
    bindRatesCurveControls(detail, context);
    attachRatesChartTooltips(detail, payload.charts);
  }


import { state } from "../state.js";
import { $, escapeHtml, bilingualLabel, titleCaseToken, zhLabel } from "../utils.js";

export function surveySynthesisHeadline() {
    return ((state.growthCycle || {}).headline || [])
      .find((card) => card.id === "survey_synthesis") || null;
  }


export function renderSurveySynthesis() {
    const section = $("surveySynthesis");
    if (!section) return;
    const head = section.querySelector(".relationship-head");
    if (state.growthCycleError) {
      section.innerHTML = `${head.outerHTML}<p class="growth-empty">Failed to load survey synthesis.</p>`;
      return;
    }
    if (!state.growthCycle) {
      section.innerHTML = `${head.outerHTML}<div class="survey-synthesis-loading">Loading survey synthesis…</div>`;
      return;
    }
    const card = surveySynthesisHeadline();
    section.innerHTML = `${head.outerHTML}${
      card
        ? `<div class="survey-synthesis-layer-body">${renderSurveySynthesisCard(card)}</div>`
        : '<p class="growth-empty">Survey synthesis data is not available.</p>'
    }`;
  }


export function renderSurveySynthesisCard(card) {
    const crossEvidence = _crossSectorEvidenceHtml(card);
    const rows = [
      { question: "ISM Growth Direction", answer: _economicDirectionLabel(card.economic_direction) },
      { question: "Manufacturing & Services PMI Trend", answer: _headlinePmiTrendLabel(card.growth_momentum) },
      { question: "New Orders Signal", answer: _newOrdersSignalLabel(card) },
      { question: "Leading Indicator Comparison", answer: _crossSectorLeadLabel(card), evidenceHtml: crossEvidence },
      { question: "ISM-implied GDP Growth", answer: _gdpGrowthLabel(card.expected_gdp_direction) },
      { question: "ISM Portfolio Contribution", answer: _portfolioContributionLabel(card.survey_portfolio_implication) },
      { question: "Observation Status", answer: _observationStatusLabel(card.bias_confirmation) },
      { question: "Services Backlog Signal", answer: _backlogConfirmationLabel(card.backlog_confirmation) },
    ];

    const rowsHtml = rows.map((row) => `
      <div class="survey-synthesis-row">
        <span class="survey-synthesis-question">${bilingualLabel(row.question)}</span>
        <strong class="survey-synthesis-answer">${bilingualLabel(row.answer)}${row.evidenceHtml || ""}</strong>
      </div>
    `).join("");

    const evidenceHtml = (card.reasons || []).length
      ? `<div class="survey-synthesis-evidence"><strong>${bilingualLabel("Evidence")}</strong><ul>${(card.reasons || []).map((r) => `<li>${escapeHtml(r)}</li>`).join("")}</ul></div>`
      : "";

    const conflictsHtml = (card.conflicts || []).length
      ? `<div class="survey-synthesis-conflicts"><strong>${bilingualLabel("Conflicts")}</strong><ul>${(card.conflicts || []).map((c) => `<li>${escapeHtml(c)}</li>`).join("")}</ul></div>`
      : "";

    const biasExplanations = {
      long: "ISM signals support a more constructive risk-asset posture, while Market Setup determines the final portfolio posture.",
      long_awaiting: "Expansion remains intact; weaker one-period momentum is caution, not a confirmed reversal. Market Setup determines the final portfolio posture.",
      neutral: "ISM signals alone do not support materially increasing risk exposure or shifting to a short posture.",
      short_or_neutral: "ISM signals support a neutral or more defensive posture, while Market Setup determines the final portfolio posture.",
      short_or_neutral_awaiting: "Contraction remains intact; one-period improvement awaits confirmation. Market Setup determines the final portfolio posture.",
    };
    const biasKey = card.bias_confirmation === "awaiting_confirmation"
      ? card.survey_portfolio_implication + "_awaiting"
      : card.survey_portfolio_implication;
    const biasExplanation = biasExplanations[biasKey]
      || "Manufacturing and Services data are insufficient to form an ISM portfolio bias.";
    const biasExplanationHtml = `
      <div class="survey-portfolio-bias-explanation">
        ${bilingualLabel(biasExplanation)}
      </div>
    `;

    return `
      <div class="survey-synthesis-card">
        <div class="survey-synthesis-grid">
          ${rowsHtml}
        </div>
        ${biasExplanationHtml}
        ${evidenceHtml}
        ${conflictsHtml}
      </div>
    `;
  }


export function _crossSectorLeadLabel(card) {
    const comparison = card.cross_sector_comparison;
    if (!comparison) return "Unavailable";
    if (comparison === "aligned") {
      const mfg = (card.components || {}).manufacturing || {};
      const svc = (card.components || {}).services || {};
      if (mfg.demand_momentum === svc.activity_momentum) {
        if (mfg.demand_momentum === "falling") return "Slowing Together";
        if (mfg.demand_momentum === "rising") return "Improving Together";
        if (mfg.demand_momentum === "flat") return "Stable Together";
      }
      return "Aligned";
    }
    if (comparison === "services_stronger") return "Services Leading";
    if (comparison === "manufacturing_stronger") return "Manufacturing Leading";
    if (comparison === "unresolved") return "Unresolved";
    return titleCaseToken(comparison);
  }


export function _economicDirectionLabel(direction) {
    if (!direction) return "Unavailable";
    if (direction === "aligned_expansion") return "Both Expanding";
    if (direction === "aligned_contraction") return "Both Contracting";
    if (direction === "aligned_neutral") return "Both Neutral";
    if (direction === "divergent") return "Diverging";
    return titleCaseToken(direction);
  }


export function _headlinePmiTrendLabel(momentum) {
    if (!momentum) return "Unavailable";
    if (momentum === "falling") return "Both Lower Than Last Month";
    if (momentum === "rising") return "Both Higher Than Last Month";
    if (momentum === "flat") return "Both Unchanged From Last Month";
    if (momentum === "mixed") return "Mixed";
    return titleCaseToken(momentum);
  }


export function _newOrdersSignalLabel(card) {
    const mfg = (card.components || {}).manufacturing || {};
    const svc = (card.components || {}).services || {};
    if (!mfg.demand_level || !svc.demand_level) return "Unavailable";
    if (mfg.demand_level !== svc.demand_level) return "Diverging";
    if (mfg.demand_momentum !== svc.demand_momentum) return "Mixed New Orders";
    if (mfg.demand_level === "expanding") {
      if (mfg.demand_momentum === "falling") return "Expanding but Slowing";
      if (mfg.demand_momentum === "rising") return "Expanding and Improving";
      if (mfg.demand_momentum === "flat") return "Expanding and Stable";
    }
    if (mfg.demand_level === "contracting") {
      if (mfg.demand_momentum === "falling") return "Contraction Deepening";
      if (mfg.demand_momentum === "rising") return "Contraction Easing";
      if (mfg.demand_momentum === "flat") return "Contracting and Stable";
    }
    return titleCaseToken(card.demand_alignment || "unavailable");
  }


export function _gdpGrowthLabel(direction) {
    if (!direction) return "Unavailable";
    if (direction === "rising") return "Growth Accelerating";
    if (direction === "slowing") return "Growth Slowing";
    if (direction === "falling") return "Growth Contracting";
    if (direction === "improving") return "Growth Improving";
    if (direction === "stable") return "Stable";
    if (direction === "mixed") return "Mixed";
    return titleCaseToken(direction);
  }


export function _portfolioContributionLabel(implication) {
    if (!implication) return "Unavailable";
    if (implication === "long") return "Supports Long Bias";
    if (implication === "short_or_neutral") {
      return "Supports Neutral or Defensive Bias";
    }
    if (implication === "neutral") return "Neutral";
    return titleCaseToken(implication);
  }


export function _observationStatusLabel(confirmation) {
    if (!confirmation) return "Unavailable";
    if (confirmation === "awaiting_confirmation") return "Continue Observing";
    if (confirmation === "not_required") {
      return "No Additional Observation Flag";
    }
    return titleCaseToken(confirmation);
  }


export function _backlogConfirmationLabel(backlog) {
    if (!backlog || backlog === "unavailable") return "Unavailable";
    if (backlog === "supports_growth") return "Supports Continued Growth";
    if (backlog === "supports_contraction") return "Supports Weaker Demand";
    if (backlog === "neutral") return "Neutral";
    return titleCaseToken(backlog);
  }


export function _crossSectorEvidenceHtml(card) {
    const mfg = (card.components || {}).manufacturing || {};
    const svc = (card.components || {}).services || {};
    const mfgLevel = mfg.demand_level;
    const svcLevel = svc.activity_level;
    if (!mfgLevel || !svcLevel) return "";
    const mfgMomentum = titleCaseToken(mfg.demand_momentum || "unavailable");
    const svcMomentum = titleCaseToken(svc.activity_momentum || "unavailable");
    const mfgLevelLabel = titleCaseToken(mfgLevel);
    const svcLevelLabel = titleCaseToken(svcLevel);
    const mfgLabel = "Manufacturing New Orders: " + mfgLevelLabel + " \u00B7 " + mfgMomentum;
    const svcLabel = "Services Business Activity: " + svcLevelLabel + " \u00B7 " + svcMomentum;
    const mfgZh = "制造业新订单：" + (zhLabel(mfgLevelLabel) || mfgLevelLabel) + " \u00B7 " + (zhLabel(mfgMomentum) || mfgMomentum);
    const svcZh = "服务业商业活动：" + (zhLabel(svcLevelLabel) || svcLevelLabel) + " \u00B7 " + (zhLabel(svcMomentum) || svcMomentum);
    return '<span class="survey-synthesis-evidence-line">'
      + escapeHtml(mfgLabel) + '<small>' + escapeHtml(mfgZh) + '</small>'
      + escapeHtml(svcLabel) + '<small>' + escapeHtml(svcZh) + '</small>'
      + '</span>';
  }


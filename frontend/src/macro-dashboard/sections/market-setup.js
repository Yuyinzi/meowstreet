import { state } from "../state.js";
import { $, escapeHtml, titleCaseToken } from "../utils.js";
import { fetchMarketSetup } from "../api.js";

export async function loadMarketSetup() {
    state.marketSetupLoading = true;
    state.marketSetupError = null;
    renderMarketSetup();
    announceStatus("Loading market setup");
    await fetchMarketSetup();
    state.marketSetupLoading = false;
    renderMarketSetup();
  }


export var MARKET_SETUP_SENTIMENT_CLASSES = {
    bull_market: "constructive",
    growth_and_conditions_aligned: "constructive",
    long: "constructive",
    neutral_to_long: "constructive",
    aligned: "constructive",
    expansion_rising: "constructive",
    confirms_expansion: "constructive",
    support_confirmed: "constructive",
    support_possible: "constructive",
    rising: "constructive",
    bear_market: "defensive",
    contraction_risk_aligned: "defensive",
    short: "defensive",
    short_or_neutral: "defensive",
    contraction_deepening: "defensive",
    confirms_contraction_risk: "defensive",
    confirms_downside_risk: "defensive",
    restrictive_confirmed: "defensive",
    falling: "defensive",
    reject: "defensive",
    transition: "caution",
    weak_growth_with_policy_support: "caution",
    growth_liquidity_conflict: "caution",
    unresolved_macro_conflict: "caution",
    insufficient_data: "caution",
    neutral: "caution",
    cautious: "caution",
    conflicting: "caution",
    conflict: "caution",
    incomplete: "caution",
    mixed: "caution",
    expansion_slowing: "caution",
    peaking: "caution",
    contraction_improving: "caution",
    troughing: "caution",
    stable: "caution",
    unresolved: "caution",
    transition_warning: "caution",
    support_constrained: "caution",
    policy_liquidity_conflict: "caution",
    no_clear_response: "caution",
    unavailable: "caution",
    wait_for_timing: "caution",
    growth_decelerating: "caution",
    partially_confirming: "caution",
    mild_risk_off: "caution",
    slowing: "caution",
    risk_rising: "defensive",
    conflicts: "defensive",
    supports: "constructive",
    expanding: "constructive",
  };


export function stateSentimentClass(value) {
    if (!value) return "neutral-state";
    return MARKET_SETUP_SENTIMENT_CLASSES[String(value).toLowerCase()] || "neutral-state";
  }


export function buildMarketSetupPresentation(setup) {
    if (!setup) return null;
    return {
      version: setup.version || null,
      generatedAt: setup.generated_at || null,
      evidenceThrough: setup.evidence_through || null,
      macroRegime: setup.macro_regime || {},
      marketConfirmation: setup.market_confirmation || {},
      marketSetup: setup.market_setup || {},
      portfolioPosture: setup.portfolio_posture || {},
      interpretation: setup.interpretation || "",
      supports: setup.supports || [],
      conflicts: setup.conflicts || [],
      offsets: setup.offsets || [],
      excludedInputs: setup.excluded_inputs || [],
      methodVersions: setup.method_versions || {},
      missingInputs: setup.missing_inputs || [],
      nextTriggers: setup.next_triggers || [],
      watchItems: setup.watch_items || [],
      evidenceLayers: setup.evidence_layers || null,
    };
  }


export function renderStateCell(label, value, sentimentClass) {
    var escapedLabel = escapeHtml(label);
    var readableValue = value ? titleCaseToken(value) : "\u2014";
    return '<div class="ms-state-cell">' +
      '<span class="ms-state-label">' + escapedLabel + '</span>' +
      '<span class="ms-state-value ' + sentimentClass + '">' + escapeHtml(readableValue) + '</span>' +
      '</div>';
  }


export function renderLayerCard(label, value, detail) {
    var escapedLabel = escapeHtml(label);
    var escapedValue = value ? escapeHtml(value) : "\u2014";
    var html = '<div class="ms-layer-card">';
    html += '<span class="ms-layer-label">' + escapedLabel + '</span>';
    html += '<span class="ms-layer-value">' + escapedValue + '</span>';
    if (detail) {
      html += '<span class="ms-layer-detail">' + escapeHtml(detail) + '</span>';
    }
    html += '</div>';
    return html;
  }


export function renderDecisionHero(pr) {
    if (!pr) return "";
    var html = '<div class="ms-hero">';
    html += '<div class="ms-hero-head">';
    html += '<h2 class="ms-hero-conclusion">Market Setup</h2>';
    if (pr.evidenceThrough) {
      html += '<span class="ms-hero-date" title="Individual source periods vary and may be more recent">' +
        'Oldest required evidence date: ' + escapeHtml(pr.evidenceThrough) + '</span>';
    }
    html += '</div>';
    html += '<div class="ms-layer-strip">';
    html += renderLayerCard("MACRO REGIME", pr.macroRegime.label, null);
    html += renderLayerCard("MARKET CONFIRMATION", pr.marketConfirmation.label, null);
    html += renderLayerCard("MARKET SETUP", pr.marketSetup.label, null);
    html += renderLayerCard("PORTFOLIO POSTURE", pr.portfolioPosture.label, null);
    html += '</div>';
    if (pr.interpretation) {
      html += '<p class="ms-hero-summary">' + escapeHtml(pr.interpretation) + '</p>';
    }
    if (pr.missingInputs.length) {
      html += '<div class="ms-hero-missing">';
      html += '<strong>Required Inputs</strong>';
      html += '<p>' + escapeHtml(pr.missingInputs.join(" \u00B7 ")) + '</p>';
      html += '</div>';
    }
    html += '</div>';
    return html;
  }


export const EVIDENCE_TARGET_IDS = Object.freeze({
    market_phase: "evidence-market-phase",
    ism_manufacturing: "evidence-ism-manufacturing",
    ism_services: "evidence-ism-services",
    yield_curve: "evidence-yield-curve",
    credit_conditions: "evidence-credit-conditions",
    real_rate_risk: "evidence-real-rate-risk",
    vix: "evidence-vix",
    fomc_policy: "evidence-fomc-policy",
    m2_money_supply: "evidence-m2-money-supply",
    consumer_sentiment: "consumerSentiment",
    housing_permits: "evidence-housing-permits",
    nfib_sbo: "evidence-nfib-sbo",
  });


export function evidenceTargetId(link) {
    return EVIDENCE_TARGET_IDS[link] || null;
  }


export function renderEvidenceLink(link) {
    var targetId = evidenceTargetId(link);
    if (!targetId) return "";
    return '<a class="ms-evidence-link" href="#' + escapeHtml(targetId) +
      '" data-evidence-target="' + escapeHtml(targetId) + '">' +
      escapeHtml(titleCaseToken(link)) + '</a>';
  }


export function renderDetailedReasoning(pr) {
    if (!pr) return "";
    var html = '<div class="ms-detailed">';
    var macroEvidence = pr.supports.concat(pr.conflicts);
    if (macroEvidence.length) {
      html += '<div class="ms-detailed-section">';
      html += '<h3>Macro Evidence</h3>';
      macroEvidence.forEach(function(entry) {
        html += '<div class="ms-evidence-item">' + escapeHtml(entry.finding || entry.source_id || "");
        var links = entry.evidence_links || [];
        if (links.length) {
          html += '<div class="ms-evidence-links">' + links.map(renderEvidenceLink).join("") + '</div>';
        }
        html += '</div>';
      });
      html += '</div>';
    }
    var confirmation = pr.marketConfirmation || {};
    var evidenceEntries = confirmation.evidence || {};
    var evidenceKeys = Object.keys(evidenceEntries);
    if (evidenceKeys.length || pr.offsets.length) {
      html += '<div class="ms-detailed-section">';
      html += '<h3>Market Confirmation &amp; Offsets</h3>';
      evidenceKeys.forEach(function(key) {
        var record = evidenceEntries[key];
        if (!record) return;
        html += '<div class="ms-evidence-item">' + escapeHtml(record.finding || key) + '</div>';
      });
      pr.offsets.forEach(function(offset) {
        html += '<div class="ms-evidence-item caution">' + escapeHtml(offset.finding || offset.id || "");
        var links = offset.evidence_links || [];
        if (links.length) {
          html += '<div class="ms-evidence-links">' + links.map(renderEvidenceLink).join("") + '</div>';
        }
        html += '</div>';
      });
      html += '</div>';
    }
    html += '<div class="ms-detailed-section">';
    html += '<h3>Current Interpretation</h3>';
    html += '<p class="ms-interpretation">' + escapeHtml(pr.interpretation || "") + '</p>';
    html += '</div>';
    var posture = pr.portfolioPosture || {};
    var positioning = posture.positioning || [];
    var avoid = posture.avoid || [];
    if (positioning.length || avoid.length) {
      html += '<div class="ms-action-grid">';
      if (positioning.length) {
        html += '<div class="ms-action-col">';
        html += '<h4>Positioning</h4><ul>';
        positioning.forEach(function(action) { html += '<li>' + escapeHtml(action.label || action.code || action) + '</li>'; });
        html += '</ul></div>';
      }
      if (avoid.length) {
        html += '<div class="ms-action-col">';
        html += '<h4>Avoid</h4><ul>';
        avoid.forEach(function(action) { html += '<li>' + escapeHtml(action.label || action.code || action) + '</li>'; });
        html += '</ul></div>';
      }
      html += '</div>';
    }
    if (pr.nextTriggers.length) {
      html += '<div class="ms-detailed-section">';
      html += '<h3>Next Triggers</h3>';
      html += '<ul class="ms-trigger-list">';
      pr.nextTriggers.forEach(function(trigger) {
        html += '<li>' + escapeHtml(trigger.label || trigger.id || "") + '</li>';
      });
      html += '</ul></div>';
    }
    if (pr.watchItems.length) {
      html += '<div class="ms-detailed-section">';
      html += '<h3>Watch Items</h3>';
      html += '<ul class="ms-watch-list">';
      pr.watchItems.forEach(function(item) {
        html += '<li>' + escapeHtml(item.label || item.id || "") + '</li>';
      });
      html += '</ul></div>';
    }
    if (pr.missingInputs.length) {
      html += '<div class="ms-pending-confirmations ms-missing-inputs">';
      html += '<h3>Missing Inputs</h3>';
      html += '<p>' + escapeHtml(pr.missingInputs.join(" \u00B7 ")) + '</p>';
      html += '</div>';
    }
    html += '</div>';
    return html;
  }


export function renderMarketSetupLoading() {
    return '<div class="market-setup-loading" aria-busy="true">Loading market setup\u2026</div>';
  }


export function renderMarketSetupError(errorMsg) {
    return '<div class="ms-error" role="alert">' +
      '<p>Failed to load market setup: ' + escapeHtml(errorMsg) + '</p>' +
      '<button class="ms-retry-btn" type="button" id="msRetryBtn">Retry Market Setup</button>' +
      '</div>';
  }


export function announceStatus(msg) {
    var el = $("marketSetupStatus");
    if (el) el.textContent = msg;
  }


export function bindMarketSetupRetry() {
    var btn = document.getElementById("msRetryBtn");
    if (btn) {
      btn.addEventListener("click", function() {
        state.marketSetup = null;
        state.marketSetupError = null;
        loadMarketSetup();
      });
    }
  }


export function bindEvidenceLinks(section) {
    if (!section) return;
    section.querySelectorAll("[data-evidence-target]").forEach(function(link) {
      link.addEventListener("click", function(event) {
        var targetId = link.dataset.evidenceTarget;
        var target = $(targetId);
        if (!target) return;
        event.preventDefault();
        if (typeof history !== "undefined" && history.replaceState) {
          history.replaceState(null, "", "#" + targetId);
        }
        var reduceMotion = typeof window !== "undefined" && window.matchMedia &&
          window.matchMedia("(prefers-reduced-motion: reduce)").matches;
        target.scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth", block: "start" });
        target.classList.add("evidence-target-highlight");
        setTimeout(function() {
          target.classList.remove("evidence-target-highlight");
        }, 1500);
      });
    });
  }


export var EVIDENCE_LAYER_ROLE_LABELS = {
    decision_input: "Decision Input",
    supplementary: "Supplementary",
    review_only: "Review Only",
    decision_output: "Action",
  };


export function evidenceRoleLabel(role) {
    if (!role) return "";
    return EVIDENCE_LAYER_ROLE_LABELS[role] || "";
  }


export function renderEvidenceLayerHead(layer, index) {
    var html = '<div class="ms-el-head">';
    var title = layer.title || layer.layer_id || "";
    html += '<h3 class="ms-el-title">' + escapeHtml(index != null ? index + " \u00B7 " + title : title) + '</h3>';
    var roleLabel = evidenceRoleLabel(layer.role);
    if (roleLabel) {
      html += '<span class="ms-el-badge ms-el-badge-' + escapeHtml(layer.role) + '">' + escapeHtml(roleLabel) + '</span>';
    }
    html += '</div>';
    if (layer.scope_note) {
      html += '<p class="ms-el-scope">' + escapeHtml(layer.scope_note) + '</p>';
    }
    return html;
  }


export function renderEvidenceFindings(title, entries) {
    var list = entries || [];
    if (!list.length) return "";
    var html = '<div class="ms-el-findings">';
    html += '<h4 class="ms-el-findings-title">' + escapeHtml(title) + '</h4>';
    html += '<ul>';
    list.forEach(function(entry) {
      html += '<li>' + escapeHtml(entry.finding || entry.id || "") + '</li>';
    });
    html += '</ul></div>';
    return html;
  }


export function renderEvidenceStringList(title, entries, listClass) {
    var list = entries || [];
    if (!list.length) return "";
    var html = '<div class="ms-el-list-block">';
    html += '<h4 class="ms-el-findings-title">' + escapeHtml(title) + '</h4>';
    html += '<ul class="' + listClass + '">';
    list.forEach(function(item) {
      html += '<li>' + escapeHtml((item && item.label) || (item && item.id) || item) + '</li>';
    });
    html += '</ul></div>';
    return html;
  }


export function renderCollapsibleSection(title, bodyHtml, options) {
    var opts = options || {};
    if (!title || !bodyHtml) return "";
    var html = '<details class="ms-el-collapsible"' + (opts.open ? " open" : "") + '>';
    html += '<summary class="ms-el-collapsible-summary">' + escapeHtml(title) + '</summary>';
    if (opts.note) {
      html += '<p class="ms-el-collapsible-note">' + escapeHtml(opts.note) + '</p>';
    }
    html += '<div class="ms-el-collapsible-body">' + bodyHtml + '</div>';
    html += '</details>';
    return html;
  }


export function renderDecisionPathOutput(output, extraClass) {
    if (!output || !output.label) return "";
    return '<span class="ms-dp-output ' + (extraClass ? extraClass + " " : "") +
      stateSentimentClass(output.sentiment) + '">' + escapeHtml(output.label) + '</span>';
  }


export function renderDecisionPathStep(step) {
    if (!step) return "";
    var kind = step.kind || "";
    var html = '<div class="ms-dp-step">';
    html += '<div class="ms-dp-step-head">';
    if (step.n != null) {
      html += '<span class="ms-dp-step-n">' + escapeHtml(String(step.n)) + '</span>';
    }
    html += '<span class="ms-dp-step-title">' + escapeHtml(step.title || "") + '</span>';
    html += '</div>';
    html += '<div class="ms-dp-step-body">';
    var output = step.output || null;
    var evidence = "";
    if (kind === "macro_thesis") {
      var input = step.input || {};
      var hasInput = !!(input.label || input.value);
      if (hasInput) {
        evidence += '<span class="ms-dp-io">' + escapeHtml(input.label || "");
        if (input.value) {
          evidence += (input.label ? ": " : "") + '<strong>' + escapeHtml(input.value) + '</strong>';
        }
        evidence += '</span>';
      }
    } else if (kind === "market_test") {
      var tests = step.tests || [];
      if (tests.length) {
        evidence += '<ul class="ms-dp-tests">';
        tests.forEach(function(test) {
          evidence += '<li class="ms-dp-test">';
          evidence += '<span class="ms-dp-test-label">' + escapeHtml(test.label || test.id || "") + '</span>';
          if (test.state_label) {
            evidence += '<span class="ms-dp-test-state ' + stateSentimentClass(test.sentiment) + '">' +
              escapeHtml(test.state_label) + '</span>';
          }
          if (test.verdict_label) {
            evidence += '<span class="ms-dp-test-verdict">' + escapeHtml(test.verdict_label) + '</span>';
          }
          evidence += '</li>';
        });
        evidence += '</ul>';
      }
      if (step.missing_inputs && step.missing_inputs.length) {
        evidence += '<span class="ms-dp-test-count ms-dp-missing">Missing: ' + escapeHtml(step.missing_inputs.join(", ")) + '</span>';
      }
      if (step.passed_count != null && step.total != null) {
        evidence += '<span class="ms-dp-test-count">' +
          escapeHtml(String(step.passed_count) + " / " + String(step.total)) + ' confirmed</span>';
      }
    } else if (kind === "relationship") {
      var inputs = step.inputs || [];
      if (inputs.length) {
        evidence += '<span class="ms-dp-io">' + escapeHtml(inputs.join(" + ")) + '</span>';
      }
    } else if (kind === "action") {
      var fields = output.fields || [];
      if (fields.length) {
        evidence += '<ul class="ms-dp-posture-fields">';
        fields.forEach(function(field) {
          if (!field.value) return;
          evidence += '<li class="ms-dp-posture-field">';
          evidence += '<span class="ms-dp-posture-field-label">' + escapeHtml(field.label) + '</span>';
          evidence += '<span class="ms-dp-posture-field-value">' + escapeHtml(field.value) + '</span>';
          evidence += '</li>';
        });
        evidence += '</ul>';
      }
    }
    if (evidence) {
      html += '<div class="ms-dp-evidence">' + evidence + '</div>';
    }
    if (output && (output.label || output.agreement)) {
      html += '<div class="ms-dp-conclusion">';
      if (output.label) {
        html += renderDecisionPathOutput(output, kind === "action" ? "ms-dp-output-lg" : "");
      }
      if (output.agreement) {
        html += '<span class="ms-dp-agreement">Agreement: ' + escapeHtml(output.agreement) + '</span>';
      }
      html += '</div>';
    }
    html += '</div></div>';
    return html;
  }


export var DECISION_PATH_TITLE = "Why This Setup?";


export function renderDecisionPath(decisionPath) {
    if (!decisionPath) return "";
    var steps = decisionPath.steps || [];
    if (!steps.length) return "";
    var html = '<div class="ms-dp-steps">';
    var tracks = steps.filter(function(step) {
      return step.kind === "macro_thesis" || step.kind === "market_test";
    });
    var downstream = steps.filter(function(step) {
      return step.kind !== "macro_thesis" && step.kind !== "market_test";
    });
    if (tracks.length) {
      html += '<div class="ms-dp-tracks">';
      tracks.forEach(function(step) {
        html += '<div class="ms-dp-track">' + renderDecisionPathStep(step) + '</div>';
      });
      html += '</div>';
      html += '<div class="ms-dp-connector" aria-hidden="true">↓</div>';
    }
    downstream.forEach(function(step, index) {
      html += renderDecisionPathStep(step);
      if (index < downstream.length - 1) {
        html += '<div class="ms-dp-connector" aria-hidden="true">↓</div>';
      }
    });
    html += '</div>';
    return html;
  }


export function renderFieldRows(rows) {
    var items = (rows || []).filter(function(row) {
      return row.value != null && row.value !== "";
    });
    if (!items.length) return "";
    var html = '<div class="ms-el-metrics">';
    items.forEach(function(row) {
      html += '<div class="ms-el-metric">';
      html += '<span class="ms-el-metric-label">' + escapeHtml(row.label) + '</span>';
      html += '<span class="ms-el-metric-value' + (row.sentiment ? " " + stateSentimentClass(row.sentiment) : "") + '">' +
        escapeHtml(row.value) + '</span>';
      html += '</div>';
    });
    html += '</div>';
    return html;
  }


export function renderDetailsMetrics(metrics) {
    var list = metrics || [];
    if (!list.length) return "";
    var html = '<details class="ms-el-details"><summary>Underlying metrics</summary>';
    html += '<ul class="ms-el-metrics">';
    list.forEach(function(metric) {
      html += '<li class="ms-el-metric">';
      html += '<span class="ms-el-metric-label">' + escapeHtml(metric.label || "") + '</span>';
      html += '<span class="ms-el-metric-value ' + stateSentimentClass(metric.sentiment) + '">' +
        escapeHtml(metric.value != null ? metric.value : "—") + '</span>';
      if (metric.period) {
        html += '<span class="ms-el-metric-period">' + escapeHtml(metric.period) + '</span>';
      }
      html += '</li>';
    });
    html += '</ul></details>';
    return html;
  }


export function renderLeadingExpectationGroup(group) {
    if (!group) return "";
    var html = '<div class="ms-el-group">';
    html += '<div class="ms-el-group-head">';
    html += '<h4 class="ms-el-group-title">' + escapeHtml(group.title || group.id || "") + '</h4>';
    if (group.group_role_label) {
      var roleClass = group.group_role === "regime_selector"
        ? "ms-el-role-badge-regime"
        : "ms-el-role-badge-supporting";
      html += '<span class="ms-el-role-badge ' + roleClass + '">' + escapeHtml(group.group_role_label) + '</span>';
    }
    html += '</div>';
    html += renderFieldRows([
      { label: "Current state", value: group.current_state, sentiment: group.sentiment },
      { label: "Relationship to macro thesis", value: group.relationship_label },
      { label: "Decision effect", value: group.decision_effect },
      { label: "Period", value: group.period },
    ]);
    if (group.interpretation) {
      html += '<p class="ms-el-interpretation">' + escapeHtml(group.interpretation) + '</p>';
    }
    if (group.data_status && group.data_status !== "available") {
      html += '<p class="ms-el-data-status">Data not available</p>';
    }
    if (group.note) {
      html += '<p class="ms-el-note">' + escapeHtml(group.note) + '</p>';
    }
    html += renderDetailsMetrics(group.details_metrics);
    html += '</div>';
    return html;
  }


export function renderLeadingExpectations(layer) {
    if (!layer) return "";
    var html = '<section class="ms-evidence-layer ms-el-section">';
    html += renderEvidenceLayerHead(layer, null);
    var groups = layer.groups || [];
    if (groups.length) {
      html += '<div class="ms-el-groups">';
      groups.forEach(function(group) {
        html += renderLeadingExpectationGroup(group);
      });
      html += '</div>';
    }
    html += '</section>';
    return html;
  }


export function renderMarketPricing(layer) {
    if (!layer) return "";
    var html = '<section class="ms-evidence-layer ms-el-section">';
    html += renderEvidenceLayerHead(layer, null);
    if (layer.tests_summary) {
      html += '<p class="ms-el-tests-summary">' + escapeHtml(layer.tests_summary) + '</p>';
    }
    var tests = layer.tests || [];
    if (tests.length) {
      html += '<ul class="ms-el-tests">';
      tests.forEach(function(test) {
        html += '<li class="ms-el-test">';
        html += '<span class="ms-el-test-label">' + escapeHtml(test.label || test.id || "") + '</span>';
        if (test.state_label) {
          html += '<span class="ms-el-test-state ' + stateSentimentClass(test.sentiment) + '">' +
            escapeHtml(test.state_label) + '</span>';
        }
        if (test.verdict_label) {
          html += '<span class="ms-el-test-verdict">' + escapeHtml(test.verdict_label) + '</span>';
        }
        if (test.test_contribution) {
          html += '<span class="ms-el-test-contribution">' + escapeHtml(test.test_contribution) + '</span>';
        }
        if (test.finding) {
          html += '<span class="ms-el-test-finding">' + escapeHtml(test.finding) + '</span>';
        }
        html += '</li>';
      });
      html += '</ul>';
    } else if (layer.status_label) {
      html += '<p class="ms-el-test-verdict">' + escapeHtml(layer.status_label) + '</p>';
    }
    if (layer.missing_inputs && layer.missing_inputs.length) {
      html += '<p class="ms-el-note">Missing inputs: ' + escapeHtml(layer.missing_inputs.join(", ")) + '</p>';
    }
    var liquidityOffset = layer.liquidity_offset;
    if (liquidityOffset) {
      html += '<div class="ms-el-liquidity-offset">';
      html += '<h4 class="ms-el-findings-title">' + escapeHtml(liquidityOffset.label || "Liquidity Offset") + '</h4>';
      html += '<div class="ms-el-test">';
      if (liquidityOffset.state_label) {
        html += '<span class="ms-el-test-state ' + stateSentimentClass(liquidityOffset.sentiment) + '">' +
          escapeHtml(liquidityOffset.state_label) + '</span>';
      }
      if (liquidityOffset.finding) {
        html += '<span class="ms-el-test-finding">' + escapeHtml(liquidityOffset.finding) + '</span>';
      }
      html += '</div>';
      if (liquidityOffset.note) {
        html += '<p class="ms-el-note">' + escapeHtml(liquidityOffset.note) + '</p>';
      }
      html += '</div>';
    }
    html += renderEvidenceFindings("Offsets", layer.offsets);
    html += renderEvidenceFindings("Context (non-voting)", layer.context);
    html += '</section>';
    return html;
  }


export function renderPortfolioConclusion(layer) {
    if (!layer) return "";
    var html = '<section class="ms-evidence-layer ms-el-section">';
    html += renderEvidenceLayerHead(layer, null);
    if (layer.posture_label) {
      html += '<p class="ms-el-posture ' + stateSentimentClass(layer.posture_code) + '">' +
        escapeHtml(layer.posture_label) + '</p>';
    }
    html += renderFieldRows([
      { label: "Net exposure", value: layer.net_exposure },
      { label: "Gross exposure", value: layer.gross_exposure },
      { label: "Implementation", value: layer.implementation },
      { label: "Broad beta", value: layer.broad_beta },
    ]);
    var positioning = layer.positioning || [];
    var avoid = layer.avoid || [];
    if (positioning.length || avoid.length) {
      html += '<div class="ms-el-action-grid">';
      if (positioning.length) {
        html += '<div class="ms-el-action-col"><h4>Positioning</h4><ul>';
        positioning.forEach(function(item) {
          html += '<li>' + escapeHtml((item && item.label) || item) + '</li>';
        });
        html += '</ul></div>';
      }
      if (avoid.length) {
        html += '<div class="ms-el-action-col"><h4>Avoid</h4><ul>';
        avoid.forEach(function(item) {
          html += '<li>' + escapeHtml((item && item.label) || item) + '</li>';
        });
        html += '</ul></div>';
      }
      html += '</div>';
    }
    html += renderEvidenceStringList("Next Triggers", layer.next_triggers, "ms-el-trigger-list");
    html += renderEvidenceStringList("Watch Items", layer.watch_items, "ms-el-watch-list");
    var excluded = layer.excluded_inputs || [];
    if (excluded.length) {
      html += '<p class="ms-el-excluded">Excluded from v2: ' + escapeHtml(excluded.join(" · ")) + '</p>';
    }
    html += '</section>';
    return html;
  }


export function renderRealityGroupCard(group) {
    if (!group) return "";
    var html = '<div class="ms-el-group">';
    html += '<div class="ms-el-group-head">';
    html += '<h4 class="ms-el-group-title">' + escapeHtml(group.title || group.id || "") + '</h4>';
    html += renderGovernanceBadge(group.governance_status, group.governance_status_label);
    html += '</div>';
    if (group.formal_signal) {
      html += '<p class="ms-el-summary ' + stateSentimentClass(group.sentiment) + '">' +
        escapeHtml(group.formal_signal) + '</p>';
    }
    if (group.relation_to_thesis) {
      html += '<p class="ms-el-note">' + escapeHtml(group.relation_to_thesis) + '</p>';
    }
    if (group.reason) {
      html += '<p class="ms-el-note">' + escapeHtml(group.reason) + '</p>';
    }
    if (group.decision_effect) {
      html += '<p class="ms-el-note">' + escapeHtml(group.decision_effect) + '</p>';
    }
    if (group.coverage) {
      html += '<p class="ms-el-note">' + escapeHtml(group.coverage) + '</p>';
    }
    if (group.period) {
      html += '<p class="ms-el-note">' + escapeHtml(group.period) + '</p>';
    }
    if (group.data_status && group.data_status !== "available") {
      html += '<p class="ms-el-data-status">Data not available</p>';
    }
    html += renderDetailsMetrics(group.details_metrics);
    html += '</div>';
    return html;
  }


export function renderRealityLayer(layer) {
    if (!layer) return "";
    var html = '<section class="ms-evidence-layer ms-el-section">';
    html += renderEvidenceLayerHead(layer, null);
    var coverage = layer.coverage_summary || [];
    if (coverage.length) {
      html += '<p class="ms-el-coverage">' + escapeHtml(coverage.join(" · ")) + '</p>';
    }
    var groups = layer.groups || [];
    if (groups.length) {
      html += '<div class="ms-el-groups">';
      groups.forEach(function(group) {
        html += renderRealityGroupCard(group);
      });
      html += '</div>';
    }
    html += '</section>';
    return html;
  }


export function renderEconomicReality(layer) {
    return renderRealityLayer(layer);
  }


export function renderFinalConfirmation(layer) {
    return renderRealityLayer(layer);
  }


export function renderGovernanceBadge(status, label) {
    if (!status || !label) return "";
    return '<span class="ms-el-governance-badge ms-el-governance-' + escapeHtml(status) + '">' +
      escapeHtml(label) + '</span>';
  }


export function renderGovernanceLegend(legend) {
    var items = legend || [];
    if (!items.length) return "";
    var html = '<div class="ms-el-governance-legend">';
    items.forEach(function(entry) {
      html += '<div class="ms-el-legend-item">';
      html += renderGovernanceBadge(entry.status, entry.label);
      html += '<span class="ms-el-legend-desc">' + escapeHtml(entry.description) + '</span>';
      html += '</div>';
    });
    html += '</div>';
    return html;
  }


export function renderEvidenceLayers(layers) {
    if (!layers) return "";
    if (layers.version !== "market_setup_evidence_layers_v2") {
      return "";
    }
    var html = '<div class="ms-el">';
    html += renderCollapsibleSection(DECISION_PATH_TITLE, renderDecisionPath(layers.decision_path));
    html += renderPortfolioConclusion(layers.portfolio_conclusion);
    html += renderCollapsibleSection(
      "Decision Inputs",
      renderLeadingExpectations(layers.leading_expectations) +
        renderMarketPricing(layers.market_pricing)
    );
    var supplementaryNote = layers.boundary_note;
    if (!supplementaryNote) {
      var scopeNotes = [];
      if (layers.economic_reality && layers.economic_reality.scope_note) {
        scopeNotes.push(layers.economic_reality.scope_note);
      }
      if (layers.final_confirmation && layers.final_confirmation.scope_note) {
        scopeNotes.push(layers.final_confirmation.scope_note);
      }
      supplementaryNote = scopeNotes.join(" ");
    }
    html += renderCollapsibleSection(
      "Supplementary Macro Context",
      renderGovernanceLegend(layers.governance_legend) +
        renderEconomicReality(layers.economic_reality) +
        renderFinalConfirmation(layers.final_confirmation),
      { note: supplementaryNote || null }
    );
    html += '</div>';
    return html;
  }


export function renderMarketSetup() {
    var section = $("marketSetup");
    if (!section) return;
    if (state.marketSetupLoading) {
      section.innerHTML = renderMarketSetupLoading();
      return;
    }
    var setup = state.marketSetup;
    if (state.marketSetupError) {
      section.innerHTML = renderMarketSetupError(state.marketSetupError);
      bindMarketSetupRetry();
      announceStatus("Market setup failed to load");
      return;
    }
    if (!setup) {
      section.innerHTML = '<div class="market-setup-loading">Market setup data is not available.</div>';
      return;
    }
    var presentation = buildMarketSetupPresentation(setup);
    section.innerHTML = renderDecisionHero(presentation) +
      (presentation.evidenceLayers ? renderEvidenceLayers(presentation.evidenceLayers) : renderDetailedReasoning(presentation));
    announceStatus("Market setup \u2014 " + (presentation.portfolioPosture.label || "loaded"));
    bindEvidenceLinks(section);
  }


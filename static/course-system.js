(function () {
  const LOCAL_STORAGE_KEY = "methodWorkflowRuns.v1";
  const EDGE_COLOR = "rgba(56, 63, 55, 0.28)";
  const NODE_LAYOUT = {
    data_readiness: { row: 1, col: 2, span: 1 },
    macro_regime: { row: 2, col: 1, span: 1 },
    international_adr_workflow: { row: 2, col: 3, span: 1 },
    sector_theme_context: { row: 3, col: 2, span: 1 },
    portfolio_construction: { row: 4, col: 1, span: 1 },
    fundamental_quantitative_bias: { row: 4, col: 3, span: 1 },
    fundamental_qualitative_bias: { row: 5, col: 1, span: 1 },
    catalyst_window: { row: 5, col: 3, span: 1 },
    technical_timing: { row: 6, col: 1, span: 1 },
    trade_risk_management: { row: 6, col: 3, span: 1 },
    process_discipline: { row: 7, col: 2, span: 1 },
  };

  const state = {
    method: null,
    graphNodes: [],
    latest: null,
    savedRuns: [],
    selectedNodeId: null,
    running: false,
  };

  function $(id) {
    return document.getElementById(id);
  }

  function delay(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  async function jsonFetch(url, options) {
    const response = await fetch(url, options);
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    return response.json();
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function fmtStatus(status) {
    return String(status || "").replace(/_/g, " ");
  }

  function fmtDate(value) {
    if (!value) return "";
    return value.replace("T", " ").replace("+00:00", " UTC");
  }

  function fmtAction(action) {
    if (typeof action === "string") {
      return fmtStatus(action);
    }
    const prefix = [action.side, action.node_id].filter(Boolean).map(fmtStatus).join(" / ");
    return `${prefix ? `${prefix}: ` : ""}${action.message || action.action || fmtStatus(action.fail_effect || "")}`;
  }

  function splitTags(value) {
    return String(value || "")
      .split(",")
      .map((item) => item.trim().toLowerCase())
      .filter(Boolean);
  }

  function buildObservations(formData) {
    const trend = String(formData.get("trend") || "").trim();
    const catalyst = String(formData.get("catalyst") || "").trim();
    const price = String(formData.get("price") || "").trim();
    const avgDollarVolume = String(formData.get("avgDollarVolume") || "").trim();
    const thesis = String(formData.get("thesis") || "").trim();
    const notes = String(formData.get("notes") || "").trim();
    const tags = splitTags(formData.get("tags"));

    const observations = {
      signals: {},
      metrics: {},
      setup: {},
    };

    if (trend) observations.signals.trend = trend;
    if (catalyst) observations.setup.catalyst = catalyst;
    if (price) observations.metrics.price = Number(price);
    if (avgDollarVolume) observations.metrics.avg_dollar_volume_millions = Number(avgDollarVolume);
    if (tags.length) observations.tags = tags;
    if (thesis) observations.context = { ...(observations.context || {}), thesis };
    if (notes) observations.context = { ...(observations.context || {}), notes };

    return observations;
  }

  function buildPayload(form) {
    const formData = new FormData(form);
    return {
      symbol: String(formData.get("symbol") || "").trim().toUpperCase(),
      observations: buildObservations(formData),
    };
  }

  function nodeLayout(nodeId) {
    return NODE_LAYOUT[nodeId] || { row: 6, col: 1, span: 1 };
  }

  function cloneNode(node) {
    return {
      node_id: node.id || node.node_id,
      title: node.title,
      decision_question: node.decision_question,
      description: node.description,
      status: node.status || "idle",
      long: node.long || { status: "idle", checks: [], evidence: [], missing_inputs: [], next_actions: [] },
      short: node.short || { status: "idle", checks: [], evidence: [], missing_inputs: [], next_actions: [] },
      checks: node.checks || [],
      tool_hooks: node.tool_hooks || [],
      incoming_edges: node.incoming_edges || [],
      outgoing_edges: node.outgoing_edges || [],
      method_basis: node.method_basis || [],
      layout: node.layout || nodeLayout(node.id || node.node_id),
    };
  }

  function normalizeMethodNodes(nodes) {
    return (nodes || []).map((node) => {
      const cloned = cloneNode(node);
      cloned.status = "idle";
      return cloned;
    });
  }

  function mergeResultNodes(resultNodes) {
    const resultMap = new Map((resultNodes || []).map((node) => [node.node_id, node]));
    state.graphNodes = state.method.workflow_nodes.map((node) => {
      const result = resultMap.get(node.id) || {};
      return {
        node_id: node.id,
        title: node.title,
        decision_question: node.decision_question,
        description: node.description,
        status: result.status || "idle",
        long: result.long || { status: "idle", checks: [], evidence: [], missing_inputs: [], next_actions: [] },
        short: result.short || { status: "idle", checks: [], evidence: [], missing_inputs: [], next_actions: [] },
        checks: result.checks || [],
        tool_hooks: result.tool_hooks || node.tool_hooks || [],
        incoming_edges: result.incoming_edges || node.incoming_edges || [],
        outgoing_edges: result.outgoing_edges || node.outgoing_edges || [],
        method_basis: result.method_basis || node.source_refs || [],
        layout: nodeLayout(node.id),
      };
    });
  }

  function rendermethodBasisItems(methodBasis) {
    if (Array.isArray(methodBasis)) {
      return methodBasis
        .map((ref) => `<li>${escapeHtml(ref.document || ref.title || ref.check_id || "")} <span class="muted">${escapeHtml(ref.section || ref.status || "")}</span></li>`)
        .join("");
    }
    if (methodBasis && typeof methodBasis === "object") {
      return Object.entries(methodBasis)
        .flatMap(([side, items]) => (items || []).map((item) => ({ side, ...item })))
        .map((item) => `<li><span class="muted">${escapeHtml(item.side)} / ${escapeHtml(item.status || "")}</span> ${escapeHtml(item.title || item.check_id || "")}</li>`)
        .join("");
    }
    return "";
  }

  function renderMethodMeta() {
    const target = $("methodMeta");
    if (!state.method) {
      target.textContent = "Method graph unavailable.";
      return;
    }
    const sourceCount = Array.isArray(state.method.source_documents) ? state.method.source_documents.length : 0;
    const nodeCount = Array.isArray(state.method.workflow_nodes) ? state.method.workflow_nodes.length : 0;
    const checkCount = Array.isArray(state.method.node_checks) ? state.method.node_checks.length : 0;
    target.textContent = `Version ${state.method.version} | ${sourceCount} notes | ${nodeCount} nodes | ${checkCount} checks`;
  }

  function renderGraph() {
    const graph = $("workflowGraph");
    if (!state.method) {
      graph.className = "workflow-graph empty";
      graph.innerHTML = "<div class=\"graph-empty\">Loading graph...</div>";
      $("graphLinks").innerHTML = "";
      return;
    }

    graph.className = "workflow-graph";
    graph.innerHTML = state.graphNodes
      .map((node) => {
        const layout = node.layout || nodeLayout(node.node_id);
        const selected = state.selectedNodeId === node.node_id ? " selected" : "";
        return `
          <button
            type="button"
            class="graph-node status-${escapeHtml(node.status)}${selected}"
            data-node-id="${escapeHtml(node.node_id)}"
            style="grid-row:${layout.row}; grid-column:${layout.col} / span ${layout.span};"
          >
            <span class="node-kicker">${escapeHtml(fmtStatus(node.status))}</span>
            <span class="node-title">${escapeHtml(node.title)}</span>
            <span class="node-question">${escapeHtml(node.decision_question)}</span>
          </button>
        `;
      })
      .join("");

    graph.querySelectorAll(".graph-node").forEach((button) => {
      button.addEventListener("click", () => {
        state.selectedNodeId = button.dataset.nodeId;
        renderGraph();
        renderNodeDetail();
      });
    });

    requestAnimationFrame(drawGraphEdges);
  }

  function drawGraphEdges() {
    const svg = $("graphLinks");
    const frame = $("graphFrame");
    if (!state.method || !frame || !svg) {
      return;
    }

    const isCompact = window.matchMedia("(max-width: 980px)").matches;
    if (isCompact) {
      svg.innerHTML = "";
      svg.style.display = "none";
      return;
    }

    svg.style.display = "block";
    const frameRect = frame.getBoundingClientRect();
    const graph = $("workflowGraph");
    const nodeEls = new Map();
    graph.querySelectorAll(".graph-node").forEach((el) => {
      nodeEls.set(el.dataset.nodeId, el);
    });

    const paths = [];
    const edges = [];
    state.method.workflow_nodes.forEach((node) => {
      (node.outgoing_edges || []).forEach((target) => {
        edges.push([node.id, target]);
      });
    });

    edges.forEach(([from, to]) => {
      const fromEl = nodeEls.get(from);
      const toEl = nodeEls.get(to);
      if (!fromEl || !toEl) return;

      const fromRect = fromEl.getBoundingClientRect();
      const toRect = toEl.getBoundingClientRect();
      const x1 = fromRect.left + fromRect.width / 2 - frameRect.left;
      const y1 = fromRect.top + fromRect.height / 2 - frameRect.top;
      const x2 = toRect.left + toRect.width / 2 - frameRect.left;
      const y2 = toRect.top + toRect.height / 2 - frameRect.top;
      const dx = Math.max(Math.abs(x2 - x1), 120);
      const midY = (y1 + y2) / 2;
      const c1x = x1 + (x2 > x1 ? dx * 0.35 : -dx * 0.35);
      const c2x = x2 - (x2 > x1 ? dx * 0.35 : -dx * 0.35);

      paths.push(`M ${x1} ${y1} C ${c1x} ${midY}, ${c2x} ${midY}, ${x2} ${y2}`);
    });

    svg.setAttribute("viewBox", `0 0 ${frame.clientWidth} ${frame.clientHeight}`);
    svg.innerHTML = `
      <defs>
        <marker id="arrowHead" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto">
          <path d="M0,0 L0,6 L9,3 z" fill="${EDGE_COLOR}" />
        </marker>
      </defs>
      ${paths.map((path) => `<path class="graph-edge" d="${path}" marker-end="url(#arrowHead)"></path>`).join("")}
    `;
  }

  function renderNodeDetail() {
    const panel = $("nodeDetail");
    const node = state.graphNodes.find((item) => item.node_id === state.selectedNodeId) || state.graphNodes[0];
    if (!node) {
      panel.className = "node-detail empty";
      panel.textContent = "Select a node.";
      return;
    }

    const longChecks = (node.long.checks || [])
      .map((check) => `<li><strong>${escapeHtml(check.status)}</strong> ${escapeHtml(check.title)}: ${escapeHtml(check.message)}</li>`)
      .join("");
    const shortChecks = (node.short.checks || [])
      .map((check) => `<li><strong>${escapeHtml(check.status)}</strong> ${escapeHtml(check.title)}: ${escapeHtml(check.message)}</li>`)
      .join("");
    const basis = rendermethodBasisItems(node.method_basis);
    const nextActions = [...(node.long.next_actions || []), ...(node.short.next_actions || [])]
      .map((action) => `<li>${escapeHtml(action)}</li>`)
      .join("");
    const missing = [...(node.long.missing_inputs || []), ...(node.short.missing_inputs || [])]
      .map((field) => `<li>${escapeHtml(field)}</li>`)
      .join("");

    panel.className = "node-detail";
    panel.innerHTML = `
      <div class="node-detail-head">
        <div>
          <div class="node-detail-kicker">Node</div>
          <h3>${escapeHtml(node.title)}</h3>
        </div>
        <div class="status-chip status-${escapeHtml(node.status)}">${escapeHtml(fmtStatus(node.status))}</div>
      </div>
      <p class="node-question">${escapeHtml(node.decision_question)}</p>
      <p class="node-description">${escapeHtml(node.description)}</p>
      <div class="node-metadata">
        <div><span>Tools</span><strong>${(node.tool_hooks || []).map(escapeHtml).join(", ") || "none"}</strong></div>
        <div><span>Incoming</span><strong>${(node.incoming_edges || []).map(escapeHtml).join(", ") || "none"}</strong></div>
        <div><span>Outgoing</span><strong>${(node.outgoing_edges || []).map(escapeHtml).join(", ") || "none"}</strong></div>
      </div>
      <div class="side-blocks">
        <section class="side-block">
          <div class="side-head">
            <h4>Long</h4>
            <span class="status-chip status-${escapeHtml(node.long.status)}">${escapeHtml(fmtStatus(node.long.status))}</span>
          </div>
          <ul class="plain-list">${longChecks || "<li>No checks for this side.</li>"}</ul>
        </section>
        <section class="side-block">
          <div class="side-head">
            <h4>Short</h4>
            <span class="status-chip status-${escapeHtml(node.short.status)}">${escapeHtml(fmtStatus(node.short.status))}</span>
          </div>
          <ul class="plain-list">${shortChecks || "<li>No checks for this side.</li>"}</ul>
        </section>
      </div>
      <section class="side-block">
        <div class="side-head">
          <h4>Missing Inputs</h4>
        </div>
        <ul class="plain-list">${missing || "<li>None</li>"}</ul>
      </section>
      <section class="side-block">
        <div class="side-head">
          <h4>Next Actions</h4>
        </div>
        <ul class="plain-list">${nextActions || "<li>None</li>"}</ul>
      </section>
      <section class="side-block">
        <div class="side-head">
          <h4>Method Basis</h4>
        </div>
        <ul class="plain-list">${basis || "<li>No source refs</li>"}</ul>
      </section>
    `;
  }

  function countStatuses(nodes) {
    return (nodes || []).reduce(
      (acc, node) => {
        acc.total += 1;
        acc[node.status] = (acc[node.status] || 0) + 1;
        return acc;
      },
      { total: 0, idle: 0, running: 0, pass: 0, fail: 0, missing: 0, mixed: 0, blocked: 0, error: 0 }
    );
  }

  function renderLatest() {
    const panel = $("resultPanel");
    const result = state.latest;
    if (!result) {
      panel.className = "result-panel empty";
      panel.textContent = "No workflow run yet.";
      return;
    }

    const counts = countStatuses(result.nodes);
    const missing = (result.missing_information || [])
      .map((item) => `<li>${escapeHtml(item.title)} <span class="muted">(${escapeHtml((item.fields || []).join(", "))})</span></li>`)
      .join("");
    const actions = (result.next_actions || [])
      .map((item) => `<li>${escapeHtml(fmtAction(item))}</li>`)
      .join("");

    panel.className = "result-panel";
    panel.innerHTML = `
      <div class="summary-strip">
        <div>
          <div class="history-symbol">${escapeHtml(result.symbol)}</div>
          <div class="history-meta">Method ${escapeHtml(result.method_version)}</div>
        </div>
        <div class="status-chip status-${escapeHtml(result.final_status)}">${escapeHtml(fmtStatus(result.final_status))}</div>
      </div>
      <div class="stats-grid">
        <div class="stat-cell"><span>Total</span><strong>${counts.total}</strong></div>
        <div class="stat-cell"><span>Pass</span><strong>${counts.pass}</strong></div>
        <div class="stat-cell"><span>Fail</span><strong>${counts.fail}</strong></div>
        <div class="stat-cell"><span>Missing</span><strong>${counts.missing}</strong></div>
        <div class="stat-cell"><span>Mixed</span><strong>${counts.mixed}</strong></div>
      </div>
      ${missing ? `<section class="result-section"><h3>Missing Information</h3><ul class="plain-list">${missing}</ul></section>` : ""}
      ${actions ? `<section class="result-section"><h3>Next Actions</h3><ul class="plain-list">${actions}</ul></section>` : ""}
      <section class="result-section">
        <h3>Saved Context</h3>
        <div class="saved-context">${escapeHtml(result.context_summary || "No optional context supplied.")}</div>
      </section>
    `;
  }

  function saveRun(result, contextSummary) {
    const entry = {
      run_at: new Date().toISOString(),
      context_summary: contextSummary || "",
      ...result,
    };
    const nextRuns = [entry, ...state.savedRuns.filter((item) => item.symbol !== entry.symbol || item.run_at !== entry.run_at)].slice(0, 8);
    state.savedRuns = nextRuns;
    localStorage.setItem(LOCAL_STORAGE_KEY, JSON.stringify(nextRuns));
    renderSavedRuns();
  }

  function loadSavedRuns() {
    try {
      const raw = localStorage.getItem(LOCAL_STORAGE_KEY);
      state.savedRuns = raw ? JSON.parse(raw) : [];
    } catch (error) {
      state.savedRuns = [];
    }
  }

  function renderSavedRuns() {
    const panel = $("historyPanel");
    if (!state.savedRuns.length) {
      panel.className = "history-list empty";
      panel.textContent = "No saved runs yet.";
      return;
    }

    panel.className = "history-list";
    panel.innerHTML = state.savedRuns
      .map((item, index) => `
        <button class="history-item" type="button" data-history-index="${index}">
          <div class="history-top">
            <div class="history-symbol">${escapeHtml(item.symbol)}</div>
            <div class="status-chip status-${escapeHtml(item.final_status)}">${escapeHtml(fmtStatus(item.final_status))}</div>
          </div>
          <div class="history-meta">${escapeHtml(fmtDate(item.run_at))}</div>
          <div class="history-snippet">${escapeHtml(item.context_summary || "No optional context.")}</div>
        </button>
      `)
      .join("");

    panel.querySelectorAll(".history-item").forEach((button) => {
      button.addEventListener("click", () => {
        const entry = state.savedRuns[Number(button.dataset.historyIndex)];
        if (!entry) return;
        state.latest = entry;
        mergeResultNodes(entry.nodes || []);
        renderGraph();
        renderNodeDetail();
        renderLatest();
      });
    });
  }

  async function loadMethod() {
    state.method = await jsonFetch("/api/method-system/method");
    state.graphNodes = normalizeMethodNodes(state.method.workflow_nodes || []);
    state.selectedNodeId = state.graphNodes[0]?.node_id || null;
    renderMethodMeta();
    renderGraph();
    renderNodeDetail();
  }

  async function runWorkflow(event) {
    event.preventDefault();
    const status = $("workflowStatus");
    const form = event.currentTarget;
    const payload = buildPayload(form);
    state.running = true;
    status.textContent = "Queuing graph...";

    state.graphNodes = state.graphNodes.map((node) => ({ ...node, status: "queued" }));
    renderGraph();
    await delay(120);
    status.textContent = "Running graph...";
    state.graphNodes = state.graphNodes.map((node) => ({ ...node, status: "running" }));
    renderGraph();
    await delay(180);

    try {
      const result = await jsonFetch("/api/method-system/workflow/evaluate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      state.latest = {
        ...result,
        context_summary: [
          payload.observations?.setup?.catalyst ? `Catalyst: ${payload.observations.setup.catalyst}` : "",
          payload.observations?.signals?.trend ? `Trend: ${payload.observations.signals.trend}` : "",
          payload.observations?.metrics?.price ? `Price: ${payload.observations.metrics.price}` : "",
          payload.observations?.metrics?.avg_dollar_volume_millions ? `Avg dollar volume: ${payload.observations.metrics.avg_dollar_volume_millions}` : "",
        ].filter(Boolean).join(" | "),
      };
      mergeResultNodes(result.nodes || []);
      if (!state.selectedNodeId && state.graphNodes.length) {
        state.selectedNodeId = state.graphNodes[0].node_id;
      }
      renderGraph();
      renderNodeDetail();
      renderLatest();
      saveRun(state.latest, state.latest.context_summary);
      status.textContent = "Complete.";
    } catch (error) {
      state.graphNodes = state.graphNodes.map((node) => ({ ...node, status: "error" }));
      renderGraph();
      status.textContent = error.message;
    } finally {
      state.running = false;
    }
  }

  async function init() {
    loadSavedRuns();
    renderSavedRuns();
    $("workflowForm").addEventListener("submit", runWorkflow);
    window.addEventListener("resize", () => requestAnimationFrame(drawGraphEdges));
    await loadMethod();
  }

  init().catch((error) => {
    $("workflowStatus").textContent = error.message;
    $("methodMeta").textContent = "Failed to load method graph.";
  });
})();

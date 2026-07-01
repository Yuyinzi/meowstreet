(function () {
  const LOCAL_STORAGE_KEY = "methodWorkflowRuns.v1";

  const MAIN_PIPELINE = [
    "data_readiness",
    "liquidity_tradability",
    "bottom_up_fundamental_bias",
    "catalyst_window",
    "technical_timing",
    "risk_position_sizing",
    "final_synthesis",
  ];

  const SUPPORT_NODES = new Set([
    "instrument_identity",
    "macro_regime",
    "sector_theme_context",
    "time_horizon_fit",
    "portfolio_fit",
  ]);

  const DETACHED_NODES = new Set([
    "process_discipline",
  ]);

  const MAIN_PIPELINE_EDGES = new Set(
    MAIN_PIPELINE.slice(0, -1).map((from, i) => `${from}->${MAIN_PIPELINE[i + 1]}`)
  );

  const SUPPORT_EDGES = new Set([
    "instrument_identity->data_readiness",
    "macro_regime->sector_theme_context",
    "macro_regime->portfolio_fit",
    "sector_theme_context->bottom_up_fundamental_bias",
    "time_horizon_fit->catalyst_window",
    "liquidity_tradability->portfolio_fit",
    "portfolio_fit->risk_position_sizing",
    "portfolio_fit->final_synthesis",
  ]);

  const NODE_LAYOUT = {
    instrument_identity: { row: 2, col: 1, span: 1, role: "support" },
    data_readiness: { row: 2, col: 2, span: 1, role: "main" },
    macro_regime: { row: 3, col: 1, span: 1, role: "support" },
    liquidity_tradability: { row: 3, col: 2, span: 1, role: "main" },
    sector_theme_context: { row: 4, col: 1, span: 1, role: "support" },
    bottom_up_fundamental_bias: { row: 4, col: 2, span: 1, role: "main" },
    time_horizon_fit: { row: 5, col: 1, span: 1, role: "support" },
    catalyst_window: { row: 5, col: 2, span: 1, role: "main" },
    technical_timing: { row: 6, col: 2, span: 1, role: "main" },
    portfolio_fit: { row: 6, col: 3, span: 1, role: "support" },
    risk_position_sizing: { row: 7, col: 2, span: 1, role: "main" },
    process_discipline: { row: 2, col: 3, span: 1, role: "detached" },
    final_synthesis: { row: 8, col: 2, span: 1, role: "main" },
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

  function fmtSourceDocument(document) {
    return String(document || "")
      .replace(/^method_notes\//, "")
      .replace(/_method_notes\.md$/, "")
      .replace(/\.md$/, "");
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

  function nodeRole(nodeId) {
    if (MAIN_PIPELINE.includes(nodeId)) return "main";
    if (SUPPORT_NODES.has(nodeId)) return "support";
    if (DETACHED_NODES.has(nodeId)) return "detached";
    return "support";
  }

  function edgeKey(from, to) {
    return `${from}->${to}`;
  }

  function edgeRole(from, to) {
    const key = edgeKey(from, to);
    if (MAIN_PIPELINE_EDGES.has(key)) return "main";
    if (SUPPORT_EDGES.has(key)) return "support";
    const fromMain = MAIN_PIPELINE.includes(from);
    const toMain = MAIN_PIPELINE.includes(to);
    if (fromMain && toMain) return "main";
    if (SUPPORT_NODES.has(from) || SUPPORT_NODES.has(to)) return "support";
    return "cross";
  }

  function selectedEdgeState(from, to) {
    if (!state.selectedNodeId) return "";
    if (from === state.selectedNodeId) return "outgoing";
    if (to === state.selectedNodeId) return "connected";
    return "muted";
  }

  function entryNodeIds() {
    if (!state.method) return [];
    return state.method.workflow_nodes
      .filter((n) => !n.incoming_edges || n.incoming_edges.length === 0)
      .map((n) => n.id);
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
      source_refs: node.source_refs || [],
      evaluation_basis: node.evaluation_basis || node.method_basis || [],
      role: node.role || nodeRole(node.id || node.node_id),
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
        source_refs: node.source_refs || [],
        evaluation_basis: result.method_basis || {},
        role: nodeRole(node.id),
        layout: nodeLayout(node.id),
      };
    });
  }

  function rendermethodBasisItems(methodBasis) {
    if (Array.isArray(methodBasis)) {
      return methodBasis
        .map((ref) => `<li>${escapeHtml(fmtSourceDocument(ref.document) || ref.title || ref.check_id || "")} <span class="muted">${escapeHtml(ref.section || ref.status || "")}</span></li>`)
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

    const entryIds = entryNodeIds();
    graph.className = "workflow-graph";
    graph.innerHTML = `
      <div class="graph-start-bar" id="graphStartBar" aria-hidden="true">
        <span class="graph-paw">&#x1F43E;</span>
      </div>
      ${state.graphNodes
        .map((node) => {
          const layout = node.layout || nodeLayout(node.node_id);
          const selected = state.selectedNodeId === node.node_id ? " selected" : "";
          const connected = !state.selectedNodeId
            || node.node_id === state.selectedNodeId
            || (node.incoming_edges || []).includes(state.selectedNodeId)
            || (node.outgoing_edges || []).includes(state.selectedNodeId);
          const focusClass = state.selectedNodeId && !connected ? " dimmed" : "";
          return `
            <button
              type="button"
              class="graph-node graph-node-${escapeHtml(node.role)} status-${escapeHtml(node.status)}${selected}${focusClass}"
              data-node-id="${escapeHtml(node.node_id)}"
              title="${escapeHtml(node.title)} — ${escapeHtml(node.decision_question)}"
              style="grid-row:${layout.row}; grid-column:${layout.col} / span ${layout.span};"
            >
              <span class="node-label">${escapeHtml(node.title)}</span>
              <span class="node-status-dot" aria-hidden="true"></span>
            </button>
          `;
        })
        .join("")}
    `;

    graph.querySelectorAll(".graph-node").forEach((button) => {
      button.addEventListener("click", () => {
        if (state.selectedNodeId === button.dataset.nodeId) {
          state.selectedNodeId = null;
        } else {
          state.selectedNodeId = button.dataset.nodeId;
        }
        renderGraph();
        renderNodeDetail();
      });
    });

    const workspace = $("graphWorkspace");
    if (workspace) {
      workspace.classList.toggle("has-detail", Boolean(state.selectedNodeId));
    }

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

    function nodeRect(el) {
      const r = el.getBoundingClientRect();
      return {
        left: r.left - frameRect.left,
        top: r.top - frameRect.top,
        right: r.right - frameRect.left,
        bottom: r.bottom - frameRect.top,
        cx: r.left + r.width / 2 - frameRect.left,
        cy: r.top + r.height / 2 - frameRect.top,
      };
    }

    const startBar = graph.querySelector(".graph-start-bar");
    if (startBar) {
      const barRect = startBar.getBoundingClientRect();
      const sx = barRect.left + barRect.width / 2 - frameRect.left;
      const sy = barRect.top + barRect.height - frameRect.top;
      const entryIds = entryNodeIds();
      entryIds.forEach((entryId) => {
        const entryEl = nodeEls.get(entryId);
        if (!entryEl) return;
        const r = nodeRect(entryEl);
        const targetLayout = NODE_LAYOUT[entryId];
        const isOffAxis = targetLayout && targetLayout.col !== 2;
        if (isOffAxis) {
          const c1x = (sx + r.cx) / 2;
          const c1y = sy + 10;
          const c2y = r.top - 30;
          paths.push({
            d: `M ${sx} ${sy} C ${c1x} ${c1y}, ${c1x} ${c2y}, ${r.cx} ${r.top}`,
            role: "start",
            state: "",
          });
        } else {
          const c1y = sy + (r.top - sy) * 0.55;
          const c2y = r.top - (r.top - sy) * 0.15;
          paths.push({
            d: `M ${sx} ${sy} C ${sx} ${c1y}, ${r.cx} ${c2y}, ${r.cx} ${r.top}`,
            role: "start",
            state: "",
          });
        }
      });
    }

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

      const s = nodeRect(fromEl);
      const t = nodeRect(toEl);

      const gap = 12;
      let x1, y1, x2, y2, c1x, c1y, c2x, c2y;
      const dx = t.cx - s.cx;
      const dy = t.cy - s.cy;
      const fromLayout = NODE_LAYOUT[from];
      const toLayout = NODE_LAYOUT[to];
      const sameCol = fromLayout && toLayout && fromLayout.col === toLayout.col;
      const rowDiff = fromLayout && toLayout ? Math.abs(fromLayout.row - toLayout.row) : 0;

      if (sameCol && rowDiff === 1) {
        x1 = s.cx; y1 = s.bottom + gap * 0.4;
        x2 = t.cx; y2 = t.top - gap * 0.4;
        c1x = s.cx;
        c1y = y1 + Math.max(30, Math.abs(dy) * 0.35);
        c2x = t.cx;
        c2y = y2 - Math.max(30, Math.abs(dy) * 0.35);
      } else if (sameCol && rowDiff > 1) {
        const routeRight = fromLayout.col === 2;
        const startX = routeRight ? s.right + gap : s.left - gap;
        const endX = routeRight ? t.right : t.left;
        const arcOut = routeRight ? Math.max(s.right, t.right) + gap * 5 : Math.min(s.left, t.left) - gap * 5;
        x1 = startX; y1 = s.cy;
        x2 = endX; y2 = t.cy;
        c1x = arcOut;
        c1y = y1;
        c2x = arcOut;
        c2y = y2;
      } else if (!sameCol && rowDiff === 0) {
        if (dx > 0) {
          x1 = s.right + gap * 0.3; y1 = s.cy;
          x2 = t.left - gap * 0.3;  y2 = t.cy;
        } else {
          x1 = s.left - gap * 0.3; y1 = s.cy;
          x2 = t.right + gap * 0.3; y2 = t.cy;
        }
        c1x = (x1 + x2) / 2;
        c1y = y1;
        c2x = (x1 + x2) / 2;
        c2y = y2;
      } else {
        const corridorX = (s.cx + t.cx) / 2;
        if (dx > 0) {
          x1 = s.right + gap * 0.3; y1 = s.cy;
          x2 = t.left - gap * 0.3; y2 = t.cy;
        } else {
          x1 = s.left - gap * 0.3; y1 = s.cy;
          x2 = t.right + gap * 0.3; y2 = t.cy;
        }
        c1x = corridorX;
        c1y = y1;
        c2x = corridorX;
        c2y = y2;
      }

      const role = edgeRole(from, to);
      paths.push({
        d: `M ${x1} ${y1} C ${c1x} ${c1y}, ${c2x} ${c2y}, ${x2} ${y2}`,
        role,
        state: selectedEdgeState(from, to),
      });
    });

    svg.setAttribute("viewBox", `0 0 ${frame.clientWidth} ${frame.clientHeight}`);
    svg.innerHTML = `
      <defs>
        <marker id="arrowHeadStart" markerWidth="5" markerHeight="5" refX="4.5" refY="2.5" orient="auto">
          <path d="M0,0.5 L0,4.5 L4.5,2.5 z" />
        </marker>
        <marker id="arrowHeadMain" markerWidth="5" markerHeight="5" refX="4.5" refY="2.5" orient="auto">
          <path d="M0,0.5 L0,4.5 L4.5,2.5 z" />
        </marker>
        <marker id="arrowHeadSupport" markerWidth="5" markerHeight="5" refX="4.5" refY="2.5" orient="auto">
          <path d="M0,0.5 L0,4.5 L4.5,2.5 z" />
        </marker>
        <marker id="arrowHeadCross" markerWidth="5" markerHeight="5" refX="4.5" refY="2.5" orient="auto">
          <path d="M0,0.5 L0,4.5 L4.5,2.5 z" />
        </marker>
        <marker id="arrowHeadOutgoing" markerWidth="5" markerHeight="5" refX="4.5" refY="2.5" orient="auto">
          <path d="M0,0.5 L0,4.5 L4.5,2.5 z" />
        </marker>
      </defs>
      ${paths.map((path) => {
        const marker = path.state === "outgoing"
          ? "url(#arrowHeadOutgoing)"
          : `url(#arrowHead${path.role.charAt(0).toUpperCase()}${path.role.slice(1)})`;
        const stateClass = path.state ? ` graph-edge-${path.state}` : "";
        return `<path class="graph-edge graph-edge-${path.role}${stateClass}" d="${path.d}" marker-end="${marker}"></path>`;
      }).join("")}
    `;
  }

  function renderNodeDetail() {
    const section = $("nodeDetailSection");
    const panel = $("nodeDetailPanel");

    if (!state.selectedNodeId) {
      section.classList.remove("visible");
      return;
    }

    const node = state.graphNodes.find((item) => item.node_id === state.selectedNodeId);
    if (!node) {
      section.classList.remove("visible");
      return;
    }

    section.classList.add("visible");

    const longChecks = (node.long.checks || [])
      .map((check) => `<li><strong>${escapeHtml(check.status)}</strong> ${escapeHtml(check.title)}: ${escapeHtml(check.message)}</li>`)
      .join("");
    const shortChecks = (node.short.checks || [])
      .map((check) => `<li><strong>${escapeHtml(check.status)}</strong> ${escapeHtml(check.title)}: ${escapeHtml(check.message)}</li>`)
      .join("");
    const sourceRefs = rendermethodBasisItems(node.source_refs);
    const evaluationBasis = rendermethodBasisItems(node.evaluation_basis);
    const nextActions = [...(node.long.next_actions || []), ...(node.short.next_actions || [])]
      .map((action) => `<li>${escapeHtml(action)}</li>`)
      .join("");
    const missing = [...(node.long.missing_inputs || []), ...(node.short.missing_inputs || [])]
      .map((field) => `<li>${escapeHtml(field)}</li>`)
      .join("");

    panel.innerHTML = `
      <div class="node-detail-head">
        <div>
          <div class="node-detail-kicker">Node</div>
          <h3>${escapeHtml(node.title)}</h3>
        </div>
        <div class="node-detail-actions">
          <div class="status-chip status-${escapeHtml(node.status)}">${escapeHtml(fmtStatus(node.status))}</div>
          <button type="button" class="node-detail-close" id="nodeDetailClose" aria-label="Close details">&times;</button>
        </div>
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
        <details class="basis-details">
          <summary class="side-head basis-summary">
            <h4>Method Basis</h4>
            <span class="basis-toggle" aria-hidden="true"></span>
          </summary>
          <ul class="plain-list">${sourceRefs || "<li>No source refs</li>"}</ul>
        </details>
      </section>
      <section class="side-block">
        <div class="side-head">
          <h4>Evaluation Basis</h4>
        </div>
        <ul class="plain-list">${evaluationBasis || "<li>No checks yet</li>"}</ul>
      </section>
    `;

    const closeBtn = $("nodeDetailClose");
    if (closeBtn) {
      closeBtn.addEventListener("click", () => {
        state.selectedNodeId = null;
        renderGraph();
        renderNodeDetail();
      });
    }
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
    state.selectedNodeId = null;
    renderMethodMeta();
    renderGraph();
    renderNodeDetail();
  }

  async function runWorkflow(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const payload = buildPayload(form);
    state.running = true;

    state.graphNodes = state.graphNodes.map((node) => ({ ...node, status: "queued" }));
    renderGraph();
    await delay(120);
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
    } catch (error) {
      state.graphNodes = state.graphNodes.map((node) => ({ ...node, status: "error" }));
      renderGraph();
      console.error(error);
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
    console.error(error);
    $("methodMeta").textContent = "Failed to load method graph.";
  });
})();

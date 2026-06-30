# Method Workflow Decision System Design

## Purpose

Build a method-method trading decision system from `data/method_notes`. The system is not a methodra-style learning site and should not behave like raw RAG over method notes. It should behave like a trader using the method methodology: given a ticker and available observations, run all applicable workflow nodes, classify the ticker as a long/short candidate or not, and explain missing data and next steps with method-backed reasoning.

The runtime system should make deterministic classifications from structured nodes and checks. LLMs may be used offline to extract and organize the method methodology from notes, but the final ticker evaluation should not depend on an LLM silently deciding whether a ticker is good or bad.

## Current Context

The project already has:

- `data/method_notes/*.md`, with 41 method-note files using a consistent section structure.
- `scripts/build_method_rulebook.py`, which currently builds a flat seed rulebook.
- `traderdash/local_system_engine.py`, which evaluates a flat list of checks.
- `dashboard/method-system.*`, a first local UI for submitting manual observations and viewing stored evaluations.

The current rulebook is useful as scaffolding, but it is too flat. It does not yet represent the method as a trader workflow, learning progression, concept graph, or bidirectional long/short decision process.

## Method Note Structure

Each note has these repeated sections:

- `Key Points`
- `Learning Path / Reasoning Chain`
- `Concepts & Definitions`
- `Methodology / Workflow`
- `Examples & Applications`
- `Cautions / Common Mistakes`
- `Transcript Gaps / Incomplete Segments`
- `Actionable Checklist`

The extraction process should use each section for a different purpose:

- `Methodology / Workflow` and `Actionable Checklist`: primary source for workflow steps, required inputs, decision checks, and next actions.
- `Concepts & Definitions`: source for concept definitions and node vocabulary.
- `Cautions / Common Mistakes`: source for blocker rules, downgrade rules, and warnings.
- `Examples & Applications`: source for examples and explanation patterns, not hard rules unless repeated elsewhere.
- `Learning Path / Reasoning Chain`: source for method progression and dependencies between concepts.
- `Key Points`: source for summary validation and additional evidence.
- `Transcript Gaps / Incomplete Segments`: source for extraction confidence warnings, not runtime trading signals.

## Node Extraction Rule

A method concept becomes a workflow node only if it changes a trading decision.

Promote a concept into a node when it can answer at least one of:

- Should the system continue, wait, reject, or downgrade this ticker?
- Does it support a long bias, a short bias, neutral stance, or risk warning?
- Does it define required input before the ticker can become actionable?
- Does it affect position sizing, timing, portfolio fit, or trade structure?

Keep a concept as supporting documentation when it explains mindset or background but does not directly decide ticker status.

Examples of nodes:

- Instrument Identity
- Liquidity / Tradability
- Time Horizon Fit
- Macro Regime
- Sector / Theme Context
- Bottom-Up Fundamental Bias
- Catalyst Window
- Technical Timing
- Portfolio Fit
- Risk / Position Sizing
- Process Discipline
- Final Synthesis

Examples of supporting concepts:

- Competency hierarchy
- Self-sustainability
- Work ethic / conscientiousness
- Free information principle
- Retail vs professional mindset

These supporting concepts should still be attached to relevant nodes where they influence explanation, workflow discipline, or warnings.

## Bidirectional Evaluation

The workflow must support both long and short candidates from the beginning.

Every decision node should be able to produce long-side and short-side outputs:

```json
{
  "node_id": "bottom_up_fundamental_bias",
  "long": {
    "status": "pass",
    "evidence": [],
    "missing_inputs": [],
    "next_actions": []
  },
  "short": {
    "status": "fail",
    "evidence": [],
    "missing_inputs": [],
    "next_actions": []
  },
  "method_basis": []
}
```

Allowed side statuses:

- `pass`: evidence supports this side.
- `fail`: evidence argues against this side.
- `missing`: required data is absent.
- `mixed`: evidence is conflicting or incomplete but not absent.

Allowed directional effects:

- `long_supportive`
- `short_supportive`
- `neutral`
- `risk_warning`
- `blocker`

## Parallel Node Execution

The system should run all available nodes rather than forcing a strict sequence. Not every ticker will have enough data to complete every node.

For example, if only market data is available, the system can still evaluate:

- ticker identity
- liquidity
- price trend
- volume behavior
- relative strength
- basic technical timing

At the same time, it should mark unavailable areas as missing:

- bottom-up fundamentals
- catalyst window
- portfolio correlation
- borrow / shortability
- user-specific risk limits

The final classification should account for passed, failed, missing, mixed, and blocker outputs.

## Workflow Graph Model

The method system should be represented as a connected workflow graph, not only a form or flat checklist. Each graph node represents an executable method-method decision area. Edges represent methodology relationships and reasoning flow, not strict execution dependencies.

Example graph shape:

```text
Instrument Identity
  -> Liquidity / Tradability
  -> Macro Regime
  -> Sector / Theme Context
  -> Bottom-Up Fundamental Bias
  -> Catalyst Window
  -> Technical Timing
  -> Portfolio Fit
  -> Risk / Position Sizing
  -> Final Synthesis
```

Because nodes run in parallel when data is available, `Technical Timing` may complete even if `Bottom-Up Fundamental Bias` or `Catalyst Window` is missing. The edge still communicates that technical timing is not sufficient by itself under the method method.

Workflow node definitions should include:

- `id`
- `title`
- `decision_question`
- `description`
- `required_inputs`
- `criteria`
- `tool_hooks`
- `long_side_rules`
- `short_side_rules`
- `source_refs`
- `depends_on` or `incoming_edges`
- `points_to` or `outgoing_edges`

Node status lifecycle:

- `idle`: not started in the UI.
- `queued`: selected for execution.
- `running`: currently being evaluated or shown as running.
- `pass`: criteria support the side or node objective.
- `fail`: criteria argue against the side or node objective.
- `mixed`: evidence conflicts or contains warnings.
- `missing`: required data is unavailable.
- `blocked`: a hard rule prevents action.
- `error`: node execution failed unexpectedly.

For display, the UI should map statuses to stable visual states:

- gray: `idle` / `queued`
- blue: `running`
- green: `pass`
- red: `fail` / `blocked`
- yellow: `missing`
- orange: `mixed`

## V1 Graph Execution UX

The first implementation should not require live server push, websocket streaming, or incremental backend events.

V1 behavior:

1. User enters a ticker.
2. UI loads the workflow graph and shows all runnable nodes as `queued`.
3. User clicks run.
4. UI shows the relevant nodes as `running` for a short local transition.
5. UI sends one API request to the backend.
6. Backend evaluates all runnable nodes and returns the completed graph result.
7. UI replaces running states with final node statuses and renders final classification.

This gives the product the correct graph-based mental model without adding streaming complexity too early. Later versions can replace the local running transition with real incremental node events.

Manual input should become optional context and override data, not the primary interaction. The primary interaction is ticker-first graph execution.

## Final Classifications

The system should not default to direct `buy` or `sell` instructions. It should classify process readiness:

- `qualified_long_candidate`
- `qualified_short_candidate`
- `long_watchlist`
- `short_watchlist`
- `wait_for_timing`
- `insufficient_data`
- `conflicting_evidence`
- `reject`

The natural-language answer can include tactical interpretation, but it must preserve the distinction between:

- bias
- setup quality
- timing readiness
- risk permission
- final actionability

Example:

```text
XYZ has a possible long bias because fundamentals and sector context are supportive.
It is not entry-ready because catalyst and low-risk timing are missing.
Final status: long_watchlist / wait_for_timing.
```

## Method Method Graph Artifact

The flat `rulebook.v1.json` should evolve into a richer artifact, tentatively:

```text
data/local_system/method.v1.json
```

The artifact should include:

- `version`
- `generated_at`
- `source_documents`
- `concepts`
- `workflow_nodes`
- `node_checks`
- `decision_rules`
- `method_sources`
- `extraction_warnings`

Concept shape:

```json
{
  "id": "catalyst",
  "title": "Catalyst",
  "definition": "An event or expected development likely to move a stock within the trading horizon.",
  "supporting_only": false,
  "source_refs": []
}
```

Workflow node shape:

```json
{
  "id": "catalyst_window",
  "title": "Catalyst Window",
  "decision_question": "Is there a catalyst likely to move the stock within the 20-60 day trading horizon?",
  "description": "Checks whether the ticker has an event or expected development inside the trading mandate.",
  "required_inputs": ["known_catalysts", "earnings_date", "event_timeline"],
  "tool_hooks": ["earnings_calendar", "news_or_event_source"],
  "incoming_edges": ["bottom_up_fundamental_bias"],
  "outgoing_edges": ["technical_timing", "risk_position_sizing"],
  "long_evidence": ["positive catalyst", "price can move before report"],
  "short_evidence": ["negative catalyst", "deteriorating report expected"],
  "missing_if": ["no catalyst identified"],
  "hard_rules": [
    "A good company is not a trade idea without a catalyst.",
    "Avoid letting trades become investments beyond 60 days."
  ],
  "source_refs": []
}
```

Check shape:

```json
{
  "id": "catalyst_present",
  "node_id": "catalyst_window",
  "field": "catalysts.known",
  "operator": "exists",
  "side": "both",
  "required": true,
  "missing_message": "Catalyst detail is missing.",
  "fail_effect": "wait_for_research",
  "source_refs": []
}
```

## Extraction Pipeline

The offline extraction should use a constrained multi-pass process:

1. Parse every note into normalized sections.
2. Extract candidate concepts, methodology steps, hard rules, cautions, examples, and checklist items from each note.
3. Cluster repeated or related items across notes.
4. Promote clusters into workflow nodes only when they satisfy the node extraction rule.
5. Attach concepts, rules, examples, cautions, and source references to nodes.
6. Generate node checks and decision rules.
7. Validate the generated artifact for schema, source coverage, duplicate nodes, missing decision questions, and empty source refs.

The LLM can be used for steps 2-6, but it must return structured JSON. The script should validate the JSON and fail loudly on malformed output.

## Runtime Evaluation

Runtime evaluation should be deterministic:

1. Normalize ticker input and observations.
2. Load `method.v1.json`.
3. Run every node with available observations/tool data.
4. Produce side-specific node results.
5. Apply final decision rules.
6. Save the evaluation and raw observations.
7. Optionally use an LLM only to explain the deterministic result in natural language.

Runtime should support manually entered observations now and later tool-provided observations such as:

- yfinance market data
- earnings calendar
- fundamentals
- sector ETF relative strength
- macro dashboard data
- portfolio holdings and exposure
- borrow / shortability data

## UI Behavior

The method system UI should feel like a trader workflow console, not a method website.

The primary user flow:

1. Enter a ticker.
2. Add optional manual observations.
3. Run method workflow.
4. View node-level long/short outputs.
5. See final classification.
6. See missing inputs and next actions.
7. Save the case for later comparison.

The UI should make missing information useful, not embarrassing. Missing nodes should tell the user which data/tool is needed next.

## Separation From Trader Chat

Existing trader chat should not query method notes. Trader personalities should keep their own extracted style and references. The method workflow system is separate and can later have its own chat surface based only on the method method graph and evaluation results.

## Testing Strategy

Tests should cover:

- note section parser with all repeated sections
- extraction artifact schema validation
- node promotion rules on controlled fixtures
- deterministic node evaluation for long, short, missing, mixed, and blocker cases
- final classification rules
- server API endpoints
- UI payload shape and render safety where practical

The most important invariant: the same inputs and same method method version produce the same classification.

## Out Of Scope For First Implementation

- Fully automated real-time data coverage for every required input.
- Portfolio brokerage integration.
- Direct buy/sell recommendations.
- Replacing existing trader chat behavior.
- Using raw method-note RAG as the runtime decision source.

# AGENTS.md

## Project Overview

Meowstreet is a local-first method-based trade workflow system. Python 3.13, FastAPI, vanilla HTML/CSS/JS, pytest.

The project is based on:

- `2026-06-26-method-workflow-decision-system-design.md`
- `2026-06-26-method-workflow-graph.md`
- `2026-06-29-meowstreet-migration.md`

Use these design docs for product intent, but follow the current standalone `app/`, `static/`, `method_notes/`, and `data/local_system/` structure in this repo when implementing changes.

## Session Handoff

Before starting a new method chapter or resuming prior work, read `progress.md`. Its latest chapter section records the authoritative current method contract, dashboard interpretation, constraints, and handoff state; older entries are historical context only.

## Method Workflow Model

Meowstreet is not a learning site and should not behave like raw RAG over method notes. It is a ticker-first workflow console that evaluates a ticker through a deterministic method-method graph.

Runtime evaluation must:

- Load the versioned artifact at `data/local_system/method.v1.json`
- Normalize ticker and observation payloads
- Run all available workflow nodes in parallel where data exists
- Produce side-specific long/short node results
- Return missing inputs and next actions when data is absent
- Classify process readiness, not direct buy/sell instructions

Allowed final classifications include:

- `qualified_long_candidate`
- `qualified_short_candidate`
- `long_watchlist`
- `short_watchlist`
- `wait_for_timing`
- `insufficient_data`
- `conflicting_evidence`
- `reject`

The same inputs and the same method method version should produce the same classification. Do not add runtime logic that silently asks an LLM to decide whether a ticker is good or bad. LLMs may only be used offline to extract or organize method methodology before validating a structured artifact.

Method concepts become executable workflow nodes only when they affect trading decisions: continue, wait, reject, downgrade, support long/short bias, require input, affect timing, position sizing, portfolio fit, risk, or final synthesis. Concepts that are only mindset or background should remain supporting documentation attached to relevant nodes.

## Method Evolution

Method material is the seed methodology and source lineage, not an immutable runtime rulebook or required dashboard vocabulary.

Meowstreet may supersede an inherited rule with a system-owned method when the replacement:

- has an approved specification in `docs/superpowers/specs/`;
- defines its operational question, inputs, formula, window, thresholds, decision effect, and missing-data behavior;
- uses a new explicit method version;
- remains deterministic for the same inputs, observation date, and method version;
- includes boundary, missing-data, look-ahead, and presentation tests;
- distinguishes validated conclusions from hypotheses and supporting context;
- does not use an LLM at runtime.

Rules that claim to implement method guidance must preserve source fidelity. Rules identified as system-owned must cite their approved Meowstreet specification instead.

Dashboard copy presents the system's current method and conclusions. It does not need to expose method terminology or source gaps unless provenance is operationally relevant.

## Operational Product Rules

Meowstreet is a trading decision system, not a presentation of source material. Implement only information that helps a user assess the market, evaluate a ticker, or take the next step in the trade workflow.

Before implementing a concept or metric from the source notes, document its operational contract:

- The precise trading question it answers
- Whether it is a primary signal, confirmation, context, or supporting evidence
- The user decision or deterministic runtime result it can change
- The input, threshold, comparison, trend, or relationship explicitly supported by the source notes
- The behavior when the input is missing, stale, conflicting, or ambiguous

A concept is operational only when it can affect at least one of the following:

- Market regime or portfolio posture
- Long-side or short-side candidate support
- Continue, wait, reject, or downgrade decisions
- Entry or exit timing
- Risk, position sizing, or portfolio fit
- Process readiness, missing inputs, or next actions
- Ticker, industry, or sector research evidence used by a defined decision rule

Do not add runtime metrics, database fields, API fields, workflow nodes, or dashboard components solely because the source material mentions them. Historical illustrations, vocabulary, background theory, mindset guidance, worked examples, method-validation steps, and educational comparisons remain supporting documentation unless a deterministic decision rule consumes them.

Preserve source fidelity:

- Do not invent formulas, thresholds, weights, composite scores, correlations, mappings, or fallback rules while claiming source fidelity. System-owned rules require an approved, versioned Meowstreet method specification.
- Do not convert qualitative guidance into a numeric rule unless the source notes define that conversion
- Do not imply predictive certainty or causality that the source notes do not establish
- When guidance is incomplete, expose the raw evidence, mark the result ambiguous or insufficient, or require the missing input
- Keep the same inputs and method version deterministic; do not use an LLM to fill gaps at runtime

Dashboard output must favor decision clarity over source completeness. Summary cards should answer a small set of high-value market or ticker questions and provide a clear general impression. Put diagnostics, secondary evidence, provenance, and historical detail in focused detail views rather than expanding the summary card. Do not show a label, conclusion, or warning unless an approved method-derived or system-owned method supports its calculation and decision meaning.

Frontend additions must look and behave like existing Meowstreet interfaces. Reuse established design tokens, components, layouts, spacing, colors, typography, badges, labels, interaction patterns, responsive behavior, and accessibility conventions. Keep equivalent metrics and states visually consistent across dashboards. Create a new shared component only when the pattern is genuinely reusable.

Reuse stable parsing, normalization, persistence, API, and presentation helpers where their contracts match. Do not force different survey universes or domain semantics through a shared formula merely to reduce code. Create focused modules or frontend files when adding another responsibility would make an existing file unwieldy or mix unrelated concerns.

Tests for operational features must verify the metric-to-decision linkage, supported source rule, deterministic result, missing-data behavior, and the absence of invented logic. A successful import or rendered value alone does not establish that a feature belongs in the trading system.

## Method Data Sources

The source material for the method graph lives in `method_notes/*.md`. These markdown files use repeated sections:

- `Key Points`
- `Learning Path / Reasoning Chain`
- `Concepts & Definitions`
- `Methodology / Workflow`
- `Examples & Applications`
- `Cautions / Common Mistakes`
- `Transcript Gaps / Incomplete Segments`
- `Actionable Checklist`

Use `Methodology / Workflow` and `Actionable Checklist` as the primary source for workflow steps, required inputs, checks, and next actions. Use `Concepts & Definitions` for vocabulary, `Cautions / Common Mistakes` for blockers and warnings, and `Transcript Gaps / Incomplete Segments` only for extraction warnings.

Regenerate the method artifact with `python3 scripts/build_method.py` after changing method-note parsing, graph node definitions, checks, or method notes.

## GDP Relationship Source Caveat

For `data/source_material/Video 03/GDP_Correlations.xlsx`:

- Treat workbook-imported GDP relationship rows as the current dashboard source of truth.
- Recomputed lag metrics are verified against the workbook for all configured relationships.
- Recomputed quad metrics are verified against the workbook for US and Europe only.
- Do not treat China quad recomputation as supported. The workbook sheet `SZSC_CN_Quadnomial` is internally inconsistent with the China correlation sheet and reuses the Europe quad GDP level series.
- If future work needs China quad-derived metrics, resolve or replace the workbook source first rather than forcing parity logic into runtime code.

## Build / Run / Test Commands

### Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/build_method.py
```

### Run

```bash
.venv/bin/uvicorn app.api:app --reload --port 8797 --workers 2
```

### Run all tests

```bash
.venv/bin/pytest -q
```

### Run a single test file

```bash
.venv/bin/pytest tests/test_method_notes_parser.py -q
```

### Run a single test function

```bash
.venv/bin/pytest tests/test_method_notes_parser.py::test_parse_method_note_sections_extracts_known_sections -q
```

### Run tests matching a pattern

```bash
.venv/bin/pytest -k "parser" -q
```

### Check Python syntax (no test execution)

```bash
python3 -m py_compile app/api.py
```

### Check JS syntax

```bash
node --check static/method-system.js
```

### Build the method method artifact

```bash
python3 scripts/build_method.py
```

There is no linter (no ruff, flake8, mypy) configured for this project.

## Code Style Guidelines

### Imports

Group imports into three blocks separated by blank lines: stdlib, third-party, local (`app`). Always import individual names rather than modules.

```python
import json
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException

from app import workflow_engine
from app.method_schema import normalize_method_payload
```

Scripts in `scripts/` inject the project root into `sys.path` before importing:

```python
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import method_builder
```

### Naming

| Kind | Convention | Example |
|------|-----------|---------|
| Public functions | `snake_case` | `parse_method_note()`, `load_workflow_method()` |
| Private/helper functions | `_snake_case` | `_is_missing()`, `_compare()`, `_seed_nodes()` |
| Module-level constants | `UPPER_SNAKE_CASE` | `ROOT`, `SECTION_NAMES`, `GRAPH_EDGES` |
| Private constants | `_UPPER_SNAKE_CASE` | `_VALID_SIDES`, `_SYMBOL_RE`, `_FAIL_PRIORITY` |
| Compiled regex (module-level) | `UPPER_SNAKE_CASE` | `HEADING_RE`, `SOURCE_RE` |
| Variables | `snake_case` | `notes_dir`, `node_ids`, `checks_by_node` |
| Test functions | `test_<description>` | `test_parse_method_note_sections_extracts_known_sections` |
| Test helpers | `snake_case` | `valid_method()`, `method_payload()` |

Classes are allowed when they model stateful services, provider clients, fetchers, adapters, or immutable configuration that would otherwise be passed through many function calls. Prefer plain functions for simple transformations and DB operations.

### Error Handling

Raise `ValueError` for all validation failures with lowercase, f-string, descriptive messages. No error codes, no trailing punctuation:

```python
raise ValueError(f"workflow node {node_id} is duplicated")
raise ValueError("observation symbol is required")
```

In the API layer (app/api.py), re-wrap with `HTTPException` and chain with `from exc`:

```python
except ValueError as exc:
    raise HTTPException(status_code=400, detail=str(exc)) from exc
```

### Data Modeling

Runtime payloads, API responses, DB rows, and method-method artifacts remain plain nested dicts with string keys. Observation payloads use dotted-path keys (e.g., `"signals.trend"`, `"metrics.price"`). Access dict paths with a custom `_get_path()` resolver (see `workflow_engine.py`). Dataclasses may be used for configuration and internal value objects, but not as the public API payload format. Do not introduce ORM models for stored rows unless the project explicitly adopts one later.

The method artifact should include `version`, `generated_at`, `source_documents`, `concepts`, `workflow_nodes`, `node_checks`, `decision_rules`, and `extraction_warnings`. Workflow nodes should include decision questions, required inputs, criteria, tool hooks, source refs, incoming edges, and outgoing edges. Node checks should remain structured and deterministic.

### LLM Extraction Schemas

Use Pydantic v2 models to validate all LLM-generated JSON or AI extraction payloads before storing, transforming, or merging them into runtime data. Do not hand-roll schema validation for LLM output with ad hoc nested `if` checks. Pydantic models should use `ConfigDict(extra="forbid")`, constrained fields such as `Literal`, `Field`, and validators where useful, and should convert to plain dicts with `model_dump()` before crossing DB, API, or dashboard boundaries.

LLM extraction remains offline/import-time only unless explicitly approved. Runtime dashboard classification and ticker workflow decisions must stay deterministic.

### LLM Configuration

AI/LLM scripts must load model, API key, and base URL from `.env` through `app.llm`. Do not hardcode model names, API URLs, or provider-specific defaults in scripts. CLI flags may override `.env` only when explicitly provided by the user; their default must be `None` so environment configuration remains the source of truth.

### Filesystem

Always use `pathlib.Path`, never `os.path` or raw strings for paths:

```python
ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = ROOT / "static"
```

### Documentation

No docstrings. No inline comments. Rely entirely on descriptive function and variable names for clarity. The exception is `tests/conftest.py` which has one explanatory comment.

### Code Patterns

- **Guard clauses**: Validate inputs at the top of functions and raise early.
- **List comprehensions**: Use liberally for transformation and filtering.
- **`setdefault` for grouping**: E.g., `checks_by_node.setdefault(check["node_id"], []).append(...)`.
- **Private helpers do the real work**: Public functions are thin wrappers that compose private ones.
- **Module-level config**: Graph definitions, section names, valid sets, and regex patterns live at module top level.
- **No mutable default arguments**: Constants defined at module level are never mutated.

### Layered Responsibilities

Create and modify files according to one clear layer of responsibility:

- `app/data_sources/` fetches or parses external source material and returns normalized source payloads. It does not open SQLite connections, write database rows, build API responses, or render UI.
- `app/db/` owns schema, connections, persistence, transactions, and database reads. It does not fetch external sources, parse source files, implement CLI behavior, or render UI.
- `app/services/` coordinates focused application workflows across data-source and database adapters. It does not contain FastAPI route handling, frontend rendering, or CLI argument parsing.
- `app/tools/` contains pure deterministic calculations and presentation-neutral domain payload builders. It does not fetch network data, open database connections, or depend on request state.
- `app/api.py` validates request inputs, composes services/tools, converts validation failures to HTTP errors, and returns plain dict payloads. Keep persistence and source parsing out of routes.
- `scripts/` are thin CLI entry points: parse arguments, call one focused service or tool, print results, and set exit status. They do not contain SQL, source parsing, merge logic, or business calculations.
- `static/` renders API payloads and client-side interactions only. It does not reimplement backend classifications or calculate domain conclusions.

When a feature crosses layers, create focused files at these boundaries rather than adding unrelated responsibilities to an existing module. Reuse a shared helper only when its source universe and domain semantics match exactly.

### Tests

- One test file per source module: `tests/test_<module>.py`
- Use `tmp_path` fixture for filesystem-dependent tests
- Use `pytest.mark.parametrize` for contract/validation tests with lambda mutations
- Use `pytest.raises(ValueError, match=...)` to validate exception messages
- Test helper functions return expected payloads as dicts, not pytest fixtures
- Tests should be self-contained — create any needed markdown files inline in the test body
- API tests use `fastapi.testclient.TestClient`; do not start a server in tests
- The subprocess test in `test_method_builder.py` uses a hardcoded absolute `cwd=`

## Target File Structure

```
app/              # Python package (all application code)
  __init__.py
  method_notes_parser.py
  method_schema.py
  method_builder.py
  workflow_engine.py
  api.py
tests/                   # pytest tests
  conftest.py
  test_*.py
scripts/                 # CLI entry points
  build_method.py
static/                  # vanilla HTML/CSS/JS (served by FastAPI)
  method-system.html
  method-system.css
  method-system.js
method_notes/            # source markdown parsed by the builder
data/local_system/      # generated JSON method artifacts
```

### Outbound HTTP

All website requests in `app/` and `scripts/` must use `app.http_client.HttpClient`. Do not call `urllib.request.urlopen`, `urllib.request.urlretrieve`, or raw `httpx` request APIs directly. Parsing and domain error translation remain with the caller. Every new source that makes HTTP requests must test request construction and response/error contracts using `httpx.MockTransport`.

## Self-Containment Rule

This repo is a standalone product. Do not import from or reference `traderdash`, `serenity`, `scripts.server`, `chat_service`, `chat_index`, `x_curl`, `tweets`, `strategy`, or any external repos. All imports must resolve within `app/`, stdlib, or the three third-party packages listed in `requirements.txt`.

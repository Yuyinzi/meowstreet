# AGENTS.md

## Project Overview

Meowstreet is a local-first method-based trade workflow system. Python 3.13, FastAPI, vanilla HTML/CSS/JS, pytest.

The project is based on:

- `2026-06-26-method-workflow-decision-system-design.md`
- `2026-06-26-method-workflow-graph.md`
- `2026-06-29-meowstreet-migration.md`

Use these design docs for product intent, but follow the current standalone `app/`, `static/`, `method_notes/`, and `data/local_system/` structure in this repo when implementing changes.

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
.venv/bin/uvicorn app.api:app --reload --port 8797
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

## Self-Containment Rule

This repo is a standalone product. Do not import from or reference `traderdash`, `serenity`, `scripts.server`, `chat_service`, `chat_index`, `x_curl`, `tweets`, `strategy`, or any external repos. All imports must resolve within `app/`, stdlib, or the three third-party packages listed in `requirements.txt`.

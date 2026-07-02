# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Architecture Overview

Meowstreet is a **local-first method-based trade workflow system**. It evaluates a ticker through a deterministic method-method graph — no LLM calls at runtime. Python 3.13, FastAPI, vanilla HTML/CSS/JS, pytest.

### Data Pipeline (two modes)

**Direct build** (no LLM):
```
method_notes/*.md → method_notes_parser.py → method_builder.py → data/local_system/method.v1.json
```

**Hybrid (LLM extract → refine → synthesize):**
```
method_notes/*.md → extract_method.py → extraction_results/*.json
                                       → refine_method_extraction.py → extraction_refined/*.json
                                       → synthesize_method.py → synthesis/method.v1.json
```

The hybrid path uses the direct build as a seed, then overlays LLM-extracted nodes/indicators/checks. Refinement adds a second LLM pass for missing indicators, formulas, thresholds, and checks with audit/repair rounds.

### Data Directory Layout

```
data/local_system/
├── method.v1.json          Runtime artifact (loaded by api.py)
├── extraction_prompts/            Baseline LLM extraction prompts
├── extraction_results/            Baseline extraction JSON per note
├── extraction_refined/            Refined extraction JSON per note
├── refinement_prompts/            Refinement prompt files
├── refinement_repairs/            Initial patches + per-round repair JSON
├── refinement_audits/             Audit findings + final reports
└── synthesis/                     Final synthesized artifacts
```

### Module Map (`app/`)

| Module | Role |
|---|---|
| `api.py` | FastAPI routes — serve static files, expose method via GET, evaluate via POST |
| `method_notes_parser.py` | Parse `method_notes/*.md` into structured dicts with named sections |
| `method_builder.py` | Build the v1 method artifact from parsed notes (seed nodes, checks, concepts, edges) |
| `method_schema.py` | Validate and normalize the method artifact and observation payloads |
| `workflow_engine.py` | Deterministic runtime: evaluate checks against observations, compute node/side/final status |
| `method_indicators.py` | Compute derived fields (EPS skew, PE differential, volume ratio) from raw observations |
| `method_extraction_schema.py` | Validate LLM extraction outputs |
| `method_synthesizer.py` | Merge LLM extractions into the seed artifact for the hybrid pipeline |
| `llm.py` | OpenAI client config — loads `.env`, builds `AsyncOpenAI` client |

### Frontend (`static/`)

Single-page vanilla HTML/CSS/JS app served by FastAPI. User enters a ticker + optional context, the JS POSTs to `/api/method-system/workflow/evaluate`, renders a graph of nodes with pass/fail/missing/mixed status, detailed node inspector, and local-storage run history.

### Graph / Workflow Engine

The workflow graph has 12 nodes (defined in `method_builder.GRAPH_EDGES`):
`instrument_identity → liquidity_tradability → time_horizon_fit → macro_regime → sector_theme_context → bottom_up_fundamental_bias → catalyst_window → technical_timing → portfolio_fit → risk_position_sizing → process_discipline → final_synthesis`

Evaluation is purely deterministic — each node runs checks against the observation payload using operators like `exists`, `gte`, `contains`, `in`, etc. Each check has a `side` (long/short/both), `required` flag, and `fail_effect`. Results aggregate to per-side pass/fail/missing/reject status, then to a final classification:
- `qualified_long_candidate` / `qualified_short_candidate`
- `long_watchlist` / `short_watchlist`
- `wait_for_timing` / `insufficient_data` / `conflicting_evidence` / `reject`

### Runtime Rules

- Load the versioned artifact from `data/local_system/method.v1.json`
- Normalize ticker and observation payloads
- Run all workflow nodes in parallel where data exists
- Produce side-specific long/short node results
- Return missing inputs and next actions when data is absent
- Classify process readiness, never direct buy/sell instructions
- Same inputs + same method version = same classification every time
- **No LLM at runtime.** LLMs are only used offline for extraction/organization.

### Workflow Concepts

**Method method** = versioned artifact with `workflow_nodes`, `node_checks`, `concepts`, `decision_rules`, `source_documents`, `extraction_warnings`, `graph_review`.

**Observation payload** = structured user input with `symbol` and nested `observations` dict (dotted-path keys like `signals.trend`, `metrics.price`).

**Computed indicators** = derived fields computed server-side before evaluation (EPS skew, PE differential, abnormal volume ratio).

## Commands

### Setup
```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

### Build method method (direct path)
```bash
.venv/bin/python scripts/build_method.py
```

### Extract via LLM (hybrid path)
```bash
# Write prompts only (no API call):
.venv/bin/python scripts/extract_method.py --write-prompts-only

# Full extraction:
OPENAI_API_KEY=... .venv/bin/python scripts/extract_method.py \
  --model gpt-4.1-mini --max-output-tokens 12000 --workers 3 --skip-existing

# Common useful flags: --max-retries 4 --log-level INFO --prompts-dir ... --results-dir ...
```
Completions use temp-file + atomic replace. `finish_reason=length` is not retried — increase `--max-output-tokens` instead.

### Refine extractions (hybrid path, stage 2)
```bash
# Write prompts only:
.venv/bin/python scripts/refine_method_extraction.py --write-prompts-only

# Full refinement (adds missing indicators, formulas, checks):
OPENAI_API_KEY=... .venv/bin/python scripts/refine_method_extraction.py \
  --input-dir data/local_system/extraction_results \
  --output-dir data/local_system/extraction_refined \
  --max-audit-repair-rounds 2 --skip-existing --workers 2
```

### Synthesize from refined extractions (hybrid path, stage 3)
```bash
.venv/bin/python scripts/synthesize_method.py \
  --extractions-dir data/local_system/extraction_refined
```
Reads from `data/local_system/extraction_refined/`, writes to `data/local_system/synthesis/`.

### Full build pipeline (hybrid)
```bash
.venv/bin/python scripts/build_method.py --extractions-dir data/local_system/extraction_results --review-output data/local_system/synthesis/method_review.md
```

### Run server
```bash
.venv/bin/uvicorn app.api:app --reload --port 8797
```
Open http://127.0.0.1:8797

### Run tests
```bash
.venv/bin/pytest -q
.venv/bin/pytest tests/test_workflow_engine.py -q               # single file
.venv/bin/pytest tests/test_workflow_engine.py::test_name -q    # single function
.venv/bin/pytest -k "parser" -q                                        # match pattern
```

### Syntax checks (no test execution)
```bash
python3 -m py_compile app/api.py
node --check static/method-system.js
```

No linter (ruff, flake8, mypy) is configured.

## Code Style

### Imports
Three blocks, blank-line separated: stdlib → third-party → `app` imports. Import individual names, not modules.
```python
import json
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException

from app import workflow_engine
from app.method_schema import normalize_method_payload
```

Scripts in `scripts/` inject project root into `sys.path` before importing `app`:
```python
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
```

### Naming
| Kind | Convention | Example |
|---|---|---|
| Public functions | `snake_case` | `parse_method_note()`, `load_workflow_method()` |
| Private helpers | `_snake_case` | `_is_missing()`, `_compare()`, `_seed_nodes()` |
| Module-level constants | `UPPER_SNAKE_CASE` | `ROOT`, `SECTION_NAMES`, `GRAPH_EDGES` |
| Private constants | `_UPPER_SNAKE_CASE` | `_VALID_SIDES`, `_SYMBOL_RE`, `_FAIL_PRIORITY` |
| Compiled regex | `UPPER_SNAKE_CASE` | `HEADING_RE`, `SOURCE_RE` |
| Test functions | `test_<description>` | `test_parse_method_note_sections_extracts_known_sections` |
| Test helpers | `snake_case` | `valid_method()`, `method_payload()` |
| All variables | `snake_case` | `notes_dir`, `node_ids`, `checks_by_node` |

### Patterns
- **Classes are allowed for services and integrations.** Use classes when they model stateful services, provider clients, fetchers, adapters, or immutable configuration that would otherwise be passed through many function calls. Prefer plain functions for simple transformations and DB operations.
- **No docstrings, no inline comments.** Rely entirely on descriptive function/variable names.
- **Guard clauses** — validate at the top, raise early.
- **List comprehensions** — use liberally for transformation/filtering.
- **`setdefault` for grouping** — `checks_by_node.setdefault(check["node_id"], []).append(...)`.
- **Module-level config** — graph edges, section names, valid sets, regex patterns at module top.
- **No mutable default arguments.**
- **`pathlib.Path` everywhere** — never `os.path` or raw string paths.
- **Private helpers do the real work** — public functions are thin wrappers.

### Data Modeling
Runtime payloads, API responses, DB rows, and method-method artifacts remain plain nested dicts with string keys. Observation payloads use dotted-path keys. Access with the `_get_path()` resolver in `workflow_engine.py`. Dataclasses may be used for configuration and internal value objects, but not as the public API payload format. Do not introduce ORM models for stored rows unless the project explicitly adopts one later.

### Error Handling
Raise `ValueError` for validation failures — lowercase, f-string, descriptive, no trailing punctuation:
```python
raise ValueError(f"workflow node {node_id} is duplicated")
```
In `api.py`, re-wrap with `HTTPException(400)` chaining from `exc`.

### Tests
- One test file per source module: `tests/test_<module>.py`.
- Use `tmp_path` fixture for filesystem tests.
- Use `pytest.mark.parametrize` for contract/validation tests.
- Use `pytest.raises(ValueError, match=...)` for exception messages.
- Test helpers return plain dicts, not pytest fixtures.
- API tests use `fastapi.testclient.TestClient` — no server process needed.
- Tests should be self-contained (inline markdown, not files on disk).

## Self-Containment Rule

This repo is standalone. Do not import from or reference `traderdash`, `serenity`, `scripts.server`, `chat_service`, `chat_index`, `x_curl`, `tweets`, `strategy`, or any external repos. All imports resolve within `app/`, stdlib, or the three third-party packages: `fastapi`, `uvicorn[standard]`, `pytest`, `httpx`, `openai`, `python-dotenv`.

## Key Design Docs

- `2026-06-26-method-workflow-decision-system-design.md`
- `2026-06-26-method-workflow-graph.md`
- `2026-06-29-meowstreet-migration.md`
- `docs/superpowers/plans/2026-06-30-hybrid-method-synthesis-taxonomy.md`

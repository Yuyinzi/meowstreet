# AGENTS.md

## Project Overview

Meowstreet is a local-first method-based trade workflow system. Python 3.13, FastAPI, vanilla HTML/CSS/JS, pytest.

## Build / Run / Test Commands

### Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/build_method.py
```

### Run

```bash
PYTHONPATH=src .venv/bin/uvicorn app.api:app --reload --port 8797
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
python3 -m py_compile src/app/api.py
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
sys.path.insert(0, str(ROOT / "src"))

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

No classes are used anywhere. The codebase is purely functional.

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

All data is nested dicts with string keys. No dataclasses, namedtuples, or ORM models. Observation payloads use dotted-path keys (e.g., `"signals.trend"`, `"metrics.price"`). Access dict paths with a custom `_get_path()` resolver (see `workflow_engine.py`).

### Filesystem

Always use `pathlib.Path`, never `os.path` or raw strings for paths:

```python
ROOT = Path(__file__).resolve().parents[2]
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
src/
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

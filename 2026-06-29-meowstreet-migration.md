# Meowstreet Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate the standalone method-based trade workflow system into `/Users/littlemay/work/meowstreet/meowstreet` as a smaller local-first repo.

**Architecture:** Treat Meowstreet as a clean product, not a sliced copy of Serenity Dashboard. Copy only the method-note parser, method method schema/builder, deterministic workflow engine, generated method artifact, method notes, a minimal FastAPI API, and the graph UI. Do not migrate X ingestion, trader chat, tweet RAG, strategy user surfaces, Serenity SQLite data, or dashboard pages unrelated to the method workflow.

**Tech Stack:** Python 3.13, FastAPI, Uvicorn, vanilla HTML/CSS/JS, pytest, local JSON artifacts, local markdown method notes.

---

## Source And Target

Source repo:

```text
/Users/littlemay/work/serenity-dashboard/.worktrees/method-workflow-graph
```

Target repo:

```text
/Users/littlemay/work/meowstreet/meowstreet
```

The target repo already contains:

```text
method_notes/*.md
.git/
```

Use `/Users/littlemay/work/meowstreet/meowstreet` as the repo root. The outer `/Users/littlemay/work/meowstreet` directory is not the app root.

## Migration Scope

Migrate:

- Method note markdown under `method_notes/`.
- Method method graph artifact generation.
- Deterministic long/short workflow graph evaluation.
- Minimal API:
  - `GET /api/method-system/method`
  - `POST /api/method-system/workflow/evaluate`
- Static graph console:
  - `/`
  - `/method-system.html`
  - `/method-system.css`
  - `/method-system.js`
- Tests for parser, schema, builder, workflow engine, and API.

Do not migrate:

- `scripts/ingest.py`
- `scripts/server.py`
- `scripts/chat_service.py`
- `scripts/chat_index.py`
- X curl files, raw X JSON, tweet SQLite DB, prices, strategy users, trader chat UI, or trader skill/RAG files.
- Old flat rulebook engine/store unless a later product decision needs saved evaluations.

## Target File Structure

Create this structure in `/Users/littlemay/work/meowstreet/meowstreet`:

```text
README.md
requirements.txt
pyproject.toml
.gitignore
method_notes/*.md
data/local_system/method.v1.json
meowstreet/__init__.py
meowstreet/method_notes_parser.py
meowstreet/method_schema.py
meowstreet/method_builder.py
meowstreet/workflow_engine.py
meowstreet/api.py
scripts/build_method.py
static/method-system.html
static/method-system.css
static/method-system.js
tests/test_method_notes_parser.py
tests/test_method_schema.py
tests/test_method_builder.py
tests/test_workflow_engine.py
tests/test_api.py
```

---

### Task 1: Bootstrap The Meowstreet Repo

**Files:**
- Create: `/Users/littlemay/work/meowstreet/meowstreet/README.md`
- Create: `/Users/littlemay/work/meowstreet/meowstreet/requirements.txt`
- Create: `/Users/littlemay/work/meowstreet/meowstreet/pyproject.toml`
- Create: `/Users/littlemay/work/meowstreet/meowstreet/.gitignore`
- Create: `/Users/littlemay/work/meowstreet/meowstreet/meowstreet/__init__.py`
- Create: `/Users/littlemay/work/meowstreet/meowstreet/tests/conftest.py`

- [ ] **Step 1: Check target repo status**

Run:

```bash
cd /Users/littlemay/work/meowstreet/meowstreet
git status --short --branch
```

Expected: clean or only the already copied `method_notes/` files. If there are unrelated user changes, do not revert them.

- [ ] **Step 2: Create package and test directories**

Run:

```bash
cd /Users/littlemay/work/meowstreet/meowstreet
mkdir -p meowstreet tests data/local_system static scripts
touch meowstreet/__init__.py
```

- [ ] **Step 3: Add project metadata**

Create `pyproject.toml`:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
```

Create `requirements.txt`:

```text
fastapi>=0.115,<1
uvicorn[standard]>=0.30,<1
pytest>=8,<9
httpx>=0.27,<1
```

Create `.gitignore`:

```gitignore
__pycache__/
*.pyc
.pytest_cache/
.venv/
data/*.sqlite
.DS_Store
```

Create `README.md`:

```markdown
# Meowstreet

Local-first method-based trade workflow system.

Meowstreet evaluates a ticker through a method-derived workflow graph. It is separate from Serenity Dashboard and does not use trader tweets, trader chat, X ingestion, or trader-specific RAG.

## Run

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/build_method.py
.venv/bin/uvicorn meowstreet.api:app --reload --port 8797
```

Open:

```text
http://127.0.0.1:8797
```

## Test

```bash
.venv/bin/pytest -q
```
```

- [ ] **Step 4: Add empty test config**

Create `tests/conftest.py`:

```python
# pytest discovers the local package via pyproject.toml pythonpath.
```

- [ ] **Step 5: Verify bootstrap**

Run:

```bash
cd /Users/littlemay/work/meowstreet/meowstreet
python3 -m py_compile meowstreet/__init__.py
```

Expected: exit code `0`.

- [ ] **Step 6: Commit bootstrap**

Run:

```bash
cd /Users/littlemay/work/meowstreet/meowstreet
git add README.md requirements.txt pyproject.toml .gitignore meowstreet/__init__.py tests/conftest.py
git commit -m "chore: bootstrap meowstreet app"
```

---

### Task 2: Migrate Method Note Parser

**Files:**
- Create: `/Users/littlemay/work/meowstreet/meowstreet/meowstreet/method_notes_parser.py`
- Create: `/Users/littlemay/work/meowstreet/meowstreet/tests/test_method_notes_parser.py`

- [ ] **Step 1: Write parser tests**

Create `tests/test_method_notes_parser.py`:

```python
from meowstreet import method_notes_parser


def test_parse_method_note_sections_extracts_known_sections(tmp_path):
    note = tmp_path / "P1 The Framework_method_notes.md"
    note.write_text(
        """# Method Notes: P1 The Framework -en

Source: `P1 The Framework -en.txt`

## Key Points
- [00:00:01] Method introduction.

## Learning Path / Reasoning Chain
1. Introduce the framework.

## Concepts & Definitions
- **Catalyst**: Event likely to move a stock.

## Methodology / Workflow
1. Generate a fundamental bias.

## Examples & Applications
- Example content.

## Cautions / Common Mistakes
- Good company does not equal good trade idea.

## Transcript Gaps / Incomplete Segments
- None flagged.

## Actionable Checklist
- [ ] Identify catalyst inside 20-60 days.
""",
        encoding="utf-8",
    )

    parsed = method_notes_parser.parse_method_note(note, root=tmp_path)

    assert parsed["path"] == "P1 The Framework_method_notes.md"
    assert parsed["title"] == "Method Notes: P1 The Framework -en"
    assert parsed["source"] == "P1 The Framework -en.txt"
    assert "Catalyst" in parsed["sections"]["Concepts & Definitions"]
    assert parsed["section_order"] == [
        "Key Points",
        "Learning Path / Reasoning Chain",
        "Concepts & Definitions",
        "Methodology / Workflow",
        "Examples & Applications",
        "Cautions / Common Mistakes",
        "Transcript Gaps / Incomplete Segments",
        "Actionable Checklist",
    ]


def test_parse_method_notes_dir_returns_sorted_documents(tmp_path):
    (tmp_path / "P2 B_method_notes.md").write_text("# B\n\n## Key Points\n- b\n", encoding="utf-8")
    (tmp_path / "P1 A_method_notes.md").write_text("# A\n\n## Key Points\n- a\n", encoding="utf-8")

    docs = method_notes_parser.parse_method_notes_dir(tmp_path, root=tmp_path)

    assert [doc["title"] for doc in docs] == ["A", "B"]
    assert all(doc["sha256"] for doc in docs)


def test_parse_method_note_preserves_transcript_gap_section(tmp_path):
    note = tmp_path / "P6 Example_method_notes.md"
    note.write_text(
        "# Example\n\n## Transcript Gaps / Incomplete Segments\n- Possible missing auto-translation.\n",
        encoding="utf-8",
    )

    parsed = method_notes_parser.parse_method_note(note, root=tmp_path)

    assert "Possible missing auto-translation" in parsed["sections"]["Transcript Gaps / Incomplete Segments"]
```

- [ ] **Step 2: Run parser tests and verify failure**

Run:

```bash
cd /Users/littlemay/work/meowstreet/meowstreet
python3 -m pytest tests/test_method_notes_parser.py -q
```

Expected: fail because `meowstreet.method_notes_parser` does not exist.

- [ ] **Step 3: Copy and retarget parser implementation**

Copy the implementation from:

```text
/Users/littlemay/work/serenity-dashboard/.worktrees/method-workflow-graph/traderdash/method_notes_parser.py
```

to:

```text
/Users/littlemay/work/meowstreet/meowstreet/meowstreet/method_notes_parser.py
```

The file should import only Python standard library modules.

- [ ] **Step 4: Run parser tests and verify pass**

Run:

```bash
cd /Users/littlemay/work/meowstreet/meowstreet
python3 -m pytest tests/test_method_notes_parser.py -q
```

Expected: `3 passed`.

- [ ] **Step 5: Commit parser**

Run:

```bash
cd /Users/littlemay/work/meowstreet/meowstreet
git add meowstreet/method_notes_parser.py tests/test_method_notes_parser.py
git commit -m "feat: parse method notes"
```

---

### Task 3: Migrate Method Method Schema

**Files:**
- Create: `/Users/littlemay/work/meowstreet/meowstreet/meowstreet/method_schema.py`
- Create: `/Users/littlemay/work/meowstreet/meowstreet/tests/test_method_schema.py`

- [ ] **Step 1: Write schema tests**

Create `tests/test_method_schema.py`:

```python
import pytest

from meowstreet import method_schema


def valid_method():
    return {
        "version": " v1 ",
        "generated_at": "2026-06-29T00:00:00+00:00",
        "source_documents": [{"path": "", "title": "P1"}],
        "concepts": [],
        "workflow_nodes": [
            {
                "id": "instrument_identity",
                "title": "Instrument Identity",
                "decision_question": "Is this tradable?",
                "description": "Confirms symbol identity.",
                "required_inputs": ["symbol"],
                "criteria": ["Symbol is present."],
                "tool_hooks": ["symbol_profile"],
                "incoming_edges": [],
                "outgoing_edges": ["final_synthesis"],
                "source_refs": [{"document": "", "section": "Methodology / Workflow"}],
            },
            {
                "id": "final_synthesis",
                "title": "Final Synthesis",
                "decision_question": "What is the decision?",
                "description": "Aggregates node outputs.",
                "required_inputs": [],
                "criteria": ["Combine checks."],
                "tool_hooks": [],
                "incoming_edges": ["instrument_identity"],
                "outgoing_edges": [],
                "source_refs": [{"document": "", "section": "Methodology / Workflow"}],
            },
        ],
        "node_checks": [
            {
                "id": "symbol_present",
                "node_id": "instrument_identity",
                "title": "Symbol present",
                "field": "symbol",
                "operator": "exists",
                "side": "both",
                "required": True,
                "missing_message": "Symbol is missing.",
                "fail_effect": "reject",
                "source_refs": [{"document": "", "section": "Actionable Checklist"}],
            }
        ],
        "decision_rules": [],
        "extraction_warnings": [],
    }


def test_normalize_method_payload_trims_version_and_keeps_graph():
    payload = method_schema.normalize_method_payload(valid_method())

    assert payload["version"] == "v1"
    assert payload["workflow_nodes"][0]["id"] == "instrument_identity"
    assert payload["node_checks"][0]["side"] == "both"


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda p: p.pop("version"), "method method version is required"),
        (lambda p: p.__setitem__("workflow_nodes", []), "workflow_nodes must not be empty"),
        (lambda p: p.__setitem__("node_checks", []), "node_checks must not be empty"),
        (lambda p: p["workflow_nodes"][0].pop("decision_question"), "workflow node instrument_identity decision_question is required"),
        (lambda p: p["workflow_nodes"][0].__setitem__("outgoing_edges", ["missing_node"]), "workflow node instrument_identity outgoing_edges references unknown node"),
        (lambda p: p["node_checks"][0].__setitem__("side", "bad"), "node check symbol_present side is invalid"),
        (lambda p: p["node_checks"][0].__setitem__("node_id", "missing_node"), "node check symbol_present references unknown node"),
    ],
)
def test_normalize_method_payload_validates_contract(mutation, message):
    payload = valid_method()
    mutation(payload)

    with pytest.raises(ValueError, match=message):
        method_schema.normalize_method_payload(payload)


def test_normalize_graph_observation_payload_requires_symbol_and_observations():
    normalized = method_schema.normalize_graph_observation_payload(
        {"symbol": " nvda ", "observations": {"metrics": {"price": 100}}}
    )

    assert normalized["symbol"] == "NVDA"
    assert normalized["observations"]["metrics"]["price"] == 100


def test_normalize_graph_observation_payload_rejects_bad_symbol():
    with pytest.raises(ValueError, match="observation symbol is invalid"):
        method_schema.normalize_graph_observation_payload({"symbol": "bad symbol", "observations": {}})
```

- [ ] **Step 2: Run schema tests and verify failure**

Run:

```bash
cd /Users/littlemay/work/meowstreet/meowstreet
python3 -m pytest tests/test_method_schema.py -q
```

Expected: fail because `meowstreet.method_schema` does not exist.

- [ ] **Step 3: Copy and retarget schema implementation**

Copy:

```text
/Users/littlemay/work/serenity-dashboard/.worktrees/method-workflow-graph/traderdash/method_schema.py
```

to:

```text
/Users/littlemay/work/meowstreet/meowstreet/meowstreet/method_schema.py
```

No import rename is needed if the source file imports only standard library modules.

- [ ] **Step 4: Run schema tests and verify pass**

Run:

```bash
cd /Users/littlemay/work/meowstreet/meowstreet
python3 -m pytest tests/test_method_schema.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit schema**

Run:

```bash
cd /Users/littlemay/work/meowstreet/meowstreet
git add meowstreet/method_schema.py tests/test_method_schema.py
git commit -m "feat: add method method schema"
```

---

### Task 4: Migrate Method Builder And Artifact Generation

**Files:**
- Create: `/Users/littlemay/work/meowstreet/meowstreet/meowstreet/method_builder.py`
- Create: `/Users/littlemay/work/meowstreet/meowstreet/scripts/build_method.py`
- Create: `/Users/littlemay/work/meowstreet/meowstreet/tests/test_method_builder.py`
- Create: `/Users/littlemay/work/meowstreet/meowstreet/data/local_system/method.v1.json`

- [ ] **Step 1: Write builder tests**

Create `tests/test_method_builder.py`:

```python
import json
import subprocess
import sys

from meowstreet import method_builder
from meowstreet import method_schema


def test_build_method_payload_contains_connected_workflow(tmp_path):
    notes_dir = tmp_path / "method_notes"
    notes_dir.mkdir()
    (notes_dir / "P1 The Framework_method_notes.md").write_text(
        """# Method Notes: P1 The Framework -en

Source: `P1 The Framework -en.txt`

## Concepts & Definitions
- **Catalyst**: An event likely to move a stock.

## Methodology / Workflow
1. Trade ideas require fundamental bias, catalyst, timing, structure, and risk management.

## Actionable Checklist
- [ ] Identify catalysts expected within 20-60 days.
""",
        encoding="utf-8",
    )

    payload = method_builder.build_method_payload(notes_dir=notes_dir, version="v1", root=tmp_path)
    normalized = method_schema.normalize_method_payload(payload)

    node_ids = {node["id"] for node in normalized["workflow_nodes"]}
    assert {"instrument_identity", "catalyst_window", "technical_timing", "final_synthesis"} <= node_ids
    assert any(node["outgoing_edges"] for node in normalized["workflow_nodes"])
    assert any(check["node_id"] == "catalyst_window" for check in normalized["node_checks"])
    assert normalized["source_documents"][0]["path"].startswith("method_notes/")


def test_build_method_records_gap_warnings(tmp_path):
    notes_dir = tmp_path / "method_notes"
    notes_dir.mkdir()
    (notes_dir / "P6 Gap_method_notes.md").write_text(
        """# Method Notes: P6 Gap -en

## Transcript Gaps / Incomplete Segments
- Possible missing middle section.
""",
        encoding="utf-8",
    )

    payload = method_builder.build_method_payload(notes_dir=notes_dir, version="v1", root=tmp_path)

    assert payload["extraction_warnings"] == [
        {
            "document": "",
            "section": "Transcript Gaps / Incomplete Segments",
            "message": "Possible missing middle section.",
        }
    ]


def test_build_method_script_writes_artifact(tmp_path):
    notes_dir = tmp_path / "method_notes"
    notes_dir.mkdir()
    (notes_dir / "P1 The Framework_method_notes.md").write_text(
        "# Method Notes: P1 The Framework -en\n\n## Methodology / Workflow\n- Catalyst and timing.\n",
        encoding="utf-8",
    )
    output = tmp_path / "data" / "local_system" / "method.v1.json"

    subprocess.run(
        [
            sys.executable,
            "scripts/build_method.py",
            "--notes-dir",
            str(notes_dir),
            "--output",
            str(output),
        ],
        cwd="/Users/littlemay/work/meowstreet/meowstreet",
        check=True,
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["version"] == "v1"
    assert payload["workflow_nodes"]
```

- [ ] **Step 2: Run builder tests and verify failure**

Run:

```bash
cd /Users/littlemay/work/meowstreet/meowstreet
python3 -m pytest tests/test_method_builder.py -q
```

Expected: fail because builder and script do not exist.

- [ ] **Step 3: Copy and retarget builder implementation**

Copy:

```text
/Users/littlemay/work/serenity-dashboard/.worktrees/method-workflow-graph/traderdash/method_builder.py
```

to:

```text
/Users/littlemay/work/meowstreet/meowstreet/meowstreet/method_builder.py
```

Then update imports in the copied file:

```python
from meowstreet import method_notes_parser
from meowstreet.method_schema import normalize_method_payload
```

- [ ] **Step 4: Add artifact build script**

Create `scripts/build_method.py`:

```python
#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from meowstreet import method_builder

DEFAULT_NOTES_DIR = ROOT / "method_notes"
DEFAULT_OUTPUT = ROOT / "data" / "local_system" / "method.v1.json"


def build_arg_parser():
    parser = argparse.ArgumentParser(description="Build the method workflow method artifact.")
    parser.add_argument("--notes-dir", default=str(DEFAULT_NOTES_DIR))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--version", default="v1")
    return parser


def main(argv=None):
    args = build_arg_parser().parse_args(argv)
    payload = method_builder.build_method_payload(
        notes_dir=args.notes_dir,
        version=args.version,
        root=ROOT,
    )
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(destination),
                "version": payload["version"],
                "source_documents": len(payload["source_documents"]),
                "workflow_nodes": len(payload["workflow_nodes"]),
                "node_checks": len(payload["node_checks"]),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run builder tests and verify pass**

Run:

```bash
cd /Users/littlemay/work/meowstreet/meowstreet
python3 -m pytest tests/test_method_builder.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Generate real method artifact**

Run:

```bash
cd /Users/littlemay/work/meowstreet/meowstreet
python3 scripts/build_method.py
python3 -m json.tool data/local_system/method.v1.json >/dev/null
```

Expected: build command prints JSON with `workflow_nodes` and `node_checks`; `json.tool` exits `0`.

- [ ] **Step 7: Commit builder and artifact**

Run:

```bash
cd /Users/littlemay/work/meowstreet/meowstreet
git add meowstreet/method_builder.py scripts/build_method.py tests/test_method_builder.py data/local_system/method.v1.json
git commit -m "feat: build method workflow method"
```

---

### Task 5: Migrate Workflow Engine

**Files:**
- Create: `/Users/littlemay/work/meowstreet/meowstreet/meowstreet/workflow_engine.py`
- Create: `/Users/littlemay/work/meowstreet/meowstreet/tests/test_workflow_engine.py`

- [ ] **Step 1: Write workflow engine tests**

Create `tests/test_workflow_engine.py`:

```python
from meowstreet import workflow_engine


def method_payload():
    return {
        "version": "v1",
        "source_documents": [],
        "concepts": [],
        "workflow_nodes": [
            {
                "id": "instrument_identity",
                "title": "Instrument Identity",
                "decision_question": "Is this tradable?",
                "description": "Confirms symbol identity.",
                "required_inputs": ["symbol"],
                "criteria": ["Symbol is present."],
                "tool_hooks": [],
                "incoming_edges": [],
                "outgoing_edges": ["technical_timing"],
                "source_refs": [],
            },
            {
                "id": "technical_timing",
                "title": "Technical Timing",
                "decision_question": "Is timing supportive?",
                "description": "Checks long and short timing.",
                "required_inputs": ["signals.trend"],
                "criteria": ["Long wants uptrend; short wants downtrend."],
                "tool_hooks": [],
                "incoming_edges": ["instrument_identity"],
                "outgoing_edges": ["final_synthesis"],
                "source_refs": [],
            },
            {
                "id": "final_synthesis",
                "title": "Final Synthesis",
                "decision_question": "What is the decision?",
                "description": "Aggregates outputs.",
                "required_inputs": [],
                "criteria": ["Aggregate checks."],
                "tool_hooks": [],
                "incoming_edges": ["technical_timing"],
                "outgoing_edges": [],
                "source_refs": [],
            },
        ],
        "node_checks": [
            {
                "id": "symbol_present",
                "node_id": "instrument_identity",
                "title": "Symbol present",
                "field": "symbol",
                "operator": "exists",
                "side": "both",
                "required": True,
                "missing_message": "Symbol missing.",
                "fail_effect": "reject",
                "source_refs": [],
            },
            {
                "id": "long_trend",
                "node_id": "technical_timing",
                "title": "Long trend",
                "field": "signals.trend",
                "operator": "equals",
                "value": "up",
                "side": "long",
                "required": False,
                "missing_message": "Trend missing.",
                "fail_effect": "wait_for_timing",
                "source_refs": [],
            },
            {
                "id": "short_trend",
                "node_id": "technical_timing",
                "title": "Short trend",
                "field": "signals.trend",
                "operator": "equals",
                "value": "down",
                "side": "short",
                "required": False,
                "missing_message": "Trend missing.",
                "fail_effect": "wait_for_timing",
                "source_refs": [],
            },
        ],
        "decision_rules": [],
        "extraction_warnings": [],
    }


def test_evaluate_workflow_method_returns_long_watchlist():
    result = workflow_engine.evaluate_workflow_method(
        method_payload(),
        {"symbol": "NVDA", "observations": {"signals": {"trend": "up"}}},
    )

    assert result["symbol"] == "NVDA"
    assert result["final_status"] == "long_watchlist"
    assert result["nodes"][1]["long"]["status"] == "pass"
    assert result["nodes"][1]["short"]["status"] == "fail"


def test_evaluate_workflow_method_returns_short_watchlist():
    result = workflow_engine.evaluate_workflow_method(
        method_payload(),
        {"symbol": "NVDA", "observations": {"signals": {"trend": "down"}}},
    )

    assert result["final_status"] == "short_watchlist"


def test_evaluate_workflow_method_returns_wait_for_timing_when_optional_timing_missing():
    result = workflow_engine.evaluate_workflow_method(
        method_payload(),
        {"symbol": "NVDA", "observations": {}},
    )

    assert result["final_status"] == "wait_for_timing"
    assert result["missing_information"]
    assert "wait_for_timing" in result["next_actions"]
```

- [ ] **Step 2: Run workflow tests and verify failure**

Run:

```bash
cd /Users/littlemay/work/meowstreet/meowstreet
python3 -m pytest tests/test_workflow_engine.py -q
```

Expected: fail because `meowstreet.workflow_engine` does not exist.

- [ ] **Step 3: Copy and retarget workflow engine**

Copy:

```text
/Users/littlemay/work/serenity-dashboard/.worktrees/method-workflow-graph/traderdash/workflow_engine.py
```

to:

```text
/Users/littlemay/work/meowstreet/meowstreet/meowstreet/workflow_engine.py
```

Then update imports:

```python
from meowstreet.method_schema import (
    normalize_method_payload,
    normalize_graph_observation_payload,
)
```

- [ ] **Step 4: Run workflow tests and verify pass**

Run:

```bash
cd /Users/littlemay/work/meowstreet/meowstreet
python3 -m pytest tests/test_workflow_engine.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit workflow engine**

Run:

```bash
cd /Users/littlemay/work/meowstreet/meowstreet
git add meowstreet/workflow_engine.py tests/test_workflow_engine.py
git commit -m "feat: evaluate method workflow"
```

---

### Task 6: Add Minimal FastAPI App

**Files:**
- Create: `/Users/littlemay/work/meowstreet/meowstreet/meowstreet/api.py`
- Create: `/Users/littlemay/work/meowstreet/meowstreet/tests/test_api.py`

- [ ] **Step 1: Write API tests**

Create `tests/test_api.py`:

```python
from fastapi.testclient import TestClient

from meowstreet.api import app


client = TestClient(app)


def test_method_endpoint_returns_graph():
    response = client.get("/api/method-system/method")

    assert response.status_code == 200
    payload = response.json()
    assert payload["version"] == "v1"
    assert payload["workflow_nodes"]
    assert payload["node_checks"]


def test_workflow_evaluate_endpoint_accepts_sparse_ticker_payload():
    response = client.post(
        "/api/method-system/workflow/evaluate",
        json={"symbol": "XYZ", "observations": {}},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["symbol"] == "XYZ"
    assert "nodes" in payload
    assert "final_status" in payload
```

- [ ] **Step 2: Run API tests and verify failure**

Run:

```bash
cd /Users/littlemay/work/meowstreet/meowstreet
python3 -m pytest tests/test_api.py -q
```

Expected: fail because `meowstreet.api` does not exist.

- [ ] **Step 3: Implement minimal API**

Create `meowstreet/api.py`:

```python
import json
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from meowstreet import workflow_engine

ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = ROOT / "static"
METHOD_PATH = ROOT / "data" / "local_system" / "method.v1.json"

app = FastAPI(title="Meowstreet")

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def load_workflow_method():
    if not METHOD_PATH.exists():
        raise HTTPException(status_code=500, detail=f"missing method artifact: {METHOD_PATH}")
    return json.loads(METHOD_PATH.read_text(encoding="utf-8"))


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "method-system.html")


@app.get("/method-system.html")
def local_system_html():
    return FileResponse(STATIC_DIR / "method-system.html")


@app.get("/method-system.css")
def local_system_css():
    return FileResponse(STATIC_DIR / "method-system.css", media_type="text/css")


@app.get("/method-system.js")
def local_system_js():
    return FileResponse(STATIC_DIR / "method-system.js", media_type="application/javascript")


@app.get("/api/method-system/method")
def method():
    return load_workflow_method()


@app.post("/api/method-system/workflow/evaluate")
def workflow_evaluate(body: dict = Body(default={})):
    try:
        return workflow_engine.evaluate_workflow_method(load_workflow_method(), body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
```

- [ ] **Step 4: Run API tests and verify pass**

Run:

```bash
cd /Users/littlemay/work/meowstreet/meowstreet
python3 -m pytest tests/test_api.py -q
```

Expected: `2 passed`.

- [ ] **Step 5: Commit API**

Run:

```bash
cd /Users/littlemay/work/meowstreet/meowstreet
git add meowstreet/api.py tests/test_api.py
git commit -m "feat: expose method workflow api"
```

---

### Task 7: Migrate Graph Console UI

**Files:**
- Create: `/Users/littlemay/work/meowstreet/meowstreet/static/method-system.html`
- Create: `/Users/littlemay/work/meowstreet/meowstreet/static/method-system.css`
- Create: `/Users/littlemay/work/meowstreet/meowstreet/static/method-system.js`

- [ ] **Step 1: Copy graph UI files**

Copy:

```text
/Users/littlemay/work/serenity-dashboard/.worktrees/method-workflow-graph/dashboard/method-system.html
/Users/littlemay/work/serenity-dashboard/.worktrees/method-workflow-graph/dashboard/method-system.css
/Users/littlemay/work/serenity-dashboard/.worktrees/method-workflow-graph/dashboard/method-system.js
```

to:

```text
/Users/littlemay/work/meowstreet/meowstreet/static/method-system.html
/Users/littlemay/work/meowstreet/meowstreet/static/method-system.css
/Users/littlemay/work/meowstreet/meowstreet/static/method-system.js
```

- [ ] **Step 2: Simplify navigation in HTML**

In `static/method-system.html`, replace the Serenity nav:

```html
<nav class="topnav">
  <a href="/" class="nav-brand">Prism</a>
  <a href="/dashboard.html" class="nav-link">Dashboard</a>
  <a href="/method-system.html" class="nav-link active">Method System</a>
  <a href="/fetch.html" class="nav-link">Fetch</a>
  <a href="/status.html" class="nav-link">Status</a>
</nav>
```

with:

```html
<nav class="topnav">
  <a href="/" class="nav-brand">Meowstreet</a>
  <a href="/method-system.html" class="nav-link active">Method System</a>
</nav>
```

Keep these asset links unchanged because `meowstreet.api` serves them:

```html
<link rel="stylesheet" href="/method-system.css?v=2" />
<script src="/method-system.js?v=2"></script>
```

- [ ] **Step 3: Run JS syntax check**

Run:

```bash
cd /Users/littlemay/work/meowstreet/meowstreet
node --check static/method-system.js
```

Expected: exit code `0`.

- [ ] **Step 4: Smoke test static routes**

Run:

```bash
cd /Users/littlemay/work/meowstreet/meowstreet
python3 -m uvicorn meowstreet.api:app --port 8797
```

In another terminal, run:

```bash
curl -sS http://127.0.0.1:8797/method-system.html | rg 'Method Trade Console|workflowGraph|method-system.js'
curl -sS http://127.0.0.1:8797/method-system.js | head -n 5
curl -sS http://127.0.0.1:8797/api/method-system/method | python3 -m json.tool >/dev/null
curl -sS -X POST http://127.0.0.1:8797/api/method-system/workflow/evaluate \
  -H 'Content-Type: application/json' \
  -d '{"symbol":"XYZ","observations":{}}' | python3 -m json.tool >/dev/null
```

Expected: all commands exit `0`.

- [ ] **Step 5: Stop server**

Press `Ctrl-C` in the terminal running Uvicorn.

- [ ] **Step 6: Commit UI**

Run:

```bash
cd /Users/littlemay/work/meowstreet/meowstreet
git add static/method-system.html static/method-system.css static/method-system.js
git commit -m "feat: add workflow graph console"
```

---

### Task 8: Final Verification And Cleanup

**Files:**
- Modify if needed: `/Users/littlemay/work/meowstreet/meowstreet/README.md`
- Modify if needed: `/Users/littlemay/work/meowstreet/meowstreet/.gitignore`

- [ ] **Step 1: Run full test suite**

Run:

```bash
cd /Users/littlemay/work/meowstreet/meowstreet
python3 -m pytest -q
```

Expected: all tests pass.

- [ ] **Step 2: Run Python compile check**

Run:

```bash
cd /Users/littlemay/work/meowstreet/meowstreet
python3 -m py_compile \
  meowstreet/method_notes_parser.py \
  meowstreet/method_schema.py \
  meowstreet/method_builder.py \
  meowstreet/workflow_engine.py \
  meowstreet/api.py \
  scripts/build_method.py
```

Expected: exit code `0`.

- [ ] **Step 3: Run JS syntax check**

Run:

```bash
cd /Users/littlemay/work/meowstreet/meowstreet
node --check static/method-system.js
```

Expected: exit code `0`.

- [ ] **Step 4: Confirm no Serenity-only code migrated**

Run:

```bash
cd /Users/littlemay/work/meowstreet/meowstreet
rg 'traderdash|serenity|scripts.server|chat_service|chat_index|x_curl|tweets|configured_users|strategy' .
```

Expected: no matches except this word inside documentation explaining what was intentionally not migrated. If code files match, remove the accidental dependency.

- [ ] **Step 5: Check git status**

Run:

```bash
cd /Users/littlemay/work/meowstreet/meowstreet
git status --short --branch
```

Expected: clean.

- [ ] **Step 6: Commit documentation or cleanup fixes if needed**

Only run this if Step 1-4 caused file edits:

```bash
cd /Users/littlemay/work/meowstreet/meowstreet
git add README.md .gitignore
git commit -m "docs: document meowstreet workflow"
```

---

## Self-Review

Spec coverage:

- Standalone repo target is explicit: `/Users/littlemay/work/meowstreet/meowstreet`.
- Method notes, parser, method builder, graph artifact, workflow engine, API, and UI are covered.
- Serenity-only systems are explicitly excluded.
- Every task has test or smoke verification and a commit point.

Placeholder scan:

- No `TBD`, `TODO`, or unspecified implementation steps are required for execution.

Type consistency:

- API payload uses `{"symbol": "...", "observations": {...}}`.
- Method endpoint uses `/api/method-system/method`.
- Evaluation endpoint uses `/api/method-system/workflow/evaluate`.
- Static JS can call the same endpoints without route changes.

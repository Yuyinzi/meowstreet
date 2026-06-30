# Method Workflow Graph Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a ticker-first method-method workflow graph that evaluates all available nodes in one backend call and renders node statuses visually in the method system UI.

**Architecture:** Add a versioned `method.v1.json` artifact containing concepts, workflow nodes, graph edges, and node checks derived from the method-note structure. Add deterministic graph evaluation beside the existing flat rulebook evaluator, then expose graph endpoints through both legacy `scripts/server.py` and FastAPI `webapp.dashboard_api`. Replace the current form-first UI with a ticker-first graph console that shows queued/running states locally and final node results from the backend.

**Tech Stack:** Python 3, SQLite, existing `traderdash` modules, legacy `http.server`, FastAPI router in `webapp`, vanilla HTML/CSS/JS, pytest.

---

## File Structure

- Create `traderdash/method_notes_parser.py`: parse note markdown into stable sections and source references.
- Create `traderdash/method_schema.py`: validate/normalize `method.v1.json`, graph nodes, checks, and graph evaluation payloads.
- Create `traderdash/method_builder.py`: build the first deterministic method method graph from note metadata and curated method node definitions.
- Create `traderdash/workflow_engine.py`: evaluate graph nodes, side-specific checks, node statuses, final classifications, missing inputs, and next actions.
- Modify `scripts/build_method_rulebook.py`: keep existing `rulebook.v1.json` behavior and add `method.v1.json` generation.
- Modify `scripts/server.py`: load method method graph, expose graph endpoint, and save graph evaluation results through the existing store shape.
- Modify `webapp/dashboard_service.py`: mirror server service helpers for FastAPI.
- Modify `webapp/dashboard_api.py`: expose FastAPI graph endpoint.
- Modify `dashboard/method-system.html`: change primary UI from observation form to ticker-first graph console.
- Modify `dashboard/method-system.css`: add graph layout, node status colors, detail panel, and responsive behavior.
- Modify `dashboard/method-system.js`: load graph, simulate queued/running states, submit one graph evaluation call, and render node details.
- Add tests:
  - `tests/test_method_notes_parser.py`
  - `tests/test_method_schema.py`
  - `tests/test_method_builder.py`
  - `tests/test_workflow_engine.py`
  - extend `tests/test_build_method_rulebook.py`
  - extend `tests/test_server.py`
  - add or extend FastAPI route tests if an existing FastAPI test file is present.

---

### Task 1: Method Note Section Parser

**Files:**
- Create: `traderdash/method_notes_parser.py`
- Test: `tests/test_method_notes_parser.py`

- [ ] **Step 1: Write failing parser tests**

Create `tests/test_method_notes_parser.py`:

```python
from pathlib import Path

from traderdash import method_notes_parser


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
    assert "Key Points" in parsed["sections"]
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
/Users/littlemay/work/serenity-dashboard/.venv/bin/pytest tests/test_method_notes_parser.py -q
```

Expected: fail with `ImportError` or `AttributeError` because `traderdash.method_notes_parser` does not exist.

- [ ] **Step 3: Implement parser module**

Create `traderdash/method_notes_parser.py`:

```python
import hashlib
import re
from pathlib import Path


SECTION_NAMES = [
    "Key Points",
    "Learning Path / Reasoning Chain",
    "Concepts & Definitions",
    "Methodology / Workflow",
    "Examples & Applications",
    "Cautions / Common Mistakes",
    "Transcript Gaps / Incomplete Segments",
    "Actionable Checklist",
]

HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
SOURCE_RE = re.compile(r"^Source:\s+`?([^`\n]+)`?\s*$", re.MULTILINE)


def _relative(path, root):
    path = Path(path)
    root = Path(root)
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _title_from_text(path, text):
    for line in text.splitlines():
        match = HEADING_RE.match(line.strip())
        if match and len(match.group(1)) == 1:
            return match.group(2).strip()
    stem = Path(path).stem
    if stem.endswith("_method_notes"):
        stem = stem[: -len("_method_notes")]
    return stem.replace("_", " ").strip() or Path(path).name


def _source_from_text(text):
    match = SOURCE_RE.search(text)
    if not match:
        return ""
    return match.group(1).strip()


def _extract_sections(text):
    lines = text.replace("\r", "").split("\n")
    sections = {}
    section_order = []
    current = None
    buffer = []

    def flush():
        if current is not None:
            sections[current] = "\n".join(buffer).strip()

    for line in lines:
        match = HEADING_RE.match(line.strip())
        if match and len(match.group(1)) == 2 and match.group(2).strip() in SECTION_NAMES:
            flush()
            current = match.group(2).strip()
            section_order.append(current)
            buffer = []
            continue
        if current is not None:
            buffer.append(line)
    flush()

    for name in SECTION_NAMES:
        sections.setdefault(name, "")
    return sections, section_order


def parse_method_note(path, root=None):
    path = Path(path)
    root = Path(root) if root is not None else path.parent
    text = path.read_text(encoding="utf-8")
    sections, section_order = _extract_sections(text)
    return {
        "path": _relative(path, root),
        "title": _title_from_text(path, text),
        "source": _source_from_text(text),
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "sections": sections,
        "section_order": section_order,
    }


def parse_method_notes_dir(notes_dir, root=None):
    notes_dir = Path(notes_dir)
    root = Path(root) if root is not None else notes_dir
    if not notes_dir.exists() or not notes_dir.is_dir():
        return []
    return [
        parse_method_note(path, root=root)
        for path in sorted(notes_dir.glob("*.md"))
    ]
```

- [ ] **Step 4: Run parser tests and verify pass**

Run:

```bash
/Users/littlemay/work/serenity-dashboard/.venv/bin/pytest tests/test_method_notes_parser.py -q
```

Expected: `3 passed`.

- [ ] **Step 5: Commit parser**

Run:

```bash
git add traderdash/method_notes_parser.py tests/test_method_notes_parser.py
git commit -m "feat: parse method note sections"
```

---

### Task 2: Method Method Schema

**Files:**
- Create: `traderdash/method_schema.py`
- Test: `tests/test_method_schema.py`

- [ ] **Step 1: Write failing schema tests**

Create `tests/test_method_schema.py`:

```python
import pytest

from traderdash import method_schema


def _valid_method():
    return {
        "version": " v1 ",
        "generated_at": "2026-06-26T00:00:00+00:00",
        "source_documents": [{"path": "data/method_notes/P1.md", "title": "P1"}],
        "concepts": [
            {
                "id": "catalyst",
                "title": "Catalyst",
                "definition": "Event likely to move a stock.",
                "supporting_only": False,
                "source_refs": [{"document": "", "section": "Concepts & Definitions"}],
            }
        ],
        "workflow_nodes": [
            {
                "id": "catalyst_window",
                "title": "Catalyst Window",
                "decision_question": "Is there a catalyst inside the mandate?",
                "description": "Checks for a catalyst.",
                "required_inputs": ["setup.catalyst"],
                "criteria": ["Catalyst exists"],
                "tool_hooks": ["earnings_calendar"],
                "incoming_edges": ["bottom_up_fundamental_bias"],
                "outgoing_edges": ["technical_timing"],
                "source_refs": [{"document": "", "section": "Methodology / Workflow"}],
            }
        ],
        "node_checks": [
            {
                "id": "catalyst_present",
                "node_id": "catalyst_window",
                "title": "Catalyst present",
                "field": "setup.catalyst",
                "operator": "exists",
                "side": "both",
                "required": True,
                "missing_message": "Catalyst detail is missing.",
                "fail_effect": "wait_for_research",
                "source_refs": [{"document": "", "section": "Actionable Checklist"}],
            }
        ],
        "decision_rules": [
            {"id": "blocked_reject", "description": "Blockers reject the setup."}
        ],
        "extraction_warnings": [],
    }


def test_normalize_method_payload_trims_version_and_keeps_graph():
    payload = method_schema.normalize_method_payload(_valid_method())

    assert payload["version"] == "v1"
    assert payload["workflow_nodes"][0]["id"] == "catalyst_window"
    assert payload["node_checks"][0]["side"] == "both"


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda p: p.pop("version"), "method method version is required"),
        (lambda p: p.__setitem__("workflow_nodes", []), "workflow_nodes must not be empty"),
        (lambda p: p.__setitem__("node_checks", []), "node_checks must not be empty"),
        (lambda p: p["workflow_nodes"][0].pop("decision_question"), "workflow node catalyst_window decision_question is required"),
        (lambda p: p["node_checks"][0].__setitem__("side", "bad"), "node check catalyst_present side is invalid"),
        (lambda p: p["node_checks"][0].__setitem__("node_id", "missing_node"), "node check catalyst_present references unknown node"),
    ],
)
def test_normalize_method_payload_validates_contract(mutation, message):
    payload = _valid_method()
    mutation(payload)

    with pytest.raises(ValueError, match=message):
        method_schema.normalize_method_payload(payload)


def test_normalize_graph_observation_payload_requires_symbol():
    normalized = method_schema.normalize_graph_observation_payload(
        {"symbol": " nvda ", "observations": {"metrics": {"price": 100}}}
    )

    assert normalized["symbol"] == "NVDA"
    assert normalized["observations"]["metrics"]["price"] == 100


def test_normalize_graph_observation_payload_rejects_bad_symbol():
    with pytest.raises(ValueError, match="observation symbol is invalid"):
        method_schema.normalize_graph_observation_payload({"symbol": "bad symbol"})
```

- [ ] **Step 2: Run schema tests and verify failure**

Run:

```bash
/Users/littlemay/work/serenity-dashboard/.venv/bin/pytest tests/test_method_schema.py -q
```

Expected: fail with `ImportError` because `traderdash.method_schema` does not exist.

- [ ] **Step 3: Implement schema normalizer**

Create `traderdash/method_schema.py`:

```python
import re


_SYMBOL_RE = re.compile(r"^[A-Z][A-Z0-9.-]*$")
_VALID_SIDES = {"long", "short", "both"}
_VALID_OPERATORS = {
    "exists",
    "truthy",
    "falsy",
    "equals",
    "not_equals",
    "contains",
    "in",
    "any_of",
    "all_of",
    "gt",
    "gte",
    "lt",
    "lte",
}


def _text(value):
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


def _value(value):
    if isinstance(value, dict):
        return {key: _value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_value(item) for item in value]
    if isinstance(value, tuple):
        return [_value(item) for item in value]
    if isinstance(value, str):
        return value.strip()
    return value


def _array(payload, key):
    value = payload.get(key)
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"{key} must be a list")
    return value


def _required_text(obj, key, label):
    value = _text(obj.get(key))
    if not value:
        raise ValueError(f"{label} {key} is required")
    obj[key] = value
    return value


def normalize_method_payload(payload):
    if not isinstance(payload, dict):
        raise ValueError("method method payload must be an object")

    normalized = _value(payload)
    version = _text(normalized.get("version"))
    if not version:
        raise ValueError("method method version is required")
    normalized["version"] = version

    workflow_nodes = _array(normalized, "workflow_nodes")
    node_checks = _array(normalized, "node_checks")
    if not workflow_nodes:
        raise ValueError("workflow_nodes must not be empty")
    if not node_checks:
        raise ValueError("node_checks must not be empty")

    node_ids = set()
    for index, node in enumerate(workflow_nodes):
        if not isinstance(node, dict):
            raise ValueError(f"workflow node {index} must be an object")
        node_id = _required_text(node, "id", "workflow node")
        _required_text(node, "title", f"workflow node {node_id}")
        _required_text(node, "decision_question", f"workflow node {node_id}")
        _required_text(node, "description", f"workflow node {node_id}")
        for key in ("required_inputs", "criteria", "tool_hooks", "incoming_edges", "outgoing_edges", "source_refs"):
            if key not in node:
                node[key] = []
            if not isinstance(node[key], list):
                raise ValueError(f"workflow node {node_id} {key} must be a list")
        node_ids.add(node_id)

    for index, check in enumerate(node_checks):
        if not isinstance(check, dict):
            raise ValueError(f"node check {index} must be an object")
        check_id = _required_text(check, "id", "node check")
        node_id = _required_text(check, "node_id", f"node check {check_id}")
        if node_id not in node_ids:
            raise ValueError(f"node check {check_id} references unknown node")
        _required_text(check, "title", f"node check {check_id}")
        _required_text(check, "field", f"node check {check_id}")
        operator = _required_text(check, "operator", f"node check {check_id}")
        if operator not in _VALID_OPERATORS:
            raise ValueError(f"node check {check_id} operator is invalid")
        side = _required_text(check, "side", f"node check {check_id}")
        if side not in _VALID_SIDES:
            raise ValueError(f"node check {check_id} side is invalid")
        if "source_refs" not in check:
            check["source_refs"] = []
        if not isinstance(check["source_refs"], list):
            raise ValueError(f"node check {check_id} source_refs must be a list")
        check["required"] = check.get("required") is True

    for key in ("source_documents", "concepts", "decision_rules", "extraction_warnings"):
        if key not in normalized:
            normalized[key] = []
        if not isinstance(normalized[key], list):
            raise ValueError(f"{key} must be a list")

    return normalized


def normalize_graph_observation_payload(payload):
    if not isinstance(payload, dict):
        raise ValueError("observation payload must be an object")
    normalized = _value(payload)
    symbol = _text(normalized.get("symbol"))
    if not symbol:
        raise ValueError("observation symbol is required")
    symbol = symbol.upper()
    if not _SYMBOL_RE.match(symbol):
        raise ValueError("observation symbol is invalid")
    observations = normalized.get("observations")
    if observations is None:
        observations = {}
    if not isinstance(observations, dict):
        raise ValueError("observations must be an object")
    normalized["symbol"] = symbol
    normalized["observations"] = observations
    return normalized
```

- [ ] **Step 4: Run schema tests and verify pass**

Run:

```bash
/Users/littlemay/work/serenity-dashboard/.venv/bin/pytest tests/test_method_schema.py -q
```

Expected: `4 passed`.

- [ ] **Step 5: Commit schema**

Run:

```bash
git add traderdash/method_schema.py tests/test_method_schema.py
git commit -m "feat: add method method graph schema"
```

---

### Task 3: Build Method Method Graph Artifact

**Files:**
- Create: `traderdash/method_builder.py`
- Modify: `scripts/build_method_rulebook.py`
- Modify: `data/local_system/method.v1.json`
- Test: `tests/test_method_builder.py`
- Test: `tests/test_build_method_rulebook.py`

- [ ] **Step 1: Write failing builder tests**

Create `tests/test_method_builder.py`:

```python
from traderdash import method_builder
from traderdash import method_schema


def test_build_method_payload_contains_connected_workflow(tmp_path):
    notes_dir = tmp_path / "notes"
    notes_dir.mkdir()
    (notes_dir / "P1 The Framework_method_notes.md").write_text(
        """# Method Notes: P1 The Framework -en

Source: `P1 The Framework -en.txt`

## Concepts & Definitions
- **Catalyst**: An event likely to move a stock.

## Methodology / Workflow
1. Trade ideas require fundamental bias, catalyst, timing, structure, and risk management.

## Cautions / Common Mistakes
- A good company is not a good trade idea without a catalyst.

## Actionable Checklist
- [ ] Identify catalysts expected within 20-60 days.
""",
        encoding="utf-8",
    )
    (notes_dir / "P15 Recap_method_notes.md").write_text(
        """# Method Notes: P15 Recap -en

## Methodology / Workflow
- Monitor leading indicators and adjust portfolio bias.

## Actionable Checklist
- [ ] Compare market regime and sector context.
""",
        encoding="utf-8",
    )

    payload = method_builder.build_method_payload(notes_dir=notes_dir, version="v1", root=tmp_path)
    normalized = method_schema.normalize_method_payload(payload)

    node_ids = {node["id"] for node in normalized["workflow_nodes"]}
    assert {"instrument_identity", "catalyst_window", "technical_timing", "final_synthesis"} <= node_ids
    assert any(node["outgoing_edges"] for node in normalized["workflow_nodes"])
    assert any(check["node_id"] == "catalyst_window" for check in normalized["node_checks"])
    assert normalized["source_documents"][0]["path"].startswith("notes/")


def test_method_payload_records_gap_warnings(tmp_path):
    notes_dir = tmp_path / "notes"
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
            "document": "notes/P6 Gap_method_notes.md",
            "section": "Transcript Gaps / Incomplete Segments",
            "message": "Possible missing middle section.",
        }
    ]
```

Extend `tests/test_build_method_rulebook.py` with:

```python
def test_main_writes_method_file(tmp_path, capsys):
    module = load_module()
    notes_dir = tmp_path / "notes"
    notes_dir.mkdir()
    (notes_dir / "P1 The Framework_method_notes.md").write_text(
        "# Method Notes: P1 The Framework -en\n\n## Methodology / Workflow\n- Catalyst and timing.\n",
        encoding="utf-8",
    )
    rulebook_output = tmp_path / "data" / "local_system" / "rulebook.v1.json"
    method_output = tmp_path / "data" / "local_system" / "method.v1.json"

    module.main([
        "--notes-dir",
        str(notes_dir),
        "--output",
        str(rulebook_output),
        "--method-output",
        str(method_output),
    ])

    assert rulebook_output.exists()
    assert method_output.exists()
    payload = json.loads(method_output.read_text(encoding="utf-8"))
    assert payload["version"] == "v1"
    assert payload["workflow_nodes"]
```

- [ ] **Step 2: Run builder tests and verify failure**

Run:

```bash
/Users/littlemay/work/serenity-dashboard/.venv/bin/pytest tests/test_method_builder.py tests/test_build_method_rulebook.py -q
```

Expected: fail because `method_builder` and `--method-output` do not exist.

- [ ] **Step 3: Implement deterministic graph builder**

Create `traderdash/method_builder.py`:

```python
from datetime import datetime, timezone
from pathlib import Path

from traderdash import method_notes_parser
from traderdash.method_schema import normalize_method_payload


DEFAULT_NODE_ORDER = [
    "instrument_identity",
    "liquidity_tradability",
    "time_horizon_fit",
    "macro_regime",
    "sector_theme_context",
    "bottom_up_fundamental_bias",
    "catalyst_window",
    "technical_timing",
    "portfolio_fit",
    "risk_position_sizing",
    "process_discipline",
    "final_synthesis",
]


def _source_ref(doc, section):
    return {"document": doc["path"], "section": section}


def _refs_for_keywords(documents, section, keywords):
    refs = []
    lowered_keywords = [keyword.lower() for keyword in keywords]
    for doc in documents:
        text = doc.get("sections", {}).get(section, "")
        lower_text = text.lower()
        if any(keyword in lower_text for keyword in lowered_keywords):
            refs.append(_source_ref(doc, section))
    if refs:
        return refs
    return [_source_ref(doc, section) for doc in documents[:3]]


def _node(node_id, title, question, description, required_inputs, criteria, tool_hooks, keywords, documents):
    index = DEFAULT_NODE_ORDER.index(node_id)
    incoming = [DEFAULT_NODE_ORDER[index - 1]] if index > 0 else []
    outgoing = [DEFAULT_NODE_ORDER[index + 1]] if index < len(DEFAULT_NODE_ORDER) - 1 else []
    return {
        "id": node_id,
        "title": title,
        "decision_question": question,
        "description": description,
        "required_inputs": required_inputs,
        "criteria": criteria,
        "tool_hooks": tool_hooks,
        "incoming_edges": incoming,
        "outgoing_edges": outgoing,
        "source_refs": _refs_for_keywords(documents, "Methodology / Workflow", keywords),
    }


def _seed_nodes(documents):
    return [
        _node(
            "instrument_identity",
            "Instrument Identity",
            "Is this a valid tradable instrument for the method workflow?",
            "Confirms symbol identity before applying trade analysis.",
            ["symbol"],
            ["Symbol is present and normalized."],
            ["symbol_profile"],
            ["stock", "equities", "symbol"],
            documents,
        ),
        _node(
            "liquidity_tradability",
            "Liquidity / Tradability",
            "Is the instrument liquid enough to trade without thin-market risk?",
            "Checks price, dollar volume, and availability of market data.",
            ["metrics.price", "metrics.avg_dollar_volume_millions"],
            ["Price is above floor.", "Average dollar volume is sufficient."],
            ["market_data"],
            ["liquidity", "volume", "price"],
            documents,
        ),
        _node(
            "time_horizon_fit",
            "Time Horizon Fit",
            "Does this idea fit the 20-60 day trading mandate?",
            "Separates method-style trades from day trades and investments.",
            ["setup.expected_holding_days"],
            ["Expected holding period is between 20 and 60 days."],
            ["user_observation"],
            ["20", "60", "time horizon"],
            documents,
        ),
        _node(
            "macro_regime",
            "Macro Regime",
            "Does the macro regime support the proposed long or short side?",
            "Uses leading indicators and market context to frame portfolio bias.",
            ["macro.regime"],
            ["Macro regime is known.", "Regime does not directly block the side."],
            ["macro_dashboard"],
            ["leading indicators", "macro", "portfolio bias"],
            documents,
        ),
        _node(
            "sector_theme_context",
            "Sector / Theme Context",
            "Is the sector or theme aligned with the setup direction?",
            "Checks whether the ticker has a relevant theme and sector context.",
            ["tags", "sector.relative_strength"],
            ["Theme is identified.", "Sector relative strength is available."],
            ["sector_relative_strength"],
            ["sector", "theme", "relative strength"],
            documents,
        ),
        _node(
            "bottom_up_fundamental_bias",
            "Bottom-Up Fundamental Bias",
            "Is there a fundamental long or short bias?",
            "Evaluates company-specific quantitative and qualitative drivers.",
            ["fundamentals.bias"],
            ["Fundamental bias is stated.", "Bias has a reason beyond price action."],
            ["fundamentals"],
            ["bottom-up", "fundamental", "quantitative", "qualitative"],
            documents,
        ),
        _node(
            "catalyst_window",
            "Catalyst Window",
            "Is there a catalyst likely to move the stock within the 20-60 day horizon?",
            "Checks whether a stock has an event or development that can turn bias into a trade idea.",
            ["setup.catalyst"],
            ["Catalyst is documented.", "Catalyst belongs inside the trading horizon."],
            ["earnings_calendar", "event_source"],
            ["catalyst", "earnings", "report"],
            documents,
        ),
        _node(
            "technical_timing",
            "Technical Timing",
            "Is there a low-risk timing window after the trade idea exists?",
            "Uses technicals only for timing, not idea generation.",
            ["signals.trend", "signals.entry_timing"],
            ["Trend is aligned.", "Entry timing is favorable or clearly missing."],
            ["market_data", "technical_indicators"],
            ["technical", "price action", "timing"],
            documents,
        ),
        _node(
            "portfolio_fit",
            "Portfolio Fit",
            "Does the position fit portfolio bias and exposure constraints?",
            "Checks whether the idea improves or damages portfolio construction.",
            ["portfolio.net_exposure", "portfolio.correlation"],
            ["Portfolio exposure is known.", "Correlation impact is acceptable."],
            ["portfolio"],
            ["portfolio", "correlation", "beta", "long short"],
            documents,
        ),
        _node(
            "risk_position_sizing",
            "Risk / Position Sizing",
            "Is risk defined before entry?",
            "Checks preemptive risk, stop logic, and position size permission.",
            ["risk.stop", "risk.position_size"],
            ["Stop is defined.", "Position size is defined."],
            ["risk_model"],
            ["risk management", "position sizing", "stop"],
            documents,
        ),
        _node(
            "process_discipline",
            "Process Discipline",
            "Is the setup being evaluated through the method process rather than impulse?",
            "Keeps the system from turning missing data into a forced trade.",
            ["process.source", "process.notes"],
            ["Idea source is documented.", "Missing information is acknowledged."],
            ["user_observation"],
            ["self-sustainability", "process", "work ethic"],
            documents,
        ),
        _node(
            "final_synthesis",
            "Final Synthesis",
            "What is the method-method classification after all runnable nodes finish?",
            "Aggregates node outputs into qualified candidate, watchlist, timing wait, insufficient data, conflict, or reject.",
            ["node_results"],
            ["No hard blocker exists.", "Long and short evidence are classified separately."],
            [],
            ["framework", "trade idea", "risk management"],
            documents,
        ),
    ]


def _seed_concepts(documents):
    return [
        {
            "id": "catalyst",
            "title": "Catalyst",
            "definition": "An event or expected development likely to move a stock within the method trading horizon.",
            "supporting_only": False,
            "source_refs": _refs_for_keywords(documents, "Concepts & Definitions", ["catalyst"]),
        },
        {
            "id": "twenty_to_sixty_day_horizon",
            "title": "20-60 Day Time Horizon",
            "definition": "The method mandate for professional-style equity trades.",
            "supporting_only": False,
            "source_refs": _refs_for_keywords(documents, "Concepts & Definitions", ["20", "60", "time horizon"]),
        },
        {
            "id": "self_sustainability",
            "title": "Self-Sustainability",
            "definition": "The trader must generate and evaluate ideas independently instead of copy trading.",
            "supporting_only": True,
            "source_refs": _refs_for_keywords(documents, "Concepts & Definitions", ["self-sustainability"]),
        },
    ]


def _check(check_id, node_id, title, field, operator, side="both", value=None, required=False, fail_effect="watchlist", missing_message=None, source_refs=None):
    payload = {
        "id": check_id,
        "node_id": node_id,
        "title": title,
        "field": field,
        "operator": operator,
        "side": side,
        "required": required,
        "fail_effect": fail_effect,
        "source_refs": source_refs or [],
    }
    if value is not None:
        payload["value"] = value
    if missing_message:
        payload["missing_message"] = missing_message
    return payload


def _seed_checks(documents):
    methodology_refs = _refs_for_keywords(documents, "Methodology / Workflow", ["framework", "trade idea"])
    catalyst_refs = _refs_for_keywords(documents, "Actionable Checklist", ["catalyst"])
    return [
        _check("symbol_present", "instrument_identity", "Symbol present", "symbol", "exists", required=True, fail_effect="reject", source_refs=methodology_refs),
        _check("price_floor", "liquidity_tradability", "Price above floor", "metrics.price", "gte", value=10, required=True, fail_effect="reject", source_refs=methodology_refs),
        _check("avg_dollar_volume", "liquidity_tradability", "Average dollar volume", "metrics.avg_dollar_volume_millions", "gte", value=25, required=False, fail_effect="watchlist", source_refs=methodology_refs),
        _check("holding_period", "time_horizon_fit", "20-60 day holding period", "setup.expected_holding_days", "gte", value=20, required=False, fail_effect="wait_for_research", source_refs=methodology_refs),
        _check("macro_regime_known", "macro_regime", "Macro regime known", "macro.regime", "exists", required=False, fail_effect="wait_for_research", source_refs=methodology_refs),
        _check("theme_tagged", "sector_theme_context", "Theme tagged", "tags", "exists", required=False, fail_effect="watchlist", source_refs=methodology_refs),
        _check("fundamental_bias", "bottom_up_fundamental_bias", "Fundamental bias stated", "fundamentals.bias", "exists", required=True, fail_effect="insufficient_data", source_refs=methodology_refs),
        _check("catalyst_present", "catalyst_window", "Catalyst present", "setup.catalyst", "exists", required=True, fail_effect="wait_for_research", missing_message="Catalyst detail is missing.", source_refs=catalyst_refs),
        _check("trend_known", "technical_timing", "Trend known", "signals.trend", "exists", required=False, fail_effect="wait_for_timing", source_refs=methodology_refs),
        _check("entry_timing", "technical_timing", "Entry timing present", "signals.entry_timing", "exists", required=False, fail_effect="wait_for_timing", source_refs=methodology_refs),
        _check("risk_stop", "risk_position_sizing", "Stop defined", "risk.stop", "exists", required=True, fail_effect="wait_for_research", source_refs=methodology_refs),
        _check("position_size", "risk_position_sizing", "Position size defined", "risk.position_size", "exists", required=True, fail_effect="wait_for_research", source_refs=methodology_refs),
    ]


def _gap_warnings(documents):
    warnings = []
    for doc in documents:
        gap_text = doc.get("sections", {}).get("Transcript Gaps / Incomplete Segments", "")
        for line in gap_text.splitlines():
            line = line.strip()
            if not line or "none flagged" in line.lower():
                continue
            if line.startswith("-"):
                line = line[1:].strip()
            warnings.append({
                "document": doc["path"],
                "section": "Transcript Gaps / Incomplete Segments",
                "message": line,
            })
    return warnings


def build_method_payload(notes_dir, version="v1", root=None):
    notes_dir = Path(notes_dir)
    root = Path(root) if root is not None else notes_dir.parents[1] if len(notes_dir.parents) > 1 else notes_dir
    documents = method_notes_parser.parse_method_notes_dir(notes_dir, root=root)
    payload = {
        "version": version,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "source_documents": [
            {
                "path": doc["path"],
                "title": doc["title"],
                "source": doc["source"],
                "sha256": doc["sha256"],
                "section_order": doc["section_order"],
            }
            for doc in documents
        ],
        "concepts": _seed_concepts(documents),
        "workflow_nodes": _seed_nodes(documents),
        "node_checks": _seed_checks(documents),
        "decision_rules": [
            {"id": "hard_blocker_reject", "description": "Any failed required reject check rejects that side."},
            {"id": "required_missing_insufficient", "description": "Missing required checks prevent qualification."},
            {"id": "timing_missing_wait", "description": "Timing failures or missing timing inputs produce wait_for_timing."},
        ],
        "extraction_warnings": _gap_warnings(documents),
    }
    return normalize_method_payload(payload)
```

- [ ] **Step 4: Wire builder script**

Modify `scripts/build_method_rulebook.py`:

```python
from traderdash import method_builder

DEFAULT_METHOD_OUTPUT = ROOT / "data" / "local_system" / "method.v1.json"
```

Add to `build_arg_parser()`:

```python
parser.add_argument("--method-output", default=str(DEFAULT_METHOD_OUTPUT))
```

Update `main()` after `write_rulebook(...)`:

```python
    method_payload = method_builder.build_method_payload(
        notes_dir=args.notes_dir,
        version=args.version,
        root=ROOT,
    )
    method_destination = Path(args.method_output)
    method_destination.parent.mkdir(parents=True, exist_ok=True)
    method_destination.write_text(
        json.dumps(method_payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
```

Update printed JSON:

```python
                "method_output": str(method_destination),
                "workflow_nodes": len(method_payload["workflow_nodes"]),
                "node_checks": len(method_payload["node_checks"]),
```

- [ ] **Step 5: Run builder tests and verify pass**

Run:

```bash
/Users/littlemay/work/serenity-dashboard/.venv/bin/pytest tests/test_method_builder.py tests/test_build_method_rulebook.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Generate real method method artifact**

Run:

```bash
/Users/littlemay/work/serenity-dashboard/.venv/bin/python scripts/build_method_rulebook.py
```

Expected output includes `"workflow_nodes": 12` and creates `data/local_system/method.v1.json`.

- [ ] **Step 7: Commit graph builder**

Run:

```bash
git add traderdash/method_builder.py scripts/build_method_rulebook.py tests/test_method_builder.py tests/test_build_method_rulebook.py data/local_system/method.v1.json
git commit -m "feat: build method method graph artifact"
```

---

### Task 4: Deterministic Workflow Graph Engine

**Files:**
- Create: `traderdash/workflow_engine.py`
- Test: `tests/test_workflow_engine.py`

- [ ] **Step 1: Write failing engine tests**

Create `tests/test_workflow_engine.py`:

```python
from traderdash import workflow_engine


def _method():
    return {
        "version": "v1",
        "generated_at": "2026-06-26T00:00:00+00:00",
        "source_documents": [],
        "concepts": [],
        "workflow_nodes": [
            {
                "id": "instrument_identity",
                "title": "Instrument Identity",
                "decision_question": "Valid symbol?",
                "description": "Check symbol.",
                "required_inputs": ["symbol"],
                "criteria": ["symbol exists"],
                "tool_hooks": ["symbol_profile"],
                "incoming_edges": [],
                "outgoing_edges": ["catalyst_window"],
                "source_refs": [],
            },
            {
                "id": "catalyst_window",
                "title": "Catalyst Window",
                "decision_question": "Catalyst?",
                "description": "Check catalyst.",
                "required_inputs": ["setup.catalyst"],
                "criteria": ["catalyst exists"],
                "tool_hooks": ["earnings_calendar"],
                "incoming_edges": ["instrument_identity"],
                "outgoing_edges": ["technical_timing"],
                "source_refs": [],
            },
            {
                "id": "technical_timing",
                "title": "Technical Timing",
                "decision_question": "Timing?",
                "description": "Check timing.",
                "required_inputs": ["signals.trend"],
                "criteria": ["trend exists"],
                "tool_hooks": ["market_data"],
                "incoming_edges": ["catalyst_window"],
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
                "fail_effect": "reject",
                "source_refs": [],
            },
            {
                "id": "catalyst_present",
                "node_id": "catalyst_window",
                "title": "Catalyst present",
                "field": "setup.catalyst",
                "operator": "exists",
                "side": "both",
                "required": True,
                "fail_effect": "wait_for_research",
                "source_refs": [],
            },
            {
                "id": "trend_up",
                "node_id": "technical_timing",
                "title": "Trend up",
                "field": "signals.trend",
                "operator": "equals",
                "value": "up",
                "side": "long",
                "required": False,
                "fail_effect": "wait_for_timing",
                "source_refs": [],
            },
            {
                "id": "trend_down",
                "node_id": "technical_timing",
                "title": "Trend down",
                "field": "signals.trend",
                "operator": "equals",
                "value": "down",
                "side": "short",
                "required": False,
                "fail_effect": "wait_for_timing",
                "source_refs": [],
            },
        ],
        "decision_rules": [],
        "extraction_warnings": [],
    }


def test_evaluate_workflow_method_returns_graph_nodes_and_long_watchlist():
    result = workflow_engine.evaluate_workflow_method(
        _method(),
        {
            "symbol": "NVDA",
            "observations": {
                "setup": {"catalyst": "earnings in 40 days"},
                "signals": {"trend": "up"},
            },
        },
    )

    assert result["symbol"] == "NVDA"
    assert result["method_version"] == "v1"
    assert result["final_status"] == "long_watchlist"
    assert [node["node_id"] for node in result["nodes"]] == [
        "instrument_identity",
        "catalyst_window",
        "technical_timing",
    ]
    timing = result["nodes"][2]
    assert timing["status"] == "mixed"
    assert timing["long"]["status"] == "pass"
    assert timing["short"]["status"] == "fail"


def test_evaluate_workflow_method_returns_insufficient_data_with_missing_required_inputs():
    result = workflow_engine.evaluate_workflow_method(
        _method(),
        {"symbol": "AMD", "observations": {"signals": {"trend": "up"}}},
    )

    assert result["final_status"] == "insufficient_data"
    assert any(item["node_id"] == "catalyst_window" for item in result["missing_information"])
    catalyst = [node for node in result["nodes"] if node["node_id"] == "catalyst_window"][0]
    assert catalyst["status"] == "missing"


def test_evaluate_workflow_method_returns_short_watchlist_for_short_supportive_timing():
    result = workflow_engine.evaluate_workflow_method(
        _method(),
        {
            "symbol": "TSLA",
            "observations": {
                "setup": {"catalyst": "negative margin update"},
                "signals": {"trend": "down"},
            },
        },
    )

    assert result["final_status"] == "short_watchlist"
    timing = [node for node in result["nodes"] if node["node_id"] == "technical_timing"][0]
    assert timing["long"]["status"] == "fail"
    assert timing["short"]["status"] == "pass"
```

- [ ] **Step 2: Run engine tests and verify failure**

Run:

```bash
/Users/littlemay/work/serenity-dashboard/.venv/bin/pytest tests/test_workflow_engine.py -q
```

Expected: fail with `ImportError` because `workflow_engine` does not exist.

- [ ] **Step 3: Implement workflow engine**

Create `traderdash/workflow_engine.py`:

```python
from numbers import Real

from traderdash.method_schema import (
    normalize_method_payload,
    normalize_graph_observation_payload,
)


SIDES = ("long", "short")


def _is_missing(value):
    return value is None or value == "" or value == [] or value == {}


def _get_path(payload, path):
    current = payload
    for part in str(path or "").split("."):
        if not part:
            return None
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _is_numeric(value):
    return isinstance(value, Real) and not isinstance(value, bool)


def _compare(actual, operator, expected):
    if operator == "exists":
        return not _is_missing(actual)
    if operator == "truthy":
        return bool(actual)
    if operator == "falsy":
        return not bool(actual)
    if _is_missing(actual):
        return False
    if operator == "equals":
        return actual == expected
    if operator == "not_equals":
        return actual != expected
    if operator == "contains":
        if isinstance(actual, str) and isinstance(expected, str):
            return expected in actual
        if isinstance(actual, (list, tuple, set)):
            return expected in actual
        return False
    if operator == "in":
        return actual in (expected or [])
    if operator == "any_of":
        if isinstance(actual, (list, tuple, set)):
            return any(item in actual for item in (expected or []))
        return actual in (expected or [])
    if operator == "all_of":
        if not isinstance(actual, (list, tuple, set)):
            return False
        return all(item in actual for item in (expected or []))
    if operator == "gt":
        return _is_numeric(actual) and _is_numeric(expected) and actual > expected
    if operator == "gte":
        return _is_numeric(actual) and _is_numeric(expected) and actual >= expected
    if operator == "lt":
        return _is_numeric(actual) and _is_numeric(expected) and actual < expected
    if operator == "lte":
        return _is_numeric(actual) and _is_numeric(expected) and actual <= expected
    raise ValueError(f"unsupported operator: {operator}")


def _check_applies_to_side(check, side):
    return check.get("side") in {"both", side}


def _build_check_result(check, side, observation):
    actual = _get_path(observation, check["field"])
    expected = check.get("value")
    if _is_missing(actual):
        status = "missing"
        message = check.get("missing_message") or f"Missing required observation for {check['field']}"
    elif _compare(actual, check["operator"], expected):
        status = "pass"
        message = check.get("pass_message") or f"{check['title']} passed"
    else:
        status = "fail"
        message = check.get("fail_message") or f"{check['title']} failed"
    return {
        "check_id": check["id"],
        "title": check["title"],
        "side": side,
        "field": check["field"],
        "operator": check["operator"],
        "expected": expected,
        "actual": actual,
        "required": check.get("required") is True,
        "status": status,
        "message": message,
        "fail_effect": check.get("fail_effect", "watchlist"),
        "source_refs": check.get("source_refs", []),
    }


def _side_status(checks):
    if not checks:
        return "missing"
    if any(check["status"] == "missing" and check["required"] for check in checks):
        return "missing"
    if any(check["status"] == "fail" and check["required"] and check["fail_effect"] == "reject" for check in checks):
        return "fail"
    has_pass = any(check["status"] == "pass" for check in checks)
    has_fail = any(check["status"] == "fail" for check in checks)
    has_missing = any(check["status"] == "missing" for check in checks)
    if has_pass and not has_fail and not has_missing:
        return "pass"
    if has_fail and not has_pass and not has_missing:
        return "fail"
    if has_missing and not has_pass and not has_fail:
        return "missing"
    return "mixed"


def _node_status(long_status, short_status):
    statuses = {long_status, short_status}
    if statuses == {"pass"}:
        return "pass"
    if statuses == {"fail"}:
        return "fail"
    if statuses == {"missing"}:
        return "missing"
    return "mixed"


def _evaluate_node(node, checks, observation):
    side_payloads = {}
    all_check_results = []
    for side in SIDES:
        side_checks = [
            _build_check_result(check, side, observation)
            for check in checks
            if _check_applies_to_side(check, side)
        ]
        all_check_results.extend(side_checks)
        side_payloads[side] = {
            "status": _side_status(side_checks),
            "checks": side_checks,
            "evidence": [check["message"] for check in side_checks if check["status"] == "pass"],
            "missing_inputs": [check["field"] for check in side_checks if check["status"] == "missing"],
            "next_actions": [
                check["message"]
                for check in side_checks
                if check["status"] in {"fail", "missing"}
            ],
        }
    return {
        "node_id": node["id"],
        "title": node["title"],
        "decision_question": node["decision_question"],
        "description": node["description"],
        "status": _node_status(side_payloads["long"]["status"], side_payloads["short"]["status"]),
        "long": side_payloads["long"],
        "short": side_payloads["short"],
        "checks": all_check_results,
        "tool_hooks": node.get("tool_hooks", []),
        "incoming_edges": node.get("incoming_edges", []),
        "outgoing_edges": node.get("outgoing_edges", []),
        "method_basis": node.get("source_refs", []),
    }


def _missing_information(nodes):
    missing = []
    for node in nodes:
        fields = sorted(set(node["long"]["missing_inputs"] + node["short"]["missing_inputs"]))
        if fields:
            missing.append({"node_id": node["node_id"], "title": node["title"], "fields": fields})
    return missing


def _next_actions(nodes):
    actions = []
    for node in nodes:
        for side in SIDES:
            for action in node[side]["next_actions"]:
                item = {"node_id": node["node_id"], "side": side, "message": action}
                if item not in actions:
                    actions.append(item)
    return actions


def _final_status(nodes):
    long_pass = sum(1 for node in nodes if node["long"]["status"] == "pass")
    short_pass = sum(1 for node in nodes if node["short"]["status"] == "pass")
    required_missing = any(
        check["required"] and check["status"] == "missing"
        for node in nodes
        for check in node["checks"]
    )
    reject_fail = any(
        check["required"] and check["status"] == "fail" and check["fail_effect"] == "reject"
        for node in nodes
        for check in node["checks"]
    )
    timing_wait = any(
        check["status"] in {"fail", "missing"} and check["fail_effect"] == "wait_for_timing"
        for node in nodes
        for check in node["checks"]
    )

    if reject_fail:
        return "reject"
    if required_missing:
        return "insufficient_data"
    if long_pass >= 3 and short_pass >= 3:
        return "conflicting_evidence"
    if timing_wait and long_pass > short_pass:
        return "wait_for_timing"
    if timing_wait and short_pass > long_pass:
        return "wait_for_timing"
    if long_pass > short_pass:
        return "long_watchlist"
    if short_pass > long_pass:
        return "short_watchlist"
    return "insufficient_data"


def evaluate_workflow_method(method_payload, observation_payload):
    method = normalize_method_payload(method_payload)
    normalized_observation = normalize_graph_observation_payload(observation_payload)
    observation = {"symbol": normalized_observation["symbol"], **normalized_observation["observations"]}

    checks_by_node = {}
    for check in method["node_checks"]:
        checks_by_node.setdefault(check["node_id"], []).append(check)

    nodes = [
        _evaluate_node(node, checks_by_node.get(node["id"], []), observation)
        for node in method["workflow_nodes"]
    ]
    return {
        "symbol": normalized_observation["symbol"],
        "method_version": method["version"],
        "nodes": nodes,
        "edges": [
            {"from": node["node_id"], "to": target}
            for node in nodes
            for target in node.get("outgoing_edges", [])
        ],
        "missing_information": _missing_information(nodes),
        "next_actions": _next_actions(nodes),
        "final_status": _final_status(nodes),
    }
```

- [ ] **Step 4: Run engine tests and verify pass**

Run:

```bash
/Users/littlemay/work/serenity-dashboard/.venv/bin/pytest tests/test_workflow_engine.py -q
```

Expected: `3 passed`.

- [ ] **Step 5: Commit engine**

Run:

```bash
git add traderdash/workflow_engine.py tests/test_workflow_engine.py
git commit -m "feat: evaluate method workflow graph"
```

---

### Task 5: Graph API Endpoints

**Files:**
- Modify: `scripts/server.py`
- Modify: `webapp/dashboard_service.py`
- Modify: `webapp/dashboard_api.py`
- Test: `tests/test_server.py`

- [ ] **Step 1: Write failing legacy server endpoint tests**

Extend `tests/test_server.py` with:

```python
def test_method_endpoint_returns_graph_payload(tmp_path, monkeypatch):
    server = load_server_module(monkeypatch, tmp_path)
    method_dir = tmp_path / "data" / "local_system"
    method_dir.mkdir(parents=True)
    (method_dir / "method.v1.json").write_text(
        json.dumps(
            {
                "version": "v1",
                "generated_at": "2026-06-26T00:00:00+00:00",
                "source_documents": [],
                "concepts": [],
                "workflow_nodes": [
                    {
                        "id": "instrument_identity",
                        "title": "Instrument Identity",
                        "decision_question": "Valid symbol?",
                        "description": "Check symbol.",
                        "required_inputs": ["symbol"],
                        "criteria": ["symbol exists"],
                        "tool_hooks": ["symbol_profile"],
                        "incoming_edges": [],
                        "outgoing_edges": [],
                        "source_refs": [],
                    }
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
                        "fail_effect": "reject",
                        "source_refs": [],
                    }
                ],
                "decision_rules": [],
                "extraction_warnings": [],
            }
        ),
        encoding="utf-8",
    )

    payload = server.Handler.route_api(None, "/api/method-system/method", {})

    assert payload["version"] == "v1"
    assert payload["workflow_nodes"][0]["id"] == "instrument_identity"


def test_workflow_evaluate_endpoint_returns_graph_result(tmp_path, monkeypatch):
    server = load_server_module(monkeypatch, tmp_path)
    method_dir = tmp_path / "data" / "local_system"
    method_dir.mkdir(parents=True)
    (method_dir / "method.v1.json").write_text(
        json.dumps(
            {
                "version": "v1",
                "generated_at": "2026-06-26T00:00:00+00:00",
                "source_documents": [],
                "concepts": [],
                "workflow_nodes": [
                    {
                        "id": "instrument_identity",
                        "title": "Instrument Identity",
                        "decision_question": "Valid symbol?",
                        "description": "Check symbol.",
                        "required_inputs": ["symbol"],
                        "criteria": ["symbol exists"],
                        "tool_hooks": ["symbol_profile"],
                        "incoming_edges": [],
                        "outgoing_edges": [],
                        "source_refs": [],
                    }
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
                        "fail_effect": "reject",
                        "source_refs": [],
                    }
                ],
                "decision_rules": [],
                "extraction_warnings": [],
            }
        ),
        encoding="utf-8",
    )

    payload = server.Handler.route_api(
        None,
        "/api/method-system/workflow/evaluate",
        {},
        method="POST",
        body={"symbol": "nvda", "observations": {}},
    )

    assert payload["symbol"] == "NVDA"
    assert payload["method_version"] == "v1"
    assert payload["nodes"][0]["node_id"] == "instrument_identity"
```

- [ ] **Step 2: Run server tests and verify failure**

Run:

```bash
X_USERNAME=testuser X_USER_ID=1 /Users/littlemay/work/serenity-dashboard/.venv/bin/pytest tests/test_server.py -k "method or workflow" -q
```

Expected: fail because `/api/method-system/method` and `/api/method-system/workflow/evaluate` are not routed.

- [ ] **Step 3: Implement service helpers in both server surfaces**

In `scripts/server.py`, add import:

```python
from traderdash import workflow_engine
```

Add helpers near existing method helpers:

```python
def load_workflow_method(root=None):
    root = Path(root or ROOT)
    path = root / "data" / "local_system" / "method.v1.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def method_payload():
    return load_workflow_method()


def workflow_evaluate_payload(payload):
    method = load_workflow_method()
    body = dict(payload or {})
    if "observations" not in body:
        body["observations"] = {}
    return workflow_engine.evaluate_workflow_method(method, body)
```

Add routes in `Handler.route_api`:

```python
        if path == "/api/method-system/method":
            return method_payload()
```

and in POST routing:

```python
        if path == "/api/method-system/workflow/evaluate":
            return workflow_evaluate_payload(body)
```

In `webapp/dashboard_service.py`, add the same import and helper functions using `ROOT` from that module.

In `webapp/dashboard_api.py`, add:

```python
@router.get("/method-system/method")
def method():
    return svc.method_payload()


@router.post("/method-system/workflow/evaluate")
def workflow_evaluate(body: dict = Body(default={})):
    return svc.workflow_evaluate_payload(body)
```

- [ ] **Step 4: Run endpoint tests and verify pass**

Run:

```bash
X_USERNAME=testuser X_USER_ID=1 /Users/littlemay/work/serenity-dashboard/.venv/bin/pytest tests/test_server.py -k "method or workflow" -q
```

Expected: `2 passed`.

- [ ] **Step 5: Commit graph API**

Run:

```bash
git add scripts/server.py webapp/dashboard_service.py webapp/dashboard_api.py tests/test_server.py
git commit -m "feat: expose method workflow graph api"
```

---

### Task 6: Ticker-First Graph UI

**Files:**
- Modify: `dashboard/method-system.html`
- Modify: `dashboard/method-system.css`
- Modify: `dashboard/method-system.js`

- [ ] **Step 1: Replace method-system HTML with graph console structure**

Modify `dashboard/method-system.html` so `<main class="method-shell">` contains:

```html
  <main class="method-shell">
    <section class="hero-band">
      <div>
        <div class="eyebrow">Method Method Graph</div>
        <h1>Trade Workflow Console</h1>
        <p class="hero-copy">Run the method process against a ticker and inspect each decision node.</p>
      </div>
      <div class="hero-meta" id="methodMeta">Loading method graph...</div>
    </section>

    <section class="workflow-command">
      <form id="workflowForm" class="ticker-form">
        <label class="ticker-field">
          <span>Ticker</span>
          <input type="text" name="symbol" placeholder="NVDA" required autocomplete="off" />
        </label>
        <button type="submit" class="primary-button">Run Graph</button>
        <div id="workflowStatus" class="status-line">Ready.</div>
      </form>
    </section>

    <section class="workflow-layout">
      <section class="graph-pane">
        <div class="pane-header">
          <h2>Workflow Graph</h2>
          <div id="finalStatus" class="status-badge status-idle">idle</div>
        </div>
        <div id="workflowGraph" class="workflow-graph" aria-label="Method workflow graph"></div>
      </section>

      <aside class="detail-pane">
        <div class="pane-header">
          <h2>Node Detail</h2>
        </div>
        <div id="nodeDetail" class="node-detail empty">Select a node.</div>
      </aside>
    </section>

    <section class="method-pane history-pane">
      <div class="pane-header">
        <h2>Latest Result</h2>
      </div>
      <div id="resultPanel" class="result-panel empty">No workflow run yet.</div>
    </section>
  </main>
```

- [ ] **Step 2: Replace method-system JavaScript with graph behavior**

Modify `dashboard/method-system.js` with this structure:

```javascript
(function () {
  const state = {
    method: null,
    graphNodes: [],
    latest: null,
    selectedNodeId: null,
  };

  function $(id) {
    return document.getElementById(id);
  }

  async function jsonFetch(url, options) {
    const response = await fetch(url, options);
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    return response.json();
  }

  function escapeHtml(value) {
    return String(value || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function fmtStatus(status) {
    return String(status || "idle").replace(/_/g, " ");
  }

  function nodeFromMethod(node) {
    return {
      node_id: node.id,
      title: node.title,
      decision_question: node.decision_question,
      description: node.description,
      status: "idle",
      long: { status: "idle", checks: [], evidence: [], missing_inputs: [], next_actions: [] },
      short: { status: "idle", checks: [], evidence: [], missing_inputs: [], next_actions: [] },
      tool_hooks: node.tool_hooks || [],
      incoming_edges: node.incoming_edges || [],
      outgoing_edges: node.outgoing_edges || [],
      method_basis: node.source_refs || [],
    };
  }

  function setGraphStatus(status) {
    state.graphNodes = state.graphNodes.map((node) => ({ ...node, status }));
    renderGraph();
  }

  function renderMethodMeta() {
    const nodeCount = state.method?.workflow_nodes?.length || 0;
    const checkCount = state.method?.node_checks?.length || 0;
    $("methodMeta").textContent = `Version ${state.method.version} | ${nodeCount} nodes | ${checkCount} checks`;
  }

  function renderGraph() {
    const graph = $("workflowGraph");
    graph.innerHTML = state.graphNodes.map((node) => `
      <button class="graph-node status-${escapeHtml(node.status)} ${state.selectedNodeId === node.node_id ? "selected" : ""}"
              type="button"
              data-node-id="${escapeHtml(node.node_id)}">
        <span class="node-title">${escapeHtml(node.title)}</span>
        <span class="node-status">${escapeHtml(fmtStatus(node.status))}</span>
      </button>
    `).join("");

    graph.querySelectorAll(".graph-node").forEach((button) => {
      button.addEventListener("click", () => {
        state.selectedNodeId = button.dataset.nodeId;
        renderGraph();
        renderNodeDetail();
      });
    });
  }

  function renderNodeDetail() {
    const target = $("nodeDetail");
    const node = state.graphNodes.find((item) => item.node_id === state.selectedNodeId);
    if (!node) {
      target.className = "node-detail empty";
      target.textContent = "Select a node.";
      return;
    }

    function sideBlock(sideName, side) {
      const checks = (side.checks || []).map((check) => `
        <li><strong>${escapeHtml(check.status)}</strong> ${escapeHtml(check.title)}: ${escapeHtml(check.message)}</li>
      `).join("");
      return `
        <div class="side-block">
          <h4>${sideName}: ${escapeHtml(fmtStatus(side.status))}</h4>
          <ul>${checks || "<li>No checks for this side.</li>"}</ul>
        </div>
      `;
    }

    target.className = "node-detail";
    target.innerHTML = `
      <h3>${escapeHtml(node.title)}</h3>
      <p>${escapeHtml(node.decision_question)}</p>
      <p class="muted">${escapeHtml(node.description)}</p>
      <div class="tool-hooks">Tools: ${(node.tool_hooks || []).map(escapeHtml).join(", ") || "none"}</div>
      ${sideBlock("Long", node.long)}
      ${sideBlock("Short", node.short)}
    `;
  }

  function renderResult() {
    if (!state.latest) {
      $("finalStatus").className = "status-badge status-idle";
      $("finalStatus").textContent = "idle";
      $("resultPanel").className = "result-panel empty";
      $("resultPanel").textContent = "No workflow run yet.";
      return;
    }
    $("finalStatus").className = `status-badge status-${state.latest.final_status}`;
    $("finalStatus").textContent = fmtStatus(state.latest.final_status);
    const missing = (state.latest.missing_information || []).map((item) => `
      <li>${escapeHtml(item.title)}: ${escapeHtml((item.fields || []).join(", "))}</li>
    `).join("");
    const actions = (state.latest.next_actions || []).slice(0, 12).map((item) => `
      <li>${escapeHtml(item.side)} / ${escapeHtml(item.node_id)}: ${escapeHtml(item.message)}</li>
    `).join("");
    $("resultPanel").className = "result-panel";
    $("resultPanel").innerHTML = `
      <div class="summary-strip">
        <div>
          <div class="history-symbol">${escapeHtml(state.latest.symbol)}</div>
          <div class="history-meta">Method ${escapeHtml(state.latest.method_version)}</div>
        </div>
        <div class="status-badge status-${escapeHtml(state.latest.final_status)}">${escapeHtml(fmtStatus(state.latest.final_status))}</div>
      </div>
      ${missing ? `<div class="result-section"><h3>Missing Information</h3><ul class="plain-list">${missing}</ul></div>` : ""}
      ${actions ? `<div class="result-section"><h3>Next Actions</h3><ul class="plain-list">${actions}</ul></div>` : ""}
    `;
  }

  async function loadMethod() {
    state.method = await jsonFetch("/api/method-system/method");
    state.graphNodes = (state.method.workflow_nodes || []).map(nodeFromMethod);
    renderMethodMeta();
    renderGraph();
    renderNodeDetail();
    renderResult();
  }

  async function runWorkflow(event) {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    const symbol = String(formData.get("symbol") || "").trim().toUpperCase();
    if (!symbol) return;
    $("workflowStatus").textContent = "Running graph...";
    setGraphStatus("running");
    try {
      const result = await jsonFetch("/api/method-system/workflow/evaluate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ symbol, observations: {} }),
      });
      state.latest = result;
      state.graphNodes = result.nodes || [];
      if (!state.selectedNodeId && state.graphNodes.length) {
        state.selectedNodeId = state.graphNodes[0].node_id;
      }
      $("workflowStatus").textContent = "Complete.";
      renderGraph();
      renderNodeDetail();
      renderResult();
    } catch (error) {
      $("workflowStatus").textContent = error.message;
      setGraphStatus("error");
    }
  }

  async function init() {
    $("workflowForm").addEventListener("submit", runWorkflow);
    await loadMethod();
  }

  init().catch((error) => {
    $("workflowStatus").textContent = error.message;
    $("methodMeta").textContent = "Failed to load method graph.";
  });
})();
```

- [ ] **Step 3: Add graph CSS**

Add to `dashboard/method-system.css`:

```css
.workflow-command {
  max-width: 1180px;
  margin: 0 auto 18px;
}

.ticker-form {
  display: grid;
  grid-template-columns: minmax(220px, 420px) auto 1fr;
  gap: 12px;
  align-items: end;
}

.ticker-field {
  display: grid;
  gap: 6px;
  font-weight: 700;
}

.workflow-layout {
  max-width: 1180px;
  margin: 0 auto;
  display: grid;
  grid-template-columns: minmax(0, 1.6fr) minmax(320px, 0.9fr);
  gap: 18px;
}

.graph-pane,
.detail-pane {
  border: 1px solid rgba(28, 36, 30, 0.18);
  background: rgba(255, 252, 244, 0.78);
  border-radius: 8px;
  padding: 16px;
}

.workflow-graph {
  display: grid;
  grid-template-columns: repeat(3, minmax(160px, 1fr));
  gap: 14px;
}

.graph-node {
  min-height: 92px;
  border: 2px solid rgba(30, 35, 31, 0.18);
  border-radius: 8px;
  background: #f8f3e7;
  color: #1f261f;
  text-align: left;
  padding: 12px;
  cursor: pointer;
}

.graph-node.selected {
  outline: 3px solid rgba(20, 90, 52, 0.25);
}

.node-title,
.node-status {
  display: block;
}

.node-title {
  font-weight: 800;
}

.node-status {
  margin-top: 10px;
  font-size: 12px;
  text-transform: uppercase;
}

.status-idle,
.status-queued {
  background: #ece7dd;
}

.status-running {
  background: #dbeafe;
  border-color: #60a5fa;
}

.status-pass {
  background: #dcfce7;
  border-color: #22c55e;
}

.status-fail,
.status-blocked,
.status-reject {
  background: #fee2e2;
  border-color: #ef4444;
}

.status-missing,
.status-insufficient_data {
  background: #fef3c7;
  border-color: #f59e0b;
}

.status-mixed,
.status-conflicting_evidence,
.status-wait_for_timing,
.status-long_watchlist,
.status-short_watchlist {
  background: #ffedd5;
  border-color: #f97316;
}

.node-detail h3 {
  margin: 0 0 8px;
}

.tool-hooks,
.muted {
  color: #5f665f;
}

.side-block {
  margin-top: 16px;
}

.side-block ul {
  margin: 8px 0 0;
  padding-left: 18px;
}

@media (max-width: 900px) {
  .ticker-form,
  .workflow-layout {
    grid-template-columns: 1fr;
  }

  .workflow-graph {
    grid-template-columns: 1fr;
  }
}
```

- [ ] **Step 4: Run syntax checks**

Run:

```bash
/Users/littlemay/work/serenity-dashboard/.venv/bin/python -m py_compile scripts/server.py webapp/dashboard_api.py webapp/dashboard_service.py
```

Expected: no output.

- [ ] **Step 5: Commit graph UI**

Run:

```bash
git add dashboard/method-system.html dashboard/method-system.css dashboard/method-system.js
git commit -m "feat: render method workflow graph"
```

---

### Task 7: End-to-End Verification

**Files:**
- No source files unless verification reveals a concrete defect.

- [ ] **Step 1: Run method-system test suite**

Run:

```bash
X_USERNAME=testuser X_USER_ID=1 /Users/littlemay/work/serenity-dashboard/.venv/bin/pytest tests/test_method_notes_parser.py tests/test_method_schema.py tests/test_method_builder.py tests/test_workflow_engine.py tests/test_build_method_rulebook.py tests/test_local_system_schema.py tests/test_local_system_engine.py tests/test_local_system_store.py tests/test_server.py -q
```

Expected: all selected tests pass.

- [ ] **Step 2: Run Python syntax verification**

Run:

```bash
/Users/littlemay/work/serenity-dashboard/.venv/bin/python -m py_compile scripts/build_method_rulebook.py scripts/server.py webapp/dashboard_api.py webapp/dashboard_service.py traderdash/method_notes_parser.py traderdash/method_schema.py traderdash/method_builder.py traderdash/workflow_engine.py
```

Expected: no output.

- [ ] **Step 3: Start local server for smoke test**

Run:

```bash
X_USERNAME=testuser X_USER_ID=1 /Users/littlemay/work/serenity-dashboard/.venv/bin/python scripts/server.py --port 8789
```

Expected: server prints `dashboard: http://127.0.0.1:8789`.

- [ ] **Step 4: Smoke test graph endpoints**

In another shell, run:

```bash
curl -sS http://127.0.0.1:8789/api/method-system/method | /Users/littlemay/work/serenity-dashboard/.venv/bin/python -m json.tool >/tmp/method-method.json
curl -sS -X POST http://127.0.0.1:8789/api/method-system/workflow/evaluate \
  -H 'Content-Type: application/json' \
  -d '{"symbol":"NVDA","observations":{"setup":{"catalyst":"earnings in 40 days"},"signals":{"trend":"up"}}}' \
  | /Users/littlemay/work/serenity-dashboard/.venv/bin/python -m json.tool >/tmp/method-workflow-result.json
```

Expected:

```bash
grep -q '"workflow_nodes"' /tmp/method-method.json
grep -q '"nodes"' /tmp/method-workflow-result.json
grep -q '"final_status"' /tmp/method-workflow-result.json
```

Each `grep` exits `0`.

- [ ] **Step 5: Browser smoke check**

Open:

```text
http://127.0.0.1:8789/method-system.html
```

Expected visual state:

- Page shows `Trade Workflow Console`.
- Ticker input and `Run Graph` button are visible.
- Workflow nodes render as graph boxes.
- Running `NVDA` changes nodes to running briefly, then final colors render.
- Clicking a node shows long/short detail checks.

- [ ] **Step 6: Stop local server**

Stop the server process with `Ctrl-C` in the server shell.

- [ ] **Step 7: Commit verification fixes if needed**

If verification required code changes, commit them:

```bash
git add scripts/build_method_rulebook.py scripts/server.py webapp/dashboard_api.py webapp/dashboard_service.py traderdash/method_notes_parser.py traderdash/method_schema.py traderdash/method_builder.py traderdash/workflow_engine.py dashboard/method-system.html dashboard/method-system.css dashboard/method-system.js tests/test_method_notes_parser.py tests/test_method_schema.py tests/test_method_builder.py tests/test_workflow_engine.py tests/test_build_method_rulebook.py tests/test_server.py data/local_system/method.v1.json
git commit -m "fix: stabilize method workflow graph"
```

If no source changes were required, do not create a verification-only commit.

---

## Self-Review Checklist

- Spec coverage: parser, method method artifact, graph nodes/edges, deterministic long/short evaluation, one-call graph execution, graph UI, endpoint coverage, and tests are covered.
- Runtime determinism: final classification is generated by `workflow_engine.py`; the plan does not use an LLM at runtime.
- Graph UX: the UI loads graph nodes first, simulates `running`, then renders one completed backend response.
- Tool hooks: `tool_hooks` are stored in node definitions and rendered in node details; they are explicit extension points.
- Trader chat separation: no task modifies trader chat retrieval or adds method notes back into trader chat.

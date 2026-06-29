from datetime import datetime, timezone
from pathlib import Path

from meowstreet import method_notes_parser
from meowstreet.method_schema import normalize_method_payload


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

GRAPH_EDGES = {
    "instrument_identity": [
        "liquidity_tradability",
        "time_horizon_fit",
        "macro_regime",
    ],
    "liquidity_tradability": ["technical_timing", "portfolio_fit"],
    "time_horizon_fit": ["catalyst_window", "risk_position_sizing"],
    "macro_regime": ["sector_theme_context", "portfolio_fit"],
    "sector_theme_context": ["bottom_up_fundamental_bias"],
    "bottom_up_fundamental_bias": ["catalyst_window"],
    "catalyst_window": ["technical_timing", "risk_position_sizing"],
    "technical_timing": ["risk_position_sizing"],
    "portfolio_fit": ["risk_position_sizing", "final_synthesis"],
    "risk_position_sizing": ["final_synthesis"],
    "process_discipline": ["final_synthesis"],
    "final_synthesis": [],
}


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
    return refs


def _incoming_edges(node_id):
    return [source for source, targets in GRAPH_EDGES.items() if node_id in targets]


def _node(
    node_id,
    title,
    question,
    description,
    required_inputs,
    criteria,
    tool_hooks,
    keywords,
    documents,
):
    incoming = _incoming_edges(node_id)
    outgoing = GRAPH_EDGES.get(node_id, [])
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
        "source_refs": _refs_for_keywords(
            documents, "Methodology / Workflow", keywords
        ),
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
            [
                "No hard blocker exists.",
                "Long and short evidence are classified separately.",
            ],
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
            "source_refs": _refs_for_keywords(
                documents, "Concepts & Definitions", ["catalyst"]
            ),
        },
        {
            "id": "twenty_to_sixty_day_horizon",
            "title": "20-60 Day Time Horizon",
            "definition": "The method mandate for professional-style equity trades.",
            "supporting_only": False,
            "source_refs": _refs_for_keywords(
                documents, "Concepts & Definitions", ["20", "60", "time horizon"]
            ),
        },
        {
            "id": "self_sustainability",
            "title": "Self-Sustainability",
            "definition": "The trader must generate and evaluate ideas independently instead of copy trading.",
            "supporting_only": True,
            "source_refs": _refs_for_keywords(
                documents, "Concepts & Definitions", ["self-sustainability"]
            ),
        },
    ]


def _check(
    check_id,
    node_id,
    title,
    field,
    operator,
    side="both",
    value=None,
    required=False,
    fail_effect="watchlist",
    missing_message=None,
    source_refs=None,
):
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
    methodology_refs = _refs_for_keywords(
        documents, "Methodology / Workflow", ["framework", "trade idea"]
    )
    catalyst_refs = _refs_for_keywords(documents, "Actionable Checklist", ["catalyst"])
    return [
        _check(
            "symbol_present",
            "instrument_identity",
            "Symbol present",
            "symbol",
            "exists",
            required=True,
            fail_effect="reject",
            source_refs=methodology_refs,
        ),
        _check(
            "price_floor",
            "liquidity_tradability",
            "Price above floor",
            "metrics.price",
            "gte",
            value=10,
            required=True,
            fail_effect="reject",
            source_refs=methodology_refs,
        ),
        _check(
            "avg_dollar_volume",
            "liquidity_tradability",
            "Average dollar volume",
            "metrics.avg_dollar_volume_millions",
            "gte",
            value=25,
            required=False,
            fail_effect="watchlist",
            source_refs=methodology_refs,
        ),
        _check(
            "holding_period",
            "time_horizon_fit",
            "20-60 day holding period",
            "setup.expected_holding_days",
            "gte",
            value=20,
            required=False,
            fail_effect="wait_for_research",
            source_refs=methodology_refs,
        ),
        _check(
            "holding_period_max",
            "time_horizon_fit",
            "Holding period below investment threshold",
            "setup.expected_holding_days",
            "lte",
            value=60,
            required=False,
            fail_effect="wait_for_research",
            source_refs=methodology_refs,
        ),
        _check(
            "macro_regime_known",
            "macro_regime",
            "Macro regime known",
            "macro.regime",
            "exists",
            required=False,
            fail_effect="wait_for_research",
            source_refs=methodology_refs,
        ),
        _check(
            "theme_tagged",
            "sector_theme_context",
            "Theme tagged",
            "tags",
            "exists",
            required=False,
            fail_effect="watchlist",
            source_refs=methodology_refs,
        ),
        _check(
            "fundamental_bias",
            "bottom_up_fundamental_bias",
            "Fundamental bias stated",
            "fundamentals.bias",
            "exists",
            required=True,
            fail_effect="insufficient_data",
            source_refs=methodology_refs,
        ),
        _check(
            "catalyst_present",
            "catalyst_window",
            "Catalyst present",
            "setup.catalyst",
            "exists",
            required=True,
            fail_effect="wait_for_research",
            missing_message="Catalyst detail is missing.",
            source_refs=catalyst_refs,
        ),
        _check(
            "trend_known",
            "technical_timing",
            "Trend known",
            "signals.trend",
            "exists",
            required=False,
            fail_effect="wait_for_timing",
            source_refs=methodology_refs,
        ),
        _check(
            "entry_timing",
            "technical_timing",
            "Entry timing present",
            "signals.entry_timing",
            "exists",
            required=False,
            fail_effect="wait_for_timing",
            source_refs=methodology_refs,
        ),
        _check(
            "risk_stop",
            "risk_position_sizing",
            "Stop defined",
            "risk.stop",
            "exists",
            required=True,
            fail_effect="wait_for_research",
            source_refs=methodology_refs,
        ),
        _check(
            "position_size",
            "risk_position_sizing",
            "Position size defined",
            "risk.position_size",
            "exists",
            required=True,
            fail_effect="wait_for_research",
            source_refs=methodology_refs,
        ),
    ]


def _gap_warnings(documents):
    warnings = []
    for doc in documents:
        gap_text = doc.get("sections", {}).get(
            "Transcript Gaps / Incomplete Segments", ""
        )
        for line in gap_text.splitlines():
            line = line.strip()
            if not line or "none flagged" in line.lower():
                continue
            if line.startswith("-"):
                line = line[1:].strip()
            warnings.append(
                {
                    "document": doc["path"],
                    "section": "Transcript Gaps / Incomplete Segments",
                    "message": line,
                }
            )
    return warnings


def build_method_payload(notes_dir, version="v1", root=None):
    notes_dir = Path(notes_dir)
    root = (
        Path(root)
        if root is not None
        else notes_dir.parents[1]
        if len(notes_dir.parents) > 1
        else notes_dir
    )
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
            {
                "id": "hard_blocker_reject",
                "description": "Any failed required reject check rejects that side.",
            },
            {
                "id": "required_missing_insufficient",
                "description": "Missing required checks prevent qualification.",
            },
            {
                "id": "timing_missing_wait",
                "description": "Timing failures or missing timing inputs produce wait_for_timing.",
            },
        ],
        "extraction_warnings": _gap_warnings(documents),
    }
    return normalize_method_payload(payload)

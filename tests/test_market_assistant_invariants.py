import asyncio
import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api import app
from app.db import market_assistant as market_assistant_db
from app.db import us_rates_liquidity as us_rates_liquidity_db
from app.routers import market_assistant as market_assistant_router
from app.services import market_assistant as market_assistant_service
from app.services import market_setup_current
from app.tools import market_setup_evidence_facts
from app.tools import market_setup_explanation_snapshot
from app.tools import market_setup_predicates
from app.tools import market_setup_v2
from app.tools.market_assistant_plans import validate_task_plan

ROOT = Path(__file__).resolve().parents[1]
METHOD_CONTRACTS_PATH = (
    ROOT / "data" / "local_system" / "market_setup_confirmation_methods.v1.json"
)

client = TestClient(app)

RESOLVED_AT = "2026-08-10T01:00:00Z"


def decision_projection(payload):
    return {
        "macro_regime.code": payload["macro_regime"]["code"],
        "market_confirmation.code": payload["market_confirmation"]["code"],
        "market_confirmation.confirmation_test_count": payload["market_confirmation"][
            "confirmation_test_count"
        ],
        "market_setup.code": payload["market_setup"]["code"],
        "market_setup.agreement": payload["market_setup"]["agreement"],
        "portfolio_posture.code": payload["portfolio_posture"]["code"],
        "missing_inputs": payload["missing_inputs"],
        "next_triggers": payload["next_triggers"],
    }


def _monthly_period(effective_date="2026-06-30", reference_period="2026-06"):
    return {
        "effective_date": effective_date,
        "reference_period": reference_period,
        "release_date": "2026-07-01",
    }


def _daily_period(effective_date="2026-07-01", observation_date="2026-07-01"):
    return {
        "effective_date": effective_date,
        "observation_date": observation_date,
    }


def _expected_growth(direction="slowing"):
    return {
        "source_module": "ism_survey_synthesis",
        "method_version": "ism_survey_synthesis_v1",
        "facts": {
            "survey_growth_direction": {
                "direction": direction,
                "source_period": _monthly_period(),
            }
        },
    }


def _financial_conditions(vix=15.0, credit_status="healthy"):
    facts = {
        "macro_financial_conditions": {
            "relationship_to_growth_direction": "neutral",
            "source_period": _monthly_period(
                effective_date="2026-07-01", reference_period="2026-06"
            ),
        },
        "credit_conditions": {
            "status": credit_status,
            "source_period": _monthly_period(
                effective_date="2026-07-01", reference_period="2026-06"
            ),
        },
    }
    if vix is not None:
        facts["vix_level"] = {"level": vix, "source_period": _daily_period()}
    return {
        "source_module": "us_rates_liquidity",
        "method_version": "us_rates_liquidity_v1",
        "facts": facts,
    }


def _policy_response(m2_status="expanding"):
    facts = {
        "macro_policy_response": {
            "relationship_to_growth_direction": "conflicts",
            "source_period": _monthly_period(
                effective_date="2026-07-01", reference_period="2026-06"
            ),
        },
    }
    if m2_status is not None:
        facts["m2_liquidity"] = {
            "status": m2_status,
            "source_period": _monthly_period(
                effective_date="2026-07-01", reference_period="2026-06"
            ),
        }
    return {
        "source_module": "fomc_policy_tone",
        "method_version": "fomc_policy_tone_v1",
        "facts": facts,
    }


def _market_environment(state="bull_market"):
    return {
        "source_module": "market_phase",
        "method_version": "market_phase_v1",
        "facts": {
            "sp500_market_phase": {
                "phase": state,
                "source_period": _daily_period(),
            }
        },
    }


def _downside_inputs(vix=18.4):
    return {
        "expected_growth": _expected_growth("slowing"),
        "market_environment": _market_environment("bear_market"),
        "financial_conditions": _financial_conditions(vix=vix),
        "policy_response": _policy_response(m2_status="expanding"),
    }


def _observation_inputs(equity_breadth=50.0):
    return {
        "expected_growth": _expected_growth("slowing"),
        "market_environment": _market_environment("bull_market"),
        "financial_conditions": _financial_conditions(vix=15.0),
        "policy_response": _policy_response(m2_status="expanding"),
        "observation_only": {
            "equity_breadth": {
                "value": equity_breadth,
                "source_period": _daily_period(),
            }
        },
    }


def _snapshot_state(inputs):
    setup_result = market_setup_v2.build_market_setup_v2(**inputs)
    evidence = market_setup_evidence_facts.build_evidence_facts(
        setup_result=setup_result,
        inputs=inputs,
        evidence_layers=None,
        surface=market_setup_evidence_facts.load_explanation_surface(),
    )
    method_contracts = market_setup_v2.build_explanation_method_contracts()
    return market_setup_explanation_snapshot.build_snapshot_state(
        setup_result=setup_result,
        evidence=evidence,
        method_contracts=method_contracts,
        as_of="2026-08-10",
        evidence_through=setup_result["evidence_through"],
        input_registry_version="market_setup_input_registry_v1",
        explanation_surface_version="market_assistant_surface_v1",
    )


def _context_id_for(explanation_fingerprint, created_at):
    digest = hashlib.sha1(f"{explanation_fingerprint}{created_at}".encode()).hexdigest()
    return f"ctx_{digest[:12]}"


def _build_resolution(db_path, inputs, *, created_at, previous_context_id=None):
    state = _snapshot_state(inputs)
    context_id = _context_id_for(
        market_setup_explanation_snapshot.compute_explanation_fingerprint(state),
        created_at,
    )
    con = market_assistant_db.connect(db_path)
    try:
        snapshot = market_assistant_db.get_or_create_snapshot(
            con, state, context_id=context_id, created_at=created_at
        )
        previous = None
        if previous_context_id:
            previous = market_assistant_db.load_snapshot(con, previous_context_id)
        delta = market_setup_explanation_snapshot.build_semantic_delta(
            previous, snapshot
        )
    finally:
        con.close()
    return {
        "resolution": {
            "mode": "current",
            "resolved_at": created_at,
            "previous_context_id": previous_context_id,
            "current_context_id": snapshot["context_id"],
            "context_changed": previous_context_id != snapshot["context_id"],
        },
        "delta": delta,
        "snapshot": snapshot,
    }


def _config(**overrides):
    config = {
        "model": "assistant-model",
        "research_model": "research-model",
        "provider": "openai_responses",
        "research_enabled": True,
        "supports_web_search": True,
        "api_key": "sk-secret-test-key",
        "base_url": None,
    }
    config.update(overrides)
    return config


def _decision_plan():
    return {
        "intent": "decision_explanation",
        "context_mode": "current",
        "operations": [
            {"operation_id": "resolve_current_explanation", "parameters": {}}
        ],
        "answer_depth": "standard",
        "research_tier": None,
    }


def _decision_research_plan():
    return {
        "intent": "decision_explanation",
        "context_mode": "current",
        "operations": [
            {"operation_id": "resolve_current_explanation", "parameters": {}},
            {
                "operation_id": "research_focused",
                "parameters": {
                    "purpose": "current_events",
                    "queries": ["latest ism report"],
                    "expected_source_class": "official_publication",
                },
            },
        ],
        "answer_depth": "standard",
        "research_tier": "focused",
    }


def _research_result(researched_vix):
    return {
        "research_result_id": "res_1",
        "artifact_schema_version": "market_assistant_research_result_v1",
        "authority": "external_research",
        "market_setup_relation": "non_decision",
        "task": {
            "purpose": "current_events",
            "depth_tier": "focused",
            "queries": ["latest vix"],
            "expected_source_class": "official_publication",
        },
        "provider_metadata": {
            "provider_id": "openai_responses_web_search",
            "model": "research-model",
        },
        "searched_at": "2026-08-10T02:00:00Z",
        "search_calls": [{"query": "latest vix"}],
        "sources": [
            {
                "source_id": "src_1",
                "canonical_url": "https://www.cboe.com/vix",
                "title": "CBOE VIX",
                "publisher": "cboe.com",
                "publication_date": "2026-08-10",
                "event_date": "2026-08-10",
                "retrieved_at": "2026-08-10T02:00:00Z",
                "cited_spans": [f"The VIX closed at {researched_vix}."],
            }
        ],
        "findings": [
            {
                "finding_id": "fnd_1",
                "statement": f"The VIX closed at {researched_vix}.",
                "purpose": "current_events",
                "framing": "reported",
                "source_refs": ["src_1"],
                "cited_spans": [f"The VIX closed at {researched_vix}."],
            }
        ],
        "object_index": [
            {
                "object_type": "research_source",
                "object_id": "src_1",
                "authority": "external_research",
                "payload": {
                    "source_id": "src_1",
                    "canonical_url": "https://www.cboe.com/vix",
                    "title": "CBOE VIX",
                    "publisher": "cboe.com",
                    "publication_date": "2026-08-10",
                    "event_date": "2026-08-10",
                    "retrieved_at": "2026-08-10T02:00:00Z",
                    "cited_spans": [f"The VIX closed at {researched_vix}."],
                    "reported_level": researched_vix,
                },
            },
            {
                "object_type": "research_finding",
                "object_id": "fnd_1",
                "authority": "external_research",
                "payload": {
                    "finding_id": "fnd_1",
                    "statement": f"The VIX closed at {researched_vix}.",
                },
            },
        ],
        "result_hash": "a" * 64,
    }


def _decision_and_research_draft(context_id, *, accepted_vix, researched_vix):
    local_claim = {
        "claim_id": "c1",
        "purpose": "decision_explanation",
        "authority": "decision_fact",
        "refs": [
            {
                "artifact_id": context_id,
                "object_type": "evidence_fact",
                "object_id": "vix_level",
            }
        ],
        "template": "The accepted VIX level is {vix_level}.",
        "bindings": {
            "vix_level": {
                "value": accepted_vix,
                "source": {
                    "artifact_id": context_id,
                    "object_type": "evidence_fact",
                    "object_id": "vix_level",
                    "field": "accepted_values.level",
                },
            }
        },
    }
    external_claim = {
        "claim_id": "ext1",
        "purpose": "source_explanation",
        "authority": "external_research",
        "refs": [
            {
                "artifact_id": "res_1",
                "object_type": "research_source",
                "object_id": "src_1",
            }
        ],
        "template": "An external source reports the VIX at {ext_level}.",
        "bindings": {
            "ext_level": {
                "value": researched_vix,
                "source": {
                    "artifact_id": "res_1",
                    "object_type": "research_source",
                    "object_id": "src_1",
                    "field": "reported_level",
                },
            }
        },
    }
    return {
        "sections": [
            {"kind": "decision", "claims": [local_claim]},
            {"kind": "research", "claims": [external_claim]},
        ]
    }


def invalid_draft():
    return {
        "sections": [
            {
                "kind": "decision",
                "claims": [
                    {
                        "claim_id": "bad1",
                        "purpose": "decision_explanation",
                        "authority": "decision_fact",
                        "refs": [
                            {
                                "artifact_id": "ctx_x",
                                "object_type": "evidence_fact",
                                "object_id": "vix_level",
                            }
                        ],
                        "template": "The VIX level is 99.9 today. unvalidated model text.",
                        "bindings": {},
                    }
                ],
            }
        ]
    }


def _accepted_values_list(fact):
    normalized = dict(fact)
    normalized["accepted_values"] = [
        {"value": value} for value in fact["accepted_values"].values()
    ]
    return normalized


class _DummyCon:
    def close(self):
        pass


class _FakeAnswerDeps:
    def __init__(self, resolution, *, plan, draft, repair, research, config):
        self.resolution = resolution
        self._plan = plan
        self._draft = draft
        self._repair = repair
        self._research = research
        self.config = config
        self.db_path = ":memory:"
        self.llm_calls = []
        self.saved_trace = None
        self.saved_artifacts = None

    async def plan_llm(self, *, question, context_summary):
        self.llm_calls.append("plan")
        return validate_task_plan(self._plan)

    async def synthesize_llm(self, *, question, plan, context_summary, artifacts):
        self.llm_calls.append("draft")
        return self._draft

    async def repair_llm(
        self, *, question, plan, context_summary, artifacts, draft, validation_report
    ):
        self.llm_calls.append("repair")
        return self._repair

    def resolve_current_explanation(self, db_path, *, previous_context_id, resolved_at):
        return self.resolution

    def load_snapshot(self, con, context_id):
        return self.resolution["snapshot"]

    def connect(self, db_path):
        return _DummyCon()

    def load_knowledge_catalog(self):
        return {"version": "market_assistant_knowledge_v1", "records": []}

    def exploration(self, con, query, *, result_id, created_at):
        raise AssertionError("exploration must not run")

    async def acquire_research(
        self, provider, task, *, result_id, searched_at, explicit_deep=False
    ):
        return self._research

    def build_research_provider(self, config):
        return object()

    def save_bundle(self, con, *, artifacts, answer_trace):
        self.saved_trace = answer_trace
        self.saved_artifacts = list(artifacts)


class _AnswerResponse:
    def __init__(self, payload):
        self._payload = payload

    def __getitem__(self, key):
        return self._payload[key]

    def __getattr__(self, name):
        try:
            return self._payload[name]
        except KeyError:
            raise AttributeError(name) from None

    def snapshot_fact(self, fact_id):
        fact = next(
            fact
            for fact in self._payload["snapshot"]["evidence"]
            if fact["fact_id"] == fact_id
        )
        return _accepted_values_list(fact)


class _AnswerHarness:
    def __init__(self, db_path):
        self.db_path = db_path

    def answer(
        self, *, accepted_vix=18.4, researched_vix=None, draft=None, repair=None
    ):
        resolution = _build_resolution(
            self.db_path,
            _downside_inputs(vix=accepted_vix),
            created_at=RESOLVED_AT,
        )
        if researched_vix is not None:
            plan = _decision_research_plan()
            research = _research_result(researched_vix)
            draft = _decision_and_research_draft(
                resolution["snapshot"]["context_id"],
                accepted_vix=accepted_vix,
                researched_vix=researched_vix,
            )
        else:
            plan = _decision_plan()
            research = None
        deps = _FakeAnswerDeps(
            resolution,
            plan=plan,
            draft=draft,
            repair=repair,
            research=research,
            config=_config(),
        )
        payload = asyncio.run(
            market_assistant_service.answer_question(
                {
                    "question": "Why is the current setup Mild Risk-Off?",
                    "mode": "current",
                },
                dependencies=deps,
            )
        )
        trace = deps.saved_trace
        payload["trace_authorities"] = sorted(
            {
                claim["authority"]
                for section in (trace.get("structured_claims") or [])
                for claim in section["claims"]
            }
        )
        payload["validation_error_codes"] = trace["validation_error_codes"]
        payload["snapshot"] = resolution["snapshot"]
        return _AnswerResponse(payload)


class _SnapshotBuild:
    def __init__(self, snapshot):
        self.snapshot = snapshot

    def fact(self, fact_id):
        fact = next(
            fact for fact in self.snapshot["evidence"] if fact["fact_id"] == fact_id
        )
        return _accepted_values_list(fact)


class _SnapshotHarness:
    def build(self, vix_status="stale"):
        inputs = _downside_inputs(vix=18.4)
        if vix_status == "stale":
            inputs["financial_conditions"]["facts"]["vix_level"] = {
                "level": 18.4,
                "source_period": {},
            }
        state = _snapshot_state(inputs)
        snapshot = market_setup_explanation_snapshot.finalize_snapshot(
            state, context_id="ctx_snapshot", created_at=RESOLVED_AT
        )
        return _SnapshotBuild(snapshot)


class _HistoricalSnapshot:
    def __init__(self, snapshot):
        self.snapshot = snapshot

    def object(self, object_type, object_id):
        if object_type != "method_contract":
            raise ValueError(f"historical object is unknown: {object_type}")
        method = deepcopy(self.snapshot["method_contracts"]["methods"][object_id])
        predicates = method["decision_contract"]["predicates"]
        method["decision_contract"]["predicates"] = {
            direction: entry["predicate"] for direction, entry in predicates.items()
        }
        return method


class _SnapshotRepository:
    def __init__(self, db_path, monkeypatch):
        self.db_path = db_path
        self._monkeypatch = monkeypatch

    def save_with_vix_predicate(self, operand):
        inputs = _observation_inputs()
        state = _snapshot_state(inputs)
        embedded = state["method_contracts"]["methods"]["vix_confirmation_v2"][
            "decision_contract"
        ]["predicates"]["downside"]["predicate"]["operand"]
        assert embedded == operand
        context_id = _context_id_for(
            market_setup_explanation_snapshot.compute_explanation_fingerprint(state),
            RESOLVED_AT,
        )
        con = market_assistant_db.connect(self.db_path)
        try:
            snapshot = market_assistant_db.get_or_create_snapshot(
                con, state, context_id=context_id, created_at=RESOLVED_AT
            )
        finally:
            con.close()
        return {"context_id": snapshot["context_id"]}

    def install_current_vix_predicate(self, operand):
        payload = json.loads(METHOD_CONTRACTS_PATH.read_text(encoding="utf-8"))
        method = payload["methods"]["vix_confirmation_v2"]
        method["predicates"]["downside"]["operand"] = operand
        method["predicates"]["upside"]["operand"] = operand
        self._monkeypatch.setattr(
            market_setup_predicates,
            "load_method_contracts",
            lambda *args, **kwargs: payload,
        )

    def load_snapshot(self, context_id):
        con = market_assistant_db.connect(self.db_path)
        try:
            snapshot = market_assistant_db.load_snapshot(con, context_id)
        finally:
            con.close()
        return _HistoricalSnapshot(snapshot)


class _Resolver:
    def __init__(self, db_path):
        self.db_path = db_path

    def resolve(self, equity_breadth=50.0, previous_context_id=None):
        return _build_resolution(
            self.db_path,
            _observation_inputs(equity_breadth=equity_breadth),
            created_at=RESOLVED_AT,
            previous_context_id=previous_context_id,
        )


def _seed_schema(db_path):
    con = market_assistant_db.connect(db_path)
    try:
        market_setup_current._init_schema(con)
        con.commit()
    finally:
        con.close()


def _assistant_env(monkeypatch):
    monkeypatch.setenv("MARKET_ASSISTANT_MODEL", "test-model")
    monkeypatch.setenv("MARKET_ASSISTANT_RESEARCH_MODEL", "test-research-model")
    monkeypatch.setenv("MARKET_ASSISTANT_RESEARCH_PROVIDER", "openai_responses")
    monkeypatch.setenv("MARKET_ASSISTANT_RESEARCH_ENABLED", "false")
    monkeypatch.setenv("MARKET_ASSISTANT_RESEARCH_SUPPORTS_WEB_SEARCH", "false")
    monkeypatch.setenv("OPENAI_BASE_URL", "")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")


def _raise_unavailable(*args, **kwargs):
    raise RuntimeError("llm client is unavailable")


@pytest.fixture
def resolver(tmp_path):
    return _Resolver(tmp_path / "resolver.sqlite")


@pytest.fixture
def answer_harness(tmp_path):
    return _AnswerHarness(tmp_path / "assistant.sqlite")


@pytest.fixture
def snapshot_harness():
    return _SnapshotHarness()


@pytest.fixture
def snapshot_repository(tmp_path, monkeypatch):
    return _SnapshotRepository(tmp_path / "repository.sqlite", monkeypatch)


def test_market_setup_is_byte_identical_with_assistant_enabled_or_unavailable(
    monkeypatch, tmp_path
):
    _assistant_env(monkeypatch)
    db_path = tmp_path / "market.sqlite"
    _seed_schema(db_path)
    monkeypatch.setattr(market_assistant_db, "DEFAULT_DB_PATH", db_path)
    monkeypatch.setattr(us_rates_liquidity_db, "DEFAULT_DB_PATH", db_path)
    monkeypatch.setattr(
        market_assistant_router, "_assistant_runtime", _raise_unavailable
    )

    before = client.get("/api/macro-dashboard/market-setup").json()
    response = client.post(
        "/api/market-assistant/questions",
        json={"question": "Why?", "mode": "current"},
    )
    assert response.status_code == 200
    assert response.json()["generation_status"] == "fallback"
    after = client.get("/api/macro-dashboard/market-setup").json()

    assert decision_projection(before) == decision_projection(after)


def test_watch_only_update_changes_explanation_context_not_market_setup(resolver):
    first = resolver.resolve(equity_breadth=50.0)
    second = resolver.resolve(
        equity_breadth=42.0, previous_context_id=first["snapshot"]["context_id"]
    )

    assert (
        first["snapshot"]["decision_fingerprint"]
        == second["snapshot"]["decision_fingerprint"]
    )
    assert (
        first["snapshot"]["explanation_fingerprint"]
        != second["snapshot"]["explanation_fingerprint"]
    )
    assert first["snapshot"]["results"] == second["snapshot"]["results"]


def test_external_vix_update_cannot_change_accepted_vix_or_posture(answer_harness):
    response = answer_harness.answer(accepted_vix=18.4, researched_vix=23.0)

    assert response.trace_authorities == ["decision_fact", "external_research"]
    assert response.snapshot["results"]["portfolio_posture"]["code"] == "mild_risk_off"
    assert response.snapshot_fact("vix_level")["accepted_values"][0]["value"] == 18.4


def test_stale_required_evidence_is_not_evaluated_as_false(snapshot_harness):
    fact = snapshot_harness.build(vix_status="stale").fact("vix_level")

    assert fact["participation"]["state"] == "not_applied"
    assert fact["decision_result"]["evaluation"] == {
        "state": "not_evaluated",
        "actual_value": fact["accepted_values"][0]["value"],
        "reason_code": "data_stale",
    }


def test_historical_snapshot_uses_frozen_v2_predicate_after_contract_upgrade(
    snapshot_repository,
):
    context = snapshot_repository.save_with_vix_predicate(20.0)
    snapshot_repository.install_current_vix_predicate(22.0)
    historical = snapshot_repository.load_snapshot(context["context_id"])

    predicate = historical.object("method_contract", "vix_confirmation_v2")[
        "decision_contract"
    ]["predicates"]["downside"]
    assert predicate["operand"] == 20.0


def test_unvalidated_draft_and_failed_repair_keeps_initial_draft_visible(
    answer_harness,
):
    response = answer_harness.answer(draft=invalid_draft(), repair=invalid_draft())

    assert response["generation_status"] == "validation_failed_visible"
    assert response["validation_error_codes"]
    assert "unvalidated model text" in response["answer_text"]

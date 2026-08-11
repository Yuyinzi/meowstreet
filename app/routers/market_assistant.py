import json
from typing import Literal

from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field
from pydantic import ValidationError

from app.db import market_assistant as market_assistant_db
from app.llm import build_async_client
from app.llm import load_market_assistant_config
from app.services import market_assistant as market_assistant_service
from app.services.market_assistant_exploration import execute_exploration
from app.services.market_assistant_llm import complete_structured
from app.services.market_assistant_llm import plan_question
from app.services.market_assistant_research import build_research_provider
from app.services.market_setup_current import resolve_current_explanation
from app.tools.market_assistant_answers import _AnswerDraft as AnswerDraftSchema
from app.tools.market_assistant_knowledge import load_knowledge_catalog

router = APIRouter(prefix="/api/market-assistant", tags=["market-assistant"])

_ARTIFACT_CORRUPTION_PREFIXES = frozenset(
    {
        "answer trace is invalid",
        "explanation snapshot integrity check failed",
        "artifact payload is invalid",
        "artifact object index is required",
        "artifact object is invalid",
        "artifact object is duplicated",
        "artifact primary authority is not permitted",
        "artifact market setup relation is invalid",
        "artifact authority is not permitted",
        "artifact reference is not found",
        "artifact object is not found",
        "artifact reference is invalid",
    }
)


class _QuestionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1)
    mode: Literal["current", "historical"] = "current"
    context_id: str | None = None
    previous_context_id: str | None = None
    conversation_id: str | None = None
    deep_research_requested: bool = False


def _assistant_runtime():
    config = load_market_assistant_config()
    client = build_async_client(config, error_context="market assistant")
    return client, config["model"]


async def _plan_llm(*, question, context_summary):
    client, model = _assistant_runtime()
    return await plan_question(
        client, model=model, question=question, context_summary=context_summary
    )


async def _synthesize_llm(*, question, plan, context_summary, artifacts):
    client, model = _assistant_runtime()
    prompt = _synthesis_prompt(question, plan, context_summary, artifacts)
    return await complete_structured(
        client, model=model, prompt=prompt, schema_type=AnswerDraftSchema
    )


async def _repair_llm(
    *,
    question,
    plan,
    context_summary,
    artifacts,
    draft,
    validation_report,
):
    client, model = _assistant_runtime()
    prompt = _repair_prompt(
        question, plan, context_summary, artifacts, draft, validation_report
    )
    return await complete_structured(
        client, model=model, prompt=prompt, schema_type=AnswerDraftSchema
    )


def _synthesis_prompt(question, plan, context_summary, artifacts):
    return [
        {
            "role": "system",
            "content": (
                "You are the Market Setup assistant. Produce a StructuredAnswerDraft "
                "for the question using only the provided artifacts."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "question": question,
                    "plan": plan,
                    "context_summary": context_summary,
                    "artifacts": artifacts,
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
        },
    ]


def _repair_prompt(
    question, plan, context_summary, artifacts, draft, validation_report
):
    return [
        {
            "role": "system",
            "content": (
                "You are the Market Setup assistant. Repair the StructuredAnswerDraft "
                "using the validation report while keeping the same artifacts."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "question": question,
                    "plan": plan,
                    "context_summary": context_summary,
                    "artifacts": artifacts,
                    "draft": draft,
                    "validation_report": validation_report,
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
        },
    ]


def _build_dependencies():
    return {
        "config": load_market_assistant_config(),
        "db_path": market_assistant_db.DEFAULT_DB_PATH,
        "plan_llm": _plan_llm,
        "synthesize_llm": _synthesize_llm,
        "repair_llm": _repair_llm,
        "build_research_provider": build_research_provider,
        "exploration": execute_exploration,
        "load_knowledge_catalog": load_knowledge_catalog,
        "save_bundle": market_assistant_db.save_answer_bundle,
        "resolve_current_explanation": resolve_current_explanation,
    }


def _validate_question_request(body):
    if not isinstance(body, dict) or not str(body.get("question") or "").strip():
        raise ValueError("question is required")
    try:
        validated = _QuestionRequest.model_validate(body)
    except ValidationError as exc:
        raise ValueError("question request is invalid") from exc
    return validated.model_dump()


def _is_artifact_corruption(exc):
    if not isinstance(exc, ValueError):
        return False
    message = str(exc)
    return any(message.startswith(prefix) for prefix in _ARTIFACT_CORRUPTION_PREFIXES)


@router.post("/questions")
async def market_assistant_questions(body: dict = Body(default={})):
    try:
        request = _validate_question_request(body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if request["mode"] == "historical" and not request.get("context_id"):
        raise HTTPException(status_code=400, detail="context id is required")
    try:
        return await market_assistant_service.answer_question(
            request, dependencies=_build_dependencies()
        )
    except ValueError as exc:
        if _is_artifact_corruption(exc):
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail="market assistant service is unavailable"
        ) from exc


@router.get("/traces/{answer_trace_id}")
def market_assistant_trace(answer_trace_id: str):
    con = market_assistant_db.connect(market_assistant_db.DEFAULT_DB_PATH)
    try:
        trace = market_assistant_db.load_answer_trace(con, answer_trace_id)
    except ValueError as exc:
        if _is_artifact_corruption(exc):
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail="market assistant service is unavailable"
        ) from exc
    finally:
        con.close()
    if trace is None:
        raise HTTPException(status_code=404, detail="answer trace is not found")
    return trace

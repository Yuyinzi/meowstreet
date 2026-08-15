import json
import logging
import secrets
from time import monotonic
from typing import Literal

from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import StreamingResponse
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
from app.services.market_assistant_llm import stream_response_turn
from app.services.market_assistant_research import build_research_provider
from app.services.market_setup_current import resolve_current_explanation
from app.tools.market_assistant_answers import _AnswerDraft as AnswerDraftSchema
from app.tools.market_assistant_answers import detect_answer_language
from app.tools.market_assistant_claim_audit import ClaimAuditSchema
from app.tools.market_assistant_knowledge import load_knowledge_catalog
from app.tools.market_assistant_plans import deterministic_plan

router = APIRouter(prefix="/api/market-assistant", tags=["market-assistant"])

STREAM_LOGGER = logging.getLogger("uvicorn.error")

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
    message_id: str | None = None
    conversation_bootstrap: list["_ConversationBootstrapMessage"] | None = Field(
        default=None, max_length=1000
    )
    deep_research_requested: bool = False
    external_search_requested: bool = False
    deep_analysis_requested: bool = Field(default=False, strict=True)
    tone: Literal[
        "beginner_cat", "professional_cat", "beginner_human", "professional_human"
    ] = "beginner_human"


class _ConversationBootstrapMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"]
    text: str = Field(min_length=1, max_length=50000)


_QuestionRequest.model_rebuild()


def _assistant_runtime():
    config = load_market_assistant_config()
    client = build_async_client(config, timeout=900.0, error_context="market assistant")
    return (
        client,
        config["model"],
        config["structured_output_mode"],
        config.get("reasoning_effort", "low"),
    )


async def _plan_llm(*, question, context_summary):
    deterministic = deterministic_plan(question)
    if deterministic["intent"] != "unsupported":
        return deterministic
    client, model, structured_output_mode, reasoning_effort = _assistant_runtime()
    return await plan_question(
        client,
        model=model,
        question=question,
        context_summary=context_summary,
        structured_output_mode=structured_output_mode,
        reasoning_effort=reasoning_effort,
    )


async def _synthesize_llm(
    *,
    question,
    plan,
    context_summary,
    artifacts,
    stream_observer=None,
    tone="beginner_human",
):
    client, model, structured_output_mode, reasoning_effort = _assistant_runtime()
    prompt = _synthesis_prompt(question, plan, context_summary, artifacts, tone=tone)
    return await complete_structured(
        client,
        model=model,
        prompt=prompt,
        schema_type=AnswerDraftSchema,
        structured_output_mode=structured_output_mode,
        reasoning_effort=reasoning_effort,
        stream_observer=stream_observer,
    )


async def _repair_llm(
    *,
    question,
    plan,
    context_summary,
    artifacts,
    draft,
    validation_report,
    tone="beginner_human",
):
    client, model, structured_output_mode, reasoning_effort = _assistant_runtime()
    prompt = _repair_prompt(
        question, plan, context_summary, artifacts, draft, validation_report, tone=tone
    )
    return await complete_structured(
        client,
        model=model,
        prompt=prompt,
        schema_type=AnswerDraftSchema,
        structured_output_mode=structured_output_mode,
        reasoning_effort=reasoning_effort,
    )


async def _stream_turn_llm(
    client,
    *,
    model,
    input_items,
    instructions,
    tools,
    reasoning_effort,
    observer=None,
):
    return await stream_response_turn(
        client,
        model=model,
        input_items=input_items,
        instructions=instructions,
        tools=tools,
        reasoning_effort=reasoning_effort,
        observer=observer,
    )


async def _claim_audit_llm(*, answer_text, explanation_view, artifact_projection):
    client, model, structured_output_mode, reasoning_effort = _assistant_runtime()
    prompt = _claim_audit_prompt(answer_text, explanation_view, artifact_projection)
    return await complete_structured(
        client,
        model=model,
        prompt=prompt,
        schema_type=ClaimAuditSchema,
        structured_output_mode=structured_output_mode,
        reasoning_effort=reasoning_effort,
    )


def _answer_language_label(question):
    return "Chinese" if detect_answer_language(question) == "zh" else "English"


def _tone_instructions(tone: str) -> str:
    if tone == "beginner_cat":
        return (
            "Tone: beginner_cat. "
            "Adopt the persona of 财财 (Caicai), a curious beginner cat learning finance. "
            "Use light cat-flavored framing and simple metaphors when they help explain, "
            "but never change Market Setup conclusions or invent facts. "
            "Stay warm, encouraging, and plain-language."
        )
    if tone == "professional_cat":
        return (
            "Tone: professional_cat. "
            "Adopt the persona of 财财 (Caicai), a market-savvy cat. "
            "You may use concise, professional terminology with a light feline observation "
            "style, but never change Market Setup conclusions or invent facts. "
            "Do not define common finance terms."
        )
    if tone == "professional_human":
        return (
            "Tone: professional_human. "
            "Adopt a professional human investor tone. Use concise terminology and "
            "direct conclusions. Do not define common finance terms. "
            "Never change Market Setup conclusions or invent facts."
        )
    return (
        "Tone: beginner_human. "
        "Adopt a plain, beginner-friendly human tone. Write for a financial beginner. "
        "Explain what the market state means before using technical terms, and define "
        "every financial term on first use. Never change Market Setup conclusions or "
        "invent facts."
    )


def _structured_answer_instructions(question, tone="beginner_human"):
    language = _answer_language_label(question)
    return (
        "You are the explanation layer for deterministic Market Setup v2. "
        "Produce a StructuredAnswerDraft using only the supplied artifacts. "
        f"Answer language: {language}. "
        + _tone_instructions(tone)
        + " "
        + (
            "Each claim template is final user-facing prose after placeholder "
            "substitution, not internal notes. Explain what the current market "
            "state means before using technical terms. For a standard setup answer, "
            "give one plain-language summary, up to three main reasons, conflicting "
            "or unconfirmed evidence, the approved general posture meaning, and "
            "backend-provided conditions that could change the conclusion. Define "
            "financial terms on first use. Preserve level versus direction and trend "
            "versus confirmation. Prefer labels and meanings; do not display internal "
            "codes, artifact IDs, object IDs, authority names, or schema fields unless "
            "the user explicitly asks for diagnostics. Use annotated artifact bindings "
            "for every factual value or enum. Each non-hypothetical binding must contain "
            "the supplied value and its exact artifact source. Every ref must match the "
            "claim authority. Split different authorities into separate claims. Do not "
            "invent facts, classifications, weights, thresholds, causality, predictions, "
            "materiality, allocations, or trading instructions. "
            "Serialize answer_text as the first top-level property. "
            "answer_text must exactly equal the deterministic rendering of sections "
            "and claims. Do not place markdown fences around the JSON object."
        )
    )


def _synthesis_prompt(
    question, plan, context_summary, artifacts, tone="beginner_human"
):
    return [
        {
            "role": "system",
            "content": _structured_answer_instructions(question, tone),
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
    question,
    plan,
    context_summary,
    artifacts,
    draft,
    validation_report,
    tone="beginner_human",
):
    return [
        {
            "role": "system",
            "content": _structured_answer_instructions(question, tone)
            + (
                " Repair the draft using only the validation report and the same "
                "evidence set. Do not acquire new evidence. Return the complete "
                "corrected StructuredAnswerDraft."
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


def _narration_instructions(tone="beginner_human"):
    return (
        "You are the Market Setup narration assistant. "
        + _tone_instructions(tone)
        + " "
        + (
            "Narrate the current market setup from the evidence. "
            "Always write for a financial beginner. "
            "Always answer the user's question before naming system labels. "
            "Use only supplied views and tool results. "
            "Do not display internal codes or artifact identifiers. "
            "When tools are needed, return tool calls only. "
            "When answering, return plain text only. "
            "Do not reinterpret or override Market Setup. "
            "Answer in the user's language. "
            "Do not invent facts, thresholds, or causality the evidence does not support. "
            "When evidence is unavailable, say it is unavailable rather than guessing."
        )
    )


def _narration_input_items(question, explanation_view, tool_results):
    return [
        {
            "type": "message",
            "role": "user",
            "content": [
                {
                    "type": "input_text",
                    "text": json.dumps(
                        {
                            "question": question,
                            "explanation_view": explanation_view,
                            "tool_results": tool_results,
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                }
            ],
        }
    ]


def _claim_audit_prompt(answer_text, explanation_view, artifact_projection):
    return [
        {
            "role": "system",
            "content": (
                "You are the Market Setup claim audit assistant. "
                "Audit the exact supplied answer string against the frozen "
                "explanation view and artifact projections. "
                "Each claim span must use exact offsets and exact text copied "
                "verbatim from the answer string. "
                "Return only a ClaimAudit matching the supplied schema. "
                "Do not alter the supplied answer wording or emit a corrected draft."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "answer_text": answer_text,
                    "explanation_view": explanation_view,
                    "artifact_projection": artifact_projection,
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
        },
    ]


def _new_request_id():
    return f"req_{secrets.token_hex(8)}"


def _build_dependencies(request):
    config = _load_market_assistant_config_or_none()
    tone = request.get("tone", "beginner_human")
    dependencies = {
        "config": config,
        "db_path": market_assistant_db.DEFAULT_DB_PATH,
        "plan_llm": _plan_llm,
        "synthesize_llm": lambda **kwargs: _synthesize_llm(tone=tone, **kwargs),
        "repair_llm": lambda **kwargs: _repair_llm(tone=tone, **kwargs),
        "stream_turn": _stream_turn_llm,
        "narration_instructions": lambda: _narration_instructions(tone=tone),
        "claim_audit_llm": _claim_audit_llm,
        "build_research_provider": build_research_provider,
        "exploration": execute_exploration,
        "load_knowledge_catalog": load_knowledge_catalog,
        "save_bundle": market_assistant_db.save_answer_bundle,
        "resolve_current_explanation": resolve_current_explanation,
        "request_id": _new_request_id(),
    }
    if config:
        dependencies["client"] = build_async_client(
            config, timeout=900.0, error_context="market assistant"
        )
    return dependencies


def _load_market_assistant_config_or_none():
    try:
        return load_market_assistant_config()
    except RuntimeError:
        return {}


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


async def _stream_answer_events(request, dependencies, started_at):
    request_id = dependencies.get("request_id")
    first_answer_delta_sent = False
    try:
        async for event in market_assistant_service.stream_answer_question(
            request, dependencies=dependencies
        ):
            if not first_answer_delta_sent and event.get("type") == "answer_delta":
                first_answer_delta_sent = True
                STREAM_LOGGER.info(
                    "market assistant stage stage=first_ndjson_answer_delta_sent "
                    "request_id=%s elapsed_seconds=%.2f",
                    request_id,
                    monotonic() - started_at,
                )
            yield _ndjson_line(event)
    except Exception:
        yield _ndjson_line(
            {"type": "error", "message": "market assistant service is unavailable"}
        )


def _ndjson_line(event):
    line = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
    return line.encode("utf-8", errors="replace").decode("utf-8") + "\n"


@router.post("/questions/stream")
async def market_assistant_questions_stream(body: dict = Body(default={})):
    started_at = monotonic()
    try:
        request = _validate_question_request(body)
        dependencies = _build_dependencies(request)
    except ValueError as exc:
        if _is_artifact_corruption(exc):
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if request["mode"] == "historical" and not request.get("context_id"):
        raise HTTPException(status_code=400, detail="context id is required")
    return StreamingResponse(
        _stream_answer_events(request, dependencies, started_at=started_at),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


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
            request, dependencies=_build_dependencies(request)
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

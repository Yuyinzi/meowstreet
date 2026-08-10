import json
from typing import Awaitable

from pydantic import BaseModel

from app.tools.market_assistant_plans import TaskPlanSchema
from app.tools.market_assistant_plans import registered_operation_ids
from app.tools.market_assistant_plans import validate_task_plan


async def complete_structured(
    client, *, model: str, prompt: list[dict], schema_type: type[BaseModel]
) -> Awaitable[dict]:
    response = await client.responses.parse(
        model=model,
        input=prompt,
        text_format=schema_type,
    )
    parsed = response.output_parsed
    if parsed is None:
        raise ValueError("structured response is unavailable")
    return parsed.model_dump(mode="json")


async def plan_question(
    client, *, model: str, question: str, context_summary: dict
) -> Awaitable[dict]:
    if not isinstance(question, str) or not question.strip():
        raise ValueError("question is required")
    if not isinstance(context_summary, dict):
        raise ValueError("context summary is required")
    prompt = _planning_prompt(question, context_summary)
    payload = await complete_structured(
        client,
        model=model,
        prompt=prompt,
        schema_type=TaskPlanSchema,
    )
    return validate_task_plan(payload)


def _planning_prompt(question, context_summary):
    operations_text = ", ".join(sorted(registered_operation_ids()))
    system_content = (
        "You are the Market Setup assistant planner. "
        "You must select operations only from the registered read-only operation registry: "
        f"{operations_text}. "
        "Every operation must carry bounded parameters only. "
        "Never include sql, file paths, urls, provider names, or credentials. "
        "Return a structured task plan matching the supplied schema."
    )
    user_content = (
        f"question: {question}\n"
        f"context summary: {json.dumps(context_summary, ensure_ascii=False, sort_keys=True)}"
    )
    return [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_content},
    ]

import json
from typing import Literal

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field


CHECKPOINT_SCHEMA_VERSION = "market_assistant_conversation_checkpoint_v1"


class _ConversationCheckpoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["market_assistant_conversation_checkpoint_v1"]
    through_sequence: int = Field(ge=1)
    preferred_language: Literal["en", "zh"]
    summary: str = Field(min_length=1, max_length=8000)
    open_questions: list[str] = Field(max_length=8)
    created_at: str = Field(min_length=1)


def estimate_provider_tokens(provider_items):
    if not isinstance(provider_items, list):
        raise ValueError("provider items are required")
    text = json.dumps(provider_items, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    ascii_count = sum(char.isascii() for char in text)
    non_ascii_count = len(text) - ascii_count
    character_estimate = (ascii_count + 3) // 4 + non_ascii_count
    byte_estimate = (len(text.encode("utf-8")) + 3) // 4
    return max(1, character_estimate, byte_estimate)


def should_compact(provider_items, *, context_window_tokens, threshold_ratio=0.8):
    if not isinstance(context_window_tokens, int) or context_window_tokens < 1:
        raise ValueError("context window tokens is invalid")
    if not isinstance(threshold_ratio, (int, float)) or not 0 < threshold_ratio < 1:
        raise ValueError("context threshold ratio is invalid")
    return estimate_provider_tokens(provider_items) >= int(
        context_window_tokens * threshold_ratio
    )


def build_checkpoint(*, messages, preferred_language, created_at):
    if preferred_language not in {"en", "zh"}:
        raise ValueError("conversation preferred language is invalid")
    if not isinstance(messages, list) or not messages:
        raise ValueError("conversation messages are required")
    through_sequence = messages[-1].get("sequence")
    if not isinstance(through_sequence, int) or through_sequence < 1:
        raise ValueError("conversation sequence is invalid")
    fragments = []
    remaining = 7600
    for message in reversed(messages):
        display = message.get("display") or {}
        role = display.get("role")
        text = str(display.get("text") or "").strip()
        if role not in {"user", "assistant"} or not text:
            continue
        prefix = "User" if role == "user" else "Assistant"
        fragment = f"{prefix}: {text[:500]}"
        if len(fragment) > remaining:
            fragment = fragment[:remaining]
        fragments.append(fragment)
        remaining -= len(fragment)
        if remaining <= 0:
            break
    summary = "\n".join(reversed(fragments))
    payload = _ConversationCheckpoint(
        schema_version=CHECKPOINT_SCHEMA_VERSION,
        through_sequence=through_sequence,
        preferred_language=preferred_language,
        summary=summary,
        open_questions=[],
        created_at=created_at,
    )
    return payload.model_dump(mode="json")


def validate_checkpoint(payload):
    return _ConversationCheckpoint.model_validate(payload).model_dump(mode="json")

from app.tools.market_assistant_conversation import build_checkpoint
from app.tools.market_assistant_conversation import estimate_provider_tokens
from app.tools.market_assistant_conversation import should_compact
from app.db import market_assistant as market_assistant_db
from app.services import market_assistant


def test_checkpoint_is_schema_validated_and_bounded_from_display_history():
    checkpoint = build_checkpoint(
        messages=[
            {
                "sequence": 1,
                "display": {"role": "user", "text": "现在市场怎么样？"},
            },
            {
                "sequence": 2,
                "display": {"role": "assistant", "text": "市场温和偏积极。"},
            },
        ],
        preferred_language="zh",
        created_at="2026-08-14T00:00:00Z",
    )

    assert checkpoint["schema_version"] == "market_assistant_conversation_checkpoint_v1"
    assert checkpoint["through_sequence"] == 2
    assert checkpoint["preferred_language"] == "zh"
    assert "现在市场怎么样" in checkpoint["summary"]


def test_context_projection_compacts_at_eighty_percent_of_configured_budget():
    items = [
        {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": "x" * 800}],
        }
    ]

    assert estimate_provider_tokens(items) > 0
    assert should_compact(items, context_window_tokens=200, threshold_ratio=0.8)
    assert not should_compact(items, context_window_tokens=10000, threshold_ratio=0.8)


def test_token_estimate_is_conservative_for_chinese_text():
    text = "市场正在改善，但信贷条件仍有分歧。" * 100
    items = [
        {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": text}],
        }
    ]

    assert estimate_provider_tokens(items) >= len(text)


def test_neutral_followup_inherits_persisted_language_and_provider_history(tmp_path):
    db_path = tmp_path / "market.sqlite"
    con = market_assistant_db.connect(db_path)
    try:
        market_assistant_db.append_conversation_message(
            con,
            conversation_id="conv_zh",
            preferred_language="zh",
            message={
                "message_id": "old_answer",
                "created_at": "2026-08-14T00:00:00Z",
                "display": {"role": "assistant", "text": "你想继续了解 VIX 还是信贷？"},
                "provider_items": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [
                            {"type": "output_text", "text": "你想继续了解 VIX 还是信贷？"}
                        ],
                    }
                ],
            },
        )
    finally:
        con.close()
    deps = {
        "db_path": str(db_path),
        "config": {"context_window_tokens": 32768, "conversation_compaction_ratio": 0.8},
    }

    prepared = market_assistant._prepare_conversation_request(
        {"question": "ok", "conversation_id": "conv_zh", "message_id": "new_question"},
        deps,
        str(db_path),
    )

    assert prepared["answer_language"] == "zh"
    assert prepared["provider_history"][0]["content"][0]["text"] == "你想继续了解 VIX 还是信贷？"
    assert prepared["conversation_context"]["conversation_id"] == "conv_zh"
    assert prepared["conversation_context"]["provider_history_item_count"] == 1
    assert len(prepared["conversation_context"]["provider_history_hash"]) == 64


def test_short_indicator_followup_keeps_conversation_language(tmp_path):
    db_path = tmp_path / "market.sqlite"
    con = market_assistant_db.connect(db_path)
    try:
        market_assistant_db.append_conversation_message(
            con,
            conversation_id="conv_zh",
            preferred_language="zh",
            message={
                "message_id": "old_answer",
                "created_at": "2026-08-14T00:00:00Z",
                "display": {"role": "assistant", "text": "你想继续了解 VIX 还是信贷？"},
                "provider_items": [],
            },
        )
    finally:
        con.close()

    prepared = market_assistant._prepare_conversation_request(
        {"question": "VIX?", "conversation_id": "conv_zh", "message_id": "new_question"},
        {
            "db_path": str(db_path),
            "config": {
                "context_window_tokens": 32768,
                "conversation_compaction_ratio": 0.8,
            },
        },
        str(db_path),
    )

    assert prepared["answer_language"] == "zh"


def test_explicit_language_request_changes_conversation_language():
    assert market_assistant._conversation_language("Please answer in English", "zh") == "en"
    assert market_assistant._conversation_language("请用中文回答", "en") == "zh"


def test_empty_backend_conversation_bootstraps_existing_display_history(tmp_path):
    db_path = tmp_path / "market.sqlite"

    prepared = market_assistant._prepare_conversation_request(
        {
            "question": "ok",
            "conversation_id": "conv_migrated",
            "message_id": "new_question",
            "conversation_bootstrap": [
                {"role": "user", "text": "当前市场怎么样？"},
                {"role": "assistant", "text": "你想继续了解 VIX 还是信贷？"},
            ],
        },
        {
            "db_path": str(db_path),
            "config": {
                "context_window_tokens": 32768,
                "conversation_compaction_ratio": 0.8,
            },
        },
        str(db_path),
    )

    assert prepared["answer_language"] == "zh"
    assert [item["role"] for item in prepared["provider_history"]] == [
        "user",
        "assistant",
    ]
    con = market_assistant_db.connect(db_path)
    try:
        history = market_assistant_db.load_conversation_history(con, "conv_migrated")
    finally:
        con.close()
    assert [item["display"]["text"] for item in history["messages"]] == [
        "当前市场怎么样？",
        "你想继续了解 VIX 还是信贷？",
    ]


def test_preparation_compacts_history_over_configured_budget(tmp_path):
    db_path = tmp_path / "market.sqlite"
    con = market_assistant_db.connect(db_path)
    try:
        for index in range(3):
            market_assistant_db.append_conversation_message(
                con,
                conversation_id="conv_compact",
                preferred_language="en",
                message={
                    "message_id": f"old_{index}",
                    "created_at": "2026-08-14T00:00:00Z",
                    "display": {"role": "user", "text": "x" * 800},
                    "provider_items": [
                        {
                            "type": "message",
                            "role": "user",
                            "content": [{"type": "input_text", "text": "x" * 800}],
                        }
                    ],
                },
            )
    finally:
        con.close()
    deps = {
        "db_path": str(db_path),
        "config": {"context_window_tokens": 100, "conversation_compaction_ratio": 0.8},
    }

    prepared = market_assistant._prepare_conversation_request(
        {"question": "continue", "conversation_id": "conv_compact", "message_id": "new"},
        deps,
        str(db_path),
    )

    assert "Conversation checkpoint:" in prepared["provider_history"][0]["content"][0]["text"]

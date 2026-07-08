import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import llm
from app.db import us_rates_liquidity
from app.tools import us_rates_liquidity as us_rates_liquidity_tool


DEFAULT_MODEL = "gpt-4.1-mini"
TONE = "trader_cat"


def build_prompt(snapshot):
    return "\n".join(
        [
            "You are a disciplined trader cat explaining a fixed credit-condition snapshot.",
            "Do not change the regime. Do not give buy or sell instructions.",
            "Use concise, practical language. One light cat-flavored phrase is allowed.",
            "Return strict JSON with keys text_en and text_zh.",
            f"Snapshot: {json.dumps(snapshot, sort_keys=True, ensure_ascii=False)}",
        ]
    )


def parse_response(content):
    parsed = json.loads(content)
    text_en = str(parsed.get("text_en") or "").strip()
    text_zh = str(parsed.get("text_zh") or "").strip()
    if not text_en:
        raise ValueError("ai interpretation text_en is required")
    if not text_zh:
        raise ValueError("ai interpretation text_zh is required")
    return {"text_en": text_en, "text_zh": text_zh}


async def generate_with_openai(client, model, snapshot):
    response = await client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "user",
                "content": build_prompt(snapshot),
            }
        ],
        response_format={"type": "json_object"},
    )
    return parse_response(response.choices[0].message.content)


def load_current_snapshot(con):
    latest_points = us_rates_liquidity.load_latest_points(con)
    latest_macro = us_rates_liquidity.load_latest_macro_indicator_points(con)
    credit_rate_points = us_rates_liquidity.load_rate_points_for_series(
        con,
        ["treasury_10y"],
    )
    credit_macro_points = us_rates_liquidity.load_macro_indicator_points_for_series(
        con,
        ["aaa_corporate_yield", "bbb_corporate_yield", "ccc_corporate_yield"],
    )
    payload = us_rates_liquidity_tool.build_dashboard_payload(
        us_rates_liquidity.load_rate_series(con),
        latest_points,
        latest_macro,
        credit_rate_points=credit_rate_points,
        credit_macro_points=credit_macro_points,
        credit_macro_series_points=credit_macro_points,
    )
    return payload["credit_interpretation_snapshot"]


def interpretation_row(snapshot, generated, model):
    return {
        "scope": snapshot["scope"],
        "as_of": snapshot.get("as_of"),
        "snapshot_hash": snapshot["hash"],
        "prompt_version": snapshot["prompt_version"],
        "model": model,
        "tone": TONE,
        "status": snapshot["status"],
        "text_en": generated["text_en"],
        "text_zh": generated["text_zh"],
        "metrics_json": json.dumps(snapshot, sort_keys=True, ensure_ascii=False),
        "generated_at": datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
    }


async def async_main(argv=None):
    parser = argparse.ArgumentParser(
        description="Generate stored AI interpretation for US credit conditions"
    )
    parser.add_argument(
        "--db-path", type=Path, default=us_rates_liquidity.DEFAULT_DB_PATH
    )
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--openai-api-key", default="")
    parser.add_argument("--openai-base-url", default="")
    args = parser.parse_args(argv)
    con = us_rates_liquidity.connect(args.db_path)
    try:
        snapshot = load_current_snapshot(con)
        existing = us_rates_liquidity.load_ai_interpretation(
            con,
            snapshot["scope"],
            snapshot["hash"],
        )
        if existing and not args.force:
            print(f"credit interpretation unchanged: {snapshot['hash']}")
            return 0
        config = llm.load_openai_config(args, root=ROOT)
        client = llm.build_async_client(config, max_retries=0, timeout=60)
        model = config["model"]
        generated = await generate_with_openai(client, model, snapshot)
        saved = us_rates_liquidity.replace_ai_interpretation(
            con,
            interpretation_row(snapshot, generated, model),
        )
        print(f"credit interpretation generated: {saved['interpretations']}")
        print(f"snapshot_hash: {snapshot['hash']}")
        return 0
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1
    finally:
        con.close()


def main(argv=None):
    return asyncio.run(async_main(argv))


if __name__ == "__main__":
    raise SystemExit(main())

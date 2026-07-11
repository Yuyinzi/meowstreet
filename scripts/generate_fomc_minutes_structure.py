import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import llm
from app.db import us_rates_liquidity
from app.tools import fomc_minutes_structure


MINUTES_MODEL_SPECS = [
    {
        "name": "extractor_model",
        "arg_name": "extractor_model",
        "env_names": ["FOMC_MINUTES_EXTRACTOR_MODEL", "OPENAI_MODEL"],
        "label": "FOMC minutes extractor model",
    },
    {
        "name": "reviewer_model",
        "arg_name": "reviewer_model",
        "env_names": ["FOMC_MINUTES_REVIEWER_MODEL", "OPENAI_MODEL"],
        "label": "FOMC minutes reviewer model",
    },
]


def target_events(events, minutes_docs, statement_tones):
    return [
        event
        for event in events
        if event["event_id"] in minutes_docs and event["event_id"] in statement_tones
    ]


def should_skip_existing_extraction(existing, source_hash, force):
    return bool(existing and existing.get("source_hash") == source_hash and not force)


async def call_json(client, model, prompt):
    response = await client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0,
        top_p=1,
        seed=1,
    )
    return response.choices[0].message.content


async def generate_event_minutes_structure(
    con,
    event,
    minutes_document,
    statement_tone,
    client,
    models,
    max_rounds,
    force,
):
    existing = us_rates_liquidity.load_macro_event_tone_extraction(
        con,
        event["event_id"],
        "minutes",
        minutes_document["source_hash"],
    )
    if should_skip_existing_extraction(
        existing, minutes_document["source_hash"], force
    ):
        print("fomc minutes structure skipped:")
        print(f"  event: {event['event_id']}")
        print(f"  source_hash: {minutes_document['source_hash']}")
        return 0

    feedback = []
    reviewer_feedback = []
    final_feedback = []
    extraction = None
    extraction_status = "rejected"
    rounds_used = 0
    for round_index in range(max_rounds):
        rounds_used = round_index + 1
        extractor_prompt = fomc_minutes_structure.build_extractor_prompt(
            event,
            statement_tone,
            minutes_document["text"],
            feedback,
        )
        content = await call_json(
            client,
            models["extractor_model"],
            extractor_prompt,
        )
        extraction = fomc_minutes_structure.parse_extractor_response(content)
        reviewer_prompt = fomc_minutes_structure.build_reviewer_prompt(
            event,
            statement_tone,
            minutes_document["text"],
            extraction,
        )
        review_content = await call_json(
            client,
            models["reviewer_model"],
            reviewer_prompt,
        )
        review = fomc_minutes_structure.parse_reviewer_response(review_content)
        final_feedback = review["feedback"]
        reviewer_feedback.extend(review["feedback"])
        if review["approved"]:
            extraction_status = "approved"
            break
        feedback = review["feedback"]

    if extraction is None:
        raise ValueError(f"fomc minutes extraction failed for {event['event_id']}")

    row = fomc_minutes_structure.tone_extraction_row(
        event["event_id"],
        minutes_document["source_hash"],
        statement_tone,
        extraction,
        reviewer_feedback,
        extraction_status,
        rounds_used,
        models["extractor_model"],
        models["reviewer_model"],
        datetime.now(UTC).isoformat(),
        final_feedback,
    )
    us_rates_liquidity.replace_macro_event_tone_extraction(con, row)
    print("fomc minutes structure saved:")
    print(f"  event: {event['event_id']}")
    print(f"  risk_focus: {extraction['risk_focus']}")
    print(f"  policy_conviction: {extraction['policy_conviction']}")
    print(f"  minutes_confirmation: {extraction['minutes_confirmation']}")
    print(f"  extraction_status: {extraction_status}")
    return 1


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Generate FOMC minutes structure extraction"
    )
    parser.add_argument(
        "--db-path", type=Path, default=us_rates_liquidity.DEFAULT_DB_PATH
    )
    target_group = parser.add_mutually_exclusive_group(required=True)
    target_group.add_argument("--event-id")
    target_group.add_argument("--all", action="store_true")
    parser.add_argument("--max-rounds", type=int, default=3)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--extractor-model", default="")
    parser.add_argument("--reviewer-model", default="")
    parser.add_argument("--openai-api-key", default="")
    parser.add_argument("--openai-base-url", default="")
    return parser.parse_args(argv)


def load_event_maps(con, events):
    minutes_docs = {}
    statement_tones = {}
    for event in events:
        minutes_doc = us_rates_liquidity.load_macro_event_document(
            con,
            event["event_id"],
            "minutes",
        )
        if minutes_doc:
            minutes_docs[event["event_id"]] = minutes_doc
        statement_doc = us_rates_liquidity.load_macro_event_document(
            con,
            event["event_id"],
            "statement",
        )
        if statement_doc:
            statement_tone = us_rates_liquidity.load_macro_event_tone_extraction(
                con,
                event["event_id"],
                "statement",
                statement_doc["source_hash"],
            )
            if statement_tone and statement_tone["extraction_status"] == "approved":
                statement_tones[event["event_id"]] = statement_tone
    return minutes_docs, statement_tones


async def async_main(argv=None):
    args = parse_args(argv)
    con = us_rates_liquidity.connect(args.db_path)
    try:
        events = us_rates_liquidity.load_macro_events(con, "fomc_meeting")
        if args.event_id:
            events = [event for event in events if event["event_id"] == args.event_id]
            if not events:
                raise ValueError(f"fomc event is unknown: {args.event_id}")
        minutes_docs, statement_tones = load_event_maps(con, events)
        events = target_events(events, minutes_docs, statement_tones)
        if not events:
            print("fomc_minutes_structure: 0")
            return 0
        llm_bundle = llm.build_async_client_bundle(
            args,
            root=ROOT,
            model_specs=MINUTES_MODEL_SPECS,
            max_retries=0,
            timeout=120,
            error_context="FOMC minutes structure extraction",
        )
        client = llm_bundle["client"]
        models = llm_bundle["models"]
        generated = 0
        failed = 0
        for event in events:
            try:
                generated += await generate_event_minutes_structure(
                    con,
                    event,
                    minutes_docs[event["event_id"]],
                    statement_tones[event["event_id"]],
                    client,
                    models,
                    args.max_rounds,
                    args.force,
                )
            except Exception as exc:
                failed += 1
                print("fomc minutes structure failed:", file=sys.stderr)
                print(f"  event: {event['event_id']}", file=sys.stderr)
                print(f"  reason: {exc}", file=sys.stderr)
                if not args.all:
                    return 1
                continue
        print(f"fomc_minutes_structure: {generated}")
        return 1 if failed else 0
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1
    finally:
        con.close()


def main(argv=None):
    return asyncio.run(async_main(argv))


if __name__ == "__main__":
    raise SystemExit(main())

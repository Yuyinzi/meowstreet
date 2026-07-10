import argparse
import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import llm
from app.db import us_rates_liquidity
from app.tools import fomc_policy_tone


def generated_at_now():
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


FOMC_TONE_MODEL_SPECS = [
    {
        "name": "extractor_model",
        "arg_name": "extractor_model",
        "env_names": ["FOMC_TONE_EXTRACTOR_MODEL", "OPENAI_MODEL"],
        "label": "FOMC tone extractor model",
    },
    {
        "name": "reviewer_model",
        "arg_name": "reviewer_model",
        "env_names": ["FOMC_TONE_REVIEWER_MODEL", "OPENAI_MODEL"],
        "label": "FOMC tone reviewer model",
    },
]


def previous_event_and_document(events, event_id, load_document):
    current = next((event for event in events if event["event_id"] == event_id), None)
    if not current:
        return None, None
    previous_events = [
        event for event in events if event.get("start_date") < current.get("start_date")
    ]
    for event in reversed(previous_events):
        document = load_document(event["event_id"])
        if document:
            return event, document
    return None, None


def _event_label(event):
    if not event:
        return "none"
    end_date = event.get("end_date") or event.get("start_date")
    return f"{event['event_id']} ({event.get('start_date')} to {end_date})"


def should_skip_existing_extraction(existing, force):
    return bool(existing) and not force


def _short_hash(document):
    if not document:
        return "none"
    return str(document.get("source_hash") or "")[:12] or "none"


def log_generation_context(
    event,
    current_document,
    previous_event,
    previous_document,
    models,
):
    print("fomc policy tone generation:")
    print(f"  current: {_event_label(event)}")
    print(f"  previous: {_event_label(previous_event)}")
    print(f"  statement_url: {current_document.get('url')}")
    print(f"  source_hash: {_short_hash(current_document)}")
    print(f"  previous_source_hash: {_short_hash(previous_document)}")
    print(f"  extractor_model: {models['extractor_model']}")
    print(f"  reviewer_model: {models['reviewer_model']}")


def log_generation_result(row):
    print("fomc policy tone saved:")
    print(f"  policy_action: {row['policy_action']}")
    print(f"  guidance_bias: {row['guidance_bias']}")
    print(f"  language_tone: {row['language_tone']}")
    print(f"  overall_bias: {row['overall_bias']}")
    print(f"  statement_tone: {row['statement_tone']}")
    print(f"  marker_tone: {row['marker_tone']}")
    print(f"  tone_change: {row['tone_change']}")
    print(f"  confidence: {row['confidence']}")
    print(f"  extraction_status: {row['extraction_status']}")
    print(f"  review_rounds: {row['review_rounds']}")


async def run_extract_review_loop(
    event,
    current_document,
    previous_event,
    previous_document,
    extract,
    review,
    max_rounds,
):
    feedback = []
    final_reviewer_feedback = []
    extraction = None
    for round_index in range(1, max_rounds + 1):
        try:
            extraction = await extract(
                fomc_policy_tone.build_extractor_prompt(
                    event,
                    current_document,
                    previous_event,
                    previous_document,
                    feedback=feedback,
                )
            )
        except ValueError as exc:
            feedback.append(f"Extractor output failed schema validation: {exc}")
            continue
        review_result = await review(
            fomc_policy_tone.build_reviewer_prompt(
                event,
                current_document,
                previous_document,
                extraction,
            )
        )
        feedback.extend(review_result["feedback"])
        final_reviewer_feedback = review_result["feedback"]
        if review_result["approved"]:
            return {
                "extraction": extraction,
                "reviewer_feedback": feedback,
                "final_reviewer_feedback": final_reviewer_feedback,
                "extraction_status": "approved",
                "review_rounds": round_index,
            }
    if extraction is None:
        raise ValueError(
            f"extractor did not return valid FOMC tone JSON after {max_rounds} rounds"
        )
    return {
        "extraction": extraction,
        "reviewer_feedback": feedback,
        "final_reviewer_feedback": final_reviewer_feedback,
        "extraction_status": "max_rounds_reached",
        "review_rounds": max_rounds,
    }


def run_extract_review_loop_sync(**kwargs):
    return asyncio.run(run_extract_review_loop(**kwargs))


async def _call_json(client, model, prompt, parser):
    response = await client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0,
    )
    return parser(response.choices[0].message.content)


def _check_skip(con, event, force):
    current_document = us_rates_liquidity.load_macro_event_document(
        con,
        event["event_id"],
        "statement",
    )
    if not current_document:
        print("fomc policy tone skipped:")
        print(f"  current: {_event_label(event)}")
        print("  reason: no statement document")
        return True
    existing = us_rates_liquidity.load_macro_event_tone_extraction(
        con,
        event["event_id"],
        "statement",
        current_document["source_hash"],
    )
    if should_skip_existing_extraction(existing, force):
        print("fomc policy tone skipped:")
        print(f"  current: {_event_label(event)}")
        print(f"  source_hash: {_short_hash(current_document)}")
        print(f"  existing_generated_at: {existing['generated_at']}")
        print(
            "  reason: existing extraction for this statement hash; use --force to regenerate"
        )
        return True
    return False


async def async_main(argv=None):
    parser = argparse.ArgumentParser(description="Generate FOMC policy tone extraction")
    parser.add_argument(
        "--db-path", type=Path, default=us_rates_liquidity.DEFAULT_DB_PATH
    )
    parser.add_argument("--event-id", required=True)
    parser.add_argument("--max-rounds", type=int, default=3)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--extractor-model", default="")
    parser.add_argument("--reviewer-model", default="")
    parser.add_argument("--openai-api-key", default="")
    parser.add_argument("--openai-base-url", default="")
    args = parser.parse_args(argv)
    con = us_rates_liquidity.connect(args.db_path)
    try:
        all_events = us_rates_liquidity.load_macro_events(con, "fomc_meeting")
        events = [event for event in all_events if event["event_id"] == args.event_id]
        if not events:
            raise ValueError(f"fomc event is unknown: {args.event_id}")
        event = events[0]
        if _check_skip(con, event, args.force):
            print("fomc_policy_tone: 0")
            return 0
        current_document = us_rates_liquidity.load_macro_event_document(
            con,
            event["event_id"],
            "statement",
        )
        llm_bundle = llm.build_async_client_bundle(
            args,
            root=ROOT,
            model_specs=FOMC_TONE_MODEL_SPECS,
            max_retries=0,
            timeout=120,
            error_context="FOMC tone extraction",
        )
        client = llm_bundle["client"]
        models = llm_bundle["models"]
        previous_event, previous_document = previous_event_and_document(
            all_events,
            event["event_id"],
            lambda event_id: us_rates_liquidity.load_macro_event_document(
                con,
                event_id,
                "statement",
            ),
        )
        log_generation_context(
            event,
            current_document,
            previous_event,
            previous_document,
            models,
        )
        result = await run_extract_review_loop(
            event,
            current_document,
            previous_event,
            previous_document,
            extract=lambda prompt: _call_json(
                client,
                models["extractor_model"],
                prompt,
                fomc_policy_tone.parse_extractor_response,
            ),
            review=lambda prompt: _call_json(
                client,
                models["reviewer_model"],
                prompt,
                fomc_policy_tone.parse_reviewer_response,
            ),
            max_rounds=args.max_rounds,
        )
        row = fomc_policy_tone.tone_extraction_row(
            event_id=event["event_id"],
            source_document_type="statement",
            source_hash=current_document["source_hash"],
            previous_event_id=previous_event["event_id"] if previous_event else None,
            extraction=result["extraction"],
            reviewer_feedback=result["reviewer_feedback"],
            extraction_status=result["extraction_status"],
            review_rounds=result["review_rounds"],
            extractor_model=models["extractor_model"],
            reviewer_model=models["reviewer_model"],
            generated_at=generated_at_now(),
            final_reviewer_feedback=result["final_reviewer_feedback"],
        )
        us_rates_liquidity.replace_macro_event_tone_extraction(con, row)
        log_generation_result(row)
        print("fomc_policy_tone: 1")
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

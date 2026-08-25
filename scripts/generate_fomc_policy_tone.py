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
    return (
        bool(existing and existing.get("extraction_status") == "approved") and not force
    )


def target_events(all_events, event_id=None, generate_all=False):
    if generate_all:
        return list(all_events)
    events = [event for event in all_events if event["event_id"] == event_id]
    if not events:
        raise ValueError(f"fomc event is unknown: {event_id}")
    return events


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


async def generate_event_tone(
    con,
    all_events,
    event,
    current_document,
    client,
    models,
    max_rounds,
    verbose=False,
    persist=True,
):
    previous_event, previous_document = previous_event_and_document(
        all_events,
        event["event_id"],
        lambda event_id: us_rates_liquidity.load_macro_event_document(
            con,
            event_id,
            "statement",
        ),
    )
    if verbose:
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
        max_rounds=max_rounds,
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
    if persist:
        us_rates_liquidity.replace_macro_event_tone_extraction(con, row)
    if verbose:
        log_generation_result(row)
    return row


_ORIGINAL_GENERATE_EVENT_TONE = generate_event_tone


def prepare_fomc_policy_tone(
    db_path, event_id, client, extractor_model, reviewer_model, max_rounds=3
):
    from app.services import macro_refresh_official

    return macro_refresh_official.prepare_fomc_policy_tone(
        db_path,
        event_id,
        client,
        extractor_model,
        reviewer_model,
        max_rounds=max_rounds,
    )


def persist_fomc_policy_tone(db_path, prepared_extraction):
    from app.services import macro_refresh_official

    return macro_refresh_official.persist_fomc_policy_tone(
        db_path, prepared_extraction
    )


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


def classify_events(con, events, force):
    classified = {"pending": [], "reused": [], "unavailable": []}
    for event in events:
        current_document = us_rates_liquidity.load_macro_event_document(
            con,
            event["event_id"],
            "statement",
        )
        if not current_document:
            classified["unavailable"].append(
                (event, {"reason": "no statement document"})
            )
            continue
        existing = us_rates_liquidity.load_macro_event_tone_extraction(
            con,
            event["event_id"],
            "statement",
            current_document["source_hash"],
        )
        if should_skip_existing_extraction(existing, force):
            classified["reused"].append((event, existing))
            continue
        classified["pending"].append((event, current_document))
    return classified


def _print_event_classification(event, status, detail):
    print(f"fomc policy tone {status}:")
    print(f"  event: {event['event_id']}")
    print(f"  current: {_event_label(event)}")
    if status == "reused":
        print(f"  source_hash: {_short_hash(detail)}")
        if detail.get("generated_at"):
            print(f"  existing_generated_at: {detail['generated_at']}")
        print(
            "  reason: existing extraction for this statement hash; use --force to regenerate"
        )
        return
    print(f"  reason: {detail.get('reason', 'unknown')}")


def _summary(generated, classified, failed):
    return (
        f"fomc_policy_tone: generated={generated} "
        f"reused={len(classified['reused'])} "
        f"unavailable={len(classified['unavailable'])} failed={failed}"
    )


async def async_main(argv=None):
    parser = argparse.ArgumentParser(description="Generate FOMC policy tone extraction")
    parser.add_argument(
        "--db-path", type=Path, default=us_rates_liquidity.DEFAULT_DB_PATH
    )
    target_group = parser.add_mutually_exclusive_group(required=True)
    target_group.add_argument("--event-id")
    target_group.add_argument("--all", action="store_true")
    parser.add_argument("--max-rounds", type=int, default=3)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--extractor-model", default="")
    parser.add_argument("--reviewer-model", default="")
    parser.add_argument("--openai-api-key", default="")
    parser.add_argument("--openai-base-url", default="")
    args = parser.parse_args(argv)
    con = us_rates_liquidity.connect(args.db_path)
    try:
        all_events = us_rates_liquidity.load_macro_events(con, "fomc_meeting")
        events = target_events(all_events, args.event_id, args.all)
        classified = classify_events(con, events, args.force)
        if args.verbose:
            for status in ("reused", "unavailable"):
                for event, detail in classified[status]:
                    _print_event_classification(event, status, detail)
        pending = classified["pending"]
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1
    finally:
        con.close()
    if not pending:
        print(_summary(0, classified, 0))
        return 0
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
    generated = 0
    failed = 0
    for event, current_document in pending:
        try:
            if generate_event_tone is not _ORIGINAL_GENERATE_EVENT_TONE:
                await generate_event_tone(
                    None,
                    all_events,
                    event,
                    current_document,
                    client,
                    models,
                    args.max_rounds,
                    verbose=args.verbose,
                )
            else:
                prepared = await asyncio.to_thread(
                    prepare_fomc_policy_tone,
                    args.db_path,
                    event["event_id"],
                    client,
                    models["extractor_model"],
                    models["reviewer_model"],
                    args.max_rounds,
                )
                if prepared.get("status") != "ok":
                    raise ValueError(prepared.get("error", "FOMC tone preparation failed"))
                persisted = await asyncio.to_thread(
                    persist_fomc_policy_tone, args.db_path, prepared
                )
                if persisted.get("status") != "ok":
                    raise ValueError(persisted.get("error", "FOMC tone persistence failed"))
                if args.verbose:
                    log_generation_result(prepared["row"])
        except Exception as exc:
            failed += 1
            print("fomc policy tone failed:", file=sys.stderr)
            print(f"  current: {_event_label(event)}", file=sys.stderr)
            print(f"  reason: {exc}", file=sys.stderr)
            if not args.all:
                print(_summary(generated, classified, failed))
                return 1
            continue
        generated += 1
    print(_summary(generated, classified, failed))
    return 1 if failed else 0


def main(argv=None):
    return asyncio.run(async_main(argv))


if __name__ == "__main__":
    raise SystemExit(main())

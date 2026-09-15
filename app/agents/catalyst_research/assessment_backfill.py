from app.agents.catalyst_research.domain import assess_catalyst_events as _default_assess
from app.agents.catalyst_research.persistence import repository as default_repository


async def backfill_catalyst_assessments(connection, *, ticker=None, batch_size=50, dry_run=False, dependencies=None):
    if isinstance(batch_size, bool) or not isinstance(batch_size, int) or not 1 <= batch_size <= 50:
        raise ValueError("batch size must be between 1 and 50")
    dependencies = dependencies or {}
    loader = dependencies.get("load_unassessed_events") or default_repository.load_unassessed_events
    saver = dependencies.get("save_catalyst_assessments") or default_repository.save_catalyst_assessments
    assess = dependencies.get("assess_catalyst_events") or _default_assess
    llm_client = dependencies.get("llm_client")
    model = dependencies.get("model")
    pending = loader(connection, ticker=ticker)
    if dry_run:
        return {"ticker": ticker, "pending": len(pending), "assessed": 0, "llm_call_count": 0, "dry_run": True}
    assessed_count = 0
    llm_call_count = 0
    for start in range(0, len(pending), batch_size):
        batch = pending[start : start + batch_size]
        events = [
            {
                "id": index,
                "event_id": row["event_id"],
                "source_type": row["source_type"],
                "title": row["title"],
                "earnings_state": row["earnings_state"],
            }
            for index, row in enumerate(batch, 1)
        ]
        result = await assess(events, llm_client=llm_client, model=model, batch_size=batch_size)
        if not isinstance(result, dict):
            raise ValueError("assessment result is invalid")
        llm_call_count += result.get("llm_call_count", 0)
        by_id = {event["id"]: event for event in events}
        rows = []
        for item in result.get("events") or []:
            source = by_id.get(item.get("id"))
            if source is None:
                raise ValueError("assessment result references unknown event")
            rows.append(
                {
                    "event_id": source["event_id"],
                    "catalyst_type": item["catalyst_type"],
                    "meaningful_state": item["meaningful_state"],
                    "assessment_method": item.get("catalyst_type_method"),
                    "model": item.get("assessment_model"),
                    "prompt_schema_version": item.get("assessment_prompt_schema_version"),
                    "input_hash": item.get("assessment_input_hash"),
                    "output_hash": item.get("assessment_output_hash"),
                }
            )
        saver(connection, rows)
        assessed_count += len(rows)
    return {"ticker": ticker, "pending": len(pending), "assessed": assessed_count, "llm_call_count": llm_call_count, "dry_run": False}

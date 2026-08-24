import asyncio
from datetime import date
from pathlib import Path
import tempfile

from app.data_sources import census_nrc
from app.data_sources import fred
from app.data_sources import michigan_consumer_sentiment
from app.data_sources import nfib_sbet
from app.data_sources import nfib_sbet_api
from app.db import consumer_sentiment
from app.db import macro_indicators
from app.db import us_rates_liquidity
from app.services import nfib_sbet_regional_import
from app.services import nfib_sbet_import
from app.tools import fomc_minutes_structure
from app.tools import fomc_policy_tone


FRED_CONSUMER_SERIES = (
    "BOGZ1FL010000336Q",
    "TDSP",
    "PSAVERT",
    "HHMSDODNS",
)


def _put(artifacts, key, value):
    if hasattr(artifacts, "put"):
        artifacts.put(key, value)
    else:
        artifacts[key] = value


def _get(artifacts, key):
    if hasattr(artifacts, "get"):
        return artifacts.get(key)
    if key not in artifacts:
        raise ValueError(f"macro refresh artifact is missing: {key}")
    return artifacts[key]


def _bytes(value):
    if isinstance(value, bytes):
        return value
    if isinstance(value, bytearray):
        return bytes(value)
    if isinstance(value, Path):
        return value.read_bytes()
    if isinstance(value, str):
        path = Path(value)
        if path.exists():
            return path.read_bytes()
        return value.encode("utf-8")
    raise ValueError(f"macro refresh fetcher returned unsupported value: {type(value).__name__}")


def _fetch_bytes(fetcher, argument):
    return _bytes(fetcher(argument))


def fetch_consumer_michigan(artifacts, *, fetcher=None, http_client=None):
    if fetcher is not None:
        values = {
            table_id: _fetch_bytes(fetcher, table_id)
            for table_id in (1, 5)
        }
    else:
        with tempfile.TemporaryDirectory() as directory:
            paths = michigan_consumer_sentiment.MichiganConsumerSentimentClient(
                http_client=http_client
            ).fetch_csvs(directory)
            values = {table_id: path.read_bytes() for table_id, path in paths.items()}
    result = {"artifact_key": "consumer.michigan", "tables": values}
    _put(artifacts, result["artifact_key"], values)
    return result


def persist_consumer_michigan(db_path, artifacts):
    values = _get(artifacts, "consumer.michigan")
    with tempfile.TemporaryDirectory() as directory:
        table_1 = Path(directory) / "table_1.csv"
        table_5 = Path(directory) / "table_5.csv"
        table_1.write_bytes(_bytes(values[1] if 1 in values else values["1"]))
        table_5.write_bytes(_bytes(values[5] if 5 in values else values["5"]))
        from scripts.import_consumer_sentiment import import_michigan_csvs

        result = import_michigan_csvs(table_1, table_5, db_path)
    return {"status": "ok", "artifact_key": "consumer.michigan", "series": result}


def fetch_consumer_fred(artifacts, *, fetcher=None, http_client=None):
    if fetcher is not None:
        values = {
            series_id: _fetch_bytes(fetcher, series_id)
            for series_id in FRED_CONSUMER_SERIES
        }
    else:
        with tempfile.TemporaryDirectory() as directory:
            paths = fred.FredClient(directory, http_client=http_client).fetch_csvs(
                FRED_CONSUMER_SERIES
            )
            values = {series_id: path.read_bytes() for series_id, path in paths.items()}
    result = {"artifact_key": "consumer.fred", "series": values}
    _put(artifacts, result["artifact_key"], values)
    return result


def persist_consumer_fred(db_path, artifacts):
    values = _get(artifacts, "consumer.fred")
    with tempfile.TemporaryDirectory() as directory:
        for series_id, value in values.items():
            (Path(directory) / f"{series_id}.csv").write_bytes(_bytes(value))
        from scripts.import_consumer_sentiment import import_fred_csvs

        result = import_fred_csvs(directory, db_path)
    return {"status": "ok", "artifact_key": "consumer.fred", "series": result}


def fetch_building_permits(artifacts, *, fetcher=None, destination=None, http_client=None):
    if fetcher is not None:
        value = _fetch_bytes(fetcher, destination or census_nrc.PERMIT_HISTORY_URL)
    else:
        with tempfile.TemporaryDirectory() as directory:
            path = census_nrc.fetch_permits_workbook(
                Path(directory) / "permits_cust.xlsx", http_client=http_client
            )
            value = path.read_bytes()
    result = {"artifact_key": "census.building_permits", "bytes": value}
    _put(artifacts, result["artifact_key"], value)
    return result


def persist_building_permits(db_path, artifacts, *, release_date=None):
    value = _get(artifacts, "census.building_permits")
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "permits_cust.xlsx"
        path.write_bytes(_bytes(value))
        payload = census_nrc.parse_permits_workbook(path, release_date=release_date)
    con = macro_indicators.connect(db_path)
    try:
        result = macro_indicators.merge_macro_indicator_observations_batch(
            con,
            [
                {
                    **observation,
                    "series_id": payload["series"]["series_id"],
                }
                for observation in payload["observations"]
            ],
        )
    finally:
        con.close()
    return {"status": "ok", "artifact_key": "census.building_permits", **result}


def fetch_nfib(artifacts, *, fetcher=None, source_url=None, cache_path=None, reference_date=None, http_client=None):
    if fetcher is not None:
        value = _fetch_bytes(fetcher, source_url or nfib_sbet_import.DEFAULT_NFIB_SOURCE_URL)
        resolved_url = source_url or nfib_sbet_import.DEFAULT_NFIB_SOURCE_URL
    else:
        resolved_url = source_url or nfib_sbet.discover_latest_sbet_url(
            reference_date=reference_date, http_client=http_client
        )
        report_year, report_month = nfib_sbet.report_month_from_url(resolved_url)
        directory = Path(cache_path or tempfile.mkdtemp())
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"nfib-sbet-{report_year:04d}-{report_month:02d}.pdf"
        nfib_sbet.fetch_sbet_report(str(path), resolved_url, http_client=http_client)
        value = path.read_bytes()
    result = {
        "artifact_key": "nfib.national",
        "bytes": value,
        "source_url": resolved_url,
    }
    _put(artifacts, result["artifact_key"], result)
    return result


def persist_nfib(db_path, artifacts, *, release_date=None):
    staged = _get(artifacts, "nfib.national")
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "nfib-sbet.pdf"
        path.write_bytes(_bytes(staged["bytes"] if isinstance(staged, dict) else staged))
        payload = nfib_sbet.parse_sbet_report(
            str(path), staged["source_url"], release_date
        )
    con = macro_indicators.connect(db_path)
    try:
        result = macro_indicators.merge_macro_indicator_observations_batch(
            con, payload["observations"]
        )
    finally:
        con.close()
    return {"status": "ok", "artifact_key": "nfib.national", **result}


def fetch_nfib_regional(artifacts, start_year=2021, end_year=None, *, fetcher=None):
    end_year = end_year or date.today().year
    fetch_region = fetcher or nfib_sbet_api.fetch_regional_data
    payloads = [
        fetch_region(region_id, start_year, end_year)
        for region_id in sorted(nfib_sbet_regional_import.ALL_REGION_IDS)
    ]
    if fetcher is None:
        payloads.append(nfib_sbet_api.fetch_national_data(start_year, end_year))
    result = {
        "artifact_key": "nfib.regional",
        "payloads": payloads,
        "start_year": start_year,
        "end_year": end_year,
    }
    _put(artifacts, result["artifact_key"], result)
    return result


def persist_nfib_regional(db_path, artifacts):
    staged = _get(artifacts, "nfib.regional")
    observations = []
    for payload in staged["payloads"]:
        region_id = payload.get("region_id", nfib_sbet_regional_import.NATIONAL_REGION_ID)
        for api_observation in payload.get("observations", []):
            observations.extend(
                nfib_sbet_regional_import._api_obs_to_db_obs(
                    api_observation, region_id, payload
                )
            )
    con = macro_indicators.connect(db_path)
    try:
        count = nfib_sbet_regional_import.merge_nfib_regional_observations_batch(
            con, observations
        )
    finally:
        con.close()
    return {"status": "ok", "artifact_key": "nfib.regional", "observations": count}


def fetch_fomc_documents(artifacts, events, document_type, *, fetcher=None):
    fetch_document = fetcher
    if fetch_document is None:
        from scripts.fetch_fomc_documents import fetch_minutes_document, fetch_statement_document

        fetch_document = {
            "statement": fetch_statement_document,
            "minutes": fetch_minutes_document,
        }[document_type]
    rows = []
    for event in events:
        if fetcher is None:
            rows.append(fetch_document(event))
        else:
            try:
                rows.append(fetch_document(event, document_type))
            except TypeError as exc:
                try:
                    rows.append(fetch_document(event))
                except TypeError:
                    try:
                        rows.append(fetch_document(event.get("url", "")))
                    except TypeError:
                        raise exc
    artifact_key = f"fomc.documents.{document_type}"
    result = {"artifact_key": artifact_key, "rows": rows, "document_type": document_type}
    _put(artifacts, artifact_key, rows)
    return result


def persist_fomc_documents(db_path, artifacts, document_type):
    artifact_key = f"fomc.documents.{document_type}"
    rows = _get(artifacts, artifact_key)
    con = us_rates_liquidity.connect(db_path)
    try:
        for row in rows:
            us_rates_liquidity.replace_macro_event_document(con, row)
    finally:
        con.close()
    return {"status": "ok", "artifact_key": artifact_key, "documents": len(rows)}


def _load_fomc_context(db_path, event_id, document_type):
    if not db_path:
        return None
    con = us_rates_liquidity.connect(db_path)
    try:
        events = us_rates_liquidity.load_macro_events(con, "fomc_meeting")
        event = next((item for item in events if item["event_id"] == event_id), None)
        document = us_rates_liquidity.load_macro_event_document(
            con, event_id, document_type
        )
        previous_event = None
        previous_document = None
        if event:
            earlier = [item for item in events if item.get("start_date") < event.get("start_date")]
            for candidate in reversed(earlier):
                previous_document = us_rates_liquidity.load_macro_event_document(
                    con, candidate["event_id"], document_type
                )
                if previous_document:
                    previous_event = candidate
                    break
        return event, document, previous_event, previous_document
    finally:
        con.close()


def prepare_fomc_policy_tone(db_path, event_id, client, extractor_model, reviewer_model, max_rounds=3):
    if client is None:
        return {"status": "skipped", "event_id": event_id, "error": "OPENAI_API_KEY is not configured"}
    context = _load_fomc_context(db_path, event_id, "statement")
    if not context or not context[0] or not context[1]:
        return {"status": "failed", "event_id": event_id, "error": "FOMC statement document is unavailable"}
    event, document, previous_event, previous_document = context
    from scripts import generate_fomc_policy_tone as script

    result = asyncio.run(
        script.run_extract_review_loop(
            event,
            document,
            previous_event,
            previous_document,
            extract=lambda prompt: script._call_json(
                client, extractor_model, prompt, fomc_policy_tone.parse_extractor_response
            ),
            review=lambda prompt: script._call_json(
                client, reviewer_model, prompt, fomc_policy_tone.parse_reviewer_response
            ),
            max_rounds=max_rounds,
        )
    )
    row = fomc_policy_tone.tone_extraction_row(
        event_id=event_id,
        source_document_type="statement",
        source_hash=document["source_hash"],
        previous_event_id=previous_event["event_id"] if previous_event else None,
        extraction=result["extraction"],
        reviewer_feedback=result["reviewer_feedback"],
        extraction_status=result["extraction_status"],
        review_rounds=result["review_rounds"],
        extractor_model=extractor_model,
        reviewer_model=reviewer_model,
        generated_at=script.generated_at_now(),
        final_reviewer_feedback=result["final_reviewer_feedback"],
    )
    return {"status": "ok", "event_id": event_id, "row": row}


def persist_fomc_policy_tone(db_path, prepared_extraction):
    if prepared_extraction.get("status") != "ok":
        return {"status": prepared_extraction.get("status", "failed"), "event_id": prepared_extraction.get("event_id"), "error": prepared_extraction.get("error")}
    con = us_rates_liquidity.connect(db_path)
    try:
        us_rates_liquidity.replace_macro_event_tone_extraction(con, prepared_extraction["row"])
    finally:
        con.close()
    return {"status": "ok", "event_id": prepared_extraction["event_id"]}


def prepare_fomc_minutes_structure(db_path, event_id, client, extractor_model, reviewer_model, max_rounds=3):
    if client is None:
        return {"status": "skipped", "event_id": event_id, "error": "OPENAI_API_KEY is not configured"}
    context = _load_fomc_context(db_path, event_id, "minutes")
    if not context or not context[0] or not context[1]:
        return {"status": "failed", "event_id": event_id, "error": "FOMC minutes document is unavailable"}
    event, document, _, _ = context
    statement_context = _load_fomc_context(db_path, event_id, "statement")
    statement_tone = None
    if statement_context and statement_context[1]:
        con = us_rates_liquidity.connect(db_path)
        try:
            statement_tone = us_rates_liquidity.load_macro_event_tone_extraction(
                con, event_id, "statement", statement_context[1]["source_hash"]
            )
        finally:
            con.close()
    if not statement_tone or statement_tone.get("extraction_status") != "approved":
        return {"status": "failed", "event_id": event_id, "error": "approved FOMC policy tone is unavailable"}
    from scripts import generate_fomc_minutes_structure as script

    extraction = None
    feedback = []
    reviewer_feedback = []
    final_feedback = []
    extraction_status = "rejected"
    for round_index in range(max_rounds):
        content = asyncio.run(
            script.call_json(
                client,
                extractor_model,
                fomc_minutes_structure.build_extractor_prompt(
                    event, statement_tone, document["text"], feedback
                ),
            )
        )
        try:
            extraction = fomc_minutes_structure.parse_extractor_response(content)
        except ValueError as exc:
            feedback = ["Extractor output failed schema validation.", str(exc)]
            continue
        review = fomc_minutes_structure.parse_reviewer_response(
            asyncio.run(
                script.call_json(
                    client,
                    reviewer_model,
                    fomc_minutes_structure.build_reviewer_prompt(
                        event, statement_tone, document["text"], extraction
                    ),
                )
            )
        )
        reviewer_feedback.extend(review["feedback"])
        final_feedback = review["feedback"]
        if review["approved"]:
            extraction_status = "approved"
            break
        feedback = review["feedback"]
    if extraction is None:
        return {"status": "failed", "event_id": event_id, "error": "valid FOMC minutes structure JSON was not produced"}
    row = fomc_minutes_structure.tone_extraction_row(
        event["event_id"], document["source_hash"], statement_tone, extraction,
        reviewer_feedback, extraction_status, round_index + 1, extractor_model,
        reviewer_model, script.datetime.now(script.UTC).isoformat(), final_feedback,
    )
    return {"status": "ok", "event_id": event_id, "row": row}


def persist_fomc_minutes_structure(db_path, prepared_extraction):
    if prepared_extraction.get("status") != "ok":
        return {"status": prepared_extraction.get("status", "failed"), "event_id": prepared_extraction.get("event_id"), "error": prepared_extraction.get("error")}
    con = us_rates_liquidity.connect(db_path)
    try:
        us_rates_liquidity.replace_macro_event_tone_extraction(con, prepared_extraction["row"])
    finally:
        con.close()
    return {"status": "ok", "event_id": prepared_extraction["event_id"]}


fetch_consumer_sentiment = fetch_consumer_michigan
persist_consumer_sentiment = persist_consumer_michigan
fetch_us_building_permits = fetch_building_permits
persist_us_building_permits = persist_building_permits
fetch_nfib_sbet = fetch_nfib
persist_nfib_sbet = persist_nfib
fetch_nfib_sbet_regional = fetch_nfib_regional
persist_nfib_sbet_regional = persist_nfib_regional

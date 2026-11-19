from datetime import date, datetime
from json import JSONDecodeError, loads
from math import isclose, isfinite
from pathlib import Path
from sqlite3 import Error as SQLiteError, Row, connect
from urllib.parse import quote


_SERIES_READERS = {
    "macro": ("macro_indicator_points", "series_id", "date", "value"),
    "rate": ("us_rate_points", "series_id", "date", "value"),
    "benchmark": ("benchmark_prices", "benchmark_id", "date", "close"),
    "economic": ("economic_confirmation_current_observations", "series_id", "reference_period", "value"),
    "regional": ("macro_indicator_regional_observations", "region_id,indicator_id", "date", "value"),
    "cot": ("cot_observations", "commodity_id,cftc_contract_market_code", "report_date", "open_interest"),
}
_GDP_TABLES = {"lag": "gdp_lag_rows", "quad": "gdp_quad_rows"}
_ISM_TABLES = {"industry_rankings": "ism_industry_rankings", "industry_signals": "ism_report_industry_signals", "comments": "ism_report_comments", "commodities": "ism_report_commodities", "narrative": "ism_report_narrative_facts"}
_TASK_LABELS = {"ok": "Succeeded", "succeeded": "Succeeded", "completed_with_warnings": "Completed with warnings", "running": "Last reported: running", "failed": "Failed", "blocked": "Blocked", "skipped": "Skipped", "interrupted": "Interrupted", "partially_failed": "Partially failed", "completed_partial": "Completed with limitations", "unsupported": "Unsupported"}


def _connect_read_only(path):
    con = connect(f"{Path(path).resolve().as_uri()}?mode=ro", uri=True, timeout=5)
    con.row_factory = Row
    con.execute("pragma query_only=on")
    con.execute("begin")
    return con


def _missing():
    return {"availability": "missing", "current_period": None}


def _unavailable():
    return {"availability": "unavailable", "current_period": None}


def _latest(con, table, groups, period, fields="*", limit=1):
    query = f"select {fields} from (select *, row_number() over (partition by {groups} order by {period} desc) as freshness_row from {table}) where freshness_row<=? order by freshness_row"
    return [dict(row) for row in con.execute(query, (limit,))]


def _lineage_evidence(con, dataset, row):
    if not row or not dataset.get("lineage_source"):
        return {}
    try:
        lineage = con.execute("select * from macro_source_lineage where dataset_id=? and observation_date=?", (dataset["id"], row["date"])).fetchone()
        if lineage and lineage["basis"] == "conflicting" and isclose(lineage["value"], row["value"], rel_tol=1e-12, abs_tol=1e-12):
            return {"lineage_basis": "conflicting"}
        if not lineage or lineage["source_series_id"] != dataset["lineage_source"] or lineage["basis"] not in {"captured_at_import", "reconstructed_from_cached_source"}:
            return {}
        if not isclose(lineage["value"], row["value"], rel_tol=1e-12, abs_tol=1e-12) or date.fromisoformat(lineage["source_date"]) > date.fromisoformat(row["date"]) or len(lineage["source_hash"]) != 64:
            return {}
        return {"source_observation_date": lineage["source_date"], "lineage_basis": lineage["basis"]}
    except (SQLiteError, ValueError, TypeError):
        return {}


def _evidence(row, period_key, value_key=None):
    if row is None:
        return _missing()
    invalid = value_key is not None and (not isinstance(row.get(value_key), (int, float)) or not isfinite(row[value_key]))
    if row.get("availability") not in {None, "available"}:
        invalid = True
    return {
        "availability": "invalid" if invalid else "available", "current_period": row.get(period_key),
        **{key: row[key] for key in ("release_date", "source_hash", "retrieved_at", "generated_at", "revision_status") if row.get(key)},
    }


def _series_evidence(con, kind, datasets):
    table, groups, period, value = _SERIES_READERS[kind]
    columns = [*groups.split(","), period, value]
    if kind == "economic":
        columns.extend(["release_date", "as_of_timestamp", "source_hash", "vintage_id"])
    if kind == "regional":
        columns.append("availability")
    stored = _latest(con, table, groups, period, ",".join(columns), limit=3 if kind == "benchmark" else 1)
    by_key = {}
    recent = {}
    for row in stored:
        key = tuple(row[k] for k in groups.split(","))
        by_key.setdefault(key, row)
        recent.setdefault(key, []).append(row)
    metadata = {}
    if kind == "macro":
        try:
            metadata = {(r["series_id"], r["date"]): dict(r) for r in con.execute("select series_id,date,release_date,revision_status,retrieved_at,source_hash from macro_indicator_observation_metadata m where date=(select max(date) from macro_indicator_points p where p.series_id=m.series_id)")}
        except SQLiteError:
            pass
    result = {}
    for dataset in datasets:
        storage = dataset["storage"]
        key = (storage["region"], storage["key"]) if kind == "regional" else (storage["key"], storage["contract"]) if kind == "cot" else (storage["key"],)
        row = by_key.get(key)
        if row and kind == "macro":
            row = {**row, **metadata.get((storage["key"], row[period]), {})}
        evidence = _evidence(row, period, value)
        if kind in {"macro", "rate"}:
            evidence.update(_lineage_evidence(con, dataset, row))
        if kind == "benchmark":
            evidence["recent_observations"] = [_evidence(item, period, value) for item in recent.get(key, [])]
        if row and kind == "economic":
            evidence["retrieved_at"] = row["as_of_timestamp"]
        if kind == "macro" and storage.get("survey"):
            try:
                promoted, _ = _ism_report(con, storage["survey"])
                evidence["source"] = _ism_source(con, storage["survey"], promoted)
                if row:
                    artifact = con.execute("select source_hash,current_value from ism_at_a_glance_rows where series_id=? and report_month=? order by rowid desc limit 1", (storage["key"], row[period])).fetchone()
                    evidence["source_hash"] = artifact["source_hash"] if artifact and artifact["current_value"] == row[value] else None
            except SQLiteError:
                evidence["availability"] = "unavailable"
        result[dataset["id"]] = evidence
    return result


def _gdp_evidence(con, dataset):
    table = _GDP_TABLES[dataset["storage"]["key"]]
    value = "gdp_level" if table != "gdp_lag_rows" else "gdp_yoy"
    row = con.execute(f"select date,{value} from {table} where relationship_id=? order by date desc limit 1", ("us_sp500_gdp",)).fetchone()
    return _evidence(dict(row) if row else None, "date", value)


def _shfe_evidence(con, dataset):
    main = dataset["storage"]["key"] == "main"
    table, period = ("shfe_cu_main_daily", "date") if main else ("shfe_cu_contract_daily", "trade_date")
    row = con.execute(f"select {period},close,retrieved_at from {table} order by {period} desc limit 1").fetchone()
    return _evidence(dict(row) if row else None, period, "close")


def _fomc_document(con, document_type):
    row = con.execute("select e.start_date,d.source_hash,d.fetched_at from macro_event_documents d join macro_events e on e.event_id=d.event_id where e.event_type='fomc_meeting' and d.document_type=? and length(trim(d.text))>0 order by e.start_date desc,d.fetched_at desc limit 1", (document_type,)).fetchone()
    evidence = _evidence(dict(row) if row else None, "start_date")
    if row:
        evidence["retrieved_at"] = row["fetched_at"]
    return evidence


def _fomc_evidence(con, dataset):
    storage = dataset["storage"]
    if storage["kind"] == "fomc_calendar":
        rows = con.execute("select start_date from macro_events where event_type='fomc_meeting' order by start_date").fetchall()
        return {"availability": "available" if rows else "missing", "current_period": rows[-1][0] if rows else None, "event_periods": [row[0] for row in rows]}
    kind = "minutes" if storage["key"] in {"minutes", "minutes_structure"} else "statement"
    source = _fomc_document(con, kind)
    if storage["kind"] == "fomc_document":
        return source
    row = con.execute("select e.start_date,x.source_hash,x.generated_at from macro_event_tone_extractions x join macro_events e on e.event_id=x.event_id where e.event_type='fomc_meeting' and x.source_document_type=? and x.extraction_status='approved' order by e.start_date desc,x.generated_at desc limit 1", (kind,)).fetchone()
    return {**_evidence(dict(row) if row else None, "start_date"), "source": source}


def _ism_report(con, survey):
    row = con.execute("select report_id,report_month,source_hash,fetched_at from ism_report_snapshots where survey_type=? and parse_status='ok' order by report_month desc,fetched_at desc,report_id desc limit 1", (survey,)).fetchone()
    if row is None:
        return _missing(), None
    evidence = _evidence(dict(row), "report_month")
    evidence["retrieved_at"] = row["fetched_at"] or None
    return evidence, dict(row)


def _ism_source(con, survey, promoted):
    row = con.execute("select report_month,source_hash,fetched_at,parse_status from ism_report_source_snapshots where survey_type=? order by report_month desc,julianday(fetched_at) desc,source_url desc limit 1", (survey,)).fetchone()
    if row is None:
        return promoted
    raw = dict(row)
    period = raw["report_month"]
    current = promoted.get("current_period")
    if current and period and period < current:
        return promoted
    if period == current and raw["source_hash"] == promoted.get("source_hash"):
        return promoted
    if period == current:
        try:
            raw_time = datetime.fromisoformat(raw["fetched_at"].replace("Z", "+00:00"))
            promoted_time = datetime.fromisoformat(promoted["retrieved_at"].replace("Z", "+00:00"))
            if raw_time < promoted_time:
                return promoted
            if raw_time == promoted_time:
                raw["parse_status"] = "ambiguous"
        except (ValueError, TypeError, KeyError):
            raw["parse_status"] = "ambiguous"
    evidence = _evidence(raw, "report_month")
    evidence["retrieved_at"] = raw["fetched_at"]
    if not period or raw["parse_status"] not in {"ok", "prepared"}:
        evidence["availability"] = "invalid"
    return evidence


def _ism_promotion(con, report):
    row = con.execute("select report_month,source_hash from ism_report_narrative_facts where report_id=? and source_hash=?", (report["report_id"], report["source_hash"])).fetchone()
    return _evidence(dict(row) if row else None, "report_month")


def _ism_evidence(con, dataset):
    storage = dataset["storage"]
    survey = storage["key"] if storage["kind"] == "ism_report" else storage["survey"]
    promoted, report = _ism_report(con, survey)
    source = _ism_source(con, survey, promoted)
    if storage["kind"] == "ism_report":
        return {**promoted, "source": source}
    artifact = storage["key"]
    table = _ISM_TABLES[artifact]
    if report is None:
        return {**_missing(), "source": source}
    promotion = _ism_promotion(con, report)
    if artifact == "industry_rankings":
        row = con.execute("select date from ism_industry_rankings where survey_type=? order by date desc limit 1", (survey,)).fetchone()
        evidence = _evidence(dict(row) if row else None, "date")
        if row:
            rankings = con.execute("select industry,direction,rank from ism_industry_rankings where survey_type=? and date=?", (survey, row["date"])).fetchall()
            signals = con.execute("select a.industry,a.signal_type,a.rank,a.source_hash from ism_report_industry_signals a join ism_report_snapshots r on r.report_id=a.report_id where r.survey_type=? and a.report_month=? and a.signal_type in ('overall_growth','overall_contraction')", (survey, row["date"])).fetchall()
            hashes = {signal["source_hash"] for signal in signals}
            actual = {(item["industry"], item["direction"], item["rank"]) for item in rankings}
            expected = {(item["industry"], "growth" if item["signal_type"] == "overall_growth" else "contraction", item["rank"]) for item in signals}
            evidence["source_hash"] = next(iter(hashes)) if len(hashes) == 1 and actual == expected else None
    else:
        row = con.execute(f"select a.report_month,a.source_hash from {table} a join ism_report_snapshots r on r.report_id=a.report_id where r.survey_type=? order by a.report_month desc,a.rowid desc limit 1", (survey,)).fetchone()
        evidence = _evidence(dict(row) if row else None, "report_month")
    if promotion["availability"] == "available" and (evidence.get("current_period") or "") < report["report_month"]:
        evidence = {**promotion, "empty_section": True}
    elif evidence["availability"] == "missing":
        evidence["availability"] = "unverified_empty"
    return {**evidence, "source": source}


def load_observations(datasets, db_path):
    try:
        con = _connect_read_only(db_path)
    except (SQLiteError, OSError):
        return {row["id"]: _unavailable() for row in datasets}
    result = {}
    groups = {}
    for dataset in datasets:
        groups.setdefault(dataset["storage"]["kind"], []).append(dataset)
    try:
        for kind, selected in groups.items():
            if kind in _SERIES_READERS:
                try:
                    result.update(_series_evidence(con, kind, selected))
                except SQLiteError:
                    result.update({row["id"]: _unavailable() for row in selected})
                continue
            reader = _gdp_evidence if kind == "gdp" else _shfe_evidence if kind == "shfe" else _fomc_evidence if kind.startswith("fomc_") else _ism_evidence
            for dataset in selected:
                try:
                    result[dataset["id"]] = reader(con, dataset)
                except SQLiteError:
                    result[dataset["id"]] = _unavailable()
    finally:
        con.close()
    return result


def _history_records(con):
    children = con.execute("with ranked as (select r.run_id,r.job_id,r.payload as run_payload,c.name,c.payload,row_number() over(partition by r.job_id,c.name,json_extract(c.payload,'$.status') order by json_extract(c.payload,'$.updated_at') desc,r.sequence desc) as rank from job_notification_runs r join job_notification_children c on c.run_id=r.run_id where r.job_id in ('macro_refresh','investing_refresh')) select run_id,job_id,run_payload,name,payload from ranked where rank=1").fetchall()
    roots = con.execute("with ranked as (select run_id,job_id,payload,row_number() over(partition by status order by sequence desc) as rank from job_notification_runs where job_id='investing_refresh') select run_id,job_id,payload from ranked where rank=1").fetchall()
    records = []
    for row in children:
        records.append(_task_record(dict(row), loads(row["payload"]), loads(row["run_payload"])))
    for row in roots:
        payload = loads(row["payload"])
        records.append(_task_record({**dict(row), "name": None}, {**payload, "updated_at": payload.get("ended_at") or payload.get("updated_at")}, payload))
    return records


def _task_record(row, payload, run):
    status = payload.get("status")
    run_id = row["run_id"]
    return {"run_id": run_id, "job_id": row["job_id"], "stage": row["name"], "status": status, "status_label": _TASK_LABELS.get(status, "Unknown"), "at": payload.get("updated_at"), "origin": run.get("origin") if run.get("origin") in {"manual", "command_line", "background"} else None, "href": f"/notifications.html?run={quote(str(run_id), safe='')}"}


def _latest_task(records):
    return max(records, key=lambda record: record.get("at") or "", default=None)


def _dataset_history(dataset, records):
    matching, checks, processing = [], [], []
    for mapping in dataset["tasks"]:
        selected = [r for r in records if r["job_id"] == mapping["job_id"] and (r["stage"] in {mapping.get("fetch"), mapping.get("persist")} if mapping["job_id"] == "macro_refresh" else r["stage"] is None)]
        matching.extend(selected)
        if mapping["successful_check_supported"]:
            checks.extend(r for r in selected if r["status"] in {"ok", "succeeded", "completed_with_warnings"} and (r["stage"] == mapping.get("fetch") or mapping["job_id"] == "investing_refresh"))
        processing.extend(r for r in selected if r["stage"] == mapping.get("persist") or mapping["job_id"] == "investing_refresh")
    return {"availability": "available", "last_attempt": _latest_task(matching), "last_successful_check": _latest_task(checks), "last_processing": _latest_task(processing)}


def load_task_history(datasets, db_path):
    try:
        con = _connect_read_only(db_path)
    except (SQLiteError, OSError):
        return {row["id"]: {"availability": "unavailable"} for row in datasets}
    try:
        records = _history_records(con)
        return {row["id"]: _dataset_history(row, records) for row in datasets}
    except (SQLiteError, JSONDecodeError, TypeError, KeyError):
        return {row["id"]: {"availability": "unavailable"} for row in datasets}
    finally:
        con.close()

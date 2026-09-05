import base64
import hashlib
import json
import secrets
import sqlite3
from datetime import UTC, date, datetime
from pathlib import Path

from app.agents.catalyst_research.config import (
    ADAPTER_SCHEMA_VERSION,
    RESEARCH_VERSION,
    RESULT_SCHEMA_VERSION,
)


ROOT = Path(__file__).resolve().parents[4]
DEFAULT_DB_PATH = ROOT / "data" / "local_system" / "market_data.sqlite"
_TERMINAL_JOB_STATES = {"completed", "completed_partial", "unsupported", "failed"}
_JOB_STATES = {"queued", "running", *_TERMINAL_JOB_STATES}
_ADAPTER_STATES = {"candidate", "active", "failed_validation", "stale", "superseded"}
_SOURCE_TYPES = {"ir_home", "press_releases", "events_presentations", "earnings_results"}


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _decode(value):
    if value is None:
        return None
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return value


def _dict(row):
    return dict(row) if row is not None else None


def _id(prefix):
    return f"{prefix}{secrets.token_hex(12)}"


def _now_iso(value=None):
    current = value or datetime.now(UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    return current.astimezone(UTC).isoformat()


def _ticker(value):
    normalized = str(value or "").strip().upper()
    if not normalized:
        raise ValueError("ticker is required")
    return normalized


def _decode_row(row, json_columns=()):
    result = _dict(row)
    if result is None:
        return None
    for key in json_columns:
        if key in result:
            result[key] = _decode(result[key])
    return result


def connect(db_path=DEFAULT_DB_PATH):
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.execute("pragma foreign_keys = on")
    con.executescript(
        """
        pragma journal_mode = wal;
        create table if not exists catalyst_research_jobs (
            job_id text primary key,
            ticker text not null,
            company_name text,
            cik text,
            requested_years integer not null check (requested_years between 1 and 4),
            requested_start text not null,
            requested_end text not null,
            as_of text not null,
            research_version text not null,
            status text not null check (status in ('queued','running','completed','completed_partial','unsupported','failed')),
            execution_paths_json text not null default '{}',
            call_counts_json text not null default '{}',
            statistics_json text,
            warnings_json text not null default '[]',
            next_actions_json text not null default '[]',
            error_summary text,
            created_at text not null,
            started_at text,
            completed_at text
        );
        create table if not exists catalyst_search_attempts (
            attempt_id text primary key,
            job_id text not null references catalyst_research_jobs(job_id),
            provider text not null,
            query text not null,
            requested_limit integer not null,
            started_at text not null,
            completed_at text,
            outcome text,
            diagnostics_json text,
            provider_request_id text
        );
        create table if not exists catalyst_search_results (
            search_result_id text primary key,
            job_id text not null references catalyst_research_jobs(job_id),
            attempt_id text not null references catalyst_search_attempts(attempt_id),
            result_id integer not null,
            query text not null,
            rank integer,
            title text,
            url text not null,
            snippet text,
            metadata_json text,
            unique(job_id, result_id)
        );
        create table if not exists catalyst_ir_sources (
            source_id text primary key,
            job_id text not null references catalyst_research_jobs(job_id),
            ticker text not null,
            source_type text not null check (source_type in ('ir_home','press_releases','events_presentations','earnings_results')),
            url text not null,
            final_url text,
            acceptance_status text not null default 'pending' check (acceptance_status in ('pending','accepted','rejected')),
            extraction_status text not null default 'pending' check (extraction_status in ('pending','complete','partial','unsupported','failed')),
            active_adapter_id text,
            evidence_result_ids_json text not null default '[]',
            requested_start text,
            requested_end text,
            coverage_start text,
            coverage_end text,
            page_count integer not null default 0,
            item_count integer not null default 0,
            content_hash text,
            snapshot_hash text references catalyst_source_snapshots(content_hash),
            truncation_reason text,
            discovery_provider text,
            execution_path text,
            checked_at text
        );
        create table if not exists catalyst_source_snapshots (
            content_hash text primary key,
            requested_url text not null,
            final_url text,
            content_type text,
            fetched_at text not null,
            raw_html text,
            structural_html text,
            normalized_json text,
            snapshot_schema_version text,
            response_bytes integer,
            truncated integer not null default 0
        );
        create table if not exists catalyst_source_adapters (
            adapter_id text primary key,
            ticker text not null,
            source_type text not null check (source_type in ('press_releases','events_presentations')),
            version integer not null check (version >= 1),
            adapter_schema_version text not null,
            source_url text not null,
            allowed_hosts_json text not null default '[]',
            access_mode text,
            adapter_json text not null,
            state text not null check (state in ('candidate','active','failed_validation','stale','superseded')),
            generation_model text,
            prompt_schema_version text,
            source_snapshot_hash text references catalyst_source_snapshots(content_hash),
            input_hash text,
            output_hash text,
            created_at text not null,
            validated_at text,
            activated_at text,
            stale_at text,
            superseded_at text,
            unique(ticker, source_type, version)
        );
        create table if not exists catalyst_adapter_validations (
            validation_id text primary key,
            adapter_id text not null references catalyst_source_adapters(adapter_id),
            job_id text not null references catalyst_research_jobs(job_id),
            validator_version text,
            executor_version text,
            status text not null check (status in ('passed','failed')),
            report_json text not null,
            source_content_hashes_json text not null default '[]',
            page_content_hashes_json text not null default '[]',
            validated_at text not null
        );
        create table if not exists catalyst_ir_events (
            event_id text primary key,
            job_id text not null references catalyst_research_jobs(job_id),
            source_id text not null references catalyst_ir_sources(source_id),
            ticker text not null,
            published_date text,
            event_date text,
            count_date text not null,
            title text not null,
            normalized_title text not null,
            canonical_url text not null,
            source_type text not null check (source_type in ('press_releases','events_presentations')),
            earnings_state text not null default 'ambiguous' check (earnings_state in ('earnings','non_earnings','ambiguous')),
            classification_method text,
            adapter_id text,
            adapter_version integer,
            executor_version text,
            first_seen_at text not null,
            content_hash text,
            unique(job_id, ticker, source_type, count_date, normalized_title, canonical_url)
        );
        create table if not exists catalyst_ir_classifications (
            event_id text primary key references catalyst_ir_events(event_id),
            earnings_state text not null check (earnings_state in ('earnings','non_earnings','ambiguous')),
            classification_method text not null,
            model text,
            prompt_schema_version text,
            input_hash text,
            output_hash text,
            classified_at text not null
        );
        create unique index if not exists idx_catalyst_active_adapter
        on catalyst_source_adapters(ticker, source_type)
        where state = 'active';
        create unique index if not exists idx_catalyst_event_job_key
        on catalyst_ir_events(job_id, ticker, source_type, count_date, normalized_title, canonical_url);
        create index if not exists idx_catalyst_jobs_ticker_completed
        on catalyst_research_jobs(ticker, status, completed_at desc);
        """
    )
    return con


def create_job(con, request, company=None, now=None):
    ticker = _ticker(request.get("ticker"))
    years = request.get("years", 4)
    if not isinstance(years, int) or isinstance(years, bool) or not 1 <= years <= 4:
        raise ValueError("years must be between 1 and 4")
    as_of = request.get("as_of") or (now.date() if now else datetime.now(UTC).date())
    if isinstance(as_of, datetime):
        as_of = as_of.date()
    try:
        as_of = date.fromisoformat(str(as_of))
    except (TypeError, ValueError) as exc:
        raise ValueError("as of date is invalid") from exc
    try:
        requested_start = as_of.replace(year=as_of.year - years)
    except ValueError:
        requested_start = as_of.replace(year=as_of.year - years, day=28)
    company = company or {}
    job = {
        "job_id": _id("cr_"),
        "ticker": ticker,
        "company_name": company.get("company_name") or company.get("name"),
        "cik": company.get("cik"),
        "requested_years": years,
        "requested_start": str(requested_start),
        "requested_end": str(as_of),
        "as_of": str(as_of),
        "research_version": RESEARCH_VERSION,
        "status": "queued",
        "execution_paths_json": _json({}),
        "call_counts_json": _json({}),
        "created_at": _now_iso(now),
    }
    con.execute(
        """insert into catalyst_research_jobs(
            job_id,ticker,company_name,cik,requested_years,requested_start,requested_end,
            as_of,research_version,status,execution_paths_json,call_counts_json,created_at
        ) values (:job_id,:ticker,:company_name,:cik,:requested_years,:requested_start,:requested_end,
            :as_of,:research_version,:status,:execution_paths_json,:call_counts_json,:created_at)""",
        job,
    )
    con.commit()
    return job


def _job(con, job_id):
    row = con.execute("select * from catalyst_research_jobs where job_id = ?", (job_id,)).fetchone()
    if row is None:
        raise ValueError(f"research job {job_id} was not found")
    return row


def _nonterminal_job(con, job_id):
    job = _job(con, job_id)
    if job["status"] in _TERMINAL_JOB_STATES:
        raise ValueError(f"research job {job_id} is terminal")
    return job


def start_job(con, job_id, started_at):
    job = _job(con, job_id)
    if job["status"] != "queued":
        raise ValueError(f"research job {job_id} cannot start from {job['status']}")
    con.execute("update catalyst_research_jobs set status = 'running', started_at = ? where job_id = ?", (started_at, job_id))
    con.commit()


def record_search_attempt(con, attempt):
    _nonterminal_job(con, attempt.get("job_id"))
    attempt_id = attempt.get("attempt_id") or _id("csa_")
    if not attempt.get("provider") or not attempt.get("query"):
        raise ValueError("search attempt provider and query are required")
    with con:
        cursor = con.execute(
        """insert into catalyst_search_attempts(
            attempt_id,job_id,provider,query,requested_limit,started_at,completed_at,
            outcome,diagnostics_json,provider_request_id
        ) select ?,?,?,?,?,?,?,?,?,? where exists (
            select 1 from catalyst_research_jobs where job_id = ? and status not in ('completed','completed_partial','unsupported','failed')
        )""",
        (attempt_id, attempt["job_id"], attempt["provider"], attempt["query"],
         attempt.get("requested_limit", 10), attempt.get("started_at") or _now_iso(),
         attempt.get("completed_at"), attempt.get("outcome"),
         _json(attempt.get("diagnostics", attempt.get("diagnostics_json", {}))),
         attempt.get("provider_request_id"), attempt["job_id"]),
        )
        if cursor.rowcount != 1:
            raise ValueError(f"research job {attempt['job_id']} is terminal")


def record_search_results(con, job_id, attempt_id, results):
    _nonterminal_job(con, job_id)
    attempt = con.execute("select * from catalyst_search_attempts where attempt_id = ?", (attempt_id,)).fetchone()
    if attempt is None or attempt["job_id"] != job_id:
        raise ValueError("search attempt does not belong to job")
    saved = []
    with con:
        for position, result in enumerate(results, 1):
            result_id = result.get("result_id", position)
            try:
                result_id = int(result_id)
            except (TypeError, ValueError) as exc:
                raise ValueError("search result id is invalid") from exc
            row = {
            "search_result_id": result.get("search_result_id") or _id("csr_"),
            "job_id": job_id,
            "attempt_id": attempt_id,
            "result_id": result_id,
            "query": result.get("query") or attempt["query"],
            "rank": result.get("rank", position),
            "title": result.get("title"),
            "url": result.get("url") or "",
            "snippet": result.get("snippet"),
            "metadata_json": _json(result.get("metadata", {})),
            }
            if not row["url"]:
                raise ValueError("search result url is required")
            cursor = con.execute(
            """insert into catalyst_search_results(
                search_result_id,job_id,attempt_id,result_id,query,rank,title,url,snippet,metadata_json
            ) select :search_result_id,:job_id,:attempt_id,:result_id,:query,:rank,:title,:url,:snippet,:metadata_json
            where exists (select 1 from catalyst_research_jobs where job_id = :job_id and status not in ('completed','completed_partial','unsupported','failed'))
            on conflict(job_id,result_id) do update set
                attempt_id=excluded.attempt_id,query=excluded.query,rank=excluded.rank,title=excluded.title,
                url=excluded.url,snippet=excluded.snippet,metadata_json=excluded.metadata_json""",
            row,
            )
            if cursor.rowcount != 1:
                raise ValueError(f"research job {job_id} is terminal")
            saved.append(row)
    return saved


def save_snapshot(con, snapshot):
    raw_html = snapshot.get("raw_html")
    structural_html = snapshot.get("structural_html")
    normalized = snapshot.get("normalized", snapshot.get("normalized_json", {}))
    content = raw_html or structural_html or _json(normalized)
    computed_hash = hashlib.sha256(str(content).encode()).hexdigest()
    supplied_hash = snapshot.get("content_hash")
    if supplied_hash is not None and supplied_hash != computed_hash:
        raise ValueError("content hash does not match snapshot content")
    content_hash = supplied_hash or computed_hash
    con.execute(
        """insert or ignore into catalyst_source_snapshots(
            content_hash,requested_url,final_url,content_type,fetched_at,raw_html,structural_html,
            normalized_json,snapshot_schema_version,response_bytes,truncated
        ) values (?,?,?,?,?,?,?,?,?,?,?)""",
        (content_hash, snapshot.get("requested_url") or snapshot.get("url") or "", snapshot.get("final_url"),
         snapshot.get("content_type"), snapshot.get("fetched_at") or _now_iso(), raw_html,
         structural_html, _json(normalized),
         snapshot.get("snapshot_schema_version"), snapshot.get("response_bytes"), int(bool(snapshot.get("truncated", False)))),
    )
    con.commit()
    return content_hash


def prune_unreferenced_snapshots(con):
    referenced = {
        row[0]
        for row in con.execute("select snapshot_hash from catalyst_ir_sources where snapshot_hash is not null")
    }
    referenced.update(row[0] for row in con.execute("select source_snapshot_hash from catalyst_source_adapters where source_snapshot_hash is not null"))
    for column in ("source_content_hashes_json", "page_content_hashes_json"):
        for row in con.execute(f"select {column} from catalyst_adapter_validations"):
            values = _decode(row[0]) or []
            referenced.update(values if isinstance(values, list) else [])
    rows = con.execute("select content_hash from catalyst_source_snapshots").fetchall()
    removable = [row[0] for row in rows if row[0] not in referenced]
    if removable:
        con.executemany("delete from catalyst_source_snapshots where content_hash = ?", ((item,) for item in removable))
        con.commit()
    return len(removable)


def save_source(con, source):
    job_id = source.get("job_id")
    _nonterminal_job(con, job_id)
    source_id = source.get("source_id") or _id("cis_")
    row = {
        "source_id": source_id, "job_id": job_id, "ticker": _ticker(source.get("ticker")),
        "source_type": source.get("source_type"), "url": source.get("url") or "",
        "final_url": source.get("final_url"), "acceptance_status": source.get("acceptance_status", "pending"),
        "extraction_status": source.get("extraction_status", "pending"), "active_adapter_id": source.get("active_adapter_id"),
        "evidence_result_ids_json": _json(source.get("evidence_result_ids", [])), "requested_start": source.get("requested_start"),
        "requested_end": source.get("requested_end"), "coverage_start": source.get("coverage_start"), "coverage_end": source.get("coverage_end"),
        "page_count": source.get("page_count", 0), "item_count": source.get("item_count", 0), "content_hash": source.get("content_hash"),
        "snapshot_hash": source.get("snapshot_hash") or source.get("content_hash"), "truncation_reason": source.get("truncation_reason"),
        "discovery_provider": source.get("discovery_provider"), "execution_path": source.get("execution_path"), "checked_at": source.get("checked_at"),
    }
    if row["source_type"] not in _SOURCE_TYPES:
        raise ValueError("source type is invalid")
    if not row["url"]:
        raise ValueError("source url is required")
    job_ticker = _job(con, job_id)["ticker"]
    if row["ticker"] != job_ticker:
        raise ValueError("source ticker does not match job ticker")
    with con:
        cursor = con.execute(
        """insert into catalyst_ir_sources(
            source_id,job_id,ticker,source_type,url,final_url,acceptance_status,extraction_status,active_adapter_id,
            evidence_result_ids_json,requested_start,requested_end,coverage_start,coverage_end,page_count,item_count,
            content_hash,snapshot_hash,truncation_reason,discovery_provider,execution_path,checked_at
        ) select ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,? where exists (
            select 1 from catalyst_research_jobs where job_id = ? and status not in ('completed','completed_partial','unsupported','failed')
        )""",
        (*tuple(row.values()), job_id),
        )
        if cursor.rowcount != 1:
            raise ValueError(f"research job {job_id} is terminal")
    row["evidence_result_ids"] = _decode(row.pop("evidence_result_ids_json"))
    return row


def create_adapter_candidate(con, candidate):
    ticker = _ticker(candidate.get("ticker"))
    source_type = candidate.get("source_type")
    if source_type not in {"press_releases", "events_presentations"}:
        raise ValueError("adapter source type is invalid")
    _nonterminal_job(con, candidate.get("job_id")) if candidate.get("job_id") else None
    latest = con.execute("select coalesce(max(version), 0) from catalyst_source_adapters where ticker = ? and source_type = ?", (ticker, source_type)).fetchone()[0]
    adapter_id = candidate.get("adapter_id") or _id("ira_")
    adapter_json = candidate.get("adapter_json", candidate.get("adapter", {}))
    row = {
        "adapter_id": adapter_id, "ticker": ticker, "source_type": source_type, "version": latest + 1,
        "adapter_schema_version": candidate.get("adapter_schema_version", ADAPTER_SCHEMA_VERSION),
        "source_url": candidate.get("source_url") or candidate.get("url") or "", "allowed_hosts_json": _json(candidate.get("allowed_hosts", [])),
        "access_mode": candidate.get("access_mode"), "adapter_json": _json(adapter_json), "state": "candidate",
        "generation_model": candidate.get("generation_model") or candidate.get("model"), "prompt_schema_version": candidate.get("prompt_schema_version"),
        "source_snapshot_hash": candidate.get("source_snapshot_hash") or candidate.get("snapshot_hash") or candidate.get("content_hash"), "input_hash": candidate.get("input_hash"),
        "output_hash": candidate.get("output_hash"), "created_at": candidate.get("created_at") or _now_iso(),
    }
    if not row["source_url"]:
        raise ValueError("adapter source url is required")
    con.execute(
        """insert into catalyst_source_adapters(
            adapter_id,ticker,source_type,version,adapter_schema_version,source_url,allowed_hosts_json,access_mode,
            adapter_json,state,generation_model,prompt_schema_version,source_snapshot_hash,input_hash,output_hash,created_at
        ) values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        tuple(row.values()),
    )
    con.commit()
    result = dict(row)
    result["allowed_hosts"] = _decode(result.pop("allowed_hosts_json"))
    result["adapter"] = _decode(result.pop("adapter_json"))
    return result


def record_adapter_validation(con, validation):
    adapter = con.execute("select state from catalyst_source_adapters where adapter_id = ?", (validation.get("adapter_id"),)).fetchone()
    adapter_id = validation.get("adapter_id")
    if adapter is None:
        raise ValueError(f"adapter {adapter_id} was not found")
    if adapter["state"] != "candidate":
        raise ValueError(f"adapter {adapter_id} is terminal")
    _nonterminal_job(con, validation.get("job_id"))
    status = validation.get("status") or validation.get("validation_status")
    if status not in {"passed", "failed"}:
        raise ValueError("adapter validation status is invalid")
    with con:
        cursor = con.execute(
            """insert into catalyst_adapter_validations(
                validation_id,adapter_id,job_id,validator_version,executor_version,status,report_json,
                source_content_hashes_json,page_content_hashes_json,validated_at
            ) select ?,?,?,?,?,?,?,?,?,? where exists (
                select 1 from catalyst_research_jobs
                where job_id = ? and status = 'running'
            )""",
            (
                validation.get("validation_id") or _id("iav_"),
                adapter_id,
                validation["job_id"],
                validation.get("validator_version"),
                validation.get("executor_version"),
                status,
                _json(validation.get("report", validation.get("report_json", {}))),
                _json(validation.get("source_content_hashes", [])),
                _json(validation.get("page_content_hashes", [])),
                validation.get("validated_at") or _now_iso(),
                validation["job_id"],
            ),
        )
        if cursor.rowcount != 1:
            raise ValueError(f"research job {validation['job_id']} is terminal")
        if status == "failed":
            con.execute(
                "update catalyst_source_adapters set state = 'failed_validation' where adapter_id = ? and state = 'candidate'",
                (adapter_id,),
            )


def _require_candidate_with_passing_validation(con, adapter_id):
    adapter = con.execute("select * from catalyst_source_adapters where adapter_id = ?", (adapter_id,)).fetchone()
    if adapter is None:
        raise ValueError(f"adapter {adapter_id} was not found")
    if adapter["state"] != "candidate":
        raise ValueError(f"adapter {adapter_id} is not a candidate and has no passing validation")
    if con.execute("select 1 from catalyst_adapter_validations where adapter_id = ? and status = 'passed'", (adapter_id,)).fetchone() is None:
        raise ValueError(f"adapter {adapter_id} has no passing validation")
    return adapter


def activate_adapter(con, adapter_id, activated_at):
    with con:
        adapter = _require_candidate_with_passing_validation(con, adapter_id)
        con.execute("update catalyst_source_adapters set state = 'superseded', superseded_at = ? where ticker = ? and source_type = ? and state = 'active'", (activated_at, adapter["ticker"], adapter["source_type"]))
        changed = con.execute("update catalyst_source_adapters set state = 'active', validated_at = coalesce(validated_at, ?), activated_at = ? where adapter_id = ? and state = 'candidate'", (activated_at, activated_at, adapter_id)).rowcount
        if changed != 1:
            raise ValueError(f"adapter {adapter_id} could not be activated")


def mark_adapter_stale(con, adapter_id, stale_at):
    adapter = con.execute("select state from catalyst_source_adapters where adapter_id = ?", (adapter_id,)).fetchone()
    if adapter is None:
        raise ValueError(f"adapter {adapter_id} was not found")
    if adapter["state"] != "active":
        raise ValueError(f"adapter {adapter_id} is not active")
    con.execute("update catalyst_source_adapters set state = 'stale', stale_at = ? where adapter_id = ?", (stale_at, adapter_id))
    con.commit()


def load_active_adapter(con, ticker, source_type):
    row = con.execute("select * from catalyst_source_adapters where ticker = ? and source_type = ? and state = 'active'", (_ticker(ticker), source_type)).fetchone()
    result = _decode_row(row, ("allowed_hosts_json", "adapter_json"))
    if result is None:
        return None
    result["allowed_hosts"] = result.pop("allowed_hosts_json")
    result["adapter"] = result.pop("adapter_json")
    return result


def save_finalized_observations(con, job_id, events, classifications):
    job = _job(con, job_id)
    if job["status"] in _TERMINAL_JOB_STATES:
        raise ValueError(f"research job {job_id} is terminal")
    classification_by_id = {item.get("event_id") or item.get("id"): item for item in classifications}
    with con:
        for position, event in enumerate(events, 1):
            event_id = event.get("event_id") or event.get("id") or _id("ire_")
            classification = (
                classification_by_id.get(event_id)
                or classification_by_id.get(event.get("id"))
                or classification_by_id.get(position)
            )
            state = (classification or event).get("earnings_state", "ambiguous")
            if state not in {"earnings", "non_earnings", "ambiguous"}:
                raise ValueError("event earnings state is invalid")
            count_date = event.get("count_date") or event.get("event_date") or event.get("published_date")
            title = str(event.get("title") or "").strip()
            canonical_url = event.get("canonical_url") or event.get("url")
            if not event.get("source_id"):
                raise ValueError("event source id is required")
            if not count_date:
                raise ValueError("event count date is required")
            if not title:
                raise ValueError("event title is required")
            if not canonical_url:
                raise ValueError("event url is required")
            if _ticker(event.get("ticker")) != job["ticker"]:
                raise ValueError("event ticker does not match job ticker")
            source_row = con.execute("select job_id, ticker, source_type from catalyst_ir_sources where source_id = ?", (event["source_id"],)).fetchone()
            if source_row is None or source_row["job_id"] != job_id:
                raise ValueError("event source does not belong to job")
            if source_row["ticker"] != _ticker(event.get("ticker")) or source_row["source_type"] != event.get("source_type"):
                raise ValueError("event source does not match event")
            normalized_title = event.get("normalized_title") or " ".join(title.lower().split())
            existing = con.execute(
                "select event_id from catalyst_ir_events where job_id = ? and ticker = ? and source_type = ? and count_date = ? and normalized_title = ? and canonical_url = ?",
                (job_id, _ticker(event.get("ticker")), event.get("source_type"), count_date, normalized_title, canonical_url),
            ).fetchone()
            if existing:
                event_id = existing["event_id"]
            cursor = con.execute(
                """insert into catalyst_ir_events(
                    event_id,job_id,source_id,ticker,published_date,event_date,count_date,title,normalized_title,canonical_url,
                    source_type,earnings_state,classification_method,adapter_id,adapter_version,executor_version,first_seen_at,content_hash
                ) select ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,? where exists (
                    select 1 from catalyst_research_jobs where job_id = ? and status not in ('completed','completed_partial','unsupported','failed')
                )
                on conflict(job_id,ticker,source_type,count_date,normalized_title,canonical_url) do update set earnings_state=excluded.earnings_state""",
                (event_id, job_id, event["source_id"], _ticker(event.get("ticker")), event.get("published_date"), event.get("event_date"),
                 count_date, title, normalized_title, canonical_url,
                 event["source_type"], state, (classification or event).get("classification_method"), event.get("adapter_id"), event.get("adapter_version"),
                 event.get("executor_version"), event.get("first_seen_at") or _now_iso(), event.get("content_hash"), job_id),
            )
            if cursor.rowcount != 1:
                raise ValueError(f"research job {job_id} is terminal")
            con.execute(
                """insert or replace into catalyst_ir_classifications(
                    event_id,earnings_state,classification_method,model,prompt_schema_version,input_hash,output_hash,classified_at
                ) values (?,?,?,?,?,?,?,?)""",
                (event_id, state, (classification or event).get("classification_method", "manual"), (classification or event).get("model"),
                 (classification or event).get("prompt_schema_version"), (classification or event).get("input_hash"),
                 (classification or event).get("output_hash"), (classification or event).get("classified_at") or _now_iso()),
            )


def finalize_job(con, job_id, result):
    job = _job(con, job_id)
    if job["status"] in _TERMINAL_JOB_STATES:
        raise ValueError(f"research job {job_id} is terminal")
    status = result.get("status")
    if status not in _TERMINAL_JOB_STATES:
        raise ValueError("final job status is invalid")
    error_summary = result.get("error_summary") or result.get("error")
    if error_summary:
        error_summary = str(error_summary)[:1000]
    with con:
        cursor = con.execute(
            """update catalyst_research_jobs set status=?, statistics_json=?, warnings_json=?, next_actions_json=?,
                error_summary=?, completed_at=?, execution_paths_json=coalesce(?, execution_paths_json), call_counts_json=coalesce(?, call_counts_json)
                where job_id=? and status = 'running'""",
            (status, _json(result.get("statistics", {})), _json(result.get("warnings", [])), _json(result.get("next_actions", [])),
             error_summary, result.get("completed_at") or _now_iso(),
             _json(result["execution_paths"]) if "execution_paths" in result else None,
             _json(result["call_counts"]) if "call_counts" in result else None, job_id),
        )
        if cursor.rowcount != 1:
            current = _job(con, job_id)
            if current["status"] in _TERMINAL_JOB_STATES:
                raise ValueError(f"research job {job_id} is terminal")
            raise ValueError(f"research job {job_id} cannot finalize from {current['status']}; job must be running")


def load_job_result(con, job_id):
    job = _job(con, job_id)
    sources = [_decode_row(row, ("evidence_result_ids_json",)) for row in con.execute("select * from catalyst_ir_sources where job_id = ? order by source_type, source_id", (job_id,))]
    for source in sources:
        source["evidence_result_ids"] = source.pop("evidence_result_ids_json")
    result = {
        "schema_version": RESULT_SCHEMA_VERSION, "research_version": job["research_version"], "job_id": job_id,
        "status": job["status"], "ticker": job["ticker"], "company_name": job["company_name"], "as_of": job["as_of"],
        "requested_window": {"start": job["requested_start"], "end": job["requested_end"], "years": job["requested_years"]},
        "sources": sources, "statistics": _decode(job["statistics_json"]) or {}, "warnings": _decode(job["warnings_json"]) or [],
        "next_actions": _decode(job["next_actions_json"]) or [], "error_summary": job["error_summary"],
        "completed_at": job["completed_at"], "observation_count": con.execute("select count(*) from catalyst_ir_events where job_id = ?", (job_id,)).fetchone()[0],
    }
    return result


def load_latest_result(con, ticker):
    normalized = _ticker(ticker)
    row = con.execute(
        """select job_id from catalyst_research_jobs where ticker = ? and status in ('completed','completed_partial')
           order by case status when 'completed' then 0 else 1 end, completed_at desc limit 1""", (normalized,)
    ).fetchone()
    if not row:
        return None
    result = load_job_result(con, row["job_id"])
    latest = con.execute(
        "select job_id, status, completed_at from catalyst_research_jobs where ticker = ? order by created_at desc limit 1",
        (normalized,),
    ).fetchone()
    result["latest_job_id"] = latest["job_id"]
    result["latest_job_status"] = latest["status"]
    result["latest_job_completed_at"] = latest["completed_at"]
    return result


def _encode_cursor(payload):
    return base64.urlsafe_b64encode(_json(payload).encode()).decode().rstrip("=")


def _decode_cursor(value):
    try:
        padded = value + "=" * (-len(value) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded).decode())
    except (ValueError, TypeError, UnicodeError):
        raise ValueError("event cursor is invalid") from None
    if not isinstance(payload, dict) or not {"ticker", "count_date", "event_id"} <= payload.keys():
        raise ValueError("event cursor is invalid")
    if (
        not isinstance(payload["ticker"], str)
        or not payload["ticker"]
        or not isinstance(payload["count_date"], str)
        or not payload["count_date"]
        or not isinstance(payload["event_id"], str)
        or not payload["event_id"]
        or (payload.get("job_id") is not None and not isinstance(payload.get("job_id"), str))
    ):
        raise ValueError("event cursor is invalid")
    return payload


def load_events_page(con, ticker, job_id, limit, cursor):
    normalized = _ticker(ticker)
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 200:
        raise ValueError("event limit must be between 1 and 200")
    payload = _decode_cursor(cursor) if cursor else None
    if payload and (payload["ticker"] != normalized or payload.get("job_id") != job_id):
        raise ValueError("event cursor does not belong to ticker or job")
    where = ["ticker = ?"]
    params = [normalized]
    if job_id:
        _job(con, job_id)
        where.append("job_id = ?")
        params.append(job_id)
    if payload:
        where.append("(count_date > ? or (count_date = ? and event_id > ?))")
        params.extend([payload["count_date"], payload["count_date"], payload["event_id"]])
    rows = con.execute(
        f"select * from catalyst_ir_events where {' and '.join(where)} order by count_date, event_id limit ?",
        (*params, limit + 1),
    ).fetchall()
    has_more = len(rows) > limit
    rows = rows[:limit]
    events = [dict(row) for row in rows]
    next_cursor = None
    if has_more and rows:
        last = rows[-1]
        next_cursor = _encode_cursor({"ticker": normalized, "job_id": job_id, "count_date": last["count_date"], "event_id": last["event_id"]})
    return {"ticker": normalized, "job_id": job_id, "events": events, "next_cursor": next_cursor}

from collections import Counter
from collections.abc import Mapping
import base64
import hashlib
import json
import re
import secrets
import sqlite3
from datetime import UTC, date, datetime
from pathlib import Path

from app.agents.catalyst_research.config import (
    ADAPTER_SCHEMA_VERSION,
    LEGACY_RESULT_SCHEMA_VERSION,
    RESEARCH_MODES,
    RESEARCH_VERSION,
    RESULT_SCHEMA_VERSION,
)


ROOT = Path(__file__).resolve().parents[4]
DEFAULT_DB_PATH = ROOT / "data" / "local_system" / "market_data.sqlite"
_TERMINAL_JOB_STATES = {"completed", "completed_partial", "unsupported", "failed"}
_JOB_STATES = {"queued", "running", *_TERMINAL_JOB_STATES}
_ADAPTER_STATES = {"candidate", "active", "failed_validation", "stale", "superseded"}
_SOURCE_TYPES = {"ir_home", "press_releases", "events_presentations", "earnings_results"}
_REGISTRY_CONFIDENCE = {"high", "medium", "low"}
_ENDPOINT_CHANNELS = {"press_releases", "events_presentations", "earnings_results"}
_ENDPOINT_TYPES = {"rss", "atom", "search_domain", "archive"}
_ENDPOINT_STATES = {"unverified", "active", "quiet", "stale", "failing", "retired"}
_ENDPOINT_HEALTH_COLUMNS = {
    "status",
    "last_checked_at",
    "last_success_at",
    "last_item_at",
    "last_guid",
    "consecutive_failures",
    "last_error_code",
}
_DISCOVERY_METHODS = {"rss", "atom", "search", "archive_adapter", "manual"}
_EXTRACTION_PROVIDERS = {"feed_metadata", "direct_http", "firecrawl", "manual"}
_SEARCH_PURPOSES = {"source_discovery", "historical_backfill", "incremental_gap_check"}


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


def _validated_event_id(value):
    if not isinstance(value, str) or not value or value != value.strip() or len(value) > 200:
        raise ValueError("event id is invalid")
    return value


def _classification_key(item):
    if not isinstance(item, dict):
        return None
    if "event_id" in item and item["event_id"] is not None:
        value = item["event_id"]
    elif "id" in item:
        value = item["id"]
    else:
        return None
    try:
        hash(value)
    except TypeError:
        return None
    return value


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
            completed_at text,
            mode text not null default 'research'
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
            provider_request_id text,
            search_purpose text not null default 'source_discovery'
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
            acceptance_status text not null default 'pending' check (acceptance_status in ('pending','accepted','ambiguous','rejected')),
            extraction_status text not null default 'pending' check (extraction_status in ('pending','complete','partial','unsupported','failed','discovery_required')),
            active_adapter_id text,
            adapter_version integer,
            executor_version text,
            evidence_result_ids_json text not null default '[]',
            requested_start text,
            requested_end text,
            coverage_start text,
            coverage_end text,
            coverage_continuous integer check (coverage_continuous in (0,1)),
            verification_reason text,
            page_count integer not null default 0,
            item_count integer not null default 0,
            content_hash text,
            snapshot_hash text references catalyst_source_snapshots(content_hash),
            truncation_reason text,
            discovery_provider text,
            execution_path text,
            checked_at text,
            endpoint_id text,
            discovery_method text,
            extraction_provider text,
            attempts_json text
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
            canonical_url text,
            source_type text not null check (source_type in ('press_releases','events_presentations','earnings_results')),
            earnings_state text not null default 'ambiguous' check (earnings_state in ('earnings','non_earnings','ambiguous')),
            classification_method text,
            adapter_id text,
            adapter_version integer,
            executor_version text,
            first_seen_at text not null,
            content_hash text,
            endpoint_id text,
            external_guid text,
            discovery_method text,
            extraction_provider text,
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
        create table if not exists catalyst_company_registry (
            ticker text primary key,
            company_name text not null,
            cik text,
            official_domains_json text not null,
            source_confidence text not null,
            registry_version integer not null,
            discovered_at text not null,
            last_validated_at text,
            updated_at text not null
        );
        create table if not exists catalyst_source_endpoints (
            endpoint_id text primary key,
            ticker text not null,
            channel text not null,
            endpoint_type text not null,
            url text,
            domain text not null,
            status text not null,
            confidence text not null,
            discovered_at text not null,
            last_checked_at text,
            last_success_at text,
            last_item_at text,
            last_guid text,
            consecutive_failures integer not null default 0,
            last_error_code text,
            updated_at text not null
        );
        create table if not exists catalyst_endpoint_checks (
            check_id text primary key,
            endpoint_id text not null,
            job_id text,
            checked_at text not null,
            outcome text not null,
            http_status integer,
            item_count integer not null,
            new_item_count integer not null,
            newest_item_at text,
            error_code text,
            content_hash text
        );
        create index if not exists idx_catalyst_endpoints_ticker
        on catalyst_source_endpoints(ticker, channel);
        create index if not exists idx_catalyst_endpoint_checks_endpoint
        on catalyst_endpoint_checks(endpoint_id, checked_at desc);
        create unique index if not exists idx_catalyst_endpoint_identity
        on catalyst_source_endpoints(ticker, channel, endpoint_type, coalesce(lower(url), lower(domain)));
        """
    )
    _migrate_schema(con)
    _migrate_v1_1_schema(con)
    return con


def _ensure_column(con, table, name, definition):
    columns = {row[1] for row in con.execute(f"pragma table_info({table})")}
    if name not in columns:
        con.execute(f"alter table {table} add column {name} {definition}")


def _migrate_v1_1_schema(con):
    _ensure_column(con, "catalyst_research_jobs", "mode", "text not null default 'research'")
    _ensure_column(con, "catalyst_search_attempts", "search_purpose", "text not null default 'source_discovery'")
    for column in ("endpoint_id", "discovery_method", "extraction_provider"):
        _ensure_column(con, "catalyst_ir_sources", column, "text")
    _ensure_column(con, "catalyst_ir_sources", "external_guid", "text")
    _ensure_column(con, "catalyst_ir_sources", "attempts_json", "text")
    event_sql = con.execute("select sql from sqlite_master where type = 'table' and name = 'catalyst_ir_events'").fetchone()
    if event_sql is not None and "'earnings_results'" not in event_sql[0]:
        con.execute("pragma legacy_alter_table = on")
        con.execute("pragma foreign_keys = off")
        con.execute("alter table catalyst_ir_events rename to catalyst_ir_events_legacy")
        con.execute("""create table catalyst_ir_events (
            event_id text primary key,
            job_id text not null references catalyst_research_jobs(job_id),
            source_id text not null references catalyst_ir_sources(source_id),
            ticker text not null,
            published_date text,
            event_date text,
            count_date text not null,
            title text not null,
            normalized_title text not null,
            canonical_url text,
            source_type text not null check (source_type in ('press_releases','events_presentations','earnings_results')),
            earnings_state text not null default 'ambiguous' check (earnings_state in ('earnings','non_earnings','ambiguous')),
            classification_method text,
            adapter_id text,
            adapter_version integer,
            executor_version text,
            first_seen_at text not null,
            content_hash text,
            endpoint_id text,
            external_guid text,
            discovery_method text,
            extraction_provider text,
            unique(job_id, ticker, source_type, count_date, normalized_title, canonical_url)
        )""")
        columns = [row[1] for row in con.execute("pragma table_info(catalyst_ir_events_legacy)")]
        con.execute(
            f"insert into catalyst_ir_events ({','.join(columns)}) select {','.join(columns)} from catalyst_ir_events_legacy"
        )
        con.execute("drop table catalyst_ir_events_legacy")
        con.execute("create unique index if not exists idx_catalyst_event_job_key on catalyst_ir_events(job_id, ticker, source_type, count_date, normalized_title, canonical_url)")
        con.execute("pragma foreign_keys = on")
        con.execute("pragma legacy_alter_table = off")
    for column in ("endpoint_id", "external_guid", "discovery_method", "extraction_provider"):
        _ensure_column(con, "catalyst_ir_events", column, "text")
    con.commit()


def _migrate_schema(con):
    source_columns = {row[1]: row for row in con.execute("pragma table_info(catalyst_ir_sources)")}
    source_sql = con.execute("select sql from sqlite_master where type = 'table' and name = 'catalyst_ir_sources'").fetchone()[0].lower()
    source_needs_rebuild = "'ambiguous'" not in source_sql or "discovery_required" not in source_sql
    if source_needs_rebuild:
        con.execute("pragma legacy_alter_table = on")
        con.execute("pragma foreign_keys = off")
        con.execute("alter table catalyst_ir_sources rename to catalyst_ir_sources_legacy")
        con.execute("""create table catalyst_ir_sources_new (
            source_id text primary key,
            job_id text not null references catalyst_research_jobs(job_id),
            ticker text not null,
            source_type text not null check (source_type in ('ir_home','press_releases','events_presentations','earnings_results')),
            url text not null,
            final_url text,
            acceptance_status text not null default 'pending' check (acceptance_status in ('pending','accepted','ambiguous','rejected')),
            extraction_status text not null default 'pending' check (extraction_status in ('pending','complete','partial','unsupported','failed','discovery_required')),
            active_adapter_id text,
            adapter_version integer,
            executor_version text,
            evidence_result_ids_json text not null default '[]',
            requested_start text,
            requested_end text,
            coverage_start text,
            coverage_end text,
            coverage_continuous integer check (coverage_continuous in (0,1)),
            verification_reason text,
            page_count integer not null default 0,
            item_count integer not null default 0,
            content_hash text,
            snapshot_hash text references catalyst_source_snapshots(content_hash),
            truncation_reason text,
            discovery_provider text,
            execution_path text,
            checked_at text
        )""")
        old_names = {row[1] for row in con.execute("pragma table_info(catalyst_ir_sources_legacy)")}
        new_names = [row[1] for row in con.execute("pragma table_info(catalyst_ir_sources_new)")]
        names = [name for name in new_names if name in old_names]
        con.execute(
            f"insert into catalyst_ir_sources_new ({','.join(names)}) select {','.join(names)} from catalyst_ir_sources_legacy"
        )
        con.execute("drop table catalyst_ir_sources_legacy")
        con.execute("alter table catalyst_ir_sources_new rename to catalyst_ir_sources")
        con.execute("pragma foreign_keys = on")
        con.execute("pragma legacy_alter_table = off")
    else:
        if "coverage_continuous" not in source_columns:
            con.execute("alter table catalyst_ir_sources add column coverage_continuous integer check (coverage_continuous in (0,1))")
        if "verification_reason" not in source_columns:
            con.execute("alter table catalyst_ir_sources add column verification_reason text")
        if "adapter_version" not in source_columns:
            con.execute("alter table catalyst_ir_sources add column adapter_version integer")
        if "executor_version" not in source_columns:
            con.execute("alter table catalyst_ir_sources add column executor_version text")
    event_columns = {row[1]: row for row in con.execute("pragma table_info(catalyst_ir_events)")}
    if event_columns.get("canonical_url", (None, None, None, 0))[3] == 1:
        con.execute("pragma legacy_alter_table = on")
        con.execute("pragma foreign_keys = off")
        con.execute("alter table catalyst_ir_events rename to catalyst_ir_events_legacy")
        con.execute("""create table catalyst_ir_events_new (
            event_id text primary key,
            job_id text not null references catalyst_research_jobs(job_id),
            source_id text not null references catalyst_ir_sources(source_id),
            ticker text not null,
            published_date text,
            event_date text,
            count_date text not null,
            title text not null,
            normalized_title text not null,
            canonical_url text,
            source_type text not null check (source_type in ('press_releases','events_presentations','earnings_results')),
            earnings_state text not null default 'ambiguous' check (earnings_state in ('earnings','non_earnings','ambiguous')),
            classification_method text,
            adapter_id text,
            adapter_version integer,
            executor_version text,
            first_seen_at text not null,
            content_hash text,
            unique(job_id, ticker, source_type, count_date, normalized_title, canonical_url)
        )""")
        con.execute("insert into catalyst_ir_events_new select * from catalyst_ir_events_legacy")
        con.execute("drop table catalyst_ir_events_legacy")
        con.execute("alter table catalyst_ir_events_new rename to catalyst_ir_events")
        con.execute("create unique index if not exists idx_catalyst_event_job_key on catalyst_ir_events(job_id, ticker, source_type, count_date, normalized_title, canonical_url)")
        con.execute("pragma foreign_keys = on")
        con.execute("pragma legacy_alter_table = off")
    con.commit()


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
    mode = request.get("mode") or "research"
    if mode not in RESEARCH_MODES:
        raise ValueError("research mode is invalid")
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
        "mode": mode,
        "execution_paths_json": _json({}),
        "call_counts_json": _json({}),
        "created_at": _now_iso(now),
    }
    con.execute(
        """insert into catalyst_research_jobs(
            job_id,ticker,company_name,cik,requested_years,requested_start,requested_end,
            as_of,research_version,status,mode,execution_paths_json,call_counts_json,created_at
        ) values (:job_id,:ticker,:company_name,:cik,:requested_years,:requested_start,:requested_end,
            :as_of,:research_version,:status,:mode,:execution_paths_json,:call_counts_json,:created_at)""",
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
    cursor = con.execute("update catalyst_research_jobs set status = 'running', started_at = ? where job_id = ? and status = 'queued'", (started_at, job_id))
    if cursor.rowcount != 1:
        current = _job(con, job_id)
        if current["status"] in _TERMINAL_JOB_STATES:
            raise ValueError(f"research job {job_id} is terminal")
        raise ValueError(f"research job {job_id} cannot start from {current['status']}")
    con.commit()


def update_resolved_company(con, job_id, company):
    if not isinstance(company, dict):
        raise ValueError("company identity is required")
    with con:
        cursor = con.execute(
            "update catalyst_research_jobs set company_name = ?, cik = ? where job_id = ? and status = 'running'",
            (company.get("company_name") or company.get("name"), str(company.get("cik")) if company.get("cik") is not None else None, job_id),
        )
        if cursor.rowcount != 1:
            current = _job(con, job_id)
            if current["status"] in _TERMINAL_JOB_STATES:
                raise ValueError(f"research job {job_id} is terminal")
            raise ValueError(f"research job {job_id} cannot update from {current['status']}")
    return dict(_job(con, job_id))


def _sanitize_error(value):
    message = " ".join(str(value).split())
    message = re.sub(r"(?i)\bauthorization\s*[:=]\s*(\S+)(?:\s+\S+)?", r"Authorization: \1 [redacted]", message)
    message = re.sub(r"(?i)\b(?:cookie|set-cookie)\s*[:=]\s*\S+", "Cookie: [redacted]", message)
    message = re.sub(r"(?i)\bbearer\s+\S+", "Bearer [redacted]", message)
    message = re.sub(r"(?i)(api[ _-]?key|token|client[ _-]?secret|password)\s*[:=]\s*\S+", r"\1=[redacted]", message)
    return message[:1000] or "workflow failed"


def _sanitize_runtime_report(value):
    if isinstance(value, Mapping):
        return {
            key: _sanitize_runtime_report(item)
            for key, item in value.items()
            if isinstance(key, str) and key.casefold() not in {"html", "raw_html", "structural_html"}
        }
    if isinstance(value, list):
        return [_sanitize_runtime_report(item) for item in value]
    return value


def fail_job(con, job_id, error_summary, *, completed_at=None):
    with con:
        cursor = con.execute(
            "update catalyst_research_jobs set status = 'failed', error_summary = ?, completed_at = ? where job_id = ? and status in ('queued','running')",
            (_sanitize_error(error_summary), completed_at or _now_iso(), job_id),
        )
        if cursor.rowcount != 1:
            current = _job(con, job_id)
            if current["status"] in _TERMINAL_JOB_STATES:
                raise ValueError(f"research job {job_id} is terminal")
            raise ValueError(f"research job {job_id} cannot fail from {current['status']}")


def record_search_attempt(con, attempt):
    _nonterminal_job(con, attempt.get("job_id"))
    attempt_id = attempt.get("attempt_id") or _id("csa_")
    if not attempt.get("provider") or not attempt.get("query"):
        raise ValueError("search attempt provider and query are required")
    purpose = attempt.get("search_purpose") or "source_discovery"
    if purpose not in _SEARCH_PURPOSES:
        raise ValueError("search attempt purpose is invalid")
    with con:
        cursor = con.execute(
        """insert into catalyst_search_attempts(
            attempt_id,job_id,provider,query,requested_limit,started_at,completed_at,
            outcome,diagnostics_json,provider_request_id,search_purpose
        ) select ?,?,?,?,?,?,?,?,?,?,? where exists (
            select 1 from catalyst_research_jobs where job_id = ? and status not in ('completed','completed_partial','unsupported','failed')
        )""",
        (attempt_id, attempt["job_id"], attempt["provider"], attempt["query"],
         attempt.get("requested_limit", 10), attempt.get("started_at") or _now_iso(),
         attempt.get("completed_at"), attempt.get("outcome"),
         _json(attempt.get("diagnostics", attempt.get("diagnostics_json", {}))),
         attempt.get("provider_request_id"), purpose, attempt["job_id"]),
        )
        if cursor.rowcount != 1:
            raise ValueError(f"research job {attempt['job_id']} is terminal")
    return attempt_id


def update_search_attempt(con, attempt_id, *, outcome, diagnostics=None, completed_at=None, provider_request_id=None):
    with con:
        cursor = con.execute(
            """update catalyst_search_attempts
            set completed_at = coalesce(?, completed_at), outcome = ?, diagnostics_json = ?, provider_request_id = coalesce(?, provider_request_id)
            where attempt_id = ? and exists (
                select 1 from catalyst_research_jobs
                where catalyst_research_jobs.job_id = catalyst_search_attempts.job_id
                  and status not in ('completed','completed_partial','unsupported','failed')
            )""",
            (completed_at or _now_iso(), outcome, _json(diagnostics or {}), provider_request_id, attempt_id),
        )
    if cursor.rowcount == 1:
        return
    row = con.execute(
        "select job_id from catalyst_search_attempts where attempt_id = ?", (attempt_id,)
    ).fetchone()
    if row is None:
        raise ValueError(f"search attempt {attempt_id} was not found")
    job = con.execute("select status from catalyst_research_jobs where job_id = ?", (row["job_id"],)).fetchone()
    if job is not None and job["status"] in _TERMINAL_JOB_STATES:
        raise ValueError(f"research job {row['job_id']} is terminal")
    raise ValueError(f"search attempt {attempt_id} could not be updated")


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


def _provenance_values(item):
    discovery_method = item.get("discovery_method")
    if discovery_method is not None and discovery_method not in _DISCOVERY_METHODS:
        raise ValueError("discovery method is invalid")
    extraction_provider = item.get("extraction_provider")
    if extraction_provider is not None and extraction_provider not in _EXTRACTION_PROVIDERS:
        raise ValueError("extraction provider is invalid")
    return discovery_method, extraction_provider


def _source_row(con, source):
    job_id = source.get("job_id")
    _nonterminal_job(con, job_id)
    source_id = source.get("source_id") or _id("cis_")
    discovery_method, extraction_provider = _provenance_values(source)
    row = {
        "source_id": source_id, "job_id": job_id, "ticker": _ticker(source.get("ticker")),
        "source_type": source.get("source_type"), "url": source.get("url") or "",
        "final_url": source.get("final_url"), "acceptance_status": source.get("acceptance_status", "pending"),
        "extraction_status": source.get("extraction_status", "pending"), "active_adapter_id": source.get("active_adapter_id"),
        "adapter_version": source.get("adapter_version"), "executor_version": source.get("executor_version"),
        "evidence_result_ids_json": _json(source.get("evidence_result_ids", [])), "requested_start": source.get("requested_start"),
        "requested_end": source.get("requested_end"), "coverage_start": source.get("coverage_start"), "coverage_end": source.get("coverage_end"), "coverage_continuous": None if source.get("coverage_continuous") is None else int(bool(source.get("coverage_continuous"))), "verification_reason": source.get("verification_reason"),
        "page_count": source.get("page_count", 0), "item_count": source.get("item_count", 0), "content_hash": source.get("content_hash"),
        "snapshot_hash": source.get("snapshot_hash") if "snapshot_hash" in source else source.get("content_hash"), "truncation_reason": source.get("truncation_reason"),
        "discovery_provider": source.get("discovery_provider"), "execution_path": source.get("execution_path"), "checked_at": source.get("checked_at"),
        "endpoint_id": source.get("endpoint_id"), "external_guid": source.get("external_guid"), "discovery_method": discovery_method, "extraction_provider": extraction_provider,
        "attempts_json": _json(source.get("attempts") or []),
    }
    if row["source_type"] not in _SOURCE_TYPES:
        raise ValueError("source type is invalid")
    if not row["url"]:
        raise ValueError("source url is required")
    job_ticker = _job(con, job_id)["ticker"]
    if row["ticker"] != job_ticker:
        raise ValueError("source ticker does not match job ticker")
    return row


def save_source(con, source):
    row = _source_row(con, source)
    with con:
        cursor = con.execute(
        """insert into catalyst_ir_sources(
            source_id,job_id,ticker,source_type,url,final_url,acceptance_status,extraction_status,active_adapter_id,adapter_version,executor_version,
            evidence_result_ids_json,requested_start,requested_end,coverage_start,coverage_end,coverage_continuous,verification_reason,page_count,item_count,
            content_hash,snapshot_hash,truncation_reason,discovery_provider,execution_path,checked_at,endpoint_id,external_guid,discovery_method,extraction_provider,
            attempts_json
        ) select ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,? where exists (
            select 1 from catalyst_research_jobs where job_id = ? and status not in ('completed','completed_partial','unsupported','failed')
        )""",
            (*tuple(row.values()), row["job_id"]),
        )
        if cursor.rowcount != 1:
            raise ValueError(f"research job {row['job_id']} is terminal")
    row["evidence_result_ids"] = _decode(row.pop("evidence_result_ids_json"))
    row["attempts"] = _decode(row.pop("attempts_json")) or []
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


def activate_adapter_with_source(con, adapter_id, activated_at, source):
    con.execute("begin")
    atomic = _AtomicConnection(con)
    try:
        row = _source_row(atomic, source)
        existing = atomic.execute("select source_id from catalyst_ir_sources where source_id = ?", (row["source_id"],)).fetchone()
        if existing is None:
            saved = save_source(atomic, source)
        else:
            assignments = ",".join(f"{key} = ?" for key in row if key != "source_id")
            atomic.execute(
                f"update catalyst_ir_sources set {assignments} where source_id = ? and job_id = ?",
                tuple(value for key, value in row.items() if key != "source_id") + (row["source_id"], row["job_id"]),
            )
            saved = _dict(atomic.execute("select * from catalyst_ir_sources where source_id = ?", (row["source_id"],)).fetchone())
            saved["evidence_result_ids"] = _decode(saved.pop("evidence_result_ids_json"))
            saved["attempts"] = _decode(saved.pop("attempts_json")) or []
            if saved.get("coverage_continuous") is not None:
                saved["coverage_continuous"] = bool(saved["coverage_continuous"])
        activate_adapter(atomic, adapter_id, activated_at)
    except Exception:
        con.rollback()
        raise
    con.commit()
    return saved


def mark_adapter_stale(con, adapter_id, stale_at):
    adapter = con.execute("select state from catalyst_source_adapters where adapter_id = ?", (adapter_id,)).fetchone()
    if adapter is None:
        raise ValueError(f"adapter {adapter_id} was not found")
    if adapter["state"] != "active":
        raise ValueError(f"adapter {adapter_id} is not active")
    con.execute("update catalyst_source_adapters set state = 'stale', stale_at = ? where adapter_id = ?", (stale_at, adapter_id))
    con.commit()


def record_runtime_adapter_validation(con, validation):
    adapter_id = validation.get("adapter_id")
    adapter = con.execute("select state from catalyst_source_adapters where adapter_id = ?", (adapter_id,)).fetchone()
    if adapter is None:
        raise ValueError(f"adapter {adapter_id} was not found")
    if adapter["state"] != "active":
        raise ValueError(f"adapter {adapter_id} is not active")
    _nonterminal_job(con, validation.get("job_id"))
    status = validation.get("status") or validation.get("validation_status")
    if status not in {"passed", "failed"}:
        raise ValueError("runtime validation status is invalid")
    report = _sanitize_runtime_report(validation.get("report", {}))
    with con:
        con.execute(
            "insert into catalyst_adapter_validations(validation_id,adapter_id,job_id,validator_version,executor_version,status,report_json,source_content_hashes_json,page_content_hashes_json,validated_at) values (?,?,?,?,?,?,?,?,?,?)",
            (validation.get("validation_id") or _id("iarv_"), adapter_id, validation["job_id"], validation.get("validator_version"), validation.get("executor_version"), status, _json(report), _json(validation.get("source_content_hashes", [])), _json(validation.get("page_content_hashes", [])), validation.get("validated_at") or _now_iso()),
        )


def mark_adapter_stale_with_source(con, adapter_id, stale_at, source):
    con.execute("begin")
    atomic = _AtomicConnection(con)
    try:
        adapter = atomic.execute("select * from catalyst_source_adapters where adapter_id = ?", (adapter_id,)).fetchone()
        if adapter is None:
            raise ValueError(f"adapter {adapter_id} was not found")
        if adapter["state"] != "active":
            raise ValueError(f"adapter {adapter_id} is not active")
        source = dict(source)
        source.update({"active_adapter_id": adapter_id, "adapter_version": adapter["version"], "acceptance_status": "accepted", "extraction_status": "discovery_required"})
        row = _source_row(atomic, source)
        existing = atomic.execute("select source_id from catalyst_ir_sources where source_id = ?", (row["source_id"],)).fetchone()
        if existing is None:
            saved = save_source(atomic, source)
        else:
            assignments = ",".join(f"{key} = ?" for key in row if key != "source_id")
            atomic.execute(f"update catalyst_ir_sources set {assignments} where source_id = ? and job_id = ?", tuple(value for key, value in row.items() if key != "source_id") + (row["source_id"], row["job_id"]))
            saved = _decode_row(atomic.execute("select * from catalyst_ir_sources where source_id = ?", (row["source_id"],)).fetchone(), ("evidence_result_ids_json", "attempts_json"))
            saved["evidence_result_ids"] = saved.pop("evidence_result_ids_json")
            saved["attempts"] = saved.pop("attempts_json") or []
        changed = atomic.execute("update catalyst_source_adapters set state = 'stale', stale_at = ? where adapter_id = ? and state = 'active'", (stale_at, adapter_id)).rowcount
        if changed != 1:
            raise ValueError(f"adapter {adapter_id} could not be marked stale")
    except Exception:
        con.rollback()
        raise
    con.commit()
    return saved


def load_active_adapter(con, ticker, source_type):
    row = con.execute("select * from catalyst_source_adapters where ticker = ? and source_type = ? and state = 'active'", (_ticker(ticker), source_type)).fetchone()
    result = _decode_row(row, ("allowed_hosts_json", "adapter_json"))
    if result is None:
        return None
    result["allowed_hosts"] = result.pop("allowed_hosts_json")
    result["adapter"] = result.pop("adapter_json")
    return result


def load_adapter_brief(con, adapter_id):
    if not adapter_id:
        return None
    row = con.execute(
        "select adapter_id, version, state, access_mode from catalyst_source_adapters where adapter_id = ?",
        (adapter_id,),
    ).fetchone()
    if row is None:
        return None
    return {"adapter_id": row["adapter_id"], "version": row["version"], "status": row["state"], "access_mode": row["access_mode"]}


def save_finalized_observations(con, job_id, events, classifications):
    job = _job(con, job_id)
    if job["status"] in _TERMINAL_JOB_STATES:
        raise ValueError(f"research job {job_id} is terminal")
    if not isinstance(events, list) or not isinstance(classifications, list):
        raise ValueError("events and classifications are required")
    explicit_event_ids = []
    generated_event_ids = []
    for event in events:
        if not isinstance(event, dict):
            raise ValueError("event is invalid")
        if "event_id" in event and event["event_id"] is not None:
            explicit_event_ids.append(_validated_event_id(event["event_id"]))
        else:
            generated_event_ids.append(_id("ire_"))
    duplicate_event_ids = {value for value, count in Counter(explicit_event_ids).items() if count > 1}
    if duplicate_event_ids:
        raise ValueError("duplicate event id")
    existing_ids = {
        row[0]
        for row in con.execute(
            "select event_id from catalyst_ir_events where event_id in ({})".format(",".join("?" for _ in explicit_event_ids)),
            explicit_event_ids,
        ).fetchall()
    } if explicit_event_ids else set()
    if existing_ids:
        raise ValueError("event id conflicts with existing event")
    event_input_ids = [
        event.get("id")
        for event in events
        if isinstance(event.get("id"), int) and not isinstance(event.get("id"), bool) and event.get("id") >= 1
    ]
    duplicate_input_ids = {value for value, count in Counter(event_input_ids).items() if count > 1}
    classification_rows = [_classification_key(item) for item in classifications]
    duplicate_classification_ids = {value for value, count in Counter(value for value in classification_rows if value is not None).items() if count > 1}
    classification_by_id = {
        key: item
        for key, item in zip(classification_rows, classifications)
        if key is not None and key not in duplicate_classification_ids
    }
    generated_index = 0
    with con:
        for position, event in enumerate(events, 1):
            explicit_event_id = event.get("event_id")
            if explicit_event_id is None:
                event_id = generated_event_ids[generated_index]
                generated_index += 1
            else:
                event_id = _validated_event_id(explicit_event_id)
            input_id = event.get("id") if "id" in event else None
            input_id_valid = isinstance(input_id, int) and not isinstance(input_id, bool) and input_id >= 1
            duplicate_input_id = input_id_valid and (input_id in duplicate_input_ids or input_id in duplicate_classification_ids)
            invalid_input_id = "id" in event and not input_id_valid
            classification = None if duplicate_input_id or invalid_input_id else (
                classification_by_id.get(event_id)
                or classification_by_id.get(input_id)
                or classification_by_id.get(position)
            )
            state = (classification or event).get("earnings_state", "ambiguous")
            if duplicate_input_id:
                state = "ambiguous"
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
            if event["source_type"] == "press_releases" and not canonical_url:
                raise ValueError("event url is required")
            if _ticker(event.get("ticker")) != job["ticker"]:
                raise ValueError("event ticker does not match job ticker")
            source_row = con.execute("select job_id, ticker, source_type from catalyst_ir_sources where source_id = ?", (event["source_id"],)).fetchone()
            if source_row is None or source_row["job_id"] != job_id:
                raise ValueError("event source does not belong to job")
            if source_row["ticker"] != _ticker(event.get("ticker")) or source_row["source_type"] != event.get("source_type"):
                raise ValueError("event source does not match event")
            normalized_title = event.get("normalized_title") or " ".join(title.lower().split())
            discovery_method, extraction_provider = _provenance_values(event)
            existing = con.execute(
                "select event_id from catalyst_ir_events where job_id = ? and ticker = ? and source_type = ? and count_date = ? and normalized_title = ? and (canonical_url = ? or (canonical_url is null and ? is null))",
                (job_id, _ticker(event.get("ticker")), event.get("source_type"), count_date, normalized_title, canonical_url, canonical_url),
            ).fetchone()
            if existing:
                event_id = existing["event_id"]
            cursor = con.execute(
                """insert into catalyst_ir_events(
                    event_id,job_id,source_id,ticker,published_date,event_date,count_date,title,normalized_title,canonical_url,
                    source_type,earnings_state,classification_method,adapter_id,adapter_version,executor_version,first_seen_at,content_hash,
                    endpoint_id,external_guid,discovery_method,extraction_provider
                ) select ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,? where exists (
                    select 1 from catalyst_research_jobs where job_id = ? and status not in ('completed','completed_partial','unsupported','failed')
                )
                on conflict(job_id,ticker,source_type,count_date,normalized_title,canonical_url) do update set earnings_state=excluded.earnings_state""",
                (event_id, job_id, event["source_id"], _ticker(event.get("ticker")), event.get("published_date"), event.get("event_date"),
                 count_date, title, normalized_title, canonical_url,
                 event["source_type"], state, (classification or event).get("classification_method"), event.get("adapter_id"), event.get("adapter_version"),
                 event.get("executor_version"), event.get("first_seen_at") or _now_iso(), event.get("content_hash"),
                 event.get("endpoint_id"), event.get("external_guid"), discovery_method, extraction_provider, job_id),
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


class _AtomicConnection:
    def __init__(self, connection):
        self._connection = connection

    def __getattr__(self, name):
        return getattr(self._connection, name)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False


def finalize_job_with_observations(con, job_id, events, classifications, result):
    con.execute("begin")
    atomic = _AtomicConnection(con)
    try:
        save_finalized_observations(atomic, job_id, events, classifications)
        finalize_job(atomic, job_id, result)
    except Exception:
        con.rollback()
        raise
    con.commit()


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


def list_event_normalized_titles(con, ticker):
    normalized = _ticker(ticker)
    return [
        row[0]
        for row in con.execute("select normalized_title from catalyst_ir_events where ticker = ?", (normalized,))
    ]


def load_job_result_schema_version(con, job_id):
    job = _job(con, job_id)
    return RESULT_SCHEMA_VERSION if job["research_version"] == RESEARCH_VERSION else LEGACY_RESULT_SCHEMA_VERSION


def load_job_result(con, job_id):
    job = _job(con, job_id)
    sources = [_decode_row(row, ("evidence_result_ids_json", "attempts_json")) for row in con.execute("select * from catalyst_ir_sources where job_id = ? order by source_type, source_id", (job_id,))]
    for source in sources:
        source["evidence_result_ids"] = source.pop("evidence_result_ids_json")
        source["attempts"] = source.pop("attempts_json") or []
        if source.get("coverage_continuous") is not None:
            source["coverage_continuous"] = bool(source["coverage_continuous"])
    schema_version = load_job_result_schema_version(con, job_id)
    result = {
        "schema_version": schema_version, "research_version": job["research_version"], "mode": job["mode"], "job_id": job_id,
        "status": job["status"], "ticker": job["ticker"], "company_name": job["company_name"], "cik": job["cik"], "as_of": job["as_of"],
        "requested_window": {"start": job["requested_start"], "end": job["requested_end"], "years": job["requested_years"]},
        "sources": sources, "statistics": _decode(job["statistics_json"]) or {}, "warnings": _decode(job["warnings_json"]) or [],
        "next_actions": _decode(job["next_actions_json"]) or [], "error_summary": job["error_summary"],
        "completed_at": job["completed_at"], "observation_count": con.execute("select count(*) from catalyst_ir_events where job_id = ?", (job_id,)).fetchone()[0],
        "execution_paths": _decode(job["execution_paths_json"]) or {}, "call_counts": _decode(job["call_counts_json"]) or {},
    }
    return result


def load_latest_result(con, ticker):
    normalized = _ticker(ticker)
    row = con.execute(
        """select job_id from catalyst_research_jobs where ticker = ? and status in ('completed','completed_partial')
           and mode != 'rediscover'
           and (mode = 'research' or research_version != ? or exists(
               select 1 from catalyst_ir_events where job_id = catalyst_research_jobs.job_id))
           order by case status when 'completed' then 0 else 1 end, completed_at desc, created_at desc, rowid desc limit 1""",
        (normalized, RESEARCH_VERSION),
    ).fetchone()
    if not row:
        return None
    result = load_job_result(con, row["job_id"])
    latest = con.execute(
        "select job_id, status, completed_at from catalyst_research_jobs where ticker = ? order by created_at desc, rowid desc limit 1",
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
        where.append("(count_date < ? or (count_date = ? and event_id < ?))")
        params.extend([payload["count_date"], payload["count_date"], payload["event_id"]])
    rows = con.execute(
        f"select * from catalyst_ir_events where {' and '.join(where)} order by count_date desc, event_id desc limit ?",
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


def load_ticker_activity_page(con, ticker, limit, cursor):
    normalized = _ticker(ticker)
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 200:
        raise ValueError("activity limit must be between 1 and 200")
    payload = _decode_cursor(cursor) if cursor else None
    if payload and (payload["ticker"] != normalized or payload.get("job_id") is not None):
        raise ValueError("activity cursor does not belong to ticker")
    where = ["ticker = ?"]
    params = [normalized]
    if payload:
        where.append("(count_date < ? or (count_date = ? and event_id < ?))")
        params.extend([payload["count_date"], payload["count_date"], payload["event_id"]])
    rows = con.execute(
        f"""select * from catalyst_ir_events where rowid in (
                select max(rowid) from catalyst_ir_events where ticker = ?
                group by source_type, count_date, normalized_title, canonical_url)
            and {' and '.join(where)} order by count_date desc, event_id desc limit ?""",
        (normalized, *params, limit + 1),
    ).fetchall()
    has_more = len(rows) > limit
    rows = rows[:limit]
    events = [dict(row) for row in rows]
    next_cursor = None
    if has_more and rows:
        last = rows[-1]
        next_cursor = _encode_cursor({"ticker": normalized, "count_date": last["count_date"], "event_id": last["event_id"]})
    return {"ticker": normalized, "events": events, "next_cursor": next_cursor}


def save_company_registry(con, registry):
    ticker = _ticker(registry.get("ticker"))
    company_name = str(registry.get("company_name") or "").strip()
    if not company_name:
        raise ValueError("registry company name is required")
    domains = registry.get("official_domains")
    if not isinstance(domains, list) or not domains or not all(isinstance(item, str) and item.strip() for item in domains):
        raise ValueError("registry official domains are required")
    confidence = registry.get("source_confidence")
    if confidence not in _REGISTRY_CONFIDENCE:
        raise ValueError("registry source confidence is invalid")
    version = registry.get("registry_version")
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        raise ValueError("registry version is invalid")
    row = {
        "ticker": ticker,
        "company_name": company_name,
        "cik": str(registry.get("cik")) if registry.get("cik") is not None else None,
        "official_domains_json": _json(sorted({item.strip().lower() for item in domains})),
        "source_confidence": confidence,
        "registry_version": version,
        "discovered_at": registry.get("discovered_at") or _now_iso(),
        "last_validated_at": registry.get("last_validated_at"),
        "updated_at": registry.get("updated_at") or _now_iso(),
    }
    comparable = ("company_name", "cik", "official_domains_json", "source_confidence", "registry_version", "discovered_at", "last_validated_at")
    with con:
        existing = con.execute("select * from catalyst_company_registry where ticker = ?", (ticker,)).fetchone()
        if existing is None:
            if version != 1:
                raise ValueError("initial registry version must be 1")
            con.execute(
                """insert into catalyst_company_registry(
                    ticker,company_name,cik,official_domains_json,source_confidence,registry_version,discovered_at,last_validated_at,updated_at
                ) values (:ticker,:company_name,:cik,:official_domains_json,:source_confidence,:registry_version,:discovered_at,:last_validated_at,:updated_at)""",
                row,
            )
        else:
            if all(existing[key] == row[key] for key in comparable):
                return _registry_row(existing)
            if version != existing["registry_version"] + 1:
                raise ValueError(f"registry version must be {existing['registry_version'] + 1}")
            con.execute(
                """update catalyst_company_registry set company_name=:company_name, cik=:cik, official_domains_json=:official_domains_json,
                    source_confidence=:source_confidence, registry_version=:registry_version, discovered_at=:discovered_at,
                    last_validated_at=:last_validated_at, updated_at=:updated_at where ticker=:ticker""",
                row,
            )
    return load_company_registry(con, ticker)


def _registry_row(row):
    result = _decode_row(row, ("official_domains_json",))
    result["official_domains"] = result.pop("official_domains_json")
    return result


def load_company_registry(con, ticker):
    row = con.execute("select * from catalyst_company_registry where ticker = ?", (_ticker(ticker),)).fetchone()
    if row is None:
        return None
    return _registry_row(row)


def _endpoint_row(endpoint):
    ticker = _ticker(endpoint.get("ticker"))
    channel = endpoint.get("channel")
    if channel not in _ENDPOINT_CHANNELS:
        raise ValueError("endpoint channel is invalid")
    endpoint_type = endpoint.get("endpoint_type")
    if endpoint_type not in _ENDPOINT_TYPES:
        raise ValueError("endpoint type is invalid")
    domain = str(endpoint.get("domain") or "").strip().lower()
    if not domain:
        raise ValueError("endpoint domain is required")
    url = endpoint.get("url")
    if url is not None:
        url = str(url).strip()
        if not url:
            raise ValueError("endpoint url is invalid")
    status = endpoint.get("status") or "unverified"
    if status not in _ENDPOINT_STATES:
        raise ValueError("endpoint status is invalid")
    confidence = endpoint.get("confidence")
    if confidence not in _REGISTRY_CONFIDENCE:
        raise ValueError("endpoint confidence is invalid")
    failures = endpoint.get("consecutive_failures", 0)
    if not isinstance(failures, int) or isinstance(failures, bool) or failures < 0:
        raise ValueError("endpoint consecutive failures is invalid")
    return {
        "endpoint_id": endpoint.get("endpoint_id") or _id("cse_"),
        "ticker": ticker,
        "channel": channel,
        "endpoint_type": endpoint_type,
        "url": url,
        "domain": domain,
        "status": status,
        "confidence": confidence,
        "discovered_at": endpoint.get("discovered_at") or _now_iso(),
        "last_checked_at": endpoint.get("last_checked_at"),
        "last_success_at": endpoint.get("last_success_at"),
        "last_item_at": endpoint.get("last_item_at"),
        "last_guid": endpoint.get("last_guid"),
        "consecutive_failures": failures,
        "last_error_code": endpoint.get("last_error_code"),
        "updated_at": endpoint.get("updated_at") or _now_iso(),
    }


def upsert_source_endpoint(con, endpoint):
    row = _endpoint_row(endpoint)
    with con:
        con.execute(
            """insert into catalyst_source_endpoints(
                endpoint_id,ticker,channel,endpoint_type,url,domain,status,confidence,discovered_at,last_checked_at,
                last_success_at,last_item_at,last_guid,consecutive_failures,last_error_code,updated_at
            ) values (:endpoint_id,:ticker,:channel,:endpoint_type,:url,:domain,:status,:confidence,:discovered_at,:last_checked_at,
                :last_success_at,:last_item_at,:last_guid,:consecutive_failures,:last_error_code,:updated_at)
            on conflict(ticker, channel, endpoint_type, coalesce(lower(url), lower(domain))) do update set
                url=excluded.url, domain=excluded.domain, status=excluded.status, confidence=excluded.confidence,
                last_checked_at=coalesce(excluded.last_checked_at, catalyst_source_endpoints.last_checked_at),
                last_success_at=coalesce(excluded.last_success_at, catalyst_source_endpoints.last_success_at),
                last_item_at=coalesce(excluded.last_item_at, catalyst_source_endpoints.last_item_at),
                last_guid=coalesce(excluded.last_guid, catalyst_source_endpoints.last_guid),
                consecutive_failures=excluded.consecutive_failures,
                last_error_code=coalesce(excluded.last_error_code, catalyst_source_endpoints.last_error_code),
                updated_at=excluded.updated_at""",
            row,
        )
    return dict(
        con.execute(
            """select * from catalyst_source_endpoints
                where ticker = ? and channel = ? and endpoint_type = ? and coalesce(lower(url), lower(domain)) = coalesce(lower(?), lower(?))""",
            (row["ticker"], row["channel"], row["endpoint_type"], row["url"], row["domain"]),
        ).fetchone()
    )


def load_source_endpoints(con, ticker, channel=None, statuses=None):
    normalized = _ticker(ticker)
    where = ["ticker = ?"]
    params = [normalized]
    if channel is not None:
        if channel not in _ENDPOINT_CHANNELS:
            raise ValueError("endpoint channel is invalid")
        where.append("channel = ?")
        params.append(channel)
    if statuses is not None:
        if not isinstance(statuses, (set, frozenset)) or not statuses or not statuses <= _ENDPOINT_STATES:
            raise ValueError("endpoint statuses are invalid")
        where.append("status in ({})".format(",".join("?" for _ in statuses)))
        params.extend(sorted(statuses))
    rows = con.execute(
        f"select * from catalyst_source_endpoints where {' and '.join(where)} order by channel, endpoint_type, domain, url",
        params,
    ).fetchall()
    return [dict(row) for row in rows]


def record_endpoint_check(con, check):
    endpoint_id = check.get("endpoint_id")
    if con.execute("select 1 from catalyst_source_endpoints where endpoint_id = ?", (endpoint_id,)).fetchone() is None:
        raise ValueError(f"endpoint {endpoint_id} was not found")
    outcome = str(check.get("outcome") or "").strip()
    if not outcome:
        raise ValueError("endpoint check outcome is required")
    counts = {}
    for key in ("item_count", "new_item_count"):
        value = check.get(key, 0)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError(f"endpoint check {key.replace('_', ' ')} is invalid")
        counts[key] = value
    http_status = check.get("http_status")
    if http_status is not None and (not isinstance(http_status, int) or isinstance(http_status, bool)):
        raise ValueError("endpoint check http status is invalid")
    job_id = check.get("job_id")
    if job_id is not None:
        _job(con, job_id)
    row = {
        "check_id": check.get("check_id") or _id("cec_"),
        "endpoint_id": endpoint_id,
        "job_id": job_id,
        "checked_at": check.get("checked_at") or _now_iso(),
        "outcome": outcome,
        "http_status": http_status,
        "item_count": counts["item_count"],
        "new_item_count": counts["new_item_count"],
        "newest_item_at": check.get("newest_item_at"),
        "error_code": check.get("error_code"),
        "content_hash": check.get("content_hash"),
    }
    with con:
        con.execute(
            """insert into catalyst_endpoint_checks(
                check_id,endpoint_id,job_id,checked_at,outcome,http_status,item_count,new_item_count,newest_item_at,error_code,content_hash
            ) values (:check_id,:endpoint_id,:job_id,:checked_at,:outcome,:http_status,:item_count,:new_item_count,:newest_item_at,:error_code,:content_hash)""",
            row,
        )
    return dict(row)


def update_endpoint_health(con, endpoint_id, state):
    if not isinstance(state, dict):
        raise ValueError("endpoint health state is required")
    if con.execute("select 1 from catalyst_source_endpoints where endpoint_id = ?", (endpoint_id,)).fetchone() is None:
        raise ValueError(f"endpoint {endpoint_id} was not found")
    invalid = set(state) - _ENDPOINT_HEALTH_COLUMNS - {"updated_at"}
    if invalid:
        raise ValueError(f"endpoint health field {sorted(invalid)[0]} is not updatable")
    updates = {}
    if "status" in state:
        if state["status"] not in _ENDPOINT_STATES:
            raise ValueError("endpoint status is invalid")
        updates["status"] = state["status"]
    for key in ("last_checked_at", "last_success_at", "last_item_at", "last_guid", "last_error_code"):
        if key in state:
            updates[key] = state[key]
    if "consecutive_failures" in state:
        failures = state["consecutive_failures"]
        if not isinstance(failures, int) or isinstance(failures, bool) or failures < 0:
            raise ValueError("endpoint consecutive failures is invalid")
        updates["consecutive_failures"] = failures
    updates["updated_at"] = state.get("updated_at") or _now_iso()
    assignments = ",".join(f"{key} = ?" for key in updates)
    with con:
        con.execute(f"update catalyst_source_endpoints set {assignments} where endpoint_id = ?", (*updates.values(), endpoint_id))
    return dict(con.execute("select * from catalyst_source_endpoints where endpoint_id = ?", (endpoint_id,)).fetchone())


def event_url_seen(con, ticker, canonical_url):
    normalized = _ticker(ticker)
    url = str(canonical_url or "").strip()
    if not url:
        raise ValueError("canonical url is required")
    row = con.execute(
        """select 1 from catalyst_ir_events e
            join catalyst_research_jobs j on j.job_id = e.job_id
            where e.ticker = ? and e.canonical_url = ? and j.status in ('completed','completed_partial')
            limit 1""",
        (normalized, url),
    ).fetchone()
    return row is not None


def source_url_seen(con, ticker, canonical_url):
    normalized = _ticker(ticker)
    url = str(canonical_url or "").strip()
    if not url:
        raise ValueError("canonical url is required")
    row = con.execute(
        "select 1 from catalyst_ir_sources where ticker = ? and url = ? limit 1",
        (normalized, url),
    ).fetchone()
    return row is not None


def load_latest_gap_search_at(con, ticker, channel):
    normalized = _ticker(ticker)
    if channel not in _ENDPOINT_CHANNELS:
        raise ValueError("endpoint channel is invalid")
    row = con.execute(
        """select a.completed_at from catalyst_search_attempts a
            join catalyst_research_jobs j on j.job_id = a.job_id
            where j.ticker = ? and a.search_purpose = 'incremental_gap_check' and a.completed_at is not null
            order by a.completed_at desc limit 1""",
        (normalized,),
    ).fetchone()
    return row[0] if row else None

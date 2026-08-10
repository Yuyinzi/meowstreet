import json
import sqlite3
from pathlib import Path

from app.tools.market_assistant_artifacts import validate_artifact
from app.tools.market_setup_explanation_snapshot import canonical_json
from app.tools.market_setup_explanation_snapshot import finalize_snapshot
from app.tools.market_setup_explanation_snapshot import validate_snapshot

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = ROOT / "data" / "local_system" / "market_data.sqlite"

_SNAPSHOT_COLUMNS = """
    context_id, created_at, as_of, evidence_through,
    market_setup_version, snapshot_schema_version,
    decision_fingerprint, explanation_fingerprint,
    snapshot_hash, snapshot_json
"""

_SNAPSHOT_DUPLICATE_COLUMNS = (
    "context_id",
    "created_at",
    "as_of",
    "evidence_through",
    "market_setup_version",
    "snapshot_schema_version",
    "decision_fingerprint",
    "explanation_fingerprint",
    "snapshot_hash",
)

_ARTIFACT_TABLE_BY_KIND = {
    "knowledge_record": "knowledge_records",
    "exploration_result": "exploration_results",
    "research_result": "research_results",
}

_ARTIFACT_TABLE_COLUMNS = (
    "artifact_id, artifact_kind, schema_version, primary_authority, "
    "market_setup_relation, integrity_hash, artifact_json"
)

_ARTIFACT_TABLE_PLACEHOLDERS = "?, ?, ?, ?, ?, ?, ?"

_SCHEMA_DDL = """
pragma journal_mode = wal;
pragma busy_timeout = 10000;
create table if not exists explanation_snapshots (
    context_id text not null,
    created_at text not null,
    as_of text not null,
    evidence_through text,
    market_setup_version text not null,
    snapshot_schema_version text not null,
    decision_fingerprint text not null,
    explanation_fingerprint text not null,
    snapshot_hash text not null,
    snapshot_json text not null
);
create unique index if not exists uq_explanation_snapshots_fingerprint
on explanation_snapshots(explanation_fingerprint);
create index if not exists idx_explanation_snapshots_context
on explanation_snapshots(context_id);
create table if not exists knowledge_records (
    artifact_id text primary key,
    artifact_kind text not null,
    schema_version text not null,
    primary_authority text not null,
    market_setup_relation text not null,
    integrity_hash text not null,
    artifact_json text not null
);
create table if not exists exploration_results (
    artifact_id text primary key,
    artifact_kind text not null,
    schema_version text not null,
    primary_authority text not null,
    market_setup_relation text not null,
    integrity_hash text not null,
    artifact_json text not null
);
create table if not exists research_results (
    artifact_id text primary key,
    artifact_kind text not null,
    schema_version text not null,
    primary_authority text not null,
    market_setup_relation text not null,
    integrity_hash text not null,
    artifact_json text not null
);
create table if not exists answer_traces (
    answer_trace_id text primary key,
    message_id text not null,
    trace_json text not null
);
create index if not exists idx_answer_traces_message
on answer_traces(message_id);
"""


def connect(db_path=DEFAULT_DB_PATH):
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.executescript(_SCHEMA_DDL)
    return con


def _verify_duplicated_columns(row, snapshot):
    for column in _SNAPSHOT_DUPLICATE_COLUMNS:
        if row[column] != snapshot[column]:
            raise ValueError("snapshot duplicated column is invalid")


def _verify_snapshot_references(snapshot):
    result_ids = set(snapshot["results"])
    for step in snapshot["decision_path"]:
        if step["object_id"] not in result_ids:
            raise ValueError("decision path reference is invalid")
    fact_ids = {fact["fact_id"] for fact in snapshot["evidence"]}
    methods = snapshot["method_contracts"]["methods"]
    for counterfactual in snapshot["counterfactuals"]:
        if counterfactual["object_type"] == "confirmation_test":
            if counterfactual["object_id"] not in fact_ids:
                raise ValueError("counterfactual reference is invalid")
            predicate_ref = counterfactual["predicate_ref"]
            if predicate_ref["method_id"] not in methods:
                raise ValueError("counterfactual predicate reference is invalid")


def _load_validated_snapshot(con, where_sql, params):
    row = con.execute(
        f"select {_SNAPSHOT_COLUMNS} from explanation_snapshots {where_sql}",
        params,
    ).fetchone()
    if row is None:
        return None
    try:
        payload = json.loads(row["snapshot_json"])
        snapshot = validate_snapshot(payload)
        _verify_duplicated_columns(row, snapshot)
        _verify_snapshot_references(snapshot)
    except (ValueError, TypeError) as exc:
        raise ValueError("explanation snapshot integrity check failed") from exc
    return snapshot


def get_or_create_snapshot(con, snapshot_state, *, context_id, created_at):
    finalized = finalize_snapshot(
        snapshot_state, context_id=context_id, created_at=created_at
    )
    snapshot_json = canonical_json(finalized).decode("utf-8")
    persisted = validate_snapshot(json.loads(snapshot_json))
    try:
        con.execute(
            """
            insert into explanation_snapshots(
                context_id, created_at, as_of, evidence_through,
                market_setup_version, snapshot_schema_version,
                decision_fingerprint, explanation_fingerprint,
                snapshot_hash, snapshot_json
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            on conflict(explanation_fingerprint) do nothing
            """,
            (
                persisted["context_id"],
                persisted["created_at"],
                persisted["as_of"],
                persisted["evidence_through"],
                persisted["market_setup_version"],
                persisted["snapshot_schema_version"],
                persisted["decision_fingerprint"],
                persisted["explanation_fingerprint"],
                persisted["snapshot_hash"],
                snapshot_json,
            ),
        )
        snapshot = _load_validated_snapshot(
            con,
            "where explanation_fingerprint = ?",
            (persisted["explanation_fingerprint"],),
        )
        con.commit()
    except Exception:
        con.rollback()
        raise
    if snapshot is None:
        raise ValueError("explanation snapshot was not persisted")
    return snapshot


def load_snapshot(con, context_id):
    normalized_context = str(context_id or "").strip()
    if not normalized_context:
        raise ValueError("explanation context id is required")
    return _load_validated_snapshot(con, "where context_id = ?", (normalized_context,))


def load_latest_snapshot(con):
    return _load_validated_snapshot(
        con, "order by created_at desc, rowid desc limit 1", ()
    )


def _validate_answer_trace_shape(answer_trace):
    if not isinstance(answer_trace, dict):
        raise ValueError("answer trace is required")
    if not str(answer_trace.get("answer_trace_id") or "").strip():
        raise ValueError("answer trace id is required")
    if not str(answer_trace.get("message_id") or "").strip():
        raise ValueError("answer trace message id is required")


def _insert_artifact(con, artifact):
    validate_artifact(artifact)
    table = _ARTIFACT_TABLE_BY_KIND.get(artifact["artifact_kind"])
    if table is None:
        raise ValueError(
            f"artifact kind is not persistable: {artifact['artifact_kind']}"
        )
    canonical_text = canonical_json(artifact).decode("utf-8")
    con.execute(
        f"""insert into {table}({_ARTIFACT_TABLE_COLUMNS})
            values ({_ARTIFACT_TABLE_PLACEHOLDERS})""",
        (
            artifact["artifact_id"],
            artifact["artifact_kind"],
            artifact["schema_version"],
            artifact["primary_authority"],
            artifact["market_setup_relation"],
            artifact["integrity_hash"],
            canonical_text,
        ),
    )


def save_answer_bundle(con, *, artifacts, answer_trace):
    _validate_answer_trace_shape(answer_trace)
    canonical_trace = canonical_json(answer_trace).decode("utf-8")
    con.execute("begin")
    try:
        con.execute(
            """
            insert into answer_traces(answer_trace_id, message_id, trace_json)
            values (?, ?, ?)
            """,
            (
                answer_trace["answer_trace_id"],
                answer_trace["message_id"],
                canonical_trace,
            ),
        )
        for artifact in artifacts:
            _insert_artifact(con, artifact)
        con.commit()
    except Exception:
        con.rollback()
        raise


def load_answer_trace(con, answer_trace_id):
    normalized_id = str(answer_trace_id or "").strip()
    if not normalized_id:
        raise ValueError("answer trace id is required")
    row = con.execute(
        """
        select answer_trace_id, message_id, trace_json
        from answer_traces
        where answer_trace_id = ?
        """,
        (normalized_id,),
    ).fetchone()
    if row is None:
        return None
    try:
        payload = json.loads(row["trace_json"])
        if not isinstance(payload, dict):
            raise ValueError("answer trace json is invalid")
        if payload.get("answer_trace_id") != row["answer_trace_id"]:
            raise ValueError("answer trace id does not match")
        if payload.get("message_id") != row["message_id"]:
            raise ValueError("answer trace message id does not match")
    except (ValueError, TypeError) as exc:
        raise ValueError("answer trace is invalid") from exc
    return payload

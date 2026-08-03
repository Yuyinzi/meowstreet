import json
import math
import sqlite3
from datetime import datetime
from datetime import timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = ROOT / "data" / "local_system" / "market_data.sqlite"

_CLAIMS_SERIES_IDS = frozenset({"initial_claims_sa", "continuing_claims_sa"})
_REQUIRED_FIELDS = [
    "series_id",
    "reference_period",
    "vintage_id",
    "as_of_timestamp",
    "value_at_release",
    "seasonal_adjustment",
    "source_url",
    "source_hash",
]

_EC_DDL = """
create table if not exists economic_confirmation_vintages (
    series_id text not null,
    reference_period text not null,
    vintage_id text not null,
    release_date text,
    as_of_timestamp text not null,
    value_at_release real not null,
    latest_revised_value real,
    revision_number integer not null default 0,
    seasonal_adjustment text not null,
    source_url text not null,
    source_hash text not null,
    primary key(series_id, reference_period, vintage_id)
);
create index if not exists idx_ec_vintages_series_period
on economic_confirmation_vintages(series_id, reference_period);
create table if not exists economic_confirmation_current_observations (
    series_id text not null,
    reference_period text not null,
    vintage_id text not null,
    value real not null,
    value_at_release real not null,
    latest_revised_value real,
    revision_number integer not null,
    seasonal_adjustment text not null,
    release_date text,
    as_of_timestamp text not null,
    source_url text not null,
    source_hash text not null,
    primary key(series_id, reference_period)
);
create table if not exists economic_confirmation_source_contracts (
    series_id text primary key,
    contract_json text not null
);
create table if not exists economic_confirmation_scheduled_events (
    event_id text primary key,
    scheduled_at text not null,
    status text not null,
    timezone text,
    source_url text,
    retrieved_at text
);
"""

_VINTAGE_COLUMNS = (
    "series_id, reference_period, vintage_id, release_date, as_of_timestamp, "
    "value_at_release, latest_revised_value, revision_number, seasonal_adjustment, "
    "source_url, source_hash"
)
_CURRENT_COLUMNS = (
    "series_id, reference_period, vintage_id, value, value_at_release, "
    "latest_revised_value, revision_number, seasonal_adjustment, release_date, "
    "as_of_timestamp, source_url, source_hash"
)


def connect(db_path=DEFAULT_DB_PATH):
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.executescript(_EC_DDL)
    return con


def record_vintage_batch(con, observations):
    try:
        inserted = _record_vintage_batch(con, observations)
        con.commit()
        return inserted
    except Exception:
        con.rollback()
        raise


def replace_national_claims_history_batch(con, observations):
    try:
        inserted = _record_vintage_batch(con, observations)
        _delete_legacy_monthly_continuing_claims(con)
        con.commit()
        return inserted
    except Exception:
        con.rollback()
        raise


def _record_vintage_batch(con, observations):
    inserted = 0
    seen = {}
    for observation in observations:
        normalized = _normalize_observation(observation)
        key = (
            normalized["series_id"],
            normalized["reference_period"],
            normalized["vintage_id"],
        )
        prior = seen.get(key)
        if prior is not None:
            if prior["source_hash"] != normalized["source_hash"]:
                raise ValueError(
                    f"conflicting duplicate vintage for {key[0]} {key[1]} {key[2]}"
                )
            continue
        seen[key] = normalized
        existing = con.execute(
            "select source_hash from economic_confirmation_vintages "
            "where series_id = ? and reference_period = ? and vintage_id = ?",
            (
                normalized["series_id"],
                normalized["reference_period"],
                normalized["vintage_id"],
            ),
        ).fetchone()
        if existing is not None:
            if existing["source_hash"] != normalized["source_hash"]:
                raise ValueError(
                    f"conflicting duplicate vintage for {key[0]} {key[1]} {key[2]}"
                )
            continue
        _insert_vintage(con, normalized)
        _upsert_current(con, normalized)
        inserted += 1
    return inserted


def _delete_legacy_monthly_continuing_claims(con):
    con.execute(
        "delete from economic_confirmation_vintages "
        "where series_id = 'continuing_claims_sa' "
        "and reference_period glob '????-??'"
    )
    con.execute(
        "delete from economic_confirmation_current_observations "
        "where series_id = 'continuing_claims_sa' "
        "and reference_period glob '????-??'"
    )


def load_current_series(con, ids):
    result = {}
    for series_id in _series_ids(ids):
        rows = con.execute(
            f"""select {_CURRENT_COLUMNS}
                from economic_confirmation_current_observations
                where series_id = ?
                order by reference_period""",
            (series_id,),
        ).fetchall()
        result[series_id] = [dict(row) for row in rows]
    return result


def load_series_as_of(con, ids, timestamp):
    as_of = _normalize_timestamp(timestamp)
    result = {}
    for series_id in _series_ids(ids):
        rows = con.execute(
            f"""select {_VINTAGE_COLUMNS}
                from economic_confirmation_vintages
                where series_id = ? and as_of_timestamp <= ?
                order by reference_period, as_of_timestamp""",
            (series_id, as_of),
        ).fetchall()
        by_period = {}
        for row in rows:
            by_period[row["reference_period"]] = row
        result[series_id] = [
            _vintage_record(by_period[period]) for period in sorted(by_period)
        ]
    return result


def record_scheduled_events(con, events):
    try:
        for event in events:
            if not isinstance(event, dict):
                raise ValueError("scheduled event is required to be a dict")
            event_id = str(event.get("event_id") or "").strip()
            scheduled_at = str(event.get("scheduled_at") or "").strip()
            status = str(event.get("status") or "").strip()
            if not event_id:
                raise ValueError("scheduled event is missing event_id")
            if not scheduled_at:
                raise ValueError("scheduled event is missing scheduled_at")
            if not status:
                raise ValueError("scheduled event is missing status")
            con.execute(
                """insert into economic_confirmation_scheduled_events(
                    event_id, scheduled_at, status, timezone, source_url, retrieved_at
                ) values (?, ?, ?, ?, ?, ?)
                on conflict(event_id) do update set
                    scheduled_at = excluded.scheduled_at,
                    status = excluded.status,
                    timezone = excluded.timezone,
                    source_url = excluded.source_url,
                    retrieved_at = excluded.retrieved_at""",
                (
                    event_id,
                    scheduled_at,
                    status,
                    event.get("timezone"),
                    event.get("source_url"),
                    event.get("retrieved_at"),
                ),
            )
        con.commit()
        return len(events)
    except Exception:
        con.rollback()
        raise


def load_scheduled_events(con):
    rows = con.execute(
        """select event_id, scheduled_at, status, timezone, source_url, retrieved_at
           from economic_confirmation_scheduled_events
           order by scheduled_at"""
    ).fetchall()
    return [dict(row) for row in rows]


def record_source_contract(con, series_id, contract):
    if not isinstance(contract, dict) or not contract:
        raise ValueError("source contract is required to be a non-empty dict")
    normalized = str(series_id or "").strip().lower()
    if not normalized:
        raise ValueError("series id is required")
    con.execute(
        """insert into economic_confirmation_source_contracts(series_id, contract_json)
           values (?, ?)
           on conflict(series_id) do update set contract_json = excluded.contract_json""",
        (normalized, json.dumps(contract, sort_keys=True)),
    )
    con.commit()


def load_source_contracts(con, ids):
    normalized_ids = _series_ids(ids)
    if not normalized_ids:
        return {}
    placeholders = ", ".join("?" for _ in normalized_ids)
    rows = con.execute(
        f"""select series_id, contract_json
            from economic_confirmation_source_contracts
            where series_id in ({placeholders})""",
        normalized_ids,
    ).fetchall()
    return {row["series_id"]: json.loads(row["contract_json"]) for row in rows}


def _normalize_observation(observation):
    if not isinstance(observation, dict):
        raise ValueError("vintage observation is required to be a dict")
    for field in _REQUIRED_FIELDS:
        if observation.get(field) in (None, ""):
            raise ValueError(f"vintage observation is missing required field: {field}")
    series_id = str(observation["series_id"]).strip().lower()
    if not series_id:
        raise ValueError("vintage observation is missing required field: series_id")
    if (
        series_id in _CLAIMS_SERIES_IDS
        and observation["seasonal_adjustment"] != "seasonally_adjusted"
    ):
        raise ValueError(f"claims series {series_id} must be seasonally adjusted")
    value_at_release = _parse_finite(
        observation["value_at_release"], f"{series_id} value_at_release"
    )
    revised_raw = observation.get("latest_revised_value")
    latest_revised_value = (
        None
        if revised_raw in (None, "")
        else _parse_finite(revised_raw, f"{series_id} latest_revised_value")
    )
    return {
        "series_id": series_id,
        "reference_period": str(observation["reference_period"]).strip(),
        "vintage_id": str(observation["vintage_id"]).strip(),
        "release_date": _optional_text(observation.get("release_date")),
        "as_of_timestamp": _normalize_timestamp(observation["as_of_timestamp"]),
        "value_at_release": value_at_release,
        "latest_revised_value": latest_revised_value,
        "revision_number": _parse_revision_number(
            observation.get("revision_number"), series_id
        ),
        "seasonal_adjustment": str(observation["seasonal_adjustment"]).strip(),
        "source_url": str(observation["source_url"]).strip(),
        "source_hash": str(observation["source_hash"]).strip(),
    }


def _parse_finite(value, label):
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"vintage observation has invalid value for {label}") from exc
    if not math.isfinite(parsed):
        raise ValueError(f"vintage observation has invalid value for {label}")
    return parsed


def _parse_revision_number(value, series_id):
    if value in (None, ""):
        return 0
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"vintage observation has invalid revision_number for {series_id}"
        ) from exc
    if parsed < 0:
        raise ValueError(
            f"vintage observation has invalid revision_number for {series_id}"
        )
    return parsed


def _normalize_timestamp(value):
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"invalid as_of_timestamp: {value!r}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat(timespec="seconds")


def _optional_text(value):
    if value in (None, ""):
        return None
    return str(value).strip()


def _insert_vintage(con, obs):
    con.execute(
        f"""insert into economic_confirmation_vintages({_VINTAGE_COLUMNS})
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            obs["series_id"],
            obs["reference_period"],
            obs["vintage_id"],
            obs["release_date"],
            obs["as_of_timestamp"],
            obs["value_at_release"],
            obs["latest_revised_value"],
            obs["revision_number"],
            obs["seasonal_adjustment"],
            obs["source_url"],
            obs["source_hash"],
        ),
    )


def _upsert_current(con, obs):
    con.execute(
        """insert into economic_confirmation_current_observations(
            series_id, reference_period, vintage_id, value, value_at_release,
            latest_revised_value, revision_number, seasonal_adjustment,
            release_date, as_of_timestamp, source_url, source_hash
        ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        on conflict(series_id, reference_period) do update set
            vintage_id = excluded.vintage_id,
            value = excluded.value,
            value_at_release = excluded.value_at_release,
            latest_revised_value = excluded.latest_revised_value,
            revision_number = excluded.revision_number,
            seasonal_adjustment = excluded.seasonal_adjustment,
            release_date = excluded.release_date,
            as_of_timestamp = excluded.as_of_timestamp,
            source_url = excluded.source_url,
            source_hash = excluded.source_hash
            where excluded.as_of_timestamp
                >= economic_confirmation_current_observations.as_of_timestamp""",
        (
            obs["series_id"],
            obs["reference_period"],
            obs["vintage_id"],
            obs["latest_revised_value"]
            if obs["latest_revised_value"] is not None
            else obs["value_at_release"],
            obs["value_at_release"],
            obs["latest_revised_value"],
            obs["revision_number"],
            obs["seasonal_adjustment"],
            obs["release_date"],
            obs["as_of_timestamp"],
            obs["source_url"],
            obs["source_hash"],
        ),
    )


def _vintage_record(row):
    record = dict(row)
    record["value"] = (
        row["latest_revised_value"]
        if row["latest_revised_value"] is not None
        else row["value_at_release"]
    )
    return record


def _series_ids(ids):
    normalized = []
    for series_id in ids:
        value = str(series_id or "").strip().lower()
        if not value:
            raise ValueError("series id is required")
        normalized.append(value)
    return normalized

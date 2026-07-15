import json
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = ROOT / "data" / "local_system" / "market_data.sqlite"


def connect(db_path=DEFAULT_DB_PATH):
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.executescript(
        """
        pragma journal_mode = wal;
        create table if not exists us_rate_series (
            series_id text primary key,
            title text not null,
            instrument_type text not null,
            maturity_months integer,
            units text not null,
            source_workbook text not null,
            source_sheet text not null
        );
        create table if not exists us_rate_points (
            series_id text not null,
            date text not null,
            value real not null,
            source_workbook text not null,
            source_sheet text not null,
            primary key(series_id, date),
            foreign key(series_id) references us_rate_series(series_id)
        );
        create index if not exists idx_us_rate_points_series_date
        on us_rate_points(series_id, date);
        create table if not exists macro_indicator_series (
            series_id text primary key,
            title text not null,
            units text not null,
            source text not null
        );
        create table if not exists macro_indicator_points (
            series_id text not null,
            date text not null,
            value real not null,
            source text not null,
            primary key(series_id, date),
            foreign key(series_id) references macro_indicator_series(series_id)
        );
        create index if not exists idx_macro_indicator_points_series_date
        on macro_indicator_points(series_id, date);
        create table if not exists macro_ai_interpretations (
            scope text not null,
            snapshot_hash text not null,
            as_of text,
            prompt_version text not null,
            model text not null,
            tone text not null,
            status text not null,
            text_en text not null,
            text_zh text not null,
            metrics_json text not null,
            generated_at text not null,
            primary key(scope, snapshot_hash)
        );
        create index if not exists idx_macro_ai_interpretations_scope_generated
        on macro_ai_interpretations(scope, generated_at);
        create table if not exists macro_events (
            event_id text primary key,
            event_type text not null,
            start_date text not null,
            end_date text,
            display_month text not null,
            title text not null,
            source text not null,
            policy_tone text not null default 'unknown',
            has_sep integer not null default 0,
            url text
        );
        create index if not exists idx_macro_events_type_start
        on macro_events(event_type, start_date);
        create index if not exists idx_macro_events_type_month
        on macro_events(event_type, display_month);
        create table if not exists macro_event_documents (
            event_id text not null,
            document_type text not null,
            url text not null,
            text text not null,
            source_hash text not null,
            fetched_at text not null,
            primary key(event_id, document_type),
            foreign key(event_id) references macro_events(event_id)
        );
        create index if not exists idx_macro_event_documents_type_hash
        on macro_event_documents(document_type, source_hash);
        create table if not exists macro_event_tone_extractions (
            event_id text not null,
            source_document_type text not null,
            source_hash text not null,
            previous_event_id text,
            policy_action text not null default 'unknown',
            guidance_bias text not null default 'unknown',
            language_tone text not null default 'unknown',
            overall_bias text not null default 'unknown',
            statement_tone text not null,
            minutes_tone text not null,
            marker_tone text not null,
            tone_score integer not null,
            tone_change text not null,
            confidence text not null,
            extraction_status text not null,
            review_rounds integer not null,
            extractor_model text not null,
            reviewer_model text not null,
            facts_json text not null,
            comparison_json text not null,
            reviewer_feedback_json text not null,
            final_reviewer_feedback_json text not null default '[]',
            reason text not null,
            generated_at text not null,
            primary key(event_id, source_document_type, source_hash),
            foreign key(event_id) references macro_events(event_id)
        );
        create index if not exists idx_macro_event_tone_event_type_generated
        on macro_event_tone_extractions(event_id, source_document_type, generated_at);

        """
    )
    _ensure_column(
        con,
        "macro_event_tone_extractions",
        "final_reviewer_feedback_json",
        "text not null default '[]'",
    )
    for column_name in [
        "policy_action",
        "guidance_bias",
        "language_tone",
        "overall_bias",
    ]:
        _ensure_column(
            con,
            "macro_event_tone_extractions",
            column_name,
            "text not null default 'unknown'",
        )
    return con


def _ensure_column(con, table_name, column_name, column_definition):
    columns = [
        row["name"]
        for row in con.execute(f"pragma table_info({table_name})").fetchall()
    ]
    if column_name in columns:
        return
    con.execute(
        f"alter table {table_name} add column {column_name} {column_definition}"
    )
    con.commit()


def normalize_series_id(series_id):
    normalized = str(series_id or "").strip().lower()
    if not normalized:
        raise ValueError("rate series id is required")
    return normalized


def replace_rate_series_points(con, series, points):
    sid = normalize_series_id(series["series_id"])
    con.execute("delete from us_rate_points where series_id = ?", (sid,))
    con.execute("delete from us_rate_series where series_id = ?", (sid,))
    con.execute(
        """
        insert into us_rate_series(
            series_id, title, instrument_type, maturity_months,
            units, source_workbook, source_sheet
        ) values (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            sid,
            series["title"],
            series["instrument_type"],
            series.get("maturity_months"),
            series["units"],
            series["source_workbook"],
            series["source_sheet"],
        ),
    )
    for point in points:
        con.execute(
            """
            insert into us_rate_points(
                series_id, date, value, source_workbook, source_sheet
            ) values (?, ?, ?, ?, ?)
            """,
            (
                sid,
                point["date"],
                point["value"],
                point["source_workbook"],
                point["source_sheet"],
            ),
        )
    con.commit()
    return {"series": 1, "points": len(points)}


def load_rate_series(con):
    rows = con.execute(
        """
        select series_id, title, instrument_type, maturity_months,
               units, source_workbook, source_sheet
        from us_rate_series
        order by instrument_type, maturity_months, series_id
        """
    ).fetchall()
    return [dict(row) for row in rows]


def load_rate_points(con, series_id):
    sid = normalize_series_id(series_id)
    rows = con.execute(
        """
        select date, value, source_workbook, source_sheet
        from us_rate_points
        where series_id = ?
        order by date
        """,
        (sid,),
    ).fetchall()
    return [dict(row) for row in rows]


def load_latest_points(con):
    rows = con.execute(
        """
        select p.series_id, p.date, p.value, p.source_workbook, p.source_sheet
        from us_rate_points p
        join (
            select series_id, max(date) as max_date
            from us_rate_points
            group by series_id
        ) latest
        on latest.series_id = p.series_id and latest.max_date = p.date
        order by p.series_id
        """
    ).fetchall()
    return [dict(row) for row in rows]


def load_rate_points_for_series(con, series_ids):
    normalized_ids = [normalize_series_id(series_id) for series_id in series_ids]
    grouped = {series_id: [] for series_id in normalized_ids}
    for series_id in normalized_ids:
        grouped[series_id] = load_rate_points(con, series_id)
    return grouped


def replace_macro_indicator_points(con, series, points):
    sid = normalize_series_id(series["series_id"])
    con.execute("delete from macro_indicator_points where series_id = ?", (sid,))
    con.execute("delete from macro_indicator_series where series_id = ?", (sid,))
    con.execute(
        """
        insert into macro_indicator_series(series_id, title, units, source)
        values (?, ?, ?, ?)
        """,
        (sid, series["title"], series["units"], series["source"]),
    )
    for point in points:
        con.execute(
            """
            insert into macro_indicator_points(series_id, date, value, source)
            values (?, ?, ?, ?)
            """,
            (sid, point["date"], point["value"], point["source"]),
        )
    con.commit()
    return {"series": 1, "points": len(points)}


def merge_macro_indicator_points(con, series, points):
    sid = normalize_series_id(series["series_id"])
    con.execute(
        """
        insert into macro_indicator_series(series_id, title, units, source)
        values (?, ?, ?, ?)
        on conflict(series_id) do update set
            title = excluded.title,
            units = excluded.units,
            source = excluded.source
        """,
        (sid, series["title"], series["units"], series["source"]),
    )
    for point in points:
        con.execute(
            """
            insert into macro_indicator_points(series_id, date, value, source)
            values (?, ?, ?, ?)
            on conflict(series_id, date) do update set
                value = excluded.value,
                source = excluded.source
            """,
            (sid, point["date"], point["value"], point["source"]),
        )
    con.commit()
    return {"series": 1, "points": len(points)}


def load_macro_indicator_series(con):
    rows = con.execute(
        """
        select series_id, title, units, source
        from macro_indicator_series
        order by series_id
        """
    ).fetchall()
    return [dict(row) for row in rows]


def load_macro_indicator_points(con, series_id):
    sid = normalize_series_id(series_id)
    rows = con.execute(
        """
        select date, value, source
        from macro_indicator_points
        where series_id = ?
        order by date
        """,
        (sid,),
    ).fetchall()
    return [dict(row) for row in rows]


def load_latest_macro_indicator_points(con):
    rows = con.execute(
        """
        select p.series_id, p.date, p.value, p.source
        from macro_indicator_points p
        join (
            select series_id, max(date) as max_date
            from macro_indicator_points
            group by series_id
        ) latest
        on latest.series_id = p.series_id and latest.max_date = p.date
        order by p.series_id
        """
    ).fetchall()
    return [dict(row) for row in rows]


def load_macro_indicator_points_for_series(con, series_ids):
    normalized_ids = [normalize_series_id(series_id) for series_id in series_ids]
    return {
        series_id: load_macro_indicator_points(con, series_id)
        for series_id in normalized_ids
    }


def replace_ai_interpretation(con, row):
    con.execute(
        """
        insert into macro_ai_interpretations(
            scope, snapshot_hash, as_of, prompt_version, model, tone, status,
            text_en, text_zh, metrics_json, generated_at
        ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        on conflict(scope, snapshot_hash) do update set
            as_of = excluded.as_of,
            prompt_version = excluded.prompt_version,
            model = excluded.model,
            tone = excluded.tone,
            status = excluded.status,
            text_en = excluded.text_en,
            text_zh = excluded.text_zh,
            metrics_json = excluded.metrics_json,
            generated_at = excluded.generated_at
        """,
        (
            row["scope"],
            row["snapshot_hash"],
            row.get("as_of"),
            row["prompt_version"],
            row["model"],
            row["tone"],
            row["status"],
            row["text_en"],
            row["text_zh"],
            row["metrics_json"],
            row["generated_at"],
        ),
    )
    con.commit()
    return {"interpretations": 1}


def load_ai_interpretation(con, scope, snapshot_hash):
    rows = con.execute(
        """
        select scope, as_of, snapshot_hash, prompt_version, model, tone, status,
               text_en, text_zh, metrics_json, generated_at
        from macro_ai_interpretations
        where scope = ? and snapshot_hash = ?
        """,
        (scope, snapshot_hash),
    ).fetchall()
    return dict(rows[0]) if rows else None


def normalize_event_type(event_type):
    normalized = str(event_type or "").strip().lower()
    if not normalized:
        raise ValueError("macro event type is required")
    return normalized


def replace_macro_events(con, event_type, events):
    normalized_type = normalize_event_type(event_type)
    con.execute("delete from macro_events where event_type = ?", (normalized_type,))
    for event in events:
        con.execute(
            """
            insert into macro_events(
                event_id, event_type, start_date, end_date, display_month,
                title, source, policy_tone, has_sep, url
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event["event_id"],
                normalized_type,
                event["start_date"],
                event.get("end_date"),
                event["display_month"],
                event["title"],
                event["source"],
                event.get("policy_tone", "unknown"),
                int(event.get("has_sep", 0)),
                event.get("url"),
            ),
        )
    con.commit()
    return {"events": len(events)}


def load_macro_events(con, event_type):
    normalized_type = normalize_event_type(event_type)
    rows = con.execute(
        """
        select event_id, event_type, start_date, end_date, display_month,
               title, source, policy_tone, has_sep, url
        from macro_events
        where event_type = ?
        order by start_date
        """,
        (normalized_type,),
    ).fetchall()
    return [dict(row) for row in rows]


def load_next_macro_event(con, event_type, as_of_date):
    normalized_type = normalize_event_type(event_type)
    rows = con.execute(
        """
        select event_id, event_type, start_date, end_date, display_month,
               title, source, policy_tone, has_sep, url
        from macro_events
        where event_type = ?
          and start_date >= ?
        order by start_date
        limit 1
        """,
        (normalized_type, as_of_date),
    ).fetchall()
    return dict(rows[0]) if rows else None


def replace_macro_event_document(con, row):
    con.execute(
        """
        insert into macro_event_documents(
            event_id, document_type, url, text, source_hash, fetched_at
        ) values (?, ?, ?, ?, ?, ?)
        on conflict(event_id, document_type) do update set
            url = excluded.url,
            text = excluded.text,
            source_hash = excluded.source_hash,
            fetched_at = excluded.fetched_at
        """,
        (
            row["event_id"],
            row["document_type"],
            row["url"],
            row["text"],
            row["source_hash"],
            row["fetched_at"],
        ),
    )
    con.commit()
    return {"documents": 1}


def load_macro_event_documents(con, event_id):
    rows = con.execute(
        """
        select event_id, document_type, url, text, source_hash, fetched_at
        from macro_event_documents
        where event_id = ?
        order by document_type
        """,
        (event_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def load_macro_event_document(con, event_id, document_type):
    rows = con.execute(
        """
        select event_id, document_type, url, text, source_hash, fetched_at
        from macro_event_documents
        where event_id = ? and document_type = ?
        """,
        (event_id, document_type),
    ).fetchall()
    return dict(rows[0]) if rows else None


def replace_macro_event_tone_extraction(con, row):
    con.execute(
        """
        insert into macro_event_tone_extractions(
            event_id, source_document_type, source_hash, previous_event_id,
            policy_action, guidance_bias, language_tone, overall_bias,
            statement_tone, minutes_tone, marker_tone, tone_score, tone_change,
            confidence, extraction_status, review_rounds, extractor_model,
            reviewer_model, facts_json, comparison_json, reviewer_feedback_json,
            final_reviewer_feedback_json, reason, generated_at
        ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        on conflict(event_id, source_document_type, source_hash) do update set
            previous_event_id = excluded.previous_event_id,
            policy_action = excluded.policy_action,
            guidance_bias = excluded.guidance_bias,
            language_tone = excluded.language_tone,
            overall_bias = excluded.overall_bias,
            statement_tone = excluded.statement_tone,
            minutes_tone = excluded.minutes_tone,
            marker_tone = excluded.marker_tone,
            tone_score = excluded.tone_score,
            tone_change = excluded.tone_change,
            confidence = excluded.confidence,
            extraction_status = excluded.extraction_status,
            review_rounds = excluded.review_rounds,
            extractor_model = excluded.extractor_model,
            reviewer_model = excluded.reviewer_model,
            facts_json = excluded.facts_json,
            comparison_json = excluded.comparison_json,
            reviewer_feedback_json = excluded.reviewer_feedback_json,
            final_reviewer_feedback_json = excluded.final_reviewer_feedback_json,
            reason = excluded.reason,
            generated_at = excluded.generated_at
        """,
        (
            row["event_id"],
            row["source_document_type"],
            row["source_hash"],
            row.get("previous_event_id"),
            row.get("policy_action", "unknown"),
            row.get("guidance_bias", "unknown"),
            row.get("language_tone", "unknown"),
            row.get("overall_bias", "unknown"),
            row["statement_tone"],
            row["minutes_tone"],
            row["marker_tone"],
            int(row["tone_score"]),
            row["tone_change"],
            row["confidence"],
            row["extraction_status"],
            int(row["review_rounds"]),
            row["extractor_model"],
            row["reviewer_model"],
            row["facts_json"],
            row["comparison_json"],
            row["reviewer_feedback_json"],
            row.get("final_reviewer_feedback_json", "[]"),
            row["reason"],
            row["generated_at"],
        ),
    )
    con.commit()
    return {"tone_extractions": 1}


def load_latest_macro_event_tone_extraction(con, event_id, source_document_type):
    rows = con.execute(
        """
        select event_id, source_document_type, source_hash, previous_event_id,
               policy_action, guidance_bias, language_tone, overall_bias,
               statement_tone, minutes_tone, marker_tone, tone_score,
               tone_change, confidence, extraction_status, review_rounds,
               extractor_model, reviewer_model, facts_json, comparison_json,
               reviewer_feedback_json, final_reviewer_feedback_json,
               reason, generated_at
        from macro_event_tone_extractions
        where event_id = ? and source_document_type = ?
        order by generated_at desc
        limit 1
        """,
        (event_id, source_document_type),
    ).fetchall()
    return dict(rows[0]) if rows else None


def load_macro_event_tone_extraction(con, event_id, source_document_type, source_hash):
    rows = con.execute(
        """
        select event_id, source_document_type, source_hash, previous_event_id,
               policy_action, guidance_bias, language_tone, overall_bias,
               statement_tone, minutes_tone, marker_tone, tone_score,
               tone_change, confidence, extraction_status, review_rounds,
               extractor_model, reviewer_model, facts_json, comparison_json,
               reviewer_feedback_json, final_reviewer_feedback_json,
               reason, generated_at
        from macro_event_tone_extractions
        where event_id = ? and source_document_type = ? and source_hash = ?
        """,
        (event_id, source_document_type, source_hash),
    ).fetchall()
    return dict(rows[0]) if rows else None


def _json_object(value):
    if not value:
        return {}
    return json.loads(value)


def load_macro_events_with_latest_tone(con, event_type):
    events = load_macro_events(con, event_type)
    result = []
    for event in events:
        merged = dict(event)
        document = load_macro_event_document(con, event["event_id"], "statement")
        if document:
            tone = load_macro_event_tone_extraction(
                con,
                event["event_id"],
                "statement",
                document["source_hash"],
            )
            if tone:
                merged.update(
                    {
                        "statement_tone": tone["statement_tone"],
                        "marker_tone": tone["marker_tone"],
                        "policy_action": tone["policy_action"],
                        "guidance_bias": tone["guidance_bias"],
                        "language_tone": tone["language_tone"],
                        "overall_bias": tone["overall_bias"],
                        "tone_change": tone["tone_change"],
                        "tone_confidence": tone["confidence"],
                        "tone_reason": tone["reason"],
                    }
                )
        minutes_document = load_macro_event_document(con, event["event_id"], "minutes")
        if minutes_document:
            minutes_tone = load_macro_event_tone_extraction(
                con,
                event["event_id"],
                "minutes",
                minutes_document["source_hash"],
            )
            if minutes_tone and minutes_tone["extraction_status"] == "approved":
                minutes_facts = _json_object(minutes_tone.get("facts_json"))
                merged.update(
                    {
                        "minutes_status": "available",
                        "minutes_tone": minutes_tone.get("minutes_tone", "unknown"),
                        "minutes_confirmation": minutes_facts.get(
                            "minutes_confirmation",
                            "unknown",
                        ),
                        "risk_focus": minutes_facts.get("risk_focus", "unknown"),
                        "risk_bias": minutes_facts.get("risk_bias", "unknown"),
                        "divergence_level": minutes_facts.get(
                            "divergence_level",
                            "unknown",
                        ),
                        "uncertainty_level": minutes_facts.get(
                            "uncertainty_level",
                            "unknown",
                        ),
                        "policy_conviction": minutes_facts.get(
                            "policy_conviction",
                            "unknown",
                        ),
                        "minutes_confidence": minutes_tone.get("confidence"),
                        "minutes_reason": minutes_tone.get("reason"),
                        "minutes_generated_at": minutes_tone.get("generated_at"),
                    }
                )
            else:
                merged.update(
                    {
                        "minutes_status": "pending",
                        "minutes_confirmation": "pending",
                        "policy_conviction": "unknown",
                    }
                )
        else:
            merged.update(
                {
                    "minutes_status": "pending",
                    "minutes_confirmation": "pending",
                    "policy_conviction": "unknown",
                }
            )
        result.append(merged)
    return result


def load_latest_approved_macro_event_tone(
    con, event_type, as_of_date, document_type="statement"
):
    normalized_type = normalize_event_type(event_type)
    rows = con.execute(
        """
        select e.event_id, e.start_date, e.end_date, e.display_month, e.title,
               d.source_hash,
               t.policy_action, t.guidance_bias, t.language_tone, t.overall_bias,
               t.statement_tone, t.marker_tone, t.tone_score, t.tone_change,
               t.confidence, t.extraction_status, t.reason, t.generated_at
        from macro_events e
        join macro_event_documents d
          on d.event_id = e.event_id and d.document_type = ?
        join macro_event_tone_extractions t
          on t.event_id = e.event_id
         and t.source_document_type = ?
         and t.source_hash = d.source_hash
        where e.event_type = ?
          and e.start_date <= ?
          and t.extraction_status = 'approved'
        order by e.start_date desc, t.generated_at desc
        limit 1
        """,
        (document_type, document_type, normalized_type, as_of_date),
    ).fetchall()
    return dict(rows[0]) if rows else None


def load_latest_combined_fomc_policy_read(con, as_of_date):
    statement = load_latest_approved_macro_event_tone(
        con,
        "fomc_meeting",
        as_of_date,
        "statement",
    )
    if not statement:
        return None
    minutes_document = load_macro_event_document(
        con,
        statement["event_id"],
        "minutes",
    )
    minutes = None
    minutes_facts = {}
    if minutes_document:
        minutes = load_macro_event_tone_extraction(
            con,
            statement["event_id"],
            "minutes",
            minutes_document["source_hash"],
        )
        if minutes and minutes.get("extraction_status") == "approved":
            minutes_facts = _json_object(minutes.get("facts_json"))
        else:
            minutes = None
    return {
        "event_id": statement["event_id"],
        "start_date": statement["start_date"],
        "end_date": statement["end_date"],
        "display_month": statement["display_month"],
        "title": statement["title"],
        "statement_marker_tone": statement["marker_tone"],
        "statement_policy_action": statement["policy_action"],
        "statement_guidance_bias": statement["guidance_bias"],
        "statement_language_tone": statement["language_tone"],
        "statement_overall_bias": statement["overall_bias"],
        "statement_tone_change": statement["tone_change"],
        "statement_confidence": statement["confidence"],
        "statement_reason": statement["reason"],
        "minutes_status": "available" if minutes else "pending",
        "minutes_confirmation": minutes_facts.get("minutes_confirmation", "pending"),
        "risk_focus": minutes_facts.get("risk_focus", "unknown"),
        "risk_bias": minutes_facts.get("risk_bias", "unknown"),
        "divergence_level": minutes_facts.get("divergence_level", "unknown"),
        "uncertainty_level": minutes_facts.get("uncertainty_level", "unknown"),
        "policy_conviction": minutes_facts.get("policy_conviction", "unknown"),
        "minutes_tone": minutes["minutes_tone"] if minutes else "unknown",
        "minutes_confidence": minutes["confidence"] if minutes else None,
        "minutes_reason": minutes["reason"] if minutes else None,
    }

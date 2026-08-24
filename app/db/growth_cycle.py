import json
import sqlite3
from pathlib import Path

from app.db import ism_surveys


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = ROOT / "data" / "local_system" / "market_data.sqlite"


def connect(db_path=DEFAULT_DB_PATH):
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    init_db(con)
    return con


def init_db(con):
    con.executescript(
        """
        create table if not exists ism_industry_rankings (
            date text not null,
            industry text not null,
            direction text not null,
            rank integer not null,
            source text not null,
            primary key(date, industry)
        );
        create index if not exists idx_ism_industry_rankings_date
        on ism_industry_rankings(date);
        create table if not exists ism_report_snapshots (
            report_id text primary key,
            report_month text not null,
            title text not null,
            source_url text not null,
            source_hash text not null,
            fetched_at text not null,
            parse_status text not null,
            next_report_period text,
            next_release_at text,
            next_release_label text not null
        );
        create index if not exists idx_ism_report_snapshots_month
        on ism_report_snapshots(report_month);
        create table if not exists ism_report_comments (
            report_id text not null,
            comment_index integer not null,
            report_month text not null,
            industry text not null,
            comment_text text not null,
            source_url text not null,
            source_hash text not null,
            primary key(report_id, comment_index)
        );
        create index if not exists idx_ism_report_comments_report
        on ism_report_comments(report_id);
        create table if not exists ism_at_a_glance_rows (
            report_id text not null,
            report_month text not null,
            series_id text not null,
            label text not null,
            current_value real not null,
            previous_value real,
            point_change real,
            direction text not null,
            rate_of_change text not null,
            trend_months integer,
            source_url text not null,
            source_hash text not null,
            primary key(report_id, series_id)
        );
        create index if not exists idx_ism_at_a_glance_rows_month
        on ism_at_a_glance_rows(report_month);
        create table if not exists ism_report_source_snapshots (
            source_url text primary key,
            source_name text not null,
            survey_type text not null default 'manufacturing',
            source_hash text not null,
            fetched_at text not null,
            raw_html text not null,
            parse_status text not null,
            parse_error text,
            report_id text,
            report_month text
        );
        create index if not exists idx_ism_report_source_snapshots_report
        on ism_report_source_snapshots(report_id);
        create table if not exists ism_ai_extractions (
            report_id text not null,
            source_url text not null,
            report_month text not null,
            source_hash text not null,
            extractor text not null,
            model text not null,
            prompt_version text not null,
            validation_status text not null,
            validation_error text,
            extraction_json text not null,
            primary key(report_id, source_url, prompt_version)
        );
        create table if not exists ism_report_industry_signals (
            report_id text not null,
            report_month text not null,
            signal_type text not null,
            direction text not null,
            industry text not null,
            rank integer not null,
            evidence_text text not null,
            source_url text not null,
            source_hash text not null,
            primary key(report_id, signal_type, direction, industry)
        );
        create index if not exists idx_ism_report_industry_signals_industry
        on ism_report_industry_signals(industry, report_month);
        create table if not exists ism_report_ai_summaries (
            report_id text primary key,
            report_month text not null,
            compared_to_report_month text,
            summary_text text not null,
            summary_json text not null,
            model text not null,
            prompt_version text not null,
            source_hash text not null
        );
        create table if not exists ism_report_commodities (
            report_id text not null,
            report_month text not null,
            commodity text not null,
            signal_type text not null,
            months integer,
            source_hash text not null,
            primary key(report_id, commodity, signal_type)
        );
        create table if not exists ism_report_narrative_facts (
            report_id text primary key,
            report_month text not null,
            facts_json text not null,
            source_hash text not null
        );
        create table if not exists ism_ai_section_extractions (
            report_id text not null,
            source_url text not null,
            report_month text not null,
            source_hash text not null,
            section_name text not null,
            status text not null,
            payload_json text not null,
            error text,
            attempt_count integer not null,
            model text not null,
            prompt_version text not null,
            updated_at text not null,
            primary key(report_id, source_url, prompt_version, section_name)
        );
        create index if not exists idx_ism_ai_section_extractions_report
        on ism_ai_section_extractions(report_id, prompt_version, status);
        create table if not exists ism_ai_summary_runs (
            report_id text not null,
            report_month text not null,
            source_hash text not null,
            facts_hash text not null,
            status text not null,
            quality_status text not null,
            summary_text text not null,
            summary_json text not null,
            guidance text not null,
            error text,
            attempt_count integer not null,
            model text not null,
            prompt_version text not null,
            updated_at text not null,
            primary key(report_id, facts_hash, prompt_version, updated_at)
        );
        create index if not exists idx_ism_ai_summary_runs_report
        on ism_ai_summary_runs(report_id, status, quality_status, updated_at);
        create table if not exists ism_report_industry_signal_coverage (
            report_id text not null,
            report_month text not null,
            signal_type text not null,
            direction text not null,
            list_present integer not null,
            declared_count integer,
            extracted_count integer not null,
            validation_status text not null,
            evidence_text text not null,
            source_url text not null,
            source_hash text not null,
            primary key(report_id, signal_type, direction)
        );
        create index if not exists idx_ism_signal_coverage_month
        on ism_report_industry_signal_coverage(report_month);
        """
    )
    con.commit()
    source_snap_columns = {
        row["name"]
        for row in con.execute(
            "pragma table_info(ism_report_source_snapshots)"
        ).fetchall()
    }
    if "survey_type" not in source_snap_columns:
        con.execute(
            "alter table ism_report_source_snapshots add column survey_type text not null default 'manufacturing'"
        )
        con.execute(
            "update ism_report_source_snapshots set survey_type = 'services' where report_id like 'ism_services_%'"
        )
    con.execute(
        "create index if not exists idx_ism_report_source_snapshots_survey on ism_report_source_snapshots(survey_type)"
    )
    con.commit()
    ism_surveys.init_db(con)


def replace_ism_industry_rankings(con, rows, survey_type="manufacturing"):
    return ism_surveys.replace_industry_rankings(con, survey_type, rows)


def load_latest_ism_industry_rankings(con, survey_type="manufacturing"):
    rows = ism_surveys.load_industry_rankings(con, survey_type, limit_months=1)
    return [{k: v for k, v in row.items() if k != "survey_type"} for row in rows]


def replace_ism_report_snapshot(con, report, comments, survey_type="manufacturing"):
    return ism_surveys.replace_report_snapshot(con, survey_type, report, comments)


def load_existing_ism_report_months(con, survey_type="manufacturing"):
    return ism_surveys.load_existing_report_months(con, survey_type)


def load_latest_ism_report_snapshot(con, survey_type="manufacturing"):
    return ism_surveys.load_latest_report_snapshot(con, survey_type)


def load_all_ism_report_snapshots(con):
    rows = con.execute(
        """
        select report_id, report_month, title, source_url, source_hash, fetched_at,
               parse_status, next_report_period, next_release_at, next_release_label
        from ism_report_snapshots
        order by report_month
        """
    ).fetchall()
    return [dict(row) for row in rows]


def load_ism_report_comments(con, report_id):
    rows = con.execute(
        """
        select report_id, report_month, industry, comment_index, comment_text,
               source_url, source_hash
        from ism_report_comments
        where report_id = ?
        order by comment_index
        """,
        (report_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def replace_ism_at_a_glance_rows(con, rows, commit=True):
    report_ids = sorted({row["report_id"] for row in rows})
    for report_id in report_ids:
        con.execute(
            "delete from ism_at_a_glance_rows where report_id = ?", (report_id,)
        )
    for row in rows:
        con.execute(
            """
            insert into ism_at_a_glance_rows(
                report_id, report_month, series_id, label, current_value,
                previous_value, point_change, direction, rate_of_change,
                trend_months, source_url, source_hash
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["report_id"],
                row["report_month"],
                row["series_id"],
                row["label"],
                row["current_value"],
                row.get("previous_value"),
                row.get("point_change"),
                row["direction"],
                row["rate_of_change"],
                row.get("trend_months"),
                row["source_url"],
                row["source_hash"],
            ),
        )
    if commit:
        con.commit()
    return {"at_a_glance_rows": len(rows)}


def load_latest_ism_at_a_glance_rows(con):
    latest = con.execute(
        "select max(report_month) as latest_month from ism_at_a_glance_rows"
    ).fetchone()["latest_month"]
    if latest is None:
        return []
    rows = con.execute(
        """
        select report_id, report_month, series_id, label, current_value,
               previous_value, point_change, direction, rate_of_change,
               trend_months, source_url, source_hash
        from ism_at_a_glance_rows
        where report_month = ?
        order by series_id
        """,
        (latest,),
    ).fetchall()
    return [dict(row) for row in rows]


def replace_ism_report_source_snapshot(con, snapshot, commit=True):
    con.execute(
        """
        insert into ism_report_source_snapshots(
            source_url, source_name, survey_type, source_hash, fetched_at, raw_html,
            parse_status, parse_error, report_id, report_month
        ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        on conflict(source_url) do update set
            source_name = excluded.source_name,
            survey_type = excluded.survey_type,
            source_hash = excluded.source_hash,
            fetched_at = excluded.fetched_at,
            raw_html = excluded.raw_html,
            parse_status = excluded.parse_status,
            parse_error = excluded.parse_error,
            report_id = excluded.report_id,
            report_month = excluded.report_month
        """,
        (
            snapshot["source_url"],
            snapshot["source_name"],
            snapshot.get("survey_type", "manufacturing"),
            snapshot["source_hash"],
            snapshot["fetched_at"],
            snapshot["raw_html"],
            snapshot["parse_status"],
            snapshot.get("parse_error"),
            snapshot.get("report_id"),
            snapshot.get("report_month"),
        ),
    )
    if commit:
        con.commit()
    return {"source_snapshots": 1}


def load_ism_report_source_snapshot(con, source_url):
    row = con.execute(
        """
        select source_url, source_name, survey_type, source_hash, fetched_at, raw_html,
               parse_status, parse_error, report_id, report_month
        from ism_report_source_snapshots
        where source_url = ?
        """,
        (source_url,),
    ).fetchone()
    return dict(row) if row else None


def load_ism_report_source_snapshots(con, survey_type):
    rows = con.execute(
        """
        select source_url, source_name, survey_type, source_hash, fetched_at, raw_html,
               parse_status, parse_error, report_id, report_month
        from ism_report_source_snapshots
        where survey_type = ? and parse_status = 'ok'
          and report_id is not null and report_month is not null
        order by report_month, fetched_at, source_url
        """,
        (survey_type,),
    ).fetchall()
    return [dict(row) for row in rows]


def _derive_coverage_from_flat_signals(flat_signals):
    from collections import OrderedDict

    from app.tools.ism_ai_extraction import declared_industry_count

    groups = OrderedDict()
    for signal in flat_signals:
        key = (signal["signal_type"], signal["direction"])
        groups.setdefault(key, []).append(signal)
    coverage = []
    for (signal_type, direction), signals in groups.items():
        extracted_count = len(signals)
        declared = declared_industry_count(signals[0]["evidence_text"])
        list_present = extracted_count > 0
        if declared is not None and extracted_count == declared:
            validation_status = "complete"
        else:
            validation_status = "partial"
        coverage.append(
            {
                "signal_type": signal_type,
                "direction": direction,
                "list_present": list_present,
                "declared_count": declared,
                "extracted_count": extracted_count,
                "validation_status": validation_status,
                "evidence_text": signals[0]["evidence_text"],
            }
        )
    return coverage


def replace_ism_ai_extraction(con, extraction):
    import json

    from app.tools.ism_ai_extraction import (
        validate_extraction,
        validate_factual_extraction,
    )

    payload = extraction["extraction_json"]
    report_id = extraction["report_id"]
    payload = (
        validate_extraction(payload)
        if "ai_summary" in payload
        else validate_factual_extraction(payload)
    )

    if not payload.get("industry_signal_coverage") and payload.get("industry_signals"):
        payload["industry_signal_coverage"] = _derive_coverage_from_flat_signals(
            payload["industry_signals"]
        )
    con.execute(
        "delete from ism_report_industry_signals where report_id = ?",
        (report_id,),
    )
    con.execute(
        """
        insert into ism_ai_extractions(
            report_id, source_url, report_month, source_hash, extractor,
            model, prompt_version, validation_status, validation_error,
            extraction_json
        ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        on conflict(report_id, source_url, prompt_version) do update set
            report_month = excluded.report_month,
            source_hash = excluded.source_hash,
            extractor = excluded.extractor,
            model = excluded.model,
            validation_status = excluded.validation_status,
            validation_error = excluded.validation_error,
            extraction_json = excluded.extraction_json
        """,
        (
            report_id,
            extraction["source_url"],
            extraction["report_month"],
            extraction["source_hash"],
            extraction["extractor"],
            extraction["model"],
            extraction["prompt_version"],
            extraction["validation_status"],
            extraction.get("validation_error"),
            json.dumps(payload, sort_keys=True),
        ),
    )
    for signal in payload.get("industry_signals", []):
        con.execute(
            """
            insert into ism_report_industry_signals(
                report_id, report_month, signal_type, direction, industry,
                rank, evidence_text, source_url, source_hash
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                report_id,
                extraction["report_month"],
                signal["signal_type"],
                signal["direction"],
                signal["industry"],
                signal["rank"],
                signal["evidence_text"],
                extraction["source_url"],
                extraction["source_hash"],
            ),
        )
    con.execute(
        "delete from ism_report_industry_signal_coverage where report_id = ?",
        (report_id,),
    )
    for row in payload.get("industry_signal_coverage", []):
        con.execute(
            """
            insert into ism_report_industry_signal_coverage(
                report_id, report_month, signal_type, direction, list_present,
                declared_count, extracted_count, validation_status, evidence_text,
                source_url, source_hash
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                report_id,
                extraction["report_month"],
                row["signal_type"],
                row["direction"],
                1 if row["list_present"] else 0,
                row.get("declared_count"),
                row["extracted_count"],
                row["validation_status"],
                row["evidence_text"],
                extraction["source_url"],
                extraction["source_hash"],
            ),
        )
    con.commit()
    return {
        "ai_extractions": 1,
        "industry_signals": len(payload.get("industry_signals", [])),
        "industry_signal_coverage": len(payload.get("industry_signal_coverage", [])),
    }


def load_ism_report_industry_signals(con, report_id):
    rows = con.execute(
        """
        select report_id, report_month, signal_type, direction, industry,
               rank, evidence_text, source_url, source_hash
        from ism_report_industry_signals
        where report_id = ?
        order by signal_type, direction, rank
        """,
        (report_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def replace_ism_report_industry_signal_coverage(
    con, report_id, report_month, coverage_rows, source_url, source_hash
):
    con.execute(
        "delete from ism_report_industry_signal_coverage where report_id = ?",
        (report_id,),
    )
    for row in coverage_rows:
        con.execute(
            """
            insert into ism_report_industry_signal_coverage(
                report_id, report_month, signal_type, direction, list_present,
                declared_count, extracted_count, validation_status, evidence_text,
                source_url, source_hash
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                report_id,
                report_month,
                row["signal_type"],
                row["direction"],
                1 if row["list_present"] else 0,
                row.get("declared_count"),
                row["extracted_count"],
                row["validation_status"],
                row["evidence_text"],
                source_url,
                source_hash,
            ),
        )
    con.commit()
    return {"industry_signal_coverage": len(coverage_rows)}


def load_ism_report_industry_signal_coverage(con, report_id):
    rows = con.execute(
        """
        select report_id, report_month, signal_type, direction, list_present,
               declared_count, extracted_count, validation_status, evidence_text,
               source_url, source_hash
        from ism_report_industry_signal_coverage
        where report_id = ?
        order by signal_type, direction
        """,
        (report_id,),
    ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["list_present"] = bool(item["list_present"])
        result.append(item)
    return result


def load_ism_at_a_glance_rows(con, report_id):
    rows = con.execute(
        """
        select report_id, report_month, series_id, label, current_value,
               previous_value, point_change, direction, rate_of_change,
               trend_months, source_url, source_hash
        from ism_at_a_glance_rows
        where report_id = ?
        order by series_id
        """,
        (report_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def load_recent_ism_report_snapshots(con, limit=6, survey_type="manufacturing"):
    return ism_surveys.load_recent_report_snapshots(con, survey_type, limit)


def load_ism_report_industry_signals_for_reports(con, report_ids):
    if not report_ids:
        return []
    placeholders = ",".join("?" for _ in report_ids)
    rows = con.execute(
        f"""
        select report_id, report_month, signal_type, direction, industry,
               rank, evidence_text, source_url, source_hash
        from ism_report_industry_signals
        where report_id in ({placeholders})
        order by report_id, signal_type, direction, rank
        """,
        report_ids,
    ).fetchall()
    return [dict(row) for row in rows]


def load_ism_report_industry_signal_coverage_for_reports(con, report_ids):
    if not report_ids:
        return []
    placeholders = ",".join("?" for _ in report_ids)
    rows = con.execute(
        f"""
        select report_id, report_month, signal_type, direction, list_present,
               declared_count, extracted_count, validation_status, evidence_text,
               source_url, source_hash
        from ism_report_industry_signal_coverage
        where report_id in ({placeholders})
        order by report_id, signal_type, direction
        """,
        report_ids,
    ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["list_present"] = bool(item["list_present"])
        result.append(item)
    return result


def load_ism_at_a_glance_rows_for_reports(con, report_ids):
    if not report_ids:
        return []
    placeholders = ",".join("?" for _ in report_ids)
    rows = con.execute(
        f"""
        select report_id, report_month, series_id, label, current_value,
               previous_value, point_change, direction, rate_of_change,
               trend_months, source_url, source_hash
        from ism_at_a_glance_rows
        where report_id in ({placeholders})
        order by report_id, series_id
        """,
        report_ids,
    ).fetchall()
    return [dict(row) for row in rows]


def replace_ism_ai_summary(con, payload, source):
    report = payload["report"]
    summary = payload["ai_summary"]
    con.execute(
        """
        insert into ism_report_ai_summaries(
            report_id, report_month, compared_to_report_month, summary_text,
            summary_json, model, prompt_version, source_hash
        ) values (?, ?, ?, ?, ?, ?, ?, ?)
        on conflict(report_id) do update set
            report_month = excluded.report_month,
            compared_to_report_month = excluded.compared_to_report_month,
            summary_text = excluded.summary_text,
            summary_json = excluded.summary_json,
            model = excluded.model,
            prompt_version = excluded.prompt_version,
            source_hash = excluded.source_hash
        """,
        (
            report["report_id"],
            report["report_month"],
            summary.get("compared_to_report_month"),
            summary["summary_text"],
            json.dumps(summary, sort_keys=True),
            source["model"],
            source["prompt_version"],
            source["source_hash"],
        ),
    )
    return {"ai_summary": 1}


def replace_ism_report_commodities(con, payload, source):
    report = payload["report"]
    con.execute(
        "delete from ism_report_commodities where report_id = ?",
        (report["report_id"],),
    )
    for commodity in payload["commodities"]:
        con.execute(
            """
            insert into ism_report_commodities(
                report_id, report_month, commodity, signal_type, months, source_hash
            ) values (?, ?, ?, ?, ?, ?)
            """,
            (
                report["report_id"],
                report["report_month"],
                commodity["commodity"],
                commodity["signal_type"],
                commodity.get("months"),
                source["source_hash"],
            ),
        )
    return {"commodities": len(payload["commodities"])}


def load_ism_report_commodities(con, report_id):
    rows = con.execute(
        """
        select report_id, report_month, commodity, signal_type, months, source_hash
        from ism_report_commodities
        where report_id = ?
        order by commodity
        """,
        (report_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def replace_ism_report_narrative_facts(con, payload, source):
    report = payload["report"]
    con.execute(
        """
        insert into ism_report_narrative_facts(
            report_id, report_month, facts_json, source_hash
        ) values (?, ?, ?, ?)
        on conflict(report_id) do update set
            report_month = excluded.report_month,
            facts_json = excluded.facts_json,
            source_hash = excluded.source_hash
        """,
        (
            report["report_id"],
            report["report_month"],
            json.dumps(payload.get("narrative_facts", {}), sort_keys=True),
            source["source_hash"],
        ),
    )
    return {"narrative_facts": 1}


def load_ism_report_narrative_facts(con, report_id):
    row = con.execute(
        """
        select report_id, report_month, facts_json, source_hash
        from ism_report_narrative_facts
        where report_id = ?
        """,
        (report_id,),
    ).fetchone()
    if not row:
        return None
    item = dict(row)
    item["facts_json"] = json.loads(item["facts_json"])
    return item


def load_ism_report_ai_summary(con, report_id):
    row = con.execute(
        """
        select report_id, report_month, compared_to_report_month, summary_text,
               summary_json, model, prompt_version, source_hash
        from ism_report_ai_summaries
        where report_id = ?
        """,
        (report_id,),
    ).fetchone()
    return dict(row) if row else None


def replace_ism_ai_report_outputs(con, payload, source):
    from app.tools.ism_ai_extraction import validate_extraction
    from app.tools.ism_ai_extraction import validate_factual_extraction

    has_ai_summary = "ai_summary" in payload
    payload = (
        validate_extraction(payload)
        if has_ai_summary
        else validate_factual_extraction(payload)
    )
    report = payload["report"]
    extraction_saved = replace_ism_ai_extraction(
        con,
        {
            "report_id": report["report_id"],
            "report_month": report["report_month"],
            "source_url": source["source_url"],
            "source_hash": source["source_hash"],
            "extractor": "llm",
            "model": source["model"],
            "prompt_version": source["prompt_version"],
            "validation_status": "ok",
            "validation_error": None,
            "extraction_json": payload,
        },
    )
    summary_saved = (
        replace_ism_ai_summary(con, payload, source)
        if has_ai_summary
        else {"ai_summary": 0}
    )
    commodity_saved = replace_ism_report_commodities(con, payload, source)
    narrative_saved = replace_ism_report_narrative_facts(con, payload, source)
    con.commit()
    return {
        **extraction_saved,
        **summary_saved,
        **commodity_saved,
        **narrative_saved,
    }


def replace_ism_ai_section_extraction(con, checkpoint):
    con.execute(
        """
        insert into ism_ai_section_extractions(
            report_id, source_url, report_month, source_hash, section_name,
            status, payload_json, error, attempt_count, model, prompt_version,
            updated_at
        ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        on conflict(report_id, source_url, prompt_version, section_name) do update set
            report_month = excluded.report_month,
            source_hash = excluded.source_hash,
            status = excluded.status,
            payload_json = excluded.payload_json,
            error = excluded.error,
            attempt_count = excluded.attempt_count,
            model = excluded.model,
            updated_at = excluded.updated_at
        """,
        (
            checkpoint["report_id"],
            checkpoint["source_url"],
            checkpoint["report_month"],
            checkpoint["source_hash"],
            checkpoint["section_name"],
            checkpoint["status"],
            json.dumps(checkpoint.get("payload_json", {}), sort_keys=True),
            checkpoint.get("error"),
            checkpoint["attempt_count"],
            checkpoint["model"],
            checkpoint["prompt_version"],
            checkpoint["updated_at"],
        ),
    )
    con.commit()
    return {"ai_section_extractions": 1}


def load_ism_ai_section_extractions(con, report_id, source_url, prompt_version):
    rows = con.execute(
        """
        select report_id, source_url, report_month, source_hash, section_name,
               status, payload_json, error, attempt_count, model, prompt_version,
               updated_at
        from ism_ai_section_extractions
        where report_id = ? and source_url = ? and prompt_version = ?
        order by section_name
        """,
        (report_id, source_url, prompt_version),
    ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["payload_json"] = json.loads(item["payload_json"])
        result.append(item)
    return result


def load_ism_ai_section_extraction(
    con, report_id, source_url, prompt_version, section_name
):
    rows = load_ism_ai_section_extractions(con, report_id, source_url, prompt_version)
    for row in rows:
        if row["section_name"] == section_name:
            return row
    return None


def replace_ism_ai_summary_run(con, summary_run):
    con.execute(
        """
        insert into ism_ai_summary_runs(
            report_id, report_month, source_hash, facts_hash, status,
            quality_status, summary_text, summary_json, guidance, error,
            attempt_count, model, prompt_version, updated_at
        ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            summary_run["report_id"],
            summary_run["report_month"],
            summary_run["source_hash"],
            summary_run["facts_hash"],
            summary_run["status"],
            summary_run["quality_status"],
            summary_run["summary_text"],
            json.dumps(summary_run["summary_json"], sort_keys=True),
            summary_run.get("guidance", ""),
            summary_run.get("error"),
            summary_run["attempt_count"],
            summary_run["model"],
            summary_run["prompt_version"],
            summary_run["updated_at"],
        ),
    )
    con.commit()
    return {"ai_summary_runs": 1}


def load_latest_ism_ai_summary_run(con, report_id):
    row = con.execute(
        """
        select report_id, report_month, source_hash, facts_hash, status,
               quality_status, summary_text, summary_json, guidance, error,
               attempt_count, model, prompt_version, updated_at
        from ism_ai_summary_runs
        where report_id = ?
        order by updated_at desc
        limit 1
        """,
        (report_id,),
    ).fetchone()
    if not row:
        return None
    item = dict(row)
    item["summary_json"] = json.loads(item["summary_json"])
    return item

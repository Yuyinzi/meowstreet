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
        """
    )
    con.commit()


def replace_ism_industry_rankings(con, rows):
    con.execute("delete from ism_industry_rankings")
    for row in rows:
        con.execute(
            """
            insert into ism_industry_rankings(date, industry, direction, rank, source)
            values (?, ?, ?, ?, ?)
            """,
            (
                row["date"],
                row["industry"],
                row["direction"],
                row["rank"],
                row["source"],
            ),
        )
    con.commit()
    return len(rows)


def load_latest_ism_industry_rankings(con):
    latest = con.execute(
        "select max(date) as latest_date from ism_industry_rankings"
    ).fetchone()["latest_date"]
    if latest is None:
        return []
    rows = con.execute(
        """
        select date, industry, direction, rank, source
        from ism_industry_rankings
        where date = ?
        order by direction desc, rank desc, industry
        """,
        (latest,),
    ).fetchall()
    return [
        {
            "date": row["date"],
            "industry": row["industry"],
            "direction": row["direction"],
            "rank": row["rank"],
            "source": row["source"],
        }
        for row in rows
    ]


def replace_ism_report_snapshot(con, report, comments):
    con.execute(
        """
        insert into ism_report_snapshots(
            report_id, report_month, title, source_url, source_hash, fetched_at,
            parse_status, next_report_period, next_release_at, next_release_label
        ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        on conflict(report_id) do update set
            report_month = excluded.report_month,
            title = excluded.title,
            source_url = excluded.source_url,
            source_hash = excluded.source_hash,
            fetched_at = excluded.fetched_at,
            parse_status = excluded.parse_status,
            next_report_period = excluded.next_report_period,
            next_release_at = excluded.next_release_at,
            next_release_label = excluded.next_release_label
        """,
        (
            report["report_id"],
            report["report_month"],
            report["title"],
            report["source_url"],
            report["source_hash"],
            report["fetched_at"],
            report.get("parse_status", ""),
            report.get("next_report_period"),
            report.get("next_release_at"),
            report.get("next_release_label", ""),
        ),
    )
    con.execute(
        "delete from ism_report_comments where report_id = ?",
        (report["report_id"],),
    )
    for comment in comments:
        con.execute(
            """
            insert into ism_report_comments(
                report_id, comment_index, report_month, industry, comment_text,
                source_url, source_hash
            ) values (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                comment["report_id"],
                comment["comment_index"],
                comment["report_month"],
                comment["industry"],
                comment["comment_text"],
                comment["source_url"],
                comment["source_hash"],
            ),
        )
    con.commit()
    return {"reports": 1, "comments": len(comments)}


def load_existing_ism_report_months(con):
    rows = con.execute("select report_month from ism_report_snapshots").fetchall()
    return {row["report_month"] for row in rows}


def load_latest_ism_report_snapshot(con):
    rows = con.execute(
        """
        select report_id, report_month, title, source_url, source_hash, fetched_at,
               parse_status, next_report_period, next_release_at, next_release_label
        from ism_report_snapshots
        order by report_month desc
        limit 1
        """
    ).fetchall()
    return dict(rows[0]) if rows else None


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


def replace_ism_at_a_glance_rows(con, rows):
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


def replace_ism_report_source_snapshot(con, snapshot):
    con.execute(
        """
        insert into ism_report_source_snapshots(
            source_url, source_name, source_hash, fetched_at, raw_html,
            parse_status, parse_error, report_id, report_month
        ) values (?, ?, ?, ?, ?, ?, ?, ?, ?)
        on conflict(source_url) do update set
            source_name = excluded.source_name,
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
            snapshot["source_hash"],
            snapshot["fetched_at"],
            snapshot["raw_html"],
            snapshot["parse_status"],
            snapshot.get("parse_error"),
            snapshot.get("report_id"),
            snapshot.get("report_month"),
        ),
    )
    con.commit()
    return {"source_snapshots": 1}


def load_ism_report_source_snapshot(con, source_url):
    row = con.execute(
        """
        select source_url, source_name, source_hash, fetched_at, raw_html,
               parse_status, parse_error, report_id, report_month
        from ism_report_source_snapshots
        where source_url = ?
        """,
        (source_url,),
    ).fetchone()
    return dict(row) if row else None


def replace_ism_ai_extraction(con, extraction):
    import json

    from app.tools.ism_ai_extraction import validate_extraction

    payload = extraction["extraction_json"]
    report_id = extraction["report_id"]
    payload = validate_extraction(payload)
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
    con.commit()
    return {
        "ai_extractions": 1,
        "industry_signals": len(payload.get("industry_signals", [])),
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


def replace_ism_report_narrative_facts(con, payload, source):
    report = payload["report"]
    con.execute(
        "delete from ism_report_narrative_facts where report_id = ?",
        (report["report_id"],),
    )
    con.execute(
        """
        insert into ism_report_narrative_facts(
            report_id, report_month, facts_json, source_hash
        ) values (?, ?, ?, ?)
        """,
        (
            report["report_id"],
            report["report_month"],
            json.dumps(payload.get("narrative_facts", {}), sort_keys=True),
            source["source_hash"],
        ),
    )
    return {"narrative_facts": 1}


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

    payload = validate_extraction(payload)
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
    summary_saved = replace_ism_ai_summary(con, payload, source)
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

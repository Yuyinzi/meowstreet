import json

from app.db import growth_cycle, ism_surveys
from app.db import us_rates_liquidity as usrl
from app.tools.ism_services_ai_extraction import (
    ServicesFactualExtractionModel,
)


_OPERATIONAL_SERIES = frozenset(
    {
        "ism_services_pmi",
        "ism_services_business_activity",
        "ism_services_new_orders",
        "ism_services_order_backlog",
    }
)


def _services_metric_points(payload):
    report_month = payload["report"]["report_month"]
    points = {}
    for row in payload["at_a_glance_rows"]:
        if row["series_id"] in _OPERATIONAL_SERIES:
            points[row["series_id"]] = [
                {
                    "date": report_month,
                    "value": row["current_value"],
                    "source": "ISM AI extraction",
                }
            ]
    return points


def _replace_services_metrics(con, payload, commit=True):
    report_month = payload["report"]["report_month"]
    series_ids = sorted(_OPERATIONAL_SERIES)
    placeholders = ",".join("?" for _ in series_ids)
    con.execute(
        f"delete from macro_indicator_points where series_id in ({placeholders}) and date = ?",
        (*series_ids, report_month),
    )
    count = 0
    for series_id, points in _services_metric_points(payload).items():
        series = {
            "series_id": series_id,
            "title": series_id.replace("_", " ").title(),
            "units": "index",
            "source": "ISM AI extraction",
        }
        saved = usrl.merge_macro_indicator_points(con, series, points, commit=False)
        count += saved["points"]
    if commit:
        con.commit()
    return {"metrics": count}


def _services_at_a_glance_rows(payload, source_url, source_hash):
    report = payload["report"]
    return [
        {
            "report_id": report["report_id"],
            "report_month": report["report_month"],
            "series_id": row["series_id"],
            "label": row["label"],
            "current_value": row["current_value"],
            "previous_value": row["previous_value"],
            "point_change": row["point_change"],
            "direction": row["direction"],
            "rate_of_change": row["rate_of_change"],
            "trend_months": row["trend_months"],
            "source_url": source_url,
            "source_hash": source_hash,
        }
        for row in payload["at_a_glance_rows"]
    ]


def _services_comments(payload, source_url, source_hash):
    report = payload["report"]
    return [
        {
            "report_id": report["report_id"],
            "report_month": report["report_month"],
            "comment_index": index,
            "industry": comment["industry"],
            "comment_text": comment["comment_text"],
            "source_url": source_url,
            "source_hash": source_hash,
        }
        for index, comment in enumerate(payload.get("respondent_comments", []), start=1)
    ]


def _services_industry_signals(payload, source_url, source_hash):
    return [
        {
            "report_id": payload["report"]["report_id"],
            "report_month": payload["report"]["report_month"],
            "signal_type": signal["signal_type"],
            "direction": signal["direction"],
            "industry": signal["industry"],
            "rank": signal["rank"],
            "evidence_text": signal["source_excerpt"],
            "source_url": source_url,
            "source_hash": source_hash,
        }
        for signal in payload.get("industry_signals", [])
    ]


def _replace_services_rich_outputs(con, payload, source, commit=True):
    report = payload["report"]
    source_url = source["source_url"]
    source_hash = source["source_hash"]

    con.execute(
        "delete from ism_report_industry_signals where report_id = ?",
        (report["report_id"],),
    )
    for signal in _services_industry_signals(payload, source_url, source_hash):
        con.execute(
            """
            insert into ism_report_industry_signals(
                report_id, report_month, signal_type, direction, industry,
                rank, evidence_text, source_url, source_hash
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                signal["report_id"],
                signal["report_month"],
                signal["signal_type"],
                signal["direction"],
                signal["industry"],
                signal["rank"],
                signal["evidence_text"],
                signal["source_url"],
                signal["source_hash"],
            ),
        )

    con.execute(
        "delete from ism_report_commodities where report_id = ?",
        (report["report_id"],),
    )
    for commodity in payload.get("commodities", []):
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
                source_hash,
            ),
        )

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
            source_hash,
        ),
    )

    if commit:
        con.commit()
    return {
        "industry_signals": len(payload.get("industry_signals", [])),
        "commodities": len(payload.get("commodities", [])),
        "narrative_facts": 1,
    }


def _services_industry_rankings(payload):
    report_month = payload["report"]["report_month"]
    ranking_rows = []
    for signal in payload.get("industry_signals", []):
        if signal["signal_type"] == "overall_growth":
            ranking_rows.append(
                {
                    "date": report_month,
                    "industry": signal["industry"],
                    "direction": "growth",
                    "rank": signal["rank"],
                    "source": "ISM AI extraction",
                }
            )
        elif signal["signal_type"] == "overall_contraction":
            ranking_rows.append(
                {
                    "date": report_month,
                    "industry": signal["industry"],
                    "direction": "contraction",
                    "rank": signal["rank"],
                    "source": "ISM AI extraction",
                }
            )
    return ranking_rows


def _replace_services_rankings(con, payload, commit=True):
    report_month = payload["report"]["report_month"]
    con.execute(
        "delete from ism_industry_rankings where survey_type = 'services' and date = ?",
        (report_month,),
    )
    ranking_rows = _services_industry_rankings(payload)
    for row in ranking_rows:
        con.execute(
            "insert into ism_industry_rankings(survey_type, date, industry, direction, rank, source) "
            "values ('services', ?, ?, ?, ?, ?)",
            (
                row["date"],
                row["industry"],
                row["direction"],
                row["rank"],
                row["source"],
            ),
        )
    if commit:
        con.commit()
    return len(ranking_rows)


def _services_signal_coverage(payload, source_url, source_hash):
    report_id = payload["report"]["report_id"]
    report_month = payload["report"]["report_month"]
    return [
        {
            "report_id": report_id,
            "report_month": report_month,
            **coverage,
            "source_url": source_url,
            "source_hash": source_hash,
        }
        for coverage in payload.get("industry_signal_coverage", [])
    ]


def _replace_services_signal_coverage(con, payload, source):
    source_url = source["source_url"]
    source_hash = source["source_hash"]
    report_id = payload["report"]["report_id"]
    con.execute(
        "delete from ism_report_industry_signal_coverage where report_id = ?",
        (report_id,),
    )
    rows = _services_signal_coverage(payload, source_url, source_hash)
    for row in rows:
        con.execute(
            """
            insert into ism_report_industry_signal_coverage(
                report_id, report_month, signal_type, direction,
                list_present, declared_count, extracted_count,
                validation_status, evidence_text, source_url, source_hash
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["report_id"],
                row["report_month"],
                row["signal_type"],
                row["direction"],
                row["list_present"],
                row["declared_count"],
                row["extracted_count"],
                row["validation_status"],
                row["evidence_text"],
                row["source_url"],
                row["source_hash"],
            ),
        )
    return len(rows)


def promote_services_extraction(con, extraction, source):
    validated = ServicesFactualExtractionModel.model_validate(extraction)
    payload = validated.model_dump()
    report = payload["report"]
    source_url = source["source_url"]
    source_hash = source["source_hash"]

    with con:
        _replace_services_metrics(con, payload, commit=False)

        growth_cycle.replace_ism_at_a_glance_rows(
            con,
            _services_at_a_glance_rows(payload, source_url, source_hash),
            commit=False,
        )

        report_snapshot = {
            "report_id": report["report_id"],
            "report_month": report["report_month"],
            "title": report["title"],
            "source_url": source_url,
            "source_hash": source_hash,
            "fetched_at": source.get("updated_at", ""),
            "parse_status": "ok",
            "next_report_period": None,
            "next_release_at": None,
            "next_release_label": "",
        }
        comments = _services_comments(payload, source_url, source_hash)
        ism_surveys.replace_report_snapshot(
            con, "services", report_snapshot, comments, commit=False
        )

        _replace_services_rich_outputs(con, payload, source, commit=False)

        ranking_count = _replace_services_rankings(con, payload, commit=False)

        coverage_count = _replace_services_signal_coverage(con, payload, source)

        con.execute(
            """
            update ism_report_source_snapshots
            set parse_status = 'ok', report_id = ?, report_month = ?
            where source_url = ?
            """,
            (report["report_id"], report["report_month"], source_url),
        )

    return {
        "report_id": report["report_id"],
        "metrics": 4,
        "at_a_glance_rows": len(payload["at_a_glance_rows"]),
        "comments": len(comments),
        "industry_signals": len(payload.get("industry_signals", [])),
        "commodities": len(payload.get("commodities", [])),
        "narrative_facts": 1,
        "rankings": ranking_count,
        "signal_coverage": coverage_count,
    }

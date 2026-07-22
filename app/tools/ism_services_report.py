import hashlib
import re

from app.tools.ism_official_report import (
    IsmReportUnavailable,
    extract_report_text,
    normalize_text,
    parse_next_release,
    split_industries,
)
from app.tools import ism_services_industry


MONTHS = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]

METRIC_PATTERNS = {
    "ism_services_pmi": r"Services PMI(?:®)?(?:\s+Report)?\s+(?:registered|at)\s+(\d+(?:\.\d+)?)\s+percent",
    "ism_services_business_activity": r"Business Activity Index(?:\s+at|.*?to)\s+(\d+(?:\.\d+)?)\s+percent",
    "ism_services_new_orders": r"New Orders Index(?:\s+registered|.*?to)\s+(\d+(?:\.\d+)?)\s+percent",
    "ism_services_order_backlog": r"Backlog of Orders Index(?:\s+registered|.*?to)\s+(\d+(?:\.\d+)?)\s+percent",
}

_REQUIRED_METRICS = {
    "ism_services_pmi",
    "ism_services_business_activity",
    "ism_services_new_orders",
}


def report_month_from_title(text):
    match = re.search(
        r"\b(" + "|".join(MONTHS) + r")\s+(\d{4})\s+ISM Services",
        text,
    )
    if not match:
        raise IsmReportUnavailable("no report page available")
    month_name, year = match.groups()
    month_num = f"{MONTHS.index(month_name) + 1:02d}"
    return f"{year}-{month_num}-01", month_name, year


def report_id(report_month):
    year, month, _day = report_month.split("-")
    return f"ism_services_{year}_{month}"


def clean_title(month_name, year):
    return f"{month_name} {year} ISM Services PMI Report"


def parse_metrics(text):
    metrics = {}
    for series_id, pattern in METRIC_PATTERNS.items():
        match = re.search(pattern, text)
        if match:
            metrics[series_id] = float(match.group(1))
    missing = [s for s in _REQUIRED_METRICS if s not in metrics]
    if missing:
        raise ValueError(
            f"ism services report required metrics are missing: {', '.join(sorted(set(missing)))}"
        )
    return metrics


def ranking_rows(report_month, industries, direction):
    if direction == "growth":
        return [
            {
                "date": report_month,
                "industry": industry,
                "direction": direction,
                "rank": index + 1,
                "source": "ISM official report",
            }
            for index, industry in enumerate(industries)
        ]
    return [
        {
            "date": report_month,
            "industry": industry,
            "direction": direction,
            "rank": -index - 1,
            "source": "ISM official report",
        }
        for index, industry in enumerate(industries)
    ]


def parse_rankings(text, report_month):
    growth_match = re.search(
        r"The\s+\d+\s+services industries reporting growth.*?are:\s+(.*?)\.",
        text,
    )
    contraction_match = re.search(
        r"The\s+\w+\s+(?:services\s+)?industr(?:y|ies)(?:\s+in contraction|\s+reporting contraction(?:\s+in\s+[A-Za-z]+)?)\s+(?:is|are):?\s+(.*?)\.",
        text,
    )
    rows = []
    if growth_match:
        growth_industries = [
            ism_services_industry.normalize_industry(name)
            for name in split_industries(growth_match.group(1))
        ]
        rows.extend(ranking_rows(report_month, growth_industries, "growth"))
    if contraction_match:
        contraction_industries = [
            ism_services_industry.normalize_industry(name)
            for name in split_industries(contraction_match.group(1))
        ]
        rows.extend(ranking_rows(report_month, contraction_industries, "contraction"))
    return rows


def clean_comment_text(value):
    stripped = value.strip()
    stripped = stripped.strip('“”" ')
    return normalize_text(stripped)


def parse_comments(text, report, source_url):
    section_match = re.search(r"WHAT RESPONDENTS ARE SAYING\s+(.*)", text)
    if not section_match:
        return []
    comments = []
    for index, match in enumerate(
        re.finditer(r"[“\"]([^”\"]+)[”\"]\s+\[([^\]]+)\]", section_match.group(1)),
        start=1,
    ):
        industry = ism_services_industry.normalize_industry(match.group(2).strip())
        comments.append(
            {
                "report_id": report["report_id"],
                "report_month": report["report_month"],
                "industry": industry,
                "comment_index": index,
                "comment_text": clean_comment_text(match.group(1)),
                "source_url": source_url,
                "source_hash": report["source_hash"],
                "source": "ISM official report",
            }
        )
    return comments


def prepare_report(html, source_url, fetched_at):
    return parse_report(html, source_url, fetched_at, "ismworld")


def _require_services_identity(text):
    lower = text.lower()
    if "services pmi" not in lower:
        raise ValueError(
            "ism report survey mismatch: expected services, "
            "document lacks Services PMI marker"
        )


def prepare_report_for_ai(html, source_url, fetched_at, source_name="ismworld"):
    source_text = extract_report_text(html, source_name)
    _require_services_identity(source_text)
    report_month, _month_name, _year = report_month_from_title(source_text)
    return {
        "report_id": report_id(report_month),
        "report_month": report_month,
        "source_url": source_url,
        "source_name": source_name,
        "fetched_at": fetched_at,
        "source_text": source_text,
    }


def _extract_at_a_glance_region(source_text):
    match = re.search(
        r"SERVICES AT A GLANCE\s*(.*?)(?=\n\s*\n|INDUSTRY PERFORMANCE|WHAT RESPONDENTS|COMMODITIES REPORTED|$)",
        source_text,
        re.I | re.S,
    )
    if not match:
        raise ValueError("ism services at a glance region not found")
    return match.group(1).strip()


def _extract_industry_signals_region(source_text):
    match = re.search(
        r"INDUSTRY PERFORMANCE\s*(.*?)(?=\n\s*\n|WHAT RESPONDENTS|COMMODITIES REPORTED|$)",
        source_text,
        re.I | re.S,
    )
    if not match:
        raise ValueError("ism services industry signals region not found")
    return match.group(1).strip()


def _extract_comments_commodities_region(source_text):
    match = re.search(
        r"WHAT RESPONDENTS ARE SAYING\s*(.*?)(?=\n\s*\n|INDUSTRY PERFORMANCE|COMMODITIES REPORTED|SERVICES AT A GLANCE|$)",
        source_text,
        re.I | re.S,
    )
    comments_part = match.group(1).strip() if match else ""
    commodities_match = re.search(
        r"COMMODITIES REPORTED\s*(.*?)(?=\n\s*\n|The next ISM|Tempe|$)",
        source_text,
        re.I | re.S,
    )
    commodities_part = commodities_match.group(1).strip() if commodities_match else ""
    if not comments_part and not commodities_part:
        raise ValueError("ism services comments or commodities region not found")
    parts = [p for p in [comments_part, commodities_part] if p]
    return "\n\n".join(parts)


def _extract_narrative_region(source_text):
    after = source_text
    after = re.split(r"(?i)\b(?:The next ISM|About This Report)\b", after, maxsplit=1)[
        0
    ]
    commodity_marker = re.search(r"COMMODITIES REPORTED", after, re.I)
    if commodity_marker:
        after = after[commodity_marker.end() :]
    after = after.strip()
    if not after:
        raise ValueError("ism services narrative region not found")
    return after


def parse_report(html, source_url, fetched_at, source_name="ismworld"):
    text = extract_report_text(html, source_name)
    normalized = normalize_text(text)
    lower_text = normalized.lower()
    if "services pmi" not in lower_text:
        raise ValueError(
            "ism report survey mismatch: expected services, "
            "document lacks Services PMI marker"
        )
    source_hash = hashlib.sha256(html.encode("utf-8")).hexdigest()
    report_month, month_name, year = report_month_from_title(normalized)
    next_report_period, next_release_at, next_release_label = parse_next_release(
        normalized
    )
    report = {
        "report_id": report_id(report_month),
        "report_month": report_month,
        "title": clean_title(month_name, year),
        "source_url": source_url,
        "source_hash": source_hash,
        "source_name": source_name,
        "fetched_at": fetched_at,
        "parse_status": "ok",
        "next_report_period": next_report_period,
        "next_release_at": next_release_at,
        "next_release_label": next_release_label,
    }
    return {
        "survey_type": "services",
        "report": report,
        "metrics": parse_metrics(normalized),
        "rankings": parse_rankings(normalized, report_month),
        "comments": parse_comments(normalized, report, source_url),
    }

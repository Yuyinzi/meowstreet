import hashlib
import re
from html.parser import HTMLParser

from app.tools.ism_official_report import (
    IsmReportUnavailable,
    extract_report_text as extract_shared_report_text,
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


class ServicesArticleTextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self._active = False
        self._div_depth = 0
        self._skip_depth = 0
        self.found = False

    def handle_starttag(self, tag, attrs):
        classes = dict(attrs).get("class", "").split()
        if not self._active:
            if tag == "div" and "richText__content" in classes:
                self._active = True
                self._div_depth = 1
                self.found = True
            return
        if tag == "div":
            self._div_depth += 1
        if tag in ("script", "style"):
            self._skip_depth += 1

    def handle_endtag(self, tag):
        if not self._active:
            return
        if tag in ("script", "style") and self._skip_depth:
            self._skip_depth -= 1
        if tag == "div":
            self._div_depth -= 1
            if self._div_depth == 0:
                self._active = False

    def handle_data(self, data):
        if not self._active or self._skip_depth:
            return
        text = data.strip()
        if text:
            self.parts.append(text)


def extract_report_text(html, source_name):
    if source_name == "ismworld":
        parser = ServicesArticleTextExtractor()
        parser.feed(html)
        if parser.found and parser.parts:
            return "\n".join(parser.parts)
    return extract_shared_report_text(html, source_name)


_ISM_SVC = r"ISM\s*(?:®\s*)?Services(?:\s+PMI)?\s*(?:®)?"


def report_month_from_title(text):
    month_year = r"(" + "|".join(MONTHS) + r")\s+(\d{4})"
    patterns = [
        month_year + r"\s+" + _ISM_SVC,
        _ISM_SVC + r"\s+Report for\s+" + month_year,
        month_year + r"\s+Services\s+ISM\s*(?:®)?\s+Report On Business",
    ]
    match = next(
        (candidate for pattern in patterns if (candidate := re.search(pattern, text))),
        None,
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


_TITLE_RE = re.compile(r"[A-Z][a-z]+ \d{4} ISM\s*(?:®\s*)?Services", re.I)
_AT_A_GLANCE_RE = re.compile(
    r"(?:ISM\s*(?:®\s*)?)?SERVICES"
    r"(?:\s+SURVEY\s+RESULTS)?\s+AT A GLANCE",
    re.I,
)
_INDUSTRY_PERFORMANCE_RE = re.compile(
    r"^[ \t]*INDUSTRY PERFORMANCE[ \t]*$", re.I | re.M
)
_RESPONDENTS_RE = re.compile(r"^[ \t]*WHAT RESPONDENTS ARE SAYING[ \t]*$", re.I | re.M)
_COMMODITIES_RE = re.compile(
    r"^[ \t]*COMMODITIES REPORTED(?: UP/DOWN IN PRICE, AND IN SHORT SUPPLY)?[ \t]*$",
    re.I | re.M,
)
_INDEX_SUMMARIES_RE = re.compile(
    r"^[ \t]*[A-Z]+(?:[ \t]+|\r?\n[ \t]*)"
    r"\d{4}(?:[ \t]+|\r?\n[ \t]*)"
    r"SERVICES INDEX SUMMARIES[ \t]*$",
    re.I | re.M,
)

_SERVICES_COMPONENT_NAMES = [
    "Business Activity",
    "New Orders",
    "Employment",
    "Supplier Deliveries",
    "Inventories",
    "Inventory Sentiment",
    "Prices",
    "Backlog of Orders",
    "New Export Orders",
    "Imports",
]

_SERVICES_COMPONENT_HEADING_RE = re.compile(
    r"^(?:" + "|".join(_SERVICES_COMPONENT_NAMES) + r")(?:\s+Index)?$", re.I
)
_INDUSTRY_LIST_LINE_RE = re.compile(
    r"\bindustr(?:y|ies)\s+(?:reporting|reported)\b", re.I
)


def _first_marker(source_text, patterns, start):
    matches = [pattern.search(source_text, start) for pattern in patterns]
    present = [match for match in matches if match is not None]
    return min(present, key=lambda match: match.start()) if present else None


def _extract_at_a_glance_region(source_text):
    match = _AT_A_GLANCE_RE.search(source_text)
    if match:
        end_m = _first_marker(
            source_text,
            [_COMMODITIES_RE, _INDUSTRY_PERFORMANCE_RE, _RESPONDENTS_RE],
            match.end(),
        )
        end = end_m.start() if end_m else len(source_text)
        region = source_text[match.end() : end].strip()
        if region:
            return region
    end_m = _INDUSTRY_PERFORMANCE_RE.search(source_text)
    if not end_m:
        raise ValueError("ism services at a glance region not found")
    region = source_text[: end_m.start()].strip()
    if not region:
        raise ValueError("ism services at a glance region not found")
    return region


def _extract_component_industry_lists(source_text):
    match = _INDEX_SUMMARIES_RE.search(source_text)
    if not match:
        return ""
    lines = source_text[match.end() :].split("\n")
    result = []
    heading = None
    for line in lines:
        s = line.strip()
        if not s:
            continue
        heading_match = _SERVICES_COMPONENT_HEADING_RE.match(s)
        if heading_match:
            heading = s
            continue
        if _INDUSTRY_LIST_LINE_RE.search(s) and ":" in s:
            if heading is not None:
                result.append(heading)
                heading = None
            result.append(s)
    return "\n".join(result)


def _extract_industry_signals_region(source_text):
    match = _INDUSTRY_PERFORMANCE_RE.search(source_text)
    if not match:
        raise ValueError("ism services industry signals region not found")
    end_m = _first_marker(
        source_text, [_RESPONDENTS_RE, _AT_A_GLANCE_RE, _COMMODITIES_RE], match.end()
    )
    end = end_m.start() if end_m else len(source_text)
    region = source_text[match.end() : end].strip()
    component_part = _extract_component_industry_lists(source_text)
    if component_part:
        region += "\n\n" + component_part
    return region


def _extract_comments_commodities_region(source_text):
    match = _RESPONDENTS_RE.search(source_text)
    comments_part = ""
    if match:
        comments_end_m = _first_marker(
            source_text, [_AT_A_GLANCE_RE, _COMMODITIES_RE], match.end()
        )
        comments_end = comments_end_m.start() if comments_end_m else len(source_text)
        comments_part = source_text[match.end() : comments_end].strip()
    commodities_match = _COMMODITIES_RE.search(source_text)
    commodities_part = ""
    if commodities_match:
        commodities_end_m = _INDEX_SUMMARIES_RE.search(
            source_text, commodities_match.end()
        )
        commodities_end = (
            commodities_end_m.start() if commodities_end_m else len(source_text)
        )
        commodities_part = source_text[
            commodities_match.end() : commodities_end
        ].strip()
    if not comments_part and not commodities_part:
        raise ValueError("ism services comments or commodities region not found")
    parts = [p for p in [comments_part, commodities_part] if p]
    return "\n\n".join(parts)


def _extract_narrative_region(source_text):
    end_m = _first_marker(source_text, [_AT_A_GLANCE_RE, _INDUSTRY_PERFORMANCE_RE], 0)
    end = end_m.start() if end_m else len(source_text)
    narrative = source_text[:end].strip()
    if not narrative:
        raise ValueError("ism services narrative region not found")
    return narrative


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

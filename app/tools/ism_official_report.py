import hashlib
import re
from datetime import datetime
from html.parser import HTMLParser


MONTHS = {
    "January": "01",
    "February": "02",
    "March": "03",
    "April": "04",
    "May": "05",
    "June": "06",
    "July": "07",
    "August": "08",
    "September": "09",
    "October": "10",
    "November": "11",
    "December": "12",
}

METRIC_LABELS = {
    "Manufacturing PMI": "ism_manufacturing_pmi",
    "New Orders": "ism_manufacturing_new_orders",
    "Production": "ism_manufacturing_production",
    "Employment": "ism_manufacturing_employment",
    "Supplier Deliveries": "ism_manufacturing_supplier_deliveries",
    "Inventories": "ism_manufacturing_inventories",
    "Customers' Inventories": "ism_manufacturing_customer_inventories",
    "Customers’ Inventories": "ism_manufacturing_customer_inventories",
    "Prices": "ism_manufacturing_prices",
    "Backlog of Orders": "ism_manufacturing_order_backlog",
    "New Export Orders": "ism_manufacturing_exports",
    "Imports": "ism_manufacturing_imports",
}

ET_OFFSETS = {
    "January": "-05:00",
    "February": "-05:00",
    "March": "-04:00",
    "April": "-04:00",
    "May": "-04:00",
    "June": "-04:00",
    "July": "-04:00",
    "August": "-04:00",
    "September": "-04:00",
    "October": "-04:00",
    "November": "-05:00",
    "December": "-05:00",
}


class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        text = data.strip()
        if text:
            self.parts.append(text)


def html_to_text(html):
    parser = TextExtractor()
    parser.feed(html)
    return "\n".join(parser.parts)


def normalize_text(text):
    return re.sub(r"\s+", " ", text).strip()


def report_month_from_title(text):
    match = re.search(r"\b(" + "|".join(MONTHS) + r")\s+(\d{4})\s+ISM", text)
    if not match:
        raise ValueError("ism report month is missing")
    month_name, year = match.groups()
    return f"{year}-{MONTHS[month_name]}-01", month_name, year


def report_id(report_month):
    year, month, _day = report_month.split("-")
    return f"ism_manufacturing_{year}_{month}"


def clean_title(month_name, year):
    return f"{month_name} {year} ISM Manufacturing PMI Report"


def parse_metrics(text):
    metrics = {}
    for label, series_id in METRIC_LABELS.items():
        pattern = rf"{re.escape(label)}(?:\s?®\s?)?\s+(\d+(?:\.\d+)?)\s+"
        match = re.search(pattern, text)
        if match:
            metrics[series_id] = float(match.group(1))
    missing = [
        series_id for series_id in METRIC_LABELS.values() if series_id not in metrics
    ]
    if missing:
        raise ValueError(
            f"ism report metrics are missing: {', '.join(sorted(set(missing)))}"
        )
    return metrics


def split_industries(value):
    cleaned = value.replace("; and ", "; ").replace(";and ", "; ")
    cleaned = cleaned.replace(" and ", "; ")
    return [item.strip(" .") for item in cleaned.split(";") if item.strip(" .")]


def ranking_rows(report_month, industries, direction):
    if direction == "growth":
        total = len(industries)
        return [
            {
                "date": report_month,
                "industry": industry,
                "direction": direction,
                "rank": total - index,
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
        r"The\s+\d+\s+manufacturing industries reporting growth.*?are:\s+(.*?)\.",
        text,
    )
    contraction_match = re.search(
        r"The\s+\w+\s+industries in contraction are:\s+(.*?)\.",
        text,
    )
    if not growth_match or not contraction_match:
        raise ValueError("ism report overall industry rankings are missing")
    rows = []
    rows.extend(
        ranking_rows(report_month, split_industries(growth_match.group(1)), "growth")
    )
    rows.extend(
        ranking_rows(
            report_month,
            split_industries(contraction_match.group(1)),
            "contraction",
        )
    )
    return rows


def clean_comment_text(value):
    stripped = value.strip()
    stripped = stripped.strip('“”" ')
    return normalize_text(stripped)


def parse_comments(text, report, source_url):
    section_match = re.search(
        r"WHAT RESPONDENTS ARE SAYING\s+(.*?)\s+MANUFACTURING AT A GLANCE",
        text,
    )
    if not section_match:
        return []
    comments = []
    for index, match in enumerate(
        re.finditer(r"“([^”]+)”\s+\[([^\]]+)\]", section_match.group(1)),
        start=1,
    ):
        comments.append(
            {
                "report_id": report["report_id"],
                "report_month": report["report_month"],
                "industry": match.group(2).strip(),
                "comment_index": index,
                "comment_text": clean_comment_text(match.group(1)),
                "source_url": source_url,
                "source_hash": report["source_hash"],
            }
        )
    return comments


def parse_next_release(text):
    match = re.search(
        r"The next ISM\s?® Manufacturing PMI\s?® Report featuring ([A-Za-z]+) (\d{4}) data will be released at 10:00 a\.m\. ET on ([A-Za-z]+, [A-Za-z]+ \d{1,2}, \d{4})\.",
        text,
    )
    if not match:
        return None, None, ""
    period_month, period_year, release_label_date = match.groups()
    release_dt = datetime.strptime(release_label_date, "%A, %B %d, %Y")
    offset = ET_OFFSETS[release_dt.strftime("%B")]
    next_report_period = f"{period_year}-{MONTHS[period_month]}-01"
    next_release_at = f"{release_dt.date().isoformat()}T10:00:00{offset}"
    return (
        next_report_period,
        next_release_at,
        f"{release_label_date} at 10:00 a.m. ET",
    )


def parse_at_a_glance_rows(text, report, source_url):
    rows = []
    found_series = set()
    for label, series_id in METRIC_LABELS.items():
        pattern = rf"{re.escape(label)}(?:\s?®\s?)?\s+(\d+(?:\.\d+)?)\s+(\d+(?:\.\d+)?)\s+([+-]?\d+(?:\.\d+)?)\s+([A-Za-z’' ]+?)\s+([A-Za-z’' ]+?)\s+(\d+)"
        match = re.search(pattern, text)
        if match:
            current, previous, change, direction, rate, months = match.groups()
            if series_id not in found_series:
                found_series.add(series_id)
                rows.append(
                    {
                        "report_id": report["report_id"],
                        "report_month": report["report_month"],
                        "series_id": series_id,
                        "label": label,
                        "current_value": float(current),
                        "previous_value": float(previous),
                        "point_change": float(change.replace("+", "")),
                        "direction": direction.strip(),
                        "rate_of_change": rate.strip(),
                        "trend_months": int(months),
                        "source_url": source_url,
                        "source_hash": report["source_hash"],
                    }
                )
    missing = sorted(set(METRIC_LABELS.values()) - found_series)
    if missing:
        raise ValueError(
            f"ism at-a-glance rows are missing: {', '.join(sorted(set(missing)))}"
        )
    return rows


def parse_report(html, source_url, fetched_at):
    text = html_to_text(html)
    normalized = normalize_text(text)
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
        "fetched_at": fetched_at,
        "parse_status": "ok",
        "next_report_period": next_report_period,
        "next_release_at": next_release_at,
        "next_release_label": next_release_label,
    }
    return {
        "report": report,
        "metrics": parse_metrics(normalized),
        "rankings": parse_rankings(normalized, report_month),
        "comments": parse_comments(normalized, report, source_url),
        "at_a_glance_rows": parse_at_a_glance_rows(normalized, report, source_url),
    }

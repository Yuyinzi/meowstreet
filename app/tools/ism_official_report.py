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

AT_A_GLANCE_RATE_LABELS = (
    "From Contracting",
    "From Growing",
    "Faster",
    "Slower",
    "Same",
    "Unchanged",
)

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


class IsmReportUnavailable(ValueError):
    pass


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


def extract_prnewswire_article_text(html):
    match = re.search(r"<article\b.*?</article>", html, flags=re.I | re.S)
    if match:
        return html_to_text(match.group(0))
    return html_to_text(html)


def extract_report_text(html, source_name):
    if source_name == "prnewswire":
        return extract_prnewswire_article_text(html)
    return html_to_text(html)


def report_month_from_title(text):
    match = re.search(
        r"\b(" + "|".join(MONTHS) + r")\s+(\d{4})\s+(?:Manufacturing\s+)?ISM",
        text,
    )
    if not match:
        raise IsmReportUnavailable("no report page available")
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
        r"The\s+\w+\s+(?:manufacturing\s+)?industr(?:y|ies)(?:\s+in contraction|\s+reporting contraction(?:\s+in\s+[A-Za-z]+)?)\s+(?:is|are):?\s+(.*?)\.",
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
        re.finditer(r"[“\"]([^”\"]+)[”\"]\s+\[([^\]]+)\]", section_match.group(1)),
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


def split_at_a_glance_direction_rate(value):
    for rate in AT_A_GLANCE_RATE_LABELS:
        suffix = f" {rate}"
        if value.endswith(suffix):
            direction = value[: -len(suffix)].strip()
            if direction:
                return direction, rate
    raise ValueError(f"ism at-a-glance direction/rate is unknown: {value}")


NUMBER_RE = re.compile(r"^[+-]?\d+(?:\.\d+)?$")


def _find_label_index(tokens, label):
    words = label.replace("’", "'").split()
    normalized_tokens = [token.replace("’", "'") for token in tokens]
    for index in range(0, len(normalized_tokens) - len(words) + 1):
        if normalized_tokens[index : index + len(words)] == words:
            return index
    return None


def _parse_at_a_glance_row_from_tokens(tokens, label, report, source_url, source_hash):
    index = _find_label_index(tokens, label)
    if index is None:
        return None
    start = index + len(label.split())
    values = tokens[start:]
    numeric_positions = [
        idx for idx, value in enumerate(values) if NUMBER_RE.match(value)
    ]
    if len(numeric_positions) < 4:
        return None
    current_pos, previous_pos, change_pos, months_pos = numeric_positions[:4]
    direction_rate = " ".join(values[change_pos + 1 : months_pos])
    direction, rate = split_at_a_glance_direction_rate(direction_rate)
    return {
        "current_value": float(values[current_pos]),
        "previous_value": float(values[previous_pos]),
        "point_change": float(values[change_pos].replace("+", "")),
        "direction": direction,
        "rate_of_change": rate,
        "trend_months": int(values[months_pos]),
        "source_url": source_url,
        "source_hash": source_hash,
        "report_id": report["report_id"],
        "report_month": report["report_month"],
        "label": label,
    }


def parse_at_a_glance_rows(text, report, source_url):
    rows = []
    found_series = set()
    for label, series_id in METRIC_LABELS.items():
        pattern = rf"{re.escape(label)}(?:\s?®\s?)?\s+(\d+(?:\.\d+)?)\s+(\d+(?:\.\d+)?)\s+([+-]?\d+(?:\.\d+)?)\s+([A-Za-z’' ]+?)\s+(\d+)"
        match = re.search(pattern, text)
        if match:
            current, previous, change, direction_rate, months = match.groups()
            direction, rate = split_at_a_glance_direction_rate(direction_rate.strip())
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
    section_match = re.search(
        r"MANUFACTURING AT A GLANCE\s+(.*?)(?:OVERALL ECONOMY|COMMODITIES REPORTED|MANUFACTURING INDEX SUMMARIES|The next ISM|$)",
        text,
    )
    section_tokens = section_match.group(1).split() if section_match else []
    missing = sorted(set(METRIC_LABELS.values()) - found_series)
    for series_id in missing:
        label = next(k for k, v in METRIC_LABELS.items() if v == series_id)
        fallback = _parse_at_a_glance_row_from_tokens(
            section_tokens,
            label,
            report,
            source_url,
            report["source_hash"],
        )
        if fallback:
            fallback["series_id"] = series_id
            rows.append(fallback)
            found_series.add(series_id)
    missing = sorted(set(METRIC_LABELS.values()) - found_series)
    if missing:
        raise ValueError(
            f"ism at-a-glance rows are missing: {', '.join(sorted(set(missing)))}"
        )
    return rows


def prepare_report_for_ai(html, source_url, fetched_at, source_name="ismworld"):
    report_text = extract_report_text(html, source_name)
    report_month, month_name, year = report_month_from_title(report_text)
    if "Manufacturing PMI" not in report_text:
        raise ValueError("ism report is not a manufacturing pmi report")
    report_text = re.split(
        r"(?i)\b(?:About This Report|Buying Policy)\b",
        report_text,
        maxsplit=1,
    )[0]
    cleaned = re.sub(r"\s+", " ", report_text).strip()
    cleaned = re.sub(r"(?i)PR Newswire legal boilerplate.*$", "", cleaned).strip()
    return {
        "report_id": report_id(report_month),
        "report_month": report_month,
        "month_name": month_name,
        "year": year,
        "source_url": source_url,
        "source_name": source_name,
        "fetched_at": fetched_at,
        "report_text": cleaned,
    }


def parse_report(html, source_url, fetched_at, source_name="ismworld"):
    text = extract_report_text(html, source_name)
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
        "source_name": source_name,
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

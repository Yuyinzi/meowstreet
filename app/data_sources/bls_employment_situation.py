import hashlib
import io
import re
from datetime import date
from datetime import datetime
from datetime import timezone

from pypdf import PdfReader

_MONTH_NAMES = (
    "January|February|March|April|May|June|July|August|September|"
    "October|November|December"
)
_MONTH_NAME_PATTERN = f"(?:{_MONTH_NAMES})"
_MONTHS = {
    "january": 1,
    "jan": 1,
    "february": 2,
    "feb": 2,
    "march": 3,
    "mar": 3,
    "april": 4,
    "apr": 4,
    "may": 5,
    "june": 6,
    "jun": 6,
    "july": 7,
    "jul": 7,
    "august": 8,
    "aug": 8,
    "september": 9,
    "sep": 9,
    "october": 10,
    "oct": 10,
    "november": 11,
    "nov": 11,
    "december": 12,
    "dec": 12,
}
_METRIC_LABELS = [
    ("nonfarm payroll", "nonfarm_payrolls"),
    ("3-month", "payrolls_3m_average"),
    ("unemployment rate", "unemployment_rate"),
    ("average weekly hours", "average_weekly_hours"),
    ("average hourly earnings", "average_hourly_earnings"),
]
_RELEASE_DATE_RE = re.compile(
    rf"FOR RELEASE[^\n]*?({_MONTH_NAME_PATTERN} \d{{1,2}}, \d{{4}})", re.IGNORECASE
)
_REFERENCE_MONTH_RE = re.compile(
    rf"EMPLOYMENT SITUATION[^\n]*?({_MONTH_NAME_PATTERN}) (\d{{4}})", re.IGNORECASE
)
_MONTH_COL_RE = re.compile(r"([A-Za-z][a-z]{2,8})\.? (\d{4})")
_REVISION_RE = re.compile(
    rf"({_MONTH_NAME_PATTERN}) (\d{{4}})[\s\S]*?revised\s+from ([\d,]+(?:\.[\d]+)?) "
    r"to ([\d,]+(?:\.[\d]+)?)",
    re.IGNORECASE,
)
_NEXT_EVENT_RE = re.compile(
    rf"scheduled[\s\S]*?({_MONTH_NAME_PATTERN} \d{{1,2}}, \d{{4}}) at "
    r"(\d{1,2}):(\d{2})",
    re.IGNORECASE,
)


def parse_employment_situation_release(pdf_bytes, source_url):
    text = _extract_pdf_text(pdf_bytes)
    source_hash = hashlib.sha256(pdf_bytes).hexdigest()
    return parse_employment_situation_text(text, source_url, source_hash)


def parse_employment_situation_text(text, source_url, source_hash):
    release_date = _extract_release_date(text)
    reference_period = _extract_reference_month(text)
    columns = _table_columns(text)
    if columns[-1] != reference_period:
        raise ValueError(
            f"employment situation newest column {columns[-1]} does not match "
            f"reference month {reference_period}"
        )
    metric_values = _metric_rows(text, columns)
    observations = []
    for series_id, value in metric_values.items():
        observations.append(
            _observation(
                series_id,
                reference_period,
                release_date,
                value,
                None,
                0,
                source_url,
                source_hash,
            )
        )
    observations.extend(
        _revision_observations(text, release_date, source_url, source_hash)
    )
    return {
        "source_url": source_url,
        "release_date": release_date,
        "reference_period": reference_period,
        "observations": observations,
        "scheduled_events": [_next_event(text, source_url)],
    }


def _extract_pdf_text(pdf_bytes):
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    except Exception as exc:
        raise ValueError("employment situation pdf could not be read") from exc


def _extract_release_date(text):
    match = _RELEASE_DATE_RE.search(text)
    if not match:
        raise ValueError("employment situation pdf is missing release date")
    return _parse_month_day_year(match.group(1)).isoformat()


def _extract_reference_month(text):
    match = _REFERENCE_MONTH_RE.search(text)
    if not match:
        raise ValueError("employment situation pdf is missing reference month")
    return f"{match.group(2)}-{_month_number(match.group(1)):02d}"


def _table_columns(text):
    for line in text.splitlines():
        stripped = line.strip()
        if _is_month_header_line(stripped):
            return [
                _month_period(month, year)
                for month, year in _MONTH_COL_RE.findall(stripped)
            ]
    raise ValueError("employment situation pdf has no month column header")


def _is_month_header_line(stripped):
    tokens = _MONTH_COL_RE.findall(stripped)
    if len(tokens) < 2:
        return False
    remaining = _MONTH_COL_RE.sub("", stripped).replace(".", "").replace(" ", "")
    return not remaining


def _month_period(month, year):
    return f"{year}-{_month_number(month):02d}"


def _month_number(month):
    number = _MONTHS.get(month.lower().rstrip("."))
    if number is None:
        raise ValueError(f"employment situation has unknown month {month!r}")
    return number


def _metric_rows(text, columns):
    column_count = len(columns)
    in_table = False
    rows = {}
    for line in text.splitlines():
        stripped = line.strip()
        if in_table and not stripped:
            in_table = False
            continue
        if not in_table:
            if _is_month_header_line(stripped):
                in_table = True
            continue
        lower = stripped.lower()
        if "revised" in lower:
            continue
        for label, series_id in _METRIC_LABELS:
            if label in lower and series_id not in rows:
                numbers = _numbers_after(label, stripped)
                if len(numbers) != column_count:
                    raise ValueError(
                        f"employment situation {series_id} row has "
                        f"{len(numbers)} values for {column_count} columns"
                    )
                rows[series_id] = numbers[-1]
                break
    missing = [
        series_id for _label, series_id in _METRIC_LABELS if series_id not in rows
    ]
    if missing:
        raise ValueError(f"employment situation pdf is missing {', '.join(missing)}")
    return rows


def _numbers_after(label, stripped):
    index = stripped.lower().find(label)
    tail = stripped[index + len(label) :]
    return [_parse_number(token) for token in re.findall(r"[\d,]+(?:\.[\d]+)?", tail)]


def _revision_observations(text, release_date, source_url, source_hash):
    observations = []
    seen = set()
    for paragraph in _paragraphs(text):
        if "revised" not in paragraph.lower():
            continue
        for match in _REVISION_RE.finditer(paragraph):
            month = match.group(1)
            year = match.group(2)
            reference_period = f"{year}-{_month_number(month):02d}"
            if reference_period in seen:
                continue
            seen.add(reference_period)
            observations.append(
                _observation(
                    "nonfarm_payrolls",
                    reference_period,
                    release_date,
                    _parse_number(match.group(3)),
                    _parse_number(match.group(4)),
                    1,
                    source_url,
                    source_hash,
                )
            )
    return observations


def _paragraphs(text):
    return [
        paragraph.strip()
        for paragraph in re.split(r"\n\s*\n", text)
        if paragraph.strip()
    ]


def _next_event(text, source_url):
    match = _NEXT_EVENT_RE.search(text)
    if not match:
        raise ValueError("employment situation pdf is missing next release event")
    event_date = _parse_month_day_year(match.group(1))
    hour = int(match.group(2))
    minute = int(match.group(3))
    return {
        "event_id": "bls_employment_situation",
        "scheduled_at": f"{event_date.isoformat()}T{hour:02d}:{minute:02d}:00",
        "status": "upcoming",
        "timezone": "ET",
        "source_url": source_url,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
    }


def _parse_month_day_year(value):
    match = re.fullmatch(
        rf"({_MONTH_NAME_PATTERN}) (\d{{1,2}}), (\d{{4}})",
        str(value).strip(),
        re.IGNORECASE,
    )
    if not match:
        raise ValueError(f"employment situation has invalid date {value!r}")
    month_number = _month_number(match.group(1))
    return date(int(match.group(3)), month_number, int(match.group(2)))


def _observation(
    series_id,
    reference_period,
    release_date,
    value,
    latest_revised_value,
    revision_number,
    source_url,
    source_hash,
):
    return {
        "series_id": series_id,
        "reference_period": reference_period,
        "release_date": release_date,
        "as_of_timestamp": datetime.now(timezone.utc).isoformat(),
        "value_at_release": value,
        "latest_revised_value": latest_revised_value,
        "revision_number": revision_number,
        "vintage_id": f"{series_id}:{reference_period}:{release_date}",
        "seasonal_adjustment": "seasonally_adjusted",
        "source_url": source_url,
        "source_hash": source_hash,
    }


def _parse_number(value):
    text = str(value).strip().replace(",", "")
    try:
        return float(text)
    except ValueError as exc:
        raise ValueError(
            f"employment situation has non-numeric value {value!r}"
        ) from exc

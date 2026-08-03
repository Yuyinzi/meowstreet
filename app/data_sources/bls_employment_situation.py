import hashlib
import io
import re
from datetime import date
from datetime import datetime
from datetime import timezone
from html.parser import HTMLParser

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
    rf"({_MONTH_NAME_PATTERN}) (\d{{4}})[^.]*?revised\s+from ([\d,]+(?:\.[\d]+)?) "
    r"to ([\d,]+(?:\.[\d]+)?)",
    re.IGNORECASE,
)
_NEXT_EVENT_RE = re.compile(
    rf"scheduled[\s\S]*?({_MONTH_NAME_PATTERN} \d{{1,2}}, \d{{4}}),? at "
    r"(\d{1,2}):(\d{2})",
    re.IGNORECASE,
)
_HTML_RELEASE_DATE_RE = re.compile(
    rf"embargoed until[^\n]*?({_MONTH_NAME_PATTERN} \d{{1,2}}, \d{{4}})",
    re.IGNORECASE,
)
_HTML_MONTH_HEADER_RE = re.compile(r"([A-Za-z]{3,9})\.?\s?(\d{4})(?:\([^)]*\))?")
_HTML_REVISION_RE = re.compile(
    rf"for ({_MONTH_NAME_PATTERN}) was revised (down|up) by [\d,]+,\s*from "
    r"([+\-]?[\d,]+(?:\.[\d]+)?) to ([+\-]?[\d,]+(?:\.[\d]+)?)",
    re.IGNORECASE,
)
_HOUSEHOLD_METRICS = [
    (None, "unemployment rate", "unemployment_rate"),
]
_ESTABLISHMENT_METRICS = [
    ("over-the-month change", "total nonfarm", "nonfarm_payrolls_change"),
    ("3-month average change", "total nonfarm", "payrolls_3m_average_change"),
    ("hours and earnings", "average weekly hours", "average_weekly_hours"),
    ("hours and earnings", "average hourly earnings", "average_hourly_earnings"),
]
_REQUIRED_HTML_METRICS = [
    "nonfarm_payrolls_change",
    "unemployment_rate",
    "average_weekly_hours",
    "average_hourly_earnings",
]


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


def parse_employment_situation_html(
    overview_html,
    household_html,
    establishment_html,
    overview_url,
    household_url,
    establishment_url,
):
    overview_text = _html_text(overview_html)
    release_date = _extract_release_date_from_html(overview_text)
    reference_period = _extract_reference_month_from_html(overview_text)
    source_hash = _html_source_hash(overview_html, household_html, establishment_html)
    household_values = _extract_table_metric(
        _html_table_rows(household_html), _HOUSEHOLD_METRICS, reference_period
    )
    establishment_values = _extract_table_metric(
        _html_table_rows(establishment_html), _ESTABLISHMENT_METRICS, reference_period
    )
    values = {**household_values, **establishment_values}
    missing = [
        series_id for series_id in _REQUIRED_HTML_METRICS if series_id not in values
    ]
    if missing:
        raise ValueError(f"employment situation html is missing {', '.join(missing)}")
    observations = []
    for series_id in _REQUIRED_HTML_METRICS:
        url = household_url if series_id in household_values else establishment_url
        observations.append(
            _observation(
                series_id,
                reference_period,
                release_date,
                values[series_id],
                None,
                0,
                url,
                source_hash,
            )
        )
    if "payrolls_3m_average_change" in values:
        observations.append(
            _observation(
                "payrolls_3m_average_change",
                reference_period,
                release_date,
                values["payrolls_3m_average_change"],
                None,
                0,
                establishment_url,
                source_hash,
            )
        )
    observations.extend(
        _html_revision_observations(
            overview_text, reference_period, release_date, overview_url, source_hash
        )
    )
    return {
        "source_url": overview_url,
        "release_date": release_date,
        "reference_period": reference_period,
        "observations": observations,
        "scheduled_events": [_next_event(overview_text, overview_url)],
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


def _extract_release_date_from_html(text):
    match = _HTML_RELEASE_DATE_RE.search(text)
    if not match:
        raise ValueError("employment situation html is missing release date")
    return _parse_month_day_year(match.group(1)).isoformat()


def _extract_reference_month_from_html(text):
    match = _REFERENCE_MONTH_RE.search(text)
    if not match:
        raise ValueError("employment situation html is missing reference month")
    return f"{match.group(2)}-{_month_number(match.group(1)):02d}"


def _html_text(html):
    parser = _TextAndTablesParser()
    parser.feed(_decode_html(html))
    parser.close()
    return _collapse_whitespace("".join(parser.text_parts))


def _html_table_rows(html):
    parser = _TextAndTablesParser()
    parser.feed(_decode_html(html))
    parser.close()
    return parser.rows


def _html_source_hash(*documents):
    payload = b"".join(
        document if isinstance(document, bytes) else str(document).encode("utf-8")
        for document in documents
    )
    return hashlib.sha256(payload).hexdigest()


def _extract_table_metric(rows, labels, reference_period):
    values = {}
    if not rows:
        return values
    header = rows[0]
    periods = [_month_period_from_cell(cell) for cell in header]
    if reference_period in periods:
        current_index = periods.index(reference_period)
    else:
        current_index = len(header) - 1
    current_sections = []
    was_header = False
    for row in rows[1:]:
        cells = [cell for cell in row if cell]
        if not cells:
            was_header = False
            continue
        if len(cells) == 1:
            section = _collapse_whitespace(cells[0])
            if was_header:
                current_sections.append(section)
            else:
                current_sections = [section]
            was_header = True
            continue
        was_header = False
        if current_index >= len(row):
            continue
        label_cell = _collapse_whitespace(row[0]).lower()
        for section_keyword, row_label, series_id in labels:
            if section_keyword is not None and not any(
                section_keyword in section.lower() for section in current_sections
            ):
                continue
            if row_label not in label_cell:
                continue
            if series_id in values:
                raise ValueError(f"employment situation html has ambiguous {series_id}")
            values[series_id] = _parse_number(row[current_index])
            break
    return values


def _month_period_from_cell(cell):
    match = _HTML_MONTH_HEADER_RE.fullmatch(str(cell).strip())
    if match is None:
        return None
    if match.group(1).lower().rstrip(".") not in _MONTHS:
        return None
    return _month_period(match.group(1), match.group(2))


def _decode_html(document):
    if isinstance(document, bytes):
        return document.decode("utf-8", errors="replace")
    return str(document)


def _collapse_whitespace(text):
    return re.sub(r"\s+", " ", text).strip()


class _TextAndTablesParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.text_parts = []
        self.rows = []
        self._current_row = None
        self._current_cell = None

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self._current_row = None
        elif tag == "tr":
            self._current_row = []
        elif tag in ("td", "th"):
            self._current_cell = []

    def handle_endtag(self, tag):
        if tag == "table":
            self._current_row = None
            self._current_cell = None
        elif tag == "tr":
            if self._current_row is not None and self._current_row:
                self.rows.append(self._current_row)
            self._current_row = None
        elif tag in ("td", "th"):
            if self._current_cell is not None:
                if self._current_row is not None:
                    self._current_row.append(
                        _collapse_whitespace("".join(self._current_cell))
                    )
                self._current_cell = None

    def handle_data(self, data):
        normalized = _collapse_whitespace(data)
        self.text_parts.append(normalized)
        if self._current_cell is not None:
            self._current_cell.append(normalized)


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


def _html_revision_observations(
    text, reference_period, release_date, source_url, source_hash
):
    observations = []
    seen = set()
    for match in _HTML_REVISION_RE.finditer(text):
        period = _revision_period_for_month(match.group(1), reference_period)
        if period is None or period in seen:
            continue
        seen.add(period)
        observations.append(
            _observation(
                "nonfarm_payrolls_change",
                period,
                release_date,
                _parse_number(match.group(3)) / 1000,
                _parse_number(match.group(4)) / 1000,
                1,
                source_url,
                source_hash,
            )
        )
    return observations


def _revision_period_for_month(month_name, reference_period):
    month_number = _month_number(month_name)
    year = int(reference_period[:4])
    month = int(reference_period[5:7])
    for back in (1, 2):
        candidate_month = month - back
        candidate_year = year
        if candidate_month < 1:
            candidate_month += 12
            candidate_year -= 1
        if candidate_month == month_number:
            return f"{candidate_year}-{candidate_month:02d}"
    return None


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
    text = str(value).strip().replace(",", "").replace("$", "")
    try:
        return float(text)
    except ValueError as exc:
        raise ValueError(
            f"employment situation has non-numeric value {value!r}"
        ) from exc

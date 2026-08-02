import csv
import hashlib
import io
import re
from datetime import date
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from urllib.parse import urljoin

import httpx
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
_RELEASE_DATE_RE = re.compile(
    rf"EMBARGOED UNTIL[\s\S]*?({_MONTH_NAME_PATTERN} \d{{1,2}}, \d{{4}})",
    re.IGNORECASE,
)
_INITIAL_VALUE_RE = re.compile(
    rf"week ending ({_MONTH_NAME_PATTERN} \d{{1,2}})[\s\S]*?"
    r"seasonally adjusted initial claims[\s\S]*?was ([\d,]+)",
    re.IGNORECASE,
)
_CONTINUING_VALUE_RE = re.compile(
    rf"insured unemployment[\s\S]*?week ending ({_MONTH_NAME_PATTERN} \d{{1,2}})"
    r"[^.]*?was ([\d,]+)",
    re.IGNORECASE,
)
_REVISION_RE = re.compile(
    r"revised (?:up|down) by [\d,]+ from ([\d,]+) to ([\d,]+)",
    re.IGNORECASE,
)
_FORM_RE = re.compile(
    r'<form[^>]*action=["\']([^"\']+)["\'][^>]*>(.*?)</form>',
    re.IGNORECASE | re.DOTALL,
)
_INPUT_RE = re.compile(r"<input[^>]*>", re.IGNORECASE)
_ATTR_RE = re.compile(r'([\w-]+)=["\']([^"\']*)["\']', re.IGNORECASE)
_SERIES_VALUE_COLUMNS = {
    "initial_claims_sa": ("initial claims",),
    "continuing_claims_sa": ("continued claims", "continuing claims"),
}
_DATE_COLUMN_NAMES = frozenset(
    {"date", "report date", "week ending", "week ended", "period"}
)
_MONTH_DAY_RE = re.compile(r"(\d{4})-(\d{1,2})")
_FULL_DATE_RE = re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})")


def fetch_claims_history(client, initial_url, continuing_url):
    observations = []
    observations.extend(
        _fetch_claims_history_series(client, initial_url, "initial_claims_sa")
    )
    observations.extend(
        _fetch_claims_history_series(client, continuing_url, "continuing_claims_sa")
    )
    return observations


def fetch_claims_release(client, release_url):
    content = _fetch_bytes(client, release_url, "claims release pdf")
    text = _extract_pdf_text(content, "claims release pdf")
    return parse_claims_release_text(text, release_url)


def parse_claims_release_text(text, source_url):
    release_date = _extract_release_date(text)
    observations = []
    observations.extend(
        _release_observations(
            text, "initial claims", "initial_claims_sa", release_date, source_url
        )
    )
    observations.extend(
        _release_observations(
            text,
            "insured unemployment",
            "continuing_claims_sa",
            release_date,
            source_url,
        )
    )
    return observations


def parse_claims_history_csv(content, series_id, source_url):
    text = _decode_text(content)
    source_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    reader = csv.DictReader(io.StringIO(text))
    fieldnames = reader.fieldnames or []
    date_column = _date_column(fieldnames)
    value_column = _value_column(fieldnames, series_id)
    as_of_timestamp = datetime.now(timezone.utc).isoformat()
    retrieval_date = as_of_timestamp[:10]
    observations = []
    seen = set()
    for line_num, row in enumerate(reader, start=2):
        date_raw = str(row.get(date_column) or "").strip()
        value_raw = str(row.get(value_column) or "").strip()
        if not date_raw and not value_raw:
            continue
        if not date_raw:
            raise ValueError(f"claims csv row {line_num} is missing date")
        if not value_raw:
            continue
        reference_period = _parse_reference_period(date_raw)
        if reference_period in seen:
            raise ValueError(
                f"claims csv has duplicate {series_id} period {reference_period}"
            )
        seen.add(reference_period)
        value = _parse_number(value_raw)
        if value < 0:
            raise ValueError(
                f"claims csv row {line_num} has negative {series_id} value"
            )
        observations.append(
            {
                "series_id": series_id,
                "reference_period": reference_period,
                "release_date": None,
                "as_of_timestamp": as_of_timestamp,
                "value_at_release": value,
                "latest_revised_value": None,
                "revision_number": 0,
                "vintage_id": f"{series_id}:{reference_period}:{retrieval_date}",
                "seasonal_adjustment": "seasonally_adjusted",
                "source_url": source_url,
                "source_hash": source_hash,
            }
        )
    if not observations:
        raise ValueError(f"claims csv has no {series_id} observations")
    return observations


def _fetch_claims_history_series(client, page_url, series_id):
    page = _fetch_bytes(client, page_url, "claims chartbook page")
    endpoint, params = _discover_raw_data_form(page, page_url)
    params = _extend_history_window(params)
    csv_content = _fetch_csv(client, endpoint, params)
    return parse_claims_history_csv(csv_content, series_id, endpoint)


def _discover_raw_data_form(page_html, page_url):
    html = _decode_text(page_html)
    for action, body in _FORM_RE.findall(html):
        params = {}
        for tag in _INPUT_RE.findall(body):
            attrs = dict(_ATTR_RE.findall(tag))
            name = attrs.get("name")
            if name:
                params[name] = attrs.get("value", "")
        if "chartnum" in params:
            endpoint = urljoin(page_url, action.strip())
            return endpoint, params
    raise ValueError(f"claims chartbook page has no raw data form at {page_url}")


def _extend_history_window(params):
    current_year = datetime.now().year
    try:
        discovered_end = int(params.get("endyr") or 0)
    except (TypeError, ValueError):
        discovered_end = 0
    params["endyr"] = str(max(discovered_end, current_year))
    return params


def _fetch_csv(client, endpoint, params):
    try:
        response = client.request("POST", endpoint, data=params, timeout=60)
    except httpx.HTTPError as exc:
        raise ValueError(
            f"failed to fetch claims history csv from {endpoint}: {exc}"
        ) from exc
    return response.content


def _fetch_bytes(client, url, label):
    try:
        response = client.request("GET", url, timeout=60)
    except httpx.HTTPError as exc:
        raise ValueError(f"failed to fetch {label} from {url}: {exc}") from exc
    return response.content


def _extract_pdf_text(content, label):
    try:
        reader = PdfReader(io.BytesIO(content))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    except Exception as exc:
        raise ValueError(f"{label} could not be read") from exc


def _extract_release_date(text):
    match = _RELEASE_DATE_RE.search(text)
    if not match:
        raise ValueError("claims release pdf is missing release date")
    return _parse_month_day_year(match.group(1))


def _release_observations(text, label, series_id, release_date, source_url):
    paragraph = _series_paragraph(text, label)
    if paragraph is None:
        raise ValueError(
            f"claims release pdf is missing seasonally adjusted {label} data"
        )
    if label == "initial claims":
        value_match = _INITIAL_VALUE_RE.search(paragraph)
    else:
        value_match = _CONTINUING_VALUE_RE.search(paragraph)
    if not value_match:
        raise ValueError(
            f"claims release pdf is missing seasonally adjusted {label} value"
        )
    reference_period = _resolve_reference_date(value_match.group(1), release_date)
    value = _parse_number(value_match.group(2))
    observations = [
        _release_observation_payload(
            series_id,
            reference_period,
            release_date,
            source_url,
            text,
            value_at_release=value,
            latest_revised_value=None,
            revision_number=0,
        )
    ]
    revision_match = _REVISION_RE.search(paragraph, value_match.start())
    if revision_match:
        prior_reference_period = (
            date.fromisoformat(reference_period) - timedelta(days=7)
        ).isoformat()
        observations.append(
            _release_observation_payload(
                series_id,
                prior_reference_period,
                release_date,
                source_url,
                text,
                value_at_release=_parse_number(revision_match.group(1)),
                latest_revised_value=_parse_number(revision_match.group(2)),
                revision_number=1,
            )
        )
    return observations


def _release_observation_payload(
    series_id,
    reference_period,
    release_date,
    source_url,
    text,
    value_at_release,
    latest_revised_value,
    revision_number,
):
    return {
        "series_id": series_id,
        "reference_period": reference_period,
        "release_date": release_date.isoformat(),
        "as_of_timestamp": datetime.now(timezone.utc).isoformat(),
        "value_at_release": value_at_release,
        "latest_revised_value": latest_revised_value,
        "revision_number": revision_number,
        "vintage_id": f"{series_id}:{reference_period}:{release_date.isoformat()}",
        "seasonal_adjustment": "seasonally_adjusted",
        "source_url": source_url,
        "source_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
    }


def _series_paragraph(text, keyword):
    for paragraph in _paragraphs(text):
        lower = paragraph.lower()
        if keyword in lower and "seasonally adjusted" in lower:
            return paragraph
    return None


def _paragraphs(text):
    return [
        paragraph.strip()
        for paragraph in re.split(r"\n\s*\n", text)
        if paragraph.strip()
    ]


def _resolve_reference_date(month_day, release_date):
    month_number, day = _parse_month_day(month_day)
    candidate = date(release_date.year, month_number, day)
    if candidate > release_date + timedelta(days=45):
        candidate = candidate.replace(year=release_date.year - 1)
    return candidate.isoformat()


def _parse_month_day(month_day):
    match = re.fullmatch(
        rf"({_MONTH_NAME_PATTERN}) (\d{{1,2}})",
        str(month_day).strip(),
        re.IGNORECASE,
    )
    if not match:
        raise ValueError(f"claims release pdf has invalid week ending {month_day!r}")
    return _month_number(match.group(1)), int(match.group(2))


def _parse_month_day_year(value):
    match = re.fullmatch(
        rf"({_MONTH_NAME_PATTERN}) (\d{{1,2}}), (\d{{4}})",
        str(value).strip(),
        re.IGNORECASE,
    )
    if not match:
        raise ValueError(f"claims release pdf has invalid release date {value!r}")
    month_number = _month_number(match.group(1))
    return date(int(match.group(3)), month_number, int(match.group(2)))


def _month_number(month):
    number = _MONTHS.get(month.lower().rstrip("."))
    if number is None:
        raise ValueError(f"claims release pdf has unknown month {month!r}")
    return number


def _date_column(fieldnames):
    for header in fieldnames:
        if header.strip().lower() in _DATE_COLUMN_NAMES:
            return header
    raise ValueError("claims csv has no date column")


def _value_column(fieldnames, series_id):
    for header in fieldnames:
        name = header.strip().lower()
        for key in _SERIES_VALUE_COLUMNS[series_id]:
            if key in name:
                return header
    raise ValueError(f"claims csv is missing {series_id} value column")


def _parse_reference_period(value):
    text = str(value).strip()
    month_match = _MONTH_DAY_RE.fullmatch(text)
    if month_match:
        return f"{month_match.group(1)}-{int(month_match.group(2)):02d}"
    full_match = _FULL_DATE_RE.fullmatch(text)
    if full_match:
        return (
            f"{full_match.group(1)}-{int(full_match.group(2)):02d}-"
            f"{int(full_match.group(3)):02d}"
        )
    raise ValueError(f"claims csv has invalid reference period: {value!r}")


def _parse_number(value):
    text = str(value).strip().replace(",", "")
    try:
        return float(text)
    except ValueError as exc:
        raise ValueError(f"claims csv has non-numeric value: {value!r}") from exc


def _decode_text(content):
    if isinstance(content, (bytes, bytearray)):
        return content.decode("utf-8-sig", errors="replace")
    return str(content)

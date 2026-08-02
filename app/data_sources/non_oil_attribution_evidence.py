import io
import json
import math
from html.parser import HTMLParser
from urllib.parse import urljoin
from urllib.parse import urlparse

from openpyxl import load_workbook

from app.http_client import HttpClient

VERSION = "non_oil_attribution_evidence_v1"

IWCC_SOURCE_NAME = "International Wrought Copper Council"
IWCC_SOURCE_URL = "http://www.coppercouncil.org/iwcc-statistics-and-data"
IWCC_WORKBOOK_ANCHOR = "Semis production and demand.xlsx"
IWCC_SHEET_FACTORS = {"production": "supply", "demand": "demand"}
IWCC_GEOGRAPHY = "Global"
IWCC_UNITS = "t"

FAOSTAT_SOURCE_NAME = "Food and Agriculture Organization of the United Nations"
FAOSTAT_SOURCE_URL = "https://www.fao.org/faostat/en/#data/FO"
FAOSTAT_API_URL = "https://fenixservices.fao.org/faostat/api/v1/en/data/FO"
FAOSTAT_ITEM = "Sawnwood"
FAOSTAT_AREA = "World"
FAOSTAT_ELEMENT_FACTORS = {
    "Production": "supply",
    "Import Quantity": "trade",
    "Export Quantity": "trade",
}
_FAOSTAT_REQUIRED_ROW_FIELDS = ("item", "area", "year", "element", "value", "unit")

_DEFAULT_CLIENT = HttpClient()


class _AnchorCollector(HTMLParser):
    def __init__(self):
        super().__init__()
        self._anchors = []
        self._current_href = None
        self._text_parts = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self._current_href = dict(attrs).get("href")
            self._text_parts = []

    def handle_data(self, data):
        if self._current_href is not None:
            self._text_parts.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._current_href is not None:
            self._anchors.append((self._current_href, "".join(self._text_parts)))
            self._current_href = None

    def anchors(self):
        return self._anchors


def _normalize_anchor(text):
    return " ".join(str(text).strip().lower().split())


def fetch_iwcc_copper_facts(http_client=None):
    client = http_client or _DEFAULT_CLIENT
    page_response = client.request("GET", IWCC_SOURCE_URL)
    workbook_url = _iwcc_workbook_url(page_response.content)
    workbook_response = client.request("GET", workbook_url)
    raw_facts = _parse_iwcc_workbook(workbook_response.content)
    return [normalize_non_oil_attribution_fact(raw_fact) for raw_fact in raw_facts]


def _iwcc_workbook_url(page_content):
    collector = _AnchorCollector()
    collector.feed(page_content.decode("utf-8", errors="replace"))
    workbook_anchor = next(
        (
            href
            for href, text in collector.anchors()
            if _normalize_anchor(text) == _normalize_anchor(IWCC_WORKBOOK_ANCHOR)
        ),
        None,
    )
    if workbook_anchor is None:
        raise ValueError("iwcc semis production and demand workbook anchor is missing")
    resolved = urljoin(IWCC_SOURCE_URL, workbook_anchor)
    if urlparse(resolved).netloc != urlparse(IWCC_SOURCE_URL).netloc:
        raise ValueError(
            "iwcc semis production and demand workbook is not on the iwcc origin"
        )
    return resolved


def _parse_iwcc_workbook(content):
    workbook = _load_iwcc_workbook(content)
    raw_facts = []
    seen_factors = set()
    for sheet in workbook.worksheets:
        factor_category = IWCC_SHEET_FACTORS.get(_normalize_anchor(sheet.title))
        if factor_category is None:
            continue
        if factor_category in seen_factors:
            raise ValueError(
                f"iwcc semis production and demand workbook has duplicate {factor_category} sheets"
            )
        seen_factors.add(factor_category)
        headers = _iwcc_year_headers(sheet)
        global_rows = _iwcc_global_rows(sheet)
        if not global_rows:
            raise ValueError(
                f"iwcc semis production and demand workbook is missing global {factor_category} cells"
            )
        if len(global_rows) > 1:
            raise ValueError(
                f"iwcc semis production and demand workbook has duplicate global {factor_category} rows"
            )
        newest_year = max(headers)
        raw_facts.append(
            _iwcc_raw_fact(
                factor_category,
                sheet.title,
                newest_year,
                global_rows[0],
                headers[newest_year],
            )
        )
    if seen_factors != set(IWCC_SHEET_FACTORS.values()):
        raise ValueError(
            "iwcc semis production and demand workbook is missing a factor"
        )
    return raw_facts


def _load_iwcc_workbook(content):
    try:
        return load_workbook(io.BytesIO(content), data_only=True)
    except Exception as exc:
        raise ValueError(
            "iwcc semis production and demand workbook is invalid"
        ) from exc


def _iwcc_year_headers(sheet):
    header_row = next(sheet.iter_rows(min_row=1, max_row=1), None)
    if header_row is None:
        raise ValueError("iwcc semis production and demand workbook is missing headers")
    headers = {}
    for cell in header_row:
        try:
            year = int(cell.value)
        except (TypeError, ValueError):
            continue
        if 1000 <= year <= 9999:
            headers[year] = cell.column
    if not headers:
        raise ValueError(
            "iwcc semis production and demand workbook is missing year headers"
        )
    return headers


def _iwcc_global_rows(sheet):
    return [
        row
        for row in sheet.iter_rows(min_row=2)
        if _normalize_anchor(row[0].value) == "global"
    ]


def _iwcc_raw_fact(factor_category, metric_name, year, global_row, column):
    value = _iwcc_global_value(global_row[column - 1].value, factor_category)
    return {
        "commodity_id": "copper",
        "source_name": IWCC_SOURCE_NAME,
        "source_url": IWCC_SOURCE_URL,
        "factor_category": factor_category,
        "metric_name": metric_name,
        "geography": IWCC_GEOGRAPHY,
        "observation_date": f"{year}-12-31",
        "publication_date": None,
        "value": value,
        "units": IWCC_UNITS,
    }


def _iwcc_global_value(raw_value, factor_category):
    try:
        value = float(raw_value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"iwcc semis production and demand global {factor_category} value is not numeric"
        ) from exc
    if not math.isfinite(value):
        raise ValueError(
            f"iwcc semis production and demand global {factor_category} value is not numeric"
        )
    return value


def fetch_faostat_lumber_facts(http_client=None):
    client = http_client or _DEFAULT_CLIENT
    response = client.request("GET", FAOSTAT_API_URL)
    raw_facts = _faostat_raw_facts(_faostat_payload(response.content))
    return [normalize_non_oil_attribution_fact(raw_fact) for raw_fact in raw_facts]


def _faostat_payload(content):
    try:
        payload = json.loads(content)
    except ValueError as exc:
        raise ValueError(
            "faostat forestry production and trade payload is invalid"
        ) from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise ValueError("faostat forestry production and trade payload is invalid")
    return payload


def _faostat_raw_facts(payload):
    rows = payload["data"]
    _require_faostat_source_fields(rows)
    candidates = [
        row
        for row in rows
        if row.get("item") == FAOSTAT_ITEM and row.get("area") == FAOSTAT_AREA
    ]
    return [
        _faostat_raw_fact(element_label, candidates)
        for element_label in FAOSTAT_ELEMENT_FACTORS
    ]


def _require_faostat_source_fields(rows):
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("faostat forestry production and trade row is invalid")
        missing = [
            field
            for field in _FAOSTAT_REQUIRED_ROW_FIELDS
            if row.get(field) in (None, "")
        ]
        if missing:
            raise ValueError(
                "faostat forestry production and trade row is missing a required source field"
            )


def _faostat_raw_fact(element_label, candidates):
    element_rows = [row for row in candidates if row.get("element") == element_label]
    if not element_rows:
        raise ValueError(
            f"faostat forestry production and trade is missing {element_label} facts for {FAOSTAT_ITEM} in {FAOSTAT_AREA}"
        )
    newest_row = max(element_rows, key=lambda row: _faostat_year(row))
    year = _faostat_year(newest_row)
    value = _faostat_value(newest_row, element_label)
    return {
        "commodity_id": "lumber",
        "source_name": FAOSTAT_SOURCE_NAME,
        "source_url": FAOSTAT_SOURCE_URL,
        "factor_category": FAOSTAT_ELEMENT_FACTORS[element_label],
        "metric_name": element_label,
        "geography": newest_row["area"],
        "observation_date": f"{year}-12-31",
        "publication_date": None,
        "value": value,
        "units": newest_row["unit"],
    }


def _faostat_year(row):
    try:
        return int(row["year"])
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "faostat forestry production and trade year is invalid"
        ) from exc


def _faostat_value(row, element_label):
    try:
        value = float(row["value"])
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"faostat forestry production and trade {element_label} value is not numeric"
        ) from exc
    if not math.isfinite(value):
        raise ValueError(
            f"faostat forestry production and trade {element_label} value is not numeric"
        )
    return value


def normalize_non_oil_attribution_fact(raw_fact):
    required = (
        "commodity_id",
        "source_name",
        "source_url",
        "factor_category",
        "metric_name",
        "geography",
        "observation_date",
        "value",
        "units",
    )
    if any(raw_fact.get(key) in (None, "") for key in required):
        raise ValueError(" non-oil attribution fact has a required field missing")
    try:
        value = float(raw_fact["value"])
    except (TypeError, ValueError) as exc:
        raise ValueError(" non-oil attribution fact value is invalid") from exc
    if not math.isfinite(value):
        raise ValueError(" non-oil attribution fact value is invalid")
    return {
        **raw_fact,
        "method_version": VERSION,
        "value": value,
        "status": "available",
    }

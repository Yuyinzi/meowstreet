import re
from pathlib import Path

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None


SERIES_IDS = {
    "nfib_sbo_optimism",
    "nfib_sbo_employment_plans",
    "nfib_sbo_expansion_outlook",
    "nfib_sbo_inventory_plans",
    "nfib_sbo_economic_expectations",
    "nfib_sbo_real_sales_expectations",
}

_LEADING_COMPONENT_SERIES = {
    "employment_plans": "nfib_sbo_employment_plans",
    "expansion_outlook": "nfib_sbo_expansion_outlook",
    "inventory_plans": "nfib_sbo_inventory_plans",
    "economic_expectations": "nfib_sbo_economic_expectations",
    "real_sales_expectations": "nfib_sbo_real_sales_expectations",
}

_OPTIMISM_SERIES = "nfib_sbo_optimism"

_COMPONENT_LABELS = {
    "Plans to Increase Employment": "employment_plans",
    "Plans to Make Capital Expenditures": "expansion_outlook",
    "Plans to Increase Inventories": "inventory_plans",
    "Expect Economy to Improve": "economic_expectations",
    "Expect Real Sales Higher": "real_sales_expectations",
}

_HISTORICAL_SECTION_HEADERS = {
    "Plans to Increase Employment": "employment_plans",
    "Plans to Make Capital Expenditures": "expansion_outlook",
    "Plans to Increase Inventories": "inventory_plans",
    "Expect Economy to Improve": "economic_expectations",
    "Expect Real Sales Higher": "real_sales_expectations",
    "Small Business Optimism Index": "optimism",
}

_REPORT_MONTH_RE = re.compile(
    r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})\b"
)

_OPTIMISM_RE = re.compile(r"Optimism Index\s+(\d+\.?\d*)")

_COMPONENT_LINE_RE = re.compile(
    r"(Plans to Increase Employment|Plans to Make Capital Expenditures|"
    r"Plans to Increase Inventories|Expect Economy to Improve|"
    r"Expect Real Sales Higher)\s+(-?\d+)"
)

_MONTH_NUM = {
    "January": 1,
    "February": 2,
    "March": 3,
    "April": 4,
    "May": 5,
    "June": 6,
    "July": 7,
    "August": 8,
    "September": 9,
    "October": 10,
    "November": 11,
    "December": 12,
}

_HISTORICAL_LINE_RE = re.compile(r"(\d{4})-(\d{1,2})\s+(-?\d+\.?\d*)")


def _month_period(year, month):
    return f"{int(year):04d}-{int(month):02d}-01"


def _normalize_period_to_end_of_month(period):
    parts = period.split("-")
    if len(parts) >= 2:
        return f"{parts[0]}-{parts[1]}-30"
    return period


def _parse_report_month(text):
    match = _REPORT_MONTH_RE.search(text)
    if not match:
        raise ValueError("nfib report is missing required report month")
    month_name, year = match.groups()
    return int(year), _MONTH_NUM[month_name]


def _build_leading_component_observation(series_id, period, value, provenance):
    return {
        "series_id": series_id,
        "date": period,
        "value": float(value),
        "source": "nfib_sbet_pdf",
        "revision_status": "official_current_history",
        "source_url": provenance.get("source_url", ""),
        "release_date": provenance.get("release_date", ""),
        "source_identifier": provenance.get("source_identifier", ""),
    }


def _parse_summary_table(text, report_year, report_month, provenance):
    optimism_match = _OPTIMISM_RE.search(text)
    if optimism_match:
        provenance["optimism"] = float(optimism_match.group(1))

    for line in text.split("\n"):
        match = _COMPONENT_LINE_RE.search(line)
        if match:
            label = match.group(1)
            key = _COMPONENT_LABELS.get(label)
            if key:
                provenance[key] = float(match.group(2))

    period = _month_period(report_year, report_month)
    end_of_month = _normalize_period_to_end_of_month(period)

    if "optimism" not in provenance:
        raise ValueError("nfib report is missing required optimism index value")

    for key in _LEADING_COMPONENT_SERIES:
        if key not in provenance:
            raise ValueError(f"nfib report is missing required component: {key}")

    observations = [
        _build_leading_component_observation(
            _OPTIMISM_SERIES, end_of_month, provenance["optimism"], provenance
        )
    ]
    for key, series_id in _LEADING_COMPONENT_SERIES.items():
        observations.append(
            _build_leading_component_observation(
                series_id, end_of_month, provenance[key], provenance
            )
        )

    return observations


def _parse_historical_sections(text, provenance):
    observations = []
    seen = set()

    for label, key in _HISTORICAL_SECTION_HEADERS.items():
        lines = text.split("\n")
        section_start = None
        for i, line in enumerate(lines):
            if label in line and i < len(lines) - 1:
                next_line = lines[i + 1].strip()
                if _HISTORICAL_LINE_RE.match(next_line):
                    section_start = i + 1
                    break
                elif re.match(r"\(Net %\)|\(SA\)", next_line) and i < len(lines) - 2:
                    if _HISTORICAL_LINE_RE.match(lines[i + 2].strip()):
                        section_start = i + 2
                        break

        if section_start is None:
            continue

        if key == "optimism":
            series_id = _OPTIMISM_SERIES
        else:
            series_id = _LEADING_COMPONENT_SERIES[key]

        for line in lines[section_start:]:
            stripped = line.strip()
            if not stripped:
                break
            match = _HISTORICAL_LINE_RE.match(stripped)
            if not match:
                break
            year, month, value = match.groups()
            period = _month_period(year, month)
            end_of_month = _normalize_period_to_end_of_month(period)
            obs_key = (series_id, end_of_month)
            if obs_key in seen:
                raise ValueError(
                    f"duplicate observation for {series_id} at {end_of_month}"
                )
            seen.add(obs_key)
            observations.append(
                _build_leading_component_observation(
                    series_id, end_of_month, value, provenance
                )
            )

    return observations


def parse_sbet_report_text(text, source_url, release_date, source_identifier):
    report_year, report_month = _parse_report_month(text)
    provenance = {
        "source_url": source_url,
        "release_date": release_date or "",
        "source_identifier": source_identifier or f"{report_month}-{report_year}",
    }
    summary_observations = _parse_summary_table(
        text, report_year, report_month, provenance
    )
    historical_observations = _parse_historical_sections(text, provenance)
    all_observations = summary_observations + historical_observations
    if not all_observations:
        raise ValueError("nfib report is missing required observations")
    return {"observations": all_observations}


def parse_sbet_report(pdf_path, source_url, release_date=None):
    if PdfReader is None:
        raise ImportError("pypdf is required to parse NFIB SBET PDFs")
    path = Path(pdf_path)
    if not path.exists():
        raise ValueError(f"pdf path does not exist: {pdf_path}")
    reader = PdfReader(str(path))
    text = "\n".join(page.extract_text() for page in reader.pages)
    source_identifier = path.name
    return parse_sbet_report_text(text, source_url, release_date, source_identifier)


def fetch_sbet_report(destination, source_url):
    import urllib.request

    dest = Path(destination)
    dest.parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(source_url, str(dest))
    return dest

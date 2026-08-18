import hashlib
import re
from calendar import monthrange
from datetime import date
from pathlib import Path

import httpx

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None

from app.http_client import HttpClient


SERIES_IDS = {
    "nfib_sbo_optimism",
    "nfib_sbo_employment_plans",
    "nfib_sbo_expansion_outlook",
    "nfib_sbo_inventory_plans",
    "nfib_sbo_economic_expectations",
    "nfib_sbo_real_sales_expectations",
    "nfib_sbo_capital_outlay_plans",
    "nfib_sbo_current_inventory_low",
    "nfib_sbo_job_openings",
    "nfib_sbo_credit_conditions_expectations",
    "nfib_sbo_earnings_trends",
}

_LEADING_COMPONENT_SERIES = {
    "employment_plans": "nfib_sbo_employment_plans",
    "expansion_outlook": "nfib_sbo_expansion_outlook",
    "inventory_plans": "nfib_sbo_inventory_plans",
    "economic_expectations": "nfib_sbo_economic_expectations",
    "real_sales_expectations": "nfib_sbo_real_sales_expectations",
}

_CONTEXT_COMPONENT_SERIES = {
    "capital_outlay_plans": "nfib_sbo_capital_outlay_plans",
    "current_inventory_low": "nfib_sbo_current_inventory_low",
    "job_openings": "nfib_sbo_job_openings",
    "credit_conditions_expectations": "nfib_sbo_credit_conditions_expectations",
    "earnings_trends": "nfib_sbo_earnings_trends",
}

_OPTIMISM_SERIES = "nfib_sbo_optimism"

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

_MONTH_ABBR = {
    "Jan": 1,
    "Feb": 2,
    "Mar": 3,
    "Apr": 4,
    "May": 5,
    "Jun": 6,
    "Jul": 7,
    "Aug": 8,
    "Sep": 9,
    "Oct": 10,
    "Nov": 11,
    "Dec": 12,
}

_REPORT_MONTH_RE = re.compile(
    r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})\b"
)

_COMPONENT_LINE_RE = re.compile(
    r"(Plans to Increase Employment|Good Time to Expand|Plans to Increase Inventories|"
    r"Expect Economy to Improve|Expect Real Sales Higher|"
    r"Plans to Make Capital Outlays|Current Inventory-too low|"
    r"Current Job Openings|Expected Credit Conditions|Earnings Trends"
    r")\s*(?:\(net\$?\))?\s*(-?\d+)"
)

_OPTIMISM_VALUE_RE = re.compile(
    r"Small Business Optimism Index.*?(?:was|is|of)\s+(\d+\.?\d*)", re.DOTALL
)

_MONTH_HEADER_RE = re.compile(
    r"Jan\s+Feb\s+Mar\s+Apr\s+May\s+Jun\s+Jul\s+Aug\s+Sep\s+Oct\s+Nov\s+Dec"
)

_GRID_ROW_RE = re.compile(r"(\d{4})\s+((-?\d+\.?\d*\s*)+)")

_UPLOAD_BASE_URL = "https://www.nfib.com/wp-content/uploads"

_DISCOVER_LOOKBACK_MONTHS = 3

_REPORT_URL_TEMPLATES = (
    "NFIB-{month_name}-{year}-SBET-Report.pdf",
    "NFIB-SBET-Report-{month_name}-{year}.pdf",
    "Monthly-Economic-Report-{month_name}-{year}.pdf",
)

_MONTH_NAME = {number: name for name, number in _MONTH_NUM.items()}

_SECTION_MARKERS = [
    ("OPTIMISM INDEX", _OPTIMISM_SERIES, True),
    ("OUTLOOK FOR EXPANSION", "nfib_sbo_expansion_outlook", False),
    (
        "OUTLOOK FOR GENERAL BUSINESS CONDITIONS",
        "nfib_sbo_economic_expectations",
        False,
    ),
    ("SALES EXPECTATIONS", "nfib_sbo_real_sales_expectations", False),
    ("HIRING PLANS", "nfib_sbo_employment_plans", False),
    ("INVENTORY PLANS", "nfib_sbo_inventory_plans", False),
]

_NEXT_SECTION_BOUNDARIES = [
    "OPTIMISM INDEX",
    "OUTLOOK FOR EXPANSION",
    "OUTLOOK FOR GENERAL BUSINESS CONDITIONS",
    "SALES EXPECTATIONS",
    "HIRING PLANS",
    "INVENTORY PLANS",
    "ACTUAL EMPLOYMENT CHANGES",
    "JOB OPENINGS",
    "SMALL BUSINESS COMPENSATION",
    "ACTUAL COMPENSATION CHANGES",
    "COMPENSATION PLANS",
    "CREDIT CONDITIONS",
    "ACTUAL INTEREST RATE",
    "ACTUAL INVENTORY CHANGES",
    "CURRENT INVENTORY",
    "CAPITAL EXPENDITURE PLANS",
    "UNCERTAINTY INDEX",
    "EMPLOYMENT INDEX",
    "EARNINGS",
    "ACTUAL SALES CHANGES",
    "PRICE PLANS",
    "ACTUAL PRICE CHANGES",
]


def _hash_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _end_of_month(year, month):
    _, last = monthrange(int(year), int(month))
    return f"{int(year):04d}-{int(month):02d}-{last:02d}"


def _parse_report_month(text):
    match = _REPORT_MONTH_RE.search(text)
    if not match:
        raise ValueError("nfib report is missing required report month")
    month_name, year = match.groups()
    return int(year), _MONTH_NUM[month_name]


def _parse_summary_table(text, report_year, report_month, provenance):
    for line in text.split("\n"):
        m = _COMPONENT_LINE_RE.search(line)
        if m:
            label = m.group(1)
            val = float(m.group(2))
            if label == "Good Time to Expand":
                provenance["expansion_outlook"] = val
            elif label == "Plans to Increase Employment":
                provenance["employment_plans"] = val
            elif label == "Plans to Increase Inventories":
                provenance["inventory_plans"] = val
            elif label == "Expect Economy to Improve":
                provenance["economic_expectations"] = val
            elif label == "Expect Real Sales Higher":
                provenance["real_sales_expectations"] = val
            elif label == "Plans to Make Capital Outlays":
                provenance["capital_outlay_plans"] = val
            elif label == "Current Inventory-too low":
                provenance["current_inventory_low"] = val
            elif label == "Current Job Openings":
                provenance["job_openings"] = val
            elif label == "Expected Credit Conditions":
                provenance["credit_conditions_expectations"] = val
            elif label == "Earnings Trends":
                provenance["earnings_trends"] = val

    optimism_m = _OPTIMISM_VALUE_RE.search(text)
    if optimism_m:
        provenance["optimism"] = float(optimism_m.group(1))

    end_of_month = _end_of_month(report_year, report_month)

    for key in _LEADING_COMPONENT_SERIES:
        if key not in provenance:
            raise ValueError(f"nfib report is missing required component: {key}")

    observations = []
    if "optimism" in provenance:
        observations.append(
            _build_observation(
                _OPTIMISM_SERIES, end_of_month, provenance["optimism"], provenance
            )
        )
    for key, series_id in _LEADING_COMPONENT_SERIES.items():
        observations.append(
            _build_observation(series_id, end_of_month, provenance[key], provenance)
        )
    for key, series_id in _CONTEXT_COMPONENT_SERIES.items():
        if key in provenance:
            observations.append(
                _build_observation(series_id, end_of_month, provenance[key], provenance)
            )
    return observations


def _build_observation(series_id, period, value, provenance):
    return {
        "series_id": series_id,
        "date": period,
        "value": float(value),
        "source": "nfib_sbet_pdf",
        "revision_status": "official_current_history",
        "source_url": provenance.get("source_url", ""),
        "release_date": provenance.get("release_date", ""),
        "source_identifier": provenance.get("source_identifier", ""),
        "source_hash": provenance.get("source_hash", ""),
    }


def _parse_grid(lines, start_idx, months):
    data_rows = []
    for j in range(start_idx, len(lines)):
        stripped = lines[j].strip()
        if not stripped:
            continue
        row_m = _GRID_ROW_RE.match(stripped)
        if row_m:
            year = row_m.group(1)
            val_str = row_m.group(2).strip()
            vals = re.findall(r"-?\d+\.?\d*", val_str)
            row_data = {}
            for idx, v in enumerate(vals):
                if idx < len(months):
                    row_data[months[idx]] = float(v)
            data_rows.append((year, row_data))
        else:
            break
    return data_rows


def _is_expansion_outlook_grid(g_rows):
    for year, row_data in g_rows:
        if year == "2021":
            jan = row_data.get(1)
            if jan is not None and -5 <= jan <= 15:
                return True
            return False
    return False


def _find_next_boundary(lines, start_i):
    for j in range(start_i, len(lines)):
        for b in _NEXT_SECTION_BOUNDARIES:
            if lines[j].strip().upper().startswith(b):
                return j
    return len(lines)


def _assign_grid_data(entry, sid, observations, seen, provenance):
    _, g_months, g_rows = entry
    for year, row_data in g_rows:
        for month_num, value in row_data.items():
            period = _end_of_month(year, month_num)
            obs_key = (sid, period)
            if obs_key in seen:
                continue
            seen.add(obs_key)
            observations.append(_build_observation(sid, period, value, provenance))


def _parse_historical_sections(text, provenance):
    observations = []
    seen = set()
    lines = text.split("\n")

    grid_entries = []
    for i, line in enumerate(lines):
        if _MONTH_HEADER_RE.search(line):
            month_names = line.split()
            months = []
            for mname in month_names:
                mname = mname.strip().rstrip(",")
                if mname in _MONTH_ABBR:
                    months.append(_MONTH_ABBR[mname])
            if not months:
                continue
            data_rows = _parse_grid(lines, i + 1, months)
            if data_rows:
                grid_entries.append([i, months, data_rows])

    ASSIGN_ORDER = [
        ("OPTIMISM INDEX", _OPTIMISM_SERIES, False),
        ("OUTLOOK FOR EXPANSION", "nfib_sbo_expansion_outlook", False),
        (
            "OUTLOOK FOR GENERAL BUSINESS CONDITIONS",
            "nfib_sbo_economic_expectations",
            True,
        ),
        ("SALES EXPECTATIONS", "nfib_sbo_real_sales_expectations", False),
        ("HIRING PLANS", "nfib_sbo_employment_plans", False),
        ("INVENTORY PLANS", "nfib_sbo_inventory_plans", False),
        ("CAPITAL EXPENDITURE PLANS", "nfib_sbo_capital_outlay_plans", False),
        ("CURRENT INVENTORY (TOO LOW)", "nfib_sbo_current_inventory_low", False),
        ("JOB OPENINGS", "nfib_sbo_job_openings", False),
        (
            "EXPECT EASIER CREDIT CONDITIONS",
            "nfib_sbo_credit_conditions_expectations",
            False,
        ),
        ("EARNINGS", "nfib_sbo_earnings_trends", False),
    ]

    def _pop_nearest(line_i, skip=0, max_dist=25):
        candidates = [
            (gi, entry) for gi, entry in enumerate(grid_entries) if entry[0] > line_i
        ]
        if len(candidates) > skip:
            grid_i, entry = candidates[skip]
            if entry[0] - line_i < max_dist:
                return grid_entries.pop(grid_i)
        return None

    def _is_header_line(stripped_line, marker):
        if not stripped_line.startswith(marker):
            return False
        remainder = stripped_line[len(marker) :].lstrip()
        return not remainder

    def _bounded_grids(marker_i):
        boundary_i = _find_next_boundary(lines, marker_i + 1)
        return [
            gi
            for gi, ge in enumerate(grid_entries)
            if ge[0] > marker_i and ge[0] < boundary_i
        ]

    _VULNERABLE_MARKERS = {"JOB OPENINGS", "EARNINGS"}

    def _assign_one(marker, sid, disambiguate, observations, seen, provenance):
        header_indices = [
            i
            for i, line in enumerate(lines)
            if _is_header_line(line.strip().upper(), marker)
        ]
        marker_i = next(
            (i for i in reversed(header_indices) if _bounded_grids(i)), None
        )
        if marker_i is None:
            marker_i = header_indices[-1] if header_indices else None
        if marker_i is None:
            return

        candidates = _bounded_grids(marker_i)

        if not candidates:
            entry = _pop_nearest(
                marker_i, skip=1 if marker == "SALES EXPECTATIONS" else 0
            )
            if entry is None:
                return
            actual_sid = sid
            if disambiguate and _is_expansion_outlook_grid(entry[2]):
                actual_sid = "nfib_sbo_expansion_outlook"
            _assign_grid_data(entry, actual_sid, observations, seen, provenance)
        elif marker in {"INVENTORY PLANS", "SALES EXPECTATIONS"}:
            taken = candidates[1] if len(candidates) >= 2 else candidates[0]
            _assign_grid_data(
                grid_entries.pop(taken), sid, observations, seen, provenance
            )
        elif disambiguate and len(candidates) >= 2:
            first_gi = candidates[0]
            if _is_expansion_outlook_grid(grid_entries[first_gi][2]):
                entry = grid_entries.pop(first_gi)
                _assign_grid_data(
                    entry, "nfib_sbo_expansion_outlook", observations, seen, provenance
                )
                for gi, ge in enumerate(grid_entries):
                    if ge[0] > marker_i and ge[0] < _find_next_boundary(
                        lines, marker_i + 1
                    ):
                        _assign_grid_data(
                            grid_entries.pop(gi), sid, observations, seen, provenance
                        )
                        break
            else:
                _assign_grid_data(
                    grid_entries.pop(first_gi), sid, observations, seen, provenance
                )
        else:
            _assign_grid_data(
                grid_entries.pop(candidates[0]), sid, observations, seen, provenance
            )

    for marker, sid, disambiguate in ASSIGN_ORDER:
        if marker in _VULNERABLE_MARKERS:
            _assign_one(marker, sid, disambiguate, observations, seen, provenance)

    for marker, sid, disambiguate in ASSIGN_ORDER:
        if marker not in _VULNERABLE_MARKERS:
            _assign_one(marker, sid, disambiguate, observations, seen, provenance)

    return observations


def _normalize_observations(observations):
    observations_by_key = {}
    for observation in observations:
        key = (observation["series_id"], observation["date"])
        existing = observations_by_key.get(key)
        if existing and existing["value"] != observation["value"]:
            raise ValueError("nfib report has conflicting values")
        observations_by_key[key] = observation
    return list(observations_by_key.values())


def _required_historical_dates(report_year, report_month):
    return {
        _end_of_month(year, month)
        for year in range(2021, report_year + 1)
        for month in range(1, 13)
        if (year, month) <= (report_year, report_month)
    }


def _validate_historical_coverage(observations, report_year, report_month):
    required_dates = _required_historical_dates(report_year, report_month)
    dates_by_series = {}
    for observation in observations:
        dates_by_series.setdefault(observation["series_id"], set()).add(
            observation["date"]
        )
    if any(
        not required_dates.issubset(dates_by_series.get(series_id, set()))
        for series_id in SERIES_IDS
    ):
        raise ValueError("nfib report is missing historical months")


def parse_sbet_report_text(
    text, source_url, release_date, source_identifier, source_hash=None
):
    report_year, report_month = _parse_report_month(text)
    provenance = {
        "source_url": source_url,
        "release_date": release_date or "",
        "source_identifier": source_identifier or f"{report_month}-{report_year}",
        "source_hash": source_hash or "",
    }
    summary_observations = _parse_summary_table(
        text, report_year, report_month, provenance
    )
    historical_observations = _parse_historical_sections(text, provenance)
    historical_observations = _normalize_observations(historical_observations)
    _validate_historical_coverage(historical_observations, report_year, report_month)
    all_observations = _normalize_observations(
        historical_observations + summary_observations
    )
    if not all_observations:
        raise ValueError("nfib report is missing required observations")
    return {"observations": all_observations}


def _read_report_text(report_path):
    path = Path(report_path)
    if not path.exists():
        raise ValueError(f"report path does not exist: {report_path}")
    if path.suffix.lower() == ".txt":
        return path.read_text()
    if PdfReader is None:
        raise ImportError("pypdf is required to parse NFIB SBET PDFs")
    reader = PdfReader(str(path))
    return "\n".join(page.extract_text() for page in reader.pages)


def parse_sbet_report(report_path, source_url, release_date=None):
    path = Path(report_path)
    text = _read_report_text(str(path))
    source_hash = _hash_file(str(path))
    result = parse_sbet_report_text(
        text, source_url, release_date, path.name, source_hash
    )
    return result


def fetch_sbet_report(destination, source_url, http_client=None):
    dest = Path(destination)
    dest.parent.mkdir(parents=True, exist_ok=True)
    client = http_client or HttpClient()
    response = client.request("GET", source_url, timeout=60)
    dest.write_bytes(response.content)
    return dest


def _shift_month(year, month, delta):
    total = int(year) * 12 + int(month) - 1 + delta
    return total // 12, total % 12 + 1


def _candidate_report_urls(reference_date):
    today = reference_date or date.today()
    urls = []
    for offset in range(1, _DISCOVER_LOOKBACK_MONTHS + 1):
        report_year, report_month = _shift_month(today.year, today.month, -offset)
        upload_dirs = [
            _shift_month(report_year, report_month, 1),
            (report_year, report_month),
        ]
        for template in _REPORT_URL_TEMPLATES:
            filename = template.format(
                month_name=_MONTH_NAME[report_month], year=report_year
            )
            for upload_year, upload_month in upload_dirs:
                urls.append(
                    f"{_UPLOAD_BASE_URL}/{upload_year:04d}/{upload_month:02d}/{filename}"
                )
    return urls


def discover_latest_sbet_url(reference_date=None, http_client=None):
    client = http_client or HttpClient()
    for url in _candidate_report_urls(reference_date):
        try:
            client.request("HEAD", url, timeout=30)
        except httpx.HTTPStatusError:
            continue
        return url
    raise ValueError("nfib sbet: no report pdf found for recent months")


def report_month_from_url(source_url):
    match = re.search(r"([A-Z][a-z]+)-(\d{4})", Path(source_url).name)
    if not match or match.group(1) not in _MONTH_NUM:
        raise ValueError(f"nfib sbet: cannot determine report month from url: {source_url}")
    return int(match.group(2)), _MONTH_NUM[match.group(1)]

import hashlib
import re
from calendar import monthrange
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
    r"Expect Economy to Improve|Expect Real Sales Higher)\s*(?:\(net\$?\))?\s*(-?\d+)"
)

_OPTIMISM_VALUE_RE = re.compile(
    r"Small Business Optimism Index.*?(?:was|is|of)\s+(\d+\.?\d*)", re.DOTALL
)

_MONTH_HEADER_RE = re.compile(
    r"Jan\s+Feb\s+Mar\s+Apr\s+May\s+Jun\s+Jul\s+Aug\s+Sep\s+Oct\s+Nov\s+Dec"
)

_GRID_ROW_RE = re.compile(r"(\d{4})\s+((-?\d+\.?\d*\s*)+)")

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

    optimism_m = _OPTIMISM_VALUE_RE.search(text)
    if optimism_m:
        provenance["optimism"] = float(optimism_m.group(1))

    end_of_month = _end_of_month(report_year, report_month)

    if "optimism" not in provenance:
        raise ValueError("nfib report is missing required optimism index value")
    for key in _LEADING_COMPONENT_SERIES:
        if key not in provenance:
            raise ValueError(f"nfib report is missing required component: {key}")

    observations = [
        _build_observation(
            _OPTIMISM_SERIES, end_of_month, provenance["optimism"], provenance
        )
    ]
    for key, series_id in _LEADING_COMPONENT_SERIES.items():
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
    ]

    SKIP_TEXTS = [
        "SMALL BUSINESS COMPENSATION",
        "CURRENT INVENTORY",
    ]

    def _pop_nearest(line_i, max_dist=25):
        best_gi = None
        for gi, entry in enumerate(grid_entries):
            if entry[0] <= line_i:
                continue
            d = entry[0] - line_i
            if best_gi is None or d < (grid_entries[best_gi][0] - line_i):
                best_gi = gi
        if best_gi is not None:
            dist = grid_entries[best_gi][0] - line_i
            if dist < max_dist:
                return grid_entries.pop(best_gi)
        return None

    for i, line in enumerate(lines):
        upper = line.strip().upper()
        if any(s in upper for s in SKIP_TEXTS):
            _pop_nearest(i)

    for marker, sid, disambiguate in ASSIGN_ORDER:
        candidates = []
        for i, line in enumerate(lines):
            stripped = line.strip().upper()
            if not stripped.startswith(marker):
                continue
            for ge in grid_entries:
                if ge[0] > i and ge[0] - i < 25:
                    candidates.append((ge[0] - i, i))
                    break
        if not candidates:
            continue
        candidates.sort(key=lambda x: x[0])
        best_i = candidates[0][1]
        entry = _pop_nearest(best_i)
        if entry is None:
            continue
        _, g_months, g_rows = entry
        if disambiguate and _is_expansion_outlook_grid(g_rows):
            actual_sid = "nfib_sbo_expansion_outlook"
        else:
            actual_sid = sid
        for year, row_data in g_rows:
            for month_num, value in row_data.items():
                period = _end_of_month(year, month_num)
                obs_key = (actual_sid, period)
                if obs_key in seen:
                    continue
                seen.add(obs_key)
                observations.append(
                    _build_observation(actual_sid, period, value, provenance)
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
    all_observations = historical_observations + summary_observations
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
    result = parse_sbet_report_text(text, source_url, release_date, path.name)
    result["source_hash"] = _hash_file(str(path))
    return result


def fetch_sbet_report(destination, source_url):
    import urllib.request

    dest = Path(destination)
    dest.parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(source_url, str(dest))
    return dest

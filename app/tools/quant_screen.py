import csv
import io
import math

_TOL = 1e-9

_REQUIRED_COLUMNS = ["symbol", "price", "market_cap", "eps_fy0", "eps_fy1", "eps_fy2"]

_HEADER_SYNONYMS = {
    "symbol": ["ticker", "symbol"],
    "price": ["price", "last price", "last"],
    "market_cap": ["market cap", "market capitalization"],
    "eps_fy0": [
        "eps fy0",
        "eps fy0 - previous financial year",
        "eps0",
    ],
    "eps_fy1": [
        "eps fy1",
        "eps fy1 - current financial year",
        "eps1",
    ],
    "eps_fy2": [
        "eps fy2",
        "eps fy2 - next financial year",
        "eps2",
    ],
    "eps_fy3": ["eps fy3", "eps3"],
    "sector": ["sector", "naics sector name"],
}

_MISSING_TOKENS = {"", "null", "nan", "na", "n/a", "none"}

_MARKET_CAP_TIERS = [
    (1e9, "micro"),
    (3e9, "small"),
    (1e10, "mid"),
    (4e10, "large"),
]


def parse_screener_table(text):
    if not isinstance(text, str):
        raise ValueError("screener table must be a string")
    stripped = text.strip()
    if not stripped:
        raise ValueError("screener table is empty")
    delimiter = "\t" if "\t" in stripped else ","
    reader = csv.DictReader(io.StringIO(stripped), delimiter=delimiter)
    if not reader.fieldnames:
        raise ValueError("screener table has no header row")
    canonical = _canonicalize_headers(reader.fieldnames)
    missing = [col for col in _REQUIRED_COLUMNS if canonical.get(col) is None]
    if missing:
        raise ValueError(f"missing required columns: {', '.join(sorted(missing))}")
    rows = []
    row_errors = []
    for line_number, raw_row in enumerate(reader, start=2):
        row, error = _parse_row(line_number, raw_row, canonical)
        if error:
            row_errors.append(error)
        if row is not None:
            rows.append(row)
    return rows, row_errors


def build_screen_payload(rows, row_errors=None):
    if not rows:
        raise ValueError("screener table contains no usable rows")
    computed = [_compute_row(row) for row in rows]
    sector_means = _sector_means(computed)
    leave_one_out = _leave_one_out_pe1(computed, sector_means["mean_pe1"])
    for row in computed:
        metrics = row["metrics"]
        row["eg_case"], row["eg_case_reason"] = classify_eg_case(
            metrics["eg1"],
            metrics["eg2"],
            sector_means["mean_eg1"],
            sector_means["mean_eg2"],
            eps_fy1=row.get("eps_fy1"),
            eps_fy2=row.get("eps_fy2"),
        )
        row["long_filter"] = long_filter_steps(metrics, sector_means)
        row["short_filter"] = short_filter_steps(metrics, sector_means)
    sorted_rows = sorted(
        computed,
        key=lambda row: (row["metrics"]["pe1"] is None, -(row["metrics"]["pe1"] or 0)),
    )
    return {
        "disclaimer": (
            "Candidate identification only — not a trade signal. "
            "Non-participation is always an option."
        ),
        "row_count": len(sorted_rows),
        "sector": {
            "mean_pe1": sector_means["mean_pe1"],
            "mean_pe2": sector_means["mean_pe2"],
            "mean_eg1": sector_means["mean_eg1"],
            "mean_eg2": sector_means["mean_eg2"],
            "mean_method": "arithmetic mean of valid values",
            "leave_one_out": leave_one_out,
        },
        "rows": [_present_row(row) for row in sorted_rows],
        "row_errors": row_errors if row_errors is not None else [],
    }


def classify_eg_case(eg1, eg2, sector_eg1, sector_eg2, eps_fy1=None, eps_fy2=None):
    if eg1 is None or eg2 is None or sector_eg1 is None or sector_eg2 is None:
        return "unclassified", "missing earnings growth inputs"
    if eps_fy1 is not None and eps_fy2 is not None:
        if eps_fy1 < 0 and eps_fy2 >= 0:
            return 9, None
        if eps_fy1 < 0 and eps_fy2 < 0 and abs(eps_fy2) > abs(eps_fy1):
            return 10, None
    s1, s2, e1, e2 = sector_eg1, sector_eg2, eg1, eg2
    if eps_fy1 is not None and eps_fy2 is not None:
        if _lt(e1, 0) and _gt(e2, 0) and _lt(e2, s2):
            return 7, None
        if _lt(e1, 0) and _eq(e2, s2):
            return 8, None
    if _gt(e1, s1) and _gt(e2, s2):
        if _gt(e2, e1):
            return 1, None
        if _eq(e2, e1):
            return 2, None
        if _lt(e2, e1):
            return 3, None
    if _eq(e1, s1) and _gt(e2, s2):
        return 4, None
    if _lt(e1, s1) and _gt(e2, s2):
        return 5, None
    if (
        _lt(e1, s1)
        and (_lt(e2, s2) or _eq(e2, s2))
        and _gt(e1, 0)
        and _gt(e2, 0)
    ):
        return 6, None
    return "unclassified", "earnings growth profile does not match any defined case"


def long_filter_steps(metrics, sector_means):
    pe1 = metrics["pe1"]
    pe2 = metrics["pe2"]
    eg1 = metrics["eg1"]
    eg2 = metrics["eg2"]
    peg1 = metrics["peg1"]
    tier = metrics["market_cap_tier"]
    mean_pe1 = sector_means["mean_pe1"]
    mean_pe2 = sector_means["mean_pe2"]
    mean_eg1 = sector_means["mean_eg1"]
    mean_eg2 = sector_means["mean_eg2"]
    pe_inputs = [pe1, pe2, mean_pe1, mean_pe2]
    eg_inputs = [eg1, eg2, mean_eg1, mean_eg2]
    steps = [
        {
            "name": "pe_premium_both_periods",
            "passed": (
                None
                if any(value is None for value in pe_inputs)
                else pe1 > mean_pe1 and pe2 > mean_pe2
            ),
            "detail": {
                "pe1": pe1,
                "mean_pe1": mean_pe1,
                "pe2": pe2,
                "mean_pe2": mean_pe2,
            },
        },
        {
            "name": "eg_above_sector_both_periods",
            "passed": (
                None
                if any(value is None for value in eg_inputs)
                else eg1 > mean_eg1 and eg2 > mean_eg2
            ),
            "detail": {
                "eg1": eg1,
                "mean_eg1": mean_eg1,
                "eg2": eg2,
                "mean_eg2": mean_eg2,
                "accelerating": (
                    None if eg1 is None or eg2 is None else eg2 > eg1
                ),
            },
        },
        {
            "name": "market_cap_mid_tier",
            "passed": None if tier is None else tier == "mid",
            "detail": {"tier": tier},
        },
        {
            "name": "peg1_above_1",
            "passed": None if peg1 is None else peg1 > 1,
            "detail": {"peg1": peg1},
        },
    ]
    return _finalize_steps(steps)


def short_filter_steps(metrics, sector_means):
    pe1 = metrics["pe1"]
    pe2 = metrics["pe2"]
    eg1 = metrics["eg1"]
    eg2 = metrics["eg2"]
    market_cap = metrics["market_cap"]
    mean_pe1 = sector_means["mean_pe1"]
    mean_pe2 = sector_means["mean_pe2"]
    mean_eg1 = sector_means["mean_eg1"]
    mean_eg2 = sector_means["mean_eg2"]
    pe_inputs = [pe1, pe2, mean_pe1, mean_pe2]
    eg_inputs = [eg1, eg2, mean_eg1, mean_eg2]
    steps = [
        {
            "name": "pe_discount_both_periods",
            "passed": (
                None
                if any(value is None for value in pe_inputs)
                else pe1 < mean_pe1 and pe2 < mean_pe2
            ),
            "detail": {
                "pe1": pe1,
                "mean_pe1": mean_pe1,
                "pe2": pe2,
                "mean_pe2": mean_pe2,
            },
        },
        {
            "name": "eg_below_sector_and_declining",
            "passed": (
                None
                if any(value is None for value in eg_inputs)
                else eg1 < mean_eg1 and eg2 < mean_eg2 and eg2 < eg1
            ),
            "detail": {
                "eg1": eg1,
                "mean_eg1": mean_eg1,
                "eg2": eg2,
                "mean_eg2": mean_eg2,
            },
        },
        {
            "name": "market_cap_large",
            "passed": (
                None if market_cap is None else market_cap >= 2e10
            ),
            "detail": {"market_cap": market_cap},
        },
    ]
    return _finalize_steps(steps)


def _finalize_steps(steps):
    first_failed = None
    for step in steps:
        if step["passed"] is not True and first_failed is None:
            first_failed = step["name"]
    return {
        "steps": steps,
        "first_failed": first_failed,
        "passes": all(step["passed"] is True for step in steps),
    }


def _compute_row(row):
    price = row["price"]
    market_cap = row["market_cap"]
    eps0 = row.get("eps_fy0")
    eps1 = row.get("eps_fy1")
    eps2 = row.get("eps_fy2")
    eps3 = row.get("eps_fy3")
    eg1, override1, small1 = _eg_with_flags(eps0, eps1)
    eg2, override2, small2 = _eg_with_flags(eps1, eps2)
    eg3, override3, small3 = _eg_with_flags(eps2, eps3)
    pe1 = _pe(price, eps1)
    pe2 = _pe(price, eps2)
    pe3 = _pe(price, eps3)
    peg1 = _peg(pe1, eg1)
    peg2 = _peg(pe2, eg2)
    peg3 = _peg(pe3, eg3)
    flags = []
    if override1 or override2 or override3:
        flags.append("sign_change_override")
    if small1 or small2 or small3:
        flags.append("small_base_review")
    metrics = {
        "symbol": row["symbol"],
        "price": price,
        "market_cap": market_cap,
        "market_cap_tier": _market_cap_tier(market_cap),
        "eps_fy0": eps0,
        "eps_fy1": eps1,
        "eps_fy2": eps2,
        "eps_fy3": eps3,
        "eg1": eg1,
        "eg2": eg2,
        "eg3": eg3,
        "pe1": pe1,
        "pe2": pe2,
        "pe3": pe3,
        "peg1": peg1,
        "peg2": peg2,
        "peg3": peg3,
        "flags": flags,
    }
    return {**row, "metrics": metrics}


def _present_row(row):
    metrics = row["metrics"]
    return {
        "symbol": metrics["symbol"],
        "price": metrics["price"],
        "market_cap": metrics["market_cap"],
        "market_cap_tier": metrics["market_cap_tier"],
        "eps_fy0": metrics["eps_fy0"],
        "eps_fy1": metrics["eps_fy1"],
        "eps_fy2": metrics["eps_fy2"],
        "eps_fy3": metrics["eps_fy3"],
        "eg1": metrics["eg1"],
        "eg2": metrics["eg2"],
        "eg3": metrics["eg3"],
        "pe1": metrics["pe1"],
        "pe2": metrics["pe2"],
        "pe3": metrics["pe3"],
        "peg1": metrics["peg1"],
        "peg2": metrics["peg2"],
        "peg3": metrics["peg3"],
        "flags": metrics["flags"],
        "eg_case": row["eg_case"],
        "eg_case_reason": row["eg_case_reason"],
        "long_filter": row["long_filter"],
        "short_filter": row["short_filter"],
    }


def _eg_with_flags(eps_prev, eps_next):
    if eps_prev is None or eps_next is None or eps_prev == 0:
        return None, False, False
    if eps_prev < 0 and eps_next >= 0:
        return 1.0, True, False
    if eps_prev > 0 and eps_next < 0:
        return -1.0, True, False
    value = (eps_next - eps_prev) / abs(eps_prev)
    return value, False, abs(value) > 2.0


def _pe(price, eps):
    if eps is None or eps == 0:
        return None
    return price / eps


def _peg(pe, eg):
    if pe is None or eg is None or eg == 0:
        return None
    return pe / (eg * 100)


def _market_cap_tier(market_cap):
    if market_cap is None or math.isnan(market_cap):
        return None
    for threshold, tier in _MARKET_CAP_TIERS:
        if market_cap < threshold:
            return tier
    if market_cap >= 4e10:
        return "mega"
    return None


def _sector_means(computed_rows):
    def mean(values):
        valid = [v for v in values if v is not None and not math.isnan(v)]
        return sum(valid) / len(valid) if valid else None

    return {
        "mean_pe1": mean([row["metrics"]["pe1"] for row in computed_rows]),
        "mean_pe2": mean([row["metrics"]["pe2"] for row in computed_rows]),
        "mean_eg1": mean([row["metrics"]["eg1"] for row in computed_rows]),
        "mean_eg2": mean([row["metrics"]["eg2"] for row in computed_rows]),
    }


def _leave_one_out_pe1(computed_rows, mean_all):
    if mean_all is None:
        return []
    pe1_by_symbol = [
        (row["metrics"]["symbol"], row["metrics"]["pe1"])
        for row in computed_rows
        if row["metrics"]["pe1"] is not None
    ]
    contributions = []
    for index, (symbol, _) in enumerate(pe1_by_symbol):
        without = [
            pe for other_index, (_, pe) in enumerate(pe1_by_symbol)
            if other_index != index
        ]
        if not without:
            continue
        mean_without = sum(without) / len(without)
        contributions.append({
            "symbol": symbol,
            "contribution": mean_all - mean_without,
        })
    contributions.sort(key=lambda item: -abs(item["contribution"]))
    return contributions


def _canonicalize_headers(fieldnames):
    normalized_to_canonical = {}
    for canonical, synonyms in _HEADER_SYNONYMS.items():
        for synonym in synonyms:
            normalized_to_canonical[_normalize_header(synonym)] = canonical
    canonical = {}
    for field in fieldnames:
        normalized = _normalize_header(field)
        if normalized in normalized_to_canonical:
            canonical[normalized_to_canonical[normalized]] = field
    return canonical


def _normalize_header(value):
    return " ".join(value.strip().lower().split())


def _parse_row(line_number, raw_row, canonical):
    symbol = _parse_symbol(raw_row.get(canonical.get("symbol")))
    if symbol is None:
        return None, {"line": line_number, "reason": "missing symbol"}
    price = _parse_number(raw_row.get(canonical.get("price")))
    market_cap = _parse_number(raw_row.get(canonical.get("market_cap")))
    eps_fy0 = _parse_number(raw_row.get(canonical.get("eps_fy0")))
    eps_fy1 = _parse_number(raw_row.get(canonical.get("eps_fy1")))
    eps_fy2 = _parse_number(raw_row.get(canonical.get("eps_fy2")))
    eps_fy3 = _parse_number(raw_row.get(canonical.get("eps_fy3")))
    required_values = [price, market_cap, eps_fy0, eps_fy1, eps_fy2]
    if all(value is None for value in required_values):
        return None, {
            "line": line_number,
            "reason": "all required numeric values missing",
        }
    row = {
        "symbol": symbol,
        "price": price,
        "market_cap": market_cap,
        "eps_fy0": eps_fy0,
        "eps_fy1": eps_fy1,
        "eps_fy2": eps_fy2,
    }
    if eps_fy3 is not None:
        row["eps_fy3"] = eps_fy3
    sector = raw_row.get(canonical.get("sector"))
    if sector is not None and str(sector).strip():
        row["sector"] = str(sector).strip()
    return row, None


def _parse_symbol(value):
    if value is None:
        return None
    symbol = str(value).strip().upper()
    return symbol if symbol else None


def _parse_number(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        if isinstance(value, float) and math.isnan(value):
            return None
        return float(value)
    cleaned = str(value).strip()
    if cleaned.lower() in _MISSING_TOKENS:
        return None
    for char in "$,%":
        cleaned = cleaned.replace(char, "")
    cleaned = cleaned.strip()
    if cleaned.lower() in _MISSING_TOKENS:
        return None
    try:
        parsed = float(cleaned)
        if math.isnan(parsed):
            return None
        return parsed
    except ValueError:
        return None


def _gt(a, b):
    return a > b + _TOL


def _lt(a, b):
    return a < b - _TOL


def _eq(a, b):
    return abs(a - b) <= _TOL

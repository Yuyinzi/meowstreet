import hashlib
import json
from calendar import monthrange
from datetime import datetime, timezone

import httpx

from app.http_client import HttpClient


API_BASE = "https://api.nfib-sbet.org:443/rest/sbetdb/_proc"
API_PROCEDURE = "getTotalsFullQuarter2"

REGIONS = {
    "pacific": {
        "statev": "AK,CA,HI,OR,WA",
        "display_label": "Pacific",
        "states": "AK, CA, HI, OR, WA",
    },
    "west_gulf": {
        "statev": "AR,LA,OK,TX",
        "display_label": "West Gulf (West South Central)",
        "states": "AR, LA, OK, TX",
    },
    "north_atlantic": {
        "statev": "CT,MA,ME,NH,NJ,NY,PA,RI,VT",
        "display_label": "North Atlantic (Northeast)",
        "states": "CT, MA, ME, NH, NJ, NY, PA, RI, VT",
    },
}

_VALID_REGION_IDS = set(REGIONS.keys())

OFFICIAL_INDICATORS = {
    "emp_count_change_expect": {
        "title": "Plans to Increase Employment",
        "units": "net_pct",
        "formula": "ans1_minus_ans3",
    },
    "expand_good": {
        "title": "Good Time to Expand",
        "units": "net_pct",
        "formula": "ans1",
    },
    "inventory_expect": {
        "title": "Plans to Increase Inventories",
        "units": "net_pct",
        "formula": "ans1plus2_minus_ans4plus5",
    },
    "bus_cond_expect": {
        "title": "Expect Economy to Improve",
        "units": "net_pct",
        "formula": "ans1plus2_minus_ans4plus5",
    },
    "sales_expect": {
        "title": "Expect Real Sales Higher",
        "units": "net_pct",
        "formula": "ans1plus2_minus_ans4plus5",
    },
    "cap_ex_expect": {
        "title": "Plans to Make Capital Expenditures",
        "units": "net_pct",
        "formula": "ans1",
    },
    "inventory_current": {
        "title": "Current Inventory Too Low",
        "units": "net_pct",
        "formula": "ans3_minus_ans1",
    },
    "job_opening_unfilled": {
        "title": "Current Job Openings",
        "units": "net_pct",
        "formula": "ans1plus2plus3",
    },
    "credit_access_expect": {
        "title": "Credit Conditions Expectation",
        "units": "net_pct",
        "formula": "ans1_minus_ans3",
    },
    "earn_change": {
        "title": "Earnings Trends",
        "units": "net_pct",
        "formula": "ans1plus2_minus_ans4plus5",
    },
}

_OPT_INDEX_QUESTIONS = ",".join(sorted(OFFICIAL_INDICATORS.keys()))

_LEADING_IDS = [
    "emp_count_change_expect",
    "expand_good",
    "inventory_expect",
    "bus_cond_expect",
    "sales_expect",
]

_CONTEXT_IDS = [
    "cap_ex_expect",
    "inventory_current",
    "job_opening_unfilled",
    "credit_access_expect",
    "earn_change",
]

SERIES_TO_INDICATOR = {
    "nfib_sbo_optimism": "OPT_INDEX",
    "nfib_sbo_employment_plans": "emp_count_change_expect",
    "nfib_sbo_expansion_outlook": "expand_good",
    "nfib_sbo_inventory_plans": "inventory_expect",
    "nfib_sbo_economic_expectations": "bus_cond_expect",
    "nfib_sbo_real_sales_expectations": "sales_expect",
    "nfib_sbo_capital_outlay_plans": "cap_ex_expect",
    "nfib_sbo_current_inventory_low": "inventory_current",
    "nfib_sbo_job_openings": "job_opening_unfilled",
    "nfib_sbo_credit_conditions_expectations": "credit_access_expect",
    "nfib_sbo_earnings_trends": "earn_change",
}

INDICATOR_TO_SERIES = {v: k for k, v in SERIES_TO_INDICATOR.items()}

ALL_SERIES_IDS = set(SERIES_TO_INDICATOR.keys())

_SEASONAL_INDEX = 1.095


def _positive_negative_formula(numerator_expr, answers):
    total = answers.get("total", 0)
    if not total:
        return 0
    if numerator_expr == "ans1":
        return (answers.get(1, 0) / total) * 100
    if numerator_expr == "ans3_minus_ans1":
        return ((answers.get(3, 0) - answers.get(1, 0)) / total) * 100
    if numerator_expr == "ans1_minus_ans3":
        return ((answers.get(1, 0) - answers.get(3, 0)) / total) * 100
    if numerator_expr == "ans1plus2plus3":
        return (
            (answers.get(1, 0) + answers.get(2, 0) + answers.get(3, 0)) / total
        ) * 100
    if numerator_expr == "ans1plus2_minus_ans4plus5":
        return (
            (
                answers.get(1, 0)
                + answers.get(2, 0)
                - answers.get(4, 0)
                - answers.get(5, 0)
            )
            / total
        ) * 100
    return 0


def _compute_net_percent(answers, question_code):
    meta = OFFICIAL_INDICATORS.get(question_code)
    if not meta:
        return 0
    return _positive_negative_formula(meta["formula"], answers)


def _group_by_period_distributions(rows):
    periods = {}
    for row in rows:
        y = row.get("time_year")
        q = row.get("time_quarter")
        m = row.get("time_month")
        q_short = row.get("resp_q_short")
        a_code = row.get("resp_acode")
        count = row.get("totalcount", 0)

        try:
            count = int(count)
        except (ValueError, TypeError):
            count = 0
        try:
            a_code = int(a_code)
        except (ValueError, TypeError):
            continue

        year = int(y)
        quarter = int(q)
        month = int(m)

        period_key = (year, quarter, month)
        periods.setdefault(period_key, {}).setdefault(q_short, {}).setdefault(a_code, 0)
        periods[period_key][q_short][a_code] = (
            periods[period_key][q_short].get(a_code, 0) + count
        )

    for pk in periods:
        for q_short in periods[pk]:
            total = sum(periods[pk][q_short].values())
            periods[pk][q_short]["total"] = total

    return periods


def _parse_distributions(rows):
    if not rows:
        return {}

    periods = _group_by_period_distributions(rows)
    sorted_periods = sorted(periods.keys())

    all_components = {}
    for pk in sorted_periods:
        dist = periods[pk]
        year, quarter, _ = pk
        _, last_day = monthrange(year, quarter * 3)
        date_key = f"{year:04d}-{quarter * 3:02d}-{last_day:02d}"

        component_values = {}
        for q_short, answers in dist.items():
            net_pct = round(_compute_net_percent(answers, q_short), 1)
            component_values[q_short] = net_pct

        if component_values:
            all_components[date_key] = component_values

    return all_components


def _compute_optimism_from_components(component_values):
    count_available = 0
    total = 0.0
    for q_short in list(_LEADING_IDS) + list(_CONTEXT_IDS):
        val = component_values.get(q_short)
        if val is not None:
            total += val
            count_available += 1
    if count_available != 10:
        return None
    return round((total / 10 + 100) / _SEASONAL_INDEX, 1)


def _build_observations(component_dict):
    result = []
    for date_key in sorted(component_dict.keys()):
        comps = component_dict[date_key]
        opt = _compute_optimism_from_components(comps)
        entry = {"date": date_key, "optimism": opt}
        for q_short in _LEADING_IDS + _CONTEXT_IDS:
            entry[q_short] = comps.get(q_short)
        entry["_availability"] = "available"
        result.append(entry)
    return result


def _build_request_body(region_id, start_year, end_year):
    region_info = REGIONS[region_id]
    return {
        "app_name": "sbet",
        "params": [
            {"name": "minYear", "param_type": "IN", "value": int(start_year)},
            {"name": "minMonth", "param_type": "IN", "value": 1},
            {"name": "maxYear", "param_type": "IN", "value": int(end_year)},
            {"name": "maxMonth", "param_type": "IN", "value": 12},
            {"name": "questions", "param_type": "IN", "value": _OPT_INDEX_QUESTIONS},
            {"name": "industry", "param_type": "IN", "value": ""},
            {"name": "employee", "param_type": "IN", "value": ""},
            {"name": "statev", "param_type": "IN", "value": region_info["statev"]},
        ],
    }


def _build_national_request_body(start_year, end_year):
    return {
        "app_name": "sbet",
        "params": [
            {"name": "minYear", "param_type": "IN", "value": int(start_year)},
            {"name": "minMonth", "param_type": "IN", "value": 1},
            {"name": "maxYear", "param_type": "IN", "value": int(end_year)},
            {"name": "maxMonth", "param_type": "IN", "value": 12},
            {"name": "questions", "param_type": "IN", "value": _OPT_INDEX_QUESTIONS},
            {"name": "industry", "param_type": "IN", "value": ""},
            {"name": "employee", "param_type": "IN", "value": ""},
            {"name": "statev", "param_type": "IN", "value": ""},
        ],
    }


def _hash_body(body):
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()


def validate_region_id(region_id):
    if region_id not in _VALID_REGION_IDS:
        raise ValueError(f"nfib regional api: unknown region id: {region_id}")


def _do_request(body, http_client=None):
    url = f"{API_BASE}/{API_PROCEDURE}"
    body_hash = _hash_body(body)
    retrieval_time = datetime.now(timezone.utc).isoformat()

    client = http_client or HttpClient()
    try:
        response = client.request(
            "POST",
            url,
            json=body,
            headers={"Content-Type": "application/json"},
            timeout=60,
        )
    except httpx.HTTPStatusError as exc:
        code = exc.response.status_code if exc.response is not None else "unknown"
        raise ValueError(f"nfib regional api: http {code}: {exc}") from exc
    except httpx.HTTPError as exc:
        raise ValueError(f"nfib regional api: connection failed: {exc}") from exc
    except Exception as exc:
        raise ValueError(f"nfib regional api: request failed: {exc}") from exc

    raw_bytes = response.content
    response_hash = hashlib.sha256(raw_bytes).hexdigest()
    try:
        raw = json.loads(raw_bytes.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError(f"nfib regional api: non-json response: {exc}") from exc

    if not isinstance(raw, list):
        raise ValueError("nfib regional api: response is not an array")

    return raw, body_hash, response_hash, retrieval_time, url


def fetch_regional_data(region_id, start_year, end_year, http_client=None):
    validate_region_id(region_id)
    body = _build_request_body(region_id, start_year, end_year)
    raw, body_hash, response_hash, retrieval_time, url = _do_request(body, http_client)
    component_dict = _parse_distributions(raw)
    observations = _build_observations(component_dict)
    return {
        "region_id": region_id,
        "start_year": start_year,
        "end_year": end_year,
        "frequency": "quarterly_3_month_aggregate",
        "retrieval_time": retrieval_time,
        "request_hash": body_hash,
        "response_hash": response_hash,
        "request_body": body,
        "provenance": {
            "url": url,
            "procedure": API_PROCEDURE,
            "retrieval_time": retrieval_time,
            "request_hash": body_hash,
            "response_hash": response_hash,
        },
        "observations": observations,
    }


def fetch_national_data(start_year, end_year, http_client=None):
    body = _build_national_request_body(start_year, end_year)
    raw, body_hash, response_hash, retrieval_time, url = _do_request(body, http_client)
    component_dict = _parse_distributions(raw)
    observations = _build_observations(component_dict)
    return {
        "region_id": "national",
        "start_year": start_year,
        "end_year": end_year,
        "frequency": "quarterly_3_month_aggregate",
        "retrieval_time": retrieval_time,
        "request_hash": body_hash,
        "response_hash": response_hash,
        "request_body": body,
        "provenance": {
            "url": url,
            "procedure": API_PROCEDURE,
            "retrieval_time": retrieval_time,
            "request_hash": body_hash,
            "response_hash": response_hash,
        },
        "observations": observations,
    }

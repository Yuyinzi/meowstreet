from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.tools.macro_data_freshness_daily import evaluate_daily_policy
from app.tools.macro_data_freshness_quarterly import evaluate_quarterly_policy


STATUS_LABELS = {"due": "Update due", "missing": "Missing", "processing": "Processing needed", "unknown": "Unknown", "current": "Fresh"}
_STATUS_ORDER = {key: index for index, key in enumerate(STATUS_LABELS)}


def _instant(value, zone=None):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        if zone is None:
            raise ValueError("timestamp timezone is required")
        parsed = parsed.replace(tzinfo=ZoneInfo(zone))
    return parsed


def _release_bounds(release, zone):
    precision = release["precision"]
    if precision == "exact":
        instant = _instant(release["at"], zone)
        return instant, instant
    start = datetime.combine(date.fromisoformat(release["at"]), time.min, ZoneInfo(zone))
    end = datetime.combine(date.fromisoformat(release.get("window_end") or release["at"]) + timedelta(days=1), time.min, ZoneInfo(zone))
    return start, end


def _release_payload(release, zone):
    if release is None:
        return None
    return {**release, "at": _instant(release["at"], zone).isoformat() if release["precision"] == "exact" else release["at"], "timezone": zone}


def _schedule_state(schedule, as_of):
    empty = {"expected_release": None, "next_release": None, "schedule_ambiguous": False, "schedule_covered": False}
    if not schedule.get("timezone") or not schedule.get("coverage_start") or not schedule.get("coverage_end"):
        return empty
    zone = schedule["timezone"]
    today = as_of.astimezone(ZoneInfo(zone)).date()
    if not date.fromisoformat(schedule["coverage_start"]) <= today <= date.fromisoformat(schedule["coverage_end"]):
        return empty
    ordered = sorted(schedule["releases"], key=lambda row: _release_bounds(row, zone)[0])
    known = []
    upcoming = []
    ambiguous = False
    for release in ordered:
        start, end = _release_bounds(release, zone)
        if end <= as_of:
            known.append(release)
        else:
            upcoming.append(release)
            ambiguous = ambiguous or start <= as_of < end
    return {
        "expected_release": _release_payload(known[-1], zone) if known else None,
        "next_release": _release_payload(upcoming[0], zone) if upcoming else None,
        "schedule_ambiguous": ambiguous,
        "schedule_covered": True,
    }


def _period_date(value, basis):
    normalized = f"{value}-01" if basis == "month" and isinstance(value, str) and len(value) == 7 else value
    return date.fromisoformat(normalized)


def _period_key(value, basis):
    parsed = _period_date(value, basis)
    if basis == "month":
        return parsed.year, parsed.month
    if basis == "quarter":
        return parsed.year, (parsed.month - 1) // 3
    return parsed.year, parsed.month, parsed.day


def _result(status, reason, schedule_state):
    return {"status": status, "status_label": STATUS_LABELS[status], "reason": reason, "expected_release": schedule_state["expected_release"], "next_release": schedule_state["next_release"]}


def _invalid_observation(observation, as_of, calendar=False, basis="date", observation_timezone="UTC"):
    period = observation.get("current_period")
    if period:
        try:
            today = as_of.astimezone(ZoneInfo(observation_timezone)).date()
            future = _period_key(period, basis) > _period_key(today.isoformat(), basis) if basis == "quarter" else _period_date(period, basis) > today
            if future and not calendar:
                return True
        except (KeyError, TypeError, ValueError):
            return True
    for key in ("retrieved_at", "generated_at"):
        if observation.get(key):
            try:
                if _instant(observation[key]) > as_of:
                    return True
            except (TypeError, ValueError):
                return True
    return False


def _evaluate_extraction(row, observation, expected, state, as_of):
    source = observation.get("source") or {}
    if source.get("availability") in {"unavailable", "invalid"} or _invalid_observation(source, as_of, basis=row["period_basis"]):
        return _result("unknown", "The corresponding source artifact is unavailable or invalid", state)
    source_period = source.get("current_period")
    if expected and source_period and _period_key(source_period, row["period_basis"]) < _period_key(expected["period"], row["period_basis"]):
        return _result("due", "A newer source report is expected under the verified publication schedule", state)
    if expected and source.get("availability") == "missing":
        return _result("due", "The source document expected under the verified publication schedule has not been stored", state)
    if source.get("availability") != "available":
        return _result("unknown", "A valid source artifact is required to assess the processing result", state)
    if not source.get("source_hash"):
        return _result("unknown", "Source version identity is unavailable", state)
    if observation.get("availability") == "unverified_empty":
        return _result("unknown", "No rows are stored and completion of this optional report section cannot be confirmed", state)
    if observation.get("availability") == "available" and not observation.get("source_hash"):
        return _result("unknown", "The processed output does not retain a verifiable source version", state)
    if observation.get("availability") == "missing" or source_period != observation.get("current_period") or source["source_hash"] != observation.get("source_hash"):
        return _result("processing", "The promoted result does not match the latest stored source period and version", state)
    return None


def evaluate_dataset(dataset, observation, schedule, as_of, calendars=None):
    observation = dict(observation or {"availability": "missing"})
    stored_period = None
    if dataset["period_basis"] == "weekly_resample" and observation.get("source_observation_date"):
        if _invalid_observation(observation, as_of, observation_timezone="Asia/Shanghai"):
            return _result("unknown", "The stored weekly label or collection evidence is invalid or future-dated", _schedule_state(schedule, as_of))
        stored_period = observation.get("current_period")
        observation["current_period"] = observation["source_observation_date"]
        dataset = {**dataset, "period_basis": "month" if dataset.get("lineage_transform") == "yoy" else "date"}
    result = _evaluate_dataset(dataset, observation, schedule, as_of, calendars or {})
    if stored_period:
        result.update(stored_period=stored_period, current_period=observation["current_period"])
    return result


def _evaluate_dataset(dataset, observation, schedule, as_of, calendars):
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("evaluation timestamp timezone is required")
    observation = observation or {"availability": "missing"}
    state = _schedule_state(schedule, as_of)
    expected = state["expected_release"]
    calendar = dataset["storage"]["kind"] == "fomc_calendar"
    availability = observation.get("availability")
    observation_timezone = (dataset.get("freshness_policy") or {}).get("timezone") or schedule.get("timezone") or "UTC"
    if availability in {"unavailable", "invalid"} or _invalid_observation(observation, as_of, calendar, dataset["period_basis"], observation_timezone):
        return _result("unknown", "Local evidence is unavailable, invalid, or future-dated", state)
    if dataset["storage"]["kind"] in {"fomc_extraction", "ism_output", "ism_report"} or dataset["storage"].get("survey"):
        extraction = _evaluate_extraction(dataset, observation, expected, state, as_of)
        if extraction is not None:
            return extraction
    if availability == "missing":
        return _result("missing", "No valid local observation has been stored for this dataset", state)
    if observation.get("lineage_basis") == "conflicting":
        return _result("unknown", "Conflicting source-date evidence requires a verified import before freshness can be established", state)
    if dataset.get("freshness_policy"):
        if dataset["freshness_policy"]["kind"] == "current_quarter":
            quarterly = evaluate_quarterly_policy(dataset, observation, as_of)
            return {**_result(quarterly["status"], quarterly["reason"], state), **quarterly}
        if dataset["period_basis"] == "weekly_resample":
            return _result("unknown", "The original source date for this resampled observation has not been verified", state)
        daily = evaluate_daily_policy(dataset, observation, as_of, calendars)
        if daily is not None:
            return {**_result(daily["status"], daily["reason"], state), **daily}
    if calendar:
        if not state["schedule_covered"]:
            return _result("unknown", "The verified meeting calendar does not cover this evaluation date", state)
        required = {r["period"] for r in schedule["releases"]}
        known = set(observation.get("event_periods") or [])
        if required <= known:
            return _result("current", "The local calendar includes all meetings in the verified schedule coverage", state)
        return _result("due", "The local meeting calendar is missing dates present in the verified schedule", state)
    if dataset["period_basis"] == "weekly_resample":
        return _result("unknown", "Weekly resampling labels do not establish the latest underlying source observation or revision", state)
    if not state["schedule_covered"]:
        return _result("unknown", "The publication calendar or its coverage is not verified for this date", state)
    if state["schedule_ambiguous"]:
        return _result("unknown", "The release date or publication window is in progress; publication time is not established", state)
    if not expected:
        return _result("unknown", "No latest expected release is established within the verified calendar coverage", state)
    if not observation.get("current_period"):
        return _result("unknown", "The observation period cannot be established", state)
    local = _period_key(observation["current_period"], dataset["period_basis"])
    target = _period_key(expected["period"], dataset["period_basis"])
    if local < target:
        return _result("due", "A newer period is expected under the verified publication schedule; actual provider publication is not confirmed", state)
    if local > target:
        return _result("unknown", "The stored period is ahead of the latest verified release requirement", state)
    if expected.get("version"):
        version = observation.get("version")
        if not version:
            return _result("unknown", "The period matches, but the required release version cannot be confirmed", state)
        if version != expected["version"]:
            return _result("due", "A newer release version is expected for the same observation period", state)
    return _result("current", "The stored period matches the latest expected release within verified calendar coverage", state)


def _dataset_payload(row, observation, history, schedules, as_of, calendars):
    result = evaluate_dataset(row, observation, schedules[row["schedule_id"]], as_of, calendars)
    fields = ("id", "name", "category", "source", "source_url", "frequency", "storage_frequency", "period_basis")
    payload = {key: row[key] for key in fields}
    payload.update({key: observation.get(key) for key in ("current_period", "release_date", "retrieved_at", "generated_at", "version", "source_observation_date", "lineage_basis")})
    payload.update(result)
    if result.get("stored_period"):
        payload["period_basis"] = "month" if row.get("lineage_transform") == "yoy" else "date"
    payload["schedule"] = {key: schedules[row["schedule_id"]].get(key) for key in ("source_url", "source_urls", "verified_at", "coverage_start", "coverage_end", "timezone", "note")}
    payload["history"] = history or {"availability": "unavailable", "last_successful_check": None, "last_attempt": None, "last_processing": None}
    payload["evidence_availability"] = observation.get("availability", "missing")
    return payload


def build_overview(catalog, observations, tasks, as_of):
    rows = [_dataset_payload(row, observations.get(row["id"], {"availability": "missing"}), tasks.get(row["id"]), catalog["schedules"], as_of, catalog.get("market_calendars", {})) for row in catalog["datasets"]]
    rows.sort(key=lambda row: (_STATUS_ORDER[row["status"]], row["category"], row["name"], row["id"]))
    unavailable = sum(row["evidence_availability"] in {"unavailable", "invalid"} for row in rows)
    history_unavailable = any(row["history"].get("availability") == "unavailable" for row in rows)
    return {
        "version": catalog["version"], "as_of": as_of.astimezone(UTC).isoformat(), "timezone": "Asia/Shanghai",
        "availability": "partial" if unavailable or history_unavailable else "available",
        "unavailable_datasets": unavailable, "history_available": not history_unavailable,
        "statuses": [{"code": key, "label": label} for key, label in STATUS_LABELS.items()],
        "counts": {key: sum(row["status"] == key for row in rows) for key in STATUS_LABELS},
        "categories": sorted({row["category"] for row in rows}), "datasets": rows,
        "collection_schedules": catalog["collection_schedules"],
    }

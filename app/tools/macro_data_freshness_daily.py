from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo


def _result(status, reason, basis, **fields):
    return {"status": status, "status_label": {"current": "Fresh", "due": "Update due", "unknown": "Unknown"}[status], "reason": reason, "comparison_basis": basis, **fields}


def _completed_observation(observation, today, sessions=None):
    candidates = [observation, *observation.get("recent_observations", [])]
    valid = [item for item in candidates if item.get("current_period") and date.fromisoformat(item["current_period"]) < today and (sessions is None or item["current_period"] in sessions) and item.get("availability", "available") == "available"]
    return max(valid, key=lambda row: row["current_period"], default=None)


def _session_policy(policy, observation, as_of, calendars):
    basis = "Completed exchange sessions; next-local-day 08:00 monitoring deadline"
    calendar = calendars.get(policy["calendar_id"])
    if not calendar:
        return _result("unknown", "The exchange calendar is unavailable", basis)
    zone = ZoneInfo(calendar["timezone"])
    local = as_of.astimezone(zone)
    start, end = date.fromisoformat(calendar["coverage_start"]), date.fromisoformat(calendar["coverage_end"])
    if not start <= local.date() <= end:
        return _result("unknown", "The exchange calendar does not cover this evaluation date", basis)
    holidays = set(calendar["holidays"])
    days = [start + timedelta(days=n) for n in range((end - start).days + 1)]
    sessions = [day for day in days if day.weekday() < 5 and day.isoformat() not in holidays]
    deadlines = [(day, datetime.combine(day + timedelta(days=1), time(8), zone)) for day in sessions]
    elapsed = [day for day, deadline in deadlines if deadline <= local]
    if not elapsed:
        return _result("unknown", "No completed session deadline is established in calendar coverage", basis)
    expected = max(elapsed).isoformat()
    selected = _completed_observation(observation, local.date(), {d.isoformat() for d in sessions})
    following = next((deadline.isoformat() for _, deadline in deadlines if deadline > local), None)
    details = {"expected_period": expected, "policy_timezone": calendar["timezone"], "policy_source_url": calendar["source_url"], "freshness_deadline": following}
    if not selected:
        return _result("unknown", "No complete daily observation is stored; a current-day row may be intraday", basis, **details)
    current = selected["current_period"]
    return _result("current" if current >= expected else "due", "The stored completed session meets the monitoring deadline" if current >= expected else "A later completed session is expected under the exchange calendar and monitoring deadline", basis, current_period=current, **details)


def evaluate_daily_policy(dataset, observation, as_of, calendars):
    policy = dataset.get("freshness_policy")
    if not policy:
        return None
    basis = "Source-date monitoring window"
    try:
        if as_of.tzinfo is None:
            raise ValueError("timezone is required")
        local = as_of.astimezone(ZoneInfo(policy["timezone"]))
        observed = date.fromisoformat(observation["current_period"])
        if observed > local.date():
            return _result("unknown", "The source observation date is in the future", basis)
        if policy["kind"] == "session":
            return _session_policy(policy, observation, as_of, calendars)
        selected = observation
        if dataset["storage"]["kind"] == "benchmark":
            selected = _completed_observation(observation, local.date())
            if selected is None:
                return _result("unknown", "No complete daily observation is stored", basis)
        observed = date.fromisoformat(selected["current_period"])
        age = (local.date() - observed).days
        maximum = policy["max_age_days"]
        basis = f"Source-date monitoring window: {maximum} calendar days"
        return _result("current" if age <= maximum else "due", "The source date is within the configured timeliness window; latest upstream publication is not independently confirmed" if age <= maximum else "The source date exceeds the configured timeliness window; check the source and collection history", basis, current_period=selected["current_period"], policy_timezone=policy["timezone"], source_age_days=age, max_age_days=maximum, freshness_deadline=(observed + timedelta(days=maximum + 1)).isoformat())
    except (KeyError, TypeError, ValueError):
        return _result("unknown", "The source date or monitoring policy cannot be evaluated", basis)

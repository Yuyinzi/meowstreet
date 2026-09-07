from datetime import date


_CHANNELS = ("press_releases", "events_presentations")
_MONTHS_PER_QUARTER = 3
_MONTHS_PER_YEAR = 12
_DAYS_PER_MONTH = 30.4375
_STATES = ("earnings", "non_earnings", "ambiguous")


def _parse_date(value):
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _requested_dates(requested_window):
    if not isinstance(requested_window, dict):
        raise ValueError("requested window is required")
    start = _parse_date(requested_window.get("start") or requested_window.get("requested_start"))
    end = _parse_date(requested_window.get("end") or requested_window.get("requested_end"))
    if start is None or end is None or start > end:
        raise ValueError("requested window is invalid")
    return start, end


def _source_for_type(sources, source_type):
    if isinstance(sources, dict):
        source = sources.get(source_type)
        return source if isinstance(source, dict) else None
    if not isinstance(sources, list):
        return None
    return next((source for source in sources if isinstance(source, dict) and source.get("source_type") == source_type), None)


def _continuity_is_known(source):
    for key in ("coverage_continuous", "continuity_known", "continuous"):
        if key in source:
            return source[key] is True
    for key in ("continuity", "coverage_continuity", "coverage_status"):
        value = source.get(key)
        if isinstance(value, str):
            return value.strip().casefold() in {"continuous", "known", "verified"}
    return False


def _round_rate(value):
    return float(round(value, 2))


def _empty_channel(status):
    return {
        "status": status,
        "window_months": None,
        "total": 0,
        "earnings": 0,
        "non_earnings": 0,
        "ambiguous": 0,
        "per_year": None,
        "per_quarter": None,
        "per_month": None,
        "non_earnings_per_year": None,
        "non_earnings_per_quarter": None,
        "non_earnings_per_month": None,
    }


def _channel_statistics(events, source, requested_start, requested_end):
    if source is None:
        return _empty_channel("missing")
    extraction_status = source.get("extraction_status")
    if extraction_status is None and source.get("coverage_status") in {"complete", "partial"}:
        extraction_status = source.get("coverage_status")
    if extraction_status is None:
        extraction_status = source.get("status")
    if extraction_status not in {None, "complete", "partial"}:
        return _empty_channel(extraction_status or "missing")
    if extraction_status == "partial":
        start = _parse_date(source.get("coverage_start"))
        end = _parse_date(source.get("coverage_end"))
        status = "partial"
        continuity_known = start is not None and end is not None and start < end and _continuity_is_known(source)
        denominator_days = (end - start).days if continuity_known else None
    else:
        start = requested_start
        end = requested_end
        status = "complete"
        continuity_known = True
        denominator_days = (end - start).days
    counts = {state: 0 for state in _STATES}
    for event in events:
        state = event.get("earnings_state")
        if state in counts:
            counts[state] += 1
    total = sum(counts.values())
    result = {
        "status": status,
        "window_months": _round_rate(denominator_days / _DAYS_PER_MONTH) if denominator_days is not None else None,
        "total": total,
        **counts,
        "per_year": None,
        "per_quarter": None,
        "per_month": None,
        "non_earnings_per_year": None,
        "non_earnings_per_quarter": None,
        "non_earnings_per_month": None,
    }
    if denominator_days is None or denominator_days <= 0 or not continuity_known:
        return result
    months = denominator_days / _DAYS_PER_MONTH
    result.update(
        {
            "per_year": _round_rate(total / months * _MONTHS_PER_YEAR),
            "per_quarter": _round_rate(total / months * _MONTHS_PER_QUARTER),
            "per_month": _round_rate(total / months),
        }
    )
    if counts["ambiguous"] == 0:
        result.update(
            {
                "non_earnings_per_year": _round_rate(counts["non_earnings"] / months * _MONTHS_PER_YEAR),
                "non_earnings_per_quarter": _round_rate(counts["non_earnings"] / months * _MONTHS_PER_QUARTER),
                "non_earnings_per_month": _round_rate(counts["non_earnings"] / months),
            }
        )
    return result


def calculate_statistics(events, sources, requested_window) -> dict:
    if not isinstance(events, list):
        raise ValueError("events are required")
    requested_start, requested_end = _requested_dates(requested_window)
    return {
        source_type: _channel_statistics(
            [event for event in events if isinstance(event, dict) and event.get("source_type") == source_type],
            _source_for_type(sources, source_type),
            requested_start,
            requested_end,
        )
        for source_type in _CHANNELS
    }

from collections.abc import Mapping
from datetime import date

from app.agents.catalyst_research.domain import _fold_whitespace
from app.agents.catalyst_research.domain import canonicalize_public_url


_CHANNELS = ("press_releases", "events_presentations")
_SOURCE_TYPES = ("ir_home", "press_releases", "events_presentations", "earnings_results")
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
        if sources is not None:
            raise ValueError("sources are invalid")
        return None
    if any(not isinstance(source, Mapping) for source in sources):
        raise ValueError("source is invalid")
    if any(source.get("source_type") not in _SOURCE_TYPES for source in sources):
        raise ValueError("source type is invalid")
    matching = [source for source in sources if source.get("source_type") == source_type]
    if len(matching) > 1:
        raise ValueError(f"duplicate source {source_type}")
    return matching[0] if matching else None


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
    if extraction_status not in {"complete", "partial"}:
        return _empty_channel(extraction_status or "unknown")
    if extraction_status == "partial":
        start = _parse_date(source.get("coverage_start"))
        end = _parse_date(source.get("coverage_end"))
        if start is None or end is None or not requested_start <= start < end <= requested_end:
            raise ValueError("partial coverage range is invalid")
        status = "partial"
        continuity_known = _continuity_is_known(source)
        denominator_days = (end - start).days if continuity_known else None
    else:
        start = requested_start
        end = requested_end
        status = "complete"
        continuity_known = True
        denominator_days = (end - start).days
    counts = {state: 0 for state in _STATES}
    for event in events:
        if status == "partial":
            event_date = _parse_date(event.get("count_date"))
            if event_date is None or not start <= event_date <= end:
                raise ValueError("event count date is outside observed coverage")
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
    if isinstance(sources, dict):
        source_rows = []
        for source_type, source in sources.items():
            if source_type not in _SOURCE_TYPES:
                raise ValueError("source type is invalid")
            if not isinstance(source, Mapping):
                raise ValueError("source is invalid")
            source_rows.append({**source, "source_type": source_type})
        sources = source_rows
    elif sources is not None and not isinstance(sources, list):
        raise ValueError("sources are invalid")
    validated_events = []
    seen_keys = set()
    for event in events:
        if not isinstance(event, Mapping):
            raise ValueError("event is invalid")
        source_type = event.get("source_type")
        if source_type not in _CHANNELS:
            raise ValueError("event source type is invalid")
        if event.get("earnings_state") not in _STATES:
            raise ValueError("event earnings state is invalid")
        count_date_value = event.get("count_date")
        if count_date_value is None and event.get("date") is not None:
            count_date_value = event.get("date")
        count_date = _parse_date(count_date_value)
        if count_date is None:
            raise ValueError("event count date is invalid")
        if event.get("count_date") is not None and event.get("date") is not None:
            date_value = _parse_date(event.get("date"))
            if date_value is None or date_value != count_date:
                raise ValueError("event count date is inconsistent")
        if not requested_start <= count_date <= requested_end:
            raise ValueError("event count date is outside requested window")
        title = " ".join(str(event.get("title") or "").split())
        if not title:
            raise ValueError("event title is required")
        normalized_title = event.get("normalized_title")
        if normalized_title is None:
            normalized_title = title.casefold()
        expected_normalized_title = _fold_whitespace(title).casefold()
        if not isinstance(normalized_title, str) or not normalized_title.strip():
            raise ValueError("event normalized title is required")
        if normalized_title != expected_normalized_title:
            raise ValueError("event normalized title is inconsistent")
        supplied_url = event.get("canonical_url") or event.get("url")
        if source_type == "press_releases" and not supplied_url:
            raise ValueError("event url is required")
        canonical_url = canonicalize_public_url(supplied_url) if supplied_url else None
        if event.get("canonical_url") and canonicalize_public_url(event["canonical_url"]) != canonical_url:
            raise ValueError("event canonical url is inconsistent")
        key = (source_type, count_date.isoformat(), normalized_title.casefold(), canonical_url)
        if key in seen_keys:
            raise ValueError("duplicate event observation")
        seen_keys.add(key)
        validated_events.append({**event, "count_date": count_date.isoformat(), "canonical_url": canonical_url})
    return {
        source_type: _channel_statistics(
            [event for event in validated_events if event.get("source_type") == source_type],
            _source_for_type(sources, source_type),
            requested_start,
            requested_end,
        )
        for source_type in _CHANNELS
    }

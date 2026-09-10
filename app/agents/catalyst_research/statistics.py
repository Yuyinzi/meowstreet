from collections.abc import Mapping
from datetime import date
from statistics import median

from app.agents.catalyst_research.domain import _fold_whitespace
from app.agents.catalyst_research.domain import canonicalize_public_url


_CHANNELS = ("press_releases", "events_presentations")
_EVENT_CHANNELS = ("press_releases", "events_presentations", "earnings_results")
_SOURCE_TYPES = ("ir_home", "press_releases", "events_presentations", "earnings_results")
_MONTHS_PER_QUARTER = 3
_MONTHS_PER_YEAR = 12
_DAYS_PER_MONTH = 30.4375
_STATES = ("earnings", "non_earnings", "ambiguous")
_V1_1_COVERAGE_STATUSES = ("complete", "observed_partial", "missing", "unsupported")
_DISCOVERY_METHODS = ("rss", "atom", "search", "archive_adapter", "manual")
_COVERAGE_WARNING = "search and feed history may omit official records"


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


def _observed_range(source, requested_start, requested_end):
    raw_start = _parse_date(source.get("observed_start"))
    raw_end = _parse_date(source.get("observed_end"))
    if (raw_start is None) != (raw_end is None):
        raise ValueError("observed range is invalid")
    if raw_start is None:
        return None, None
    if raw_start > raw_end:
        raise ValueError("observed range is invalid")
    start = max(raw_start, requested_start)
    end = min(raw_end, requested_end)
    if start > end:
        raise ValueError("observed range is outside requested window")
    return start, end


def _observed_discovery_methods(source):
    methods = source.get("discovery_methods")
    if methods is None:
        return []
    if not isinstance(methods, list) or any(method not in _DISCOVERY_METHODS for method in methods):
        raise ValueError("discovery methods are invalid")
    unique = []
    for method in methods:
        if method not in unique:
            unique.append(method)
    return unique


def _observed_channel_statistics(events, source, requested_start, requested_end):
    coverage_status = source.get("coverage_status")
    if coverage_status not in _V1_1_COVERAGE_STATUSES:
        raise ValueError("coverage status is invalid")
    methods = _observed_discovery_methods(source)
    start, end = _observed_range(source, requested_start, requested_end)
    counts = {state: 0 for state in _STATES}
    non_earnings_days = []
    for event in events:
        state = event.get("earnings_state")
        if state in counts:
            counts[state] += 1
        if state == "non_earnings":
            non_earnings_days.append(_parse_date(event.get("count_date")))
    result = {
        "coverage_status": coverage_status,
        "discovery_methods": methods,
        "observed_start": start.isoformat() if start else None,
        "observed_end": end.isoformat() if end else None,
        "observed_total": sum(counts.values()),
        "observed_earnings": counts["earnings"],
        "observed_non_earnings": counts["non_earnings"],
        "observed_non_earnings_per_year": None,
        "observed_non_earnings_per_quarter": None,
        "observed_non_earnings_per_month": None,
        "median_days_between_observed_non_earnings": None,
    }
    if coverage_status in {"observed_partial", "missing"}:
        result["coverage_warning"] = _COVERAGE_WARNING
    span_days = (end - start).days if start and end else None
    if span_days is None or span_days <= 0:
        return result
    if counts["non_earnings"] == 0 and coverage_status != "complete":
        return result
    months = span_days / _DAYS_PER_MONTH
    result.update(
        {
            "observed_non_earnings_per_year": _round_rate(counts["non_earnings"] / months * _MONTHS_PER_YEAR),
            "observed_non_earnings_per_quarter": _round_rate(counts["non_earnings"] / months * _MONTHS_PER_QUARTER),
            "observed_non_earnings_per_month": _round_rate(counts["non_earnings"] / months),
        }
    )
    if len(non_earnings_days) >= 2:
        gaps = [
            (later - earlier).days
            for earlier, later in zip(sorted(non_earnings_days), sorted(non_earnings_days)[1:])
        ]
        result["median_days_between_observed_non_earnings"] = _round_rate(median(gaps))
    return result


def _merged_channel_sources(events, stored_channels):
    grouped = {}
    for event in events:
        if not isinstance(event, Mapping):
            raise ValueError("event is invalid")
        grouped.setdefault(event.get("source_type"), []).append(event)
    sources = []
    for channel, channel_events in grouped.items():
        if channel not in _EVENT_CHANNELS:
            raise ValueError("event source type is invalid")
        stored = stored_channels.get(channel) or {}
        days = sorted(str(event.get("count_date")) for event in channel_events)
        methods = list(stored.get("discovery_methods") or [])
        for event in channel_events:
            method = event.get("discovery_method")
            if method and method not in methods:
                methods.append(method)
        sources.append(
            _channel_evidence_source(
                channel,
                coverage_status="observed_partial",
                discovery_methods=methods,
                observed_start=days[0],
                observed_end=days[-1],
            )
        )
    for channel, stored in stored_channels.items():
        if channel in grouped:
            continue
        if channel not in _EVENT_CHANNELS:
            raise ValueError("source type is invalid")
        if not isinstance(stored, Mapping):
            raise ValueError("stored channel is invalid")
        sources.append(
            _channel_evidence_source(
                channel,
                coverage_status=stored.get("coverage_status") or "missing",
                discovery_methods=stored.get("discovery_methods") or [],
                observed_start=None,
                observed_end=None,
            )
        )
    return sources


def _channel_evidence_source(
    channel, *, coverage_status, discovery_methods, observed_start, observed_end
):
    return {
        "source_type": channel,
        "coverage_status": coverage_status,
        "discovery_methods": list(discovery_methods),
        "observed_start": observed_start,
        "observed_end": observed_end,
    }


def calculate_accumulated_statistics(events, stored_channels, requested_window) -> dict:
    if not isinstance(events, list):
        raise ValueError("events are required")
    if not isinstance(stored_channels, dict):
        raise ValueError("stored channels are required")
    sources = _merged_channel_sources(events, stored_channels)
    return calculate_statistics(events, sources, requested_window)


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
        if source_type not in _EVENT_CHANNELS:
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
    def _channel(source_type):
        source = _source_for_type(sources, source_type)
        channel_events = [event for event in validated_events if event.get("source_type") == source_type]
        if source is not None and "coverage_status" in source:
            return _observed_channel_statistics(channel_events, source, requested_start, requested_end)
        return _channel_statistics(channel_events, source, requested_start, requested_end)

    reported_channels = list(_CHANNELS)
    earnings_reported = any(event.get("source_type") == "earnings_results" for event in validated_events)
    if isinstance(sources, list):
        earnings_reported = earnings_reported or any(
            isinstance(source, Mapping)
            and source.get("source_type") == "earnings_results"
            and "coverage_status" in source
            for source in sources
        )
    if earnings_reported:
        reported_channels.append("earnings_results")
    return {source_type: _channel(source_type) for source_type in reported_channels}

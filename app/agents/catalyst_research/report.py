from collections.abc import Mapping


def _text(value):
    return str(value).strip() if isinstance(value, str) and str(value).strip() else None


def _attention_sources(result):
    sources = result.get("sources")
    if not isinstance(sources, list):
        return []
    return [dict(source) for source in sources if isinstance(source, Mapping) and source.get("extraction_status") == "failed"]


def _channel_lines(statistics):
    if not isinstance(statistics, Mapping):
        return []
    lines = []
    for channel in ("press_releases", "events_presentations", "earnings_results"):
        stats = statistics.get(channel)
        if not isinstance(stats, Mapping):
            continue
        observed = stats.get("observed_total")
        start = stats.get("observed_start") or "?"
        end = stats.get("observed_end") or "?"
        lines.append(f"- {channel}: {stats.get('coverage_status', 'unknown')} ({observed} observed, {start}..{end})")
    return lines


def render_report(result):
    if not isinstance(result, Mapping):
        raise ValueError("result is required")
    lines = ["# Catalyst research report", ""]
    header = [
        ("ticker", result.get("ticker")),
        ("job_id", result.get("job_id")),
        ("status", result.get("status")),
        ("mode", result.get("mode")),
        ("completed_at", result.get("completed_at")),
        ("observations", result.get("observation_count")),
    ]
    window = result.get("requested_window")
    if isinstance(window, Mapping):
        header.append(("window", f"{window.get('start')}..{window.get('end')}"))
    for key, value in header:
        if value is not None:
            lines.append(f"- {key}: {value}")
    channel_lines = _channel_lines(result.get("statistics"))
    if channel_lines:
        lines += ["", "## Channel coverage", ""] + channel_lines
    attention = _attention_sources(result)
    lines += ["", f"## Manual review required ({len(attention)})", ""]
    if attention:
        for source in attention:
            reason = _text(source.get("verification_reason"))
            suffix = f" ({reason})" if reason and reason != "manual_review_required" else ""
            lines.append(f"- [{source.get('source_type', 'unknown')}] {source.get('url', '')}{suffix}")
    else:
        lines.append("- none")
    warnings = [warning for warning in result.get("warnings") or [] if isinstance(warning, str)]
    if warnings:
        lines += ["", "## Warnings", ""] + [f"- {warning}" for warning in warnings]
    actions = [action for action in result.get("next_actions") or [] if isinstance(action, str)]
    if actions:
        lines += ["", "## Next actions", ""] + [f"- {action}" for action in actions]
    return "\n".join(lines) + "\n"

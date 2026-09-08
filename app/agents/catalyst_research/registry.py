from datetime import UTC, datetime

_VALID_CHANNELS = frozenset({"press_releases", "events_presentations", "earnings_results"})
_VALID_ENDPOINT_TYPES = frozenset({"rss", "atom", "search_domain", "archive"})
_FEED_ENDPOINT_TYPES = frozenset({"rss", "atom"})
_VALID_STATUSES = frozenset({"unverified", "active", "quiet", "stale", "failing", "retired"})
_USABLE_STATUSES = frozenset({"active", "quiet"})
_VALID_OUTCOMES = frozenset({"success_new", "success_empty", "request_failed", "parse_failed"})
_FAILURE_OUTCOMES = frozenset({"request_failed", "parse_failed"})
_ERROR_CODES = frozenset(
    {
        "request_failed",
        "parse_failed",
        "http_error",
        "timeout",
        "redirect_rejected",
        "domain_not_approved",
        "oversized_response",
        "invalid_format",
    }
)
FEED_FAILURE_THRESHOLD = 3


def approved_domains(registry):
    if not isinstance(registry, dict):
        raise ValueError("registry must be a dict")
    domains = registry.get("official_domains")
    if not isinstance(domains, list):
        raise ValueError("registry official domains must be a list")
    normalized = set()
    for domain in domains:
        if not isinstance(domain, str) or not domain.strip():
            raise ValueError("registry official domains must be non-empty strings")
        normalized.add(domain.strip().casefold())
    return frozenset(normalized)


def registry_ready(registry, endpoints):
    if not isinstance(registry, dict) or not isinstance(endpoints, list):
        return False
    try:
        domains = approved_domains(registry)
    except ValueError:
        return False
    if not domains:
        return False
    return any(
        _usable_feed_endpoint(endpoint, domains)
        for endpoint in endpoints
        if isinstance(endpoint, dict)
    )


def _usable_feed_endpoint(endpoint, domains):
    domain = endpoint.get("domain")
    return (
        endpoint.get("channel") in _VALID_CHANNELS
        and endpoint.get("endpoint_type") in _FEED_ENDPOINT_TYPES
        and endpoint.get("status") in _USABLE_STATUSES
        and isinstance(domain, str)
        and domain.strip().casefold() in domains
    )


def transition_endpoint(endpoint, check, *, gap_found=False, replacement_validated=False):
    _validate_endpoint(endpoint)
    outcome = str(check.get("outcome") or "").strip()
    if outcome not in _VALID_OUTCOMES:
        raise ValueError(f"endpoint check outcome {outcome!r} is not supported")
    checked_at = check.get("checked_at")
    _parse_timestamp(checked_at, "checked_at", "endpoint check")
    newest_item_at = check.get("newest_item_at")
    if newest_item_at is not None:
        _parse_timestamp(newest_item_at, "newest_item_at", "endpoint check")
    result = dict(endpoint)
    result["last_checked_at"] = checked_at
    result["updated_at"] = checked_at
    status = endpoint["status"]
    if replacement_validated or status == "retired":
        result["status"] = "retired"
        return result
    failures = int(endpoint.get("consecutive_failures") or 0)
    if outcome in _FAILURE_OUTCOMES:
        failures += 1
        result["consecutive_failures"] = failures
        error_code = str(check.get("error_code") or "").strip()
        result["last_error_code"] = error_code if error_code in _ERROR_CODES else None
        if failures >= FEED_FAILURE_THRESHOLD and status in frozenset({"active", "quiet"}):
            result["status"] = "failing"
        return result
    result["consecutive_failures"] = 0
    result["last_error_code"] = None
    result["last_success_at"] = checked_at
    if outcome == "success_new":
        if newest_item_at is not None:
            result["last_item_at"] = newest_item_at
        result["status"] = "active"
        return result
    if status in frozenset({"active", "quiet"}):
        result["status"] = "stale" if gap_found else "quiet"
    elif status in frozenset({"stale", "failing"}):
        result["status"] = "active"
    return result


def feed_due(endpoint, as_of):
    if not isinstance(endpoint, dict):
        raise ValueError("endpoint must be a dict")
    if not isinstance(as_of, datetime):
        raise ValueError("as_of must be a datetime")
    if endpoint.get("endpoint_type") not in _FEED_ENDPOINT_TYPES:
        return False
    last_checked_at = endpoint.get("last_checked_at")
    if last_checked_at is None:
        return True
    last_checked = _parse_timestamp(last_checked_at, "last_checked_at", "endpoint")
    as_of_normalized = as_of.replace(tzinfo=UTC) if as_of.tzinfo is None else as_of.astimezone(UTC)
    return as_of_normalized.date() > last_checked.date()


def _validate_endpoint(endpoint):
    if not isinstance(endpoint, dict):
        raise ValueError("endpoint must be a dict")
    status = endpoint.get("status")
    if status not in _VALID_STATUSES:
        raise ValueError(f"endpoint status {status!r} is not supported")
    channel = endpoint.get("channel")
    if channel not in _VALID_CHANNELS:
        raise ValueError(f"endpoint channel {channel!r} is not supported")
    endpoint_type = endpoint.get("endpoint_type")
    if endpoint_type not in _VALID_ENDPOINT_TYPES:
        raise ValueError(f"endpoint endpoint_type {endpoint_type!r} is not supported")


def _parse_timestamp(value, field, subject):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{subject} {field} is required")
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError as exc:
        raise ValueError(f"{subject} {field} is malformed") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)

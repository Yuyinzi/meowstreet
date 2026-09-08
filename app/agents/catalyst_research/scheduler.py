from datetime import UTC, datetime

from app.agents.catalyst_research.backfill import _router_executor
from app.agents.catalyst_research.extraction.feeds import fetch_feed as _default_fetch_feed
from app.agents.catalyst_research.persistence.repository import record_endpoint_check as _record_endpoint_check
from app.agents.catalyst_research.persistence.repository import update_endpoint_health as _update_endpoint_health
from app.agents.catalyst_research.registry import approved_domains
from app.agents.catalyst_research.registry import feed_due
from app.agents.catalyst_research.registry import transition_endpoint
from app.agents.catalyst_research.search_planner import filter_official_candidates
from app.agents.catalyst_research.search_planner import gap_queries

_FEED_ENDPOINT_TYPES = frozenset({"rss", "atom"})
_FAILURE_OUTCOMES = frozenset({"request_failed", "parse_failed"})
_PARSE_FAILURE_MESSAGES = frozenset(
    {"feed xml is invalid", "feed body is empty", "feed content type is not xml"}
)
_DEFAULT_MAX_URLS = 200
_GAP_ATTEMPT_PROVIDER = "search_router"
_GAP_ATTEMPT_PURPOSE = "incremental_gap_check"
_HEALTH_FIELDS = (
    "status",
    "last_checked_at",
    "last_success_at",
    "last_item_at",
    "last_guid",
    "last_error_code",
    "consecutive_failures",
    "updated_at",
)


def _normalize_as_of(as_of):
    if not isinstance(as_of, datetime):
        raise ValueError("as_of must be a datetime")
    if as_of.tzinfo is None:
        return as_of.replace(tzinfo=UTC)
    return as_of.astimezone(UTC)


def _parse_gap_time(value, channel):
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"latest gap search time for {channel} is malformed")
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError as exc:
        raise ValueError(f"latest gap search time for {channel} is malformed") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _gap_interval_days(config):
    if not isinstance(config, dict):
        raise ValueError("collection config is required")
    value = config.get("gap_search_interval_days", 7)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("collection config gap search interval days is invalid")
    return value


def update_plan(endpoints, latest_gap_search, as_of, config):
    if not isinstance(endpoints, list):
        raise ValueError("endpoints must be a list")
    if not isinstance(latest_gap_search, dict):
        raise ValueError("latest gap search times must be a dict")
    as_of_utc = _normalize_as_of(as_of)
    interval_days = _gap_interval_days(config)
    feed_endpoint_ids = []
    items = []
    for endpoint in endpoints:
        if not isinstance(endpoint, dict):
            raise ValueError("endpoint must be a dict")
        if endpoint.get("endpoint_type") not in _FEED_ENDPOINT_TYPES:
            continue
        if endpoint.get("status") == "retired":
            continue
        endpoint_id = endpoint.get("endpoint_id")
        if not isinstance(endpoint_id, str) or not endpoint_id.strip():
            raise ValueError("endpoint id is required")
        if not feed_due(endpoint, as_of_utc):
            continue
        feed_endpoint_ids.append(endpoint_id)
        items.append(
            {"reason": "daily_feed", "endpoint_id": endpoint_id, "channel": endpoint.get("channel")}
        )
    gap_reasons = {}
    for endpoint in endpoints:
        if not isinstance(endpoint, dict):
            raise ValueError("endpoint must be a dict")
        if endpoint.get("endpoint_type") not in _FEED_ENDPOINT_TYPES:
            continue
        if endpoint.get("status") == "retired":
            continue
        channel = endpoint.get("channel")
        if channel in gap_reasons:
            continue
        status = endpoint.get("status")
        if status == "failing":
            gap_reasons[channel] = "feed_failure"
            continue
        if status == "stale":
            gap_reasons[channel] = "feed_stale"
            continue
        last_gap = _parse_gap_time(latest_gap_search.get(channel), channel)
        if last_gap is None or (as_of_utc.date() - last_gap.date()).days >= interval_days:
            gap_reasons[channel] = "weekly_gap"
    gap_channels = list(gap_reasons)
    for channel, reason in gap_reasons.items():
        items.append({"reason": reason, "channel": channel})
    return {
        "as_of": as_of_utc.isoformat(),
        "feed_endpoint_ids": feed_endpoint_ids,
        "gap_channels": gap_channels,
        "items": items,
    }


async def run_daily_update(company, *, registry, endpoints, as_of, config, dependencies):
    if not isinstance(company, dict):
        raise ValueError("company is required")
    if not isinstance(dependencies, dict):
        raise ValueError("dependencies must be a dict")
    domains = approved_domains(registry)
    as_of_utc = _normalize_as_of(as_of)
    latest_gap_search = dependencies.get("latest_gap_search") or {}
    plan = update_plan(endpoints, latest_gap_search, as_of_utc, config)
    endpoints_by_id = {}
    for endpoint in endpoints:
        if not isinstance(endpoint, dict):
            raise ValueError("endpoint must be a dict")
        endpoints_by_id[endpoint.get("endpoint_id")] = endpoint
    fetcher = dependencies.get("fetch_feed") or _default_fetch_feed
    ingester = dependencies.get("ingest_candidates")
    router = dependencies.get("extraction_router")
    feed_results = []
    gap_reasons = {
        item["channel"]: item["reason"]
        for item in plan["items"]
        if item["reason"] != "daily_feed"
    }
    for endpoint_id in plan["feed_endpoint_ids"]:
        endpoint = endpoints_by_id[endpoint_id]
        check, event_count = await _run_feed_check(
            endpoint, fetcher, ingester, router, dependencies, company, domains, as_of_utc, config
        )
        _persist_check(dependencies, check)
        state = transition_endpoint(endpoint, check)
        _persist_health(dependencies, endpoint_id, state)
        if check["outcome"] in _FAILURE_OUTCOMES:
            gap_reasons.setdefault(endpoint["channel"], "feed_failure")
        feed_results.append(
            {
                "endpoint_id": endpoint_id,
                "channel": endpoint["channel"],
                "outcome": check["outcome"],
                "status": state["status"],
                "item_count": check["item_count"],
                "new_item_count": event_count,
                "error_code": check.get("error_code"),
            }
        )
    gap_results = []
    if gap_reasons:
        executor = dependencies.get("execute_query")
        if executor is None and dependencies.get("search_router") is not None:
            executor = _router_executor(dependencies["search_router"])
        if executor is None:
            raise ValueError("execute_query is required for gap search")
        for channel, reason in gap_reasons.items():
            gap_results.append(
                await _run_gap_search(
                    executor, ingester, router, dependencies, company, domains, channel, reason, as_of_utc, config
                )
            )
    return {"as_of": as_of_utc.isoformat(), "plan": plan, "feeds": feed_results, "gaps": gap_results}


async def _run_feed_check(endpoint, fetcher, ingester, router, dependencies, company, domains, as_of_utc, config):
    checked_at = as_of_utc.isoformat()
    try:
        parsed = await fetcher(
            endpoint, http_client=dependencies.get("http_client"), approved_domains=domains
        )
    except ValueError as exc:
        message = str(exc).strip().casefold()
        outcome = "parse_failed" if message in _PARSE_FAILURE_MESSAGES else "request_failed"
        return (
            {
                "endpoint_id": endpoint["endpoint_id"],
                "checked_at": checked_at,
                "outcome": outcome,
                "item_count": 0,
                "new_item_count": 0,
                "error_code": outcome,
            },
            0,
        )
    except Exception:
        return (
            {
                "endpoint_id": endpoint["endpoint_id"],
                "checked_at": checked_at,
                "outcome": "request_failed",
                "item_count": 0,
                "new_item_count": 0,
                "error_code": "request_failed",
            },
            0,
        )
    items = parsed.get("items") or []
    events = []
    if items:
        if ingester is None:
            raise ValueError("ingest_candidates is required when a feed returns items")
        events = await _ingest(ingester, items, company, endpoint["channel"], router, dependencies, endpoint=endpoint, config=config)
    outcome = "success_new" if events else "success_empty"
    return (
        {
            "endpoint_id": endpoint["endpoint_id"],
            "checked_at": checked_at,
            "outcome": outcome,
            "item_count": len(items),
            "new_item_count": len(events),
            "newest_item_at": parsed.get("newest_item_at"),
            "content_hash": parsed.get("content_hash"),
        },
        len(events),
    )


async def _run_gap_search(executor, ingester, router, dependencies, company, domains, channel, reason, as_of_utc, config):
    queries = gap_queries(company, channel, list(domains), as_of_utc.date(), config)
    rows = []
    outcomes = []
    for query in queries:
        try:
            result_rows = await executor(query)
        except Exception:
            outcomes.append("provider_error")
            continue
        result_rows = list(result_rows or [])
        outcomes.append("candidate_results" if result_rows else "empty_results")
        rows.extend(result_rows)
    _record_gap_attempts(dependencies, queries, outcomes, as_of_utc)
    candidates = filter_official_candidates(
        rows, company=company, channel=channel, approved_domains=domains
    )
    events = []
    if candidates:
        if ingester is None:
            raise ValueError("ingest_candidates is required when gap search finds candidates")
        events = await _ingest(ingester, candidates, company, channel, router, dependencies, endpoint=None, config=config)
    return {
        "channel": channel,
        "reason": reason,
        "query_count": len(queries),
        "candidate_count": len(candidates),
        "event_count": len(events),
    }


def _gap_attempt_recorder(dependencies):
    recorder = dependencies.get("record_search_attempt")
    if recorder is not None:
        return recorder
    repository = dependencies.get("repository")
    connection = dependencies.get("connection")
    method = getattr(repository, "record_search_attempt", None)
    if not callable(method) or connection is None:
        return None
    return lambda attempt: method(connection, attempt)


def _record_gap_attempts(dependencies, queries, outcomes, as_of_utc):
    job_id = (dependencies.get("job") or {}).get("job_id")
    if not job_id:
        return
    recorder = _gap_attempt_recorder(dependencies)
    if recorder is None:
        return
    for query, outcome in zip(queries, outcomes):
        recorder(
            {
                "job_id": job_id,
                "provider": _GAP_ATTEMPT_PROVIDER,
                "query": query.get("query") or "",
                "requested_limit": query.get("result_limit"),
                "started_at": as_of_utc.isoformat(),
                "completed_at": as_of_utc.isoformat(),
                "outcome": outcome,
                "diagnostics": {"reason": outcome},
                "search_purpose": _GAP_ATTEMPT_PURPOSE,
            }
        )


async def _ingest(ingester, candidates, company, channel, router, dependencies, *, endpoint=None, config=None):
    result = await ingester(
        candidates,
        company=company,
        channel=channel,
        endpoint=endpoint,
        job=dependencies.get("job") or {},
        extraction_router=router,
        repository=dependencies.get("repository"),
        connection=dependencies.get("connection"),
        max_urls=(config or {}).get("max_unseen_urls_per_channel", _DEFAULT_MAX_URLS),
    )
    if isinstance(result, dict):
        return list(result.get("events") or [])
    return list(result or [])


def _persist_check(dependencies, check):
    recorder = dependencies.get("record_endpoint_check")
    if recorder is not None:
        return recorder(check)
    connection = dependencies.get("connection")
    if connection is None:
        raise ValueError("connection is required to record endpoint checks")
    return _record_endpoint_check(connection, check)


def _persist_health(dependencies, endpoint_id, state):
    updater = dependencies.get("update_endpoint_health")
    health = {key: state[key] for key in _HEALTH_FIELDS if key in state}
    if updater is not None:
        return updater(endpoint_id, health)
    connection = dependencies.get("connection")
    if connection is None:
        raise ValueError("connection is required to update endpoint health")
    return _update_endpoint_health(connection, endpoint_id, health)

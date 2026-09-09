import inspect
from datetime import date

from app.agents.catalyst_research.extraction.feeds import fetch_feed as _default_fetch_feed
from app.agents.catalyst_research.ingestion import _approved_domains as _company_domains
from app.agents.catalyst_research.ingestion import _count_date as _candidate_count_date
from app.agents.catalyst_research.ingestion import _date_value
from app.agents.catalyst_research.ingestion import deduplicate_candidates
from app.agents.catalyst_research.ingestion import ingest_candidates as _default_ingest_candidates
from app.agents.catalyst_research.search_planner import filter_official_candidates
from app.agents.catalyst_research.search_planner import historical_queries


_CHANNELS = ("press_releases", "events_presentations", "earnings_results")
_FEED_ENDPOINT_TYPES = frozenset({"rss", "atom"})
_LIMIT_ORDER = ("historical_query_limit", "search_result_limit", "unseen_url_limit")
_PARTIAL_WARNING = "search and feed history may omit official records"
_DEFAULT_MAX_URLS = 200


def _requested_window(request):
    start = request.get("requested_start")
    end = request.get("requested_end")
    if start is None or end is None:
        raise ValueError("requested window is required")
    try:
        start_date = date.fromisoformat(str(start).strip())
        end_date = date.fromisoformat(str(end).strip())
    except ValueError:
        raise ValueError("requested window is invalid") from None
    if start_date > end_date:
        raise ValueError("requested window is invalid")
    return start_date, end_date


def _feed_endpoints(endpoints, channel):
    return [
        endpoint
        for endpoint in endpoints
        if endpoint.get("channel") == channel
        and endpoint.get("endpoint_type") in _FEED_ENDPOINT_TYPES
        and endpoint.get("status") != "retired"
    ]


async def _collect_feed_candidates(feed_endpoints, domains, dependencies):
    fetcher = dependencies.get("fetch_feed") or _default_fetch_feed
    http_client = dependencies.get("http_client")
    candidates = []
    warnings = []
    for endpoint in feed_endpoints:
        try:
            fetched = fetcher(endpoint, http_client=http_client, approved_domains=domains)
            parsed = await fetched if inspect.isawaitable(fetched) else fetched
        except Exception:
            warnings.append("feed_fetch_failed")
            continue
        candidates.extend(dict(item) for item in parsed.get("items") or [])
    return candidates, warnings


def _router_executor(router):
    async def execute(query):
        last_error = None
        for provider in router.provider_chain():
            try:
                return await provider.search(query["query"], limit=query.get("result_limit"))
            except Exception as exc:
                last_error = exc
        if last_error is not None:
            raise last_error
        raise ValueError("search provider is unavailable")

    return execute


async def _execute_search_plan(company, channel, domains, window, config, dependencies):
    plan = historical_queries(company, channel, list(domains), window, config)
    limits = set()
    if plan["truncated"]:
        limits.add("historical_query_limit")
    executor = dependencies.get("execute_query")
    if executor is None and dependencies.get("search_router") is not None:
        executor = _router_executor(dependencies["search_router"])
    answered = False
    rows = []
    if executor is not None:
        for query in plan["queries"]:
            try:
                result_rows = await executor(query)
            except Exception:
                continue
            answered = True
            result_rows = list(result_rows or [])
            limit = query.get("result_limit")
            if isinstance(limit, int) and not isinstance(limit, bool) and len(result_rows) > limit:
                limits.add("search_result_limit")
                result_rows = result_rows[:limit]
            rows.extend(result_rows)
    candidates = filter_official_candidates(rows, company=company, channel=channel, approved_domains=domains)
    return {"candidates": candidates, "answered": answered, "limits": limits}


def _filter_window(candidates, window_start, window_end):
    kept = []
    dropped = 0
    for candidate in candidates:
        counted = _candidate_count_date(candidate)
        if counted is None:
            kept.append(candidate)
            continue
        try:
            day = date.fromisoformat(counted)
        except ValueError:
            kept.append(candidate)
            continue
        if window_start <= day <= window_end:
            kept.append(candidate)
        else:
            dropped += 1
    return kept, dropped


async def _run_adapter(dependencies, config, company, request, channel):
    if not config.get("archive_enrichment_enabled"):
        return None, None
    runner = dependencies.get("adapter") or dependencies.get("run_adapter")
    if runner is None:
        return None, None
    try:
        result = await runner(channel=channel, company=company, request=request)
    except Exception:
        return None, "archive_adapter_failed"
    if not isinstance(result, dict):
        return None, "archive_adapter_failed"
    if result.get("status") == "stale":
        return result, "archive_adapter_failed"
    return result, None


def _adapter_boundary_proven(result):
    if not isinstance(result, dict) or result.get("status") == "stale":
        return False
    layers = [result, result.get("execution") or {}, result.get("validation") or {}]
    if any(isinstance(layer, dict) and layer.get("truncation_reason") for layer in layers):
        return False
    return any(
        isinstance(layer, dict) and bool(layer.get("boundary_reached") or layer.get("archive_exhausted"))
        for layer in layers
    )


def _adapter_events(result):
    if not isinstance(result, dict) or result.get("status") == "stale":
        return []
    events = []
    for event in result.get("events") or []:
        if not isinstance(event, dict):
            continue
        row = dict(event)
        methods = [method for method in row.get("discovery_methods") or [] if isinstance(method, str)]
        if "archive_adapter" not in methods:
            methods.append("archive_adapter")
        row["discovery_methods"] = methods
        row.setdefault("discovery_method", "archive_adapter")
        events.append(row)
    return events


def _event_day(event):
    for key in ("count_date", "published_date", "event_date", "published_at"):
        day = _date_value(event.get(key))
        if day:
            return day
    return None


def _merge_channel_evidence(ingested, adapter_result, *, feed_present, search_answered, extra_warnings, limits):
    events = [dict(event) for event in ingested.get("events") or []]
    sources = [dict(source) for source in ingested.get("sources") or []]
    warnings = list(ingested.get("warnings") or []) + list(extra_warnings)
    events.extend(_adapter_events(adapter_result))
    adapter_source = adapter_result.get("source") if isinstance(adapter_result, dict) else None
    if isinstance(adapter_source, dict):
        sources.append(dict(adapter_source))
    boundary = _adapter_boundary_proven(adapter_result)
    reachable = feed_present or search_answered
    if boundary:
        status = "complete"
    elif events:
        status = "observed_partial"
    elif reachable:
        status = "missing"
    else:
        status = "unsupported"
    if status == "observed_partial" and _PARTIAL_WARNING not in warnings:
        warnings.append(_PARTIAL_WARNING)
    methods = []
    for event in events:
        discovered = event.get("discovery_methods") or []
        if not discovered and event.get("discovery_method"):
            discovered = [event.get("discovery_method")]
        for method in discovered:
            if method and method not in methods:
                methods.append(method)
    days = sorted({day for day in (_event_day(event) for event in events) if day})
    return {
        "coverage_status": status,
        "discovery_methods": methods,
        "observed_start": days[0] if days else None,
        "observed_end": days[-1] if days else None,
        "events": events,
        "sources": sources,
        "warnings": warnings,
        "limit_state": [name for name in _LIMIT_ORDER if name in limits],
        "archive_boundary_proven": boundary,
    }


async def _backfill_channel(company, request, channel, *, endpoints, domains, window, config, dependencies):
    window_start, window_end = window
    feed_endpoints = _feed_endpoints(endpoints, channel)
    feed_candidates, feed_warnings = await _collect_feed_candidates(feed_endpoints, domains, dependencies)
    search = await _execute_search_plan(
        company,
        channel,
        domains,
        {"start": window_start.isoformat(), "end": window_end.isoformat()},
        config,
        dependencies,
    )
    candidates = deduplicate_candidates(feed_candidates + search["candidates"])
    candidates, dropped = _filter_window(candidates, window_start, window_end)
    warnings = list(feed_warnings)
    if dropped:
        warnings.append("outside_requested_window")
    ingester = dependencies.get("ingest_candidates") or _default_ingest_candidates
    max_urls = config.get("max_unseen_urls_per_channel", _DEFAULT_MAX_URLS)
    ingested = await ingester(
        candidates,
        company=company,
        channel=channel,
        endpoint=feed_endpoints[0] if feed_endpoints else None,
        job=dependencies.get("job") or {},
        extraction_router=dependencies.get("extraction_router"),
        repository=dependencies.get("repository"),
        connection=dependencies.get("connection"),
        max_urls=max_urls,
    )
    if not isinstance(ingested, dict):
        raise ValueError("ingest result is invalid")
    adapter_result, adapter_warning = await _run_adapter(dependencies, config, company, request, channel)
    extra_warnings = warnings + ([adapter_warning] if adapter_warning else [])
    limits = set(search["limits"])
    if ingested.get("truncated"):
        limits.add("unseen_url_limit")
    return _merge_channel_evidence(
        ingested,
        adapter_result,
        feed_present=bool(feed_endpoints),
        search_answered=search["answered"],
        extra_warnings=extra_warnings,
        limits=limits,
    )


async def run_historical_backfill(company, request, *, endpoints, config, dependencies):
    if not isinstance(company, dict) or not str(company.get("ticker") or "").strip():
        raise ValueError("company ticker is required")
    if not isinstance(request, dict):
        raise ValueError("request is required")
    if not isinstance(endpoints, list):
        raise ValueError("endpoints must be a list")
    for endpoint in endpoints:
        if not isinstance(endpoint, dict):
            raise ValueError("endpoint must be a dict")
    if not isinstance(config, dict):
        raise ValueError("collection config is required")
    if not isinstance(dependencies, dict):
        raise ValueError("dependencies must be a dict")
    window = _requested_window(request)
    domains = _company_domains(company)
    ticker = str(company["ticker"]).strip().upper()
    channels = {}
    for channel in _CHANNELS:
        channels[channel] = await _backfill_channel(
            company,
            request,
            channel,
            endpoints=endpoints,
            domains=domains,
            window=window,
            config=config,
            dependencies=dependencies,
        )
    warnings = []
    for channel in _CHANNELS:
        for warning in channels[channel]["warnings"]:
            if warning not in warnings:
                warnings.append(warning)
    return {
        "ticker": ticker,
        "requested_window": {"start": window[0].isoformat(), "end": window[1].isoformat()},
        "channels": channels,
        "warnings": warnings,
    }

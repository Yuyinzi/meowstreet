from collections.abc import Mapping
from datetime import UTC, date, datetime
from urllib.parse import urlsplit

from app.agents.catalyst_research.domain import canonicalize_public_url
from app.agents.catalyst_research.extraction.articles import strip_title_site_prefix


_CHANNELS = {"press_releases", "events_presentations", "earnings_results"}
_FEED_ENDPOINT_TYPES = {"rss", "atom"}
_MAX_URLS = 500
_DEFAULT_MAX_URLS = 200


def _fold(value):
    return " ".join(str(value or "").split())


def _normalized_ticker(candidate):
    return str(candidate.get("ticker") or "").strip().upper() or None


def _normalized_title(title):
    return _fold(title).casefold()


def _seen_event_titles(repository, connection, ticker, company):
    if not callable(getattr(repository, "list_event_normalized_titles", None)):
        return None
    titles = _repository_call(repository, connection, "list_event_normalized_titles", ticker)
    if not isinstance(titles, list):
        return None
    return {_normalized_title(strip_title_site_prefix(title, company)) for title in titles}


def _date_value(value):
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if not isinstance(value, str) or not value.strip():
        return None
    cleaned = value.strip()
    try:
        return date.fromisoformat(cleaned).isoformat()
    except ValueError:
        try:
            return datetime.fromisoformat(cleaned.replace("Z", "+00:00")).date().isoformat()
        except ValueError:
            return None


def _datetime_value(value):
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime(value.year, value.month, value.day)
    elif isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            parsed_date = _date_value(value)
            if parsed_date is None:
                return None
            parsed = datetime.fromisoformat(parsed_date)
    else:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _count_date(candidate):
    channel = candidate.get("channel")
    if channel == "events_presentations":
        return _date_value(candidate.get("event_date")) or _date_value(candidate.get("published_at") or candidate.get("published_date"))
    return _date_value(candidate.get("published_at") or candidate.get("published_date") or candidate.get("event_date"))


def _canonical_candidate_url(candidate):
    raw = candidate.get("canonical_url") or candidate.get("url")
    if raw is None or not str(raw).strip():
        return None
    try:
        return canonicalize_public_url(str(raw))
    except ValueError:
        return None


def _discovery_methods(candidate):
    methods = []
    for value in candidate.get("discovery_methods") or []:
        if isinstance(value, str) and value and value not in methods:
            methods.append(value)
    single = candidate.get("discovery_method")
    if isinstance(single, str) and single and single not in methods:
        methods.append(single)
    return methods


def candidate_identity(candidate):
    if not isinstance(candidate, Mapping):
        raise ValueError("candidate is invalid")
    canonical_url = _canonical_candidate_url(candidate)
    if canonical_url is not None:
        return ("url", _normalized_ticker(candidate), canonical_url)
    endpoint_id = _fold(candidate.get("endpoint_id"))
    external_guid = _fold(candidate.get("external_guid"))
    if endpoint_id and external_guid:
        return ("guid", endpoint_id, external_guid)
    return (
        "title",
        _normalized_ticker(candidate),
        _normalized_title(candidate.get("title")),
        _count_date(candidate) or "",
    )


def _conflicted_guid_keys(rows):
    grouped = {}
    for row in rows:
        endpoint_id = _fold(row.get("endpoint_id"))
        external_guid = _fold(row.get("external_guid"))
        if not endpoint_id or not external_guid:
            continue
        signature = (_canonical_candidate_url(row) or "", _normalized_title(row.get("title")))
        grouped.setdefault((endpoint_id, external_guid), set()).add(signature)
    return {key for key, signatures in grouped.items() if len(signatures) > 1}


def _identity_for(row, conflicted_guids):
    canonical_url = row.get("canonical_url")
    if canonical_url is not None:
        return ("url", _normalized_ticker(row), canonical_url)
    endpoint_id = _fold(row.get("endpoint_id"))
    external_guid = _fold(row.get("external_guid"))
    if endpoint_id and external_guid and (endpoint_id, external_guid) not in conflicted_guids:
        return ("guid", endpoint_id, external_guid)
    return (
        "title",
        _normalized_ticker(row),
        _normalized_title(row.get("title")),
        _count_date(row) or "",
    )


def _identity_sort_key(identity):
    return tuple(str(value) for value in identity)


def deduplicate_candidates(candidates):
    if not isinstance(candidates, list):
        raise ValueError("candidates are required")
    rows = []
    for candidate in candidates:
        if not isinstance(candidate, Mapping):
            raise ValueError("candidate is invalid")
        row = dict(candidate)
        row["canonical_url"] = _canonical_candidate_url(row)
        row["discovery_methods"] = _discovery_methods(row)
        rows.append(row)
    conflicted_guids = _conflicted_guid_keys(rows)
    merged = {}
    for row in rows:
        identity = _identity_for(row, conflicted_guids)
        existing = merged.get(identity)
        if existing is None:
            merged[identity] = row
            continue
        for method in row["discovery_methods"]:
            if method not in existing["discovery_methods"]:
                existing["discovery_methods"].append(method)
    return sorted(merged.values(), key=lambda row: _identity_sort_key(_identity_for(row, conflicted_guids)))


def _is_feed_metadata_candidate(row):
    methods = set(row.get("discovery_methods") or [])
    if not methods or not methods <= _FEED_ENDPOINT_TYPES:
        return False
    if not _fold(row.get("title")):
        return False
    return _count_date(row) is not None


def _primary_discovery_method(row):
    methods = row.get("discovery_methods") or []
    return methods[0] if methods else None


def _approved_domains(company):
    raw = company.get("official_domains")
    if raw is None:
        raw = company.get("approved_domains")
    if raw is None:
        raise ValueError("approved domains are required")
    domains = set()
    for value in raw:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("approved domain is invalid")
        domains.add(value.strip().casefold().rstrip("."))
    if not domains:
        raise ValueError("approved domains are required")
    return domains


def _repository_call(repository, connection, name, *args):
    method = getattr(repository, name, None)
    if not callable(method):
        raise ValueError(f"repository method {name} is unavailable")
    return method(connection, *args)


def _url_path_key(canonical):
    parsed = urlsplit(canonical)
    return (parsed.netloc.casefold(), (parsed.path.rstrip("/") or "/").casefold())


def _endpoint_url_keys(repository, connection, ticker):
    if not callable(getattr(repository, "load_source_endpoints", None)):
        return set()
    endpoints = _repository_call(repository, connection, "load_source_endpoints", ticker)
    keys = set()
    for endpoint in endpoints or []:
        if not isinstance(endpoint, Mapping):
            continue
        url = endpoint.get("url")
        if not url:
            continue
        try:
            keys.add(_url_path_key(canonicalize_public_url(str(url))))
        except ValueError:
            continue
    return keys


def _event_dates(row, channel, *, published_at=None):
    published = _date_value(published_at if published_at is not None else (row.get("published_at") or row.get("published_date")))
    event_date = _date_value(row.get("event_date")) if channel == "events_presentations" else None
    if channel == "events_presentations":
        count_date = event_date or published
    else:
        count_date = published
    return published, event_date, count_date


def _event_candidate(row, *, ticker, channel, source, title, published, event_date, count_date, canonical_url, final_url, extraction_provider, content_hash=None):
    return {
        "ticker": ticker,
        "source_type": channel,
        "title": title,
        "normalized_title": _normalized_title(title),
        "published_date": published,
        "event_date": event_date,
        "count_date": count_date,
        "canonical_url": canonical_url,
        "url": canonical_url,
        "final_url": final_url,
        "source_id": source["source_id"],
        "endpoint_id": row.get("endpoint_id"),
        "external_guid": row.get("external_guid"),
        "discovery_method": _primary_discovery_method(row),
        "discovery_methods": list(row.get("discovery_methods") or []),
        "extraction_provider": extraction_provider,
        "content_hash": content_hash,
    }


def _source_payload(row, *, ticker, channel, job_id, url, final_url, acceptance_status, extraction_status, extraction_provider, verification_reason, checked_at, attempts=None, content_hash=None):
    return {
        "job_id": job_id,
        "ticker": ticker,
        "source_type": channel,
        "url": url,
        "final_url": final_url,
        "acceptance_status": acceptance_status,
        "extraction_status": extraction_status,
        "endpoint_id": row.get("endpoint_id"),
        "external_guid": row.get("external_guid"),
        "discovery_method": _primary_discovery_method(row),
        "extraction_provider": extraction_provider,
        "verification_reason": verification_reason,
        "checked_at": checked_at,
        "item_count": 1,
        "attempts": [dict(attempt) for attempt in attempts or [] if isinstance(attempt, Mapping)],
        "content_hash": content_hash,
    }


def _save_source(repository, connection, payload):
    return _repository_call(repository, connection, "save_source", payload)


def _save_extraction_snapshot(repository, connection, result, *, url, final_url):
    text = _fold(result.get("text"))
    if not text or not callable(getattr(repository, "save_snapshot", None)):
        return None
    snapshot = {
        "requested_url": url,
        "final_url": final_url,
        "content_type": "text/markdown",
        "normalized": {
            "text": text,
            "title": result.get("title"),
            "published_at": result.get("published_at"),
        },
        "snapshot_schema_version": "catalyst_extraction_v1",
    }
    html = result.get("html")
    if isinstance(html, str) and html.strip():
        snapshot["raw_html"] = html
    return _repository_call(repository, connection, "save_snapshot", snapshot)


def _advance_feed_watermark(rows, *, endpoint, repository, connection):
    if not isinstance(endpoint, Mapping):
        return
    endpoint_id = endpoint.get("endpoint_id")
    if not endpoint_id or endpoint.get("endpoint_type") not in _FEED_ENDPOINT_TYPES:
        return
    dated = []
    for row in rows:
        published = _datetime_value(row.get("published_at") or row.get("published_date"))
        if published is not None:
            dated.append((published, row))
    if not dated:
        return
    newest, newest_row = max(dated, key=lambda item: item[0])
    state = {"last_item_at": newest.isoformat()}
    external_guid = _fold(newest_row.get("external_guid"))
    if external_guid:
        state["last_guid"] = external_guid
    _repository_call(repository, connection, "update_endpoint_health", endpoint_id, state)


async def ingest_candidates(candidates, *, company, channel, endpoint, job, extraction_router, repository, connection, max_urls=_DEFAULT_MAX_URLS):
    if not isinstance(candidates, list):
        raise ValueError("candidates are required")
    if not isinstance(company, Mapping) or not _fold(company.get("ticker")):
        raise ValueError("company ticker is required")
    if channel not in _CHANNELS:
        raise ValueError("channel is invalid")
    if endpoint is not None and not isinstance(endpoint, Mapping):
        raise ValueError("endpoint is invalid")
    if not isinstance(job, Mapping) or not _fold(job.get("job_id")):
        raise ValueError("job id is required")
    if not callable(getattr(extraction_router, "extract", None)):
        raise ValueError("extraction router is required")
    if repository is None or connection is None:
        raise ValueError("repository connection is required")
    if isinstance(max_urls, bool) or not isinstance(max_urls, int) or not 1 <= max_urls <= _MAX_URLS:
        raise ValueError("max urls must be between 1 and 500")
    ticker = str(company["ticker"]).strip().upper()
    job_id = str(job["job_id"]).strip()
    approved_domains = _approved_domains(company)
    stamped = []
    for candidate in candidates:
        if not isinstance(candidate, Mapping):
            raise ValueError("candidate is invalid")
        row = dict(candidate)
        row.setdefault("ticker", ticker)
        row.setdefault("channel", channel)
        stamped.append(row)
    rows = deduplicate_candidates(stamped)
    events = []
    sources = []
    attempted = 0
    skipped_seen = 0
    skipped_duplicates = 0
    skipped_archive = 0
    manual_review = 0
    warnings = []
    truncated = False
    processed = []
    seen_titles = _seen_event_titles(repository, connection, ticker, company)
    endpoint_keys = _endpoint_url_keys(repository, connection, ticker)
    for row in rows:
        if attempted >= max_urls:
            truncated = True
            warnings.append("unseen_url_limit")
            break
        canonical_url = row.get("canonical_url")
        if canonical_url is not None and (
            _repository_call(repository, connection, "event_url_seen", ticker, canonical_url)
            or _repository_call(repository, connection, "source_url_seen", ticker, canonical_url)
        ):
            skipped_seen += 1
            processed.append(row)
            continue
        if canonical_url is not None and _url_path_key(canonical_url) in endpoint_keys:
            skipped_archive += 1
            processed.append(row)
            continue
        processed.append(row)
        if canonical_url is None:
            manual_review += 1
            attempted += 1
            warnings.append("missing_candidate_url")
            continue
        if _is_feed_metadata_candidate(row):
            published, event_date, count_date = _event_dates(row, channel)
            source = _save_source(
                repository,
                connection,
                _source_payload(
                    row,
                    ticker=ticker,
                    channel=channel,
                    job_id=job_id,
                    url=canonical_url or "",
                    final_url=canonical_url,
                    acceptance_status="accepted",
                    extraction_status="complete",
                    extraction_provider="feed_metadata",
                    verification_reason=None,
                    checked_at=datetime.now(UTC).isoformat(),
                ),
            )
            events.append(
                _event_candidate(
                    row,
                    ticker=ticker,
                    channel=channel,
                    source=source,
                    title=_fold(row.get("title")),
                    published=published,
                    event_date=event_date,
                    count_date=count_date,
                    canonical_url=canonical_url,
                    final_url=canonical_url,
                    extraction_provider="feed_metadata",
                )
            )
            if seen_titles is not None:
                seen_titles.add(_normalized_title(strip_title_site_prefix(row.get("title"), company)))
            sources.append(source)
            attempted += 1
            continue
        if seen_titles is not None and _fold(row.get("title")):
            candidate_title = _normalized_title(strip_title_site_prefix(row.get("title"), company))
            if candidate_title in seen_titles:
                skipped_duplicates += 1
                continue
        extraction_input = {
            "url": canonical_url,
            "channel": channel,
            "title": _fold(row.get("title")),
            "published_at": row.get("published_at") or row.get("published_date"),
        }
        result = extraction_router.extract(extraction_input, company=dict(company), approved_domains=approved_domains)
        if not isinstance(result, Mapping):
            result = {"status": "manual_review_required", "extraction_provider": "manual"}
        if result.get("status") == "extracted":
            published, event_date, count_date = _event_dates(row, channel, published_at=result.get("published_at"))
            final_url = result.get("final_url") or canonical_url
            content_hash = _save_extraction_snapshot(repository, connection, result, url=canonical_url or "", final_url=final_url)
            source = _save_source(
                repository,
                connection,
                _source_payload(
                    row,
                    ticker=ticker,
                    channel=channel,
                    job_id=job_id,
                    url=canonical_url or "",
                    final_url=final_url,
                    acceptance_status="accepted",
                    extraction_status="complete",
                    extraction_provider=result.get("extraction_provider") or "direct_http",
                    verification_reason=None,
                    checked_at=datetime.now(UTC).isoformat(),
                    attempts=result.get("attempts"),
                    content_hash=content_hash,
                ),
            )
            events.append(
                _event_candidate(
                    row,
                    ticker=ticker,
                    channel=channel,
                    source=source,
                    title=_fold(result.get("title")),
                    published=published,
                    event_date=event_date,
                    count_date=count_date,
                    canonical_url=canonical_url,
                    final_url=final_url,
                    extraction_provider=result.get("extraction_provider") or "direct_http",
                    content_hash=content_hash,
                )
            )
            if seen_titles is not None:
                seen_titles.add(_normalized_title(_fold(result.get("title"))))
            sources.append(source)
            attempted += 1
            continue
        source = _save_source(
            repository,
            connection,
            _source_payload(
                row,
                ticker=ticker,
                channel=channel,
                job_id=job_id,
                url=canonical_url or "",
                final_url=result.get("final_url") or canonical_url,
                acceptance_status="ambiguous",
                extraction_status="failed",
                extraction_provider=result.get("extraction_provider") or "manual",
                verification_reason="manual_review_required",
                checked_at=datetime.now(UTC).isoformat(),
                attempts=result.get("attempts"),
            ),
        )
        sources.append(source)
        manual_review += 1
        attempted += 1
    if not truncated:
        _advance_feed_watermark(processed, endpoint=endpoint, repository=repository, connection=connection)
    return {
        "events": events,
        "sources": sources,
        "attempted": attempted,
        "skipped_seen": skipped_seen,
        "skipped_duplicates": skipped_duplicates,
        "skipped_archive": skipped_archive,
        "manual_review": manual_review,
        "truncated": truncated,
        "warnings": warnings,
    }

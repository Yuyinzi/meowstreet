from urllib.parse import urlsplit

from openai import APITimeoutError
from openai import OpenAIError

PROVIDER_ID = "openai_responses_web_search"
WEB_SEARCH_INCLUDE = ["web_search_call.action.sources"]
SEARCH_CONTEXT_SIZE_BY_TIER = {"focused": "low", "standard": "medium", "deep": "high"}

_SOURCE_CLASS_QUERY_QUALIFIERS = {
    "official_publication": "official publication",
    "news": "news",
    "market_data": "market data",
    "financial_media": "financial media",
    "academic": "academic",
}


class OpenAIWebSearchError(Exception):
    def __init__(self, reason_code, message):
        super().__init__(message)
        self.reason_code = reason_code


class OpenAIWebSearchProvider:
    def __init__(self, client, model):
        self._client = client
        self._model = model

    async def search(self, task):
        size = SEARCH_CONTEXT_SIZE_BY_TIER[task["depth_tier"]]
        responses = []
        for query in task["queries"]:
            qualified_query = _qualify_query(query, task)
            response = await self._create_response(qualified_query, size, task)
            responses.append((qualified_query, response))
        return _normalize_responses(responses, task, self._model)

    async def _create_response(self, query, size, task):
        tool = {"type": "web_search", "search_context_size": size}
        approved_domains = task.get("approved_domains")
        if approved_domains:
            tool["filters"] = {"allowed_domains": list(approved_domains)}
        try:
            return await self._client.responses.create(
                model=self._model,
                input=query,
                tools=[tool],
                include=WEB_SEARCH_INCLUDE,
            )
        except APITimeoutError as exc:
            raise OpenAIWebSearchError("timeout", "research search timed out") from exc
        except OpenAIError as exc:
            raise OpenAIWebSearchError(
                "provider_error", "research provider request failed"
            ) from exc


def _normalize_responses(responses, task, model):
    request_id = None
    search_calls = []
    sources_by_url = {}
    findings = []
    had_consulted_sources = False
    had_citations = False
    for query, response in responses:
        request_id = request_id or getattr(response, "id", None)
        call_id = None
        for item in getattr(response, "output", None) or []:
            item_type = getattr(item, "type", None)
            if item_type == "web_search_call":
                call_id = call_id or getattr(item, "id", None)
                action = getattr(item, "action", None)
                if action is None:
                    continue
                if getattr(action, "type", None) != "search":
                    continue
                for source in getattr(action, "sources", None) or []:
                    url = getattr(source, "url", None)
                    if not url:
                        continue
                    had_consulted_sources = True
                    record = sources_by_url.setdefault(
                        url, {"url": url, "cited_spans": []}
                    )
            elif item_type == "message":
                had_citations, findings = _parse_message(
                    item, task["purpose"], sources_by_url, findings, had_citations
                )
        search_calls.append(
            {"search_call_id": call_id, "query": query, "occurred_at": None}
        )
    if not had_consulted_sources and not had_citations:
        raise OpenAIWebSearchError("missing_sources", "research returned no sources")
    if not had_citations:
        raise OpenAIWebSearchError(
            "missing_citations", "research returned no cited findings"
        )
    sources = _finalize_sources(sources_by_url)
    sources = _apply_task_constraints(sources, task)
    findings = _filter_findings_to_sources(findings, sources)
    if not findings:
        raise OpenAIWebSearchError(
            "missing_citations", "research returned no cited findings"
        )
    return {
        "provider_metadata": {
            "provider_id": PROVIDER_ID,
            "model": model,
            "request_id": request_id,
        },
        "search_calls": search_calls,
        "sources": sources,
        "findings": findings,
    }


def _filter_findings_to_sources(findings, sources):
    surviving_urls = {source["url"] for source in sources}
    filtered = []
    for finding in findings:
        citations = [
            citation
            for citation in finding.get("citations") or []
            if citation.get("url") in surviving_urls
        ]
        if not citations:
            continue
        record = dict(finding)
        record["citations"] = citations
        filtered.append(record)
    return filtered


def _qualify_query(query, task):
    qualifiers = []
    expected_class = task.get("expected_source_class")
    class_qualifier = _SOURCE_CLASS_QUERY_QUALIFIERS.get(expected_class)
    if class_qualifier:
        qualifiers.append(class_qualifier)
    time_window = task.get("time_window")
    if time_window:
        qualifiers.append(f"between {time_window['start']} and {time_window['end']}")
    if not qualifiers:
        return query
    return f"{query} ({', '.join(qualifiers)})"


def _apply_task_constraints(sources, task):
    approved_domains = task.get("approved_domains")
    filtered = sources
    if approved_domains:
        filtered = [
            source
            for source in filtered
            if _host_allowed(_source_host(source["url"]), approved_domains)
        ]
    if not filtered:
        raise OpenAIWebSearchError(
            "missing_sources", "research returned no allowed sources"
        )
    return filtered


def _host_allowed(host, approved_domains):
    for domain in approved_domains:
        if host == domain or host.endswith(f".{domain}"):
            return True
    return False


def _source_host(url):
    try:
        parsed = urlsplit(url)
    except ValueError:
        return ""
    host = parsed.hostname
    if not host:
        return ""
    return host.lower().rstrip(".")


def _parse_message(item, purpose, sources_by_url, findings, had_citations):
    for content in getattr(item, "content", None) or []:
        if getattr(content, "type", None) != "output_text":
            continue
        text = getattr(content, "text", None) or ""
        if not text:
            continue
        citations = []
        for annotation in getattr(content, "annotations", None) or []:
            if getattr(annotation, "type", None) != "url_citation":
                continue
            url = getattr(annotation, "url", None)
            if not url:
                continue
            span = _citation_span(text, annotation)
            if not span:
                continue
            had_citations = True
            citations.append({"url": url, "span": span})
            record = sources_by_url.setdefault(url, {"url": url, "cited_spans": []})
            if span not in record["cited_spans"]:
                record["cited_spans"].append(span)
            title = getattr(annotation, "title", None)
            if title and "title" not in record:
                record["title"] = title
        if citations:
            findings.append(
                {
                    "statement": text,
                    "purpose": purpose,
                    "framing": "reported",
                    "citations": citations,
                }
            )
    return had_citations, findings


def _citation_span(text, annotation):
    start = getattr(annotation, "start_index", None)
    end = getattr(annotation, "end_index", None)
    if not isinstance(start, int) or not isinstance(end, int):
        return None
    if start < 0 or end > len(text) or start >= end:
        return None
    span = text[start:end].strip()
    return span or None


def _finalize_sources(sources_by_url):
    sources = []
    for url in sorted(sources_by_url):
        record = sources_by_url[url]
        if not record["cited_spans"]:
            continue
        source = {"url": url, "cited_spans": record["cited_spans"]}
        if record.get("title"):
            source["title"] = record["title"]
        sources.append(source)
    return sources

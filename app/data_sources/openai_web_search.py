from openai import APITimeoutError
from openai import OpenAIError

PROVIDER_ID = "openai_responses_web_search"
WEB_SEARCH_INCLUDE = ["web_search_call.action.sources"]
SEARCH_CONTEXT_SIZE_BY_TIER = {"focused": "low", "standard": "medium", "deep": "high"}


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
            response = await self._create_response(query, size)
            responses.append((query, response))
        return _normalize_responses(responses, task, self._model)

    async def _create_response(self, query, size):
        try:
            return await self._client.responses.create(
                model=self._model,
                input=query,
                tools=[{"type": "web_search", "search_context_size": size}],
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
                    _apply_source_dates(record, source)
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


def _apply_source_dates(record, source):
    publication_date = getattr(source, "publication_date", None)
    if publication_date and "publication_date" not in record:
        record["publication_date"] = publication_date
    event_date = getattr(source, "event_date", None)
    if event_date and "event_date" not in record:
        record["event_date"] = event_date


def _finalize_sources(sources_by_url):
    sources = []
    for url in sorted(sources_by_url):
        record = sources_by_url[url]
        if not record["cited_spans"]:
            continue
        source = {"url": url, "cited_spans": record["cited_spans"]}
        if record.get("title"):
            source["title"] = record["title"]
        for key in ("publication_date", "event_date"):
            if record.get(key):
                source[key] = record[key]
        sources.append(source)
    return sources

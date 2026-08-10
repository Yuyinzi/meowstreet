import pytest

from app.tools.market_assistant_artifacts import validate_artifact
from app.tools.market_assistant_research import build_research_result
from app.tools.market_assistant_research import compute_result_hash
from app.tools.market_assistant_research import research_limits
from app.tools.market_assistant_research import validate_research_task


def valid_task(tier="focused", **overrides):
    task = {
        "purpose": "current_events",
        "depth_tier": tier,
        "queries": ["latest federal funds rate"],
        "expected_source_class": "official_publication",
    }
    task.update(overrides)
    return task


def valid_provider_payload(**overrides):
    payload = {
        "provider_metadata": {
            "provider_id": "openai_responses_web_search",
            "model": "gpt-4o-search-preview",
        },
        "search_calls": [
            {
                "search_call_id": "sc_1",
                "query": "latest federal funds rate",
                "occurred_at": "2026-08-10T02:00:00Z",
            }
        ],
        "sources": [
            {
                "url": "https://www.federalreserve.gov/press-release.htm",
                "title": "Federal Reserve Press Release",
                "publication_date": "2026-08-09",
                "event_date": "2026-08-09",
                "retrieved_at": "2026-08-10T02:05:00Z",
                "cited_spans": ["The Federal Reserve announced a rate decision."],
            },
            {
                "url": "https://finance.example.com/news/rates",
                "title": "Example Finance News",
                "publication_date": "2026-08-09",
                "event_date": "2026-08-08",
                "retrieved_at": "2026-08-10T02:06:00Z",
                "cited_spans": ["Analysts commented on the rate decision."],
            },
        ],
        "findings": [
            {
                "statement": "The Federal Reserve reported a rate decision.",
                "purpose": "current_events",
                "framing": "reported",
                "citations": [
                    {
                        "url": "https://www.federalreserve.gov/press-release.htm",
                        "span": "The Federal Reserve announced a rate decision.",
                    }
                ],
            },
            {
                "statement": "Commentators noted the rate decision.",
                "purpose": "external_context",
                "framing": "reported",
                "citations": [
                    {
                        "url": "https://finance.example.com/news/rates",
                        "span": "Analysts commented on the rate decision.",
                    }
                ],
            },
        ],
    }
    payload.update(overrides)
    return payload


@pytest.mark.parametrize(
    ("tier", "queries", "sources"),
    [("focused", 2, 3), ("standard", 4, 6), ("deep", 8, 12)],
)
def test_research_tier_limits(tier, queries, sources):
    assert research_limits(tier) == {
        "max_queries": queries,
        "max_sources": sources,
    }


def test_deep_research_requires_explicit_user_intent():
    with pytest.raises(ValueError, match="deep research requires explicit user intent"):
        validate_research_task(valid_task(tier="deep"), explicit_deep=False)


def test_research_limits_reject_unknown_tier():
    with pytest.raises(ValueError, match="research tier is unknown"):
        research_limits("ultra")


def test_deep_research_allowed_with_explicit_intent():
    task = validate_research_task(valid_task(tier="deep"), explicit_deep=True)
    assert task["depth_tier"] == "deep"


@pytest.mark.parametrize(
    ("tier", "excess_queries"),
    [("focused", 3), ("standard", 5), ("deep", 9)],
)
def test_query_count_limit_rejected_per_tier(tier, excess_queries):
    with pytest.raises(ValueError, match="exceeds maximum queries"):
        validate_research_task(
            valid_task(
                tier=tier,
                queries=[f"query {index}" for index in range(excess_queries)],
            ),
            explicit_deep=(tier == "deep"),
        )


def test_queries_empty_rejected():
    with pytest.raises(ValueError, match="queries are required"):
        validate_research_task(valid_task(queries=[]), explicit_deep=False)


def test_blank_query_rejected():
    with pytest.raises(ValueError, match="query is empty"):
        validate_research_task(valid_task(queries=["   "]), explicit_deep=False)


@pytest.mark.parametrize(
    "forbidden_query",
    [
        "read https://example.com/report",
        "query with api_key=abc",
        "password value here",
        "secret token here",
        "value; rm -rf /",
        "echo $(id)",
        "echo `hostname`",
    ],
)
def test_query_forbidden_content_rejected(forbidden_query):
    with pytest.raises(ValueError, match="forbidden content"):
        validate_research_task(
            valid_task(queries=[forbidden_query]), explicit_deep=False
        )


def test_unknown_purpose_rejected():
    with pytest.raises(ValueError, match="research task purpose is unknown"):
        validate_research_task(valid_task(purpose="unregulated"), explicit_deep=False)


def test_unknown_tier_rejected():
    with pytest.raises(ValueError, match="research tier is unknown"):
        validate_research_task(valid_task(tier="ultra"), explicit_deep=False)


def test_unknown_source_class_rejected():
    with pytest.raises(ValueError, match="expected source class is unknown"):
        validate_research_task(
            valid_task(expected_source_class="blog"), explicit_deep=False
        )


def test_time_window_start_after_end_rejected():
    with pytest.raises(ValueError, match="start is after end"):
        validate_research_task(
            valid_task(time_window={"start": "2026-08-10", "end": "2026-08-01"}),
            explicit_deep=False,
        )


def test_time_window_accepted():
    task = validate_research_task(
        valid_task(time_window={"start": "2026-08-01", "end": "2026-08-10"}),
        explicit_deep=False,
    )
    assert task["time_window"] == {"start": "2026-08-01", "end": "2026-08-10"}


def test_extra_field_rejected():
    with pytest.raises(ValueError, match="extra inputs are not permitted"):
        validate_research_task(valid_task(provider="openai"), explicit_deep=False)


def test_domain_filter_rejects_scheme_and_path():
    with pytest.raises(ValueError, match="domain filter is invalid"):
        validate_research_task(
            valid_task(approved_domains=["https://example.com/report"]),
            explicit_deep=False,
        )


def test_domain_filter_rejects_credentials():
    with pytest.raises(ValueError, match="domain filter is invalid"):
        validate_research_task(
            valid_task(approved_domains=["user:pass@example.com"]),
            explicit_deep=False,
        )


def test_domain_filter_accepts_hostname():
    task = validate_research_task(
        valid_task(approved_domains=["www.Example.com"]), explicit_deep=False
    )
    assert task["approved_domains"] == ["www.example.com"]


def test_valid_task_returns_plain_dict():
    task = validate_research_task(valid_task(), explicit_deep=False)
    assert isinstance(task, dict)
    assert task["purpose"] == "current_events"
    assert task["depth_tier"] == "focused"
    assert task["queries"] == ["latest federal funds rate"]
    assert task["expected_source_class"] == "official_publication"


def test_build_result_normalizes_sources_and_findings():
    payload = valid_provider_payload(
        sources=[
            {
                "url": "https://www.federalreserve.gov/press-release.htm",
                "title": "Federal Reserve Press Release",
                "publication_date": "2026-08-09",
                "event_date": "2026-08-09",
                "retrieved_at": "2026-08-10T02:05:00Z",
                "cited_spans": ["The Federal Reserve announced a rate decision."],
            }
        ],
        findings=[
            {
                "statement": "The Federal Reserve reported a rate decision.",
                "purpose": "current_events",
                "framing": "reported",
                "citations": [
                    {
                        "url": "https://www.federalreserve.gov/press-release.htm",
                        "span": "The Federal Reserve announced a rate decision.",
                    }
                ],
            }
        ],
    )
    result = build_research_result(
        task=valid_task(),
        provider_payload=payload,
        result_id="res_1",
        searched_at="2026-08-10T02:00:00Z",
    )
    assert result["research_result_id"] == "res_1"
    assert result["authority"] == "external_research"
    assert result["market_setup_relation"] == "non_decision"
    assert result["task"]["depth_tier"] == "focused"
    assert result["searched_at"] == "2026-08-10T02:00:00Z"
    assert result["provider_metadata"]["provider_id"] == "openai_responses_web_search"
    assert result["search_calls"][0]["query"] == "latest federal funds rate"
    source = result["sources"][0]
    assert source["source_id"] == "src_1"
    assert source["canonical_url"] == "https://www.federalreserve.gov/press-release.htm"
    assert source["publisher"] == "www.federalreserve.gov"
    assert source["publication_date"] == "2026-08-09"
    assert source["event_date"] == "2026-08-09"
    assert source["retrieved_at"] == "2026-08-10T02:05:00Z"
    finding = result["findings"][0]
    assert finding["finding_id"] == "fnd_1"
    assert finding["source_refs"] == ["src_1"]
    assert finding["framing"] == "reported"
    assert finding["cited_spans"] == ["The Federal Reserve announced a rate decision."]


def test_stable_source_ids_assigned_in_canonical_order():
    result = build_research_result(
        task=valid_task(),
        provider_payload=valid_provider_payload(
            sources=[
                {
                    "url": "https://www.federalreserve.gov/press-release.htm",
                    "title": "Federal Reserve Press Release",
                    "cited_spans": ["span a"],
                },
                {
                    "url": "https://finance.example.com/news/rates",
                    "title": "Example Finance News",
                    "cited_spans": ["span b"],
                },
            ],
            findings=[],
        ),
        result_id="res_order",
        searched_at="2026-08-10T02:00:00Z",
    )
    assert [(s["source_id"], s["canonical_url"]) for s in result["sources"]] == [
        ("src_1", "https://finance.example.com/news/rates"),
        ("src_2", "https://www.federalreserve.gov/press-release.htm"),
    ]


def test_source_canonical_url_normalization():
    result = build_research_result(
        task=valid_task(),
        provider_payload=valid_provider_payload(
            sources=[
                {
                    "url": "https://WWW.Example.com:443/report/#fragment",
                    "title": "Example",
                    "cited_spans": ["span"],
                }
            ],
            findings=[],
        ),
        result_id="res_canon",
        searched_at="2026-08-10T02:00:00Z",
    )
    source = result["sources"][0]
    assert source["canonical_url"] == "https://www.example.com/report"
    assert source["source_id"] == "src_1"
    assert source["publisher"] == "www.example.com"
    assert source["retrieved_at"] == "2026-08-10T02:00:00Z"


def test_distinct_publication_and_event_dates():
    result = build_research_result(
        task=valid_task(),
        provider_payload=valid_provider_payload(
            sources=[
                {
                    "url": "https://example.com/report",
                    "title": "Example",
                    "publication_date": "2026-08-10",
                    "event_date": "2026-07-30",
                    "cited_spans": ["span"],
                }
            ],
            findings=[],
        ),
        result_id="res_dates",
        searched_at="2026-08-10T02:00:00Z",
    )
    source = result["sources"][0]
    assert source["publication_date"] == "2026-08-10"
    assert source["event_date"] == "2026-07-30"


def test_duplicate_source_urls_consolidated():
    result = build_research_result(
        task=valid_task(),
        provider_payload=valid_provider_payload(
            sources=[
                {
                    "url": "https://example.com/report",
                    "title": "Example Report",
                    "cited_spans": ["first span"],
                },
                {
                    "url": "https://example.com/report#more",
                    "title": "Example Report",
                    "cited_spans": ["second span"],
                },
            ],
            findings=[],
        ),
        result_id="res_dedupe",
        searched_at="2026-08-10T02:00:00Z",
    )
    sources = result["sources"]
    assert len(sources) == 1
    assert sources[0]["source_id"] == "src_1"
    assert sources[0]["cited_spans"] == ["first span", "second span"]


def test_finding_references_unknown_source_rejected():
    payload = valid_provider_payload()
    payload["findings"][0]["citations"] = [
        {"url": "https://unknown.example.com/elsewhere", "span": "text"}
    ]
    with pytest.raises(ValueError, match="cites an unknown source"):
        build_research_result(
            task=valid_task(),
            provider_payload=payload,
            result_id="res_badref",
            searched_at="2026-08-10T02:00:00Z",
        )


def test_finding_with_no_source_rejected():
    payload = valid_provider_payload()
    payload["findings"][0]["citations"] = []
    with pytest.raises(ValueError, match="requires at least one citation"):
        build_research_result(
            task=valid_task(),
            provider_payload=payload,
            result_id="res_nocite",
            searched_at="2026-08-10T02:00:00Z",
        )


def test_provider_prose_without_cited_spans_rejected():
    payload = valid_provider_payload()
    payload["findings"][0]["citations"] = [
        {"url": "https://www.federalreserve.gov/press-release.htm"}
    ]
    with pytest.raises(ValueError, match="missing a cited span"):
        build_research_result(
            task=valid_task(),
            provider_payload=payload,
            result_id="res_nospan",
            searched_at="2026-08-10T02:00:00Z",
        )


def test_source_private_url_rejected():
    payload = valid_provider_payload(
        sources=[
            {
                "url": "http://localhost:8000/status",
                "title": "local",
                "cited_spans": ["span"],
            }
        ],
        findings=[],
    )
    with pytest.raises(ValueError, match="url is private"):
        build_research_result(
            task=valid_task(),
            provider_payload=payload,
            result_id="res_private",
            searched_at="2026-08-10T02:00:00Z",
        )


@pytest.mark.parametrize(
    ("url", "message"),
    [
        ("http://127.0.0.1/status", "url is private"),
        ("http://192.168.1.1/status", "url is private"),
        ("http://intranet.internal/page", "url is private"),
        ("https://user:pass@example.com/page", "contains credentials"),
        ("file:///etc/passwd", "scheme is not approved"),
    ],
)
def test_source_url_rejections(url, message):
    payload = valid_provider_payload(
        sources=[{"url": url, "title": "source", "cited_spans": ["span"]}],
        findings=[],
    )
    with pytest.raises(ValueError, match=message):
        build_research_result(
            task=valid_task(),
            provider_payload=payload,
            result_id="res_url",
            searched_at="2026-08-10T02:00:00Z",
        )


def test_authority_and_relation_always_present():
    result = build_research_result(
        task=valid_task(),
        provider_payload=valid_provider_payload(),
        result_id="res_auth",
        searched_at="2026-08-10T02:00:00Z",
    )
    assert result["authority"] == "external_research"
    assert result["market_setup_relation"] == "non_decision"


def test_result_hash_excludes_itself():
    result = build_research_result(
        task=valid_task(),
        provider_payload=valid_provider_payload(),
        result_id="res_hash",
        searched_at="2026-08-10T02:00:00Z",
    )
    original = result["result_hash"]
    result["result_hash"] = "mutated"
    assert compute_result_hash(result) == original
    result["sources"][0]["title"] = "changed"
    assert compute_result_hash(result) != original


def test_result_validates_as_artifact():
    result = build_research_result(
        task=valid_task(),
        provider_payload=valid_provider_payload(),
        result_id="res_artifact",
        searched_at="2026-08-10T02:00:00Z",
    )
    envelope = {
        "artifact_id": result["research_result_id"],
        "artifact_kind": "research_result",
        "schema_version": result["artifact_schema_version"],
        "primary_authority": result["authority"],
        "market_setup_relation": result["market_setup_relation"],
        "payload": result,
        "object_index": result["object_index"],
        "integrity_hash": "unverified",
    }
    validated = validate_artifact(envelope)
    assert validated["payload"]["result_hash"] == result["result_hash"]


def test_result_object_index_contains_sources_and_findings():
    result = build_research_result(
        task=valid_task(),
        provider_payload=valid_provider_payload(),
        result_id="res_index",
        searched_at="2026-08-10T02:00:00Z",
    )
    object_types = [
        (obj["object_type"], obj["object_id"]) for obj in result["object_index"]
    ]
    assert ("research_source", "src_1") in object_types
    assert ("research_source", "src_2") in object_types
    assert ("research_finding", "fnd_1") in object_types
    assert ("research_finding", "fnd_2") in object_types


def test_finding_framing_required_and_closed():
    payload = valid_provider_payload()
    payload["findings"][0]["framing"] = "proven"
    with pytest.raises(ValueError, match="provider finding is invalid"):
        build_research_result(
            task=valid_task(),
            provider_payload=payload,
            result_id="res_framing",
            searched_at="2026-08-10T02:00:00Z",
        )


def test_build_result_rejects_invalid_task():
    with pytest.raises(ValueError, match="purpose is unknown"):
        build_research_result(
            task=valid_task(purpose="unregulated"),
            provider_payload=valid_provider_payload(),
            result_id="res_badtask",
            searched_at="2026-08-10T02:00:00Z",
        )

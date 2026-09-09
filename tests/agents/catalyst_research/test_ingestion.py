import asyncio
from datetime import UTC, datetime

import pytest

from app.agents.catalyst_research import ingestion
from app.agents.catalyst_research.extraction.router import ExtractionRouter
from app.agents.catalyst_research.persistence import repository


URL = "https://nvidianews.nvidia.com/news/nvidia-announces-new-platform"
SECOND_URL = "https://nvidianews.nvidia.com/news/nvidia-second-story"
THIRD_URL = "https://nvidianews.nvidia.com/news/nvidia-third-story"
DOMAINS = {"nvidia.com"}


def rss_candidate(**overrides):
    base = {
        "ticker": "NVDA",
        "channel": "press_releases",
        "url": URL,
        "external_guid": "guid-1",
        "title": "NVIDIA Announces New Platform",
        "published_at": "2026-09-07T12:00:00+00:00",
        "summary": "NVIDIA announced a new platform.",
        "discovery_method": "rss",
        "endpoint_id": "cse_feed",
    }
    base.update(overrides)
    return base


def search_candidate(**overrides):
    base = {
        "ticker": "NVDA",
        "channel": "press_releases",
        "url": f"{URL}?utm_source=newsletter",
        "title": "NVIDIA Announces New Platform",
        "published_date": "2026-09-07T12:00:00+00:00",
        "snippet": "NVIDIA announced a new platform.",
        "discovery_method": "search",
        "result_id": 1,
    }
    base.update(overrides)
    return base


def company():
    return {"ticker": "NVDA", "company_name": "NVIDIA Corporation", "official_domains": ["nvidia.com"]}


def feed_endpoint(**overrides):
    base = {
        "endpoint_id": "cse_feed",
        "ticker": "NVDA",
        "channel": "press_releases",
        "endpoint_type": "rss",
        "url": "https://nvidianews.nvidia.com/rss",
        "domain": "nvidianews.nvidia.com",
        "status": "active",
        "confidence": "high",
    }
    base.update(overrides)
    return base


def running_job(con, ticker="NVDA"):
    job = repository.create_job(
        con,
        {"ticker": ticker, "years": 2},
        {"name": "NVIDIA Corporation", "cik": "1045810"},
        datetime(2026, 9, 4, tzinfo=UTC),
    )
    repository.start_job(con, job["job_id"], "2026-09-04T00:01:00+00:00")
    return job


def direct_article(**overrides):
    base = {
        "status": "extracted",
        "url": URL,
        "final_url": URL,
        "title": "NVIDIA Announces New Platform",
        "published_at": "2026-09-07T12:00:00+00:00",
        "text": "NVIDIA announced a new platform in a press release for investors.",
        "provider": "direct_http",
    }
    base.update(overrides)
    return base


class FakeDirect:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = []

    def __call__(self, url, **kwargs):
        self.calls.append(url)
        if self.error is not None:
            raise self.error
        return dict(self.result)


def make_router(result=None, error=None):
    return ExtractionRouter(FakeDirect(result=result, error=error))


def run_ingest(candidates, con, job_id, router, endpoint=None, max_urls=200):
    return asyncio.run(
        ingestion.ingest_candidates(
            candidates,
            company=company(),
            channel="press_releases",
            endpoint=endpoint,
            job={"job_id": job_id},
            extraction_router=router,
            repository=repository,
            connection=con,
            max_urls=max_urls,
        )
    )


def test_deduplicate_prefers_canonical_url_across_rss_and_search():
    rows = [rss_candidate(), search_candidate(url=f"{URL}?utm_source=x")]
    result = ingestion.deduplicate_candidates(rows)
    assert len(result) == 1
    assert result[0]["discovery_methods"] == ["rss", "search"]
    assert result[0]["canonical_url"] == URL


def test_deduplicate_drops_fragments_and_tracking_parameters():
    rows = [
        rss_candidate(url=f"{URL}#section-2"),
        search_candidate(url=f"{URL}?utm_medium=email&gclid=abc"),
    ]
    result = ingestion.deduplicate_candidates(rows)
    assert len(result) == 1
    assert result[0]["canonical_url"] == URL


def test_deduplicate_preserves_semantically_distinct_query_parameters():
    rows = [
        search_candidate(url=f"{URL}?page=1"),
        search_candidate(url=f"{URL}?page=2"),
    ]
    result = ingestion.deduplicate_candidates(rows)
    assert len(result) == 2


def test_deduplicate_conflicting_guids_fall_through_to_distinct_records():
    rows = [
        rss_candidate(url=None, external_guid="guid-9", title="NVIDIA First Story"),
        rss_candidate(url=None, external_guid="guid-9", title="NVIDIA Different Story", published_at="2026-09-06T12:00:00+00:00"),
    ]
    result = ingestion.deduplicate_candidates(rows)
    assert len(result) == 2


def test_deduplicate_matches_guid_only_within_same_endpoint():
    rows = [
        rss_candidate(url=None, endpoint_id="cse_feed", external_guid="guid-9"),
        rss_candidate(url=None, endpoint_id="cse_other", external_guid="guid-9"),
    ]
    result = ingestion.deduplicate_candidates(rows)
    assert len(result) == 2
    same_endpoint = [
        rss_candidate(url=None, endpoint_id="cse_feed", external_guid="guid-9"),
        rss_candidate(url=None, endpoint_id="cse_feed", external_guid="guid-9", title="NVIDIA Announces New Platform"),
    ]
    merged = ingestion.deduplicate_candidates(same_endpoint)
    assert len(merged) == 1


def test_deduplicate_matches_title_and_date_when_url_absent():
    rows = [
        rss_candidate(url=None, external_guid=None),
        rss_candidate(url=None, external_guid=None, title="  NVIDIA   Announces New Platform ", discovery_method="atom", endpoint_id="cse_atom"),
    ]
    result = ingestion.deduplicate_candidates(rows)
    assert len(result) == 1
    assert result[0]["discovery_methods"] == ["rss", "atom"]


def test_deduplicate_keeps_title_date_matches_with_same_date_apart():
    rows = [
        rss_candidate(url=None, external_guid=None, title="NVIDIA Announces New Platform", published_at="2026-09-07T12:00:00+00:00"),
        rss_candidate(url=None, external_guid=None, title="NVIDIA Announces New Platform", published_at="2026-09-08T12:00:00+00:00"),
    ]
    result = ingestion.deduplicate_candidates(rows)
    assert len(result) == 2


def test_deduplicate_output_order_is_deterministic():
    rows = [
        search_candidate(url=THIRD_URL, result_id=3),
        rss_candidate(url=URL, external_guid="guid-1"),
        search_candidate(url=SECOND_URL, result_id=2),
    ]
    first = ingestion.deduplicate_candidates(rows)
    second = ingestion.deduplicate_candidates(list(reversed(rows)))
    assert [row["canonical_url"] for row in first] == [row["canonical_url"] for row in second]
    assert [row["canonical_url"] for row in first] == sorted(
        [URL, SECOND_URL, THIRD_URL]
    )


def test_candidate_identity_resolves_url_guid_then_title():
    url_identity = ingestion.candidate_identity(rss_candidate())
    assert url_identity == ("url", "NVDA", URL)
    guid_identity = ingestion.candidate_identity(rss_candidate(url=None))
    assert guid_identity == ("guid", "cse_feed", "guid-1")
    title_identity = ingestion.candidate_identity(rss_candidate(url=None, external_guid=None))
    assert title_identity == ("title", "NVDA", "nvidia announces new platform", "2026-09-07")


def test_deduplicate_rejects_non_mapping_candidates():
    with pytest.raises(ValueError, match="candidate"):
        ingestion.deduplicate_candidates([{"url": URL}, "not-a-dict"])
    with pytest.raises(ValueError, match="candidates"):
        ingestion.deduplicate_candidates("not-a-list")


def test_ingest_skips_already_persisted_event_url_before_extraction(tmp_path):
    con = repository.connect(tmp_path / "db.sqlite")
    old_job = running_job(con)
    old_source = repository.save_source(
        con,
        {"job_id": old_job["job_id"], "ticker": "NVDA", "source_type": "press_releases", "url": "https://nvidianews.nvidia.com/rss"},
    )
    repository.save_finalized_observations(
        con,
        old_job["job_id"],
        [{"source_id": old_source["source_id"], "ticker": "NVDA", "source_type": "press_releases", "count_date": "2026-09-07", "title": "NVIDIA Announces New Platform", "url": URL}],
        [],
    )
    repository.finalize_job(con, old_job["job_id"], {"status": "completed"})
    job = running_job(con)
    router = make_router(result=direct_article())
    result = run_ingest([rss_candidate()], con, job["job_id"], router)
    assert result["skipped_seen"] == 1
    assert result["attempted"] == 0
    assert result["events"] == []
    assert result["sources"] == []
    assert router._direct_extractor.calls == []


def test_ingest_skips_url_already_recorded_as_source_outcome(tmp_path):
    con = repository.connect(tmp_path / "db.sqlite")
    old_job = running_job(con)
    repository.save_source(
        con,
        {
            "job_id": old_job["job_id"],
            "ticker": "NVDA",
            "source_type": "press_releases",
            "url": URL,
            "acceptance_status": "ambiguous",
            "extraction_status": "failed",
            "extraction_provider": "manual",
        },
    )
    job = running_job(con)
    router = make_router(result=direct_article())
    result = run_ingest([rss_candidate()], con, job["job_id"], router)
    assert result["skipped_seen"] == 1
    assert result["attempted"] == 0
    assert router._direct_extractor.calls == []


def test_ingest_feed_metadata_with_valid_title_and_date_stores_event_without_extraction(tmp_path):
    con = repository.connect(tmp_path / "db.sqlite")
    job = running_job(con)
    router = make_router(result=direct_article())
    result = run_ingest([rss_candidate()], con, job["job_id"], router)
    assert result["attempted"] == 1
    assert result["skipped_seen"] == 0
    assert result["manual_review"] == 0
    assert result["truncated"] is False
    assert router._direct_extractor.calls == []
    assert len(result["events"]) == 1
    event = result["events"][0]
    assert event["title"] == "NVIDIA Announces New Platform"
    assert event["count_date"] == "2026-09-07"
    assert event["canonical_url"] == URL
    assert event["extraction_provider"] == "feed_metadata"
    assert len(result["sources"]) == 1
    source = result["sources"][0]
    assert source["extraction_status"] == "complete"
    assert source["extraction_provider"] == "feed_metadata"
    assert source["discovery_method"] == "rss"


def test_ingest_feed_item_missing_date_uses_extraction_router(tmp_path):
    con = repository.connect(tmp_path / "db.sqlite")
    job = running_job(con)
    router = make_router(result=direct_article())
    result = run_ingest([rss_candidate(published_at=None)], con, job["job_id"], router)
    assert len(router._direct_extractor.calls) == 1
    assert len(result["events"]) == 1
    assert result["events"][0]["extraction_provider"] == "direct_http"


def test_ingest_search_candidate_uses_extraction_router(tmp_path):
    con = repository.connect(tmp_path / "db.sqlite")
    job = running_job(con)
    router = make_router(result=direct_article())
    result = run_ingest([search_candidate()], con, job["job_id"], router)
    assert router._direct_extractor.calls == [URL]
    assert result["attempted"] == 1
    assert len(result["events"]) == 1
    event = result["events"][0]
    assert event["extraction_provider"] == "direct_http"
    assert event["discovery_method"] == "search"
    assert event["canonical_url"] == URL
    source = result["sources"][0]
    assert source["extraction_provider"] == "direct_http"
    assert source["extraction_status"] == "complete"
    assert source["acceptance_status"] == "accepted"
    assert source["attempts"] == [{"provider": "direct_http", "outcome": "extracted"}]


def test_ingest_manual_review_saves_failed_source_without_event(tmp_path):
    con = repository.connect(tmp_path / "db.sqlite")
    job = running_job(con)
    router = make_router(error=ValueError("metadata_missing"))
    result = run_ingest([search_candidate()], con, job["job_id"], router)
    assert result["manual_review"] == 1
    assert result["events"] == []
    assert len(result["sources"]) == 1
    source = result["sources"][0]
    assert source["extraction_status"] == "failed"
    assert source["extraction_provider"] == "manual"
    assert source["acceptance_status"] == "ambiguous"
    assert source["attempts"] == [{"provider": "direct_http", "outcome": "metadata_missing"}]
    saved = repository.load_job_result(con, job["job_id"])["sources"][0]
    assert saved["attempts"] == [{"provider": "direct_http", "outcome": "metadata_missing"}]
    assert con.execute("select count(*) from catalyst_ir_events").fetchone()[0] == 0


def test_ingest_persists_endpoint_guid_discovery_and_provider_provenance(tmp_path):
    con = repository.connect(tmp_path / "db.sqlite")
    endpoint = repository.upsert_source_endpoint(con, feed_endpoint())
    job = running_job(con)
    router = make_router(result=direct_article())
    rows = [rss_candidate(), search_candidate(url=f"{URL}?utm_source=x")]
    result = run_ingest(rows, con, job["job_id"], router, endpoint=endpoint)
    assert result["attempted"] == 1
    event = result["events"][0]
    source = result["sources"][0]
    for payload in (event, source):
        assert payload["endpoint_id"] == endpoint["endpoint_id"]
        assert payload["external_guid"] == "guid-1"
    assert event["discovery_methods"] == ["rss", "search"]
    assert source["discovery_method"] == "rss"
    saved = repository.load_job_result(con, job["job_id"])["sources"][0]
    assert saved["endpoint_id"] == endpoint["endpoint_id"]
    assert saved["external_guid"] == "guid-1"
    assert saved["discovery_method"] == "rss"


def test_ingest_url_cap_sets_unseen_url_limit_and_leaves_later_candidates_unprocessed(tmp_path):
    con = repository.connect(tmp_path / "db.sqlite")
    job = running_job(con)
    router = make_router(result=direct_article())
    rows = [
        search_candidate(url=THIRD_URL, result_id=3),
        search_candidate(url=URL, result_id=1),
        search_candidate(url=SECOND_URL, result_id=2),
    ]
    result = run_ingest(rows, con, job["job_id"], router, max_urls=2)
    assert result["attempted"] == 2
    assert result["truncated"] is True
    assert "unseen_url_limit" in result["warnings"]
    assert len(router._direct_extractor.calls) == 2
    assert con.execute("select count(*) from catalyst_ir_sources where job_id = ?", (job["job_id"],)).fetchone()[0] == 2


def test_ingest_returns_event_candidates_without_event_persistence(tmp_path):
    con = repository.connect(tmp_path / "db.sqlite")
    job = running_job(con)
    router = make_router(result=direct_article())
    result = run_ingest([rss_candidate()], con, job["job_id"], router)
    assert len(result["events"]) == 1
    assert con.execute("select count(*) from catalyst_ir_events").fetchone()[0] == 0
    assert con.execute("select count(*) from catalyst_ir_classifications").fetchone()[0] == 0
    finalized = dict(result["events"][0], id=1)
    repository.finalize_job_with_observations(
        con,
        job["job_id"],
        [finalized],
        [{"id": 1, "earnings_state": "non_earnings", "classification_method": "manual"}],
        {"status": "completed"},
    )
    assert con.execute("select count(*) from catalyst_ir_events").fetchone()[0] == 1
    assert con.execute("select count(*) from catalyst_ir_classifications").fetchone()[0] == 1


def test_ingest_advances_feed_watermark_after_all_items_processed(tmp_path):
    con = repository.connect(tmp_path / "db.sqlite")
    endpoint = repository.upsert_source_endpoint(con, feed_endpoint())
    job = running_job(con)
    router = make_router(result=direct_article())
    rows = [
        rss_candidate(url=SECOND_URL, external_guid="guid-2", published_at="2026-09-05T12:00:00+00:00"),
        rss_candidate(url=URL, external_guid="guid-1", published_at="2026-09-07T12:00:00+00:00"),
    ]
    result = run_ingest(rows, con, job["job_id"], router, endpoint=endpoint)
    assert result["truncated"] is False
    updated = repository.load_source_endpoints(con, "NVDA")[0]
    assert updated["last_item_at"] == "2026-09-07T12:00:00+00:00"
    assert updated["last_guid"] == "guid-1"


def test_ingest_does_not_advance_feed_watermark_when_truncated(tmp_path):
    con = repository.connect(tmp_path / "db.sqlite")
    endpoint = repository.upsert_source_endpoint(con, feed_endpoint())
    job = running_job(con)
    router = make_router(result=direct_article())
    rows = [
        rss_candidate(url=SECOND_URL, external_guid="guid-2", published_at="2026-09-05T12:00:00+00:00"),
        rss_candidate(url=URL, external_guid="guid-1", published_at="2026-09-07T12:00:00+00:00"),
    ]
    result = run_ingest(rows, con, job["job_id"], router, endpoint=endpoint, max_urls=1)
    assert result["truncated"] is True
    updated = repository.load_source_endpoints(con, "NVDA")[0]
    assert updated["last_item_at"] is None
    assert updated["last_guid"] is None


def test_ingest_validates_inputs(tmp_path):
    con = repository.connect(tmp_path / "db.sqlite")
    job = running_job(con)
    router = make_router(result=direct_article())
    with pytest.raises(ValueError, match="candidates"):
        asyncio.run(
            ingestion.ingest_candidates(
                "not-a-list",
                company=company(),
                channel="press_releases",
                endpoint=None,
                job={"job_id": job["job_id"]},
                extraction_router=router,
                repository=repository,
                connection=con,
                max_urls=200,
            )
        )
    with pytest.raises(ValueError, match="channel"):
        asyncio.run(
            ingestion.ingest_candidates(
                [rss_candidate()],
                company=company(),
                channel="ir_home",
                endpoint=None,
                job={"job_id": job["job_id"]},
                extraction_router=router,
                repository=repository,
                connection=con,
                max_urls=200,
            )
        )
    with pytest.raises(ValueError, match="max urls"):
        run_ingest([rss_candidate()], con, job["job_id"], router, max_urls=0)
    with pytest.raises(ValueError, match="max urls"):
        run_ingest([rss_candidate()], con, job["job_id"], router, max_urls=501)


def test_ingest_empty_candidate_list_returns_zero_counts(tmp_path):
    con = repository.connect(tmp_path / "db.sqlite")
    job = running_job(con)
    router = make_router(result=direct_article())
    result = run_ingest([], con, job["job_id"], router, endpoint=feed_endpoint())
    assert result == {
        "events": [],
        "sources": [],
        "attempted": 0,
        "skipped_seen": 0,
        "manual_review": 0,
        "truncated": False,
        "warnings": [],
    }

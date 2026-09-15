import argparse
import asyncio
import json
import sys
from pathlib import Path

from app.agents.catalyst_research import config
from app.agents.catalyst_research.report import render_report
from app.agents.catalyst_research.workflow import run_research
from app.http_client import HttpClient


_OVERRIDE_SOURCE_TYPES = ("press_releases", "events_presentations")
_LLM_FLAGS = (
    "catalyst_source_selection_model",
    "catalyst_registry_selection_model",
    "catalyst_adapter_generation_model",
    "catalyst_classification_model",
    "catalyst_assessment_model",
    "openai_api_key",
    "openai_base_url",
)
_SEARCH_FLAGS = (
    "catalyst_search_provider",
    "catalyst_search_fallback",
    "catalyst_native_search_supported",
    "tavily_api_key",
)
_COLLECTION_FLAGS = (
    "firecrawl_api_key",
    "firecrawl_base_url",
    "archive_enrichment_enabled",
)


def _parser():
    parser = argparse.ArgumentParser(
        prog="app.agents.catalyst_research",
        description="Run one catalyst research job for a ticker",
    )
    parser.add_argument("ticker")
    parser.add_argument("--years", type=int, default=4)
    parser.add_argument("--db-path", type=Path, default=None)
    parser.add_argument("--mode", choices=sorted(config.RESEARCH_MODES), default=None)
    parser.add_argument("--report", type=Path, default=None, metavar="PATH")
    parser.add_argument("--source", action="append", default=None, metavar="SOURCE_TYPE=URL")
    parser.add_argument("--force-discovery", action="store_true")
    parser.add_argument("--search-provider", dest="catalyst_search_provider", default=None)
    parser.add_argument("--search-fallback", dest="catalyst_search_fallback", default=None)
    parser.add_argument("--native-search-supported", dest="catalyst_native_search_supported", default=None)
    parser.add_argument("--tavily-api-key", dest="tavily_api_key", default=None)
    parser.add_argument("--firecrawl-api-key", dest="firecrawl_api_key", default=None)
    parser.add_argument("--firecrawl-base-url", dest="firecrawl_base_url", default=None)
    parser.add_argument("--archive-enrichment", dest="archive_enrichment_enabled", action="store_true", default=None)
    parser.add_argument("--source-selection-model", dest="catalyst_source_selection_model", default=None)
    parser.add_argument("--registry-selection-model", dest="catalyst_registry_selection_model", default=None)
    parser.add_argument("--adapter-generation-model", dest="catalyst_adapter_generation_model", default=None)
    parser.add_argument("--classification-model", dest="catalyst_classification_model", default=None)
    parser.add_argument("--catalyst-assessment-model", dest="catalyst_assessment_model", default=None)
    parser.add_argument("--openai-api-key", dest="openai_api_key", default=None)
    parser.add_argument("--openai-base-url", dest="openai_base_url", default=None)
    return parser


def _source_overrides(values):
    if not values:
        return None
    overrides = {}
    for value in values:
        source_type, separator, url = str(value).partition("=")
        source_type = source_type.strip()
        url = url.strip()
        if not separator or not source_type or not url:
            raise ValueError("source override must be source_type=url")
        if source_type not in _OVERRIDE_SOURCE_TYPES:
            raise ValueError(f"source override type {source_type} is unsupported")
        if source_type in overrides:
            raise ValueError(f"source override {source_type} is duplicated")
        overrides[source_type] = url
    return overrides


def _build_dependencies(args):
    if any(getattr(args, name, None) for name in _LLM_FLAGS):
        config.load_inference_bundle(args)
    if any(getattr(args, name, None) for name in _SEARCH_FLAGS):
        config.load_search_config(args)
    if any(getattr(args, name, None) for name in _COLLECTION_FLAGS):
        config.load_collection_config(args)
    if not any(getattr(args, name, None) for name in _LLM_FLAGS + _SEARCH_FLAGS + _COLLECTION_FLAGS):
        return {}
    return {"config_args": args}


def _stage_progress(stage, **details):
    suffix = "".join(f" {key}={value}" for key, value in details.items() if value is not None)
    print(f"stage {stage}{suffix}", file=sys.stderr)


def _request_from_args(args):
    request = {"ticker": args.ticker, "years": args.years, "force_discovery": bool(args.force_discovery)}
    if args.mode is not None:
        request["mode"] = args.mode
    overrides = _source_overrides(args.source)
    if overrides:
        request["source_overrides"] = overrides
    return request


def _print_attention_summary(result):
    attention = [
        source
        for source in result.get("sources", [])
        if isinstance(source, dict) and source.get("extraction_status") == "failed"
    ]
    if not attention:
        return
    print(f"manual review required ({len(attention)}):", file=sys.stderr)
    for source in attention:
        attempts = source.get("attempts") or []
        last = attempts[-1] if attempts and isinstance(attempts[-1], dict) else {}
        detail = f"{last.get('provider', '?')}: {last.get('outcome', '?')}" if last else "no attempts recorded"
        print(f"  {source.get('source_type', 'unknown')}: {source.get('url', '')} [{detail}]", file=sys.stderr)


def main(argv=None):
    args = _parser().parse_args(argv)
    try:
        request = _request_from_args(args)
        dependencies = {**_build_dependencies(args), "progress": _stage_progress}
        with HttpClient() as http_client:
            print(f"catalyst research started ticker={args.ticker} years={args.years}", file=sys.stderr)
            result = asyncio.run(run_research(request, db_path=args.db_path, http_client=http_client, dependencies=dependencies))
    except (ValueError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    for source in result.get("sources", []):
        if isinstance(source, dict):
            print(
                f"source {source.get('source_type')}: {source.get('extraction_status', 'unknown')} via {source.get('execution_path', 'unknown')}",
                file=sys.stderr,
            )
    _print_attention_summary(result)
    print(f"catalyst research {result.get('status', 'failed')} job={result.get('job_id')}", file=sys.stderr)
    if args.report is not None:
        try:
            args.report.write_text(render_report(result), encoding="utf-8")
        except OSError as exc:
            print(f"error: report write failed: {exc}", file=sys.stderr)
            return 2
        print(f"report written path={args.report}", file=sys.stderr)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, default=str))
    return 0 if result.get("status") in {"completed", "completed_partial"} else 1


if __name__ == "__main__":
    sys.exit(main())

"""ISM Services Report fetcher — AI extraction wrapper.

Services reports require AI extraction. The canonical multi-survey CLI
is ``fetch_ism_reports.py``; this wrapper exists for backward
compatibility with callers that target only the services survey.
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db import us_rates_liquidity
from app.services import ism_report_ingestion as ingestion
from app.services.ism_services_ai_ingestion import import_targets as ai_import_targets


def requested_months(count=1, today=None):
    """Return the *count* most recent report months as ``YYYY-MM-01`` strings."""
    if today is None:
        today = datetime.now()
    months = []
    for i in range(count):
        raw_month = today.month - 1 - i
        y = today.year
        m = raw_month
        while m <= 0:
            m += 12
            y -= 1
        months.append(f"{y}-{m:02d}-01")
    return sorted(months)


def _build_ai_client():
    from app import llm

    config = llm.load_openai_config({}, root=ROOT)
    from scripts.extract_ism_report_ai import OpenAIJsonClient, llm_timeout

    def _client_factory():
        return llm.build_async_client(
            config,
            max_retries=0,
            timeout=llm_timeout(),
            error_context="ISM Services extraction",
        )

    client = OpenAIJsonClient(
        _client_factory(),
        config["model"],
        client_factory=_client_factory,
        progress=lambda msg: print(msg, file=sys.stderr, flush=True),
    )
    return client, config["model"]


def main(argv=None, fetch=None, ai_client_factory=None):
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--db-path", type=Path, default=us_rates_liquidity.DEFAULT_DB_PATH
    )
    parser.add_argument("--months", type=int, default=1)
    args = parser.parse_args(argv)

    months = requested_months(args.months)

    targets = []
    for month in months:
        targets.extend(
            ingestion.build_targets(
                "services",
                report_month=month,
                force_latest=False,
                fetch=fetch,
            )
        )

    if ai_client_factory is not None:
        config = {"model": "test-model"}
        client = ai_client_factory(config)
        model = config["model"]
    else:
        client, model = _build_ai_client()
    results, failed = ai_import_targets(
        str(args.db_path),
        targets,
        client,
        model,
        fetch=fetch,
        report_concurrency=1,
        section_concurrency=3,
    )

    for result in results:
        if result is not None:
            rankings = result.get("rankings") or result.get("industry_signals") or 0
            print(
                f"{result['report_id']}: source={result['source']} "
                f"metrics={result.get('metrics', result.get('at_a_glance_rows', 0))} "
                f"rankings={rankings} "
                f"comments={result['comments']}"
            )

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

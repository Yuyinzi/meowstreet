import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.agents.catalyst_research import config
from app.agents.catalyst_research.assessment_backfill import backfill_catalyst_assessments
from app.agents.catalyst_research.persistence import repository


def main():
    parser = argparse.ArgumentParser(description="Backfill catalyst type and meaningfulness assessments for stored IR events")
    parser.add_argument("--ticker", default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--catalyst-assessment-model", dest="catalyst_assessment_model", default=None)
    args = parser.parse_args()
    dependencies = {}
    if not args.dry_run:
        bundle = config.load_inference_bundle(args)
        dependencies["llm_client"] = bundle.get("client")
        dependencies["model"] = (bundle.get("models") or {}).get("catalyst_assessment_model")
    connection = repository.connect()
    try:
        result = asyncio.run(
            backfill_catalyst_assessments(
                connection,
                ticker=args.ticker,
                batch_size=args.batch_size,
                dry_run=args.dry_run,
                dependencies=dependencies,
            )
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    finally:
        connection.close()
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())

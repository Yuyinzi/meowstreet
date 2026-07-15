import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db import us_rates_liquidity
from app.tools import ism_ai_extraction
from app.tools import ism_official_report


def extract_snapshot(con, source_url, client, model):
    snapshot = us_rates_liquidity.load_ism_report_source_snapshot(con, source_url)
    if not snapshot:
        raise ValueError(f"ism source snapshot is missing: {source_url}")
    report_text = ism_official_report.extract_report_text(
        snapshot["raw_html"],
        snapshot["source_name"],
    )
    payload = ism_ai_extraction.extract_with_client(report_text, client)
    saved = us_rates_liquidity.replace_ism_ai_extraction(
        con,
        {
            "report_id": payload["report"]["report_id"],
            "report_month": payload["report"]["report_month"],
            "source_url": snapshot["source_url"],
            "source_hash": snapshot["source_hash"],
            "extractor": "llm",
            "model": model,
            "prompt_version": ism_ai_extraction.PROMPT_VERSION,
            "validation_status": "ok",
            "validation_error": None,
            "extraction_json": payload,
        },
    )
    return {
        "report_id": payload["report"]["report_id"],
        "industry_signals": saved["industry_signals"],
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--db-path", type=Path, default=us_rates_liquidity.DEFAULT_DB_PATH
    )
    parser.add_argument("--source-url", action="append", required=True)
    parser.add_argument("--model", default="gpt-5-mini")
    args = parser.parse_args(argv)
    raise ValueError(
        "live OpenAI client wiring must be added after configuration is decided"
    )


if __name__ == "__main__":
    raise SystemExit(main())

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from openpyxl import load_workbook

from app.db import ticker_context as ticker_context_db


DEFAULT_ARTIFACT_PATH = ROOT / "data" / "local_system" / "gics_industry_tags.v1.json"
WORKBOOK_PATH = ROOT / "data" / "materials" / "Video 16" / "GICS Breakdown.xlsx"
EXPECTED_TAG_COUNTS = {"cyclical": 41, "defensive": 22, "both": 6}


def load_artifact(artifact_path):
    payload = json.loads(Path(artifact_path).read_text(encoding="utf-8"))
    industries = payload.get("industries") or []
    if len(industries) != 69:
        raise ValueError(f"artifact has {len(industries)} industries, expected 69")
    counts = Counter(row["cycle_tag"] for row in industries)
    if dict(counts) != EXPECTED_TAG_COUNTS:
        raise ValueError(f"artifact tag counts {dict(counts)} do not match the workbook")
    return payload


def workbook_tags(workbook_path):
    wb = load_workbook(workbook_path, data_only=True)
    ws = wb["Sheet1"]
    tags = {}
    for row in ws.iter_rows(min_row=4, max_row=87, max_col=7, values_only=True):
        _, _, _, industry, cyclical, defensive, both = row
        if industry is None:
            continue
        tag = (
            "cyclical"
            if cyclical
            else "defensive"
            if defensive
            else "both"
            if both
            else None
        )
        if tag is None:
            raise ValueError(f"workbook industry {industry} has no cycle tag")
        tags[str(industry).strip()] = tag
    return tags


def verify_against_workbook(industries, workbook_path):
    workbook = workbook_tags(workbook_path)
    artifact = {row["industry"]: row["cycle_tag"] for row in industries}
    if artifact != workbook:
        missing = sorted(set(workbook) - set(artifact))
        extra = sorted(set(artifact) - set(workbook))
        mismatched = sorted(
            name for name in set(artifact) & set(workbook) if artifact[name] != workbook[name]
        )
        raise ValueError(
            f"artifact does not match the workbook: missing={missing} extra={extra} mismatched={mismatched}"
        )


def main(argv=None):
    parser = argparse.ArgumentParser(description="Import GICS industry cycle tags into SQLite")
    parser.add_argument("--artifact", default=str(DEFAULT_ARTIFACT_PATH))
    parser.add_argument("--db", default=str(ticker_context_db.DEFAULT_DB_PATH))
    parser.add_argument("--skip-workbook-check", action="store_true")
    args = parser.parse_args(argv)

    payload = load_artifact(args.artifact)
    if not args.skip_workbook_check:
        verify_against_workbook(payload["industries"], WORKBOOK_PATH)

    con = ticker_context_db.connect(args.db)
    try:
        saved_tags = ticker_context_db.save_industry_tags(con, payload["industries"])
        aliases = [
            {
                "source": "yahoo",
                "source_industry": alias["yahoo_industry"],
                "gics_industry": alias["gics_industry"],
            }
            for alias in payload.get("yahoo_aliases") or []
        ]
        saved_aliases = ticker_context_db.save_industry_aliases(con, aliases)
    finally:
        con.close()

    print(f"imported {saved_tags} industry tags and {saved_aliases} yahoo aliases into {args.db}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

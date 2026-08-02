#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services import commodity_attribution_catalog as catalog_service

DEFAULT_SOURCE = (
    ROOT
    / "data"
    / "materials"
    / "Video 12"
    / "Cyclical_Commodities_Demand_Supply_Factors.pdf"
)
DEFAULT_OUTPUT = (
    ROOT
    / "data"
    / "local_system"
    / "commodity_attribution_evidence_catalog.v1.json"
)


def build_arg_parser():
    parser = argparse.ArgumentParser(
        description="Build the  commodity attribution evidence catalog."
    )
    parser.add_argument("--source-path", default=str(DEFAULT_SOURCE))
    parser.add_argument("--output-path", default=str(DEFAULT_OUTPUT))
    return parser


def main(argv=None):
    args = build_arg_parser().parse_args(argv)
    try:
        payload = catalog_service.write_commodity_attribution_catalog(
            args.output_path, args.source_path
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "output": str(Path(args.output_path)),
                "version": payload["version"],
                "source_document": payload["source_document"],
                "resources": len(payload["resources"]),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

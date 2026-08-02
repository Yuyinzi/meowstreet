#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services import non_oil_attribution_source_audit as audit_service

DEFAULT_CATALOG = (
    ROOT
    / "data"
    / "local_system"
    / "commodity_attribution_evidence_catalog.v1.json"
)
DEFAULT_OUTPUT = (
    ROOT / "data" / "local_system" / "non_oil_attribution_source_audit.v1.json"
)


def build_arg_parser():
    parser = argparse.ArgumentParser(
        description="Build the  non-oil attribution source audit artifact."
    )
    parser.add_argument("--catalog-path", default=str(DEFAULT_CATALOG))
    parser.add_argument("--output-path", default=str(DEFAULT_OUTPUT))
    return parser


def main(argv=None):
    args = build_arg_parser().parse_args(argv)
    try:
        payload = audit_service.write_non_oil_attribution_source_audit(
            args.output_path, args.catalog_path
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "output": str(Path(args.output_path)),
                "version": payload["version"],
                "source_catalog": payload["source_catalog"],
                "audits": len(payload["audits"]),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

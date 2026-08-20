import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db import market_data
from app.services import local_data_bootstrap


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Initialize local schemas and import stable GICS reference data"
    )
    parser.add_argument("--db-path", type=Path, default=market_data.DEFAULT_DB_PATH)
    parser.add_argument("--reference-path", type=Path, default=None)
    args = parser.parse_args(argv)
    try:
        result = local_data_bootstrap.bootstrap_local_data(
            args.db_path, args.reference_path
        )
    except (ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

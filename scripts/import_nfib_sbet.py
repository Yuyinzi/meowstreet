import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db import macro_indicators
from app.services import nfib_sbet_import


def fetch_nfib(artifacts, *, fetcher=None, source_url=None, cache_path=None, reference_date=None, http_client=None):
    from app.services import macro_refresh_official

    return macro_refresh_official.fetch_nfib(
        artifacts,
        fetcher=fetcher,
        source_url=source_url,
        cache_path=cache_path,
        reference_date=reference_date,
        http_client=http_client,
    )


def persist_nfib(db_path, artifacts, *, release_date=None):
    from app.services import macro_refresh_official

    return macro_refresh_official.persist_nfib(
        db_path, artifacts, release_date=release_date
    )


fetch_nfib_sbet = fetch_nfib
persist_nfib_sbet = persist_nfib


def main(argv=None):
    parser = argparse.ArgumentParser(description="Import official NFIB SBET PDF data")
    parser.add_argument(
        "--db-path", type=Path, default=macro_indicators.DEFAULT_DB_PATH
    )
    parser.add_argument(
        "--cache-path", type=Path, default=nfib_sbet_import.DEFAULT_CACHE_DIR
    )
    parser.add_argument("--source-url", default=None)
    parser.add_argument("--release-date")
    parser.add_argument("--fetch-pdf", action="store_true")
    parser.add_argument("--import-pdf", type=Path)
    args = parser.parse_args(argv)

    cache_path = Path(args.cache_path)
    artifacts = {}
    if args.import_pdf:
        source_url = args.source_url or nfib_sbet_import.DEFAULT_NFIB_SOURCE_URL
        fetch_nfib(
            artifacts,
            fetcher=lambda _source_url: Path(args.import_pdf).read_bytes(),
            source_url=source_url,
        )
        result = persist_nfib(
            args.db_path, artifacts, release_date=args.release_date
        )
        print(
            f"imported {result['observations']} nfib observations from {args.import_pdf}"
        )
    elif args.source_url:
        fetch_nfib(
            artifacts,
            source_url=args.source_url,
            cache_path=cache_path,
        )
        result = persist_nfib(
            args.db_path,
            artifacts,
            release_date=args.release_date,
        )
        print(
            f"imported {result['observations']} nfib observations from "
            f"{cache_path / 'nfib-sbet-current.pdf'}"
        )
    elif args.fetch_pdf:
        fetch_nfib(artifacts, cache_path=cache_path)
        print(f"fetched latest nfib report to {cache_path}")
    else:
        fetch_nfib(artifacts, cache_path=cache_path)
        result = persist_nfib(
            args.db_path,
            artifacts,
            release_date=args.release_date,
        )
        print(
            f"imported {result['observations']} nfib observations from latest discovered report"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

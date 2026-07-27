import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db import macro_indicators
from app.services import nfib_sbet_import


def main(argv=None):
    parser = argparse.ArgumentParser(description="Import official NFIB SBET PDF data")
    parser.add_argument(
        "--db-path", type=Path, default=macro_indicators.DEFAULT_DB_PATH
    )
    parser.add_argument(
        "--cache-path", type=Path, default=nfib_sbet_import.DEFAULT_CACHE_DIR
    )
    parser.add_argument(
        "--source-url", default=nfib_sbet_import.DEFAULT_NFIB_SOURCE_URL
    )
    parser.add_argument("--release-date")
    parser.add_argument("--fetch-pdf", action="store_true")
    parser.add_argument("--import-pdf", type=Path)
    args = parser.parse_args(argv)

    cache_path = Path(args.cache_path)

    if args.import_pdf:
        pdf_path = args.import_pdf
    elif args.fetch_pdf:
        cache_path.mkdir(parents=True, exist_ok=True)
        pdf_path = cache_path / "nfib-sbet-current.pdf"
        nfib_sbet_import.nfib_sbet.fetch_sbet_report(str(pdf_path), args.source_url)
    else:
        cache_path.mkdir(parents=True, exist_ok=True)
        pdf_path = cache_path / "nfib-sbet-current.pdf"
        nfib_sbet_import.nfib_sbet.fetch_sbet_report(str(pdf_path), args.source_url)

    con = macro_indicators.connect(args.db_path)
    try:
        count = nfib_sbet_import.import_cached_official_sbet(
            con, str(pdf_path), args.source_url, args.release_date
        )
    finally:
        con.close()

    print(f"imported {count} nfib observations from {pdf_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

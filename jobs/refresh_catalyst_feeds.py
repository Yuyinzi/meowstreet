import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.agents.catalyst_research.persistence import repository
from app.agents.catalyst_research.workflow import run_research
from app.http_client import HttpClient

_OK_STATUSES = {"completed", "completed_partial"}
_UNSUPPORTED_STATUS = "unsupported"


def _parser():
    parser = argparse.ArgumentParser(
        prog="refresh_catalyst_feeds",
        description="Run catalyst feed update mode for tickers with registered feed endpoints",
    )
    parser.add_argument("--db-path", type=Path, default=repository.DEFAULT_DB_PATH)
    parser.add_argument("--ticker", action="append", default=None, metavar="TICKER")
    return parser


def _tickers(args, connection):
    if args.ticker:
        return sorted({str(value).strip().upper() for value in args.ticker if str(value).strip()})
    return repository.list_feed_tickers(connection)


def _refresh_ticker(ticker, db_path, http_client):
    request = {"ticker": ticker, "years": 1, "mode": "update"}
    return asyncio.run(run_research(request, db_path=db_path, http_client=http_client))


def main(argv=None):
    args = _parser().parse_args(argv)
    connection = repository.connect(args.db_path)
    try:
        tickers = _tickers(args, connection)
    finally:
        connection.close()
    counts = {"ok": 0, "unsupported": 0, "failed": 0}
    with HttpClient() as http_client:
        for ticker in tickers:
            try:
                result = _refresh_ticker(ticker, args.db_path, http_client)
            except Exception as exc:
                counts["failed"] += 1
                print(f"ticker {ticker}: failed - {exc}", file=sys.stderr)
                continue
            status = result.get("status", "failed")
            if status in _OK_STATUSES:
                counts["ok"] += 1
                print(f"ticker {ticker}: {status}")
            elif status == _UNSUPPORTED_STATUS:
                counts["unsupported"] += 1
                print(f"ticker {ticker}: unsupported (no source registry)")
            else:
                counts["failed"] += 1
                print(f"ticker {ticker}: failed - status {status}", file=sys.stderr)
    print(
        "catalyst feed refresh completed: "
        f"ok={counts['ok']} unsupported={counts['unsupported']} failed={counts['failed']}"
    )
    return 0 if counts["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

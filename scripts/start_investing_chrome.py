import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.data_sources.investing_chrome import start_investing_chrome


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Launch dedicated Chrome for interactive Investing.com verification"
    )
    parser.add_argument("--profile-dir", type=Path, default=None)
    parser.add_argument("--cdp-port", type=int, default=None)
    parser.add_argument(
        "--headless",
        action="store_true",
        help="diagnostic only: run headless; production refresh uses "
        "scripts/refresh_investing_rendered.py",
    )
    parser.add_argument("--initial-url", default=None)
    args = parser.parse_args(argv)
    kwargs = {"profile_dir": args.profile_dir, "headless": args.headless}
    if args.cdp_port is not None:
        kwargs["cdp_port"] = args.cdp_port
    if args.initial_url:
        kwargs["initial_url"] = args.initial_url
    start_investing_chrome(**kwargs)


if __name__ == "__main__":
    raise SystemExit(main())

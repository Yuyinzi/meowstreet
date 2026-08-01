import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db import macro_indicators
from app.services.investing_rendered_refresh import (
    DEFAULT_CDP_PORT,
    DEFAULT_LOCK_PATH,
    DEFAULT_PROFILE_DIR,
    DEFAULT_READY_TIMEOUT_SECONDS,
    refresh_investing_rendered,
)

_REMEDIATION = (
    "start an interactive Chrome session with the profile, sign in and complete "
    "any Investing.com verification, fully close Chrome, then retry the job"
)


def main(argv=None, refresh=refresh_investing_rendered):
    parser = argparse.ArgumentParser(
        description="Refresh the  Iron Ore 62% CFR China rendered "
        "Investing.com history unattended with the persistent browser profile"
    )
    parser.add_argument(
        "--db-path", type=Path, default=macro_indicators.DEFAULT_DB_PATH
    )
    parser.add_argument(
        "--profile-dir",
        type=Path,
        default=DEFAULT_PROFILE_DIR,
        help="Investing persistent Chrome profile directory",
    )
    parser.add_argument(
        "--cdp-port",
        type=int,
        default=DEFAULT_CDP_PORT,
        help="dedicated CDP port for the temporary headless Chrome",
    )
    parser.add_argument(
        "--lock-file",
        type=Path,
        default=DEFAULT_LOCK_PATH,
        help="lock file guarding against overlapping runs",
    )
    parser.add_argument(
        "--readiness-timeout",
        type=int,
        default=DEFAULT_READY_TIMEOUT_SECONDS,
        help="seconds to wait for the headless Chrome CDP endpoint",
    )
    args = parser.parse_args(argv)
    con = macro_indicators.connect(args.db_path)
    try:
        result = refresh(
            con,
            profile_dir=args.profile_dir,
            cdp_port=args.cdp_port,
            lock_path=args.lock_file,
            readiness_timeout=args.readiness_timeout,
        )
    except ValueError as exc:
        print(
            f" investing rendered refresh failed: {exc}\n{_REMEDIATION}",
            file=sys.stderr,
        )
        return 1
    finally:
        con.close()
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

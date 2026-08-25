#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

SKIP_REFRESH=0
SETUP_ONLY=0
for arg in "$@"; do
  case "$arg" in
    --skip-refresh) SKIP_REFRESH=1 ;;
    --setup-only) SETUP_ONLY=1 ;;
    -h|--help)
      echo "Usage: ./start.sh [--skip-refresh] [--setup-only]"
      echo
      echo "Sets up the environment, installs dependencies, initializes the local"
      echo "database, runs the macro data refresh, and starts the server."
      echo
      echo "  --skip-refresh  skip the macro data refresh job"
      echo "  --setup-only    stop after setup and refresh; do not start the server"
      exit 0
      ;;
    *)
      echo "error: unknown option: $arg" >&2
      exit 1
      ;;
  esac
done

step() {
  printf '\n==> %s\n' "$*"
}

PYTHON=""
for candidate in python3.13 python3; do
  if command -v "$candidate" >/dev/null 2>&1 \
    && "$candidate" -c 'import sys; raise SystemExit(sys.version_info < (3, 13))'; then
    PYTHON="$candidate"
    break
  fi
done
if [ -z "$PYTHON" ]; then
  echo "error: Python 3.13 or newer is required" >&2
  exit 1
fi
if ! command -v node >/dev/null 2>&1 || ! command -v npm >/dev/null 2>&1; then
  echo "error: Node.js 20.11 or newer (with npm) is required" >&2
  exit 1
fi

if [ ! -d .venv ]; then
  step "Creating virtual environment"
  "$PYTHON" -m venv .venv
fi

step "Installing Python dependencies"
.venv/bin/pip install -r requirements.txt

if [ ! -f .env ]; then
  step "Creating .env from .env.example"
  cp .env.example .env
  echo "edit .env to configure optional API keys (OPENAI_API_KEY, EIA_KEY)"
fi

step "Installing frontend dependencies"
npm ci

step "Building dashboard assets"
npm run build

step "Initializing local database"
.venv/bin/python scripts/bootstrap_local_data.py

if [ "$SKIP_REFRESH" -eq 0 ]; then
  if ! curl -fsS --max-time 2 http://127.0.0.1:9222/json/version >/dev/null 2>&1; then
    step "Launching dedicated Chrome for Investing.com (CDP port 9222)"
    if .venv/bin/python scripts/start_investing_chrome.py; then
      echo "a Chrome window was opened on Investing.com"
      echo "sign in, complete any verification, confirm a historical-data page"
      echo "renders, and keep the window open during the refresh"
      if [ -t 0 ]; then
        read -r -p "press Enter when the Investing.com session is ready..."
      fi
    else
      echo "warning: could not launch Chrome; the tracked_commodities refresh lane" >&2
      echo "warning: will fail without a verified Investing.com session (see README)" >&2
    fi
  fi
  step "Refreshing macro data (this can take a while)"
  if ! .venv/bin/python jobs/refresh_macro_data.py; then
    echo "warning: macro data refresh reported failures; dashboards may show insufficient data" >&2
  fi
else
  echo "skipping macro data refresh (--skip-refresh)"
fi

if [ "$SETUP_ONLY" -eq 1 ]; then
  step "Setup complete"
  exit 0
fi

step "Starting server at http://127.0.0.1:8797"
exec .venv/bin/uvicorn app.api:app --reload --port 8797 --workers 2

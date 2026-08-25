# Meowstreet

Meowstreet is a local-first trade workflow console for assessing market context, reviewing a ticker, and identifying the next research or risk-management step.

## What it does

- Brings market context and macro signals into one workspace
- Organizes ticker research into a repeatable workflow
- Shows process readiness, missing inputs, and next actions

## Screenshots

![Meowstreet dashboard](static/dashboard.png)
![Meowstreet dashboard](static/ISM.png)

## Getting started

Prerequisites: Python 3.13 and Node.js 20.11 or newer.

### Quick setup

The fastest path is the one-command setup script. It creates the virtual
environment, installs Python and frontend dependencies, copies `.env.example`
to `.env` when missing, builds the dashboard assets, bootstraps the local
database, runs the macro data refresh, and starts the server:

```bash
./start.sh
```

Use `./start.sh --skip-refresh` to skip the macro data refresh, or
`./start.sh --setup-only` to stop before starting the server.

Open `http://127.0.0.1:8797` in your browser.

### Manual setup

To run the steps individually instead, create a virtual environment, install
dependencies, build the dashboard assets, bootstrap the stable reference data,
and start the server:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
npm ci
npm run build
.venv/bin/python scripts/bootstrap_local_data.py
.venv/bin/uvicorn app.api:app --reload --port 8797 --workers 2
```

### Investing.com browser session (CDP)

The tracked commodities lane (COMEX Copper, LME 3M Copper, Iron Ore 62% CFR
China) fetches from Investing.com through a real Chrome window driven over the
Chrome DevTools Protocol on port 9222. Headless automation is not supported —
Investing.com blocks it — so a one-time manual verification is required:

```bash
.venv/bin/python scripts/start_investing_chrome.py
```

1. In the Chrome window that opens, sign in to Investing.com and complete any
   CAPTCHA/anti-bot verification.
2. Confirm a price historical-data page renders with the Date/Price table.
3. Keep that Chrome process open while refresh jobs run.

The profile persists at `data/private/investing_chrome_profile/`, so
verification usually survives restarts; repeat the steps above when a refresh
reports a session or re-verification error. `./start.sh` detects a missing CDP
endpoint before the refresh and launches this Chrome window for you. See
`docs/operations/macro-data-cron.md` for the dedicated incremental cron job.

## Testing

Run the test suite:

```bash
npm run build
.venv/bin/pytest -q
```

## Data and refresh jobs

### Local data

Meowstreet keeps application data on your machine. The bootstrap command imports
stable GICS reference rows only. It imports no time series or reports and makes
no network calls. Bootstrap is optional for server startup, but recommended for
ticker-context features.

Dashboards initially show insufficient-data states until scheduled refresh jobs
populate observations. Cron jobs own time-series and report ingestion; bootstrap
does not run those jobs.

### Scheduled macro refresh

`jobs/refresh_macro_data.py` runs the enabled source lanes concurrently by
default. The current registry uses fixed lanes for `fred_macro`, `credit`,
`yahoo`, ISM Manufacturing and Services, `consumer`, `census`, `nfib`, `fomc`,
`tracked_commodities`, `cftc`, `eia`, `shfe`, `dce_sina`, `dol`, `bls`, and
`federal_reserve`. Each enabled lane has one serial queue; independent lanes
overlap, and the number of lane workers is derived from the enabled plan. There
is no worker-count flag. Use `--serial` as the recovery and diagnostic mode
when reproducing a provider issue.

Every FRED consumer, including the separate credit lane, shares one global
request-start limiter of 600 ms. SQLite writes are serialized through one
writer gate with a 60-second wait timeout. A fetch or enrichment failure blocks
only dependent work; `blocked` also covers work whose lane stopped admitting
tasks after `--stop-on-error`, or work cancelled/interrupted before it started.
Unrelated lanes continue. Missing `OPENAI_API_KEY` is an intentional skipped
ISM enrichment; when a key is available, enrichment is enabled automatically.

The refresh owns one aggregate progress surface. TTY runs show live lane
activity; cron and redirected output are stable plain text in plan order. The
final line reports `ok`, `skipped`, `failed`, and `blocked` counts. Failures and
blocked tasks produce a non-zero exit status. Ctrl+C stops admission at a safe
boundary and exits 130.

Copy `.env.example` to `.env` to configure optional assistant and offline AI
enrichment features. Deterministic dashboard imports, including core ISM fields,
do not require `OPENAI_API_KEY`. When a key is configured, the macro refresh
automatically enriches saved ISM reports; without one, those enrichment tasks are
reported as skipped.

Keep API credentials and other sensitive settings in `.env`; Git ignores this
file.

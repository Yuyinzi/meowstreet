# Meowstreet

Meowstreet is a local-first trade workflow console for assessing market context, reviewing a ticker, and identifying the next research or risk-management step.

## What it does

- Brings market context and macro signals into one workspace
- Organizes ticker research into a repeatable workflow
- Shows process readiness, missing inputs, and next actions

## Screenshots

![Meowstreet dashboard](static/dashboard.png)
![Meowstreet dashboard](static/ISM.png)
## Run locally

Prerequisites: Python 3.13 and Node.js 20.11 or newer.

Create a virtual environment, install dependencies, build the dashboard assets,
bootstrap the stable reference data, and start the server:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
npm ci
npm run build
.venv/bin/python scripts/bootstrap_local_data.py
.venv/bin/uvicorn app.api:app --reload --port 8797 --workers 2
```

Open `http://127.0.0.1:8797` in your browser.

## Test

Run the test suite:

```bash
npm run build
.venv/bin/pytest -q
```

## Local data

Meowstreet keeps application data on your machine. The bootstrap command imports
stable GICS reference rows only. It imports no time series or reports and makes
no network calls. Bootstrap is optional for server startup, but recommended for
ticker-context features.

Dashboards initially show insufficient-data states until scheduled refresh jobs
populate observations. Cron jobs own time-series and report ingestion; bootstrap
does not run those jobs.

Copy `.env.example` to `.env` to configure optional assistant features. `.env`
is not needed for deterministic dashboards and is required only for assistant
features. Keep API credentials and other sensitive settings in `.env`; Git
ignores this file.

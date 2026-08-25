# Macro Data Cron Refresh

This project uses one local wrapper command for scheduled data refreshes:

```bash
cd /Users/littlemay/work/meowstreet/meowstreet
mkdir -p logs
.venv/bin/python jobs/refresh_macro_data.py
```

The refresh uses source-lane concurrency by default. The enabled plan creates
one serial queue per fixed source lane, so independent providers can overlap
without reordering tasks inside a lane. The number of workers is derived from
the enabled lanes; there is no worker-count option. Use `--serial` for recovery
or diagnostics when an issue needs a deterministic, single-worker run.

The current lanes are `fred_macro`, `credit`, `yahoo`, `ism_manufacturing`,
`ism_services`, `consumer`, `census`, `nfib`, `fomc`, `tracked_commodities`,
`cftc`, `eia`, `shfe`, `dce_sina`, `dol`, `bls`, and `federal_reserve`.

The scheduled refresh updates implemented official market and macro sources:

- Yahoo benchmark indices: S&P 500 (`us_sp500`), Nasdaq 100 (`us_nasdaq_100`), Nasdaq Composite (`us_nasdaq_composite`), and DJIA (`us_djia`). To refresh all configured benchmarks manually, run `.venv/bin/python scripts/refresh_benchmark_market_data.py --all`.
- US Rates / Liquidity FRED data
- Building Permits: U.S. Census Bureau New Residential Construction history
- Consumer Sentiment: University of Michigan Table 1 (aggregate) and Table 5 (components) from the official website, plus FRED capacity series: BOGZ1FL010000336Q (household debt-to-GDP), TDSP (debt service ratio), PSAVERT (personal saving rate), HHMSDODNS (mortgage liabilities)
- M2 FRED `M2SL`
- ISM Manufacturing and Services official latest report imports, with deterministic core fields and optional offline AI enrichment
- GDP/S&P FRED relationship CSV data
- FOMC calendar, statement and minutes documents, statement policy-tone extraction, and minutes structure extraction
- Lumber: Yahoo Finance `LBR=F` daily closes (active series `lumber_cme_lbr_yahoo_v1`)

ISM official report imports have a deterministic core phase and an optional AI
enrichment phase. Raw source snapshots and per-section AI extraction
checkpoints survive failures without replacing previously promoted data.

ISM enrichment is planned as `skipped` when `OPENAI_API_KEY` is missing. A
configured key enables enrichment automatically. A configured-but-failing AI
extraction is `failed`; the deterministic core import remains committed.

Consumer sentiment refreshes download the complete official Michigan monthly history from the UM Time Series Data form and replace all stored rows. The website is the sole UMCSI source. No workbook (UMCSI.xlsx) or FRED UMCSENT series is imported. Capacity series use the FRED CSV client and are fully replaced on each refresh.

## P12 Lumber (Yahoo LBR)

The active lumber series `lumber_cme_lbr_yahoo_v1` uses Yahoo Finance `LBR=F` daily closes from `2022-08-08` onward. The prior `lumber` Investing.com rows are an immutable audit archive and receive no new writes.

```bash
.venv/bin/python scripts/audit_lumber_overlap.py
.venv/bin/python scripts/import_lumber.py --initial
.venv/bin/python scripts/import_lumber.py
```

- The audit command is read-only: it compares archived `lumber` against Yahoo `LBR=F` shared dates and writes `data/local_system/audits/lumber_overlap_v1.json` only when the overlap has no unequal shared prices.
- `--initial` stores the successful overlap audit and LBR observations in one SQLite transaction; the JSON file remains an on-demand export. Plain runs use a 14-calendar-day overlap and upsert by `(series_id, date)`.
- Refresh failures retain the last active LBR observations and never fall back to Investing.

## Investing Rendered History (Interactive Chrome Cron)

The markets COMEX Copper (`copper_comex`), LME 3M Copper (`copper_lme`), and Iron Ore 62% CFR China (`iron_ore_62_cfr_china`) are refreshed from the rendered Investing.com historical-data table by a dedicated job that attaches to an already-open, verified interactive Chrome session on CDP port 9222. It runs the rendered-table incremental importer but never starts or closes Chrome. One run handles the three markets in order and reports each under `ranges` or `no_new_data`. It is kept out of the broad macro refresh runner because it depends on an authenticated browser session and needs a distinct failure path.

### Bootstrap and Manual Recovery

The persistent profile must hold a valid Investing.com session, and its Chrome process must remain open while cron runs. Start it after a restart, session expiry, or CAPTCHA/anti-bot verification:

```bash
.venv/bin/python scripts/start_investing_chrome.py
```

1. In the Chrome window, log in to Investing.com and complete any verification.
2. Confirm a price historical-data page renders with the Date/Price table.
3. Keep that Chrome process open while cron runs.

Investing.com returns HTTP 403 to the project’s headless Chrome, so headless automation is not supported. When the job fails with a session, CAPTCHA, rendered-table, navigation, or CDP error, repeat the manual bootstrap above and retry.

### Cron

Add a separate cron line (not the broad macro cron) scheduled after the expected daily close, for example 19:00 Monday–Friday in the machine's Asia/Shanghai timezone:

```cron
0 19 * * 1-5 cd /Users/littlemay/work/meowstreet/meowstreet && .venv/bin/python scripts/refresh_investing_rendered.py >> logs/investing-rendered.log 2>&1
```

The `logs/` directory must exist before cron runs because shell redirection opens `logs/investing-rendered.log` before starting Python. This command is idempotent and never overwrites existing logs:

```bash
mkdir -p logs
```

- A dedicated `fcntl` lock file prevents overlapping runs; a concurrent run fails fast with "refresh already running" and exits non-zero.
- Chrome must already be open through `scripts/start_investing_chrome.py`; cron attaches to it through CDP port 9222 and leaves it running.
- An already-up-to-date series is a successful no-op: the job exits zero and reports zero observations with the affected market in `no_new_data`. Each of the three markets appears under `ranges` or `no_new_data` on every run.
- Session, CAPTCHA, rendered-table, navigation, and CDP failures exit non-zero and print an actionable remediation message to stderr.

### Manual Run

```bash
.venv/bin/python scripts/refresh_investing_rendered.py
```

Optional configuration: `--cdp-port`, `--lock-file`, `--readiness-timeout`, and `--db-path`. The CLI never prints cookies or credentials.

## ISM Official Reports

The ISM command separates deterministic official-field imports from optional
offline AI enrichment:

```bash
.venv/bin/python scripts/fetch_ism_reports.py --survey all --latest-only --core-only
.venv/bin/python scripts/fetch_ism_reports.py --survey all --enrichment-only
```

- `--core-only` fetches and deterministically imports official ISM fields without an AI client.
- `--enrichment-only` reads successful saved snapshots and never refetches the report.
- The default ISM command runs core import and automatically attempts enrichment when `OPENAI_API_KEY` exists.
- Missing credentials produce `skipped`, not `failed`; configured extraction errors produce `failed` while core rows remain committed.

The default command is equivalent to running the core phase followed by the
eligible enrichment phase:

```bash
.venv/bin/python scripts/fetch_ism_reports.py --survey manufacturing --latest-only
.venv/bin/python scripts/fetch_ism_reports.py --survey services --latest-only
```

Historical import:

```bash
.venv/bin/python scripts/fetch_ism_reports.py --survey services --report-month 2026-06 --core-only
.venv/bin/python scripts/fetch_ism_reports.py --survey services --backfill-since 2024 --core-only
.venv/bin/python scripts/fetch_ism_reports.py --survey services --missing-only --core-only
```

### Source Routing

For the latest released month, the importer first discovers the matching PR Newswire archive item and uses it when available; if no matching archive item is found, it falls back to the ISM World monthly URL. Historical months use matching PR Newswire archive items, and a missing historical archive result is skipped rather than sent to a yearless ISM World URL.

### AI Configuration

Set in `.env` loaded through `app.llm`:

```env
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o
OPENAI_BASE_URL=https://api.openai.com/v1
```

### Failure Recovery

Failed extraction stores the raw source snapshot and per-section checkpoints. Previously promoted data is never replaced by an incomplete extraction. Core rows remain committed when an enrichment task fails.

Retry a failed Services extraction offline:

```bash
.venv/bin/python scripts/extract_ism_services_report_ai.py \
  --source-url https://www.ismworld.org/.../services/june/ \
  --db-path data/local_system/market_data.sqlite
```

### Concurrency

- **Section concurrency** (default 3): controls parallel AI calls within one report.
- **Report concurrency** (default 1): controls parallel reports.

```bash
.venv/bin/python scripts/fetch_ism_reports.py --survey services --report-concurrency 2
```

Official data is promoted only after all five factual sections validate.

## Cron

Install with `crontab -e`:

```cron
0 12,20 * * * cd /Users/littlemay/work/meowstreet/meowstreet && .venv/bin/python jobs/refresh_macro_data.py >> logs/macro_refresh.log 2>&1
30 8 * * 2-6 cd /Users/littlemay/work/meowstreet/meowstreet && .venv/bin/python jobs/refresh_macro_data.py --skip-yahoo --skip-rates --skip-consumer-sentiment --skip-m2 --skip-ism --skip-gdp --skip-fomc --skip-nfib-sbo --skip-nfib-sbo-regional --skip-cyclical-commodities --skip-oil --skip-tracked-commodities >> logs/macro_refresh.log 2>&1
```

The `logs/` directory must exist before cron runs because shell redirection opens `logs/macro_refresh.log` before starting Python.

The schedule uses the machine's local timezone. On the current local Mac setup, that means Asia/Shanghai time.

The second line runs the Lumber Yahoo refresh on weekday mornings at 08:30 Asia/Shanghai. Refresh failures retain the last active LBR observations.

### Refresh Output and Verbosity

The refresh runner records one result for every planned provider task. Each task
has one of these statuses:

- `ok`: the provider completed successfully or had no new data to import.
- `skipped`: the task was intentionally not run, such as optional ISM enrichment without `OPENAI_API_KEY`.
- `failed`: the task ran but returned an error.
- `blocked`: a required dependency failed or was blocked; the task is not run.

By default a failed task does not stop unrelated lanes. `--stop-on-error` stops
admission of later work in the failed lane only; other lanes continue. A
failure or blocked task makes the overall command exit non-zero. Ctrl+C stops
new task admission at a safe boundary, leaves active network/database work to
finish safely, and exits with status 130.

Use verbose mode when investigating a successful run:

```bash
.venv/bin/python jobs/refresh_macro_data.py --verbose
```

`jobs/refresh_macro_data.py --verbose` replays successful provider and FOMC detail output. The refresh owns one aggregate progress surface: an interactive TTY shows live lane activity and aggregate counts, while redirected cron logs receive stable plain-text summaries in plan order with no cursor movement or ANSI controls. Failed and blocked diagnostics are always reported. The final line has deterministic aggregate counts, for example:

```text
macro data refresh completed: ok=18 skipped=2 failed=0 blocked=0
```

All FRED consumers share one in-process limiter that waits at least 600 ms
between request starts, including retries and the separate `credit` lane.
SQLite write stages use one shared writer gate and wait no longer than 60
seconds. Fetch and AI work never holds that gate.

## Manual Run

Run all refreshes:

```bash
cd /Users/littlemay/work/meowstreet/meowstreet
.venv/bin/python jobs/refresh_macro_data.py
```

Economic Confirmation refreshes DOL claims, the official BLS Employment Situation HTML release and summary tables, and Federal Reserve G.17 independently. A failed source leaves its prior observations intact, allows remaining sources to run, and makes the command exit nonzero.

Claims history is fetched in one official OUI National weekly-claims report request. The report supplies seasonally adjusted Initial Claims and Continued Claims; source failure keeps prior rows, allows BLS and G.17 to run, and returns a nonzero command status.

Skip a provider group:

```bash
.venv/bin/python jobs/refresh_macro_data.py --skip-yahoo
.venv/bin/python jobs/refresh_macro_data.py --skip-gdp
.venv/bin/python jobs/refresh_macro_data.py --skip-rates
.venv/bin/python jobs/refresh_macro_data.py --skip-m2
.venv/bin/python jobs/refresh_macro_data.py --skip-building-permits
.venv/bin/python jobs/refresh_macro_data.py --skip-ism
.venv/bin/python jobs/refresh_macro_data.py --skip-consumer-sentiment
.venv/bin/python jobs/refresh_macro_data.py --skip-fomc
.venv/bin/python jobs/refresh_macro_data.py --skip-lumber
```

Stop after first provider failure:

```bash
.venv/bin/python jobs/refresh_macro_data.py --stop-on-error
```

## Consumer Sentiment Manual Commands

Fetch Michigan CSV files (Table 1 and Table 5) from the University of Michigan website:

```bash
cd /Users/littlemay/work/meowstreet/meowstreet
.venv/bin/python scripts/import_consumer_sentiment.py --fetch-michigan-csv data/consumer_sentiment/
```

Import Michigan CSV files into the database:

```bash
cd /Users/littlemay/work/meowstreet/meowstreet
.venv/bin/python scripts/import_consumer_sentiment.py --michigan-csv-import data/consumer_sentiment/table_1.csv data/consumer_sentiment/table_5.csv
```

Fetch FRED capacity series CSV files:

```bash
.venv/bin/python scripts/import_consumer_sentiment.py --fetch-fred-csv data/consumer_sentiment/
```

Import FRED capacity series CSV files into the database:

```bash
.venv/bin/python scripts/import_consumer_sentiment.py --fred-csv-import data/consumer_sentiment/
```

### Consumer Sentiment Refresh Failure Recovery

When consumer sentiment refresh fails, check logs to determine which step failed:

- **Fetch failed:** Verify upstream Michigan website availability and retry. The Michigan website occasionally returns empty responses; re-running the same command typically resolves transient failures.
- **Import failed:** Check that the CSV files exist at the expected path and match the expected format (date, value columns for Table 1; date, expectations, current_conditions for Table 5). Verify the database is accessible and writable.
- **Both fetch and import succeeded but no new data appeared:** Confirm the expected CSV file was written to disk, then re-run the import step manually. If the parsed row count is zero, inspect the CSV header row and column names.

FRED fetch failures indicate upstream API availability. FRED import failures mean the CSV directory is missing one or more of the four expected series files.

## FOMC Release Automation

Each twice-daily refresh performs these four ordered FOMC stages:

1. **Calendar** — imports `data/downloads/fomc_calendar.csv` into the database
2. **Documents** — checks only the latest completed meeting that is still missing each document type; it does not poll stored historical documents
3. **Policy tone** — runs the existing statement extractor-reviewer pipeline for newly stored document hashes
4. **Minutes structure** — runs the existing minutes extractor-reviewer pipeline for newly stored minutes document hashes (requires an approved statement tone for the same meeting)

Missing pre-release document links are normal skips (unavailable). Document or extraction failures after a link becomes available are reported as task failures and retry at the next scheduled run.

The statement and minutes generators require their existing `.env` configuration loaded through `app.llm`:

```env
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o
OPENAI_BASE_URL=https://api.openai.com/v1
```

### Manual Recovery Commands

```bash
.venv/bin/python scripts/fetch_fomc_documents.py --document-type all
.venv/bin/python scripts/generate_fomc_policy_tone.py --all
.venv/bin/python scripts/generate_fomc_minutes_structure.py --all
```

Use `--backfill` only to retrieve missing documents from older completed meetings:

```bash
.venv/bin/python scripts/fetch_fomc_documents.py --document-type all --backfill
```

## Logs

Cron appends output to:

```text
logs/macro_refresh.log
logs/investing-rendered.log
```

The command prints each task with its `ok`, `skipped`, `failed`, or `blocked`
status. It continues after provider failures by default but exits with code `1`
if any task failed or is blocked.

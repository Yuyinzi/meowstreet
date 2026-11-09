# Macro Data Freshness Runbook

How to check whether a stale-looking dashboard metric is genuinely broken or
simply waiting on its publication schedule. Distilled from the 2026-08-18
freshness audit. Read `macro-data-cron.md` first for the task inventory.

## The Golden Rule

Lag days alone never indicate a bug. Compare `max(date)` against the source's
**publication schedule**, not against today. A monthly series that is 50 days
old is usually current; a daily series that is 5 days old is usually broken.

## Check Scope

Check active scheduled sources only. GDP relationship freshness checks cover
`us_sp500_gdp` only. Exclude Europe/China GDP workbook relationships and the
legacy `sp500_pe` series from freshness checks, gap reports, and recovery tasks.
These exclusions do not apply to S&P 500 benchmark prices or the US GDP/S&P 500
relationship. Archived or superseded commodity series are also outside the
active freshness inventory.

## Triage Workflow

Run these steps in order. Stop as soon as one explains the lag.

### 1. Read the current state from the DB

All dashboard series live in `data/local_system/market_data.sqlite`.
Most use `macro_indicator_points`; several families use dedicated tables
(`ism_industry_rankings`, `economic_confirmation_current_observations`,
`macro_event_documents`, SHFE/DCE tables, ...).

```bash
sqlite3 data/local_system/market_data.sqlite \
  "select series_id, max(date), count(*) from macro_indicator_points \
   where series_id like '<pattern>%' and series_id != 'sp500_pe' group by series_id order by max(date)"
```

### 2. Classify by frequency and compute the expected latest date

Use the release calendar below. If `max(date)` matches the latest release
that should exist, the series is healthy — do not "fix" it.

### 3. Check the cron logs for task failures

```bash
grep -n -i "failed\|error" logs/macro_refresh.log | tail -40
tail -20 logs/investing-rendered.log
```

Cron entries (check with `crontab -l`):

- `0 12,20 * * *` — `jobs/refresh_macro_data.py` → `logs/macro_refresh.log`
- `0 19 * * 1-5` — `scripts/refresh_investing_rendered.py` →
  `logs/investing-rendered.log` (requires the interactive Chrome session
  on CDP port 9222; see macro-data-cron.md)

A task that failed yesterday but succeeded today is usually self-healed —
re-check the DB before digging into code.

### 4. Probe the upstream source directly

Only when the schedule says newer data should exist. Verify whether the
upstream has actually published it. Every fetcher is importable, so probe
without writing to the DB, e.g.:

```python
from app.data_sources import oil
payload = oil.fetch_oil_observations(api_key, price_start_date="2026-08-01")
```

For web sources, fetch the release page (Fed G.17 page carries its release
date; FOMC calendar lists minutes release dates; EIA/EIA API returns its
latest row).

- Upstream has nothing newer → healthy, done.
- Upstream has newer data → real bug, go to step 5.

### 5. Root-cause the pipeline

Failure modes actually observed, most likely first:

1. **Task not registered in cron** — the importer exists but
   `jobs/refresh_macro_data.py` does not schedule it (check `_planned_tasks`,
   and `git log -p jobs/refresh_macro_data.py` for deliberate removals).
2. **Hardcoded or stale source locator** — e.g. a URL pinned to last month's
   PDF. Prefer discovery over pinned URLs.
3. **Upstream format/wording drift** — parser regexes stop matching (ISM
   changed its contraction sentence to past tense in July 2026). Reproduce by
   feeding the stored raw snapshot (`ism_report_source_snapshots.raw_html`)
   through the parser.
4. **Source discontinued** — upstream stops the series entirely (OECD
   % -of-GDP series on FRED). Needs a spec-approved replacement series, not a
   retry loop.
5. **Timing race** — cron runs before same-day publication (noon run vs
   evening SHFE data; 20:00 run vs 21:15 CST G.17 release). Self-heals on the
   next run; only fix if it never converges.
6. **Silent fallback in tests, not production** — if tests were "passing"
   while production lagged, check whether the test suite hits the real
   network when a stub is missing. `jobs/refresh_macro_data.run(argv, **mains)`
   defaults every task main to `None` for this reason: an unstubbed task must
   be unplanned, never real.

### 6. Fix, backfill, verify

- Fix code + tests; reuse cached/raw snapshots where possible (ISM section
  extractions are checkpointed by source hash — re-runs cost no LLM calls).
- Backfill with the real importer, then re-query the DB.
- Run the focused test files, then the full suite: `.venv/bin/pytest -q`.
  The suite must never make real network calls.

## Release Calendar

All times ET. "Expected latest" is relative to a hypothetical check date;
recompute from the schedule.

| Data | Frequency | Release timing | Investigate when |
|---|---|---|---|
| Initial/continuing claims | weekly | Thu 8:30, reference week ending prior Sat | `max(reference_period)` older than the latest Thursday's week |
| COT | weekly | Fri ~15:30, positions as of Tue | > 10 days |
| EIA oil stocks/production/imports | weekly | Wed 10:30, week ending prior Fri | > 10 days |
| EIA WTI/Brent spot | daily | ~2 day publication lag | > 5 days |
| Yahoo/Sina/DCE/SHFE market series | daily, trading days | same/next day | > 5 days |
| Investing rendered (COMEX/LME/iron ore 62) | daily | weekday 19:00 cron via Chrome CDP | > 5 weekdays; check Chrome session first |
| USD broad/AFE/EME (Fed) | daily | ~1 day lag | > 7 days |
| CPI (`cpi_yoy`, P12 CPI series) | monthly | mid-month (~12th) 8:30 | after release day with old month |
| Core PCE, personal saving rate | monthly | end of month (~26th) 8:30, BEA Personal Income | same |
| Building permits SAAR | monthly | ~17th-18th 8:30, Census New Residential Construction | same |
| M2 money stock | monthly | 4th Tuesday, H.6 | same |
| Employment situation (payrolls, unemployment, AHE, hours) | monthly | first Fri 8:30 | same |
| G.17 (industrial production, capacity utilization) | monthly | mid-month (~15th) 9:15 | after the release date on the G.17 page |
| ISM manufacturing / services | monthly | 1st / 3rd business day; `report_month` is the DATA month | `latest_released_report_month(survey_type=...)` in `app/services/ism_report_ingestion.py` is the source of truth; cron uses `--latest-only` discovery |
| NFIB SBET | monthly | 2nd Tuesday | if newer PDF exists under nfib.com wp-content uploads |
| UMCSI consumer sentiment | monthly | preliminary mid-month, final end of month | SCA front page shows a newer month than the DB |
| Household debt-to-GDP (FRED `BOGZ1FL010000336Q`), mortgage liabilities | quarterly | Z.1, ~10 weeks after quarter end | > 120 days |
| Debt service ratio (TDSP) | quarterly | ~same as Z.1 | > 120 days |
| US GDP/S&P 500 relationship (`us_sp500_gdp`) | quarterly | advance estimate ~4 weeks after quarter end | > 100 days |
| FOMC statement/tone | event-driven, 8/yr | meeting day 14:00 | after a meeting day with no new statement |
| FOMC minutes/structure | event-driven | 3 weeks after each meeting | after the minutes release date on the FOMC calendar page |

## Quick Commands

```bash
# Staleness overview
sqlite3 data/local_system/market_data.sqlite \
  "select series_id, max(date) from macro_indicator_points where series_id != 'sp500_pe' group by series_id order by max(date)"

# Non-macro_indicator_points families
sqlite3 data/local_system/market_data.sqlite \
  "select survey_type, max(date) from ism_industry_rankings group by survey_type"
sqlite3 data/local_system/market_data.sqlite \
  "select series_id, max(reference_period) from economic_confirmation_current_observations group by series_id"
sqlite3 data/local_system/market_data.sqlite \
  "select event_id, document_type, substr(fetched_at,1,10) from macro_event_documents order by event_id desc limit 10"

# Cron health
grep -c "failed" logs/macro_refresh.log
tail -30 logs/macro_refresh.log

# Current cron schedule
crontab -l
```

## Case Studies (2026-08-18)

- `oil_*` stuck at 07-17/07-20: EIA request bug, fixed by commit `5fc7c91`;
  after the fix the DB matched EIA's latest published rows (weekly 08-07,
  spot 08-11) — no further action needed.
- `copper_comex/lme`, `iron_ore_62_cfr_china` stuck at 07-31: their
  cron entry was never installed after the 08-01 reroute to Investing
  rendered. Fixed by installing the documented weekday 19:00 cron line.
- `lumber` stuck at 07-29: archived series by design; the live series is
  `lumber_cme_lbr_yahoo_v1`. Check archived-series lists before treating
  an old series as broken.
- ISM manufacturing rankings missing 2026-07: workbook importer removed from
  cron (`c8a1aed`) while the AI path hardcoded `rankings: 0`, plus a new
  past-tense contraction sentence the parser regex rejected. Fixed in
  `de88ed0`.
- G.17 July data "missing": released 21:15 CST the same day, after both cron
  runs. Timing, not a bug.
- FOMC minutes for the July meeting "missing": published 3 weeks after the
  meeting; the next cron run after release picks it up automatically.

## November 2026 refresh repair

- The broad Investing lane formerly used a different, failing API path from the
  healthy evening rendered-table job. Both now use rendered rows and share the
  browser lock. Check stored dates before treating a broad-job failure as a
  complete loss of commodity updates.
- Manufacturing and Services can legitimately be on different report months
  between their releases. Latest-target selection now uses each survey's verified
  release day at 10:00 New York time. The published calendar currently covers
  2026 and requires the next year's dates before year-end. Survey Synthesis still
  requires matching months; scheduling repair does not change that method rule.
- DOL history and the release PDF now run independently. Inspect both task results
  and both source periods. A history failure remains visible even if the latest
  PDF is successfully imported.

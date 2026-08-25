# Task 8 report

## Scope

Task 8 stages commodity and economic-confirmation refresh work into provider-specific fetch and persistence nodes. CFTC archives remain in `cftc`; cyclical USD/inflation FRED CSVs use `fred_macro` and the shared `fred` resource; EIA credentials remain an explicit fetch failure. DOL, BLS, and Federal Reserve G.17 each have an independent lane and persistence path.

## SHFE preflight and reconciliation concern

Before editing, the main workspace was checked with:

```text
 M app/services/shfe_copper_import.py
 M tests/test_shfe_copper_import.py
```

The exact user-owned diff was:

```diff
-from app.data_sources import shfe_copper
+from app.data_sources import shfe_copper as shfe_copper_source
 from app.db import macro_indicators
-from app.tools import shfe_copper
+from app.tools import shfe_copper as shfe_copper_tools
@@
-    return lambda start_date, end_date: shfe_copper.fetch_shfe_copper_contract_rows(
+    return lambda start_date, end_date: shfe_copper_source.fetch_shfe_copper_contract_rows(
@@
-            main_rows = shfe_copper.build_shfe_cu_main_series(
+            main_rows = shfe_copper_tools.build_shfe_cu_main_series(
@@
-        main_rows = shfe_copper.build_shfe_cu_main_series(
+        main_rows = shfe_copper_tools.build_shfe_cu_main_series(
```

The main test diff adds `test_default_fetcher_uses_shfe_copper_data_source`, which patches the data-source alias and asserts the default fetcher routes there. The isolated branch preserves that behavior and test. The two SHFE paths must be explicitly reconciled during integration; no main-workspace file was reset, staged, or overwritten.

## RED evidence

The new staged-adapter suite initially failed during collection because `app.services.macro_refresh_commodities` did not exist. This established the missing staged adapter contract before production implementation.

## Implemented

- Added `app/services/macro_refresh_commodities.py` with fetch/persist pairs for tracked commodities, CFTC archives, cyclical FRED evidence, EIA oil, SHFE copper, and DCE/Sina iron ore. Persistence consumes staged artifacts only.
- Added provider-specific registry lanes and fetch/import dependencies for `cftc`, `eia`, `shfe`, `dce_sina`, `dol`, `bls`, and `federal_reserve`; cyclical FRED tasks are in `fred_macro` with `fred` on fetch and `sqlite_writer` only on persistence.
- Added persistence helpers to tracked commodities, cyclical commodities, oil, DCE/Sina, and SHFE import services without changing their existing direct entry points.
- Added independent `fetch_dol`/`persist_dol`, `fetch_bls`/`persist_bls`, and `fetch_federal_reserve`/`persist_federal_reserve` seams to the economic-confirmation script. Existing combined CLI behavior remains unchanged.
- Preserved the explicit `EIA_KEY is not set` failure and SHFE alias-routing behavior.

## Verification

- Task 8 focused suite: `71 passed`.
- Refresh plan/executor/resource regressions: `93 passed`.
- Full suite: `4317 passed, 2 failed, 7 warnings`.
- Python syntax checks and `git diff --check` passed.
- Baseline SHFE test run remains the exact preflight failure:
  `tests/test_shfe_copper.py::test_trading_days_clamps_end_to_today`.
  It returns `2026-08-18`, `2026-08-19`, and `2026-08-20` where the test expects only `2026-08-18`; this is unrelated to Task 8 changes and was not modified or concealed.

## Commit

Pending final staging and commit in the isolated worktree.

# Task 7 report

## Scope

Task 7 staged official-source refresh adapters and registered the consumer, Census, NFIB, and FOMC lanes while preserving Tasks 1–6.

## RED evidence

- Added boundary and registry tests before implementing the new service and registry behavior.
- The first focused run failed during collection because `app.services.macro_refresh_official` did not yet exist.
- This established the expected failure for the missing staged adapter module.

## GREEN evidence

- Focused Task 7 suite passed: `104 passed`.
- Follow-up official/Census verification passed: `13 passed`.
- `python3 -m py_compile` passed for all changed Python modules.
- `git diff --check` passed.
- The isolated worktree is clean after the two commits.

## Implemented files

- Created `app/services/macro_refresh_official.py` with staged fetch/persist adapters for Michigan consumer data, consumer FRED series, Census permits, NFIB national/regional data, FOMC documents, and FOMC policy/minutes preparation and persistence.
- Updated `app/services/macro_refresh_registry.py` with `consumer`, `census`, `nfib`, and `fomc` lanes, shared `fred` resource declarations, SQLite writer declarations only on persistence tasks, and the FOMC dependency chain.
- Added staged adapter entry points to `scripts/import_consumer_sentiment.py`, `scripts/import_us_building_permits.py`, `scripts/import_nfib_sbet.py`, `scripts/import_nfib_sbet_regional.py`, and `scripts/fetch_fomc_documents.py`.
- Added FOMC preparation/persistence entry points and an opt-out persistence seam to `scripts/generate_fomc_policy_tone.py` and `scripts/generate_fomc_minutes_structure.py`.
- Reduced routine non-backfill FOMC unavailable-document logging while retaining failures and summaries.
- Added `tests/test_macro_refresh_official.py` and registry coverage in `tests/test_macro_refresh_registry.py`.

## Commits

- `02af346b` — `refactor: stage official source refresh lanes`
- `5c7bdb4f` — `fix: preserve census adapter metadata`

## Concerns

- A separate ad-hoc FOMC preparation smoke command produced no output and was slow outside the required test suites; it was not used as completion evidence. The required FOMC tests and focused Task 7 suites passed.
- The two commits must be applied in order.

## CLI composition review follow-up

The direct `main()` paths now compose the staged adapters sequentially for Census permits, national/regional NFIB, FOMC document fetching, and FOMC policy/minutes extraction. Read connections are closed before network/AI preparation; persistence opens its own database phase afterward. Existing options, summaries, and exit behavior remain supported, including FOMC backfill selection and routine compact skip output.

Follow-up regression coverage in `tests/test_staged_official_cli_order.py` verifies fetch/prepare-before-persist order and connection lifetime for all six CLI families.

Follow-up verification:

- Task 7 plus CLI regression suite: `110 passed`
- FOMC document and CLI lifetime/order subset: `32 passed`
- Python syntax and `git diff --check` passed.

Additional compatibility follow-up:

- `c0519309` — `fix: preserve FOMC CLI failure exits`
- FOMC generation and staged CLI regression subset: `42 passed`.
- Client-construction failures now retain the prior concise stderr and exit-code behavior after the read connection has closed.

FOMC document output follow-up:

- Staged document outcomes now retain structured failure records containing event id, document type, and reason.
- The direct document CLI prints only `document_type`, `fetched`, `unavailable`, and `failed` aggregate fields; raw staged rows and document bodies are never printed.
- Failed documents print `FAIL <event> <type>: <reason>` to stderr; routine unavailable documents remain aggregate-only without per-event skip spam.
- Final Task 7/FOMC CLI verification: `113 passed`.

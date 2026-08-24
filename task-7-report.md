# Task 7 report

Implemented staged official-source adapters and registry entries for consumer sentiment, Census building permits, national and regional NFIB, and FOMC documents/extractions.

- Fetch adapters stage bytes or parsed payloads in the artifact store without opening a writer connection.
- Persistence adapters consume staged artifacts and are the only phase that opens the database for writes.
- Consumer FRED fetches declare the shared `fred` resource; Michigan fetches do not.
- FOMC tasks form the calendar → document fetch/import → tone/minutes extraction/import dependency chain.
- FOMC extraction preparation returns planned `skipped` results when AI is unavailable, and persistence remains separate.
- Routine non-backfill FOMC unavailable-document logs are compact while failures and summaries remain visible.

Verification:

`python3 -m py_compile` passed for all changed Python modules.

`pytest tests/test_macro_refresh_official.py tests/test_import_consumer_sentiment.py tests/test_import_us_building_permits.py tests/test_import_nfib_sbet.py tests/test_nfib_sbet_regional_import.py tests/test_fetch_fomc_documents.py tests/test_generate_fomc_policy_tone.py tests/test_generate_fomc_minutes_structure.py tests/test_macro_refresh_registry.py -q` passed: 104 tests.

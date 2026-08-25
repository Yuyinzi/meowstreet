# Task 9 report

## Status

DONE

## Implementation

- `jobs/refresh_macro_data.py` now accepts injected task providers, artifact storage, executor, and progress factory seams; builds the registry graph and delegates execution to the source-lane executor.
- `app/services/macro_refresh_runtime.py` supplies stage-specific runtime providers for FRED, Yahoo, official, ISM, FOMC, and commodity lanes. Fetch providers write to one shared `ArtifactStore`; persist providers require and consume their matching artifact.
- Established script seams are adapted as explicit fetch/import overrides with valid stage arguments. The old flat execution loop is no longer used by `run()`.
- Added `--serial`, preserved skip/verbose/stop-on-error behavior, and kept `--workers` out of the CLI.
- Added a main-thread progress reporter with one aggregate progress bar, stable active-lane descriptions, lane/task-prefixed replay, deterministic plan-ordered summaries, and `ok`/`skipped`/`failed`/`blocked` counts.
- Successful task internals remain suppressed by default; `--verbose` replays all captured output and failures are replayed with lane/task attribution.
- Cancellation uses the executor admission boundary and reports `macro data refresh interrupted` with exit code 130.
- `main()` selects runtime staged providers while retaining established injectable seams for tests and callers.
- Registry-only legacy seams are normalized into stage-specific providers, including one-shot guards for combined CLIs so a shared command is not repeated for each source node.
- Credit fetch/import nodes now retain separate providers and plan ordering, and all non-TTY lifecycle lines are flushed in order.

## TDD and verification

The new CLI boundary tests initially failed with `TypeError: run() got an unexpected keyword argument 'task_providers'`. After implementation:

```text
pytest tests/test_refresh_macro_data.py tests/test_macro_refresh_executor.py tests/test_macro_refresh_registry.py -q
77 passed
pytest tests/test_refresh_macro_data.py -q
53 passed
```

The production review regression subset passes with `31 passed`, including registry-only legacy seam adaptation, staged artifact handoff, combined-stream lifecycle ordering, credit provider registration, and one-shot combined CLI execution.

The required Python syntax check, `git diff --check`, and CLI help smoke passed. Help includes `--serial`, `--stop-on-error`, and `--verbose`, and does not include `--workers`.

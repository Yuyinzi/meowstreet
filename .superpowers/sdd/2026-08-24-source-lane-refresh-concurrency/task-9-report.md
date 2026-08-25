# Task 9 report

## Reviewer rescue

- EIA oil fetches now load `EIA_KEY` from the application environment before building providers; no empty credential is supplied to the commodity adapter.
- Configured OpenAI settings now construct real clients through `app.llm`: ISM enrichment stages a prepared result, and FOMC policy-tone/minutes enrichment stages per-event results before writer-gated promotion. Missing keys remain planned skips.
- Legacy combined injected CLIs now use a no-op artifact fetch stage and execute only in their registry persistence node. Separable legacy CLIs retain true fetch/import adapters.
- The refresh CLI suite now asserts registry/executor result behavior rather than the retired flat loop, while retaining public injection seams, flags, status summaries, and skip behavior.

## Verification

```text
pytest tests/test_refresh_macro_data.py tests/test_macro_refresh_registry.py tests/test_macro_refresh_executor.py tests/test_macro_refresh_resources.py tests/test_macro_refresh_plan.py tests/test_macro_refresh_output.py tests/test_macro_refresh_runtime.py tests/test_macro_refresh_ism.py tests/test_ism_ai_enrichment.py tests/test_fomc_policy_tone_tool.py tests/test_fomc_minutes_structure_tool.py tests/test_oil.py tests/test_oil_import.py -q
174 passed
```

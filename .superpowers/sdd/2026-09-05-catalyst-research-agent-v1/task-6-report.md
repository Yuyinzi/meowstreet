# Task 6 report — adapter validation and generation

## RED / GREEN

- RED: `.venv/bin/pytest tests/agents/catalyst_research/test_adapter_validator.py tests/agents/catalyst_research/test_adapter_generator.py -q` failed during collection because `validator.py` and `generator.py` were missing (`2 ModuleNotFoundError` errors).
- GREEN: the same focused command passes (`5 passed`).

## Implementation

- Added deterministic candidate validation with two byte-equivalent bounded-snapshot executions followed by one bounded live execution.
- Added sanitized validation reports with validator/executor versions, source/page hashes, match counts, date formats, pagination, safety, duplicate, repeatability, and limit evidence.
- Added fail-closed active-adapter drift validation (`stale`) with no promotable observations on structural or fetch failure.
- Added bounded `responses.parse` adapter generation using `IRSourceAdapter`, trusted workflow identity-field replacement, prompt/schema/model provenance, and deterministic input/output hashes.
- Generator performs no execution or persistence; activation remains owned by the persistence layer.
- Added excluded-region drift fixture and adapter package exports.

## Verification

- `.venv/bin/pytest tests/agents/catalyst_research/test_adapter_validator.py tests/agents/catalyst_research/test_adapter_generator.py -q` — 5 passed
- `.venv/bin/pytest tests/agents/catalyst_research -q` — 169 passed
- `python3 -m py_compile app/agents/catalyst_research/adapters/validator.py app/agents/catalyst_research/adapters/generator.py` — passed
- `git diff --check` — passed

## Reviewer fix round 2

- RED: added precise tests for validator-owned response-byte upper/lower bounds and evidence, invalid snapshot hash handling, paginated duplicate/out-of-window observations, and a non-artificial page-parameter success path.
- GREEN: focused adapter validator/generator suite passes (`29 passed`); Catalyst agent suite passes (`193 passed`).
- Validator now records `max_response_bytes`, observed response sizes, and both response/overall bound status for snapshot and live pages. Actual HTML size and the explicit 2 MB response ceiling are enforced.
- Failed snapshot validation computes the structural HTML hash first; an invalid supplied hash is never echoed into `source_content_hashes` or reports.
- Pagination with more than one fetched page must produce an in-window observation distinct from the prior page; duplicate and all-out-of-window pages fail closed while one-page archive exhaustion remains valid.
- Generator provenance test now asserts the exact SHA-256 of the bounded structural snapshot, not a format-only/non-invalid assertion.

### Round 2 verification

- `.venv/bin/pytest tests/agents/catalyst_research/test_adapter_validator.py tests/agents/catalyst_research/test_adapter_generator.py -q` — 29 passed
- `.venv/bin/pytest tests/agents/catalyst_research -q` — 193 passed
- `python3 -m py_compile app/agents/catalyst_research/adapters/validator.py app/agents/catalyst_research/adapters/generator.py` — passed
- `git diff --check` — passed

## Commit

`feat: validate and generate ir adapters`

## Risks

- Validation intentionally operates on bounded structural HTML; a source that requires JavaScript/AJAX remains unsupported by the v1 adapter contract.
- Active drift validation reports stale and withholds observations, but atomic state transitions and dataset preservation are deliberately left to Task 2 persistence/workflow callers.
- Pagination and archive coverage remain bounded by the Task 5 executor limits; limit exhaustion is reported as validation failure for candidate activation.

## Reviewer fix round 1

- RED: expanded validator/generator contracts initially produced 18 failures, covering pagination loops/distinctness, mirrored report errors, unexpected fetch exceptions, snapshot metadata, and aggregate prompt bounds.
- GREEN: focused validator/generator suite now passes (`25 passed`); Catalyst agent suite passes (`189 passed`).
- Candidate and active validation now fail closed on repeated URL/content loops, missing distinct pagination observations, truncation, executor limits, malformed fields, unsafe redirects/URLs, and oversized pages. Candidate errors are mirrored into `report.errors`; active reports retain loop/page evidence while returning `stale`.
- Snapshot requested/final URLs, redirect chain, content type, response size, truncation, host allowlist, and content hash are checked before repeatability execution. Normal fetch exceptions are sanitized and returned; `KeyboardInterrupt`/`SystemExit` are not swallowed.
- Generator now filters company/source fields, bounds normalized headings/links and aggregate prompt size, preserves bounded structural evidence, and recomputes invalid/mismatched snapshot hashes from bounded content. Hashes remain stable for identical bounded inputs.

### Round 1 verification

- `.venv/bin/pytest tests/agents/catalyst_research/test_adapter_validator.py tests/agents/catalyst_research/test_adapter_generator.py -q` — 25 passed
- `.venv/bin/pytest tests/agents/catalyst_research -q` — 189 passed
- `python3 -m py_compile app/agents/catalyst_research/adapters/validator.py app/agents/catalyst_research/adapters/generator.py` — passed
- `git diff --check` — passed

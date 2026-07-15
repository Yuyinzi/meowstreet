# Meowstreet

Local-first method-based trade workflow system.

Meowstreet evaluates a ticker through a method-derived workflow graph. It is separate from Serenity Dashboard and does not use trader tweets, trader chat, X ingestion, or trader-specific RAG.

## Run

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/build_method.py
.venv/bin/uvicorn app.api:app --reload --port 8797
```

Open:

```text
http://127.0.0.1:8797
```

## Test

```bash
.venv/bin/pytest -q
```

## Macro Dashboard Data

### FOMC calendar, statements, and tone

The FOMC dashboard data is DB-backed. Import the calendar first, fetch statement documents second, then generate policy tone from the stored statement text.

Import FOMC meetings from the local CSV:

```bash
.venv/bin/python scripts/import_fomc_calendar.py
```

By default this reads:

```text
data/source_material/Video 06/fomc_calendar.csv
```

Override the CSV path when needed:

```bash
.venv/bin/python scripts/import_fomc_calendar.py \
  --calendar-path "data/source_material/Video 06/fomc_calendar.csv"
```

Fetch statement documents for all imported FOMC events:

```bash
.venv/bin/python scripts/fetch_fomc_documents.py
```

Generate tone for one statement:

```bash
.venv/bin/python scripts/generate_fomc_policy_tone.py \
  --event-id fomc_2026_06_16 \
  --max-rounds 3
```

Generate tone for all fetched statements:

```bash
.venv/bin/python scripts/generate_fomc_policy_tone.py \
  --all \
  --max-rounds 3
```

The generator loads `.env` through `app.llm`. Configure the model and API credentials there, for example:

```text
OPENAI_API_KEY=...
OPENAI_BASE_URL=...
OPENAI_MODEL=...
```

Use optional per-task model overrides only when needed:

```text
FOMC_TONE_EXTRACTOR_MODEL=...
FOMC_TONE_REVIEWER_MODEL=...
```

Existing tone rows are skipped when the stored statement `source_hash` already has an extraction. Regenerate existing rows with:

```bash
.venv/bin/python scripts/generate_fomc_policy_tone.py \
  --all \
  --max-rounds 3 \
  --force
```

Typical full refresh sequence:

```bash
.venv/bin/python scripts/import_fomc_calendar.py
.venv/bin/python scripts/fetch_fomc_documents.py --document-type all
.venv/bin/python scripts/generate_fomc_policy_tone.py --all --max-rounds 3
.venv/bin/python scripts/generate_fomc_minutes_structure.py --all --max-rounds 3
```

Tone extraction stores both the detailed interpretation and the simplified chart marker:

- `policy_action`: mechanical decision, such as `hold`, `hike`, or `cut`
- `guidance_bias`: explicit forward guidance
- `language_tone`: statement wording tone
- `overall_bias`: trader-style combined bias
- `marker_tone`: simplified dashboard marker, such as `hawkish`, `dovish`, or `neutral`

### Minutes structure extraction

Minutes analysis does not replace statement tone. The statement remains the public baseline. Minutes add structure fields:

- `minutes_confirmation`
- `risk_focus`
- `divergence_level`
- `uncertainty_level`
- `policy_conviction`

### ISM official report import

Import historical ISM Manufacturing PMI reports from PRNewswire and ISM:

```bash
.venv/bin/python scripts/fetch_ism_official_reports.py --backfill-since 2025
```

Use `--missing-only` to skip already-imported report months:

```bash
.venv/bin/python scripts/fetch_ism_official_reports.py --backfill-since 2025 --missing-only --report-concurrency 2
```

Use `--report-concurrency 2` for faster historical backfills. Each report still runs section-level extraction internally, so avoid high report concurrency unless the LLM provider and SQLite workload have been validated.

## GDP Relationship Workbook Caveat

- `data/source_material/Video 03/GDP_Correlations.xlsx` is the source of truth for the current GDP relationship dashboard import.
- Recomputed lag metrics match the workbook for all configured relationships when the same raw quarter rows are used.
- Recomputed quad metrics match the workbook for US and Europe.
- The China quad workbook sheet `SZSC_CN_Quadnomial` is internally inconsistent with the China correlation sheet. Its GDP level series matches the Europe quad GDP series rather than the China correlation-sheet GDP values.
- Until that source data issue is resolved, do not treat China quad recomputation as a supported parity target. Skip China quad-derived recomputation work and keep China workbook quad rows as imported source data if display parity is required.

## Extract Method Method JSON

Generate reviewable prompts only:

```bash
.venv/bin/python scripts/extract_method.py --write-prompts-only
```

Run extraction with the OpenAI client:

```bash
OPENAI_API_KEY=... .venv/bin/python scripts/extract_method.py
```

Useful options:

```bash
.venv/bin/python scripts/extract_method.py \
  --model gpt-4.1-mini \
  --max-output-tokens 12000 \
  --max-retries 4 \
  --workers 3 \
  --skip-existing \
  --log-level INFO
```

The extractor loads `.env` with `python-dotenv` and uses the async OpenAI client with bounded concurrency from `--workers`. Use `--skip-existing` to resume an interrupted extraction without reprocessing JSON files that already exist. Completed extractions are written with a temporary file and atomic replace. The script logs each prompt, extraction attempt, retry, skip, and output file. If the model stops with `finish_reason=length`, the script does not retry; increase `--max-output-tokens` or narrow the input before rerunning.

By default, prompts go to `data/local_system/extraction_prompts/` and validated JSON results go to `data/local_system/extraction_results/`. Override them with:

```bash
.venv/bin/python scripts/extract_method.py \
  --prompts-dir data/local_system/extraction_prompts \
  --results-dir data/local_system/extraction_results
```

The older `--output-dir` option still works as a compatibility alias when you want prompts and results in the same directory.

### Refine extracted method methods

The baseline extractor writes broad per-note JSON to `data/local_system/extraction_results`. Run the refinement stage when you want an additional LLM pass focused on missing indicators, formulas, thresholds, checks, required inputs, and dashboard metrics:

```bash
.venv/bin/python scripts/refine_method_extraction.py \
  --input-dir data/local_system/extraction_results \
  --output-dir data/local_system/extraction_refined \
  --max-audit-repair-rounds 2
```

Refinement is additive. It reads the original note plus the existing extraction, asks for patch-only additions, runs semantic audit/repair rounds, rejects duplicate item IDs by default, and writes final refined JSON to `data/local_system/extraction_refined`.

Use refined output for synthesis after review:

```bash
.venv/bin/python scripts/synthesize_method.py \
  --extractions-dir data/local_system/extraction_refined \
  --omit-empty-seed-nodes
```

Prompts and repair logs are written to:

```text
data/local_system/refinement_prompts
data/local_system/refinement_repairs
data/local_system/refinement_audits
```

## Synthesize Method Method JSON

After extraction, synthesize the final method method artifact:

```bash
.venv/bin/python scripts/synthesize_method.py
```

By default, synthesis reads per-note JSON from `data/local_system/extraction_results/` and writes final artifacts to `data/local_system/synthesis/`:

```text
data/local_system/synthesis/method.v1.json
data/local_system/synthesis/method_review.md
```

Override the locations when needed:

```bash
.venv/bin/python scripts/synthesize_method.py \
  --extractions-dir data/local_system/extraction_results \
  --output data/local_system/synthesis/method.v1.json \
  --review-output data/local_system/synthesis/method_review.md
```

You can also keep using a provider-agnostic command that reads the prompt from stdin and writes strict JSON to stdout:

```bash
.venv/bin/python scripts/extract_method.py \
  --llm-command 'your-llm-command'
```

### Synthesis taxonomy

Synthesis is a two-stage loop:

1. **Deterministic synthesis** routes items by code aliases into canonical workflow nodes.
2. **LLM routing audit** reviews the draft node assignments and applies schema-validated routing moves.

Run:

```bash
.venv/bin/python scripts/synthesize_method.py \
  --extractions-dir data/local_system/extraction_refined \
  --omit-empty-seed-nodes \
  --max-routing-audit-rounds 2
```

This writes final artifacts to:

- `data/local_system/synthesis/method.v1.json`
- `data/local_system/synthesis/method_review.md`

Routing audit artifacts are written to:

- `data/local_system/synthesis_routing_audits/`

To inspect routing audit prompts without calling the LLM:

```bash
.venv/bin/python scripts/synthesize_method.py \
  --extractions-dir data/local_system/extraction_refined \
  --omit-empty-seed-nodes \
  --write-routing-prompts-only
```

The LLM does not directly create final workflow nodes during synthesis. Its `proposed_nodes` and `dependencies` are treated as evidence. The final node IDs, node templates, default graph edges, and routing audit moves are controlled by `app/method_synthesizer.py`.

Review `data/local_system/synthesis/method_review.md` after synthesis. The report lists proposed-node mappings, fallback decision areas, dependency edge suggestions, and routing audit moves so taxonomy gaps can be fixed explicitly.

Use `--omit-empty-seed-nodes` when you want the synthesized graph to include only nodes with extracted method content. Without this flag, synthesis preserves seed workflow nodes from the base method method for compatibility.

After changing taxonomy aliases, regenerate synthesis and inspect suspicious nodes directly:

```bash
.venv/bin/python scripts/synthesize_method.py --omit-empty-seed-nodes
python3 -c 'import json, pathlib; payload=json.loads(pathlib.Path("data/local_system/synthesis/method.v1.json").read_text()); [print(node["id"], len(node.get("indicators", [])), len(node.get("sub_methods", []))) for node in payload["workflow_nodes"]]'
```

Check `catalyst_window`, `trade_risk_management`, and `fundamental_quantitative_bias` after alias changes because broad words such as `measurement`, `target`, and `process` can misroute unrelated methods.

## Data Directory Layout

```
data/local_system/
├── method.v1.json          # Runtime artifact (loaded by api.py)
├── extraction_prompts/            # Baseline LLM extraction prompts
├── extraction_results/            # Baseline extraction JSON per note
├── extraction_refined/            # Refined extraction JSON per note
├── refinement_prompts/            # Refinement prompt files
├── refinement_repairs/            # Initial patches + per-round repair JSON
│   ├── *.indicator.patch.json     #   Initial refinement patches
│   └── *.repair_round_*.json      #   Per-round repair output
├── refinement_audits/             # Audit findings + final reports
│   ├── *.audit_round_*.json       #   Per-round audit results
│   └── *.audit.md                 #   Final audit reports
├── synthesis_routing_audits/         # Routing audit prompts and patches
└── synthesis/                     # Final synthesized artifacts
    ├── method.v1.json      #   Full workflow graph
    └── method_review.md    #   Review report
```

**Pipeline flow:**

```
method_notes/*.md
  → extract_method.py → extraction_results/              (baseline)
  → refine_method_extraction.py → extraction_refined/           (refinement)
  → synthesize_method.py → synthesis/method.v1.json  (final)
```

`method.v1.json` at the root of `data/local_system/` is the server's runtime artifact — keep it in sync with `synthesis/method.v1.json` after synthesis.

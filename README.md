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

`scripts/synthesize_method.py` is deterministic. It reads LLM extraction results from `data/local_system/extraction_results`, maps extracted items and `proposed_nodes` into a compact canonical workflow graph, and writes synthesized artifacts to `data/local_system/synthesis`.

The LLM does not directly create final workflow nodes during synthesis. Its `proposed_nodes` and `dependencies` are treated as evidence. The final node IDs, node templates, and default graph edges are controlled by `app/method_synthesizer.py`.

Review `data/local_system/synthesis/method_review.md` after synthesis. The report lists proposed-node mappings, fallback decision areas, and dependency edge suggestions so taxonomy gaps can be fixed explicitly.

Use `--omit-empty-seed-nodes` when you want the synthesized graph to include only nodes with extracted method content. Without this flag, synthesis preserves seed workflow nodes from the base method method for compatibility.

After changing taxonomy aliases, regenerate synthesis and inspect suspicious nodes directly:

```bash
.venv/bin/python scripts/synthesize_method.py --omit-empty-seed-nodes
python3 -c 'import json, pathlib; payload=json.loads(pathlib.Path("data/local_system/synthesis/method.v1.json").read_text()); [print(node["id"], len(node.get("indicators", [])), len(node.get("sub_methods", []))) for node in payload["workflow_nodes"]]'
```

Check `catalyst_window`, `trade_risk_management`, and `fundamental_quantitative_bias` after alias changes because broad words such as `measurement`, `target`, and `process` can misroute unrelated methods.

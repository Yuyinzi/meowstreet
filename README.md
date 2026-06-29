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

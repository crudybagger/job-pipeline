# Job Pipeline

A modular job-search pipeline built with **Python** and **FastAPI**. Product blueprint:
`../plan.md`; design docs in `../docs/design/`.

**Stage 1 — Job Scraping and Filtering is implemented, tested, and validated against real
web data.** Stages 2–4 (resume generation, cover letters, delivery) are designed and
pending implementation. See `../docs/stage1-context-and-usage.md` for the full context and
usage guide.

## Architecture

```
Ingestion → Parsing → Matching → Queues (accepted/rejected/new)
                                     ↓
              Stage 2: tailored resume + ATS loop   (pending)
              Stage 3: matching cover letter        (pending)
              Stage 4: delivery + sent tracking     (pending)
```

Stage 1 packages under `src/`:

- **Ingestion** (`src/ingestion/ingest.py`) – per-source fetchers for Remotive, RemoteOK,
  Arbeitnow and the Bundesagentur für Arbeit Jobsuche API, plus an `html-stub` plugin seam
  (RWTH Aachen HiWi board later).
- **Parsing** (`src/parsing/parse.py`) – normalizes each board's payload into a validated
  `JobEntry` (title, description, company, website, contact, location, tags, metadata).
- **Matching** (`src/matching/match.py`) – deterministic, config-weighted score
  (experience / prospects / education) with a hard location gate (remote OR
  Aachen/Köln-area).
- **Queues** (`src/queues/store.py`, `src/queues/cli.py`) – SQLite store with
  transition-map enforcement plus the interactive CLI.
- **Orchestrator** (`src/stage1.py`) – the fetch → parse → score → queue flow shared by
  the API and the CLI.

## Quick Start

```bash
# Create a virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure: copy the example and adjust sources/keywords/threshold
# (config/pipeline.json is the real, gitignored config)
cp config/pipeline.example.json config/pipeline.json

# Run the API
uvicorn app.main:app --reload
```

## Using Stage 1

```bash
# Batch ingest from all enabled sources (persist to data/queues.db)
python -m src.queues.cli run                      # or: POST /stage1/run
python -m src.queues.cli run --source arbeitnow --limit 50 --dry-run

# Review the queues
python -m src.queues.cli status                   # queue counts (or GET /status)
python -m src.queues.cli view new                 # awaiting your review (GET /jobs?status=new)
python -m src.queues.cli view-accepted
python -m src.queues.cli show <id>                # full entry (GET /jobs/{id})
python -m src.queues.cli accept <id>              # or POST /jobs/{id}/accept
python -m src.queues.cli reject <id>
python -m src.queues.cli note <id> <text>         # human note on the entry
python -m src.queues.cli edit <id> location=Remote  # whitelist edit (PATCH /jobs/{id})
```

The FastAPI app mirrors everything (thin admin UI at `GET /ui`); all transitions are
manually triggered — no schedulers anywhere.

## Validation and tuning

```bash
pytest -q                                   # 84 tests, no live network
python scripts/stage1_live.py [--dry-run]   # real-web-data isolation check (manual)
python scripts/analyze_rejected.py          # factor breakdowns for score re-tuning
```

Re-tune `config/pipeline.json` (threshold, weights, keywords) after reviewing the
rejected list, per `plan.md`.

## Documentation

- `../docs/stage1-context-and-usage.md` – Stage 1 context and usage (this stage)
- `../docs/design/stage1-lld.md` – Stage 1 low-level design
- `../docs/design/stage1-job-scraping-and-filtering.md` – Stage 1 HLD
- `../docs/design/pipeline-integration.md` – cross-stage contract
- `../plan.md` – product blueprint (all 4 stages)

## Running Tests

```bash
pytest -q
```

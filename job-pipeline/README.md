# Job Pipeline

A modular job-search pipeline built with **Python** and **FastAPI**. Product blueprint:
`../plan.md`; design docs in `../docs/design/`.

**Stage 1 — Job Scraping and Filtering is implemented, tested, and validated against real
web data. Stage 2 — Matching Resume Generation (plus the shared `src/llm/` provider) is
implemented and tested; real runs need `LLM_API_KEY` in `.env`.** Stages 3–4 (cover
letters, delivery) are designed and pending implementation. See
`../docs/stage1-context-and-usage.md` for Stage 1's full context and usage guide.

## Architecture

```
Ingestion → Parsing → Matching → Queues (accepted/rejected/new)
                                     ↓
              Stage 2: tailored resume + ATS loop   (done — resume_ready queue)
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

Stage 2 packages under `src/`:

- **LLM provider** (`src/llm/provider.py`) – shared OpenAI-compatible
  chat-completions client over httpx: JSON mode, retries/backoff, `LLMError` on
  unconfigured/exhausted calls; mockable `set_client()` seam (no live network in tests).
- **Resume generation** (`src/resume/generate.py`) – section-targeted LaTeX editing:
  configurable `rSection`/`tableEnv` markers (auto-detect fallback), programmatic edit
  application with difflib span validation; artifacts at `data/resumes/<job_id>.tex`.
- **ATS scoring** (`src/resume/ats.py`) – LLM screener/hiring-manager persona plus a
  deterministic bucketed keyword scorer, combined 0.7·LLM + 0.3·deterministic.
- **Loop** (`src/resume/loop.py`) – generate → score → feedback round-trip via
  `metadata.ats`; advances `accepted → resume_ready` only when the combined score meets
  `stage2.ats_ready_threshold`; cap → `needs_review` (human promotes via `resume-force-ready`).
- **Orchestrator** (`src/resume/stage2.py`) – `run_stage2` batch/single-job flow (dry-run,
  per-entry error isolation), `run_ats_substage`, `force_ready`.

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

## Using Stage 2

```bash
# Tailored resumes for accepted entries (ATS loop to threshold or cap)
python -m src.queues.cli resume-generate <id>             # or: POST /jobs/{id}/resume/generate
python -m src.queues.cli resume-generate <id> --single    # one generate+score iteration
python -m src.queues.cli resume-run [--limit N] [--dry-run] [--single]  # or: POST /stage2/run

# ATS-only scoring of the current artifact (or the base resume)
python -m src.queues.cli resume-ats <id>                  # or: POST /jobs/{id}/resume/ats

# Human promotion of a capped (needs_review) entry
python -m src.queues.cli resume-force-ready <id>          # or: POST /jobs/{id}/resume/force-ready
```

Config knobs: `stage2.ats_ready_threshold`, `stage2.max_iterations`,
`stage2.latex_section_markers` in `config/pipeline.json`; `LLM_API_KEY` (+ optional
`LLM_BASE_URL`/`LLM_MODEL`) in `.env` for real LLM calls. Tailored artifacts land at
`data/resumes/<job_id>.tex`; iteration history in `metadata.ats` (visible via
`show <id>` / `GET /jobs/{id}`).

## Validation and tuning

```bash
pytest -q                                   # 155 tests, no live network
python scripts/stage1_live.py [--dry-run]   # real-web-data isolation check (manual)
python scripts/stage2_live.py [--dry-run]   # real-LLM Stage-2 check (manual; needs LLM_API_KEY)
python scripts/analyze_rejected.py          # factor breakdowns for score re-tuning
```

Re-tune `config/pipeline.json` (threshold, weights, keywords) after reviewing the
rejected list, per `plan.md`.

## Documentation

- `../docs/stage1-context-and-usage.md` – Stage 1 context and usage (this stage)
- `../docs/design/stage1-lld.md` – Stage 1 low-level design
- `../docs/design/stage1-job-scraping-and-filtering.md` – Stage 1 HLD
- `../docs/design/stage2-lld.md` – Stage 2 low-level design
- `../docs/design/stage2-resume-generation.md` – Stage 2 HLD
- `../docs/design/pipeline-integration.md` – cross-stage contract
- `../plan.md` – product blueprint (all 4 stages)

## Running Tests

```bash
pytest -q
```

# Job Pipeline

This repository is initialized from the product plan in
`./plan.md`.

The goal is a 4-stage pipeline that discovers jobs, prepares tailored application
material, and sends a review-ready package to the candidate.

## Pipeline summary (from `plan.md`)

1. **Stage 1 — Job Scraping and Filtering**
   - Collect postings from job boards using configurable keywords.
   - Score each job for fit and route into accepted/rejected queues.
   - Persist jobs with metadata (including base resume path and notes).
2. **Stage 2 — Matching Resume Generation**
   - Adapt a base LaTeX resume to each accepted job description.
   - Run an ATS-like feedback loop until the resume is marked ready.
3. **Stage 3 — Matching Cover Letter Generation**
   - Generate a company/job-specific cover letter from resume + job context.
   - Follow a repeatable narrative structure with configurable context inputs.
4. **Stage 4 — Candidate Delivery Package**
   - Compile job link, description, resume, and cover letter into one message.
   - Send via external messaging platform and track sent/applied states.

## Configuration and running each stage

> **Current state:** Stages 1 and 2 are implemented and tested (155 tests, no
> live network in CI). Stage 1 is validated against real web data; Stage 2 real
> (non-test) runs need `LLM_API_KEY` in `./job-pipeline/.env`. The Stage 3–4
> sections document how each stage is intended to be configured/run.

### Shared setup

```bash
cd ./job-pipeline
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Stage 1 — Job Scraping and Filtering

- **Configure:** `./job-pipeline/config/pipeline.json` (real config, gitignored;
  `config/pipeline.example.json` documents the shape): job board sources
  (Remotive, RemoteOK, Arbeitnow, Bundesagentur für Arbeit — plus an HTML-stub
  seam for the RWTH Aachen HiWi board), EN+DE search keywords, match-score
  weights/threshold, role/location keywords, and the candidate profile.
- **Run targets:**
  - FastAPI: `POST /ingest` (one source), `POST /stage1/run` (all enabled
    sources), `GET /status`, `GET /jobs?status=`, `GET /jobs/{id}`,
    `POST /jobs/{id}/accept|reject|note`, `PATCH /jobs/{id}`, `GET /ui`.

    ```bash
    cd ./job-pipeline
    uvicorn app.main:app --reload
    # then call POST /ingest with {"source": "remotive"}
    ```
  - CLI (from `./job-pipeline`): `python -m src.queues.cli status | view new |
    view-accepted | show <id> | accept <id> | reject <id> | note <id> <text> |
    edit <id> field=value | run [--source NAME] [--limit N] [--dry-run]`
  - Live isolation check with real web data (manual, not part of `pytest`):
    `python scripts/stage1_live.py [--dry-run]`; re-tune the score via
    `python scripts/analyze_rejected.py` (see `docs/design/stage1-lld.md`).
- **LLD:** `./docs/design/stage1-lld.md`; context & usage guide:
  `./docs/stage1-context-and-usage.md`; cross-stage contract:
  `./docs/design/pipeline-integration.md`.

### Stage 2 — Matching Resume Generation (implemented)

- **Implemented:** `./job-pipeline/src/resume/` — `generate.py` (section-targeted
  LaTeX editing with difflib span validation), `ats.py` (LLM + deterministic ATS
  scoring, combined 0.7/0.3), `loop.py` (feedback round-trip loop), `stage2.py`
  (orchestrator) — on the shared `src/llm/` OpenAI-compatible provider.
- **Configure:** `./job-pipeline/config/pipeline.json` — `stage2.ats_ready_threshold`,
  `stage2.max_iterations`, `stage2.latex_section_markers` (set for the real
  `data/Resume.tex`); `LLM_API_KEY` (+ optional `LLM_BASE_URL`, `LLM_MODEL`) in `.env`.
- **Run targets:**
  - FastAPI: `POST /stage2/run?limit=&dry_run=`,
    `POST /jobs/{id}/resume/generate?run_to_completion=`,
    `POST /jobs/{id}/resume/ats`, `POST /jobs/{id}/resume/force-ready`;
    `GET /status` reports stage2 `implemented`/`eligible`/`pending_review`.
  - CLI (from `./job-pipeline`): `python -m src.queues.cli resume-generate <id>
    [--single] | resume-ats <id> | resume-force-ready <id> | resume-run
    [--limit N] [--dry-run] [--single]`.
  - Live check with real LLM calls (manual, not part of `pytest`):
    `python scripts/stage2_live.py [--dry-run] [--job-id <id>] [--single]`
    (requires `LLM_API_KEY` in `.env`).
  - Artifacts: `data/resumes/<job_id>.tex`; iteration history round-trips via
    `metadata.ats`/`metadata.resume` (visible on `GET /jobs/{id}`).
- **LLD:** `./docs/design/stage2-lld.md`; HLD:
  `./docs/design/stage2-resume-generation.md`.

### Stage 3 — Matching Cover Letter Generation

- **Configure:** story-building context, company-research sources, and output
  format constraints per job board/company.
- **Run target:** implement under
  `./job-pipeline/src/` with a
  dedicated module/entrypoint that consumes Stage 2-ready jobs.

### Stage 4 — Candidate Delivery Package

- **Configure:** messaging provider (e.g., WhatsApp/Telegram/Signal), delivery
  channel credentials, and sent/applied status tracking fields.
- **Run target:** implement a dispatch module in
  `./job-pipeline/src/` that packages
  Stage 3 output and updates tracking state after send.

## Repository context

- `./plan.md`
  - Product blueprint for all 4 stages and expected behavior.
- `./job-pipeline/`
  - Main Python project (FastAPI app, source modules, tests, and requirements).
- `./automation/`
  - Namespace wrapper so automation modules are importable from repository root.
- `./job-pipeline/automation/`
  - Local issue-tracker automation (`issues.md` processing loop).
- `./scripts/`
  - Utility scripts for repository bootstrap tasks.

## Development checks

Run existing tests from the Python project directory:

```bash
cd ./job-pipeline
pytest -q
```

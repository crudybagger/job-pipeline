# Job Pipeline

This repository is initialized from the product plan in
`/home/runner/work/job-pipeline/job-pipeline/plan.md`.

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

> **Current state:** this repository currently contains scaffolding,
> placeholders, and automation utilities. The sections below document how each
> stage is intended to be configured/run and where to integrate implementation.

### Shared setup

```bash
cd /home/runner/work/job-pipeline/job-pipeline/job-pipeline
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Stage 1 — Job Scraping and Filtering

- **Configure:** job board sources, search keywords, and match-score threshold.
- **Run target:** ingestion endpoint in
  `/home/runner/work/job-pipeline/job-pipeline/job-pipeline/app/main.py`.

```bash
cd /home/runner/work/job-pipeline/job-pipeline/job-pipeline
uvicorn app.main:app --reload
# then call POST /ingest with source_url
```

### Stage 2 — Matching Resume Generation

- **Configure:** base resume path, keyword/experience weighting, ATS acceptance
  threshold, and retry loop limits.
- **Run target:** implement stage logic under
  `/home/runner/work/job-pipeline/job-pipeline/job-pipeline/src/` and expose an
  entrypoint (API route, CLI, or worker) consistent with Stage 1 patterns.

### Stage 3 — Matching Cover Letter Generation

- **Configure:** story-building context, company-research sources, and output
  format constraints per job board/company.
- **Run target:** implement under
  `/home/runner/work/job-pipeline/job-pipeline/job-pipeline/src/` with a
  dedicated module/entrypoint that consumes Stage 2-ready jobs.

### Stage 4 — Candidate Delivery Package

- **Configure:** messaging provider (e.g., WhatsApp/Telegram/Signal), delivery
  channel credentials, and sent/applied status tracking fields.
- **Run target:** implement a dispatch module in
  `/home/runner/work/job-pipeline/job-pipeline/job-pipeline/src/` that packages
  Stage 3 output and updates tracking state after send.

## Repository context

- `/home/runner/work/job-pipeline/job-pipeline/plan.md`
  - Product blueprint for all 4 stages and expected behavior.
- `/home/runner/work/job-pipeline/job-pipeline/job-pipeline/`
  - Main Python project (FastAPI app, source modules, tests, and requirements).
- `/home/runner/work/job-pipeline/job-pipeline/automation/`
  - Namespace wrapper so automation modules are importable from repository root.
- `/home/runner/work/job-pipeline/job-pipeline/job-pipeline/automation/`
  - Local issue-tracker automation (`issues.md` processing loop).
- `/home/runner/work/job-pipeline/job-pipeline/scripts/`
  - Utility scripts for repository bootstrap tasks.

## Development checks

Run existing tests from the Python project directory:

```bash
cd /home/runner/work/job-pipeline/job-pipeline/job-pipeline
pytest -q
```

# Technical Context

## Overview
Technologies, development setup, constraints, and dependencies for the job-pipeline repository.

## Technologies
- **Language**: Python 3.12 (CI pins `3.12`; `.venv` is CPython 3.12)
- **Web framework**: FastAPI + uvicorn[standard]
- **HTTP client**: httpx
- **Data/validation**: pydantic, pandas
- **Config**: python-dotenv
- **Testing**: pytest, pytest-asyncio
- **LLM**: OpenAI-compatible HTTP chat-completions via httpx (shared `src/llm/` abstraction; no SDK dependency)
- **CI**: GitHub Actions (`.github/workflows/ci.yml`) — install deps + `pytest -q` on push/PR to `main`
- **VCS**: Git (remote `origin`, branch `main`)

## Development Setup
```bash
cd /e/jobs/job-pipeline
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Common Commands
- Run API: `uvicorn app.main:app --reload` (from `job-pipeline/`); unified surface: `POST /ingest` `{"source": "remotive"}`, `POST /stage1/run?limit=&dry_run=`, `GET /status`, `GET /jobs?status=`, `GET /jobs/{id}`, `POST /jobs/{id}/accept|reject|note`, `PATCH /jobs/{id}`, `GET /ui`
- Run tests: `pytest -q` (from `job-pipeline/`) — currently **115 passed** via `.venv/bin/python -m pytest -q`
- Stage 1 CLI: `python -m src.queues.cli status | view <status> | view-accepted | view-rejected | show <id> | accept <id> | reject <id> | note <id> <text> | edit <id> field=value | run [--source NAME] [--limit N] [--dry-run]`
- Live isolation check (manual, real web data): `python scripts/stage1_live.py [--dry-run]`; rejected-list analysis for re-tuning: `python scripts/analyze_rejected.py`
- Issue automation loop: `python -m automation.run_issue_loop` (processes `issues.md` every 600s; commits+pushes if `.git` present)
- Stage 2 API: `POST /stage2/run?limit=&dry_run=`, `POST /jobs/{id}/resume/generate?run_to_completion=`, `POST /jobs/{id}/resume/ats`, `POST /jobs/{id}/resume/force-ready`; `GET /status` includes stage2 implemented/eligible/pending_review
- Stage 2 CLI: `python -m src.queues.cli resume-generate <id> [--single] | resume-ats <id> | resume-force-ready <id> | resume-run [--limit N] [--dry-run] [--single]`
- Stage 2 LLD: `docs/design/stage2-lld.md`; Stage 2 config knobs: `stage2.{ats_ready_threshold, max_iterations, latex_section_markers}` in `config/pipeline.json`

## Project Structure Constraints
- All Python code lives under `job-pipeline/`; run tests/uvicorn from that directory so `src.*` imports resolve.
- `automation` at repo root is a namespace wrapper forwarding to `job-pipeline/automation` (needed when running from `/e/jobs`).
- No lockfile; dependencies are unpinned in `requirements.txt`.
- Config lives at `job-pipeline/config/pipeline.json` (real, gitignored) with `pipeline.example.json` documenting the shape; `.env` overrides for secrets (`BA_API_KEY` for the Bundesagentur source; `LLM_API_KEY`, optional `LLM_BASE_URL` (default `https://api.openai.com/v1`) and `LLM_MODEL` (default `gpt-4o-mini`) for `src/llm/`; later Telegram/research keys). Stage 2 artifacts: `data/resumes/<job_id>.tex`; `stage2.latex_section_markers` must match the real `data/Resume.tex` (`\begin{rSection}{Summary}`, `\begin{rSection}{Work Experience}`, `\tableEnv{Skills}{`).
- Module docstrings follow the multi-line style: line 1 opens, prose inside, `"""` closes before the first import (a self-closing line-1 docstring followed by prose breaks the module).
- Stage-owned metadata keys (`metadata.ats`, `metadata.resume`, ...) are written only via `JobsStore.update_metadata()` — the sanctioned round-trip surface (PATCH/edit_job reject them).

## Technical Constraints
- Environment is Linux (Windows-style mount `/e/jobs`) with **fish** as the default shell — bash-isms like command substitution `(cmd)` in command position fail; prefer `bash -c` or fish-compatible syntax for complex commands.
- Scrape targets, base-resume path, score thresholds, and messaging credentials are expected in config (not yet implemented).
- Placeholder functions must keep existing signatures/behavior until real implementations land (tests assert current placeholder behavior).

## Tool Usage Patterns
- Prefer the editor tool for file edits; pytest via `.venv/bin/python -m pytest -q` from `job-pipeline/`.
- Git operations at repo root `/e/jobs` (the automation tracker operates with `REPO_ROOT = job-pipeline/`).

## Version History
- **Version 1.0**: Initialized from repository context

## Notes
- Two virtualenvs exist: `.venv` (used, tests pass) and `.venvtest` (present; parity unverified).
- `src/high_level_design_hld.py` and `src/low_level_design_lld.py` are automation-generated placeholders for Issues #1–#2 (both marked Done in `issues.md`).


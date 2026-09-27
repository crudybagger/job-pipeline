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
- Run API: `uvicorn app.main:app --reload` (from `job-pipeline/`), then `POST /ingest` with `source_url`
- Run tests: `pytest -q` (from `job-pipeline/`) — currently **3 passed** via `.venv/bin/python -m pytest -q`
- Issue automation loop: `python -m automation.run_issue_loop` (processes `issues.md` every 600s; commits+pushes if `.git` present)

## Project Structure Constraints
- All Python code lives under `job-pipeline/`; run tests/uvicorn from that directory so `src.*` imports resolve.
- `automation` at repo root is a namespace wrapper forwarding to `job-pipeline/automation` (needed when running from `/e/jobs`).
- No lockfile; dependencies are unpinned in `requirements.txt`.

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


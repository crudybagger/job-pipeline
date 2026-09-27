# Active Context

## Overview
Current work focus, recent changes, next steps, and active decisions for the project.

## Current Work Focus
Initializing and maintaining the memory bank; the repository itself is at the scaffolding-complete stage. All 4 pipeline stages are still placeholder implementations awaiting real logic per `plan.md`.

## Recent Changes
- Memory bank files created and populated from repository context (this task).
- Root `README.md` rewritten to be plan-driven and stage-oriented (PR #2, commit `6e4eea8`).
- Automation issue tracker built: `job-pipeline/automation/issue_tracker.py` + `run_issue_loop.py`; Issues #1 (HLD), #2 (LLD), #3 (scaffolding) all marked Done in `issues.md`.
- Namespace wrapper `/e/jobs/automation/__init__.py` added so `automation.*` imports resolve from repo root.

## Next Steps
1. **Stage 1**: implement real scraping in `src/ingestion/ingest.py`, normalization/enrichment in `src/parsing/parse.py`, configurable match scoring in `src/matching/match.py`; add persistent accepted/rejected queues + interactive tooling; collect required per-job fields and metadata (base resume path, notes).
2. **Stage 2**: LaTeX minimal-edit resume generation + ATS substage feedback loop with its own resume-ready queue.
3. **Stage 3**: company research + cover letter generation following the fixed narrative pattern from `plan.md`.
4. **Stage 4**: delivery-package compilation + messaging-platform integration + sent/applied tracking with candidate notes.
5. Add config layer (keywords, sources, thresholds, base resume path, messaging credentials) — `python-dotenv` is already a dependency.

## Active Decisions
- Keep the FastAPI app (`app/main.py`) as the Stage-1 entrypoint; later stages should expose entrypoints consistent with it (API route, CLI, or worker) under `src/`.
- Use local markdown issue tracking (`issues.md`) + automation loop instead of GitHub issues.
- Queue persistence technology not yet chosen (requirements include pandas; a simple DB or JSON store are candidates).

## Important Patterns and Preferences
- One package per stage under `src/`; typed pure functions; docstrings on all public functions.
- Tests isolate filesystem effects via monkey-patched module constants and temp dirs.
- Run tests from `job-pipeline/`: `pytest -q` (currently 3 passed).

## Learnings and Insights
- Host shell is fish — bash command substitutions in command position fail; adapt command syntax accordingly.
- The automation tracker only commits/pushes when a `.git` folder is present at `REPO_ROOT` (which is `job-pipeline/`).

## Open Questions
- Which persistent storage to use for the queues (SQLite vs JSON vs pandas-backed)?
- Which messaging platform to integrate first for Stage 4 (WhatsApp/Telegram/Signal)?
- Which job-board sources to prioritize for scraping?

## Blockers
- None currently; implementation can begin at any stage.

## Version History
- **Version 1.0**: Initialized from repository context

## Notes
- The ATS substage notes must round-trip through job entry metadata so Stage 2 can pick them back up (per `plan.md`).


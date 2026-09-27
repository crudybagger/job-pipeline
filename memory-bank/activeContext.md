# Active Context

## Overview
Current work focus, recent changes, next steps, and active decisions for the project.

## Current Work Focus
Stage 1–4 design plans are agreed and committed; implementation of Stage 1 is the immediate next step.

## Recent Changes
- Stage 1 design plan committed and pushed (`19dcb33`): `docs/design/stage1-job-scraping-and-filtering.md`.
- Stage 2–4 design plan committed and pushed (`01c1989`): `docs/design/stage2-4-plan.md`.
- Confirmed Stage 1 decisions: JSON-API boards now + HTML-scraper stub later (plugin pattern); SQLite queues; deterministic scoring now + pluggable LLM backend later; CLI + FastAPI tooling; JSON config with pydantic validation.
- Confirmed Stage 2–4 decisions: OpenAI-compatible LLM behind shared `src/llm/`; Telegram Bot API for Stage 4; Tavily research now → Zyte later → DuckDuckGo/firecrawl fallbacks; section-targeted LaTeX editing; ATS loop capped by threshold + max iterations; plain-text cover letters; `sent` status in the same SQLite store.

## Next Steps
1. **Implement Stage 1** per `docs/design/stage1-job-scraping-and-filtering.md`: config layer + models, ingestion dispatch + fetchers (Remotive/RemoteOK JSON-API, HTML stub), parsing normalization, deterministic scoring, SQLite queue store, CLI + FastAPI tooling, tests.
2. **Shared foundation for Stages 2–4** per `docs/design/stage2-4-plan.md`: `src/llm/` OpenAI-compatible abstraction + config extension (`stage2`/`stage3`/`stage4` sections).
3. **Stage 2**: LaTeX minimal-edit resume generation + ATS substage feedback loop with its own resume-ready queue status.
4. **Stage 3**: Tavily research chain + cover letter generation following the fixed narrative pattern.
5. **Stage 4**: delivery-message compilation + Telegram Bot API + sent/applied tracking with candidate notes.

## Active Decisions
- Keep the FastAPI app (`app/main.py`) as the Stage-1 entrypoint; later stages should expose entrypoints consistent with it (API route, CLI, or worker) under `src/`.
- Use local markdown issue tracking (`issues.md`) + automation loop instead of GitHub issues.
- Queue persistence: **SQLite** via stdlib `sqlite3` (decided; store at `job-pipeline/data/queues.db`).
- LLM: OpenAI-compatible API behind shared `src/llm/` abstraction (decided, serves Stage 1 pluggable scorer + Stages 2–3).
- Messaging: Telegram Bot API (decided, Stage 4).
- Research: Tavily now → Zyte spider future → DuckDuckGo/firecrawl fallbacks (decided, Stage 3).

## Important Patterns and Preferences
- One package per stage under `src/`; typed pure functions; docstrings on all public functions.
- Tests isolate filesystem effects via monkey-patched module constants and temp dirs.
- Run tests from `job-pipeline/`: `pytest -q` (currently 3 passed).

## Learnings and Insights
- Host shell is fish — bash command substitutions in command position fail; adapt command syntax accordingly.
- The automation tracker only commits/pushes when a `.git` folder is present at `REPO_ROOT` (which is `job-pipeline/`).

## Open Questions
- None — storage (SQLite), LLM (OpenAI-compatible), messaging (Telegram), and sources (JSON-API boards now + HTML stub later) are all decided. Open question only for implementation: exact Remotive/RemoteOK JSON field shapes (verify against live responses before finalizing field mappings).

## Blockers
- None currently; implementation can begin at any stage.

## Version History
- **Version 1.0**: Initialized from repository context

## Notes
- The ATS substage notes must round-trip through job entry metadata so Stage 2 can pick them back up (per `plan.md`).


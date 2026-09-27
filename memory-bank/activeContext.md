# Active Context

## Overview
Current work focus, recent changes, next steps, and active decisions for the project.

## Current Work Focus
Stage 1–4 design review completed (individual + whole-pipeline integration review); design docs restructured into per-stage files plus a cross-stage contract. A second integration-solidification pass added the stage trigger & queue-selection contract, the observability/admin surface (status API + UI + entry editing), and the substage modularity contract. Implementation of Stage 1 is the immediate next step.

## Recent Changes
- **Integration solidification round**: `docs/design/pipeline-integration.md` gained three contract sections: (1) *stage trigger & queue-selection contract* — per-stage input status filter + registered preconditions + batch triggers `POST /stage{1..4}/run?limit=N[&dry_run=true]` reusing per-entry code paths; (2) *observability & admin tooling* — `GET /status` pipeline summary (queue counts + stage flags), static dependency-free admin UI at `GET /ui` (thin client over the API), `PATCH /jobs/{id}` guarded generic entry edit (whitelist only; `id`/`status`/stage-owned registry keys immutable), CLI parity; (3) *substage modularity contract* — substage = one module / one primary function / one registered metadata key / own trigger route / never transitions status unless it owns it, with substage-only triggers `POST /jobs/{id}/resume/ats` (2), `POST /jobs/{id}/research` (3), `GET /jobs/{id}/delivery/preview` (4). Per-stage docs' entry-point/tooling sections amended to match.
- **Design review completed**: each stage reviewed individually and the pipeline as a whole against `plan.md` and the scaffolding code; all integration issues resolved in the design.
- Design docs restructured in `docs/design/`: `pipeline-integration.md` (new cross-stage contract), per-stage files `stage1-job-scraping-and-filtering.md` (amended), `stage2-resume-generation.md`, `stage3-cover-letter-generation.md`, `stage4-candidate-delivery.md` (split from the removed `stage2-4-plan.md`).
- Key integration decisions fixed before implementation: forward-complete `JobStatus` enum (incl. `resume_ready`, `sent`; applied state in `metadata.application`); stable job ID `sha256(title|company|source)[:12]` as store primary key; documented metadata key registry (extend, never repurpose); status transition map enforced in the store; unified `jobs` API resource (no separate `/sent`); artifacts on disk (`data/resumes/<id>.tex`, `data/coverletters/<id>.md`); Stage 2 `max_iterations` cap does **not** auto-advance (sets `metadata.ats.needs_review`, human force-ready); Stage 4 two-part delivery (text message + resume as `sendDocument` attachment) with idempotency via `metadata.delivery`; one config file shape from day one; stages never import each other (store is the only cross-stage contract); manual orchestration; shared `tests/conftest.py` fixtures.
- Confirmed Stage 1 decisions: JSON-API boards now + HTML-scraper stub later (plugin pattern); SQLite queues; deterministic scoring now + pluggable LLM backend later; CLI + FastAPI tooling; JSON config with pydantic validation.
- Confirmed Stage 2–4 decisions: OpenAI-compatible LLM behind shared `src/llm/`; Telegram Bot API for Stage 4; Tavily research now → Zyte later → DuckDuckGo/firecrawl fallbacks; section-targeted LaTeX editing; ATS loop capped by threshold + max iterations; plain-text cover letters; `sent` status in the same SQLite store.

## Next Steps
1. **Implement Stage 1** per `docs/design/stage1-job-scraping-and-filtering.md` + `docs/design/pipeline-integration.md`: full-shape config layer + models (forward-complete `JobStatus`, stable job ID), ingestion dispatch + fetchers (Remotive/RemoteOK JSON-API, HTML stub), parsing normalization, deterministic scoring, SQLite jobs store with transition enforcement, CLI + unified FastAPI routes **including the shared admin surface Stage 1 owns (`GET /status`, `PATCH /jobs/{id}`, batch `POST /stage1/run`, static UI at `GET /ui`)**, shared `tests/conftest.py` + tests.
2. **Shared foundation for Stages 2–4** per `docs/design/pipeline-integration.md`: `src/llm/` OpenAI-compatible abstraction (config `stage2`/`stage3`/`stage4` sections already shipped by Stage 1).
3. **Stage 2** per `docs/design/stage2-resume-generation.md`: LaTeX minimal-edit generation + ATS substage feedback loop; artifacts on disk; `needs_review` path for capped iterations.
4. **Stage 3** per `docs/design/stage3-cover-letter-generation.md`: Tavily research chain + cover letter generation following the fixed narrative pattern.
5. **Stage 4** per `docs/design/stage4-candidate-delivery.md`: two-part delivery compilation + Telegram Bot API (message + `sendDocument`) + idempotent send + sent/applied tracking with candidate notes.

## Active Decisions
- Keep the FastAPI app (`app/main.py`) as the Stage-1 entrypoint; later stages extend the same unified `jobs` API resource (no parallel resources like a separate `/sent`).
- Use local markdown issue tracking (`issues.md`) + automation loop instead of GitHub issues.
- Queue persistence: **SQLite** via stdlib `sqlite3` (decided; store at `job-pipeline/data/queues.db`) — the single cross-stage store; stages never import each other.
- LLM: OpenAI-compatible API behind shared `src/llm/` abstraction (decided, serves Stage 1 pluggable scorer + Stages 2–3).
- Messaging: Telegram Bot API (decided, Stage 4; resume delivered as document attachment).
- Research: Tavily now → Zyte spider future → DuckDuckGo/firecrawl fallbacks (decided, Stage 3).
- Resume/cover-letter artifacts live on disk under `job-pipeline/data/` (gitignored), not in DB blobs.
- Orchestration is deliberately manual: every status transition and stage action is human/API-triggered; batch runs (`POST /stage{1..4}/run`) are still explicit human actions, never schedulers.
- Admin UI is a dependency-free static page (`app/static/index.html`) served at `GET /ui` — a thin client over the API; every UI capability must exist as an API route first.
- Generic entry editing goes through `PATCH /jobs/{id}` with a whitelist (human-owned fields/keys only); `id`, `status`, and stage-owned registry keys are immutable there.

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


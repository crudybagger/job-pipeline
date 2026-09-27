# Progress

## Overview
Tracks what works, what remains to build, current status, known issues, and evolution of project decisions.

## What Works
- ✅ **Stage 1 — Job Scraping and Filtering implemented, tested, and validated with real web data** (LLD: `docs/design/stage1-lld.md`; context & usage guide: `docs/stage1-context-and-usage.md`): config layer (`config/pipeline.json` real, gitignored + `pipeline.example.json` full shape), models (`JobStatus`, stable job ID, metadata registry), ingestion dispatch + 4 JSON-API fetchers (Remotive, RemoteOK, Arbeitnow, Bundesagentur für Arbeit) + HTML-stub seam, parsing normalization per source, deterministic match scoring (experience/prospects/education factors + hard location gate; re-tuned once via the rejected-list analysis), SQLite jobs store with transition-map enforcement + guarded whitelist edits, `src/stage1.py` orchestrator (per-source error isolation, dry-run, limit), full CLI (`python -m src.queues.cli`) + unified FastAPI routes + static admin UI at `GET /ui`, live isolation check (`scripts/stage1_live.py`: 441 real jobs ingested) + `scripts/analyze_rejected.py`.
- ✅ **Integration solidified** (second design pass): independent stage triggering + queue-selection contract, batch stage runs, `GET /status` + `PATCH /jobs/{id}` + static admin UI (`GET /ui`), and the substage modularity contract added to `docs/design/pipeline-integration.md`; per-stage docs amended.
- ✅ **Design review of all 4 stages completed** (individual + whole-pipeline integration review); all integration issues resolved in the design.
- ✅ Design docs restructured in `docs/design/`: `pipeline-integration.md` (cross-stage contract: `JobStatus` enum, job ID scheme, metadata registry, transition map, unified API surface, data layout, config shape, testing contract) + per-stage files: `stage1-job-scraping-and-filtering.md`, `stage2-resume-generation.md`, `stage3-cover-letter-generation.md`, `stage4-candidate-delivery.md`, plus `stage1-lld.md`.
- ✅ Repository scaffolding (Issue #3, Done) + local issue-tracker automation + namespace `automation` wrapper.
- ✅ Test suite: `pytest -q` from `job-pipeline/` → **84 passed** (per-source fixture normalization from recorded live shapes in `tests/fixtures/`, store transitions, orchestrator with fake fetchers, CLI + API via TestClient, scorer units; no live network in tests).
- ✅ CI: GitHub Actions runs `pytest -q` on push/PR to `main` (Python 3.12).
- ✅ Plan-driven root README documenting all 4 stages and run targets (Stage 1 section reflects the implementation).

## What's Left to Build
- ⬜ **Shared foundation** (per `docs/design/pipeline-integration.md`): `src/llm/` OpenAI-compatible abstraction (config `stage2`/`stage3`/`stage4` sections already shipped by Stage 1; Stage 1's `llm` scorer slot stub plugs in here).
- ❌ **Stage 2** (per `docs/design/stage2-resume-generation.md`): LaTeX minimal-edit generation on disk; ATS-like scoring substage with feedback-notes loop until ready; `needs_review` path for capped iterations; separate `resume_ready` status.
- ❌ **Stage 3** (per `docs/design/stage3-cover-letter-generation.md`): Tavily-first modular research chain with graceful degradation; cover letter generation following the fixed narrative pattern; artifacts on disk.
- ❌ **Stage 4** (per `docs/design/stage4-candidate-delivery.md`): two-part delivery compilation (text + resume `sendDocument`); idempotent Telegram Bot API integration; sent/applied tracking with candidate notes in metadata.
- ❌ Real implementations for `src/high_level_design_hld.py` / `src/low_level_design_lld.py` (currently comment-only placeholders).
- ⬜ Optional Stage 1 follow-ups: validate the Bundesagentur source from a residential network (403 from datacenter IPs); re-tune weights/threshold after reviewing the rejected list (`scripts/analyze_rejected.py`); RWTH Aachen HiWi HTML fetcher via the `html-stub` plugin seam.

## Current Status
**Stage 1 implemented, tested (84 passed), and validated against real web data** (441 live jobs ingested; score re-tuned once via the rejected-list analysis). Design review complete; LLD at `docs/design/stage1-lld.md`. Ready for the shared `src/llm/` foundation + Stage 2.

## Known Issues
- `src/outreach/send_application.py` still returns `True` unconditionally (Stage 4 scope); the Stage 1 placeholder `fetch_job_listings()` is preserved intentionally.
- Two virtualenvs exist (`.venv`, `.venvtest`); only `.venv` is verified working.
- Automation tracker's git push runs with `REPO_ROOT = job-pipeline/` — commits would target the nested directory, not the monorepo root at `/e/jobs` (worth reviewing before enabling the loop).
- Dependencies in `requirements.txt` are unpinned (no lockfile).
- Bundesagentur für Arbeit API returns 403 from datacenter IPs (works from residential networks) — the source errors gracefully per-source.

## Evolution of Project Decisions
- Issue tracking moved from (nonexistent) GitHub issues to local `issues.md` + automation loop.
- Root README rewritten from a generic project description to a plan-driven, stage-oriented guide referencing `plan.md`.
- `automation` namespace wrapper introduced to fix `ModuleNotFoundError` when importing from repo root.
- Bundesagentur für Arbeit JSON API added as a 4th source (user decision) — still no new dependencies; RWTH Aachen HiWi board remains the HTML-stub plugin seam.
- Stage 1 score re-tuning round 1: `STOPWORDS` filter for experience terms; education factor now title-hit = 100 / text-hit = 40 / none = 0 (was proportional over role-keyword count).

## Milestones Achieved
- M1: Repository scaffolding + issue tracker automation ✅
- M2: Stage 1 — scraping, filtering, persistent queues ✅
- Memory bank initialized ✅

## Upcoming Milestones
- M2.5: Shared foundation — `src/llm/` OpenAI-compatible abstraction
- M3: Stage 2 — resume generation + ATS loop
- M4: Stage 3 — cover letter generation
- M5: Stage 4 — delivery package + messaging integration

## Version History
- **Version 1.0**: Initialized from repository context

## Notes
- Verify CI actually runs green on the next push (current commits are local-time Sept 2026; last commit `f1dbbbc`).


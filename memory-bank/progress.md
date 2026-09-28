# Progress

## Overview
Tracks what works, what remains to build, current status, known issues, and evolution of project decisions.

## What Works
- ✅ **Stage 1 — Job Scraping and Filtering implemented, tested (84 tests), and validated with real web data** (LLD: `docs/design/stage1-lld.md`; usage guide: `docs/stage1-context-and-usage.md`): config layer, models, ingestion dispatch + 4 JSON-API fetchers + HTML-stub seam, per-source parsing, deterministic match scoring with re-tunable weights + hard location gate, SQLite store with transition map + guarded whitelist edits, `src/stage1.py` orchestrator, full CLI + unified FastAPI routes + admin UI, live check + rejected-list analysis scripts.
- ✅ **Shared foundation M2.5 — `src/llm/` OpenAI-compatible provider** (`provider.py` + `__init__.py`): `LLMClient.complete(system, user, schema=None)` with JSON mode, retries/backoff, `LLMError` on unconfigured/exhausted calls; settings from `.env` (`LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`); mockable module seam (`set_client`/`get_client`/`complete`); no new dependencies. 7 tests (MockTransport).
- ✅ **Stage 2 production code complete** (LLD: `docs/design/stage2-lld.md`):
  - `JobsStore.update_metadata()` — stage-owned metadata round-trip (`metadata.ats`, `metadata.resume`).
  - `src/resume/generate.py` — section-targeted LaTeX editing (configurable rSection/tableEnv markers + auto-detect fallback), programmatic edit application, difflib span validation, artifact IO at `data/resumes/<job_id>.tex`.
  - `src/resume/ats.py` — LLM screener persona + deterministic bucketed keyword scorer (matching weights) + combine (0.7/0.3).
  - `src/resume/loop.py` — iteration loop with feedback round-trip; `accepted → resume_ready` only when the combined score ≥ `stage2.ats_ready_threshold`; cap → `needs_review` (stays accepted); owns the only Stage 2 status transition.
  - `src/resume/stage2.py` — `run_stage2` batch/single-job orchestrator (dry-run, per-entry error isolation), `run_ats_substage`, `force_ready`.
  - API: `POST /stage2/run`, `POST /jobs/{id}/resume/{generate,ats,force-ready}`; `GET /status` stage2 `implemented: true` + `pending_review`.
  - CLI: `resume-generate`, `resume-ats`, `resume-force-ready`, `resume-run`.
  - Config: `stage2.latex_section_markers` set in both configs, verified against the real `data/Resume.tex`.
- ✅ **Stage 2 tests (first wave)**: `test_llm.py` (7), `test_resume.py` (16), `test_ats.py` (8) — fixtures `tests/fixtures/base_resume.tex`, `FakeLLMClient` + `fake_llm` in conftest; no live network.
- ✅ **Integration contract** (`docs/design/pipeline-integration.md`) + design review of all 4 stages; per-stage design docs.
- ✅ Test suite: `pytest -q` from `job-pipeline/` → **115 passed** (84 Stage-1 baseline + 31 Stage-2/foundation).
- ✅ CI: GitHub Actions runs `pytest -q` on push/PR to `main` (Python 3.12).

## What's Left to Build
- ⬜ **Stage 2 test wrap-up**: `tests/test_loop.py` (threshold/cap/round-trip/single-iteration/status guards), `tests/test_stage2.py` (selection/dry-run/skip/error isolation/job_id guards); additions to `test_api.py` (new routes incl. 409s, status payload), `test_cli.py` (resume subcommands), `test_store.py` (`update_metadata`).
- ⬜ **Stage 2 docs wrap-up**: implementation-status note on `docs/design/stage2-resume-generation.md` (incl. the `metadata.ats` shape amendment); root + job-pipeline README stage-2 sections; optional `scripts/stage2_live.py` manual live check.
- ⬜ **Real-run prerequisite**: `LLM_API_KEY` (+ optional `LLM_BASE_URL`/`LLM_MODEL`) in `job-pipeline/.env` — absent; all Stage-2 LLM calls raise `LLMError` until set (tests unaffected).
- ❌ **Stage 3** (per `docs/design/stage3-cover-letter-generation.md`): Tavily-first modular research chain with graceful degradation; cover letter generation following the fixed narrative pattern; artifacts on disk.
- ❌ **Stage 4** (per `docs/design/stage4-candidate-delivery.md`): two-part delivery compilation (text + resume `sendDocument`); idempotent Telegram Bot API integration; sent/applied tracking with candidate notes in metadata.
- ❌ Real implementations for `src/high_level_design_hld.py` / `src/low_level_design_lld.py` (comment-only placeholders).
- ⬜ Optional Stage 1 follow-ups: validate the Bundesagentur source from a residential network (403 from datacenter IPs); RWTH Aachen HiWi HTML fetcher via the `html-stub` seam.

## Current Status
**Stage 1 done (84 tests, live-validated). Stage 2 + shared `src/llm/` foundation: production code, API/CLI surfaces, configs, and LLD complete; first test wave green — full suite 115 passed.** Remaining before Stage 3: the last Stage-2 test files, doc status notes, and the `.env` LLM key for real runs.

## Known Issues
- `LLM_API_KEY` not configured — every Stage-2 LLM call raises `LLMError` (batch records per-entry errors and continues; tests use the fake client).
- `src/outreach/send_application.py` still returns `True` unconditionally (Stage 4 scope); the Stage 1 placeholder `fetch_job_listings()` is preserved intentionally.
- Two virtualenvs exist (`.venv`, `.venvtest`); only `.venv` is verified working.
- Automation tracker's git push runs with `REPO_ROOT = job-pipeline/` — commits would target the nested directory, not the monorepo root at `/e/jobs` (worth reviewing before enabling the loop).
- Dependencies in `requirements.txt` are unpinned (no lockfile).
- Bundesagentur für Arbeit API returns 403 from datacenter IPs (works from residential networks) — errors gracefully per-source.
- Pre-existing Starlette testclient deprecation warning in the test output (unrelated to Stage 2).

## Evolution of Project Decisions
- Issue tracking moved from (nonexistent) GitHub issues to local `issues.md` + automation loop.
- Root README rewritten to a plan-driven, stage-oriented guide referencing `plan.md`.
- Bundesagentur für Arbeit JSON API added as a 4th source (user decision).
- Stage 1 score re-tuning round 1: `STOPWORDS` filter; education factor title-hit = 100 / text-hit = 40 / none = 0.
- **`metadata.ats` shape resolved** (Stage 2 LLD): `{"iterations": [...], "needs_review": bool}` — the design doc described it both as a list and as holding `needs_review`.
- **Combined ATS scoring** introduced: 0.7·LLM + 0.3·deterministic; the combined score (not the LLM's `ready` flag) drives `resume_ready` advancement.
- **`JobsStore.update_metadata()` added** as the sanctioned stage-owned metadata write surface (store.save's merge semantics would discard stage results).
- Stage 2 LLM edits return section **content only**; LaTeX structure is edited programmatically (safer than full-file generation per the design's minimal-edit constraint).

## Milestones Achieved
- M1: Repository scaffolding + issue tracker automation ✅
- M2: Stage 1 — scraping, filtering, persistent queues ✅
- M2.5: Shared foundation — `src/llm/` OpenAI-compatible abstraction ✅
- M3: Stage 2 — resume generation + ATS loop ✅ (code + surfaces; test/docs wrap-up pending)
- Memory bank initialized ✅

## Upcoming Milestones
- M3 wrap-up: `test_loop`/`test_stage2` + api/cli/store additions; docs + README updates
- M4: Stage 3 — cover letter generation
- M5: Stage 4 — delivery package + messaging integration

## Version History
- **Version 1.0**: Initialized from repository context
- **Version 1.1**: Stage 1 complete
- **Version 1.2**: Stage 2 + `src/llm/` mid-flight (code complete, 115 tests passing)

## Notes
- Verify CI actually runs green on the next push (last known commit `f1dbbbc` predates Stage 2).
- `GET /jobs/{id}` already exposes `metadata.ats`/`metadata.resume` — the needs_review path is surfaceable without UI changes.

# Active Context

## Overview
Current work focus, recent changes, next steps, and active decisions for the project.

## Current Work Focus
**Stage 2 (Matching Resume Generation) + the shared `src/llm/` foundation are implemented mid-flight: all production code, API/CLI surfaces, config markers, and the LLD are in place; the full suite passes (115 tests). Remaining: the last test files (test_loop, test_stage2, api/cli/store additions), doc status notes, and the `LLM_API_KEY` .env secret before a real run.** LLD: `docs/design/stage2-lld.md`.

## Recent Changes
- **Stage 2 LLD written** (`docs/design/stage2-lld.md`, 216 lines): module map, data flow, substage signatures, section-marker scheme (grounded in the real `data/Resume.tex`: `\begin{rSection}{...}` blocks + `\tableEnv{Skills}{...}` brace block), prompts, API/CLI surface, test plan. Resolved a design-doc conflict: `metadata.ats` is `{"iterations": [...], "needs_review": bool}` (the HLD described it both as a list and as holding `needs_review`).
- **Shared foundation M2.5 built** (`src/llm/`): `provider.py` with `LLMClient` — OpenAI-compatible `/chat/completions` over httpx, JSON-mode via `response_format` + schema instruction when `schema` is given, retries on 429/5xx/network errors with linear backoff, `LLMError` when `LLM_API_KEY` is missing or retries exhaust; settable module seam `set_client()`/`get_client()`/`complete()` for tests and Stage 1's `llm` scorer slot. Settings from `.env`: `LLM_BASE_URL` (default `https://api.openai.com/v1`), `LLM_API_KEY`, `LLM_MODEL` (default `gpt-4o-mini`). **No new dependencies** (httpx + python-dotenv already present).
- **Store extension**: `JobsStore.update_metadata(job_id, updates)` — merges stage-owned registry keys (`metadata.ats`, `metadata.resume`) wholesale; the round-trip surface substages need (store.save's existing-value-wins merge would discard stage results).
- **`src/resume/` package built** (all four modules import cleanly):
  - `generate.py`: `resolve_base_resume_path` (metadata first, config fallback, relative paths resolve against job-pipeline/), `find_section_span` (rSection begin/end matching + brace counting for `\tableEnv`), `detect_section_markers` fallback (auto-detected tableEnv markers include the trailing content brace), `locate_sections`, `edit_base_resume` (LLM returns section CONTENT only via JSON schema; edits applied programmatically right-to-left; difflib `_validate_edit` asserts every diff region lies inside the permitted spans), `save_resume`/`load_resume_artifact` (artifacts at `data/resumes/<job_id>.tex`).
  - `ats.py`: `score_resume` (LLM screener/hiring-manager persona, JSON `{score, feedback, ready}`, clamped/normalized), `score_resume_deterministic` (bucketed keyword coverage — general/experience, in-demand/prospects, role/education — weighted by matching.score_weights, empty buckets excluded from the denominator), `combine_scores` (round(0.7·llm + 0.3·det), feedback concatenated).
  - `loop.py`: `run_loop` — the only Stage 2 place that transitions status. Per iteration: edit seeded with the previous iteration's feedback (plan.md round-trip) → save artifact → LLM + deterministic scoring → append iteration to `metadata.ats` via the store → combined score ≥ `stage2.ats_ready_threshold` breaks the loop; sets `metadata.resume.ready_at` and transitions `accepted → resume_ready`. Cap without threshold: stays `accepted` + `metadata.ats.needs_review = true` (design decision 4 — no auto-advance). Single-iteration mode (`run_to_completion=False`) never sets needs_review. Refuses non-accepted entries (ValueError).
  - `stage2.py`: `run_stage2` (batch over accepted entries incl. needs_review re-runs; per-entry error isolation; dry-run; single-`job_id` mode raising 404/409-shaped errors), `run_ats_substage` (scores existing artifact or base resume, appends to metadata.ats, no generation/transition), `force_ready` (human promotion; transition-map enforced; sets `ready_at` when an artifact exists).
- **API routes added** (`app/main.py`): `POST /stage2/run?limit=&dry_run=`, `POST /jobs/{id}/resume/generate?run_to_completion=` (404 unknown / 409 not accepted), `POST /jobs/{id}/resume/ats`, `POST /jobs/{id}/resume/force-ready` (409 on bad transition); `GET /status` now reports stage2 `implemented: true` + `pending_review` (needs_review count).
- **CLI subcommands added** (`src/queues/cli.py`): `resume-generate <id> [--single]`, `resume-ats <id>`, `resume-force-ready <id>`, `resume-run [--limit N] [--dry-run] [--single]`; global error handling extended with FileNotFoundError.
- **Config markers set** (`stage2.latex_section_markers` in both `config/pipeline.json` and `config/pipeline.example.json`): summary → `\begin{rSection}{Summary}`, experience → `\begin{rSection}{Work Experience}`, skills → `\tableEnv{Skills}{` — all three verified present in the real `data/Resume.tex`.
- **Tests so far**: `tests/fixtures/base_resume.tex` (mini LaTeX with rSection/tableEnv blocks); conftest additions `FakeLLMClient`, `fake_llm` installer fixture (monkeypatches `src.llm.provider.set_client`), `base_resume_tex`. New files: `test_llm.py` (7 passed — MockTransport, JSON mode, retries, missing key, set_client seam), `test_resume.py` (16 passed — markers/spans/apply/validate/edit/path/artifact), `test_ats.py` (8 passed — deterministic scoring/weights/feedback, LLM normalization, combine). **Full suite: 115 passed** (84 Stage-1 baseline + 31 new); the single warning is the pre-existing Starlette testclient deprecation, unrelated.

## Next Steps
1. **`tests/test_loop.py`**: threshold met → `resume_ready` + `ready_at`; cap → stays accepted + `needs_review`; feedback round-trip visible in the second LLM prompt; single-iteration mode; status guards (KeyError unknown id, ValueError non-accepted).
2. **`tests/test_stage2.py`**: selection (accepted incl. needs_review), dry-run persists nothing, skip-without-base-resume, per-entry error isolation, job_id guards.
3. **Additions**: `test_api.py` (new routes incl. 409s + status payload), `test_cli.py` (resume subcommands), `test_store.py` (`update_metadata` merge/replace/KeyError).
4. **`scripts/stage2_live.py`** (optional manual live check mirroring `stage1_live.py`).
5. **Docs wrap-up**: implementation-status note on `docs/design/stage2-resume-generation.md`; root + job-pipeline README stage-2 sections; final memory-bank refresh after the remaining tests.
6. **Real-run prerequisite**: set `LLM_API_KEY` (and optionally `LLM_BASE_URL`/`LLM_MODEL`) in `job-pipeline/.env` — currently absent, so every Stage-2 LLM call raises `LLMError` (tests are unaffected; they use the scripted fake client).
7. Then: Stage 3 (cover letter generation, `docs/design/stage3-cover-letter-generation.md`), Stage 4 (delivery, `docs/design/stage4-candidate-delivery.md`).

## Active Decisions
- Keep the FastAPI app (`app/main.py`) as the entrypoint; Stage 2 extended the same unified `jobs` API resource (no parallel resources).
- Use local markdown issue tracking (`issues.md`) + automation loop instead of GitHub issues.
- Queue persistence: **SQLite** via stdlib `sqlite3` at `job-pipeline/data/queues.db` — the single cross-stage store; stages never import each other; `update_metadata` is the stage-owned metadata round-trip surface.
- LLM: OpenAI-compatible API behind shared `src/llm/` (decided; settings from `.env`, no config-format change).
- Stage 2 loop termination: config-driven threshold + iteration cap; cap never auto-advances (`needs_review` + human `force-ready`).
- Section-targeted LaTeX editing: LLM returns section content only; edits applied programmatically; difflib validation guards the spans.
- Combined ATS score = 0.7·LLM + 0.3·deterministic (constants `LLM_WEIGHT`/`DETERMINISTIC_WEIGHT` in `ats.py`); the combined score (not the LLM's `ready` flag) drives advancement.
- Artifact paths stored absolute in `metadata.resume.path` (single-candidate local pipeline; `data/` gitignored).
- Messaging: Telegram Bot API (Stage 4). Research: Tavily-first (Stage 3).
- Orchestration is deliberately manual: every transition and stage action is human/API-triggered; batch runs are explicit actions, never schedulers.
- Admin UI stays a dependency-free static page; every UI capability must exist as an API route first.

## Important Patterns and Preferences
- One package per stage under `src/`; one module / one primary function per substage; typed pure functions; multi-line docstrings (line 1 opens, `"""` closes before the first import).
- Tests isolate filesystem/LLM effects via monkey-patched module constants (`DB_PATH`, `RESUMES_DIR`, `set_client`) and temp dirs; no live network anywhere in the suite.
- Run tests from `job-pipeline/`: `.venv/bin/python -m pytest -q` (currently 115 passed).

## Learnings and Insights
- **Heredoc escaping pitfall**: writing JSON config values from a Python heredoc double-escaped backslashes (`\\begin` in the file → two literal backslashes after decode). Always verify round-tripped marker/config values against the real target file.
- **`_validate_edit` semantics**: `apply_section_edits` compares the edited base against itself, so tampering the *base* is invisible to it — the correct unit test targets `_validate_edit` directly with an out-of-span diff (e.g., a preamble change).
- Auto-detected `\tableEnv{Name}` markers must include the trailing content brace `{` (the regex `\tableEnv\{([^}]*)\}` stops at the first `}`); `find_section_span` still works either way, but the configured and detected markers should agree.
- difflib char-level SequenceMatcher (autojunk=False) is fine at resume scale (~10 KB) for the span validation.
- `run_commands` shell capture is intermittently flaky with multi-line `python -c`; prefer writing a small script (or redirecting output to a temp file) and reading it back.
- Host shell is fish; nested shells report heuristic exit codes — verify via output artifacts, not exit codes.
- pydantic v2: assigning a plain dict to a model field does not validate/convert — construct nested models explicitly.
- Bundesagentur für Arbeit API returns 403 from datacenter IPs (works from residential networks).

## Open Questions
- None blocking Stage 2 wrap-up. For the real run: which OpenAI-compatible endpoint/model the candidate will use (config via `.env`; defaults target OpenAI). Optional Stage 1 follow-ups (BA 403 from residential network, RWTH HTML fetcher) remain open.

## Blockers
- None for code work. A real (non-test) Stage-2 run is blocked only on `LLM_API_KEY` in `job-pipeline/.env`.

## Version History
- **Version 1.0**: Initialized from repository context
- **Version 1.1**: Stage 1 complete (LLD, implementation, 84 tests, live validation, re-tuning)
- **Version 1.2**: Stage 2 + `src/llm/` foundation mid-flight (code, surfaces, configs, LLD, 31 new tests; 115 passing)

## Notes
- The ATS substage notes round-trip through `metadata.ats` so Stage 2 picks them back up (per plan.md) — implemented via `JobsStore.update_metadata` + the loop's feedback re-seeding.
- `GET /jobs/{id}` already exposes `metadata.ats`/`metadata.resume`, so the needs_review path is surfaceable without UI changes.

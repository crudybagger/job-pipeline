# Active Context

## Overview
Current work focus, recent changes, next steps, and active decisions for the project.

## Current Work Focus
**Stage 1 is implemented, tested, and validated against real web data.** The low-level design lives in `docs/design/stage1-lld.md`. Sources now include the free Bundesagentur für Arbeit JSON API (Werkstudent/HiWi near Aachen/Cologne; RWTH Aachen itself stays the HTML-stub seam for later). Immediate next step: Stage 2 + shared `src/llm/` foundation.

## Recent Changes
- **Stage 1 context & usage documentation added** (`docs/stage1-context-and-usage.md`): purpose/queue semantics, targeting (EN+DE Werkstudent/HiWi remote or near Aachen/Cologne/Düsseldorf), sources table, config knobs, running via API/CLI (batch, single-source, review tooling), the re-tuning loop, live-check usage, data layout, known limitations. `job-pipeline/README.md` rewritten to reflect the implemented Stage 1 (architecture, quick start, usage, validation/tuning); HLD doc (`docs/design/stage1-job-scraping-and-filtering.md`) gained an implementation-status note with deltas (BA source, location gate, `stage1.py` orchestrator) and pointers to the LLD + usage guide; root README links the usage doc.
- **Stage 1 LLD + implementation complete** (`docs/design/stage1-lld.md`): fixed the broken mid-implementation scaffolding (truncated/corrupt docstrings in `config.py`, `parse.py`, `match.py`, `models.py`, `ingest.py` — files had one-liner module docstrings followed by a stray opening `"""` that swallowed the module or left unterminated strings; tests failed with SyntaxError before); completed `parse.py` (`_parse_arbeitnow`, `_parse_bundesagentur`, `parse_job_listing` dispatch), rewrote `match.py` (deterministic `compute_match_score` with experience/prospects/education factors + hard location gate, single `match_candidate_to_job`), added `BundesagenturFetcher` (public `X-API-Key: jobboerse-jobsuche`, override via `.env` `BA_API_KEY`), `src/queues/store.py` (SQLite jobs store, transition-map enforcement, idempotent re-ingest, guarded `edit_job` whitelist), `src/stage1.py` orchestrator (`run_stage1`, per-source error isolation, dry-run), `src/queues/cli.py` (full CLI surface), unified FastAPI routes + static admin UI at `GET /ui`, `config/pipeline.json` (real, gitignored) + `config/pipeline.example.json`.
- **Live isolation check with real web data** (`scripts/stage1_live.py`): 441 real jobs ingested (Remotive 17, RemoteOK 99, Arbeitnow 325); BA returns **403 from datacenter IPs** (works from residential networks) — reported per-source, not fatal.
- **Score re-tuning round 1** (plan.md loop, `scripts/analyze_rejected.py`): experience factor was polluted by stopword matches from prose experience entries (`the`, `team`, `and`); education factor divided by the number of role keywords so a perfect Werkstudent title hit capped at ~9/100. Fixed with a `STOPWORDS` frozenset + title-hit = full education factor (100), text-hit = 40. After re-tuning: 7 Werkstudent/SHK/HiWi-style jobs near Köln/Düsseldorf/Münster routed to `new` (scores 44-49), full-time non-student roles stay rejected. Threshold stays 40 (re-tunable).
- **Test suite**: 84 passed (`pytest -q` from `job-pipeline/`), incl. per-source fixture normalization (recorded live shapes in `tests/fixtures/`), store transition-map tests, orchestrator tests with fake fetchers, CLI + API (TestClient) tests, scorer unit tests. No live network in tests.
- `.gitignore` now covers `data/`, `config/pipeline.json`, `config/*.local.json` (paths relative to `job-pipeline/`); root README Stage 1 section updated with real run targets.

## Next Steps
1. **Shared foundation for Stages 2–4** per `docs/design/pipeline-integration.md`: `src/llm/` OpenAI-compatible abstraction (config `stage2`/`stage3`/`stage4` sections already shipped by Stage 1; Stage 1's `llm` scorer slot stub plugs in here).
2. **Stage 2** per `docs/design/stage2-resume-generation.md`: LaTeX minimal-edit generation + ATS substage feedback loop; artifacts on disk; `needs_review` path for capped iterations.
3. **Stage 3** per `docs/design/stage3-cover-letter-generation.md`: Tavily research chain + cover letter generation following the fixed narrative pattern.
4. **Stage 4** per `docs/design/stage4-candidate-delivery.md`: two-part delivery compilation + Telegram Bot API (message + `sendDocument`) + idempotent send + sent/applied tracking with candidate notes.
5. **Optional Stage 1 follow-ups**: run the live check from a residential network to validate the Bundesagentur source (403 from datacenter IPs); re-tune weights/threshold after reviewing the rejected list (`scripts/analyze_rejected.py`); add the RWTH Aachen HiWi HTML fetcher via the `html-stub` plugin seam.

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
- **Docstring convention pitfall**: several scaffolding files had a self-closing one-liner module docstring on line 1 followed by a prose block whose stray `"""` opened an unterminated string (or swallowed the module body). The correct repo style is a multi-line docstring: line 1 opens, prose inside, `"""` closes before the first import. Caught via `pytest` SyntaxError + per-file `ast.parse` checks.
- **Bundesagentur für Arbeit API**: free JSON API (`X-API-Key: jobboerse-jobsuche`), but it returns **403 from datacenter IPs** — works from residential networks. One search per source entry (query params live in the source URL).
- Nested-quote heredocs via `run_commands` are error-prone; prefer writing a small script file first, then executing it.
- pydantic v2: assigning a plain dict to a model field does **not** validate/convert (`validate_assignment` off) — construct nested models explicitly in fixtures.
- `extract_company_website` only sees **bare** URLs in the description text, not `href="..."` attributes.

## Open Questions
- None blocking Stage 2. For Stage 1: verify the Bundesagentur source from a residential network (403 from datacenter IPs); the initial score threshold (40) and weights (`experience 1.0, prospects 0.6, education 1.2`) are a starting point to be re-tuned after manual analysis of the rejected list.

## Blockers
- None currently; Stage 2 + the shared `src/llm/` foundation can begin at any time.

## Version History
- **Version 1.0**: Initialized from repository context

## Notes
- The ATS substage notes must round-trip through job entry metadata so Stage 2 can pick them back up (per `plan.md`).


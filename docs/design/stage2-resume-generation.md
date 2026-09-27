# Stage 2 Design — Matching Resume Generation

Design plan for **Stage 2** of the Job Finder and Application Pipeline (see `plan.md` at repo root for the source-of-truth blueprint). Reference implementation plan for Milestone 3. Builds on Stage 1 (`./stage1-job-scraping-and-filtering.md`) and the cross-stage contract (`./pipeline-integration.md`) — the accepted queue, SQLite store, config layer, job IDs, metadata registry, and tooling patterns are defined there and reused here.

## Scope

Generate bulletpoints, skills, and summary for the candidate from a job description: minimally edit an existing LaTeX resume, then run an independent ATS-like substage that scores the result and loops until ready. Operates only on `accepted` entries from the Stage 1 queue.

## Architecture

```
Stage 1 (accepted entries in SQLite jobs table)
        │
        ▼
src/resume/ (new package)
  generate:  edit_base_resume(job_entry, candidate, base_latex) → tailored LaTeX
             — edits only bulletpoints/skills/summary sections, human phrasing
             — artifact on disk: data/resumes/<job_id>.tex
  ats:       independent substage: score_resume(job, resume) → (score, feedback notes)
  loop:      generate → ATS score → notes → re-edit … until threshold or cap
        │
        ▼
  resume_ready status in the shared SQLite jobs table (per plan.md: separate queue for clarity)
```

## Confirmed decisions

| # | Decision | Choice | Rationale |
|---|----------|--------|-----------|
| 1 | **LLM backend** | Shared `src/llm/` OpenAI-compatible provider (`complete(system, user, schema=None)`), endpoint/key via `.env` | Stage 2 is inherently generative; one abstraction shared with Stage 3 and Stage 1's `llm` scorer slot (see `./pipeline-integration.md`). |
| 2 | **LaTeX editing** | Section-targeted editing: locate bulletpoints/skills/summary blocks in the base `.tex` by name, regenerate only those | Safest guarantee of the plan.md constraint "only edits minimal and required sections"; full re-generation risks formatting damage. |
| 3 | **ATS loop termination** | Config-driven: `ats_ready_threshold` + `max_iterations` cap; the cap does **not** auto-advance | Prevents infinite loops and makes the loop tunable like Stage 1's match threshold. Auto-advancing an unready resume into Stage 3 would contradict plan.md — see decision 4. |
| 4 | **Cap behavior (`needs_review`)** | On `max_iterations` without meeting the threshold: **stay in `accepted`**, set `metadata.ats.needs_review = true`; a human promotes via `POST /jobs/{id}/resume/force-ready` | Only threshold-met entries advance automatically. Keeps weak resumes out of Stage 3 and keeps the transition map clean. |
| 5 | **Artifact storage** | Tailored LaTeX on disk: `data/resumes/<job_id>.tex` (gitignored), path + iteration count in `metadata.resume` | LaTeX content in a DB blob is awkward to inspect and compile later; disk artifacts keep the store lean. |
| 6 | **ATS scoring backends** | LLM-backed "professional screener / tech hiring manager" + a **deterministic** second signal | Two independent signals; feedback highlights missing keywords and misaligned points, plus a "no generic AI tone" check. |

## Design details

### Entry point (per `./pipeline-integration.md` API surface)
- `POST /jobs/{id}/resume/generate` (`?run_to_completion=true` to run the loop to threshold or cap) — FastAPI route in `app/main.py`.
- Substage-only trigger: `POST /jobs/{id}/resume/ats` runs the ATS scoring substage alone (appends to `metadata.ats`; no generation, no status transition).
- Batch trigger: `POST /stage2/run?limit=N` processes up to N `accepted` entries (incl. `needs_review` re-runs) through the same per-entry code path; `?dry_run=true` reports the selection.
- CLI: `resume generate <id>`, `resume ats <id>`, `resume run [--limit N]` (+ `resume force-ready <id>` for the `needs_review` path).
- Queue selection: `accepted` entries with a resolvable `base_resume_path`, per the stage trigger & queue-selection contract in `./pipeline-integration.md`. Triggering is manual per entry or via explicit batch run (orchestration principle in `./pipeline-integration.md`).

### Generation (`src/resume/generate.py`)
- `edit_base_resume(job, candidate, base_latex) → str` — LLM-edited bulletpoints/skills/summary.
- Edits validated against allowed section markers from `stage2.latex_section_markers` config, with diff-checking so **only permitted sections change**; a diff outside the allowed markers fails the iteration.
- Base resume loaded from `metadata.base_resume_path` (falling back to `base_resume_path` config).
- Human-sounding language enforced via prompt constraints plus the ATS "no generic AI tone" check.
- Output written to `data/resumes/<job_id>.tex`; `metadata.resume = {path, iterations, ready_at}`.

### ATS substage (`src/resume/ats.py`)
- Independent module: `score_resume(job, resume_text) → (score, feedback_notes)`.
- **LLM backend**: prompts a "professional resume screener / tech hiring manager" persona; feedback highlights missing keywords and misaligned bullet points.
- **Deterministic backend**: `score_resume_deterministic(job, resume_text)` extracts keywords from the resume text and reuses Stage 1's **weighting/threshold config machinery** — not `compute_match_score()` itself (a structured candidate profile and free-text resume are different inputs; only the config weights are shared).
- Both backends' results recorded in the iteration entry.

### Loop (`src/resume/loop.py`)
- Per iteration: generate → score → append `{iteration, ats_score, feedback, timestamp}` to `metadata.ats` → read the last entry back to seed the re-edit prompt (this is the round-trip required by `plan.md`).
- Advance to `resume_ready` **only** when `ats_ready_threshold` is met; otherwise continue until `max_iterations`, then set `metadata.ats.needs_review = true` and stop (decision 4).
- The store (`src/queues/store.py`) enforces the transition `accepted → resume_ready` per the map in `./pipeline-integration.md`.

### Tests (`job-pipeline/tests/`)
- Same isolation rules as Stage 1 and the shared contract: mocked `src/llm/` backend from recorded fixtures, temp-dir SQLite via monkey-patched constant, shared `tests/conftest.py` fixtures (sample `JobEntry`, temp DB), API tests via `TestClient`; `pytest -q` green, no live external calls.

## Implementation steps (in order)

1. Prerequisite: shared foundation from `./pipeline-integration.md` (`src/llm/` + config `stage2` section)
2. `src/resume/generate.py` (section-targeted editing + diff validation)
3. `src/resume/ats.py` (LLM + deterministic backends)
4. `src/resume/loop.py` (iteration round-trip, threshold/cap logic, `needs_review`)
5. Entrypoints (API route + CLI subcommands)
6. Tests; README + memory-bank updates; `pytest -q` green

## Risks / notes

- LLM prompts need iteration to consistently produce "human-sounding" output; the ATS feedback loop is the enforcement mechanism.
- Diff validation must tolerate LaTeX section-marker formatting variations; the markers are configurable for exactly this reason.
- The `needs_review` path means some entries stay in `accepted` with a flag — tooling must surface it (the `GET /jobs/{id}` payload includes `metadata.ats`).


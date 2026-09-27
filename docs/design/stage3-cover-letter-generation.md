# Stage 3 Design — Matching Cover Letter Generation

Design plan for **Stage 3** of the Job Finder and Application Pipeline (see `plan.md` at repo root for the source-of-truth blueprint). Reference implementation plan for Milestone 4. Builds on Stage 2 (`./stage2-resume-generation.md`) and the cross-stage contract (`./pipeline-integration.md`).

## Scope

Research the company/department/hiring manager, then generate a company- and job-specific cover letter for entries that reached `resume_ready` in Stage 2. The cover letter follows the fixed repeatable narrative pattern, is consistent across runs, and does not sound generic.

## Architecture

```
Stage 2 (resume_ready entries in SQLite jobs table)
        │
        ▼
src/coverletter/ (new package)
  research:  collect company/department/hiring-manager context (modular providers)
             — results cached in metadata.research (capped)
  generate:  fixed narrative pattern (Story Hook → Background → Experience → Skills
             → Story → Fitment → Interest → Closing), consistent across runs
             — artifact on disk: data/coverletters/<job_id>.md
        │
        ▼
  status unchanged (stays resume_ready; Stage 4's send is the only transition to sent)
```

## Confirmed decisions

| # | Decision | Choice | Rationale |
|---|----------|--------|-----------|
| 1 | **LLM backend** | Shared `src/llm/` OpenAI-compatible provider; controlled temperature for run-to-run consistency | Stage 3 is generative; one shared abstraction (see `./pipeline-integration.md`). |
| 2 | **Company research** | Modular research backend behind a `Researcher` protocol: Tavily (extensive web-search snippets) now → Zyte spider in future → DuckDuckGo/firecrawl as fallback chain | Tavily is LLM-oriented with a generous free tier and clean snippets; the provider chain keeps the backend swappable. |
| 3 | **Research degradation** | Graceful: when no provider or key is configured, generation proceeds with resume-only context and records `research_degraded: true` in `metadata.research` | The pipeline must not block on external credentials; quality degrades instead of failing. |
| 4 | **Output format** | Plain text + Markdown now; PDF via LaTeX compilation only if a target board requires it later | Cover letters are typically pasted into web forms; text is universally acceptable. |
| 5 | **Narrative pattern** | Fixed 8-part pattern via a strict sectioned template + `stage3.story_context` config | Guarantees consistency across runs and jobs, per plan.md's "repeatable pattern" requirement. |
| 6 | **Artifact storage** | Cover letter on disk: `data/coverletters/<job_id>.md` (gitignored), path + timestamp in `metadata.coverletter` | Consistent with Stage 2's artifact-on-disk decision; keeps the store lean. |
| 7 | **Status effect** | Generating a cover letter does **not** change status (entry stays `resume_ready`) | Stage 4's send is the only transition to `sent`; keeps the transition map in `./pipeline-integration.md` clean. |

## Design details

### Entry point (per `./pipeline-integration.md` API surface)
- `POST /jobs/{id}/coverletter/generate` — FastAPI route in `app/main.py`.
- Substage-only trigger: `POST /jobs/{id}/research` runs the research substage alone (refreshes `metadata.research`; no generation, no status change).
- Batch trigger: `POST /stage3/run?limit=N` processes up to N `resume_ready` entries whose `metadata.resume.path` exists on disk; `?dry_run=true` reports the selection.
- CLI: `coverletter generate <id>`, `coverletter research <id>`, `coverletter run [--limit N]`.
- Queue selection: `resume_ready` entries with a resume artifact on disk, per the stage trigger & queue-selection contract in `./pipeline-integration.md`. Triggering is manual per entry or via explicit batch run (orchestration principle in `./pipeline-integration.md`).

### Research (`src/coverletter/research.py`)
- Modular provider chain behind a `Researcher` protocol: `TavilyResearcher` now → `ZyteSpider` in future → `DuckDuckGoResearcher` / `FirecrawlResearcher` fallbacks.
- A new provider is one class plus one registry entry; the chain order comes from `stage3.research_providers` config.
- Research targets: the company, the department of the job, the hiring manager, and any public social/press context — feeding the Story Hook and Fitment sections.
- Results cached in `metadata.research` (most recent 10 snippets per provider); graceful degradation per decision 3 (`research_degraded: true` when no provider/key is available).
- Provider keys via `.env`; the chain must degrade gracefully when keys are absent (never raise to the caller).

### Generation (`src/coverletter/generate.py`)
- Fixed 8-part narrative pattern: Story Hook → Candidate Background → Candidate Experience → Candidate Skills → Candidate Story → Candidate Fitment → Candidate Interest → Closing.
- Inputs: the `resume_ready` entry, its tailored resume (from `metadata.resume.path`), research context (from `metadata.research`), and `stage3.story_context` config (additional candidate story resources, per plan.md).
- Story hooks and strong points are drawn from the resume and overall candidate experience.
- Consistency across runs: strict sectioned template + controlled temperature via the shared `src/llm/` provider; job- and company-specific output; no generic AI tone (prompt constraints; Stage 2's ATS-style tone check does not apply here, so the template and temperature are the enforcement mechanisms).
- Format: plain text + Markdown (decision 4); written to `data/coverletters/<job_id>.md`; `metadata.coverletter = {path, generated_at}`.
- Status is unchanged (stays `resume_ready`, decision 7).

### Tests (`job-pipeline/tests/`)
- Same isolation rules as the shared contract: mocked `Researcher` and `src/llm/` backends from recorded fixtures (including a no-provider degradation case), temp-dir SQLite via monkey-patched constant, shared `tests/conftest.py` fixtures, API tests via `TestClient`; `pytest -q` green, no live external calls.

## Implementation steps (in order)

1. Prerequisite: shared foundation (`src/llm/` + `stage3` config section) and Stage 2
2. `src/coverletter/research.py` (`Researcher` protocol + provider chain + caching + degradation)
3. `src/coverletter/generate.py` (fixed narrative template + LLM generation + artifact write)
4. Entrypoints (API route + CLI subcommand)
5. Tests; README + memory-bank updates; `pytest -q` green

## Risks / notes

- Tavily/Zyte credentials are provided via `.env`; the chain must degrade gracefully when keys are absent.
- The fixed narrative pattern risks sounding templated if section transitions are rigid — the LLM prompt must vary phrasing per job/company while keeping the section order fixed.
- Research snippets can be stale or wrong; the design treats them as context, never as verified facts stated in the letter.


# Pipeline Integration — Cross-Stage Contract

This document is the **single integration contract** for all 4 stages of the Job Finder and Application Pipeline. It was produced by a design review of each stage individually and the pipeline as a whole (`plan.md` at repo root is the source-of-truth blueprint). Every stage design (`./stage1-job-scraping-and-filtering.md`, `./stage2-resume-generation.md`, `./stage3-cover-letter-generation.md`, `./stage4-candidate-delivery.md`) defers to this document wherever stages touch shared state.

## Core principle: the store is the only cross-stage contract

**Stage packages never import each other.** Stages communicate exclusively through:

1. the SQLite `jobs` table (one row per job entry),
2. the documented **metadata key registry** (below), and
3. the **status transition map** (below).

This is what keeps each stage independently testable and replaceable, and it is why the following shared definitions are fixed **before** Stage 1 implementation begins.

## Shared foundation (serves all stages)

### `src/llm/` — OpenAI-compatible provider abstraction

- Single abstraction used by Stage 1's pluggable `llm` scorer slot and Stages 2–3 generation: `complete(system, user, schema=None)` with JSON-mode support.
- Provider/endpoint/key/model from config + `.env`; retry/timeout handling.
- Mockable backend so tests run without network; no live external calls in CI.
- Stage 1 ships only the `llm` **slot stub** in its scorer registry; the stub consumes `src/llm/` once this shared foundation lands (interface fixed here so the seam never gets rewritten).

### One config file from day one (`config/pipeline.example.json` → `src/config.py`)

A single pydantic-validated `PipelineConfig` with nested sections, shipped as **one** example file. Stage 2–4 keys are present (empty/defaults) from the start so later stages never change the config format:

```json
{
  "sources":              [{ "name": "...", "type": "api|html", "url": "...", "enabled": true }],
  "search_keywords":      ["..."],
  "matching":             { "score_weights": { "experience": 1.0, "prospects": 1.0, "education": 1.0 }, "match_threshold": 70 },
  "candidate_profile":    { "skills": [], "experience": [], "education": [] },
  "base_resume_path":     "path/to/base.tex",
  "stage2":               { "ats_ready_threshold": 80, "max_iterations": 5, "latex_section_markers": {} },
  "stage3":               { "research_providers": [], "story_context": {}, "narrative_pattern": "..." },
  "stage4":               { "messaging": {}, "message_template": "..." }
}
```

`.env`/python-dotenv overrides for secrets (LLM key, Telegram token/chat id, research provider keys). Dependency set unchanged (JSON config, no `pyyaml`).

## Status model

### `JobStatus` enum (forward-complete from day one)

Defined **once** in `src/models.py`. Stage 1 only *uses* `new`, `accepted`, `rejected`; the enum is complete from day one so later stages never force a schema/enum migration:

| Status | Meaning | Owner |
|--------|---------|-------|
| `new` | Ingested and scored; awaiting human accept/reject | Stage 1 |
| `accepted` | Accepted by human (or auto-accepted ≥ threshold per Stage 1 config); eligible for Stage 2 | Stage 1 |
| `rejected` | Rejected by pipeline scoring or by human | Stage 1 |
| `resume_ready` | ATS loop met `ats_ready_threshold`; eligible for Stage 3 | Stage 2 |
| `sent` | Delivery package sent to the candidate (terminal pipeline state) | Stage 4 |

`applied` / `not_applied` is **not** a queue status: the candidate records it in `metadata.application` (see registry). This keeps "sent" the only pipeline-owned terminal state and avoids growing the status enum with candidate-controlled values.

### Status transition map (enforced in `store.update_status`)

```
new ──▶ accepted ──▶ resume_ready ──▶ sent
 │  ▲                                   (terminal)
 └──┼──▶ rejected
    └───────┘  (rejected ──▶ accepted via manual accept)
```

- `new → accepted` (auto on score ≥ threshold, per Stage 1 config) and `new → rejected` (auto below threshold)
- `rejected → accepted` (manual accept via CLI/API) — allowed
- `accepted → rejected` (manual reject) — allowed **only while pre-`resume_ready`**
- `accepted → resume_ready` — Stage 2 ATS loop only (threshold met; see the Stage 2 doc for the `needs_review` path)
- `resume_ready → sent` — Stage 4 send only
- Any other transition (e.g., `sent → rejected`, `resume_ready → accepted`) is invalid and refused.

### Stable job ID

Defined **once**, used by dedupe, CLI, API routes, artifact file naming, and delivery tracking:

```
id = sha256(f"{title}|{company_name}|{source}").hexdigest()[:12]
```

Stored as the `jobs` table primary key. Re-ingest of an existing `(title, company, source)` **updates** the row (idempotent), never duplicates it.

## Metadata key registry

The `JobEntry.metadata` dict is the per-job scratch space. Keys are **extended, never repurposed**:

| Key | Set by | Contents |
|-----|--------|----------|
| `score`, `score_breakdown` | Stage 1 | Match score + per-factor breakdown (enables manual score re-tuning) |
| `base_resume_path` | Config/Stage 1 | Pre-configured base LaTeX resume path |
| `notes` | Stage 1 CLI/API | **Human** notes (candidate + human reviewer) |
| `ats` | Stage 2 | List of `{iteration, ats_score, feedback, timestamp}`; also `needs_review: true` when the loop caps out below threshold |
| `resume` | Stage 2 | `{path, iterations, ready_at}` for the tailored LaTeX on disk |
| `research` | Stage 3 | Cached company/department/hiring-manager research (capped: most recent 10 snippets per provider) |
| `coverletter` | Stage 3 | `{path, generated_at}` for the cover letter on disk |
| `delivery` | Stage 4 | `{message_ids: [...], sent_at}` for idempotency + audit |
| `application` | Stage 4 (candidate) | `{applied: bool, notes: str, updated_at}` — candidate-applied state + notes |

## Unified API surface

One canonical `jobs` resource in `app/main.py` — **no separate `/sent` resource** (sent is a status of the same rows):

| Route | Stage |
|-------|-------|
| `POST /ingest` | 1 — full flow: fetch → parse → score → queue |
| `GET /jobs?status=...` | all — replaces `GET /queue/{status}` and `GET /sent` |
| `GET /jobs/{id}` | all — replaces `GET /queue/entry/{id}` |
| `POST /jobs/{id}/accept` \| `POST /jobs/{id}/reject` \| `POST /jobs/{id}/note` | 1 |
| `POST /jobs/{id}/resume/generate` (`?run_to_completion=true`) | 2 |
| `POST /jobs/{id}/resume/force-ready` | 2 — human decision for `needs_review` entries |
| `POST /jobs/{id}/coverletter/generate` | 3 |
| `POST /jobs/{id}/send` (`?force=true`) | 4 |
| `POST /jobs/{id}/application-status` (applied/not-applied + notes) | 4 |

CLI subcommands mirror the routes under `python -m src.queues.cli` (Stage 1) and per-stage CLIs (Stages 2–4 docs).

## Data layout

All artifacts live under `job-pipeline/data/` (gitignored — add `data/` to `.gitignore` in the Stage 1 wrap-up; the current `.gitignore` lacks it):

```
job-pipeline/data/
├── queues.db                  # SQLite jobs store (single cross-stage store)
├── resumes/<job_id>.tex       # Stage 2 tailored LaTeX
└── coverletters/<job_id>.md   # Stage 3 cover letter (plain text + Markdown)
```

## Orchestration: deliberately manual

Nothing auto-runs Stage 2 after acceptance. **Every status transition and stage action is human/API-triggered**, matching the review-oriented, single-candidate scope. A batch runner (e.g., "process all accepted") may be added later as a convenience, but it is not part of the core design.

## Testing contract (all stages)

- `tests/conftest.py` with shared fixtures: temp-dir SQLite path (monkey-patched `store` module constant, matching the existing isolated-tests pattern), sample `JobEntry`, mocked LLM/research/HTTP backends from recorded fixtures.
- No live network in tests; CI stays green and network-independent.
- API tests via `TestClient`; run everything from `job-pipeline/`: `pytest -q`.

## Dependencies note

`pandas` stays in `requirements.txt` reserved for Stage 1 queue reporting; no other stage depends on it. Dependencies remain unpinned (no lockfile) per the existing decision.



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

One canonical `jobs` resource in `app/main.py` — **no separate `/sent` resource** (sent is a status of the same rows). Routes fall into five groups: **read/status**, **per-entry actions**, **substage-only triggers**, **generic entry edit**, and **batch stage runs**.

### Read / status (shared admin surface, shipped with Stage 1)

| Route | Purpose |
|-------|---------|
| `GET /status` | Pipeline-wide summary: counts per status, per-stage progress (e.g., Stage 2: in-flight `accepted`, done `resume_ready`, `needs_review` flagged), aggregate flags (`metadata.ats.needs_review`, `metadata.research.research_degraded`) |
| `GET /jobs?status=...` | List one queue — replaces `GET /queue/{status}` and `GET /sent` |
| `GET /jobs/{id}` | Full entry (all fields + metadata) — replaces `GET /queue/entry/{id}` |

### Per-entry actions (owned by the stage that performs the transition)

| Route | Stage |
|-------|-------|
| `POST /ingest` | 1 — full flow: fetch → parse → score → queue |
| `POST /jobs/{id}/accept` \| `POST /jobs/{id}/reject` \| `POST /jobs/{id}/note` | 1 |
| `POST /jobs/{id}/resume/generate` (`?run_to_completion=true`) | 2 |
| `POST /jobs/{id}/resume/force-ready` | 2 — human decision for `needs_review` entries |
| `POST /jobs/{id}/coverletter/generate` | 3 |
| `POST /jobs/{id}/send` (`?force=true`) | 4 |
| `POST /jobs/{id}/application-status` (applied/not-applied + notes) | 4 |

### Substage-only triggers (see Substage modularity contract)

| Route | Stage / substage |
|-------|------------------|
| `POST /jobs/{id}/resume/ats` | 2 — ATS scoring only (appends to `metadata.ats`; no generation, no transition) |
| `POST /jobs/{id}/research` | 3 — research only (refreshes `metadata.research`; no generation, no transition) |
| `GET /jobs/{id}/delivery/preview` | 4 — compile only (returns the message parts; no send, no transition) |

### Generic entry edit (admin/misc)

| Route | Purpose |
|-------|---------|
| `PATCH /jobs/{id}` | Edit human-owned fields without triggering a stage: `title`, `company_name`, `company_website`, `contact`, `source_url`, `notes`, and human-owned metadata keys (`base_resume_path`, `notes`). Guardrails: `id` and `status` are **never** edited here (status changes only via the transition endpoints above); stage-owned registry keys (`score`, `score_breakdown`, `ats`, `resume`, `research`, `coverletter`, `delivery`, `application`) are rejected — only the owning stage's code path may write them. |

### Batch stage runs (each stage triggers independently over its queue)

| Route | Stage | Selects |
|-------|-------|---------|
| `POST /stage1/run` | 1 | All enabled `sources` from config (one ingest round) |
| `POST /stage2/run?limit=N` | 2 | Up to N `accepted` entries (incl. `needs_review` re-runs) |
| `POST /stage3/run?limit=N` | 3 | Up to N `resume_ready` entries with `metadata.resume.path` on disk |
| `POST /stage4/run?limit=N` | 4 | Up to N `resume_ready` entries with resume + cover-letter artifacts on disk |

Batch runs call the **same per-entry functions** as the per-entry routes (one code path, two entrypoints) and accept `?dry_run=true` to report what *would* be processed. Batch runs are still human-triggered — see Orchestration.

CLI subcommands mirror all five groups: `python -m src.queues.cli` (Stage 1 + the shared admin surface: `status`, `view <status>`, `show <id>`, `edit <id>`) and per-stage CLIs (Stages 2–4 docs), including substage subcommands (`resume ats <id>`, `coverletter research <id>`, `send preview <id>`) and a `run` batch subcommand per stage.

## Stage trigger & queue-selection contract

Every stage is independently triggerable and selects its work from the shared SQLite `jobs` table **only by status filter + registered preconditions** — never by importing another stage:

| Stage | Package | Input queue (status filter) | Preconditions (beyond status) | Per-entry trigger | Batch trigger | Transition on success |
|-------|---------|------------------------------|-------------------------------|-------------------|---------------|------------------------|
| 1 | `src/ingestion` + `src/parsing` + `src/matching` | — (creates/updates rows itself) | — | `POST /ingest` | `POST /stage1/run` | `new → accepted/rejected` (score-driven) |
| 2 | `src/resume` | `accepted` | `metadata.base_resume_path` or `base_resume_path` config resolvable | `POST /jobs/{id}/resume/generate` | `POST /stage2/run` | `accepted → resume_ready` (threshold met) or `metadata.ats.needs_review` (cap) |
| 3 | `src/coverletter` | `resume_ready` | `metadata.resume.path` exists on disk | `POST /jobs/{id}/coverletter/generate` | `POST /stage3/run` | none (stays `resume_ready`) |
| 4 | `src/outreach` | `resume_ready` | `metadata.resume.path` + `metadata.coverletter.path` exist on disk | `POST /jobs/{id}/send` | `POST /stage4/run` | `resume_ready → sent` |

Rules:

1. A stage's queue selection is `status ∈ input queue` **AND** all preconditions; entries failing preconditions are skipped and reported in the run result, never crashed on.
2. Stages never filter on another stage's metadata beyond the registry keys listed in this table.
3. A stage is "triggerable" iff its row here is implemented as API routes in `app/main.py` plus mirrored CLI subcommands (per-entry + batch + substage-only).
4. Adding a precondition requires registering its metadata key in the registry below **first** — the table and registry move together.

## Observability & admin tooling (status API + UI)

- **`GET /status`** (shipped with Stage 1, kept current by all stages): `{ "queues": { "new": n, "accepted": n, "rejected": n, "resume_ready": n, "sent": n }, "stages": { "stage2": { "in_flight": n, "needs_review": n }, "stage3": { "degraded_research": n }, "stage4": { "sent": n, "applied": n } } }`. Derived purely from status counts + registry keys — no stage-specific queries; each stage keeps it correct simply by writing its registered metadata.
- **Admin UI**: a single static page (`app/static/index.html`, vanilla JS + `fetch`, **no new dependencies** — no Jinja2, no frontend framework) served at `GET /ui`. It is a thin client over the API only: queue tabs with counts from `GET /status`, entry list per queue (`GET /jobs?status=...`), entry detail with full metadata (`GET /jobs/{id}`), action buttons mapping 1:1 to the API routes (accept / reject / note / generate / force-ready / send / application-status), and an edit form backed by `PATCH /jobs/{id}`. The UI owns no logic — anything it can do must exist as an API route first.
- **CLI parity**: `python -m src.queues.cli status | view <status> | show <id> | edit <id>` for headless use of the same surface.

## Substage modularity contract

Stages are packages; **substages are modules within a stage package**. A substage:

1. Is one module with **one public primary function** (e.g., `src/resume/ats.py` → `score_resume`, `src/coverletter/research.py` → `collect_research`, `src/outreach/compile.py` → `compile_message`).
2. Owns exactly one registered metadata key (or appends to one list-shaped key) and writes nothing outside it.
3. Can be triggered independently via its own subroute + CLI subcommand (see Substage-only triggers above). Running a substage never transitions status unless that substage owns the transition (Stage 4 `send` owns `resume_ready → sent`; ATS scoring does not).
4. Never imports another stage's package — only the shared foundation (`src/models`, `src/config`, `src/queues/store`, `src/llm`) and its own stage package.

**When to break a stage into substages:** whenever a stage has ≥ 2 independently useful operations or independent external dependencies (network providers, artifacts, messaging). Current decomposition:

| Stage | Substages (module → primary function) |
|-------|----------------------------------------|
| 1 | `ingestion/ingest.py → fetch_from_source` (per-source fetcher plugins), `parsing/parse.py → parse_job_listing`, `matching/match.py → compute_match_score` |
| 2 | `resume/generate.py → edit_base_resume`, `resume/ats.py → score_resume`, `resume/loop.py → run_loop` (orchestrates the two; the only Stage 2 place allowed to transition status) |
| 3 | `coverletter/research.py → collect_research` (provider chain), `coverletter/generate.py → generate_coverletter` |
| 4 | `outreach/compile.py → compile_message`, `outreach/send.py → TelegramSender.send` (owns the transition), `outreach/track.py → record_application_status` |

This makes every substage unit-testable in isolation and every stage replaceable without touching the others.

## Data layout

All artifacts live under `job-pipeline/data/` (gitignored — add `data/` to `.gitignore` in the Stage 1 wrap-up; the current `.gitignore` lacks it):

```
job-pipeline/data/
├── queues.db                  # SQLite jobs store (single cross-stage store)
├── resumes/<job_id>.tex       # Stage 2 tailored LaTeX
└── coverletters/<job_id>.md   # Stage 3 cover letter (plain text + Markdown)
```

## Orchestration: deliberately manual

Nothing auto-runs Stage 2 after acceptance. **Every status transition and stage action is human/API-triggered**, matching the review-oriented, single-candidate scope. The batch triggers above make each stage independently runnable over its whole queue, but a batch run is still an explicit human action (one API call or one CLI command) — there are no schedulers, cron jobs, watchers, or auto-advancing loops anywhere in the pipeline.

## Testing contract (all stages)

- `tests/conftest.py` with shared fixtures: temp-dir SQLite path (monkey-patched `store` module constant, matching the existing isolated-tests pattern), sample `JobEntry`, mocked LLM/research/HTTP backends from recorded fixtures.
- No live network in tests; CI stays green and network-independent.
- API tests via `TestClient`; run everything from `job-pipeline/`: `pytest -q`.

## Dependencies note

`pandas` stays in `requirements.txt` reserved for Stage 1 queue reporting; no other stage depends on it. Dependencies remain unpinned (no lockfile) per the existing decision.



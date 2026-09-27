# Stage 1 Design — Job Scraping and Filtering

Design plan for **Stage 1** of the Job Finder and Application Pipeline (see `plan.md` at repo root for the source-of-truth blueprint). This document was agreed in planning and is the reference implementation plan for Milestone 2 / Stage 1.

**Integration note:** the cross-stage contract (`./pipeline-integration.md`) defines the shared `JobStatus` enum, stable job ID scheme, metadata key registry, status transition map, unified API surface, and data layout referenced throughout this document. Stages 2–4 reuse everything defined here.

## Scope

Collect job postings from job boards (config-driven keywords), normalize them into a validated job entry, compute a configurable match score against the candidate profile, and maintain accepted/rejected queues in persistent storage with interactive tooling.

## Architecture

```
Config (JSON + .env)               Candidate profile, keywords, sources, score weights, threshold
        │
        ▼
src/ingestion/ingest.py            fetch_from_source(source_config) — per-source fetcher
        │                          (dispatch table keyed by source type: api | html)
        ▼
src/parsing/parse.py               parse_job_listing() — normalize to pydantic JobEntry model:
        │                          title, description, company_name, company_website,
        │                          contact info, source_url, metadata{base_resume_path, notes}
        ▼
src/matching/match.py              compute_match_score(candidate, job) → weighted score (0–100)
        │                          factors: experience overlap, future prospects, education correlation
        │                          + match_candidate_to_job() → score ≥ threshold
        ▼
src/queues/ (new package)          Persistent accepted/ and rejected/ queues (SQLite)
        │
        ▼
Interactive tooling                CLI (`python -m src.queues.cli`) + FastAPI routes
                                   (view accepted / view rejected / accept a rejected job)
```

## Confirmed decisions

| # | Decision | Choice | Rationale |
|---|----------|--------|-----------|
| 1 | **Job sources** | JSON-API boards first (Remotive, RemoteOK, etc.) + per-source fetcher plugin pattern with an HTML-scraper stub for later | JSON APIs need no new scraping dependencies, are far more reliable than HTML scraping, and `httpx` already covers them. HTML scraping (Indeed, Dice, LinkedIn) would require adding `beautifulsoup4`/`lxml` and more maintenance; the plugin seam keeps that path open. |
| 2 | **Queue persistence** | SQLite via stdlib `sqlite3` | Queryable, transactional, no new dependencies; JSON files get unwieldy once queues grow and need in-place status updates. pandas stays available for reporting. |
| 3 | **Match scoring** | Deterministic config-weighted keyword scoring now; LLM scorer as a pluggable backend later | Keeps Stage 1 fully testable and offline-friendly. The weights/threshold live in config so the score can be re-tuned after manual analysis of the rejected list, per `plan.md`. |
| 4 | **Interactive tooling** | Both: CLI (`python -m src.queues.cli`) and FastAPI routes | `plan.md` asks for proper interactive tooling; the CLI is the cheapest robust option, and API routes keep parity with the existing Stage-1 entrypoint pattern in `app/main.py`. |
| 5 | **Config format** | JSON config file with pydantic validation + `.env` overrides via python-dotenv | Keeps the dependency set unchanged (no `pyyaml`); separates human-tunable knobs (keywords, weights, threshold) from code. |

## Confirmed design details

### Config layer (`config/pipeline.example.json` + `src/config.py`)
- Pydantic-validated settings loaded from a config file, with `.env`/python-dotenv overrides.
- One `PipelineConfig` shape from day one (`./pipeline-integration.md`): this stage defines and ships the full example file with `stage2`/`stage3`/`stage4` sections present (empty/defaults) so later stages never change the config format.
- Stage 1 sections: `sources` (list of `{name, type: api|html, url, enabled}`), `search_keywords`, `matching` (`score_weights` for experience/prospects/education + `match_threshold`), `candidate_profile` (skills, experience entries, education), `base_resume_path`.

### Domain models (`src/models.py`)
- Pydantic `JobEntry`: `id`, `title`, `description`, `company_name`, `company_website`, `contact_info`, `source_url`, `source`, `status`, `metadata`.
- `status` is the **forward-complete `JobStatus` enum** defined once in `src/models.py` (`new`, `accepted`, `rejected`, `resume_ready`, `sent`) — Stage 1 only *uses* the first three, but the enum ships complete so Stages 2–4 never force a schema/enum migration (`./pipeline-integration.md`). Applied/not-applied is **not** a status — the candidate records it in `metadata.application`.
- Stable job **ID**: `sha256(f"{title}|{company_name}|{source}").hexdigest()[:12]`, the store's primary key and the handle for CLI, API routes, and later artifact file naming.
- `metadata` follows the **key registry** in `./pipeline-integration.md` — Stage 1 sets `score`, `score_breakdown`, `base_resume_path`, `notes` (human notes). Keys are extended, never repurposed, by later stages.
- The per-factor score breakdown is what enables the manual score re-tuning loop described in `plan.md`.

### Ingestion (`src/ingestion/ingest.py`)
- Existing `fetch_job_listings(source_url)` placeholder signature and behavior are preserved (current tests assert them); the real flow goes through a new `fetch_from_source(source_config) -> list[dict]`.
- Dispatch table keyed by source type: `RemotiveFetcher`, `RemoteOKFetcher` (JSON-API), and `HtmlFetcherStub` (raises `NotImplementedError` with a clear message) — all sharing a `Fetcher` protocol so a new source is one class plus one registry entry.
- Deduplication by (title, company, source) → the stable job ID above; re-ingest **updates** existing entries, never duplicates them.

### Parsing (`src/parsing/parse.py`)
- `parse_job_listing()` becomes a real normalizer: raw source dict → validated `JobEntry` (with the derived ID), with per-source field mapping and safe fallbacks for missing contact details (JSON-API boards often omit contact emails).

### Matching (`src/matching/match.py`)
- `compute_match_score(candidate_profile, job) -> (score, breakdown)`: weighted keyword-overlap for **experience**, future-prospects signal (title seniority + a configurable in-demand tech list), and education correlation — all weights and the threshold from `matching` config.
- `match_candidate_to_job()` returns `score >= threshold` while keeping its bool signature.
- Scorer backend registry: `deterministic` (default) with an `llm` slot stub, per decision #3. The `llm` slot consumes the shared `src/llm/` provider (`complete(system, user, schema=None)`) once the shared foundation lands — its interface is fixed in `./pipeline-integration.md` so the seam is never rewritten.

### Queue store (`src/queues/store.py`)
- SQLite `jobs` table at `job-pipeline/data/queues.db` (auto-created, gitignored) — the **single cross-stage store**; stages never import each other, they communicate only through this table plus the metadata registry and status transitions (`./pipeline-integration.md`).
- Operations: `save`, `list_by_status`, `get`, `update_status_and_notes`.
- Entries stored as JSON blobs plus indexed columns (`status`, `score`, `created_at`) for querying; `id` (stable job ID) is the primary key.
- `update_status` enforces the **status transition map** (`./pipeline-integration.md`): `new → accepted/rejected`, `rejected → accepted` (manual accept), `accepted → rejected` only pre-`resume_ready`; `accepted → resume_ready` and `resume_ready → sent` belong to Stages 2 and 4 respectively.
- Idempotent re-ingest: existing entries are updated, not duplicated.

### Interactive tooling
- CLI subcommands: `view-accepted`, `view-rejected`, `accept <id>`, `reject <id>`, `note <id> <text>`; plus the shared admin surface Stage 1 ships for all stages: `status`, `view <status>`, `show <id>`, `edit <id>`, and the batch `run`.
- FastAPI routes in `app/main.py` per the **unified API surface** in `./pipeline-integration.md`: `POST /ingest` upgraded to run the full Stage-1 flow (fetch → parse → score → queue), plus `GET /jobs?status=...`, `GET /jobs/{id}`, `POST /jobs/{id}/accept` | `reject` | `note`, and the shared admin surface Stage 1 owns: `GET /status`, `PATCH /jobs/{id}`, batch `POST /stage1/run`, and the static admin UI served at `GET /ui`. Stages 2–4 extend the same `jobs` resource (no parallel resources).
- Independent triggering: Stage 1 has no input queue — it creates/updates rows itself via `POST /ingest` (single source) or `POST /stage1/run` (all enabled sources), per the stage trigger & queue-selection contract in `./pipeline-integration.md`.

### Tests (`job-pipeline/tests/`)
- Scorer unit tests (weights/threshold from a test config), parser normalization tests with fixture payloads per source, store tests against a temp-dir SQLite DB (monkey-patched constant, matching the existing isolated-tests pattern), CLI tests, API tests via `TestClient`.
- Fetchers tested from recorded JSON fixtures — no live network in tests; CI stays green and network-independent.
- Shared `tests/conftest.py` fixtures (sample `JobEntry`, temp DB path) introduced here and reused by Stages 2–4 per the testing contract in `./pipeline-integration.md`.

## Implementation steps (in order)

1. Config layer (`config/pipeline.example.json` — full shape per `./pipeline-integration.md` — + `src/config.py`)
2. Domain models (`src/models.py`: forward-complete `JobStatus`, stable ID, metadata registry)
3. Ingestion dispatch + fetchers (`src/ingestion/ingest.py`)
4. Parsing/normalization (`src/parsing/parse.py`)
5. Matching/scoring (`src/matching/match.py`)
6. Queue store with transition enforcement (`src/queues/store.py`)
7. Interactive tooling (CLI + unified FastAPI routes)
8. Shared test fixtures (`tests/conftest.py`) + tests
9. Wrap-up: `.gitignore` for `data/` and real config, README and memory-bank updates, `pytest -q` green

## Risks / notes

- Remotive/RemoteOK JSON shapes are to be verified against live responses before the field mappings are finalized.
- The HTML fetcher stub is intentionally non-functional — it exists purely as the plugin seam for later HTML scraping.
- `fetch_job_listings()` placeholder behavior is preserved so existing tests keep passing.
- `pandas` stays in `requirements.txt` reserved for queue reporting (see `./pipeline-integration.md`, Dependencies note).

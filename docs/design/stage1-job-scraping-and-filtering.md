# Stage 1 Design — Job Scraping and Filtering

Design plan for **Stage 1** of the Job Finder and Application Pipeline (see `plan.md` at repo root for the source-of-truth blueprint). This document was agreed in planning and is the reference implementation plan for Milestone 2 / Stage 1.

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
- Contains: `sources` (list of `{name, type: api|html, url, enabled}`), `search_keywords`, `score_weights` (experience / prospects / education), `match_threshold`, `candidate_profile` (skills, experience entries, education), `base_resume_path`.

### Domain models (`src/models.py`)
- Pydantic `JobEntry`: `title`, `description`, `company_name`, `company_website`, `contact_info`, `source_url`, `source`, `status` (`accepted`/`rejected`), `metadata` (`base_resume_path`, `notes`, `score`, `score_breakdown`, `created_at`, `updated_at`).
- The per-factor score breakdown is what enables the manual score re-tuning loop described in `plan.md`.

### Ingestion (`src/ingestion/ingest.py`)
- Existing `fetch_job_listings(source_url)` placeholder signature and behavior are preserved (current tests assert them); the real flow goes through a new `fetch_from_source(source_config) -> list[dict]`.
- Dispatch table keyed by source type: `RemotiveFetcher`, `RemoteOKFetcher` (JSON-API), and `HtmlFetcherStub` (raises `NotImplementedError` with a clear message) — all sharing a `Fetcher` protocol so a new source is one class plus one registry entry.
- Deduplication by (title, company, source).

### Parsing (`src/parsing/parse.py`)
- `parse_job_listing()` becomes a real normalizer: raw source dict → validated `JobEntry`, with per-source field mapping and safe fallbacks for missing contact details.

### Matching (`src/matching/match.py`)
- `compute_match_score(candidate_profile, job) -> (score, breakdown)`: weighted keyword-overlap for **experience**, future-prospects signal (title seniority + a configurable in-demand tech list), and education correlation — all weights and the threshold from config.
- `match_candidate_to_job()` returns `score >= threshold` while keeping its bool signature.
- Scorer backend registry: `deterministic` (default) with an `llm` slot stub, per decision #3.

### Queue store (`src/queues/store.py`)
- SQLite database at `job-pipeline/data/queues.db` (auto-created, gitignored).
- Operations: `save`, `list_by_status`, `get`, `update_status_and_notes`.
- Entries stored as JSON blobs plus indexed columns (`status`, `score`, `created_at`) for querying.
- Idempotent re-ingest: existing entries are updated, not duplicated.

### Interactive tooling
- CLI subcommands: `view-accepted`, `view-rejected`, `accept <id>`, `reject <id>`, `note <id> <text>`.
- FastAPI routes in `app/main.py`: `POST /ingest` upgraded to run the full Stage-1 flow (fetch → parse → score → queue), plus `GET /queue/{status}`, `GET /queue/entry/{id}`, `POST /queue/entry/{id}/accept`.

### Tests (`job-pipeline/tests/`)
- Scorer unit tests (weights/threshold from a test config), parser normalization tests with fixture payloads per source, store tests against a temp-dir SQLite DB (monkey-patched constant, matching the existing isolated-tests pattern), CLI tests, API tests via `TestClient`.
- Fetchers tested from recorded JSON fixtures — no live network in tests; CI stays green and network-independent.

## Implementation steps (in order)

1. Config layer (`config/pipeline.example.json` + `src/config.py`)
2. Domain models (`src/models.py`)
3. Ingestion dispatch + fetchers (`src/ingestion/ingest.py`)
4. Parsing/normalization (`src/parsing/parse.py`)
5. Matching/scoring (`src/matching/match.py`)
6. Queue store (`src/queues/store.py`)
7. Interactive tooling (CLI + FastAPI routes)
8. Tests
9. Wrap-up: `.gitignore` for `data/` and real config, README and memory-bank updates, `pytest -q` green

## Risks / notes

- Remotive/RemoteOK JSON shapes are to be verified against live responses before the field mappings are finalized.
- The HTML fetcher stub is intentionally non-functional — it exists purely as the plugin seam for later HTML scraping.
- `fetch_job_listings()` placeholder behavior is preserved so existing tests keep passing.

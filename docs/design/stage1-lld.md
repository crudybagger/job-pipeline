# Stage 1 — Low-Level Design (LLD)

Low-level design for **Stage 1 — Job Scraping and Filtering**. Implements the HLD in
`./stage1-job-scraping-and-filtering.md` under the cross-stage contract
`./pipeline-integration.md`. This document is the implementation reference for Stage 1
(function signatures, scoring formula, store schema, config instance, test plan).

## 1. Module map (final)

```
src/
├── config.py               # PipelineConfig (pydantic) + load_config()
├── models.py               # JobStatus, JobEntry, job_id(), metadata registry
├── stage1.py               # run_stage1() — Stage 1 orchestrator (API + CLI share it)
├── ingestion/ingest.py     # Fetcher protocol + FETCHER_REGISTRY (4 API fetchers + HTML stub)
├── parsing/parse.py        # parse_job_listing() dispatch + per-source mappers + text helpers
├── matching/match.py       # compute_match_score(), match_candidate_to_job(), score_job()
└── queues/
    ├── store.py            # JobsStore (SQLite) + TRANSITIONS enforcement
    └── cli.py              # argparse CLI over store + stage1 orchestrator
app/
├── main.py                 # FastAPI routes (unified surface)
└── static/index.html       # dependency-free admin UI (thin client over the API)
config/
├── pipeline.example.json   # full-shape example (Stage 2-4 sections empty/defaults)
└── pipeline.json           # real config (gitignored) — candidate profile + sources
```

Substage decomposition (per the modularity contract): `ingest.py → fetch_from_source`,
`parse.py → parse_job_listing`, `match.py → compute_match_score`; `stage1.py` orchestrates
its own substages only. Stages never import each other; the store is the only cross-stage
surface.

## 2. Data flow

```
config/pipeline.json ──► load_config() ──► PipelineConfig
        │
        ▼ (per enabled source)
FETCHER_REGISTRY[name].fetch(source)          # httpx GET, JSON; errors per-source
        │  raw dicts (source-stamped)
        ▼
parse_job_listing(raw, base_resume_path)      # per-source mapper → JobEntry (id, metadata)
        │
        ▼
compute_match_score(candidate, job, matching) # (score 0-100, breakdown); location gate first
        │
        ▼
JobsStore.save()  → status = accepted | rejected | new (auto-accept flag off → new)
        │
        ▼
Tooling: CLI subcommands + FastAPI routes (view/accept/reject/note/edit/status)
```


## 3. Sources (confirmed against live responses 2026-09-27)

| name | type | URL / params | Live shape (verified) |
|------|------|--------------|------------------------|
| `remotive` | api | `https://remotive.com/api/remote-jobs?limit=N` | `{jobs:[{id,url,title,company_name,category,tags,job_type,publication_date,candidate_required_location,salary,description(<html>)}]}` |
| `remoteok` | api | `https://remoteok.com/api` | `[ {legal...}, {slug,id,epoch,date,company,position,tags,description(<html>),location,apply_url,url,salary_min,salary_max} ]` — first element is a legal-notice object without `position` (filtered) |
| `arbeitnow` | api | `https://www.arbeitnow.com/api/job-board-api` | `{data:[{slug,company_name,title,description(<html>),location,remote(bool),url,tags,job_types,created_at}], meta}` — carries German-language postings incl. Werkstudent |
| `bundesagentur` | api | `.../pc/v4/jobs?was=werkstudent&wo=Aachen&umkreis=100&page=1&size=50` (query params live in the source URL — one search per source entry) | `{embedded:[{titel,beruf,arbeitgeber,arbeitsort:{ort,plz,region,land},eintrittsdatum,refnr,distanz,externeUrl,jobDetailURL,modifikationsTimestamp}], page:{...}}` — header `X-API-Key: jobboerse-jobsuche` (override via `.env` `BA_API_KEY`) |
| `html-stub` | html | — | `NotImplementedError` (plugin seam for RWTH Aachen HiWi board later) |

Notes:
- The BA endpoint returns **HTTP 403 from datacenter IPs** (verified in this environment);
  it works from residential networks. `run_stage1()` therefore handles per-source errors
  gracefully (source skipped, error recorded in the run summary) and tests use recorded
  fixtures — no live network in pytest.
- Multiple BA searches are modeled as multiple `bundesagentur` sources (e.g. Werkstudent
  Aachen, Werkstudent Köln, HiWi Aachen, Werkstudent home-office).

## 4. Ingestion (`src/ingestion/ingest.py`)

- `Fetcher` Protocol: `name: str`, `fetch(source: SourceConfig) -> list[dict]`.
- `BundesagenturFetcher` (new): GET `source.url` with headers
  `{"X-API-Key": os.environ.get("BA_API_KEY", "jobboerse-jobsuche")}`;
  returns `[dict(entry, source=self.name) for entry in payload.get("embedded", [])]`.
- `FETCHER_REGISTRY`: `remotive`, `remoteok`, `arbeitnow`, `bundesagentur`, `html-stub`.
- `fetch_from_source(source_config)` dispatch (unchanged semantics).
- `fetch_job_listings(source_url)` legacy placeholder preserved.

## 5. Parsing (`src/parsing/parse.py`)

- Helpers: `strip_html`, `extract_email`, `extract_company_website`, `_unix_to_iso`.
- Per-source mappers (module-private, one per board):
  - `_parse_remotive`: `candidate_required_location → location`, `job_type`, `salary`,
    `publication_date` (ISO string), website/email salvaged from description.
  - `_parse_remoteok`: `position → title`, `company → company_name`, salary range join,
    `date → publication_date`.
  - `_parse_arbeitnow`: `remote == true` → `"remote"` prepended to location and `"remote"`
    added to tags; `job_types` list → `job_type` (joined); `created_at` (unix) → ISO.
  - `_parse_bundesagentur`: `titel → title` (fallback `beruf`), `arbeitgeber → company_name`,
    `arbeitsort.ort/region/land → location` (comma-joined), `eintrittsdatum` kept in
    `publication_date`, `refnr` → `tags` entry `refnr:<refnr>`, `externeUrl|jobDetailURL →
    source_url`, `distanz` → location suffix `(<distanz> km)`. Descriptions come from the
    detail endpoint (fetched lazily by Stage 2 if needed; search response has none).

## 6. Matching (`src/matching/match.py`)

Deterministic, config-weighted, offline (design decision #3). LLM backend stays a stub.

### Formula

```
eligible = location_gate(job)                      # see below
experience = coverage(candidate.skills ∪ experience-terms, job_text)
prospects  = coverage(matching.in_demand_technologies, job_text)
education  = role-keyword correlation (student-role terms)
score      = round( (w_exp*experience + w_pros*prospects + w_edu*education)
                    / (w_exp + w_pros + w_edu) )   # 0..100, gated → 0
```

- `job_text` = `title + description + tags + location`, lower-cased.
- `coverage(list, text)` = `100 * |{term: term in text}| / |list|`; empty list → neutral 50.
- `education` role keywords come from `MatchingConfig.role_keywords`
  (`werkstudent`, `hiwi`, `working student`, `studentische hilfskraft`, `student assistant`,
  `praktikum`, `intern`, `thesis`, `abschlussarbeit`): a title hit earns the full
  factor (100), description/tag-only hits earn 40, no hit earns 0. This keeps
  Werkstudent/HiWi postings competitive against full-time roles that list more skills.
- **Experience noise control**: candidate experience entries are prose; common English
  function words (`STOPWORDS` in `match.py`) and tokens shorter than 3 chars are excluded
  from the coverage term set so they cannot inflate the experience factor.
- **Location gate** (hard eligibility; the user targets remote OR Aachen/Köln area):
  eligible iff the job indicates remote (`MatchingConfig.remote_indicators` matched in
  location/tags — `remote`, `worldwide`, `anywhere`, `homeoffice`, …) **or** the location
  contains one of `MatchingConfig.location_keywords` (`aachen`, `köln`, `cologne`, …).
  An empty location with no remote tag is **not** eligible. Gated-out jobs score 0 and the
  breakdown records `location_fit: false`. `MatchingConfig.require_location_fit` (default
  `true`) disables the gate for broad searches.
- Breakdown dict (stored under `metadata.score_breakdown`): per-factor values, matched
  skills/technologies/role keywords, `location_fit`.

### Public API (signatures)

```python
compute_match_score(candidate_profile, job, matching=None) -> tuple[int, dict]
match_candidate_to_job(candidate_profile, job_listing, matching=None) -> bool   # score ≥ threshold
score_job(candidate_profile, job, matching=None, backend="deterministic") -> tuple[int, dict]
SCORER_REGISTRY = {"deterministic": compute_match_score, "llm": _llm_scorer}
```

`candidate_profile`/`matching` accept pydantic models or plain dicts (normalized
internally). `_llm_scorer` raises `NotImplementedError` (shared `src/llm/` lands with the
Stage 2–4 foundation).

## 7. Queue store (`src/queues/store.py`)

SQLite at `job-pipeline/data/queues.db` (module constant `DB_PATH`, monkey-patched in
tests; auto-created, gitignored). The single cross-stage store.

```sql
CREATE TABLE IF NOT EXISTS jobs (
  id         TEXT PRIMARY KEY,
  status     TEXT NOT NULL,
  score      REAL NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,

## 9. Interactive tooling

### CLI (`python -m src.queues.cli`) — subcommands

`status` · `view <status>` · `show <id>` · `view-accepted` · `view-rejected` ·
`accept <id>` · `reject <id>` · `note <id> <text>` · `edit <id>` (guarded field=value
edits via the same whitelist as `PATCH /jobs/{id}`) · `run [--source NAME] [--limit N]
[--dry-run]` (batch Stage 1 over enabled sources) · `--config PATH` global option.

### FastAPI routes (`app/main.py`) — unified surface

| Route | Purpose |
|-------|---------|
| `GET /` | health |
| `POST /ingest` | full Stage-1 flow for one source `{source: "remotive", limit?, dry_run?}` |
| `POST /stage1/run` | batch over all enabled sources (`?limit=&dry_run=`) |
| `GET /status` | queue counts + stage flags (pipeline summary) |
| `GET /jobs?status=&limit=` | list entries (score desc) |
| `GET /jobs/{id}` | one entry |
| `POST /jobs/{id}/accept` \| `reject` | guarded status transitions (manual) |
| `POST /jobs/{id}/note` | append human note to `metadata.notes` |
| `PATCH /jobs/{id}` | whitelist edit: human fields only (`title`, `company_name`, `company_website`, `contact_info`, `location`, `tags`, `job_type`, `salary`, `metadata.notes`, `metadata.base_resume_path`); `id`, `status`, stage-owned registry keys immutable → 422 |
| `GET /ui` | static `app/static/index.html` (dependency-free thin client) |

## 10. Config instance (`config/pipeline.json`)

- `sources`: `remotive`, `remoteok`, `arbeitnow` + four `bundesagentur` searches
  (Werkstudent Aachen umkreis=100, Werkstudent Köln umkreis=100, HiWi/wissenschaftliche
  Hilfskraft Aachen umkreis=100, Werkstudent home-office NRW).
- `search_keywords` (EN+DE): `werkstudent`, `hiwi`, `working student`,
  `studentische hilfskraft`, `student assistant`, `software engineer`, `backend`,
  `python`, `golang`, `java`.
- `matching`: weights `experience 1.0, prospects 0.6, education 1.2` (student-role
  correlation matters most for this candidate); `match_threshold: 40` (initial value —
  expected to be re-tuned after manual analysis of the rejected list, per `plan.md`);
  `auto_accept_above_threshold: false` (human review first); `in_demand_technologies`:
  AWS/Kubernetes/Kafka/Redis/golang/Python/Java/Docker/Jenkins/microservices;
  `role_keywords` + `location_keywords` + `remote_indicators` as in §6.
- `candidate_profile` (from `./data/*.md`, `./data/Resume*.tex`): skills (Java, Go,
  Python, AWS, Kubernetes, Docker, Jenkins, Kafka, Redis, RabbitMQ, React, Node.js,
  MongoDB, Prometheus, Grafana, Rust, SQL…), experience entries (Amazon UPI payments,
  Visa Data/AI inferencing platform, Raze B2B SaaS, Spring Spree), education
  (B.Tech NIT Warangal 2023 + ongoing M.Sc.), `location: Aachen`, languages EN+DE.
- `base_resume_path`: `../data/Resume.tex` (resolved from `job-pipeline/`; Stage 1 only
  stamps it into metadata — Stage 2 owns reading it).
- `stage2`/`stage3`/`stage4` sections ship empty/defaults from day one.

## 11. Test plan (`job-pipeline/tests/`)

No live network in pytest (testing contract); recorded fixtures in `tests/fixtures/`.

| File | Covers |
|------|--------|
| `conftest.py` | shared fixtures: tmp SQLite store (monkey-patched `store.DB_PATH`), sample `JobEntry`, candidate/matching dicts, fixture loaders |
| `fixtures/*.json` | one recorded raw payload per source (remotive, remoteok, arbeitnow, bundesagentur) |
| `test_config.py` | config resolution order, validation, defaults on missing file |
| `test_models.py` | `job_id` stability, forward-complete `JobStatus`, registry keys |
| `test_parse.py` | per-source normalization from fixtures, HTML/email/website helpers, fallbacks, unknown-source error |
| `test_ingest.py` | registry dispatch, unregistered/html errors, `BundesagenturFetcher` via monkey-patched `_get_json`, legacy placeholder |
| `test_match.py` | per-factor scoring, location gate, weights/threshold from config, dispatch, llm stub |
| `test_store.py` | upsert idempotency, status preservation on re-ingest, transition map enforcement, notes/counters |
| `test_stage1.py` | `run_stage1` with fake fetchers: classify/dry-run/limit, per-source error isolation, idempotent re-run |
| `test_cli.py` | CLI functions over a tmp store |
| `test_api.py` | `TestClient`: health, ingest (fake fetcher), jobs list/show, accept/reject/note, PATCH whitelist, status, batch run |
| `test_pipeline.py` | legacy placeholder (unchanged) |

### Live isolation check (manual, not pytest)

`job-pipeline/scripts/stage1_live.py` — runs the full Stage-1 flow against the real
boards with the real config and prints the run summary + top scored jobs. Network
failures per source (e.g. BA 403 from datacenter IPs) are reported, not fatal.

## 12. Risks / notes

- BA 403 from this environment → fixtures + graceful degradation; live check from a
  residential network.
- Initial threshold 40 and weights are a starting point for re-tuning.
- `pandas` untouched; dependency set unchanged (BA fetcher uses `httpx` + the public
  API key header).
- `fetch_job_listings()` placeholder behavior preserved.

  payload    TEXT NOT NULL      -- JobEntry JSON
);
```

`class JobsStore:` — `__init__(path=None)`, `save(entry: JobEntry)`,
`get(job_id) -> JobEntry | None`, `list_by_status(status, limit=None) -> list[JobEntry]`
(score desc), `count_by_status() -> dict[str, int]`,
`update_status_and_notes(job_id, new_status=None, notes=None) -> JobEntry`.

- **Idempotent re-ingest** (`save`): existing row → payload fields + score refreshed,
  `status` preserved (ingest never demotes an already-classified job); metadata merged
  with existing values winning for non-empty human-owned keys (`notes`).
- **Transition map** (`update_status_and_notes`, `InvalidTransitionError` on violation):

```
new          → accepted | rejected
rejected     → accepted                (manual accept)
accepted     → rejected | resume_ready (reject only pre-resume_ready)
resume_ready → sent                    (Stage 4 owns)
sent         → ∅                       (terminal)
```

## 8. Orchestrator (`src/stage1.py`)

```python
run_stage1(config: PipelineConfig, store: JobsStore, source_name: str | None = None,
           limit: int | None = None, dry_run: bool = False) -> dict
```

- Iterates enabled sources (`source_name` filters to one); per source: fetch → parse →
  score → classify (`score ≥ threshold` → accepted if `auto_accept_above_threshold` else
  new; else rejected) → `store.save()`.
- Per-source errors are caught and recorded as `{"source": name, "error": "..."}` in the
  run summary — one broken board never fails the batch.
- Summary: `{"sources": [{name, ingested, accepted, rejected, new, error?}], "ingested",
  "accepted", "rejected", "new", "dry_run"}`.
- `dry_run=True`: fetch/parse/score run, nothing persisted.
- `base_resume_path` from `config.base_resume_path` is stamped into every entry's
  metadata (the real config value resolves from `job-pipeline/`).

- `parse_job_listing(raw: dict, base_resume_path: str = "") -> JobEntry`:
  dispatch on `raw["source"]`; builds `id = job_id(title, company_name, source)`;
  metadata `{"base_resume_path": base_resume_path, "notes": ""}`; unknown source →
  `ValueError`.

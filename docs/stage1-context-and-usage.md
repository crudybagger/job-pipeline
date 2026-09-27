# Stage 1 — Context and Usage

Practical guide for **Stage 1 — Job Scraping and Filtering** of the Job Finder and
Application Pipeline. Design references: `docs/design/stage1-job-scraping-and-filtering.md`
(HLD) and `docs/design/stage1-lld.md` (LLD, function-level). Cross-stage contract:
`docs/design/pipeline-integration.md`.

**Status: implemented, tested (84 passing), and validated against real web data.**

## 1. What Stage 1 does (context)

Stage 1 is the pipeline's entry point. It collects job postings from job boards,
normalizes them, scores them against the candidate profile, and files each posting
into one of three persistent queues:

| Status | Meaning | Routed by |
|--------|---------|-----------|
| `new` | Ingested and scored; **awaiting your accept/reject review** | scoring ≥ threshold (auto-accept off) |
| `accepted` | Eligible for Stage 2 (tailored resume) | scoring ≥ threshold with auto-accept on, or a manual accept |
| `rejected` | Rejected by scoring or by you | scoring below threshold, or a manual reject |

Later stages (`resume_ready` → Stage 2, `sent` → Stage 4) extend the same store; Stage 1
never touches them.

For every job it collects: title, description (stripped to plain text), company name and
website, contact details (email when the board exposes one), location, salary, tags, job
type, publication date, source URL — plus metadata: `score`, `score_breakdown`,
`base_resume_path` (pre-configured resume starting point for Stage 2) and `notes`.

### Targeting (this candidate's configuration)

The real config targets **English and German Werkstudent/HiWi jobs — remote, or anywhere
near Aachen, Cologne (Köln), Düsseldorf, Bonn** — and HiWi roles at RWTH Aachen
(via the Bundesagentur für Arbeit source; the RWTH job portal itself has no JSON API and
stays the `html-stub` plugin seam for a later milestone).

Scoring reflects `plan.md`'s three factors, combined with configurable weights
(defaults: `experience 1.0, prospects 0.6, education 1.2`):

1. **Experience** — overlap of the candidate's skills/experience terms with the job text.
2. **Prospects** — coverage of the `in_demand_technologies` list (AWS, Kubernetes, Kafka,
   Redis, golang, …).
3. **Education** — correlation with ongoing education via student-role keywords
   (`werkstudent`, `hiwi`, `working student`, `studentische hilfskraft`, `praktikum`,
   `intern`, `thesis`, …): a title hit earns the full factor, description/tag-only hits
   40, none 0.

A **hard location gate** runs first: jobs that are neither remote nor near a configured
location score 0 regardless of the other factors. Disable it with
`matching.require_location_fit: false` for broad searches.

## 2. Sources

| name | type | What it provides |
|------|------|------------------|
| `remotive` | api | Global remote jobs (English) |
| `remoteok` | api | Global remote jobs (English) |
| `arbeitnow` | api | German job board — carries German-language Werkstudent postings |
| `bundesagentur` | api | Bundesagentur für Arbeit Jobsuche API — Werkstudent/HiWi near Aachen/Köln; one search per source entry (query params live in the source URL) |
| `html-stub` | html | Plugin seam for the RWTH Aachen HiWi board (raises `NotImplementedError`) |

Add a source by appending an entry to `sources` in `config/pipeline.json`:

```json
{ "name": "bundesagentur", "type": "api",
  "url": "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v4/jobs?was=werkstudent&wo=Aachen&umkreis=100&page=1&size=50",
  "enabled": true }
```

Notes:
- The Bundesagentur endpoint authenticates via the public `X-API-Key: jobboerse-jobsuche`
  header (override with the `BA_API_KEY` env var) and **returns 403 from datacenter IPs** —
  it works from residential networks. One broken board never fails a batch run; its error
  is recorded per source.
- A new non-JSON source = one fetcher class + one `FETCHER_REGISTRY` entry in

## 3. Configuration

All knobs live in one file: `job-pipeline/config/pipeline.json` (real, gitignored;
`config/pipeline.example.json` documents the full shape, including empty Stage 2–4
sections). Sections relevant to Stage 1:

```json
{
  "sources":            [ "...boards to scrape (see section 2)..." ],
  "search_keywords":    ["werkstudent", "hiwi", "...EN+DE search terms..."],
  "matching": {
    "score_weights":    { "experience": 1.0, "prospects": 0.6, "education": 1.2 },
    "match_threshold":  40,
    "auto_accept_above_threshold": false,
    "in_demand_technologies": ["aws", "kubernetes", "..."],
    "role_keywords":    ["werkstudent", "hiwi", "working student", "..."],
    "location_keywords": ["aachen", "köln", "cologne", "düsseldorf", "bonn", "..."],
    "remote_indicators": ["remote", "worldwide", "anywhere", "homeoffice", "..."],
    "require_location_fit": true
  },
  "candidate_profile": {
    "skills": ["java", "golang", "python", "aws", "..."],
    "experience": ["Software Engineer at Amazon ...", "..."],
    "education": ["B.Tech Computer Science, NIT Warangal (2023)", "..."],
    "location": "Aachen",
    "languages": ["english", "german"]
  },
  "base_resume_path": "../data/Resume.tex"
}
```

- `match_threshold` and all keyword lists are the re-tuning knobs — adjust them after a
  manual review of the rejected list (section 5.2) and re-ingest.
- `auto_accept_above_threshold: false` keeps every passing job in `new` for human review;
  set `true` to route them straight to `accepted` (Stage 2 eligibility).
- `.env` (python-dotenv) overrides for secrets: `BA_API_KEY` (Bundesagentur), later
  `LLM_API_KEY` / `TELEGRAM_TOKEN` / research keys for Stages 2–4. `PIPELINE_CONFIG` env
  var selects an alternative config path.

## 4. Running Stage 1

From `job-pipeline/` (tests/uvicorn resolve `src.*` imports from there):

### 4.1 Batch run — all enabled sources

```bash
# API
uvicorn app.main:app --reload
# then: POST /stage1/run?limit=100    (or ?dry_run=true to persist nothing)

# CLI
python -m src.queues.cli run                      # all enabled sources
python -m src.queues.cli run --source arbeitnow --limit 50 --dry-run
```

Run summary (also returned by both interfaces):

```json
{
  "sources": [
    {"source": "arbeitnow", "ingested": 325, "accepted": 0, "new": 7, "rejected": 318},
    {"source": "bundesagentur", "ingested": 0, "error": "Client error '403 ...'"}
  ],
  "ingested": 441, "accepted": 0, "new": 7, "rejected": 434, "dry_run": false
}
```

### 4.2 Single-source run

```bash
# API
POST /ingest {"source": "remotive", "limit": 100, "dry_run": false}

# CLI
python -m src.queues.cli run --source remotive
```

### 4.3 Review and interactive tooling

```text
API                                      CLI equivalent
GET  /status                             python -m src.queues.cli status
GET  /jobs?status=new&limit=20           python -m src.queues.cli view new
GET  /jobs/{id}                          python -m src.queues.cli show <id>
GET  /jobs?status=accepted               python -m src.queues.cli view-accepted
GET  /jobs?status=rejected               python -m src.queues.cli view-rejected
POST /jobs/{id}/accept                   python -m src.queues.cli accept <id>
POST /jobs/{id}/reject                   python -m src.queues.cli reject <id>
POST /jobs/{id}/note {"note": "..."}     python -m src.queues.cli note <id> <text>
PATCH /jobs/{id} {"updates": {...}}      python -m src.queues.cli edit <id> field=value
GET  /ui                                 # dependency-free admin UI in the browser
```

- Status changes are **transition-map enforced** (`new → accepted/rejected`,
  `rejected → accepted` manual rescue, `accepted → rejected` only pre-`resume_ready`);
  violations return HTTP `409`.
- `PATCH /jobs/{id}` and `edit` accept only human-owned fields (`title`, `company_name`,
  `company_website`, `contact_info`, `location`, `tags`, `job_type`, `salary`,
  `metadata.notes`, `metadata.base_resume_path`); `id`, `status` and stage-owned keys are
  immutable → HTTP `422`.
- Orchestration is deliberately manual: nothing auto-runs after ingestion; a batch run is
  an explicit human action (one API call or one CLI command — no schedulers anywhere).


## 5. Validation and re-tuning

### 5.1 Live isolation check with real web data

`scripts/stage1_live.py` runs the full Stage-1 flow against the real boards with the real
config and prints the run summary plus the top scored jobs per queue. It is **manual —
not part of the pytest suite** (the testing contract keeps CI network-independent).

```bash
cd job-pipeline
.venv/bin/python scripts/stage1_live.py              # ingest + show top jobs
.venv/bin/python scripts/stage1_live.py --dry-run    # nothing persisted
.venv/bin/python scripts/stage1_live.py --source arbeitnow --limit 50
```

Last validated run: 441 real jobs ingested (Remotive 17, RemoteOK 99, Arbeitnow 325);
after the first re-tuning, 7 Werkstudent/SHK/HiWi-style jobs near Köln, Düsseldorf and
Münster routed to `new` (scores 44–49). The Bundesagentur source reports
`403 from datacenter IPs` per-source and is non-fatal — run the check from a residential
network to validate it.

### 5.2 The re-tuning loop (plan.md)

The match score is **expected to be re-tuned after manual analysis of the rejected list**:

1. Run a batch (`python -m src.queues.cli run`) and review the rejected queue.
2. Inspect factor breakdowns: `python scripts/analyze_rejected.py` prints per-job
   `experience/prospects/education` values, the location-gate reason and matched skills.
3. Adjust `config/pipeline.json` — weights, `match_threshold`, `role_keywords`,
   `location_keywords`, `remote_indicators`, candidate skills/experience.
4. Re-ingest to re-score: existing entries are updated in place, not duplicated; entries
   already classified keep their queue status, so point a fresh re-score at a new/fresh
   store when re-routing everything (or manually accept rescued jobs via
   `POST /jobs/{id}/accept`).

### 5.3 Tests

```bash
cd job-pipeline && pytest -q    # 84 passed; recorded fixtures in tests/fixtures/,
                                # no live network in the suite
```

## 6. Data layout and code map

```
job-pipeline/
├── config/pipeline.json            # real config (gitignored); example alongside
├── data/queues.db                  # SQLite jobs store (single cross-stage store)
├── src/
│   ├── config.py                   # PipelineConfig (pydantic) + load_config()
│   ├── models.py                   # JobStatus, JobEntry, job_id(), metadata registry
│   ├── stage1.py                   # run_stage1() orchestrator (API + CLI share it)
│   ├── ingestion/ingest.py         # fetchers: remotive/remoteok/arbeitnow/bundesagentur + html-stub
│   ├── parsing/parse.py            # parse_job_listing() dispatch + per-source mappers
│   ├── matching/match.py           # compute_match_score(), location gate, score_job()
│   └── queues/{store,cli}.py       # SQLite store + interactive CLI
├── app/{main.py,static/index.html} # FastAPI unified surface + admin UI
└── scripts/{stage1_live,analyze_rejected}.py
```

Key invariants (cross-stage contract): stages never import each other — they communicate
only through the SQLite `jobs` table, the metadata key registry, and the status transition
map. Stage IDs are stable (`sha256(title|company|source)[:12]`), so re-ingestion updates
the same row.

## 7. Known limitations

- Bundesagentur für Arbeit endpoint: 403 from datacenter IPs; search-response entries
  carry no description (full text requires the `jobdetails` endpoint — fetched lazily by
  Stage 2 if needed).
- RWTH Aachen HiWi board is not scraped yet (HTML-only; the `html-stub` seam is the
  plugin point).
- Initial threshold (40) and weights are a starting point — re-tune per section 5.2.

  `src/ingestion/ingest.py` and one parser in `src/parsing/parse.py`.

# System Patterns

## Overview
The repository is a monorepo rooted at `/e/jobs` containing the product blueprint, a Python/FastAPI pipeline project, and tooling. The pipeline is organized as stage packages under `job-pipeline/src/`, with a thin FastAPI app as the entrypoint and a markdown-based local issue tracker driven by an automation loop.

## Repository Layout
```
/e/jobs
├── plan.md                  # Product blueprint (source of truth for the 4 stages)
├── README.md                # Plan-driven, stage-oriented root README
├── automation/              # Namespace wrapper package
│   └── __init__.py          # Extends __path__ → job-pipeline/automation
├── memory-bank/             # This memory bank
└── job-pipeline/            # Main Python project
    ├── app/main.py          # FastAPI app: GET / (health), POST /ingest
    ├── src/                 # Stage packages (all placeholder logic)
    │   ├── ingestion/ingest.py        # fetch_job_listings() → returns []
    │   ├── parsing/parse.py           # parse_job_listing() → returns input
    │   ├── matching/match.py          # match_candidate_to_job() → False
    │   ├── outreach/send_application.py  # send_application() → True
    │   ├── high_level_design_hld.py   # Placeholder (Issue #1, Done)
    │   └── low_level_design_lld.py    # Placeholder (Issue #2, Done)
    ├── automation/          # Local issue-tracker automation
    │   ├── issue_tracker.py # Parse/modify/persist issues.md; placeholder
    │   │                    #   generation; git commit+push when .git exists
    │   └── run_issue_loop.py  # Long-running loop, processes issues every 600s
    ├── issues.md            # Markdown issue tracker (Issues #1–#3 all Done)
    ├── tests/               # test_pipeline.py, test_issue_tracker.py
    ├── requirements.txt
    └── .github/workflows/ci.yml  # CI: pytest on push/PR to main (Python 3.12)
```

## Architecture / Data Flow
```
Job boards → Ingestion (Stage 1) → Parsing → Matching (score filter)
        → accepted/rejected queues (persistent, planned)
        → Resume generation + ATS loop (Stage 2) → resume-ready queue
        → Cover letter generation (Stage 3)
        → Delivery package + messaging (Stage 4) → sent queue + tracking
```
Planned queues (per `plan.md`): accepted, rejected, resume-ready, sent — all in persistent storage.

## Key Technical Decisions
- **FastAPI app as Stage-1 entrypoint** (`app/main.py`); `POST /ingest(source_url)` triggers `fetch_job_listings`. Stages 2–4 should expose entrypoints consistent with this pattern (API route, CLI, or worker) under `src/`.
- **One package per pipeline stage** under `src/` (ingestion → parsing → matching → outreach), each with pure functions and type hints, currently returning placeholder values.
- **Markdown issue tracking** (`issues.md`) instead of GitHub issues; automation loop parses open issues, generates `src/<slug>.py` placeholders, marks issues Done/assignee=automation, and commits+pushes when inside a git repo.
- **Namespace wrapper** (`/e/jobs/automation/__init__.py`) overrides `__path__` to forward `automation.*` imports to `job-pipeline/automation`, so tests/scripts run from repo root resolve correctly.
- **Isolated tests**: `test_issue_tracker.py` monkey-patches module constants (`ISSUES_FILE`, `SRC_ROOT`, `REPO_ROOT`, `is_git_repo`) to a temp directory, keeping production files untouched.

## Component Relationships
- `app/main.py` imports from `src.ingestion.ingest` (repo-root-relative `src` package; tests run from `job-pipeline/`).
- `automation.run_issue_loop` → `automation.issue_tracker.run_once` → `process_open_issues()` → `plan_issue`/`implement_task`/`save_issues` → optional `git_commit_and_push`.
- Test environment: pytest from `job-pipeline/` (3 tests pass).

## Critical Implementation Paths
- Stage 1: implement real scraping in `src/ingestion/ingest.py` + normalization in `src/parsing/parse.py`; wire score filter into `src/matching/match.py`; add persistent queues.
- Stage 2: LaTeX resume editing + ATS substage loop (new queue; notes round-trip via job metadata).
- Stage 3: company research + fixed narrative-pattern cover letter generation.
- Stage 4: message compilation + messaging-platform integration + sent/applied tracking with candidate notes.

## Version History
- **Version 1.0**: Initialized from repository context

## Notes
- Environment shell is fish; some shell command substitutions must be written bash-style carefully.
- Git history: `f1dbbbc` add system prompt → `6e4eea8` Rewrite root README (#2) → `315f469` First commit.

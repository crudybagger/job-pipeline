# Stage 2–4 Design — Resume Generation, Cover Letters, and Delivery

Design plan for **Stages 2–4** of the Job Finder and Application Pipeline (see `plan.md` at repo root for the source-of-truth blueprint). This document was agreed in planning and is the reference implementation plan for Milestones 3–5. It builds directly on the Stage 1 design (`./stage1-job-scraping-and-filtering.md`): the accepted queue, SQLite store, config layer, and tooling patterns from Stage 1 are reused.

## Architecture

```
Stage 1 (accepted queue, SQLite)
        │
        ▼
STAGE 2  src/resume/ (new package)
  generate:  edit_base_resume(job_entry, candidate, base_latex) → tailored LaTeX
             — edits only bulletpoints/skills/summary sections, human phrasing
  ats:       independent substage: score_resume(job, resume) → (score, feedback notes)
  loop:      generate → ATS score → notes → re-edit … until ready
        │
        ▼
  resume-ready queue (separate status in the SQLite store, per plan.md)
        │
        ▼
STAGE 3  src/coverletter/ (new package)
  research:  collect company/department/hiring-manager context (modular providers)
  generate:  fixed narrative pattern (Story Hook → Background → Experience → Skills
             → Story → Fitment → Interest → Closing), consistent across runs
        │
        ▼
STAGE 4  src/outreach/ (new package)
  compile:   job link + description + resume + cover letter → single text message
  send:      Telegram Bot API integration
  track:     sent queue + applied/not-applied status + candidate notes → metadata
```

## Confirmed decisions

| # | Decision | Choice | Rationale |
|---|----------|--------|-----------|
| 1 | **LLM backend (Stages 2–3)** | OpenAI-compatible API behind a shared `src/llm/` provider abstraction; endpoint + key via `.env` | Stages 2–3 are inherently generative (human-sounding language, natural keyword weaving); a single abstraction avoids duplicated plumbing and is reused by Stage 1's pluggable `llm` scorer slot. Works with OpenAI or any compatible endpoint. |
| 2 | **Messaging (Stage 4)** | Telegram Bot API behind a pluggable sender abstraction | Simplest integration: free, no phone-number approval, plain HTTP via existing `httpx`; bot token + chat id via `.env`. |
| 3 | **Company research (Stage 3)** | Modular research backend: Tavily (extensive web search snippets) now → Zyte spider in future → DuckDuckGo/firecrawl/other free tools as fallback chain | Tavily is LLM-oriented with a generous free tier and clean snippets; the provider chain keeps the backend swappable. |
| 4 | **LaTeX editing (Stage 2)** | Section-targeted editing: locate bulletpoints/skills/summary blocks in the base `.tex` by name, regenerate only those | Safest guarantee of the plan.md constraint "only edits minimal and required sections"; full re-generation risks formatting damage. |
| 5 | **ATS loop termination (Stage 2)** | Config-driven: `ats_ready_threshold` + `max_iterations` cap; stops at whichever comes first | Prevents infinite loops; makes the loop tunable like Stage 1's match threshold, per plan.md's re-tunable philosophy. |
| 6 | **Output format (Stage 3)** | Plain text + Markdown first; PDF via LaTeX compilation only if a target board requires it later | Cover letters are typically pasted into web forms; text is universally acceptable. |
| 7 | **Sent tracking (Stage 4)** | Same SQLite store, new `sent` status/queue; candidate notes round-trip via job entry metadata | Keeps one store and one tooling surface, consistent with Stage 1's queues. |

## Implementation outline

### Shared foundation (first — serves all stages)
- `src/llm/` — OpenAI-compatible client abstraction: `complete(system, user, schema=None)` with JSON-mode support; provider/endpoint/key/model from config + `.env`; retry/timeout handling; mockable backend so tests run without network.
- Extend `src/config.py` with per-stage sections:
  - `stage2`: `ats_ready_threshold`, `max_iterations`, LaTeX section markers
  - `stage3`: research provider chain config, `story_context`, narrative pattern
  - `stage4`: messaging credentials, message template

### Stage 2 — `src/resume/`
- `generate.py`: `edit_base_resume(job, candidate, base_latex)` → LLM-edited bulletpoints/skills/summary; edits validated against allowed section markers, with diff-checking so only permitted sections change.
- `ats.py`: independent `score_resume(job, resume)` → `(score, feedback_notes)` — LLM-backed "professional screener / tech hiring manager" scoring backend, plus the deterministic backend from Stage 1 as a second signal; feedback highlights missing keywords and misaligned points.
- `loop.py`: generate → score → write notes back to entry metadata → stage 2 picks them up and re-iterates; entry moves to the **resume-ready queue** (new status in the SQLite store) when `ats_ready_threshold` is met or `max_iterations` is reached.
- Human-sounding language enforced via prompt constraints plus a "no generic AI tone" check in the ATS feedback.

### Stage 3 — `src/coverletter/`
- `research.py`: modular provider chain behind a `Researcher` protocol — `TavilyResearcher` now → `ZyteSpider` in future → `DuckDuckGoResearcher` / `FirecrawlResearcher` fallbacks; results cached in entry metadata; graceful degradation when no provider or key is available.
- `generate.py`: fixed 8-part narrative pattern (Story Hook → Background → Experience → Skills → Story → Fitment → Interest → Closing); story context from `stage3.story_context` config; consistency across runs via a strict sectioned template and controlled temperature; job- and company-specific output; plain text + Markdown.

### Stage 4 — `src/outreach/`
- `compile.py`: single text message template (job link, description excerpt, resume, cover letter) driven by `stage4` config; respects Telegram's 4096-char limit with smart splitting.
- `send.py`: `TelegramSender` behind a `Sender` protocol; marks the entry **sent** and moves it to the sent queue.
- `track.py` + tooling: `GET /sent` and `POST /sent/{id}/status` (applied/not-applied + notes) API routes and CLI subcommands; candidate notes persisted in job entry metadata for future analysis.

### Tests
- Same isolation rules as Stage 1: mocked LLM/research/HTTP backends from recorded fixtures, temp-dir SQLite (monkey-patched constants), API tests via `TestClient`; `pytest -q` green; no live external calls in CI.

## Suggested sequencing

1. Shared foundation (`src/llm/` + config extension)
2. Stage 2 (resume generation + ATS loop)
3. Stage 3 (cover letter generation)
4. Stage 4 (delivery package + Telegram + tracking)
5. Wrap-up: README + memory-bank updates, `pytest -q` green

## Risks / notes

- LLM prompts need iteration to consistently produce "human-sounding" output; the ATS feedback loop is the enforcement mechanism.
- Tavily/Zyte credentials are provided via `.env`; the research chain must degrade gracefully when keys are absent.
- Telegram message size limit (4096 chars) may split large packages — handled in `compile.py`.


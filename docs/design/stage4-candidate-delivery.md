# Stage 4 Design — Candidate Delivery Package

Design plan for **Stage 4** of the Job Finder and Application Pipeline (see `plan.md` at repo root for the source-of-truth blueprint). Reference implementation plan for Milestone 5. Builds on Stages 1–3 and the cross-stage contract (`./pipeline-integration.md`).

## Scope

Compile the job link, job description, tailored resume, and cover letter into a single review-ready delivery, send it to the candidate via Telegram, and track sent/applied state with candidate notes. Operates only on `resume_ready` entries.

## Architecture

```
Stage 3 (resume_ready entries in SQLite jobs table)
        │
        ▼
src/outreach/ (new package)
  compile:   job link + description excerpt + cover letter + resume extract
             → single text message (+ resume as a document attachment)
             — respects Telegram's 4096-char limit with section-boundary splitting
  send:      TelegramSender behind a Sender protocol (Telegram Bot API via httpx)
             — marks the entry sent; idempotent
  track:     metadata.application (applied/not-applied + candidate notes) + tooling
        │
        ▼
  sent status in the shared SQLite jobs table (terminal pipeline state)
```

## Confirmed decisions

| # | Decision | Choice | Rationale |
|---|----------|--------|-----------|
| 1 | **Messaging** | Telegram Bot API behind a pluggable `Sender` protocol; bot token + chat id via `.env` | Simplest integration: free, no phone-number approval, plain HTTP via existing `httpx`. |
| 2 | **Delivery shape** | **Two-part delivery**: (a) text message with job link, description excerpt, cover letter (plain text), and a plain-text resume extract; (b) the actual `.tex` (or compiled PDF if available) sent as a **file attachment** via Telegram `sendDocument` | Raw LaTeX pasted into a text message is useless to the candidate; Telegram natively supports documents, so the candidate gets a usable file plus a readable message. |
| 3 | **Message size** | Split on the template's **section boundaries** (job / description / cover letter / resume extract), send sequentially in order, prefix parts `(n/m)` | Never split mid-sentence or mid-section; sequential sends keep parts in order; prefixes make the assembly obvious. |
| 4 | **Idempotency** | Before sending: refuse if `status == sent` or `metadata.delivery.message_ids` is non-empty, unless `force=true`; record all `message_ids` + `sent_at` in `metadata.delivery` | Retrying after a network error (or a manual re-run) must not double-send to the candidate. |
| 5 | **Sent tracking** | Same SQLite `jobs` store, `sent` status (terminal); no separate `/sent` API resource | One store and one tooling surface, consistent with Stage 1's queues; sent is a status of the same rows (`GET /jobs?status=sent`). |
| 6 | **Applied state** | Candidate records `{applied: bool, notes, updated_at}` in `metadata.application` via `POST /jobs/{id}/application-status`; notes also land in `metadata.notes` history | Per plan.md: candidate marks applied/not-applied with notes stored in job metadata for future analysis; avoids growing the status enum with candidate-controlled states. |

## Design details

### Entry point (per `./pipeline-integration.md` API surface)
- `POST /jobs/{id}/send` (`?force=true` to override the idempotency guard) — FastAPI route in `app/main.py`.
- `POST /jobs/{id}/application-status` (applied/not-applied + candidate notes) — candidate-facing tracking.
- Substage-only trigger: `GET /jobs/{id}/delivery/preview` runs the compile substage alone (returns the message parts; no send, no transition).
- Batch trigger: `POST /stage4/run?limit=N` sends for up to N `resume_ready` entries with both resume and cover-letter artifacts on disk; `?dry_run=true` reports the selection.
- `GET /jobs?status=sent` — replaces the previously planned separate `GET /sent` resource.
- CLI: `send <id>`, `send preview <id>`, `send run [--limit N]`, `application-status <id> <applied|not-applied> <notes>`, `view-sent`.
- Queue selection: `resume_ready` entries with resume + cover-letter artifacts on disk, per the stage trigger & queue-selection contract in `./pipeline-integration.md`. Triggering is manual per entry or via explicit batch run (orchestration principle in `./pipeline-integration.md`).

### Compilation (`src/outreach/compile.py`)
- `compile_message(entry) -> list[str]` — builds the text message parts from `stage4.message_template` config:
  - job link, job description excerpt (configurable length), cover letter (plain text), plain-text resume extract (bulletpoints/summary, not raw LaTeX — decision 2).
- Splitting per decision 3: split on template section boundaries, never mid-sentence/mid-section; sequential parts prefixed `(n/m)`; each part ≤ 4096 chars (Telegram limit).
- The full resume artifact (`.tex`, or PDF if a compiled one exists next to it) is attached separately via `sendDocument`, not inlined.

### Sending (`src/outreach/send.py`)
- `TelegramSender` behind a `Sender` protocol (a new sender = one class plus one registry entry); uses existing `httpx`, bot token + chat id from `.env`.
- Sends message parts sequentially in order, then the resume document; collects all returned `message_id`s.
- Idempotency per decision 4: refuse when `status == sent` or `metadata.delivery.message_ids` non-empty unless `force=true`; on success set `metadata.delivery = {message_ids, sent_at}` and transition the entry `resume_ready → sent` (transition enforced by the store per the map in `./pipeline-integration.md`).
- The existing placeholder `src/outreach/send_application.py` (`send_application()` returning `True`) is **preserved** — the real flow is `TelegramSender` in `send.py`, consistent with how Stage 1 preserves `fetch_job_listings()`.

### Tracking (`src/outreach/track.py`)
- `POST /jobs/{id}/application-status` records `{applied, notes, updated_at}` in `metadata.application`; appended notes also go to `metadata.notes` history for future analysis (per plan.md).
- Candidate notes feedback round-trips through job entry metadata so future runs can analyze what worked.
- Tooling surfaces sent jobs + application state via `GET /jobs?status=sent` and the CLI `view-sent`.

### Tests (`job-pipeline/tests/`)
- Same isolation rules as the shared contract: mocked `Sender` (recorded fixtures, including an idempotency-refusal case and a multi-part split case), temp-dir SQLite via monkey-patched constant, shared `tests/conftest.py` fixtures, API tests via `TestClient`; `pytest -q` green, no live external calls.

## Implementation steps (in order)

1. Prerequisite: Stages 1–3 (`resume_ready` entries with resume + cover letter artifacts)
2. `src/outreach/compile.py` (template + section-boundary splitting)
3. `src/outreach/send.py` (`TelegramSender` + idempotency + `resume_ready → sent`)
4. `src/outreach/track.py` (application-status + notes round-trip)
5. Entrypoints (API routes + CLI subcommands)
6. Tests; README + memory-bank updates; `pytest -q` green

## Risks / notes

- Telegram message size limit (4096 chars) is handled in `compile.py` via section-boundary splitting; very long descriptions may still need excerpting (configurable).
- Telegram API failures mid-send (some parts sent) leave `metadata.delivery.message_ids` partially filled — the idempotency guard treats any non-empty list as "already delivered" unless `force=true`, so a retry resumes rather than duplicating.
- Candidate notes are free text; keep `metadata.application` schema validation minimal (bool + string + timestamp).


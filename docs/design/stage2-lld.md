# Stage 2 — Low-Level Design (LLD)

Low-level design for **Stage 2 — Matching Resume Generation**. Implements the design in
`./stage2-resume-generation.md` under the cross-stage contract `./pipeline-integration.md`.
This document is the implementation reference for Stage 2 (module map, function signatures,
metadata shapes, section-marker scheme, prompts, API/CLI surface, test plan).

## 1. Module map (final)

```
src/
├── llm/                       # Shared foundation (M2.5, built with Stage 2)
│   ├── __init__.py            # exports complete, LLMClient, LLMError, set_client
│   └── provider.py            # OpenAI-compatible client + mockable complete() seam
├── resume/                    # Stage 2 package (new)
│   ├── __init__.py
│   ├── generate.py            # edit_base_resume(), section markers, artifact IO
│   ├── ats.py                 # score_resume(), score_resume_deterministic(), combine_scores()
│   ├── loop.py                # run_loop() — the only place that transitions status
│   └── stage2.py              # run_stage2(), run_ats_substage(), force_ready()
└── queues/store.py            # + update_metadata() (stage-owned metadata round-trip)
app/main.py                    # + POST /jobs/{id}/resume/{generate,ats,force-ready}, POST /stage2/run
src/queues/cli.py              # + resume-generate, resume-ats, resume-run, resume-force-ready
config/pipeline.json           # stage2.latex_section_markers filled for the real base resume
tests/                         # test_llm, test_resume, test_ats, test_loop, test_stage2 (+ api/cli/store)
```

Substage decomposition (per the modularity contract): `generate.py → edit_base_resume`,
`ats.py → score_resume`, `loop.py → run_loop` (orchestrates the two; the only Stage 2 place
allowed to transition status). Stages never import each other; the store is the only
cross-stage surface.

## 2. Data flow

```
store.list_by_status("accepted")            # incl. metadata.ats.needs_review re-runs
        │  per entry (limit N, resolvable base_resume_path required)
        ▼
resolve_base_resume_path(job, config)       # metadata.base_resume_path → config.base_resume_path
        │
        ▼  ─────────────── per iteration (until threshold or max_iterations) ───────────────
edit_base_resume(job, base_latex, config, feedback)
        │   LLM rewrites ONLY summary/skills/experience section content (JSON)
        │   edits applied programmatically; difflib check: nothing outside spans changed
        ▼
save_resume(job_id, latex)                  # data/resumes/<job_id>.tex (monkeypatchable dir)
        │
        ▼
score_resume(job, resume)                   # LLM screener persona → {score, feedback, ready}
score_resume_deterministic(job, resume, matching)   # keyword coverage, matching weights
combine_scores(llm, deterministic)          # 0.7*llm + 0.3*det → {score, feedback, ready}
        │
        ▼
store.update_metadata(job_id, {"ats": ..., "resume": ...})   # iteration appended, round-trip
        │  combined score >= stage2.ats_ready_threshold
        ▼
store.update_status_and_notes(job_id, resume_ready)          # accepted → resume_ready
        │  else: cap reached (run_to_completion)
        ▼
metadata.ats.needs_review = true            # stays accepted; human promotes via force-ready
```

## 3. Shared foundation — `src/llm/provider.py`

- `LLMClient(base_url=None, api_key=None, model=None, timeout=None, max_retries=None,
  backoff=None, transport=None)`; settings read from `.env` at construction:
  `LLM_BASE_URL` (default `https://api.openai.com/v1`), `LLM_API_KEY`, `LLM_MODEL`
  (default `gpt-4o-mini`), `LLM_TIMEOUT` (60s), `LLM_MAX_RETRIES` (2).
- `complete(system, user, schema=None) -> str` — POST `{base_url}/chat/completions`;
  when `schema` is given the user message gains a schema instruction and the request sets
  `response_format: {"type": "json_object"}`. Retries on 429/5xx/network errors with
  linear backoff; raises `LLMError` when unconfigured (no `LLM_API_KEY`) or exhausted.
- Module-level seam: `set_client(client | None)` / `get_client()` / module `complete()` —
  tests (and Stage 1's `llm` scorer slot) monkey-patch the client; **no live calls in CI**.
- No new dependencies (httpx + python-dotenv already in requirements.txt).

## 4. Store extension — `JobsStore.update_metadata`

`update_metadata(job_id, updates: dict) -> JobEntry` — merges keys into `metadata`
wholesale per key, refreshes `updated_at`, persists. Unlike `edit_job`, stage-owned
registry keys (`metadata.ats`, `metadata.resume`, …) are accepted here: this is the
round-trip surface substages use (store.save's existing-value-wins merge would discard
stage results). Unknown IDs raise `KeyError`; no transition logic involved.

## 5. Section-marker scheme (grounded in `data/Resume.tex`)

The real base resume uses `\begin{rSection}{Name}...\end{rSection}` blocks and a
`\tableEnv{Skills}{...}` brace block. `stage2.latex_section_markers` maps a logical
section name → a **unique begin-marker substring**:

```json
"latex_section_markers": {
  "summary":    "\\begin{rSection}{Summary}",
  "experience": "\\begin{rSection}{Work Experience}",
  "skills":     "\\tableEnv{Skills}{"
}
```

- `find_section_span(latex, marker) -> (start, end) | None` — the **editable content span**:
  after the marker to the matching `\end{rSection}` for begin/end environments, or to the
  matching closing brace (brace counting) for brace-delimited blocks.
- `detect_section_markers(latex)` — fallback when the config is empty: scans
  `\begin{rSection}{X}` / `\tableEnv{X}` blocks and keyword-matches titles
  (summary/experience/skills).
- `locate_sections(latex, config) -> {name: (start, end)}` — config wins; missing spans skipped.
- The LLM returns **content only** (`{summary, skills, experience}` strings); edits are
  applied programmatically right-to-left, then `_validate_edit` (difflib opcodes) asserts
  every diff region lies inside the permitted spans — a diff outside them fails the
  iteration. The LLM never touches LaTeX structure.

## 6. Substage signatures

```python
# generate.py
resolve_base_resume_path(job: JobEntry, config: PipelineConfig) -> Path   # metadata first, config fallback; FileNotFoundError
find_section_span(latex: str, marker: str) -> tuple[int, int] | None
detect_section_markers(latex: str) -> dict[str, str]
locate_sections(latex: str, config: PipelineConfig) -> dict[str, tuple[int, int]]
edit_base_resume(job: JobEntry, base_latex: str, config: PipelineConfig, feedback: str = "") -> str
apply_section_edits(base_latex: str, spans: dict, edits: dict) -> str      # + _validate_edit
save_resume(job_id: str, latex: str) -> Path                               # RESUMES_DIR/<job_id>.tex
load_resume_artifact(job: JobEntry) -> str | None

# ats.py
score_resume(job: JobEntry, resume_text: str) -> dict                      # {score 0-100, feedback, ready}
score_resume_deterministic(job: JobEntry, resume_text: str, matching: MatchingConfig) -> dict
combine_scores(llm_result: dict, deterministic_result: dict) -> dict       # round(0.7*llm + 0.3*det)

# loop.py
run_loop(job: JobEntry, config: PipelineConfig, store: JobsStore, run_to_completion: bool = True) -> dict

# stage2.py
run_stage2(config=None, store=None, limit=None, dry_run=False, run_to_completion=True, job_id=None) -> dict
run_ats_substage(store: JobsStore, job_id: str, config: PipelineConfig | None = None) -> dict
force_ready(store: JobsStore, job_id: str, config: PipelineConfig | None = None) -> JobEntry
```

## 7. Metadata shapes (registered keys, docs/design/pipeline-integration.md)

```jsonc
"metadata": {
  "ats": {                       // appended per iteration (design doc's list shape kept
    "iterations": [              //   under the `iterations` key so needs_review fits)
      {"iteration": 1, "ats_score": 84, "deterministic_score": 71, "score": 80,
       "feedback": "...", "timestamp": "...ISO..."}
    ],
    "needs_review": false
  },
  "resume": {"path": "/abs/data/resumes/<job_id>.tex", "iterations": 2, "ready_at": "...ISO..." | null}
}
```

Note: `stage2-resume-generation.md` describes `metadata.ats` both as a list and as having
`needs_review` — resolved here as an object with `iterations` + `needs_review` (amended in
the design doc). The loop re-reads the last iteration's feedback to seed the next edit
prompt — the plan.md-required round-trip.

## 8. Loop rules (design decisions 3–4)

- Iterations run from `len(metadata.ats.iterations) + 1` up to `max_iterations`
  (or a single iteration when `run_to_completion=False`).
- **Advance** to `resume_ready` only when the combined score ≥ `stage2.ats_ready_threshold`;
  sets `metadata.resume.ready_at` and transitions via the store map (`accepted → resume_ready`).
- **Cap** without the threshold: stays `accepted`, `metadata.ats.needs_review = true`.
  A human promotes via `POST /jobs/{id}/resume/force-ready` (also sets `ready_at`).
  Single-iteration runs never set `needs_review`.
- `run_loop` refuses entries whose stored status is not `accepted` (ValueError);
  unknown IDs raise `KeyError`.
- `run_ats_substage` scores the existing artifact (or the base resume when none) and
  appends an iteration to `metadata.ats` — **no generation, no transition**.

## 9. Prompts

- **Editor** (`generate.py`): system = expert resume editor; rules — edit only the given
  sections, keep real employers/dates, never invent experience, weave job keywords
  naturally, human phrasing (no generic AI tone), valid LaTeX (escape %, &, #).
  User message: job title/company/tags/description (≤ 8000 chars), current section
  contents, candidate profile (skills/experience/education), previous ATS feedback.
  JSON schema `{summary, skills, experience}` (strings).
- **ATS screener** (`ats.py`): system = professional resume screener / tech hiring
  manager; strict but fair, flags missing keywords, misaligned bullets, generic AI tone.
  JSON schema `{score: int 0-100, feedback: string, ready: boolean}`.

## 10. API + CLI surface

| Surface | Call | Notes |
|---------|------|-------|
| API | `POST /jobs/{id}/resume/generate?run_to_completion=` | loop for one accepted entry (404 unknown, 409 not accepted) |
| API | `POST /jobs/{id}/resume/ats` | substage-only scoring (no transition) |
| API | `POST /jobs/{id}/resume/force-ready` | human promotion of `needs_review` (409 on bad transition) |
| API | `POST /stage2/run?limit=&dry_run=` | batch over accepted entries |
| API | `GET /status` | stage2 `implemented: true`, `eligible`, `pending_review` (needs_review count) |
| CLI | `resume-generate <id> [--single]` / `resume-ats <id>` / `resume-force-ready <id>` / `resume-run [--limit N] [--dry-run] [--single]` | same code paths |

## 11. Test plan (no live network)

| File | Coverage |
|------|----------|
| `test_llm.py` | httpx.MockTransport: payload/messages/JSON mode, retries on 5xx, missing key → LLMError, `set_client` seam |
| `test_resume.py` | marker detection + span location on a fixture `.tex`, apply + `_validate_edit` (in/out of span), `edit_base_resume` with fake client, invalid JSON, path resolution, artifact save/load |
| `test_ats.py` | deterministic keyword scoring (hit/miss/weights/feedback), LLM scoring normalization, invalid JSON, `combine_scores` weighting |
| `test_loop.py` | threshold → resume_ready + ready_at; cap → needs_review (stays accepted); feedback round-trip in prompt; single-iteration mode; status guards |
| `test_stage2.py` | selection (accepted incl. needs_review), dry-run, skip without base resume, per-entry error isolation, job_id guards |
| `test_api.py` / `test_cli.py` / `test_store.py` | new routes (incl. 409s), CLI subcommands, `update_metadata` merge/replace |

Fixtures: `tests/fixtures/base_resume.tex` (mini LaTeX with rSection/tableEnv blocks),
`fake_llm` conftest fixture (scripted client, records calls). `pytest -q` green from
`job-pipeline/`.

## 12. Risks / notes

- LLM output quality needs live iteration; the ATS loop is the enforcement mechanism.
- Marker config must match the real `.tex` exactly (markers shipped in both configs).
- `LLM_API_KEY` absent → every Stage 2 call raises `LLMError`; batch records per-entry
  errors and continues (same isolation as Stage 1's per-source errors).
- Artifact paths stored absolute (single-candidate, local pipeline); `data/` is gitignored.

"""Job Pipeline API — Stage 1 unified surface (plus shared admin tools).

Implements the unified API surface from docs/design/pipeline-integration.md:
full Stage-1 flow triggers (POST /ingest, POST /stage1/run), the jobs
resource (list/show/accept/reject/note/PATCH), the observability summary
(GET /status) and the static admin UI (GET /ui). Stages 2-4 extend the
same jobs resource; they never get parallel resources.


"""
import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from src.models import JobStatus
from src.queues import store as store_module
from src.queues.store import JobsStore, edit_job
from src.stage1 import run_stage1
from src.resume.ats import (
    combine_scores,
    score_resume,
    score_resume_deterministic,
)
from src.resume.generate import load_resume_artifact, resolve_base_resume_path
from src.resume.stage2 import force_ready, run_ats_substage, run_stage2
from src.queues.cli import _entry_brief

app = FastAPI(title="Job Pipeline API")

STATIC_UI_PATH = Path(__file__).resolve().parent / "static" / "index.html"


def get_store() -> JobsStore:
    """Create a store from the (monkey-patchable) module DB path."""
    return JobsStore(store_module.DB_PATH)


class IngestRequest(BaseModel):
    """Body for POST /ingest: full Stage-1 flow for one source."""

    source: str
    limit: int | None = None
    dry_run: bool = False


class NoteRequest(BaseModel):
    """Body for POST /jobs/{id}/note."""

    note: str


class EditRequest(BaseModel):
    """Body for PATCH /jobs/{id}: whitelist field updates."""

    updates: dict = Field(default_factory=dict)


@app.get("/")
async def health_check():
    """Health check."""
    return {"status": "ok"}


@app.post("/ingest")
async def ingest(request: IngestRequest):
    """Run the full Stage-1 flow for one source: fetch -> parse -> score -> queue."""
    try:
        summary = run_stage1(store=get_store(), source_name=request.source,
                             limit=request.limit, dry_run=request.dry_run)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return summary


@app.post("/stage1/run")
async def stage1_run(limit: int | None = None, dry_run: bool = False):
    """Batch Stage-1 run over all enabled sources."""
    return run_stage1(store=get_store(), limit=limit, dry_run=dry_run)


@app.get("/status")
async def status():
    """Pipeline summary: queue counts + stage flags."""
    store = get_store()
    try:
        counts = store.count_by_status()
        accepted = store.list_by_status(JobStatus.ACCEPTED.value)
        needs_review = sum(
            1
            for entry in accepted
            if (entry.metadata.get("ats") or {}).get("needs_review")
        )
        return {
            "queues": counts,
            "stages": {
                "stage1": {"implemented": True, "pending_review": counts.get("new", 0)},
                "stage2": {"implemented": True,
                           "eligible": counts.get("accepted", 0),
                           "pending_review": needs_review},
                "stage3": {"implemented": False,
                           "eligible": counts.get("resume_ready", 0)},
                "stage4": {"implemented": False,
                           "eligible": counts.get("resume_ready", 0)},
            },
        }
    finally:
        store.close()


@app.get("/jobs")
async def list_jobs(status: str = "new", limit: int | None = None):
    """List entries with the given status, best score first."""
    store = get_store()
    try:
        entries = store.list_by_status(status, limit=limit)
        return [_entry_brief(entry) for entry in entries]
    finally:
        store.close()


@app.get("/jobs/{job_id}")
async def get_job(job_id: str):
    """Return one full job entry."""
    store = get_store()
    try:
        entry = store.get(job_id)
        if entry is None:
            raise HTTPException(status_code=404, detail=f"Unknown job id: {job_id}")
        return JSONResponse(json.loads(json.dumps(entry.model_dump(mode="json"))))
    finally:
        store.close()


@app.post("/jobs/{job_id}/accept")
async def accept_job(job_id: str):
    """Manually accept a new or rejected job (transition-map enforced)."""
    return _transition(job_id, JobStatus.ACCEPTED)


@app.post("/jobs/{job_id}/reject")
async def reject_job(job_id: str):
    """Reject a new or (pre-resume_ready) accepted job."""
    return _transition(job_id, JobStatus.REJECTED)


def _transition(job_id: str, target: JobStatus):
    """Shared guarded status transition for the manual accept/reject routes."""
    store = get_store()
    try:
        entry = store.update_status_and_notes(job_id, new_status=target)
    except store_module.InvalidTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    finally:
        store.close()
    return JSONResponse(json.loads(json.dumps(entry.model_dump(mode="json"))))


@app.post("/jobs/{job_id}/note")
async def note_job(job_id: str, request: NoteRequest):
    """Append a human note to metadata.notes."""
    store = get_store()
    try:
        entry = store.update_status_and_notes(job_id, notes=request.note)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    finally:
        store.close()
    return JSONResponse(json.loads(json.dumps(entry.model_dump(mode="json"))))


@app.patch("/jobs/{job_id}")
async def patch_job(job_id: str, request: EditRequest):
    """Guarded whitelist edit: human-owned fields only."""
    store = get_store()
    try:
        entry = edit_job(store, job_id, request.updates)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    finally:
        store.close()
    return JSONResponse(json.loads(json.dumps(entry.model_dump(mode="json"))))


class ResumeAction(BaseModel):
    """Empty body placeholder for the Stage-2 per-job resume routes."""

    pass


@app.post("/stage2/run")
async def stage2_run(limit: int | None = None, dry_run: bool = False):
    """Batch Stage-2 run over accepted entries (generate -> ATS loop)."""
    return run_stage2(store=get_store(), limit=limit, dry_run=dry_run)


@app.post("/jobs/{job_id}/resume/generate")
async def resume_generate(job_id: str, run_to_completion: bool = True):
    """Run the Stage-2 loop for one accepted job (generate -> ATS -> re-edit)."""
    try:
        return run_stage2(store=get_store(), job_id=job_id,
                          run_to_completion=run_to_completion)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/jobs/{job_id}/resume/ats")
async def resume_ats(job_id: str):
    """Substage-only ATS scoring: appends to metadata.ats; no transition."""
    try:
        return run_ats_substage(get_store(), job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/jobs/{job_id}/resume/force-ready")
async def resume_force_ready(job_id: str):
    """Human promotion of a needs_review (or any accepted) entry to resume_ready."""
    try:
        entry = force_ready(get_store(), job_id)
    except store_module.InvalidTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return JSONResponse(json.loads(json.dumps(entry.model_dump(mode="json"))))


@app.get("/ui", response_class=HTMLResponse)
async def admin_ui():
    """Serve the dependency-free static admin UI."""
    return HTMLResponse(STATIC_UI_PATH.read_text(encoding="utf-8"))


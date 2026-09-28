"""Stage 2 orchestrator: accepted entries -> tailored resumes -> resume_ready.

run_stage2() is the single entry point shared by the FastAPI routes
(POST /stage2/run, POST /jobs/{id}/resume/generate) and the CLI
(`resume-run`, `resume-generate`). It orchestrates Stage 2's own
substages only (generate, ats, loop) and never imports another stage's
package. Selection: accepted entries with a resolvable base_resume_path,
including needs_review re-runs (docs/design/stage2-resume-generation.md).
"""

import logging
from datetime import datetime, timezone

from src.config import PipelineConfig, load_config
from src.models import JobEntry, JobStatus
from src.queues.store import JobsStore
from src.resume.ats import (
    combine_scores,
    score_resume,
    score_resume_deterministic,
)
from src.resume.generate import (
    load_resume_artifact,
    resolve_base_resume_path,
    save_resume,
)
from src.resume.loop import run_loop

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _select_entries(
    store: JobsStore, config: PipelineConfig, limit: int | None, job_id: str | None
) -> list[JobEntry]:
    """Stage 2 queue selection: accepted entries (incl. needs_review)."""
    if job_id is not None:
        entry = store.get(job_id)
        if entry is None:
            raise KeyError(f"Unknown job id: {job_id}")
        if entry.status != JobStatus.ACCEPTED:
            raise ValueError(
                f"Job {job_id} is not accepted (status: {entry.status.value})"
            )
        return [entry]
    return store.list_by_status(JobStatus.ACCEPTED.value, limit=limit)


def run_stage2(
    config: PipelineConfig | None = None,
    store: JobsStore | None = None,
    limit: int | None = None,
    dry_run: bool = False,
    run_to_completion: bool = True,
    job_id: str | None = None,
) -> dict:
    """Run the Stage-2 flow over the selected accepted entries.

    Args:
        config: pipeline config; loaded from the config file when None.
        store: jobs store; a default DB-path store is created when None.
        limit: cap the number of batch entries processed.
        dry_run: report the selection, persist nothing.
        run_to_completion: pass-through to run_loop (threshold or cap
            vs. a single iteration).
        job_id: restrict the run to one accepted entry (the per-job
            generate route case).

    Returns:
        dict: run summary with selection, per-entry results and errors.
    """
    if config is None:
        config = load_config()
    if store is None:
        store = JobsStore()

    entries = _select_entries(store, config, limit, job_id)
    summary: dict = {
        "selected": 0,
        "processed": 0,
        "resume_ready": 0,
        "needs_review": 0,
        "skipped": [],
        "errors": [],
        "results": [],
        "dry_run": dry_run,
    }

    for entry in entries:
        summary["selected"] += 1
        try:
            resolve_base_resume_path(entry, config)
        except (FileNotFoundError, ValueError) as exc:
            summary["skipped"].append({"job_id": entry.id, "reason": str(exc)})
            continue
        if dry_run:
            continue
        try:
            result = run_loop(entry, config, store, run_to_completion=run_to_completion)
        except Exception as exc:  # noqa: BLE001 - one entry never fails the batch
            logger.warning("Stage-2 run failed for %s: %s", entry.id, exc)
            summary["errors"].append({"job_id": entry.id, "error": str(exc)})
            continue
        summary["processed"] += 1
        summary["results"].append(result)
        if result.get("status") == JobStatus.RESUME_READY.value:
            summary["resume_ready"] += 1
        elif result.get("needs_review"):
            summary["needs_review"] += 1

    return summary


def run_ats_substage(
    store: JobsStore, job_id: str, config: PipelineConfig | None = None
) -> dict:
    """Substage-only ATS scoring for one entry (no generation, no transition).

    Scores the existing tailored artifact when present, otherwise the
    base resume, and appends an iteration entry to metadata.ats via the
    store (the round-trip surface). Raises KeyError for unknown IDs.
    """
    if config is None:
        config = load_config()
    entry = store.get(job_id)
    if entry is None:
        raise KeyError(f"Unknown job id: {job_id}")

    resume_text = load_resume_artifact(entry)
    if resume_text is None:
        resume_text = resolve_base_resume_path(entry, config).read_text(
            encoding="utf-8"
        )

    llm_result = score_resume(entry, resume_text)
    det_result = score_resume_deterministic(entry, resume_text, config.matching)
    combined = combine_scores(llm_result, det_result)

    ats_meta = dict(entry.metadata.get("ats") or {})
    iterations = list(ats_meta.get("iterations") or [])
    iteration_number = len(iterations) + 1
    iterations.append(
        {
            "iteration": iteration_number,
            "ats_score": llm_result["score"],
            "deterministic_score": det_result["score"],
            "score": combined["score"],
            "feedback": combined["feedback"],
            "timestamp": _now(),
        }
    )
    store.update_metadata(
        job_id, {"ats": {"iterations": iterations, "needs_review": False}}
    )
    return {
        "job_id": job_id,
        "iteration": iteration_number,
        "ats_score": llm_result["score"],
        "deterministic_score": det_result["score"],
        "score": combined["score"],
        "feedback": combined["feedback"],
    }


def force_ready(
    store: JobsStore, job_id: str, config: PipelineConfig | None = None
) -> JobEntry:
    """Human promotion of an accepted entry to resume_ready.

    The needs_review path (design decision 4): a human promotes a capped
    entry via POST /jobs/{id}/resume/force-ready. Transition-map enforced
    (accepted -> resume_ready); InvalidTransitionError propagates. Sets
    metadata.resume.ready_at when a tailored artifact exists.
    """
    updated = store.update_status_and_notes(job_id, new_status=JobStatus.RESUME_READY)
    resume_meta = dict(updated.metadata.get("resume") or {})
    if resume_meta.get("path"):
        resume_meta.setdefault("ready_at", _now())
        updated = store.update_metadata(job_id, {"resume": resume_meta})
    return updated

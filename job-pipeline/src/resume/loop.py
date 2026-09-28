"""Stage 2 substage: the generate -> score -> feedback loop.

run_loop() is the only Stage 2 place allowed to transition status. Per
iteration: edit the base resume (seeded with the previous ATS feedback —
the metadata.ats round-trip required by plan.md), persist the artifact on
disk, score it (LLM + deterministic), and append the iteration entry to
metadata.ats via the store. Advancement to resume_ready happens ONLY when
the combined ATS score meets stage2.ats_ready_threshold; otherwise the
loop continues until stage2.max_iterations, then sets
metadata.ats.needs_review = true and stops (design decision 4).
"""

import logging
from datetime import datetime, timezone

from src.config import PipelineConfig
from src.models import JobEntry, JobStatus
from src.queues.store import JobsStore
from src.resume.ats import combine_scores, score_resume, score_resume_deterministic
from src.resume.generate import (
    edit_base_resume,
    resolve_base_resume_path,
    save_resume,
)

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _last_feedback(ats_meta: dict) -> str:
    """Return the previous iteration's feedback (the plan.md round-trip)."""
    iterations = (ats_meta or {}).get("iterations") or []
    if not iterations:
        return ""
    return str(iterations[-1].get("feedback") or "")


def run_loop(
    job: JobEntry,
    config: PipelineConfig,
    store: JobsStore,
    run_to_completion: bool = True,
) -> dict:
    """Run the Stage-2 loop for one accepted job entry.

    Args:
        job: the accepted JobEntry (re-fetched from the store by id).
        config: pipeline config.
        store: the shared jobs store.
        run_to_completion: run iterations until the threshold or the cap;
            when False, run a single generate+score iteration.

    Returns:
        dict: {job_id, iterations, score, status, needs_review, error?}.
    """
    stored = store.get(job.id)
    if stored is None:
        raise KeyError(f"Unknown job id: {job.id}")
    if stored.status != JobStatus.ACCEPTED:
        raise ValueError(
            f"Job {stored.id} is not accepted (status: {stored.status.value})"
        )

    base_path = resolve_base_resume_path(stored, config)
    base_latex = base_path.read_text(encoding="utf-8")

    ats_meta = dict(stored.metadata.get("ats") or {})
    start_iteration = len(ats_meta.get("iterations") or [])
    max_iterations = config.stage2.max_iterations
    threshold = config.stage2.ats_ready_threshold
    target = start_iteration + (max_iterations if run_to_completion else 1)

    iterations = list(ats_meta.get("iterations") or [])
    last_score: int | None = None
    error: str | None = None

    for iteration in range(start_iteration + 1, target + 1):
        feedback = _last_feedback({"iterations": iterations})
        try:
            tailored = edit_base_resume(stored, base_latex, config, feedback=feedback)
            artifact = save_resume(stored.id, tailored)
            llm_result = score_resume(stored, tailored)
            det_result = score_resume_deterministic(stored, tailored, config.matching)
        except Exception as exc:  # noqa: BLE001 - record per-iteration errors
            logger.warning("Iteration %s failed for %s: %s", iteration, stored.id, exc)
            error = str(exc)
            break

        combined = combine_scores(llm_result, det_result)
        iterations.append(
            {
                "iteration": iteration,
                "ats_score": llm_result["score"],
                "deterministic_score": det_result["score"],
                "score": combined["score"],
                "feedback": combined["feedback"],
                "timestamp": _now(),
            }
        )
        last_score = combined["score"]
        store.update_metadata(
            stored.id,
            {
                "ats": {"iterations": iterations, "needs_review": False},
                "resume": {"path": str(artifact), "iterations": iteration},
            },
        )
        if combined["score"] >= threshold:
            break
        if not run_to_completion:
            break

    if last_score is not None and last_score >= threshold:
        store.update_metadata(
            stored.id,
            {
                "resume": {
                    "path": str(artifact),
                    "iterations": len(iterations),
                    "ready_at": _now(),
                }
            },
        )
        updated = store.update_status_and_notes(
            stored.id, new_status=JobStatus.RESUME_READY
        )
        return {
            "job_id": stored.id,
            "iterations": len(iterations),
            "score": last_score,
            "status": updated.status.value,
            "needs_review": False,
            "error": error,
        }

    needs_review = False
    if error is None and run_to_completion and last_score is not None:
        # Cap reached without meeting the threshold (design decision 4):
        # stay accepted, flag for human review.
        needs_review = True
        store.update_metadata(
            stored.id, {"ats": {"iterations": iterations, "needs_review": True}}
        )

    return {
        "job_id": stored.id,
        "iterations": len(iterations),
        "score": last_score,
        "status": JobStatus.ACCEPTED.value,
        "needs_review": needs_review,
        "error": error,
    }

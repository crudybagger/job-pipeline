"""Stage 1 orchestrator: fetch -> parse -> score -> queue.

run_stage1() is the single entry point shared by the FastAPI routes
(POST /ingest, POST /stage1/run) and the CLI (`run` subcommand). It
orchestrates Stage 1's own substages only (ingestion, parsing, matching)
and never imports another stage's package.
"""

import logging

from src.config import PipelineConfig, SourceConfig, load_config
from src.ingestion.ingest import fetch_from_source
from src.matching.match import compute_match_score
from src.models import JobStatus
from src.parsing.parse import parse_job_listing
from src.queues.store import JobsStore

logger = logging.getLogger(__name__)


def _classify(score: int, threshold: int, auto_accept: bool) -> JobStatus:
    """Route a scored job into its queue status.

    score >= threshold -> accepted when auto-accept is enabled, otherwise
    new (human review first, per the review-oriented scope). Below the
    threshold -> rejected.
    """
    if score >= threshold:
        return JobStatus.ACCEPTED if auto_accept else JobStatus.NEW
    return JobStatus.REJECTED


def run_stage1(
    config: PipelineConfig | None = None,
    store: JobsStore | None = None,
    source_name: str | None = None,
    limit: int | None = None,
    dry_run: bool = False,
) -> dict:
    """Run the full Stage-1 flow over the enabled source(s).

    Per source: fetch raw listings, parse each into a JobEntry, compute
    the match score against the candidate profile, classify into its
    queue status and persist via the store. A fetch error on one source
    is recorded in the summary and never fails the batch.

    Args:
        config: pipeline config; loaded from the config file when None.
        store: jobs store; a default DB-path store is created when None.
        source_name: restrict the run to one source (POST /ingest case).
        limit: cap the number of listings processed per source.
        dry_run: fetch/parse/score everything but persist nothing.

    Returns:
        dict: run summary with per-source counts and totals.
    """
    if config is None:
        config = load_config()
    if store is None:
        store = JobsStore()

    threshold = config.matching.match_threshold
    auto_accept = config.matching.auto_accept_above_threshold
    base_resume_path = config.base_resume_path

    sources = [s for s in config.sources if s.enabled]
    if source_name is not None:
        sources = [s for s in sources if s.name.lower() == source_name.lower()]
        if not sources:
            raise ValueError(f"No enabled source named: {source_name}")

    summary: dict = {
        "sources": [],
        "ingested": 0,
        "accepted": 0,
        "rejected": 0,
        "new": 0,
        "dry_run": dry_run,
    }

    for source in sources:
        source_result: dict = {"source": source.name, "ingested": 0, "accepted": 0,
                               "rejected": 0, "new": 0}
        try:
            raw_listings = fetch_from_source(source)
        except Exception as exc:  # noqa: BLE001 - one broken board never fails the batch
            logger.warning("Source %s failed: %s", source.name, exc)
            source_result["error"] = str(exc)
            summary["sources"].append(source_result)
            continue

        for raw in raw_listings:
            if limit is not None and source_result["ingested"] >= limit:
                break
            try:
                entry = parse_job_listing(raw, base_resume_path=base_resume_path)
                score, breakdown = compute_match_score(
                    config.candidate_profile, entry, config.matching
                )
                entry.metadata["score"] = score
                entry.metadata["score_breakdown"] = breakdown
                entry.status = _classify(score, threshold, auto_accept)
            except Exception as exc:  # noqa: BLE001 - skip malformed listings
                logger.warning("Skipping malformed listing from %s: %s", source.name, exc)
                continue

            source_result["ingested"] += 1
            if not dry_run:
                store.save(entry)
            source_result[entry.status.value] += 1

        summary["sources"].append(source_result)
        for key in ("ingested", "accepted", "rejected", "new"):
            summary[key] += source_result[key]

    return summary


__all__ = ["run_stage1", "SourceConfig"]

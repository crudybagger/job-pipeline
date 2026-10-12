"""Stage 2 live check — real LLM calls against real queued jobs, run manually.

Runs the Stage-2 flow (generate -> ATS score -> feedback loop) over accepted
entries from the real store with the real config, and prints the run summary
plus per-entry results and the tailored-artifact locations. NOT part of the
pytest suite (testing contract: no live network in tests).

Requires `LLM_API_KEY` (+ optional `LLM_BASE_URL` / `LLM_MODEL`) in
`job-pipeline/.env`. Per-entry errors (e.g. LLMError when the key is missing
or the API is unreachable) are reported per entry and are not fatal — same
isolation as Stage 1's per-source errors.

Usage (from job-pipeline/):
    .venv/bin/python scripts/stage2_live.py                      # batch over accepted entries
    .venv/bin/python scripts/stage2_live.py --job-id <id>        # one accepted entry
    .venv/bin/python scripts/stage2_live.py --single             # one generate+score iteration
    .venv/bin/python scripts/stage2_live.py --dry-run            # report the selection, persist nothing
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import load_config  # noqa: E402
from src.models import JobStatus  # noqa: E402
from src.queues.store import JobsStore  # noqa: E402
from src.resume.stage2 import run_stage2  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job-id", default=None, help="restrict to one accepted job id")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--single", action="store_true",
                        help="run a single generate+score iteration instead of the loop")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--top", type=int, default=10,
                        help="how many resume-ready entries to list afterwards")
    args = parser.parse_args()

    config = load_config()
    store = JobsStore()
    try:
        try:
            summary = run_stage2(
                config, store, limit=args.limit, dry_run=args.dry_run,
                run_to_completion=not args.single, job_id=args.job_id,
            )
        except KeyError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1

        print("=== Stage 2 live run summary ===")
        print(f"dry_run: {summary['dry_run']}")
        print(f"selected={summary['selected']} processed={summary['processed']} "
              f"resume_ready={summary['resume_ready']} "
              f"needs_review={summary['needs_review']}")
        for skip in summary["skipped"]:
            print(f"  SKIPPED {skip['job_id']}: {skip['reason']}")
        for err in summary["errors"]:
            print(f"  ERROR   {err['job_id']}: {err['error']}")
        for result in summary["results"]:
            line = (f"  {result['job_id']}: iterations={result['iterations']} "
                    f"score={result['score']} status={result['status']}")
            if result.get("needs_review"):
                line += "  (needs_review — promote via resume-force-ready)"
            if result.get("error"):
                line += f"  ERROR: {result['error']}"
            print(line)

        if args.dry_run:
            return 0

        entries = store.list_by_status(JobStatus.RESUME_READY.value, limit=args.top)
        if entries:
            print(f"\n=== {len(entries)} resume-ready entries ===")
            for entry in entries:
                resume_meta = entry.metadata.get("resume") or {}
                ats_meta = entry.metadata.get("ats") or {}
                print(f"  {entry.id}: {entry.title} @ {entry.company_name}")
                print(f"      artifact: {resume_meta.get('path') or 'n/a'}")
                print(f"      iterations: {resume_meta.get('iterations')}  "
                      f"ats entries: {len(ats_meta.get('iterations') or [])}")
        return 0
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())

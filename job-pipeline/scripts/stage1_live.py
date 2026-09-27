"""Stage 1 live isolation check — real web data, run manually.

Runs the full Stage-1 flow (fetch -> parse -> score -> queue) against the
real job boards with the real config and prints the run summary plus the
top scored jobs. NOT part of the pytest suite (testing contract: no live
network in tests). Network failures per source (e.g. the Bundesagentur
für Arbeit endpoint returns 403 from datacenter IPs) are reported per
source and are not fatal.

Usage (from job-pipeline/):
    .venv/bin/python scripts/stage1_live.py            # all enabled sources
    .venv/bin/python scripts/stage1_live.py --dry-run  # nothing persisted
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import load_config  # noqa: E402
from src.models import JobStatus  # noqa: E402
from src.queues.store import JobsStore  # noqa: E402
from src.stage1 import run_stage1  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default=None, help="restrict to one source name")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--top", type=int, default=10, help="how many top jobs to show")
    args = parser.parse_args()

    config = load_config()
    store = JobsStore()
    try:
        summary = run_stage1(
            config, store, source_name=args.source, limit=args.limit,
            dry_run=args.dry_run,
        )
        print("=== Stage 1 live run summary ===")
        print(f"dry_run: {summary['dry_run']}")
        for source in summary["sources"]:
            line = (f"  {source['source']}: ingested={source['ingested']} "
                    f"accepted={source['accepted']} new={source['new']} "
                    f"rejected={source['rejected']}")
            if source.get("error"):
                line += f"  ERROR: {source['error']}"
            print(line)
        print(f"TOTAL ingested={summary['ingested']} accepted={summary['accepted']} "
              f"new={summary['new']} rejected={summary['rejected']}")

        if args.dry_run:
            return 0

        for status in (JobStatus.NEW, JobStatus.ACCEPTED):
            entries = store.list_by_status(status, limit=args.top)
            if not entries:
                continue
            print(f"\n=== Top {len(entries)} {status.value} jobs ===")
            for entry in entries:
                score = entry.metadata.get("score")
                print(f"  [{score}] {entry.title} @ {entry.company_name} "
                      f"({entry.location or 'n/a'}) via {entry.source}")
                print(f"      {entry.source_url}")
        return 0
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())

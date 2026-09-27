"""One-off analysis of the rejected list for threshold re-tuning (plan.md)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.queues.store import JobsStore  # noqa: E402


def main() -> None:
    store = JobsStore()
    try:
        entries = store.list_by_status("rejected", limit=10)
        for entry in entries:
            breakdown = entry.metadata.get("score_breakdown", {})
            print(
                f"score={entry.metadata.get('score')} | {entry.title[:55]!r} | "
                f"loc={entry.location[:25]!r}"
            )
            print(
                f"   exp={breakdown.get('experience')} pros={breakdown.get('prospects')} "
                f"edu={breakdown.get('education')} gate={breakdown.get('location_reason')} "
                f"skills={breakdown.get('matched_skills', [])[:6]}"
            )
        scores = [e.metadata.get("score", 0) for e in store.list_by_status("rejected")]
        if scores:
            scores.sort(reverse=True)
            print("\ntop rejected scores:", scores[:15])
            print("median rejected score:", scores[len(scores) // 2])
    finally:
        store.close()


if __name__ == "__main__":
    main()

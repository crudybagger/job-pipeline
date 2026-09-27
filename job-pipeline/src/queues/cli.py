"""Stage 1 interactive CLI tooling over the jobs store and Stage-1 flow.

Usage (from job-pipeline/):
    python -m src.queues.cli status
    python -m src.queues.cli view new
    python -m src.queues.cli view-accepted
    python -m src.queues.cli show <id>
    python -m src.queues.cli accept <id>
    python -m src.queues.cli reject <id>
    python -m src.queues.cli note <id> <text>
    python -m src.queues.cli edit <id> title="New title" location=Remote
    python -m src.queues.cli run [--source remotive] [--limit 50] [--dry-run]

`--config PATH` selects a config file for the run subcommand. The edit
subcommand only accepts whitelist fields (same as PATCH /jobs/{id}).


"""
import argparse
import json
import sys

from src.config import load_config
from src.models import JobStatus
from src.queues.store import JobsStore, edit_job
from src.stage1 import run_stage1


def _entry_brief(entry) -> dict:
    """Compact JSON-serializable view of a job entry for listings."""
    data = entry.model_dump(mode="json")
    metadata = data.get("metadata") or {}
    return {
        "id": data["id"],
        "title": data.get("title"),
        "company_name": data.get("company_name"),
        "location": data.get("location"),
        "source": data.get("source"),
        "status": data.get("status"),
        "score": metadata.get("score"),
        "url": data.get("source_url"),
    }


def cmd_status(store: JobsStore) -> str:
    """Pipeline summary: queue counts."""
    return json.dumps({"queues": store.count_by_status()}, indent=2)


def cmd_view(store: JobsStore, status: str, limit: int | None = None) -> str:
    """List entries with the given status."""
    entries = store.list_by_status(status, limit=limit)
    return json.dumps([_entry_brief(entry) for entry in entries], indent=2)


def cmd_show(store: JobsStore, job_id: str) -> str:
    """Show one full entry."""
    entry = store.get(job_id)
    if entry is None:
        raise KeyError(f"Unknown job id: {job_id}")
    return json.dumps(entry.model_dump(mode="json"), indent=2)


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser (kept separate for testability)."""
    parser = argparse.ArgumentParser(prog="src.queues.cli", description=__doc__)
    parser.add_argument("--config", dest="config_path", default=None)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status")

    view = sub.add_parser("view")
    view.add_argument("status", choices=[s.value for s in JobStatus])
    view.add_argument("--limit", type=int, default=None)

    for name in ("view-accepted", "view-rejected"):
        view_alias = sub.add_parser(name)
        view_alias.add_argument("--limit", type=int, default=None)

    show = sub.add_parser("show")
    show.add_argument("job_id")

    for name in ("accept", "reject"):
        action = sub.add_parser(name)
        action.add_argument("job_id")

    note = sub.add_parser("note")
    note.add_argument("job_id")
    note.add_argument("text")

    edit = sub.add_parser("edit")
    edit.add_argument("job_id")
    edit.add_argument("updates", nargs="+", help='field=value pairs, e.g. title="New title"')

    run = sub.add_parser("run")
    run.add_argument("--source", dest="source", default=None)
    run.add_argument("--limit", type=int, default=None)
    run.add_argument("--dry-run", action="store_true")

    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns a process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)

    store = JobsStore()
    try:
        if args.command == "status":
            print(cmd_status(store))
        elif args.command == "view":
            print(cmd_view(store, args.status, limit=args.limit))
        elif args.command == "view-accepted":
            print(cmd_view(store, JobStatus.ACCEPTED.value, limit=args.limit))
        elif args.command == "view-rejected":
            print(cmd_view(store, JobStatus.REJECTED.value, limit=args.limit))
        elif args.command == "show":
            print(cmd_show(store, args.job_id))
        elif args.command == "accept":
            entry = store.update_status_and_notes(
                args.job_id, new_status=JobStatus.ACCEPTED
            )
            print(json.dumps(_entry_brief(entry), indent=2))
        elif args.command == "reject":
            entry = store.update_status_and_notes(
                args.job_id, new_status=JobStatus.REJECTED
            )
            print(json.dumps(_entry_brief(entry), indent=2))
        elif args.command == "note":
            entry = store.update_status_and_notes(args.job_id, notes=args.text)
            print(json.dumps(entry.model_dump(mode="json")["metadata"]["notes"], indent=2))
        elif args.command == "edit":
            updates: dict[str, str] = {}
            for pair in args.updates:
                if "=" not in pair:
                    raise ValueError(f"Expected field=value, got: {pair}")
                key, value = pair.split("=", 1)
                updates[key.strip()] = value.strip().strip('"').strip("'")
            entry = edit_job(store, args.job_id, updates)
            print(json.dumps(_entry_brief(entry), indent=2))
        elif args.command == "run":
            config = load_config(args.config_path)
            summary = run_stage1(
                config,
                store,
                source_name=args.source,
                limit=args.limit,
                dry_run=args.dry_run,
            )
            print(json.dumps(summary, indent=2))
    except KeyError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    finally:
        store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

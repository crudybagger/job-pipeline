"""Stage 1 persistent queue store: SQLite jobs table.

The single cross-stage store (docs/design/pipeline-integration.md): one
row per job entry, the stable job ID is the primary key, entries are
stored as JSON payloads plus indexed columns (status, score, created_at)
for querying. update_status_and_notes enforces the status transition map.
Stages never import each other — they communicate only through this
store plus the metadata registry and the transition map.
"""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from src.models import JobEntry, JobStatus

# Module constant so tests can monkey-patch it to a temp directory.
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "queues.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
  id         TEXT PRIMARY KEY,
  status     TEXT NOT NULL,
  score      REAL NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  payload    TEXT NOT NULL
);
"""

# Status transition map (docs/design/pipeline-integration.md). Stage 1
# owns new/accepted/rejected; accepted -> resume_ready is Stage 2's and
# resume_ready -> sent is Stage 4's transition. sent is terminal.
TRANSITIONS: dict[str, set[str]] = {
    JobStatus.NEW.value: {JobStatus.ACCEPTED.value, JobStatus.REJECTED.value},
    JobStatus.REJECTED.value: {JobStatus.ACCEPTED.value},
    JobStatus.ACCEPTED.value: {
        JobStatus.REJECTED.value,
        JobStatus.RESUME_READY.value,
    },
    JobStatus.RESUME_READY.value: {JobStatus.SENT.value},
    JobStatus.SENT.value: set(),
}


class InvalidTransitionError(ValueError):
    """Raised when a status change is not allowed by the transition map."""


def _now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


class JobsStore:
    """SQLite-backed persistent jobs store."""

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path is not None else DB_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path))
        self._conn.execute(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        self._conn.close()

    def save(self, entry: JobEntry) -> JobEntry:
        """Insert or update a job entry (idempotent re-ingest).

        A new row gets the entry's status. An existing row keeps its
        status (ingest never demotes an already-classified job) and
        merges metadata, with existing non-empty values winning so
        human notes survive re-ingestion.
        """
        existing = self.get(entry.id)
        now = _now()
        if existing is None:
            payload = entry.model_dump(mode="json")
            self._conn.execute(
                "INSERT INTO jobs (id, status, score, created_at, updated_at, payload) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    entry.id,
                    entry.status.value,
                    float(entry.metadata.get("score") or 0),
                    now,
                    now,
                    json.dumps(payload),
                ),
            )
            self._conn.commit()
            return entry

        merged_metadata = dict(existing.metadata)
        for key, value in entry.metadata.items():
            if value or key not in merged_metadata:
                merged_metadata[key] = value
        updated = entry.model_copy(
            update={"status": existing.status, "metadata": merged_metadata}
        )
        self._conn.execute(
            "UPDATE jobs SET status = ?, score = ?, updated_at = ?, payload = ? "
            "WHERE id = ?",
            (
                existing.status.value,
                float(merged_metadata.get("score") or 0),
                now,
                json.dumps(updated.model_dump(mode="json")),
                existing.id,
            ),
        )
        self._conn.commit()
        return updated

    def get(self, job_id: str) -> JobEntry | None:
        """Return one entry by ID, or None."""
        row = self._conn.execute(
            "SELECT payload FROM jobs WHERE id = ?", (job_id,)
        ).fetchone()
        if row is None:
            return None
        return JobEntry.model_validate(json.loads(row[0]))

    def list_by_status(
        self, status: JobStatus | str, limit: int | None = None
    ) -> list[JobEntry]:
        """List entries with the given status, best score first."""
        status_value = status.value if isinstance(status, JobStatus) else str(status)
        query = (
            "SELECT payload FROM jobs WHERE status = ? "
            "ORDER BY score DESC, created_at DESC"
        )
        params: tuple = (status_value,)
        if limit is not None:
            query += " LIMIT ?"
            params = (status_value, int(limit))
        rows = self._conn.execute(query, params).fetchall()
        return [JobEntry.model_validate(json.loads(row[0])) for row in rows]

    def count_by_status(self) -> dict[str, int]:
        """Return a {status: count} summary over all rows."""
        rows = self._conn.execute(
            "SELECT status, COUNT(*) FROM jobs GROUP BY status"
        ).fetchall()
        return {row[0]: row[1] for row in rows}

    def update_status_and_notes(
        self,
        job_id: str,
        new_status: JobStatus | str | None = None,
        notes: str | None = None,
    ) -> JobEntry:
        """Update a job's status (transition-map enforced) and/or notes.

        Notes are appended to metadata.notes on a new line (human-owned
        key). Raises InvalidTransitionError for disallowed transitions
        and KeyError for unknown IDs.
        """
        entry = self.get(job_id)
        if entry is None:
            raise KeyError(f"Unknown job id: {job_id}")

        updates: dict = {}
        if new_status is not None:
            status_value = (
                new_status.value if isinstance(new_status, JobStatus) else str(new_status)
            )
            allowed = TRANSITIONS.get(entry.status.value, set())
            if status_value not in allowed:
                raise InvalidTransitionError(
                    f"Transition {entry.status.value} -> {status_value} is not allowed"
                )
            updates["status"] = JobStatus(status_value)

        if notes is not None and notes != "":
            existing_notes = str(entry.metadata.get("notes") or "")
            merged = f"{existing_notes}\n{notes}" if existing_notes else notes
            metadata = dict(entry.metadata)
            metadata["notes"] = merged
            updates["metadata"] = metadata

        if not updates:
            return entry

        updated = entry.model_copy(update=updates)
        self._conn.execute(
            "UPDATE jobs SET status = ?, updated_at = ?, payload = ? WHERE id = ?",
            (
                updated.status.value,
                _now(),
                json.dumps(updated.model_dump(mode="json")),
                job_id,
            ),
        )
        self._conn.commit()
        return updated


# Human-owned fields editable through the guarded generic edit surface
# (PATCH /jobs/{id} and the CLI `edit` subcommand). id, status and
# stage-owned metadata registry keys are immutable there.
EDITABLE_FIELDS = frozenset(
    {
        "title",
        "company_name",
        "company_website",
        "contact_info",
        "location",
        "tags",
        "job_type",
        "salary",
        "metadata.notes",
        "metadata.base_resume_path",
    }
)


def edit_job(store: JobsStore, job_id: str, updates: dict) -> JobEntry:
    """Apply a guarded whitelist edit to a job entry.

    Only EDITABLE_FIELDS may be changed; anything else (id, status,
    stage-owned registry keys) raises ValueError. Unknown IDs raise
    KeyError.
    """
    entry = store.get(job_id)
    if entry is None:
        raise KeyError(f"Unknown job id: {job_id}")

    data = entry.model_dump()
    metadata = dict(data.get("metadata") or {})
    for key, value in updates.items():
        if key not in EDITABLE_FIELDS:
            raise ValueError(f"Field is not editable: {key}")
        if key.startswith("metadata."):
            metadata[key.split(".", 1)[1]] = value
        else:
            data[key] = value
    data["metadata"] = metadata

    updated = JobEntry.model_validate(data)
    store._conn.execute(
        "UPDATE jobs SET updated_at = ?, payload = ? WHERE id = ?",
        (_now(), json.dumps(updated.model_dump(mode="json")), job_id),
    )
    store._conn.commit()
    return updated

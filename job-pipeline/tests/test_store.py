"""Stage 1 queue store tests: persistence, transitions, idempotency."""

import pytest

from src.models import JobEntry, JobStatus
from src.queues.store import (
    InvalidTransitionError,
    JobsStore,
    TRANSITIONS,
    edit_job,
)


def test_save_and_get(store, sample_job_entry):
    saved = store.save(sample_job_entry)
    assert saved.id == sample_job_entry.id
    fetched = store.get(sample_job_entry.id)
    assert fetched is not None
    assert fetched.title == sample_job_entry.title
    assert fetched.metadata["score"] == 62


def test_list_by_status_orders_by_score(store):
    for i, (score, status) in enumerate(
        [(10, JobStatus.NEW), (90, JobStatus.NEW), (50, JobStatus.REJECTED)]
    ):
        store.save(
            JobEntry(id=f"id{i}", title=f"Job {i}", status=status,
                     metadata={"score": score})
        )
    new_ids = [entry.id for entry in store.list_by_status(JobStatus.NEW)]
    assert new_ids == ["id1", "id0"]
    assert len(store.list_by_status(JobStatus.REJECTED)) == 1
    assert len(store.list_by_status(JobStatus.NEW, limit=1)) == 1


def test_count_by_status(store, sample_job_entry):
    assert store.count_by_status() == {}
    store.save(sample_job_entry)
    assert store.count_by_status() == {"new": 1}


def test_save_is_idempotent_on_reingest(store, sample_job_entry):
    store.save(sample_job_entry)
    # Manual note + accept after first ingest.
    store.update_status_and_notes(sample_job_entry.id, notes="looks good")
    store.update_status_and_notes(sample_job_entry.id, new_status=JobStatus.ACCEPTED)
    # Re-ingest with a new score: status and human notes survive.
    sample_job_entry.metadata["score"] = 75
    sample_job_entry.metadata["notes"] = ""
    store.save(sample_job_entry)
    fetched = store.get(sample_job_entry.id)
    assert fetched.status == JobStatus.ACCEPTED
    assert fetched.metadata["notes"] == "looks good"
    assert fetched.metadata["score"] == 75
    assert store.count_by_status()["accepted"] == 1


def test_transition_map_shape():
    assert TRANSITIONS["new"] == {"accepted", "rejected"}
    assert TRANSITIONS["rejected"] == {"accepted"}
    assert TRANSITIONS["accepted"] == {"rejected", "resume_ready"}
    assert TRANSITIONS["resume_ready"] == {"sent"}
    assert TRANSITIONS["sent"] == set()


def test_update_status_enforces_transitions(store, sample_job_entry):
    store.save(sample_job_entry)
    # new -> accepted is allowed.
    store.update_status_and_notes(sample_job_entry.id, new_status=JobStatus.ACCEPTED)
    # sent is Stage 4's transition: accepted -> sent is not allowed.
    with pytest.raises(InvalidTransitionError):
        store.update_status_and_notes(sample_job_entry.id, new_status=JobStatus.SENT)
    # accepted -> resume_ready is Stage 2's allowed transition.
    store.update_status_and_notes(sample_job_entry.id, new_status=JobStatus.RESUME_READY)
    # resume_ready -> rejected is not allowed (reject only pre-resume_ready).
    with pytest.raises(InvalidTransitionError):
        store.update_status_and_notes(sample_job_entry.id, new_status=JobStatus.REJECTED)


def test_update_notes_appends(store, sample_job_entry):
    store.save(sample_job_entry)
    store.update_status_and_notes(sample_job_entry.id, notes="first note")
    updated = store.update_status_and_notes(sample_job_entry.id, notes="second note")
    assert "first note" in updated.metadata["notes"]
    assert "second note" in updated.metadata["notes"]


def test_unknown_id_raises(store):
    with pytest.raises(KeyError):
        store.update_status_and_notes("nope", new_status=JobStatus.ACCEPTED)
    assert store.get("nope") is None


def test_edit_job_whitelist(store, sample_job_entry):
    store.save(sample_job_entry)
    updated = edit_job(store, sample_job_entry.id, {"location": "Remote"})
    assert updated.location == "Remote"
    # Stage-owned registry keys and status are not editable.
    with pytest.raises(ValueError):
        edit_job(store, sample_job_entry.id, {"status": "accepted"})
    with pytest.raises(ValueError):
        edit_job(store, sample_job_entry.id, {"metadata.score": 100})
    # metadata.notes / base_resume_path are human-owned and editable.
    updated = edit_job(
        store, sample_job_entry.id, {"metadata.base_resume_path": "other.tex"}
    )
    assert updated.metadata["base_resume_path"] == "other.tex"


def test_store_persists_across_connections(tmp_db_path, sample_job_entry):
    first = JobsStore(tmp_db_path)
    first.save(sample_job_entry)
    first.close()
    second = JobsStore(tmp_db_path)
    fetched = second.get(sample_job_entry.id)
    second.close()
    assert fetched is not None
    assert fetched.title == sample_job_entry.title

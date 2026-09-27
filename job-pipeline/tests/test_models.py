"""Shared domain model tests: stable ID, JobStatus, registry."""

from src.models import (
    META_NOTES,
    META_SCORE,
    STAGE_OWNED_METADATA_KEYS,
    JobEntry,
    JobStatus,
    job_id,
)


def test_job_id_is_stable_and_truncated():
    first = job_id("Werkstudent", "Example GmbH", "arbeitnow")
    second = job_id("Werkstudent", "Example GmbH", "arbeitnow")
    assert first == second
    assert len(first) == 12


def test_job_id_differs_per_field():
    assert job_id("A", "B", "c") != job_id("B", "A", "c")
    assert job_id("A", "B", "c") != job_id("A", "B", "d")


def test_job_status_is_forward_complete():
    values = {status.value for status in JobStatus}
    assert values == {"new", "accepted", "rejected", "resume_ready", "sent"}


def test_stage_owned_metadata_keys_are_immutable_via_edit():
    assert META_SCORE in STAGE_OWNED_METADATA_KEYS
    assert META_NOTES not in STAGE_OWNED_METADATA_KEYS


def test_job_entry_defaults():
    entry = JobEntry(id="x", title="Software Engineer")
    assert entry.status == JobStatus.NEW
    assert entry.metadata == {}
    assert entry.tags == []

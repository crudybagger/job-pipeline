"""Stage 1 CLI tests over a temp store."""

import json

import pytest

from src.models import JobEntry, JobStatus
from src.queues import cli


def _save_job(store, job_id="abc123def456", status=JobStatus.NEW):
    entry = JobEntry(
        id=job_id,
        title="Werkstudent Softwareentwicklung",
        company_name="Example GmbH",
        location="Aachen",
        source="arbeitnow",
        status=status,
        metadata={"score": 62, "notes": ""},
    )
    store.save(entry)
    return entry


def _run(argv):
    code = cli.main(argv)
    return code


def test_status_command(store, capsys):
    _save_job(store)
    assert _run(["status"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["queues"] == {"new": 1}


def test_view_commands(store, capsys):
    _save_job(store)
    assert _run(["view", "new"]) == 0
    entries = json.loads(capsys.readouterr().out)
    assert entries[0]["id"] == "abc123def456"
    assert _run(["view-accepted"]) == 0
    assert json.loads(capsys.readouterr().out) == []
    assert _run(["view-rejected"]) == 0
    assert json.loads(capsys.readouterr().out) == []


def test_show_command(store, capsys):
    _save_job(store)
    assert _run(["show", "abc123def456"]) == 0
    entry = json.loads(capsys.readouterr().out)
    assert entry["title"] == "Werkstudent Softwareentwicklung"


def test_show_unknown_id_fails(store, capsys):
    assert _run(["show", "nope"]) == 1
    assert "nope" in capsys.readouterr().err


def test_accept_and_reject_commands(store, capsys):
    _save_job(store)
    assert _run(["accept", "abc123def456"]) == 0
    json.loads(capsys.readouterr().out)
    assert store.get("abc123def456").status == JobStatus.ACCEPTED
    assert _run(["reject", "abc123def456"]) == 0
    json.loads(capsys.readouterr().out)
    assert store.get("abc123def456").status == JobStatus.REJECTED


def test_note_command(store, capsys):
    _save_job(store)
    assert _run(["note", "abc123def456", "looks interesting"]) == 0
    json.loads(capsys.readouterr().out)
    assert "looks interesting" in store.get("abc123def456").metadata["notes"]


def test_edit_command(store, capsys):
    _save_job(store)
    assert _run(["edit", "abc123def456", "location=Remote"]) == 0
    entry = json.loads(capsys.readouterr().out)
    assert entry["location"] == "Remote"


def test_edit_command_rejects_non_whitelisted(store):
    _save_job(store)
    assert _run(["edit", "abc123def456", "status=accepted"]) == 1


def test_build_parser_requires_command():
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args([])

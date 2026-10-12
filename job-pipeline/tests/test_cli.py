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

# --- Stage 2 resume subcommands (docs/design/stage2-lld.md) ------------------

from pathlib import Path

from src.resume import generate as gen

BASE_RESUME = Path(__file__).resolve().parent / "fixtures" / "base_resume.tex"

_STAGE2_EDIT_RESPONSE = {
    "summary": "Tailored summary mentioning Kubernetes and Python.",
    "experience": "\\item Engineered Kubernetes systems with Go.",
    "skills": "\\entry{Programming}{Go, Python, AWS}",
}
_STAGE2_SCORE = {"score": 100, "feedback": "", "ready": True}


def _save_accepted(store, job_id="cli123456789"):
    entry = JobEntry(
        id=job_id,
        title="Werkstudent Softwareentwicklung",
        company_name="Example GmbH",
        location="Aachen",
        source="arbeitnow",
        status=JobStatus.ACCEPTED,
        metadata={"score": 62, "notes": "", "base_resume_path": str(BASE_RESUME)},
    )
    store.save(entry)
    return entry


def _stage2_config(pipeline_config):
    from src.config import Stage2Config

    pipeline_config.stage2 = Stage2Config(
        ats_ready_threshold=60, max_iterations=1, latex_section_markers={}
    )
    return pipeline_config


def test_resume_generate_command(
    store, capsys, fake_llm, monkeypatch, tmp_path, pipeline_config
):
    monkeypatch.setattr(cli, "load_config", lambda path=None: _stage2_config(pipeline_config))
    monkeypatch.setattr(gen, "RESUMES_DIR", tmp_path / "resumes")
    _save_accepted(store)
    fake_llm([_STAGE2_EDIT_RESPONSE, _STAGE2_SCORE])
    assert _run(["resume-generate", "cli123456789"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "resume_ready"
    assert store.get("cli123456789").status == JobStatus.RESUME_READY


def test_resume_generate_command_single(
    store, capsys, fake_llm, monkeypatch, tmp_path, pipeline_config
):
    monkeypatch.setattr(cli, "load_config", lambda path=None: _stage2_config(pipeline_config))
    monkeypatch.setattr(gen, "RESUMES_DIR", tmp_path / "resumes")
    _save_accepted(store)
    fake_llm(
        [_STAGE2_EDIT_RESPONSE, {"score": 30, "feedback": "keep going", "ready": False}]
    )
    assert _run(["resume-generate", "cli123456789", "--single"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "accepted"
    assert payload["iterations"] == 1
    assert payload["needs_review"] is False


def test_resume_generate_unknown_id(store, capsys, monkeypatch, pipeline_config):
    monkeypatch.setattr(cli, "load_config", lambda path=None: _stage2_config(pipeline_config))
    assert _run(["resume-generate", "nope"]) == 1
    assert "nope" in capsys.readouterr().err


def test_resume_ats_command(store, capsys, fake_llm, monkeypatch, pipeline_config):
    monkeypatch.setattr(cli, "load_config", lambda path=None: _stage2_config(pipeline_config))
    _save_accepted(store)
    fake_llm([{"score": 84, "feedback": "Add Kafka.", "ready": False}])
    assert _run(["resume-ats", "cli123456789"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ats_score"] == 84
    assert len(store.get("cli123456789").metadata["ats"]["iterations"]) == 1


def test_resume_force_ready_command(store, capsys, monkeypatch):
    _save_accepted(store)
    assert _run(["resume-force-ready", "cli123456789"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "resume_ready"
    assert store.get("cli123456789").status == JobStatus.RESUME_READY
    assert _run(["resume-force-ready", "nope"]) == 1


def test_resume_run_command_dry_run(store, capsys, monkeypatch, pipeline_config):
    monkeypatch.setattr(cli, "load_config", lambda path=None: _stage2_config(pipeline_config))
    _save_accepted(store)
    assert _run(["resume-run", "--dry-run"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["dry_run"] is True
    assert payload["selected"] == 1
    assert payload["processed"] == 0


def test_resume_run_command_batch(
    store, capsys, fake_llm, monkeypatch, tmp_path, pipeline_config
):
    monkeypatch.setattr(cli, "load_config", lambda path=None: _stage2_config(pipeline_config))
    monkeypatch.setattr(gen, "RESUMES_DIR", tmp_path / "resumes")
    _save_accepted(store)
    fake_llm([_STAGE2_EDIT_RESPONSE, _STAGE2_SCORE])
    assert _run(["resume-run"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["processed"] == 1
    assert payload["resume_ready"] == 1
    assert store.get("cli123456789").status == JobStatus.RESUME_READY

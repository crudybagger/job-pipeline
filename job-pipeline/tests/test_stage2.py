"""Tests for the Stage 2 orchestrator (docs/design/stage2-lld.md).

Covers queue selection (accepted incl. needs_review re-runs), dry-run,
skipping entries without a resolvable base resume, per-entry error
isolation, the single-job guards, run_ats_substage and force_ready.
"""

from pathlib import Path

import pytest

from src.config import Stage2Config
from src.models import JobEntry, JobStatus
from src.llm import provider
from src.queues.store import InvalidTransitionError
from src.resume import generate as gen
from src.resume import stage2 as stage2_mod
from src.resume.stage2 import force_ready, run_ats_substage, run_stage2

BASE_RESUME = Path(__file__).resolve().parent / "fixtures" / "base_resume.tex"


def _accepted(store, job_id="stage2job1", score=62, **meta_extra):
    entry = JobEntry(
        id=job_id,
        title="Werkstudent Softwareentwicklung (m/w/d)",
        description="Backend-Team support with Python, Kubernetes, Go and AWS.",
        company_name="Example GmbH",
        source="arbeitnow",
        status=JobStatus.ACCEPTED,
        tags=["werkstudent", "python"],
        job_type="internship",
        metadata={
            "score": score,
            "base_resume_path": str(BASE_RESUME),
            "notes": "",
            **meta_extra,
        },
    )
    store.save(entry)
    return entry


def _config(pipeline_config, threshold=80, max_iterations=1):
    pipeline_config.stage2 = Stage2Config(
        ats_ready_threshold=threshold,
        max_iterations=max_iterations,
        latex_section_markers={},
    )
    return pipeline_config


def _edit_response():
    return {
        "summary": "Tailored summary mentioning Kubernetes and Python.",
        "experience": "\\item Engineered Kubernetes systems with Go.",
        "skills": "\\entry{Programming}{Go, Python, AWS}",
    }


def _score_response(score, feedback="", ready=False):
    return {"score": score, "feedback": feedback, "ready": ready}


def test_batch_processes_accepted_entries(
    store, pipeline_config, fake_llm, tmp_path, monkeypatch
):
    monkeypatch.setattr(gen, "RESUMES_DIR", tmp_path / "resumes")
    _accepted(store, "job-a")
    _accepted(store, "job-b")
    fake_llm(
        [
            _edit_response(),
            _score_response(0),
            _edit_response(),
            _score_response(0),
        ]
    )
    summary = run_stage2(_config(pipeline_config), store)
    assert summary["selected"] == 2
    assert summary["processed"] == 2
    assert summary["resume_ready"] == 0
    assert summary["needs_review"] == 2
    assert summary["errors"] == []
    assert len(summary["results"]) == 2


def test_limit_caps_selection(store, pipeline_config, fake_llm, tmp_path, monkeypatch):
    monkeypatch.setattr(gen, "RESUMES_DIR", tmp_path / "resumes")
    _accepted(store, "job-a", score=90)
    _accepted(store, "job-b", score=50)
    fake_llm([_edit_response(), _score_response(0)])
    summary = run_stage2(_config(pipeline_config), store, limit=1)
    assert summary["selected"] == 1
    assert summary["processed"] == 1
    assert summary["results"][0]["job_id"] == "job-a"


def test_dry_run_persists_nothing(store, pipeline_config, tmp_path, monkeypatch):
    resumes_dir = tmp_path / "resumes"
    monkeypatch.setattr(gen, "RESUMES_DIR", resumes_dir)
    _accepted(store, "job-a")
    summary = run_stage2(_config(pipeline_config), store, dry_run=True)
    assert summary["dry_run"] is True
    assert summary["selected"] == 1
    assert summary["processed"] == 0
    assert summary["results"] == []
    assert store.get("job-a").status == JobStatus.ACCEPTED
    assert not resumes_dir.exists()


def test_skips_entries_without_base_resume(store, pipeline_config, tmp_path, monkeypatch):
    monkeypatch.setattr(gen, "RESUMES_DIR", tmp_path / "resumes")
    entry = JobEntry(
        id="nobase123456",
        title="Werkstudent Data Engineering",
        company_name="Example GmbH",
        source="arbeitnow",
        status=JobStatus.ACCEPTED,
        metadata={"score": 55, "base_resume_path": "", "notes": ""},
    )
    store.save(entry)
    config = _config(pipeline_config)
    config.base_resume_path = ""
    summary = run_stage2(config, store)
    assert summary["selected"] == 1
    assert summary["processed"] == 0
    assert len(summary["skipped"]) == 1
    assert summary["skipped"][0]["job_id"] == "nobase123456"
    assert "base_resume_path" in summary["skipped"][0]["reason"]


def test_needs_review_entries_are_reselected(
    store, pipeline_config, fake_llm, tmp_path, monkeypatch
):
    monkeypatch.setattr(gen, "RESUMES_DIR", tmp_path / "resumes")
    _accepted(
        store,
        "job-a",
        ats={
            "iterations": [{"iteration": 1, "feedback": "note one"}],
            "needs_review": True,
        },
    )
    client = fake_llm([_edit_response(), _score_response(0)])
    summary = run_stage2(_config(pipeline_config), store)
    assert summary["selected"] == 1
    assert summary["processed"] == 1
    # The stored needs_review feedback is seeded into the re-run prompt.
    assert "note one" in client.calls[0]["user"]


def test_error_isolation_one_entry_fails(
    store, pipeline_config, fake_llm, tmp_path, monkeypatch
):
    monkeypatch.setattr(gen, "RESUMES_DIR", tmp_path / "resumes")
    _accepted(store, "bad-job")
    _accepted(store, "good-job")
    real_run_loop = stage2_mod.run_loop

    def flaky(entry, config, store_arg, run_to_completion=True):
        if entry.id == "bad-job":
            raise RuntimeError("boom")
        return real_run_loop(
            entry, config, store_arg, run_to_completion=run_to_completion
        )

    monkeypatch.setattr(stage2_mod, "run_loop", flaky)
    fake_llm([_edit_response(), _score_response(0)])
    summary = run_stage2(_config(pipeline_config), store)
    assert len(summary["errors"]) == 1
    assert summary["errors"][0]["job_id"] == "bad-job"
    assert "boom" in summary["errors"][0]["error"]
    assert summary["processed"] == 1
    assert summary["results"][0]["job_id"] == "good-job"


def test_single_job_guards(store, pipeline_config):
    config = _config(pipeline_config)
    with pytest.raises(KeyError):
        run_stage2(config, store, job_id="missing")
    entry = JobEntry(id="rej123456789", title="Rejected Job", status=JobStatus.REJECTED)
    store.save(entry)
    with pytest.raises(ValueError, match="not accepted"):
        run_stage2(config, store, job_id="rej123456789")


def test_single_job_mode_processes_one(
    store, pipeline_config, fake_llm, tmp_path, monkeypatch
):
    monkeypatch.setattr(gen, "RESUMES_DIR", tmp_path / "resumes")
    _accepted(store, "job-a")
    _accepted(store, "job-b")
    fake_llm([_edit_response(), _score_response(0)])
    summary = run_stage2(_config(pipeline_config), store, job_id="job-a")
    assert summary["selected"] == 1
    assert summary["processed"] == 1
    assert summary["results"][0]["job_id"] == "job-a"
    assert store.get("job-b").status == JobStatus.ACCEPTED


def test_ats_substage_appends_iteration_no_transition(store, pipeline_config, fake_llm):
    _accepted(store, "job-a")
    client = fake_llm([_score_response(84, "Add Kafka.", False)])
    result = run_ats_substage(store, "job-a", _config(pipeline_config))
    assert result["job_id"] == "job-a"
    assert result["iteration"] == 1
    assert result["ats_score"] == 84
    assert "score" in result and "feedback" in result
    stored = store.get("job-a")
    assert stored.status == JobStatus.ACCEPTED  # substage never transitions
    assert len(stored.metadata["ats"]["iterations"]) == 1
    assert client.calls[0]["schema"] is not None


def test_ats_substage_scores_existing_artifact(
    store, pipeline_config, fake_llm, tmp_path, monkeypatch
):
    monkeypatch.setattr(gen, "RESUMES_DIR", tmp_path / "resumes")
    _accepted(store, "job-a")
    artifact = gen.save_resume(
        "job-a", "\\begin{document}DISTINCTIVE-ARTIFACT\\end{document}"
    )
    store.update_metadata("job-a", {"resume": {"path": str(artifact), "iterations": 1}})
    client = fake_llm([_score_response(70)])
    run_ats_substage(store, "job-a", _config(pipeline_config))
    assert "DISTINCTIVE-ARTIFACT" in client.calls[0]["user"]


def test_ats_substage_unknown_id_raises(store, pipeline_config):
    with pytest.raises(KeyError):
        run_ats_substage(store, "missing", _config(pipeline_config))


def test_force_ready_promotes_accepted(store, tmp_path, monkeypatch, pipeline_config):
    monkeypatch.setattr(gen, "RESUMES_DIR", tmp_path / "resumes")
    _accepted(store, "job-a")
    artifact = gen.save_resume("job-a", "\\begin{document}tailored\\end{document}")
    store.update_metadata("job-a", {"resume": {"path": str(artifact), "iterations": 2}})
    updated = force_ready(store, "job-a")
    assert updated.status == JobStatus.RESUME_READY
    stored = store.get("job-a")
    assert stored.status == JobStatus.RESUME_READY
    assert stored.metadata["resume"]["ready_at"]


def test_force_ready_guards(store, pipeline_config):
    entry = JobEntry(id="newjob999999", title="New Job", status=JobStatus.NEW)
    store.save(entry)
    with pytest.raises(InvalidTransitionError):
        force_ready(store, "newjob999999")
    with pytest.raises(KeyError):
        force_ready(store, "missing")

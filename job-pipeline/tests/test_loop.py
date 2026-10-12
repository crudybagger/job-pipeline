"""Tests for the Stage 2 loop substage (docs/design/stage2-lld.md).

Covers the threshold -> resume_ready advancement (metadata.resume.ready_at
plus the store transition), the cap -> needs_review behavior (design
decision 4: stays accepted), the metadata.ats feedback round-trip into the
re-edit prompt, the single-iteration mode, per-iteration error recording
and the status guards. No live network: the LLM is the scripted
FakeLLMClient from conftest.
"""

from pathlib import Path

import pytest

from src.config import Stage2Config
from src.models import JobEntry, JobStatus
from src.resume import generate as gen
from src.resume.loop import run_loop

BASE_RESUME = Path(__file__).resolve().parent / "fixtures" / "base_resume.tex"


def _accepted(store, job_id="loopjob123", **meta_extra):
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
            "score": 62,
            "base_resume_path": str(BASE_RESUME),
            "notes": "",
            **meta_extra,
        },
    )
    store.save(entry)
    return entry


def _config(pipeline_config, threshold=80, max_iterations=5):
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


def test_threshold_advances_to_resume_ready(
    store, pipeline_config, fake_llm, tmp_path, monkeypatch
):
    monkeypatch.setattr(gen, "RESUMES_DIR", tmp_path / "resumes")
    entry = _accepted(store)
    fake_llm([_edit_response(), _score_response(100)])
    result = run_loop(entry, _config(pipeline_config, threshold=60), store)
    assert result["status"] == "resume_ready"
    assert result["needs_review"] is False
    assert result["iterations"] == 1
    assert result["score"] >= 60
    stored = store.get(entry.id)
    assert stored.status == JobStatus.RESUME_READY
    resume_meta = stored.metadata["resume"]
    assert resume_meta["ready_at"]
    assert Path(resume_meta["path"]).is_file()
    assert len(stored.metadata["ats"]["iterations"]) == 1
    assert stored.metadata["ats"]["needs_review"] is False


def test_cap_sets_needs_review_and_stays_accepted(
    store, pipeline_config, fake_llm, tmp_path, monkeypatch
):
    monkeypatch.setattr(gen, "RESUMES_DIR", tmp_path / "resumes")
    entry = _accepted(store)
    fake_llm(
        [
            _edit_response(),
            _score_response(0),
            _edit_response(),
            _score_response(0),
        ]
    )
    result = run_loop(
        entry, _config(pipeline_config, threshold=80, max_iterations=2), store
    )
    assert result["status"] == "accepted"
    assert result["needs_review"] is True
    assert result["iterations"] == 2
    stored = store.get(entry.id)
    assert stored.status == JobStatus.ACCEPTED
    assert stored.metadata["ats"]["needs_review"] is True
    assert len(stored.metadata["ats"]["iterations"]) == 2
    assert "ready_at" not in (stored.metadata.get("resume") or {})


def test_feedback_round_trip_in_edit_prompt(
    store, pipeline_config, fake_llm, tmp_path, monkeypatch
):
    monkeypatch.setattr(gen, "RESUMES_DIR", tmp_path / "resumes")
    entry = _accepted(store)
    client = fake_llm(
        [
            _edit_response(),
            _score_response(0, "Add Kafka to skills."),
            _edit_response(),
            _score_response(0),
        ]
    )
    run_loop(entry, _config(pipeline_config, threshold=80, max_iterations=2), store)
    assert len(client.calls) == 4
    # First iteration: no previous feedback in the prompt.
    assert "ATS feedback" not in client.calls[0]["user"]
    # Second iteration: the previous combined feedback is seeded in.
    assert "Add Kafka to skills." in client.calls[2]["user"]


def test_feedback_round_trip_from_store_metadata(
    store, pipeline_config, fake_llm, tmp_path, monkeypatch
):
    monkeypatch.setattr(gen, "RESUMES_DIR", tmp_path / "resumes")
    entry = _accepted(
        store,
        ats={
            "iterations": [{"iteration": 1, "feedback": "note one"}],
            "needs_review": False,
        },
    )
    client = fake_llm([_edit_response(), _score_response(0)])
    result = run_loop(
        entry, _config(pipeline_config), store, run_to_completion=False
    )
    assert result["iterations"] == 2
    # The stored metadata.ats feedback seeds the re-edit prompt.
    assert "note one" in client.calls[0]["user"]
    stored = store.get(entry.id)
    assert [it["iteration"] for it in stored.metadata["ats"]["iterations"]] == [1, 2]


def test_single_iteration_mode(store, pipeline_config, fake_llm, tmp_path, monkeypatch):
    monkeypatch.setattr(gen, "RESUMES_DIR", tmp_path / "resumes")
    entry = _accepted(store)
    fake_llm([_edit_response(), _score_response(30)])
    result = run_loop(
        entry,
        _config(pipeline_config, threshold=80, max_iterations=5),
        store,
        run_to_completion=False,
    )
    assert result["status"] == "accepted"
    assert result["needs_review"] is False
    assert result["iterations"] == 1
    assert len(store.get(entry.id).metadata["ats"]["iterations"]) == 1


def test_iteration_error_recorded(store, pipeline_config, fake_llm, tmp_path, monkeypatch):
    monkeypatch.setattr(gen, "RESUMES_DIR", tmp_path / "resumes")
    entry = _accepted(store)
    fake_llm([RuntimeError("boom")])
    result = run_loop(entry, _config(pipeline_config, threshold=60), store)
    assert "boom" in result["error"]
    assert result["status"] == "accepted"
    # Per-iteration errors never set needs_review (design decision 4).
    assert result["needs_review"] is False
    assert result["iterations"] == 0
    assert "ats" not in store.get(entry.id).metadata


def test_run_loop_refuses_non_accepted(store, pipeline_config):
    entry = JobEntry(
        id="newjob123456",
        title="Werkstudent Softwareentwicklung",
        company_name="Example GmbH",
        source="arbeitnow",
        status=JobStatus.NEW,
        metadata={"base_resume_path": str(BASE_RESUME)},
    )
    store.save(entry)
    with pytest.raises(ValueError, match="not accepted"):
        run_loop(entry, _config(pipeline_config), store)


def test_run_loop_unknown_id_raises(store, pipeline_config):
    entry = JobEntry(id="nope12345678", title="Missing Job")
    with pytest.raises(KeyError):
        run_loop(entry, _config(pipeline_config), store)

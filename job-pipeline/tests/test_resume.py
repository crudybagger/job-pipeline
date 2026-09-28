"""Tests for the Stage 2 generation substage (docs/design/stage2-lld.md)."""

import json
from pathlib import Path

import pytest

from src.config import Stage2Config
from src.resume import generate as gen
from src.resume.generate import (
    apply_section_edits,
    detect_section_markers,
    edit_base_resume,
    find_section_span,
    load_resume_artifact,
    locate_sections,
    resolve_base_resume_path,
    save_resume,
)


def _config(markers=None, base_resume_path="../data/Resume.tex"):
    from src.config import PipelineConfig

    config = PipelineConfig()
    config.base_resume_path = base_resume_path
    config.stage2 = Stage2Config(latex_section_markers=markers or {})
    return config


def test_detect_section_markers_finds_all_three(base_resume_tex):
    markers = detect_section_markers(base_resume_tex)
    assert set(markers) == {"summary", "experience", "skills"}
    assert "\\begin{rSection}{Summary}" in markers["summary"]
    assert "\\begin{rSection}{Work Experience}" in markers["experience"]
    assert "\\tableEnv{Skills}{" in markers["skills"]


def test_find_section_span_rsection(base_resume_tex):
    span = find_section_span(base_resume_tex, "\\begin{rSection}{Summary}")
    assert span is not None
    start, end = span
    content = base_resume_tex[start:end]
    assert content.startswith("\n")
    assert "\\end{rSection}" not in content
    assert "Master's student" in content


def test_find_section_span_brace_block(base_resume_tex):
    span = find_section_span(base_resume_tex, "\\tableEnv{Skills}{")
    assert span is not None
    start, end = span
    content = base_resume_tex[start:end]
    assert "\\entry{Programming}" in content
    assert "\\entry{Languages}" in content
    # The closing brace of the tableEnv block itself is not in the span.
    assert base_resume_tex[end] == "}"


def test_find_section_span_missing_marker_returns_none():
    assert find_section_span("\\begin{document}\\end{document}", "nope") is None


def test_locate_sections_config_wins(base_resume_tex):
    config = _config(markers={
        "summary": "\\begin{rSection}{Summary}",
        "experience": "\\begin{rSection}{Work Experience}",
        "skills": "\\tableEnv{Skills}{",
    })
    spans = locate_sections(base_resume_tex, config)
    assert set(spans) == {"summary", "experience", "skills"}


def test_locate_sections_auto_detect_fallback(base_resume_tex):
    spans = locate_sections(base_resume_tex, _config())
    assert set(spans) == {"summary", "experience", "skills"}


def test_apply_section_edits_only_touches_spans(base_resume_tex):
    config = _config()
    spans = locate_sections(base_resume_tex, config)
    edits = {
        "summary": "Tailored summary mentioning Kubernetes and Python.",
        "experience": base_resume_tex[spans["experience"][0]:spans["experience"][1]],
        "skills": "\\entry{Programming}{Go, Python, AWS}",
    }
    result = apply_section_edits(base_resume_tex, spans, edits)
    assert "Tailored summary mentioning Kubernetes and Python." in result
    assert "\\documentclass{resume}" in result
    assert "\\begin{rSection}{Work Experience}" in result


def test_apply_section_edits_rejects_out_of_span_change(base_resume_tex):
    config = _config()
    spans = locate_sections(base_resume_tex, config)
    # A result whose preamble differs from the base must fail validation:
    # the diff reaches outside the permitted sections.
    tampered = base_resume_tex.replace("\\documentclass{resume}", "\\documentclass{article}")
    with pytest.raises(ValueError, match="outside the permitted sections"):
        gen._validate_edit(base_resume_tex, spans, tampered)


def test_edit_base_resume_with_fake_llm(base_resume_tex, fake_llm, sample_job_entry):
    config = _config()
    client = fake_llm([
        {
            "summary": "Kubernetes-focused summary.",
            "experience": "\\item Engineered Kubernetes systems with Go.",
            "skills": "\\entry{Programming}{Go, Python}",
        }
    ])
    result = edit_base_resume(sample_job_entry, base_resume_tex, config)
    assert "Kubernetes-focused summary." in result
    assert client.calls, "LLM was called"
    call = client.calls[0]
    assert call["schema"] is not None
    assert "Werkstudent" in call["user"] or "job" in call["user"].lower()


def test_edit_base_resume_invalid_json_raises(base_resume_tex, fake_llm, sample_job_entry):
    fake_llm(["not json at all"])
    with pytest.raises(ValueError, match="invalid JSON"):
        edit_base_resume(sample_job_entry, base_resume_tex, _config())


def test_edit_base_resume_no_sections_raises(base_resume_tex, sample_job_entry):
    config = _config(markers={"summary": "\\begin{rSection}{Nonexistent}"})
    with pytest.raises(ValueError, match="No editable sections"):
        edit_base_resume(sample_job_entry, base_resume_tex, config)


def test_resolve_base_resume_path_metadata_wins(tmp_path, sample_job_entry):
    resume = tmp_path / "job-resume.tex"
    resume.write_text("\\begin{document}x\\end{document}", encoding="utf-8")
    sample_job_entry.metadata["base_resume_path"] = str(resume)
    path = resolve_base_resume_path(sample_job_entry, _config())
    assert path == resume


def test_resolve_base_resume_path_config_fallback(sample_job_entry, monkeypatch):
    sample_job_entry.metadata["base_resume_path"] = ""
    monkeypatch.setattr(gen, "PROJECT_ROOT", Path("/e/jobs/job-pipeline"))
    path = resolve_base_resume_path(
        sample_job_entry, _config(base_resume_path="../data/Resume.tex")
    )
    assert path.is_file()
    assert path.name == "Resume.tex"


def test_resolve_base_resume_path_missing_raises(sample_job_entry):
    sample_job_entry.metadata["base_resume_path"] = ""
    with pytest.raises(FileNotFoundError):
        resolve_base_resume_path(sample_job_entry, _config(base_resume_path=""))


def test_save_and_load_artifact(tmp_path, monkeypatch, sample_job_entry):
    monkeypatch.setattr(gen, "RESUMES_DIR", tmp_path / "resumes")
    path = save_resume(sample_job_entry.id, "\\begin{document}tailored\\end{document}")
    assert path == tmp_path / "resumes" / f"{sample_job_entry.id}.tex"
    sample_job_entry.metadata["resume"] = {"path": str(path)}
    expected = "\\begin{document}tailored\\end{document}"
    assert load_resume_artifact(sample_job_entry) == expected


def test_load_resume_artifact_missing_returns_none(sample_job_entry):
    sample_job_entry.metadata["resume"] = {"path": "/nonexistent/x.tex"}
    assert load_resume_artifact(sample_job_entry) is None
    sample_job_entry.metadata["resume"] = {}
    assert load_resume_artifact(sample_job_entry) is None

"""Tests for the Stage 2 ATS substage (docs/design/stage2-lld.md)."""

import pytest

from src.config import MatchingConfig, ScoreWeights
from src.resume.ats import (
    combine_scores,
    score_resume,
    score_resume_deterministic,
)


def _job():
    from src.models import JobEntry

    return JobEntry(
        id="ats123",
        title="Werkstudent Backend Development (m/w/d)",
        description=(
            "Support our backend team with Python and Kubernetes. You will build "
            "Go microservices on AWS and work with Kafka event pipelines."
        ),
        company_name="Example GmbH",
        tags=["werkstudent", "python", "kubernetes"],
        job_type="internship",
    )


def _matching():
    return MatchingConfig(
        score_weights=ScoreWeights(experience=1.0, prospects=1.0, education=1.0),
        in_demand_technologies=["aws", "kubernetes", "python", "go", "kafka"],
        role_keywords=["werkstudent", "hiwi", "working student", "intern"],
    )


def test_score_resume_with_fake_llm(fake_llm):
    fake_llm([{"score": 84, "feedback": "Add Kafka to skills.", "ready": False}])
    result = score_resume(_job(), "resume text")
    assert result == {"score": 84, "feedback": "Add Kafka to skills.", "ready": False}


def test_score_resume_normalizes_and_clamps(fake_llm):
    fake_llm([{"score": 250, "feedback": "", "ready": "yes"}])
    result = score_resume(_job(), "resume text")
    assert result["score"] == 100
    assert result["ready"] is True


def test_score_resume_invalid_json_raises(fake_llm):
    fake_llm(["garbage"])
    with pytest.raises(ValueError, match="invalid JSON"):
        score_resume(_job(), "resume text")


def test_score_resume_prompt_contains_job_and_resume(fake_llm):
    fake_llm([{"score": 50, "feedback": "", "ready": False}])
    score_resume(_job(), "the resume text")
    user = fake_llm_calls_user(fake_llm)
    assert "Werkstudent Backend Development" in user
    assert "the resume text" in user


def fake_llm_calls_user(fake_llm):
    # The installer returns the client; the fixture records installed clients.
    from src.llm import provider

    return provider.get_client().calls[-1]["user"]


def test_deterministic_scores_matching_resume_higher():
    job = _job()
    matching = _matching()
    strong = score_resume_deterministic(
        job,
        "Werkstudent with Python, Kubernetes, Go, AWS and Kafka experience.",
        matching,
    )
    weak = score_resume_deterministic(job, "Sales and marketing background.", matching)
    assert strong["score"] > weak["score"]
    assert strong["score"] <= 100
    assert weak["score"] == 0


def test_deterministic_feedback_lists_missing_keywords():
    result = score_resume_deterministic(
        _job(), "Python and Kubernetes experience only.", _matching()
    )
    assert "Missing" in result["feedback"]
    assert "go" in result["feedback"] or "aws" in result["feedback"]


def test_deterministic_weights_affect_score():
    job = _job()
    resume = "Werkstudent with Python, Kubernetes, Go, AWS and Kafka."
    even = score_resume_deterministic(
        job, resume, _matching()  # all weights 1.0
    )
    skewed = score_resume_deterministic(
        job,
        resume,
        MatchingConfig(
            score_weights=ScoreWeights(experience=0.0, prospects=1.0, education=1.0),
            in_demand_technologies=["aws", "kubernetes", "python", "go", "kafka"],
            role_keywords=["werkstudent", "hiwi", "working student", "intern"],
        ),
    )
    assert skewed["score"] >= even["score"]


def test_combine_scores_weighted_mean():
    combined = combine_scores(
        {"score": 80, "feedback": "llm note", "ready": True},
        {"score": 50, "feedback": "det note", "ready": False},
    )
    assert combined["score"] == round(0.7 * 80 + 0.3 * 50)  # 71
    assert "llm note" in combined["feedback"]
    assert "det note" in combined["feedback"]
    assert combined["ready"] is True

"""Stage 1 matching tests: factors, location gate, weights, dispatch."""

import pytest

from src.matching.match import (
    SCORER_REGISTRY,
    compute_match_score,
    location_gate,
    match_candidate_to_job,
    score_job,
)


def _job(**overrides):
    base = {
        "title": "Werkstudent Softwareentwicklung (m/w/d)",
        "description": "Support our backend team with Python, Java, AWS, "
                       "Docker, Kubernetes, Kafka and microservices.",
        "tags": ["werkstudent", "python"],
        "location": "Aachen",
    }
    base.update(overrides)
    return base


def test_perfect_role_and_skills_scores_above_threshold(candidate_profile, matching):
    score, breakdown = compute_match_score(candidate_profile, _job(), matching)
    assert score > matching["match_threshold"]
    assert breakdown["location_fit"] is True
    assert "python" in breakdown["matched_skills"]
    assert "werkstudent" in breakdown["matched_role_keywords_title"]


def test_location_gate_rejects_far_jobs(candidate_profile, matching):
    job = _job(location="München")
    score, breakdown = compute_match_score(candidate_profile, job, matching)
    assert score == 0
    assert breakdown["location_fit"] is False
    assert breakdown["location_reason"] == "fail"


def test_location_gate_accepts_remote_jobs(candidate_profile, matching):
    job = _job(location="Remote (Worldwide)", tags=["remote"])
    eligible, reason = location_gate(job, matching)
    assert eligible is True
    assert reason == "remote"


def test_location_gate_accepts_cologne(candidate_profile, matching):
    eligible, reason = location_gate(_job(location="Köln"), matching)
    assert eligible is True
    assert reason == "location"


def test_location_gate_empty_location_fails(candidate_profile, matching):
    eligible, reason = location_gate(_job(location=""), matching)
    assert eligible is False
    assert reason == "no_location"


def test_location_gate_can_be_disabled(candidate_profile, matching):
    matching["require_location_fit"] = False
    eligible, reason = location_gate(_job(location="München"), matching)
    assert eligible is True
    assert reason == "gate_disabled"


def test_empty_term_list_is_neutral(candidate_profile, matching):
    matching["in_demand_technologies"] = []
    _, breakdown = compute_match_score(candidate_profile, _job(), matching)
    assert breakdown["prospects"] == 50.0


def test_weights_from_config(candidate_profile, matching):
    matching["score_weights"] = {"experience": 0.0, "prospects": 0.0, "education": 1.0}
    score, breakdown = compute_match_score(candidate_profile, _job(), matching)
    # With the other weights at zero, the score is the education factor.
    assert score == round(breakdown["education"])
    # A title hit counts full weight, so it beats a description-only hit.
    assert breakdown["matched_role_keywords_title"]
    assert score > 0


def test_match_candidate_to_job_threshold(candidate_profile, matching):
    matching["match_threshold"] = 99
    assert match_candidate_to_job(candidate_profile, _job(), matching) is False
    matching["match_threshold"] = 1
    assert match_candidate_to_job(candidate_profile, _job(), matching) is True


def test_score_job_dispatch_and_registry(candidate_profile, matching):
    score, _ = score_job(candidate_profile, _job(), matching)
    assert score == SCORER_REGISTRY["deterministic"](candidate_profile, _job(), matching)[0]
    with pytest.raises(ValueError):
        score_job(candidate_profile, _job(), matching, backend="no-such-backend")


def test_llm_scorer_is_a_stub(candidate_profile, matching):
    with pytest.raises(NotImplementedError):
        score_job(candidate_profile, _job(), matching, backend="llm")


def test_german_description_matching(candidate_profile, matching):
    """A German-language Werkstudent posting matches role keywords."""
    job = _job(
        title="Werkstudent Softwareentwicklung (m/w/d)",
        description="Unterstützung unseres Backend-Teams mit Python, Java, "
                    "AWS, Docker, Kubernetes, Kafka und Microservices. "
                    "Flexible Arbeitszeiten, Homeoffice möglich.",
        location="Aachen",
    )
    score, breakdown = compute_match_score(candidate_profile, job, matching)
    assert score > 0
    assert breakdown["location_fit"] is True

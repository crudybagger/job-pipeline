"""Stage 1 matching: deterministic, config-weighted match scoring.

Implements plan.md's scoring intent: the score reflects the candidate's
existing experience/skills, the future prospects of the job (in-demand
technologies) and the correlation with the candidate's current education
(student-role keywords). Weights, threshold and keyword lists live in the
config so the score can be re-tuned after manual analysis of the rejected
list. A location gate encodes the candidate's geographic constraints
(remote OR near the configured cities) as hard eligibility. The llm
backend is a pluggable slot stub for the shared src/llm/ foundation.


"""
from src.config import CandidateProfile, MatchingConfig
from src.models import JobEntry


def _as_dict(obj) -> dict:
    """Normalize a pydantic model or dict to a plain dict."""
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    return dict(obj or {})


def _job_text(job) -> str:
    """Lower-cased searchable text: title + description + tags + location."""
    job = _as_dict(job)
    parts = [
        str(job.get("title") or ""),
        str(job.get("description") or ""),
        " ".join(str(tag) for tag in (job.get("tags") or [])),
        str(job.get("location") or ""),
    ]
    return " ".join(parts).lower()


def _coverage(terms: list[str], text: str) -> tuple[float, list[str]]:
    """Fraction of terms present in the text (0-100) plus the matched terms.

    An empty term list scores neutral (50) so a missing config section
    neither rewards nor punishes a job.
    """
    if not terms:
        return 50.0, []
    matched = [term for term in terms if term.lower() in text]
    return 100.0 * len(matched) / len(terms), matched


# Common English function words; experience entries are prose, and these
# tokens would otherwise inflate the experience/skills coverage.
STOPWORDS = frozenset(
    {
        "the", "and", "for", "with", "from", "that", "this", "our", "their",
        "have", "has", "had", "was", "are", "were", "been", "its", "his",
        "her", "into", "over", "about", "after", "before", "also", "while",
        "when", "where", "which", "what", "who", "how", "not", "but", "all",
        "any", "can", "will", "would", "could", "should", "may", "might",
        "did", "does", "done", "them", "they", "then", "than", "there",
    }
)


def _candidate_terms(candidate: dict) -> list[str]:
    """Terms describing the candidate's experience/skills for coverage."""
    terms: list[str] = []
    for skill in (candidate.get("skills") or []):
        skill = str(skill)
        if skill and skill not in terms:
            terms.append(skill)
    for experience in (candidate.get("experience") or []):
        # Experience entries are prose; keep their significant words so
        # short tokens and stopwords do not flood the matching set.
        for word in str(experience).lower().replace("(", " ").replace(")", " ").split():
            if len(word) >= 3 and word not in STOPWORDS and word not in terms:
                terms.append(word)
    return terms


def location_gate(job, matching: dict) -> tuple[bool, str]:
    """Hard geographic eligibility: remote OR a configured location match.

    Returns (eligible, reason). reason is one of: "gate_disabled",
    "remote", "location", "no_location", "fail".
    """
    if not matching.get("require_location_fit", True):
        return True, "gate_disabled"
    job = _as_dict(job)
    location = str(job.get("location") or "").lower()
    tags = [str(tag).lower() for tag in (job.get("tags") or [])]
    remote_indicators = [str(item).lower() for item in (matching.get("remote_indicators") or [])]
    location_keywords = [str(item).lower() for item in (matching.get("location_keywords") or [])]
    if any(indicator in location or indicator in tags for indicator in remote_indicators):
        return True, "remote"
    if location_keywords and any(keyword in location for keyword in location_keywords):
        return True, "location"
    if not location and not any("remote" in tag for tag in tags):
        return False, "no_location"
    return False, "fail"

def compute_match_score(candidate_profile, job, matching=None) -> tuple[int, dict]:
    """Compute the weighted match score (0-100) and a breakdown dict.

    Factors (per plan.md): experience/skills overlap, future prospects
    (in-demand technologies) and education correlation (student-role
    keywords), combined with the configured score weights. The location
    gate is applied first: ineligible jobs score 0 with the breakdown
    recording location_fit=False.
    """
    candidate = _as_dict(candidate_profile)
    matching_dict = _as_dict(matching)
    job = _as_dict(job)
    text = _job_text(job)

    eligible, gate_reason = location_gate(job, matching_dict)

    experience_value, matched_skills = _coverage(_candidate_terms(candidate), text)

    prospects_value, matched_in_demand = _coverage(
        [str(item) for item in (matching_dict.get("in_demand_technologies") or [])], text
    )

    role_keywords = [str(item).lower() for item in (matching_dict.get("role_keywords") or [])]
    title = str(job.get("title") or "").lower()
    title_hits = [keyword for keyword in role_keywords if keyword in title]
    text_only_hits = [
        keyword
        for keyword in role_keywords
        if keyword not in title_hits and keyword in text
    ]
    if role_keywords:
        # Student-role correlation: a student-role keyword in the title is
        # the strongest signal (full weight); description/tag hits are a
        # weaker signal. This keeps Werkstudent/HiWi postings competitive
        # against full-time roles that list more skills.
        if title_hits:
            education_value = 100.0
        elif text_only_hits:
            education_value = 40.0
        else:
            education_value = 0.0
    else:
        education_value = 50.0

    breakdown = {
        "experience": round(experience_value, 1),
        "prospects": round(prospects_value, 1),
        "education": round(education_value, 1),
        "location_fit": eligible,
        "location_reason": gate_reason,
        "matched_skills": matched_skills,
        "matched_in_demand": matched_in_demand,
        "matched_role_keywords_title": title_hits,
        "matched_role_keywords_text": text_only_hits,
    }
    if not eligible:
        return 0, breakdown

    weights = _as_dict(matching_dict.get("score_weights") or {})
    w_experience = float(weights.get("experience", 1.0))
    w_prospects = float(weights.get("prospects", 1.0))
    w_education = float(weights.get("education", 1.0))
    total_weight = w_experience + w_prospects + w_education
    if total_weight <= 0:
        total_weight = 1.0
    score = (
        w_experience * experience_value
        + w_prospects * prospects_value
        + w_education * education_value
    ) / total_weight
    return int(round(min(100.0, max(0.0, score)))), breakdown


def match_candidate_to_job(candidate_profile, job_listing, matching=None) -> bool:
    """Return True when the match score is at or above the configured threshold.

    Keeps the original bool signature from the scaffolding; the threshold
    comes from the matching config (default 70).
    """
    matching_dict = _as_dict(matching)
    threshold = int(matching_dict.get("match_threshold") or 70)
    score, _ = compute_match_score(candidate_profile, job_listing, matching)
    return score >= threshold


def _llm_scorer(candidate_profile, job, matching=None) -> tuple[int, dict]:
    """Pluggable llm scorer slot stub (design decision #3)."""
    raise NotImplementedError(
        "The llm scorer backend requires the shared src/llm/ foundation "
        "(docs/design/pipeline-integration.md); use the deterministic backend"
    )


SCORER_REGISTRY = {"deterministic": compute_match_score, "llm": _llm_scorer}


def score_job(candidate_profile, job, matching=None, backend: str = "deterministic") -> tuple[int, dict]:
    """Dispatch to the registered scorer backend (default: deterministic)."""
    scorer = SCORER_REGISTRY.get(backend)
    if scorer is None:
        raise ValueError(f"Unknown scorer backend: {backend}")
    return scorer(candidate_profile, job, matching)

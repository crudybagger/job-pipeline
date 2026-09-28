"""Stage 2 substage: independent ATS-like resume scoring.

score_resume() prompts an LLM "professional resume screener / tech hiring
manager" persona; score_resume_deterministic() extracts keywords from the
job posting and reuses Stage 1's matching-config weights (not
compute_match_score itself — a structured candidate profile and a free-
text resume are different inputs). combine_scores() merges the two
independent signals into one iteration record
(docs/design/stage2-resume-generation.md).
"""

import json
import re
from collections import Counter

from src.config import MatchingConfig
from src.llm import complete
from src.models import JobEntry

# Weights for combining the two independent ATS signals (documented in
# docs/design/stage2-lld.md; deterministic is the sanity signal).
LLM_WEIGHT = 0.7
DETERMINISTIC_WEIGHT = 0.3

_ATS_SYSTEM_PROMPT = (
    "You are a professional resume screener and tech hiring manager reviewing a "
    "candidate's tailored resume against one job description. Score the resume the "
    "way an ATS plus a human screener would: keyword coverage of the job "
    "description, alignment of the experience bullet points with the role, and "
    "overall fit. The resume must sound human — flag generic AI phrasing. Be "
    "strict but fair; do not reward invented experience or employers."
)

_ATS_SCHEMA = {
    "type": "object",
    "properties": {
        "score": {"type": "integer", "minimum": 0, "maximum": 100},
        "feedback": {
            "type": "string",
            "description": (
                "Concrete improvement notes: missing keywords, misaligned "
                "bullet points, generic phrasing"
            ),
        },
        "ready": {"type": "boolean"},
    },
    "required": ["score", "feedback", "ready"],
}

_STOPWORDS = frozenset(
    {
        "the", "and", "for", "with", "you", "your", "our", "are", "will",
        "that", "this", "from", "have", "has", "was", "were", "not", "but",
        "all", "any", "can", "who", "what", "how", "why", "its", "his",
        "her", "their", "them", "they", "been", "being", "into", "over",
        "under", "about", "across", "per", "via", "job", "work", "role",
        "team", "teams", "candidate", "candidate's", "apply", "application",
        "please", "we", "us", "a", "an", "in", "on", "at", "to", "of",
        "as", "is", "it", "or", "by", "be", "de", "der", "und", "die",
        "das", "den", "dem", "ein", "eine", "einen", "mit", "für", "fur",
        "und", "oder", "sowie", "wir", "sie", "ich",
    }
)


def _tokenize(text: str) -> list[str]:
    """Lowercase word tokens (keeping +/# for c++/c#), stopwords removed."""
    tokens = re.findall(r"[a-z0-9+#.]+", text.lower())
    return [token for token in tokens if token not in _STOPWORDS and len(token) >= 2]


def _extract_job_keywords(job: JobEntry, limit: int = 40) -> list[str]:
    """Deterministic keyword set: title tokens (always), tags verbatim,
    top description tokens by frequency."""
    keywords: list[str] = []
    title_tokens = _tokenize(job.title)
    keywords.extend(title_tokens)
    for tag in job.tags:
        tag_token = tag.strip().lower()
        if tag_token and tag_token not in _STOPWORDS:
            keywords.append(tag_token)
    counts = Counter(_tokenize(job.description))
    for token, _count in counts.most_common(limit):
        if token not in keywords:
            keywords.append(token)
    # Deduplicate while preserving order, cap the total.
    seen: set[str] = set()
    unique: list[str] = []
    for keyword in keywords:
        if keyword not in seen:
            seen.add(keyword)
            unique.append(keyword)
    return unique[: limit + 10]


def score_resume(job: JobEntry, resume_text: str) -> dict:
    """LLM screener: return {score, feedback, ready} for one job/resume pair.

    Raises ValueError when the LLM response is unusable.
    """
    user_prompt = (
        f"Job title: {job.title}\n"
        f"Company: {job.company_name}\n"
        f"Job type: {job.job_type}\n"
        f"Job description:\n{job.description[:8000]}\n\n"
        f"Resume to score:\n{resume_text[:12000]}"
    )
    raw = complete(_ATS_SYSTEM_PROMPT, user_prompt, schema=_ATS_SCHEMA)
    try:
        result = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"LLM returned invalid JSON: {exc}") from exc
    if not isinstance(result, dict):
        raise ValueError("LLM response is not a JSON object")
    try:
        score = int(result.get("score", 0))
    except (TypeError, ValueError):
        score = 0
    return {
        "score": max(0, min(100, score)),
        "feedback": str(result.get("feedback", "")),
        "ready": bool(result.get("ready", False)),
    }


def score_resume_deterministic(
    job: JobEntry, resume_text: str, matching: MatchingConfig
) -> dict:
    """Keyword-coverage scorer using Stage 1's matching-config weights.

    Buckets: general job keywords (experience weight), in-demand
    technologies present in the job (prospects weight), role keywords
    present in the job (education weight). Each bucket contributes its
    coverage (0-100) times its weight; empty buckets are excluded from
    the denominator. Feedback lists missing keywords per bucket.
    """
    keywords = _extract_job_keywords(job)
    tokens = set(_tokenize(resume_text))
    keyword_set = set(keywords)
    buckets: dict[str, list[str]] = {
        "experience": [
            k
            for k in keywords
            if k not in set(matching.in_demand_technologies)
            and k not in set(matching.role_keywords)
        ],
        "prospects": [
            k for k in keywords if k in set(matching.in_demand_technologies)
        ],
        "education": [
            k for k in keywords if k in set(matching.role_keywords)
        ],
    }
    weights = matching.score_weights
    weight_map = {
        "experience": weights.experience,
        "prospects": weights.prospects,
        "education": weights.education,
    }

    total_weight = 0.0
    weighted_score = 0.0
    missing_parts: list[str] = []
    for name, bucket in buckets.items():
        if not bucket:
            continue
        matched = [k for k in bucket if k in tokens]
        coverage = 100.0 * len(matched) / len(bucket)
        weighted_score += coverage * weight_map[name]
        total_weight += weight_map[name]
        missing = [k for k in bucket if k not in tokens]
        if missing:
            missing_parts.append(
                f"Missing {name} keywords: " + ", ".join(missing[:10])
            )

    score = round(weighted_score / total_weight) if total_weight else 0
    score = max(0, min(100, score))
    feedback = "\n".join(missing_parts)
    return {
        "score": score,
        "feedback": feedback,
        "ready": bool(keyword_set) and score >= 80,
    }


def combine_scores(llm_result: dict, deterministic_result: dict) -> dict:
    """Merge the two independent ATS signals into one iteration record.

    Combined score = round(LLM_WEIGHT * llm + DETERMINISTIC_WEIGHT * det),
    feedback concatenated (LLM first). `ready` carries the LLM's flag;
    the loop decides advancement via the combined score against the
    configured threshold.
    """
    score = round(
        LLM_WEIGHT * llm_result.get("score", 0)
        + DETERMINISTIC_WEIGHT * deterministic_result.get("score", 0)
    )
    feedback_parts = [
        part
        for part in (
            llm_result.get("feedback", ""),
            deterministic_result.get("feedback", ""),
        )
        if part
    ]
    return {
        "score": max(0, min(100, score)),
        "feedback": "\n".join(feedback_parts),
        "ready": bool(llm_result.get("ready", False)),
    }

"""Stage 2 substage: section-targeted LaTeX resume editing.

edit_base_resume() minimally edits the base resume for one job: the LLM
rewrites only the bulletpoints/skills/summary section content identified
by configurable markers, the edits are applied programmatically (the LLM
never touches LaTeX structure), and a difflib check verifies that text
outside the permitted sections is unchanged. Artifact on disk:
data/resumes/<job_id>.tex (docs/design/stage2-resume-generation.md).
"""

import difflib
import json
import re
from pathlib import Path

from src.config import PipelineConfig
from src.llm import complete
from src.models import JobEntry

# Module constant so tests can monkey-patch it to a temp directory.
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
RESUMES_DIR = PROJECT_ROOT / "data" / "resumes"

# Logical sections Stage 2 may edit (plan.md: bulletpoints, skills, summary).
EDITABLE_SECTIONS = ("summary", "skills", "experience")

# Default marker scheme: unique begin-marker substrings in the base .tex.
# An empty stage2.latex_section_markers config falls back to auto-detection
# of \begin{rSection}{Name} / \tableEnv{Name} blocks by keyword.
DEFAULT_SECTION_MARKERS = {
    "summary": "\\begin{rSection}{Summary}",
    "experience": "\\begin{rSection}{Work Experience}",
    "skills": "\\tableEnv{Skills}{",
}

_AUTO_KEYWORDS = {
    "summary": ("summary",),
    "experience": ("work experience", "experience"),
    "skills": ("skills",),
}

_EDIT_SYSTEM_PROMPT = (
    "You are an expert resume editor. You tailor an existing LaTeX resume to one "
    "job description. Rules: edit ONLY the sections you are given; keep the "
    "candidate's real experience, employers and dates exactly as provided; never "
    "invent employers, degrees or technologies the candidate does not have; weave "
    "the job description's keywords naturally into the existing bullet points and "
    "the summary; keep the phrasing human, specific and concise — no generic AI "
    "tone, no filler adjectives; keep valid LaTeX (escape %, &, # as LaTeX "
    "requires)."
)

_EDIT_SCHEMA = {
    "type": "object",
    "properties": {
        name: {
            "type": "string",
            "description": f"Rewritten {name} section content (LaTeX), without the section markers",
        }
        for name in EDITABLE_SECTIONS
    },
}


def resolve_base_resume_path(job: JobEntry, config: PipelineConfig) -> Path:
    """Resolve the base resume path: job metadata first, then config fallback.

    Relative paths resolve against job-pipeline/ (PROJECT_ROOT). Raises
    FileNotFoundError when nothing is configured or the file is missing.
    """
    configured = str(
        job.metadata.get("base_resume_path") or config.base_resume_path or ""
    )
    if not configured:
        raise FileNotFoundError(
            "No base_resume_path in job metadata or config.base_resume_path"
        )
    path = Path(configured)
    if not path.is_absolute():
        path = (PROJECT_ROOT / configured).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Base resume not found: {path}")
    return path


def _matching_brace(text: str, open_idx: int) -> int:
    """Return the index of the brace matching the one at open_idx."""
    depth = 0
    for idx in range(open_idx, len(text)):
        char = text[idx]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return idx
    raise ValueError("Unbalanced braces in LaTeX source")


def find_section_span(latex: str, marker: str) -> tuple[int, int] | None:
    """Return the (start, end) character span of a section's editable content.

    `marker` is a unique begin-marker substring (e.g.
    `\\begin{rSection}{Summary}`). For begin/end environments the content
    runs from just after the marker to the matching `\\end{<env>}`; for
    brace-delimited blocks (e.g. `\\tableEnv{Skills}{`) to the matching
    closing brace. Returns None when the marker is absent.
    """
    start = latex.find(marker)
    if start == -1:
        return None
    content_start = start + len(marker)
    env_match = re.search(r"\\begin\{([^}]+)\}", marker)
    if env_match:
        end_token = "\\end{" + env_match.group(1) + "}"
        end = latex.find(end_token, content_start)
        if end == -1:
            return None
        return (content_start, end)
    open_idx = latex.find("{", content_start - 1)
    if open_idx == -1:
        return None
    close_idx = _matching_brace(latex, open_idx)
    return (content_start, close_idx)


def detect_section_markers(latex: str) -> dict[str, str]:
    """Auto-detect begin-marker substrings for the editable sections.

    Fallback when stage2.latex_section_markers is empty: scans
    \\begin{rSection}{X} / \\tableEnv{X} blocks and keyword-matches the
    section titles (case-insensitive).
    """
    markers: dict[str, str] = {}
    pattern = re.compile(r"\\begin\{rSection\}\{([^}]*)\}|\\tableEnv\{([^}]*)\}")
    for name, keywords in _AUTO_KEYWORDS.items():
        for match in pattern.finditer(latex):
            title = (match.group(1) or match.group(2) or "").strip().lower()
            if any(keyword in title for keyword in keywords):
                marker = match.group(0)
                if marker.startswith("\\tableEnv") and not marker.endswith("{"):
                    marker += "{"  # brace-delimited block: include the content brace
                markers[name] = marker
                break
    return markers


def locate_sections(latex: str, config: PipelineConfig) -> dict[str, tuple[int, int]]:
    """Map each editable section name to its content span in the base LaTeX.

    Configured markers win; an empty config falls back to auto-detection.
    Sections whose marker is absent or unterminated are skipped.
    """
    configured = config.stage2.latex_section_markers or {}
    markers = {k: v for k, v in configured.items() if k in EDITABLE_SECTIONS}
    if not markers:
        markers = detect_section_markers(latex)
    spans: dict[str, tuple[int, int]] = {}
    for name, marker in markers.items():
        span = find_section_span(latex, marker)
        if span is not None:
            spans[name] = span
    return spans


def _validate_edit(base: str, spans: dict[str, tuple[int, int]], result: str) -> None:
    """Verify every diff region between base and result lies inside spans."""
    allowed = list(spans.values())
    matcher = difflib.SequenceMatcher(None, base, result, autojunk=False)
    for tag, i1, i2, _j1, _j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        if not any(i1 >= start and i2 <= end for start, end in allowed):
            raise ValueError(
                f"Edit touches text outside the permitted sections "
                f"(opcode {tag} at {i1}:{i2})"
            )


def apply_section_edits(
    base_latex: str, spans: dict[str, tuple[int, int]], edits: dict
) -> str:
    """Apply per-section content edits right-to-left, then verify the result."""
    result = base_latex
    for name in sorted(spans, key=lambda n: spans[n][0], reverse=True):
        replacement = edits.get(name)
        if not isinstance(replacement, str) or not replacement.strip():
            continue
        start, end = spans[name]
        result = result[:start] + replacement.strip() + result[end:]
    _validate_edit(base_latex, spans, result)
    return result


def _build_edit_user_prompt(
    job: JobEntry, sections: dict[str, str], candidate: dict, feedback: str
) -> str:
    """Build the editor user prompt: job context, current sections, feedback."""
    parts = [
        f"Job title: {job.title}",
        f"Company: {job.company_name}",
        f"Tags: {', '.join(job.tags)}",
        f"Job description:\n{job.description[:8000]}",
        "Candidate profile:",
        f"  Skills: {', '.join(candidate.get('skills') or [])}",
        f"  Experience: {' | '.join(candidate.get('experience') or [])}",
        f"  Education: {' | '.join(candidate.get('education') or [])}",
    ]
    for name, content in sections.items():
        parts.append(f"Current {name} section content (edit ONLY this):\n{content}")
    if feedback:
        parts.append(f"ATS feedback from the previous iteration to address:\n{feedback}")
    return "\n\n".join(parts)


def edit_base_resume(
    job: JobEntry,
    base_latex: str,
    config: PipelineConfig,
    feedback: str = "",
) -> str:
    """Return the tailored LaTeX with only the permitted sections edited.

    The LLM rewrites the summary/skills/experience section content; the
    edits are applied programmatically and validated so text outside the
    permitted spans is unchanged. Raises ValueError when no editable
    section can be located or the LLM response is unusable.
    """
    spans = locate_sections(base_latex, config)
    if not spans:
        raise ValueError(
            "No editable sections located in the base resume "
            "(check stage2.latex_section_markers)"
        )
    sections = {name: base_latex[start:end] for name, (start, end) in spans.items()}
    candidate = config.candidate_profile.model_dump()
    user_prompt = _build_edit_user_prompt(job, sections, candidate, feedback)
    raw = complete(_EDIT_SYSTEM_PROMPT, user_prompt, schema=_EDIT_SCHEMA)
    try:
        edits = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"LLM returned invalid JSON: {exc}") from exc
    if not isinstance(edits, dict):
        raise ValueError("LLM response is not a JSON object")
    return apply_section_edits(base_latex, spans, edits)


def save_resume(job_id: str, latex: str) -> Path:
    """Write the tailored LaTeX artifact to data/resumes/<job_id>.tex."""
    RESUMES_DIR.mkdir(parents=True, exist_ok=True)
    path = RESUMES_DIR / f"{job_id}.tex"
    path.write_text(latex, encoding="utf-8")
    return path


def load_resume_artifact(job: JobEntry) -> str | None:
    """Return the tailored resume text when an artifact exists on disk."""
    resume_meta = job.metadata.get("resume") or {}
    path_value = (
        resume_meta.get("path") if isinstance(resume_meta, dict) else None
    )
    if not path_value:
        return None
    path = Path(str(path_value))
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8")

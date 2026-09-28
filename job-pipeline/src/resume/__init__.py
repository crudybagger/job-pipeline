"""Stage 2 — Matching Resume Generation package
(docs/design/stage2-resume-generation.md): section-targeted LaTeX editing,
the independent ATS scoring substage, and the generate -> score ->
feedback loop that advances entries to resume_ready.
"""

from src.resume.generate import edit_base_resume, resolve_base_resume_path, save_resume

__all__ = ["edit_base_resume", "resolve_base_resume_path", "save_resume"]

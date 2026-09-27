"""Automation package for the job-pipeline repository.

This package contains helper utilities that allow the repository to
automatically process open issues, generate placeholder implementations,
and keep the issue tracker (`issues.md`) up‑to‑date.  The automation can be
run as a long‑running process (see ``run_issue_loop.py``) or invoked
periodically via a scheduler such as ``cron``.

Only the Python standard library is used so the script works out of the
box in the existing environment.  Git operations are performed only when
the repository is a valid Git repository; otherwise they are skipped to
avoid failures in environments without a ``.git`` folder (for example in
the execution sandbox used for unit tests).
"""

# Export the public API of the automation package.
__all__ = [
    "issue_tracker",
]

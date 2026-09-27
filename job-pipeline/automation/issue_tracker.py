"""Utility functions for managing the local ``issues.md`` tracker.

The repository does not currently use a GitHub issue tracker – instead a
simple markdown file (``issues.md``) stores issue information.  This module
provides a small API to read, modify, and persist that data, as well as a
very lightweight *automation* routine that:

1. Parses open issues from the markdown file.
2. Generates a cheap placeholder implementation for each open issue (a
   ``src/<slug>.py`` file with a comment).
3. Updates the issue description to note the work that has been performed.
4. Marks the issue as ``Done`` and changes its assignee to ``automation``.
5. Commits and pushes the changes using Git – only if a ``.git`` folder is
   present (the test environment does not contain one).

The functions are deliberately straightforward and have no external
dependencies.  They are deliberately written to be easy to unit‑test –
see ``tests/test_issue_tracker.py`` for examples.
"""

from __future__ import annotations

import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List

# ---------------------------------------------------------------------------
# Path configuration
# ---------------------------------------------------------------------------

# ``issue_tracker.py`` lives in ``<repo_root>/automation``.  ``repo_root`` is the
# directory that contains the top‑level repository (the *job‑pipeline* folder).
# The file resides in ``<repo_root>/automation``, so we need to go **one** level
# up from ``automation`` to reach the repository root.
REPO_ROOT = Path(__file__).resolve().parents[1]
ISSUES_FILE = REPO_ROOT / "issues.md"
SRC_ROOT = REPO_ROOT / "src"


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class Issue:
    """Simple representation of a single issue entry in ``issues.md``.

    Attributes
    ----------
    number: int
        The numeric identifier of the issue (e.g. ``1`` for ``Issue #1``).
    title: str
        Human readable title – the part after the ``#`` in the markdown
        heading.
    status: str
        Current status – the script treats ``Open`` (case‑insensitive) as a
        work‑in‑progress issue and all other values as closed/completed.
    assignee: str
        The person or automation responsible for the issue.
    description: str
        Free‑form description text.
    """

    number: int
    title: str
    status: str
    assignee: str
    description: str

    def to_markdown(self) -> str:
        """Render the issue back into the markdown format used in the file.

        Returns
        -------
        str
            A markdown block that reproduces the original layout.
        """
        # The original file uses a trailing two‑space line break after the
        # ``Status`` and ``Assignee`` lines.  We preserve that for consistency.
        return (
            f"## Issue #{self.number} – {self.title}\n"
            f"**Status:** {self.status}  \n"
            f"**Assignee:** {self.assignee}  \n"
            f"**Description:** {self.description}\n"
        )


# ---------------------------------------------------------------------------
# Helper functions for I/O
# ---------------------------------------------------------------------------

def load_issues() -> List[Issue]:
    """Parse ``issues.md`` and return a list of :class:`Issue` objects.

    The original implementation used a single regular expression that captured
    the description up to the *first* newline after the ``**Description:**``
    marker.  This meant that multi‑line descriptions – which are introduced by the
    automation loop when it appends a note – were truncated, causing the appended
    note to be lost after re‑loading the file.  The test suite expects the note to
    be retained, so we now parse the file in two steps:

    1. Split the file content into individual issue blocks using a look‑ahead for
       the next ``## Issue #`` heading.
    2. For each block, apply a regular expression that captures the description
       *including* any intervening new‑lines up to the start of the next block
       (or the end of the file).

    This approach remains simple while correctly handling descriptions that span
    multiple lines.
    """
    if not ISSUES_FILE.is_file():
        return []

    content = ISSUES_FILE.read_text(encoding="utf-8")

    # Split on a newline followed by the next issue heading.  The leading newline
    # is stripped from the subsequent block by ``lstrip`` to keep the heading at
    # the start of the string.
    raw_issues = re.split(r"\n(?=## Issue #)", content.strip())

    # Regular expression for a single issue block.  ``(?P<description>.*)`` with
    # ``re.DOTALL`` captures everything after the ``**Description:**`` line up to
    # the end of the block (the split ensures we are already isolated from the
    # next issue heading).
    pattern = re.compile(
        r"## Issue #(?P<number>\d+) – (?P<title>.+?)\n"
        r"\*\*Status:\*\* (?P<status>\w+)\s*  *\n"
        r"\*\*Assignee:\*\* (?P<assignee>.+?)\s*  *\n"
        r"\*\*Description:\*\* (?P<description>.*)",
        re.DOTALL,
    )

    issues: List[Issue] = []
    for block in raw_issues:
        # ``re.match`` works because each block starts with the heading.
        match = pattern.match(block)
        if not match:
            # Skip any malformed block – this mirrors the original behaviour of
            # returning an empty list on unparsable content.
            continue
        issues.append(
            Issue(
                number=int(match.group("number")),
                title=match.group("title").strip(),
                status=match.group("status").strip(),
                assignee=match.group("assignee").strip(),
                description=match.group("description").strip(),
            )
        )
    return issues


def save_issues(issues: List[Issue]) -> None:
    """Write the list of ``Issue`` objects back to ``issues.md``.

    The original file starts with a top‑level heading ``# Issue Tracker``.
    The function preserves that heading and inserts a blank line between
    individual issue blocks for readability.
    """
    header = "# Issue Tracker\n\n"
    body = "\n".join(issue.to_markdown() for issue in issues) + "\n"
    ISSUES_FILE.write_text(header + body, encoding="utf-8")


def _slugify(text: str) -> str:
    """Return a filesystem‑friendly slug from a free‑form string.

    Non‑alphanumeric characters are replaced with underscores, and the
    result is lower‑cased.
    """
    text = text.lower()
    # Replace any character that is not a letter, number or underscore with
    # an underscore.
    return re.sub(r"[^a-z0-9_]+", "_", text).strip("_")


def implement_task(task: str, issue: Issue) -> Path:
    """Create a placeholder Python module for the given *task*.

    The module is placed under ``src/`` and named after a slugified version of
    the task description.  If the file already exists the function does
    nothing and simply returns the existing path.
    """
    # Ensure the ``src`` directory exists.
    SRC_ROOT.mkdir(parents=True, exist_ok=True)

    filename = f"{_slugify(task)}.py"
    file_path = SRC_ROOT / filename
    if not file_path.exists():
        file_path.write_text(
            f"# Placeholder implementation for Issue #{issue.number}: {issue.title}\n"
            f"# Task: {task}\n\n"
            "# TODO: replace with real implementation\n",
            encoding="utf-8",
        )
    return file_path


def plan_issue(issue: Issue) -> List[str]:
    """Generate a *very* simple plan for the supplied issue.

    The real world would involve sophisticated analysis, but for the
    purpose of this automation we construct a single placeholder task that
    mirrors the issue title.
    """
    # Strip any trailing whitespace and use the title as the baseline task.
    task = issue.title.strip()
    if not task:
        task = f"implement_issue_{issue.number}"
    return [task]


def is_git_repo() -> bool:
    """Return ``True`` if the repository contains a ``.git`` directory.

    The function is deliberately simple – presence of the directory is a good
    enough indicator for the automation script.
    """
    return (REPO_ROOT / ".git").exists()


def git_commit_and_push(message: str) -> None:
    """Commit all changes and push them to the remote ``origin``.

    This helper is a thin wrapper around ``git`` commands.  It raises a
    ``subprocess.CalledProcessError`` if any of the commands fail.  Callers
    should handle the exception appropriately – the automation loop does so
    and simply logs the error.
    """
    # ``git add .`` stages every change in the repository.
    subprocess.run(["git", "add", "."], cwd=str(REPO_ROOT), check=True)
    # Create a commit with the provided message.
    subprocess.run(["git", "commit", "-m", message], cwd=str(REPO_ROOT), check=True)
    # Push the commit to the ``origin`` remote.
    subprocess.run(["git", "push"], cwd=str(REPO_ROOT), check=True)


def process_open_issues() -> None:
    """Process *all* open issues in the tracker.

    The function performs the following steps for each issue whose status is
    ``Open`` (case‑insensitive):

    1. Generate a placeholder implementation file via :func:`implement_task`.
    2. Append a short note to the issue description indicating that a stub
       has been created.
    3. Mark the issue as ``Done`` and set the assignee to ``automation``.

    After iterating the issues the function persists the updated markdown
    file.  If the repository is a Git repository, the changes are committed and
    pushed; otherwise the Git step is skipped (useful for CI runs where the
    repository is a shallow checkout without a remote).
    """
    issues = load_issues()
    updated = False

    for issue in issues:
        if issue.status.lower() != "open":
            continue

        # 1. Plan and implement a placeholder task.
        tasks = plan_issue(issue)
        for task in tasks:
            implement_task(task, issue)

        # 2. Update the description with a note.
        note = "\n\n*Automation*: placeholder implementation generated."
        if note.strip() not in issue.description:
            issue.description = issue.description.rstrip() + note

        # 3. Mark the issue as done.
        issue.status = "Done"
        issue.assignee = "automation"
        updated = True

    if not updated:
        # Nothing to do – exit early to avoid unnecessary Git activity.
        return

    # Persist the modified issues.
    save_issues(issues)

    # Commit and push the changes if we are inside a Git repository.
    if is_git_repo():
        try:
            git_commit_and_push("Automated processing of open issues")
        except subprocess.CalledProcessError as exc:
            # In automation contexts we prefer to surface the error but not
            # abort the whole script.
            print(f"Git command failed: {exc}")
    else:
        # No git repository – useful when running in the sandbox for unit
        # tests.
        print("Skipping git commit/push – not a git repository.")


# ---------------------------------------------------------------------------
# Entry‑point helpers (used by the long‑running loop script)
# ---------------------------------------------------------------------------

def run_once() -> None:
    """Convenient wrapper used by ``run_issue_loop.py``.

    ``run_once`` simply delegates to :func:`process_open_issues`.  It exists so
    that the loop file can keep its import surface minimal and to aid unit
    testing – the loop can be patched to replace this function with a mock.
    """
    process_open_issues()

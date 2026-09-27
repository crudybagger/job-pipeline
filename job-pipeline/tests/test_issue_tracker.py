"""Tests for the automation issue‑tracker utilities.

The tests are deliberately isolated from the real repository by creating a
temporary directory that mimics the expected layout (``issues.md`` and a
``src`` folder).  All paths in :mod:`automation.issue_tracker` are monkey‑
patched to point at this temporary location so that the production files are
unchanged.
"""

from __future__ import annotations

import pathlib
import shutil
import tempfile
import textwrap

import pytest

# The module under test lives in ``automation.issue_tracker``.  Importing it
# activates the module‑level constants.  We will patch those constants after
# import.
from automation import issue_tracker


SAMPLE_ISSUES = textwrap.dedent(
    """
    # Issue Tracker

    ## Issue #10 – Test Issue Ten
    **Status:** Open  
    **Assignee:** planner  
    **Description:** This is a sample open issue for test case ten.

    ## Issue #11 – Another Issue
    **Status:** Open  
    **Assignee:** developer  
    **Description:** Another open issue that should be processed.
    """
).lstrip()


@pytest.fixture()
def temp_repo():
    """Create a temporary repository layout for the duration of a test.

    The fixture yields a ``pathlib.Path`` pointing at the temporary directory.
    The directory contains an ``issues.md`` file and an empty ``src`` folder.
    After the test the directory and all its contents are removed.
    """
    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td)
        # Create the minimal repo structure.
        (root / "src").mkdir(parents=True, exist_ok=True)
        (root / "issues.md").write_text(SAMPLE_ISSUES, encoding="utf-8")
        yield root
        # TemporaryDirectory cleans up automatically.


def _patch_module_paths(tmp_root: pathlib.Path) -> None:
    """Patch global paths in ``automation.issue_tracker`` to point to *tmp_root*.

    This function mutates the module-level constants ``ISSUES_FILE``,
    ``SRC_ROOT`` and ``REPO_ROOT`` so that all file operations are confined to
    the temporary directory used by the test.
    """
    issue_tracker.ISSUES_FILE = tmp_root / "issues.md"
    issue_tracker.SRC_ROOT = tmp_root / "src"
    issue_tracker.REPO_ROOT = tmp_root
    # Ensure git detection is disabled – the temporary directory does not
    # contain a ``.git`` folder.
    issue_tracker.is_git_repo = lambda: False


def test_load_and_save_issues(temp_repo: pathlib.Path):
    """Round‑trip loading and saving of the ``issues.md`` file.

    The test validates that ``load_issues`` parses the sample markdown into
    :class:`Issue` objects correctly and that ``save_issues`` writes a file that
    can be parsed again without loss of information.
    """
    _patch_module_paths(temp_repo)

    issues = issue_tracker.load_issues()
    assert len(issues) == 2
    # Verify fields of the first issue.
    first = issues[0]
    assert first.number == 10
    assert first.title == "Test Issue Ten"
    assert first.status == "Open"
    assert first.assignee == "planner"
    assert "sample open issue" in first.description

    # Modify the status and save back.
    first.status = "Done"
    issue_tracker.save_issues(issues)

    # Reload and verify the change persisted.
    reloaded = issue_tracker.load_issues()
    assert any(i.number == 10 and i.status == "Done" for i in reloaded)


def test_process_open_issues_creates_files_and_updates_issues(temp_repo: pathlib.Path):
    """``process_open_issues`` should generate placeholder modules and update
    the issue tracker.
    """
    _patch_module_paths(temp_repo)

    # Run the processing function – this should handle both open issues.
    issue_tracker.process_open_issues()

    # After processing, the issues file should reflect ``Done`` status.
    issues = issue_tracker.load_issues()
    assert all(i.status == "Done" for i in issues)
    assert all(i.assignee == "automation" for i in issues)
    # The description should contain the automation note.
    for i in issues:
        assert "*Automation*: placeholder implementation generated" in i.description

    # Verify placeholder source files exist.
    expected_files = [
        temp_repo / "src" / "test_issue_ten.py",
        temp_repo / "src" / "another_issue.py",
    ]
    for path in expected_files:
        assert path.is_file(), f"Expected placeholder file {path} not found"

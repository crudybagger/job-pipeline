"""Namespace wrapper for the automation utilities.

The actual implementation of the automation logic lives inside the
``job-pipeline/automation`` package.  When the repository is executed from the
top‑level directory (``/e/jobs``), the ``automation`` package is not on the
Python import search path, which leads to ``ModuleNotFoundError`` when running
``python -m automation.run_issue_loop`` or importing ``automation`` in the test
suite.

This ``__init__`` file makes ``automation`` a *namespace package* by extending
its ``__path__`` attribute to include the real implementation directory.  As a
result, statements such as ``import automation.issue_tracker`` resolve to the
modules under ``job-pipeline/automation`` without requiring any changes to the
existing code or tests.

The wrapper is deliberately lightweight – it does not import any submodules at
import time, preserving the original lazy‑loading behaviour of the package.
"""

from __future__ import annotations

import pathlib
import sys

# Determine the absolute path to the real automation package located within the
# ``job-pipeline`` directory.
# ``__file__`` points to ``/e/jobs/automation/__init__.py``.  The implementation
# lives one directory up (the repository root) under ``job-pipeline/automation``.
# ``parents[1]`` (or ``parent.parent``) therefore yields ``/e/jobs``.
_repo_root = pathlib.Path(__file__).resolve().parents[1]
_implementation_path = _repo_root / "job-pipeline" / "automation"

if not _implementation_path.is_dir():
    # If the expected directory does not exist we raise an ImportError to make
    # the problem obvious at import time.
    raise ImportError(
        f"Automation implementation not found at expected location: {_implementation_path}"
    )

# ``__path__`` tells Python where to look for submodules of this package.  By
# overriding it with a list containing the implementation path we effectively
# turn this package into a namespace that forwards imports to the real code.
__path__ = [str(_implementation_path)]

# Ensure the implementation directory is also discoverable via ``sys.path`` –
# this helps with tools that rely on ``sys.path`` rather than ``__path__``.
if str(_implementation_path) not in sys.path:
    sys.path.insert(0, str(_implementation_path))

# The public API mirrors the original ``automation`` package.
__all__ = ["issue_tracker", "run_issue_loop"]

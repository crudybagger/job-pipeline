"""Simple long‑running loop that processes open issues every 10 minutes.

The script can be started in a terminal session (or as a background service)
and will repeatedly invoke :func:`automation.issue_tracker.run_once`.  Errors are
caught and logged so that a single failure does not terminate the loop.

Usage::

    $ python -m automation.run_issue_loop

The infinite ``while`` loop is deliberately straightforward – advanced use
cases can replace this with a proper scheduler (e.g. ``systemd`` timers or
``cron``) without modifying the core logic.
"""

import time
import traceback

from automation.issue_tracker import run_once


def main() -> None:
    """Run ``run_once`` indefinitely, pausing 600 seconds between runs.

    The function prints a timestamped log line before each iteration so that
    operators can see activity in the console output.
    """
    while True:
        try:
            print(f"[Automation] Starting issue processing at {time.strftime('%Y-%m-%d %H:%M:%S')}")
            run_once()
        except Exception as exc:  # pragma: no cover – defensive; tests cover core logic
            # Print a full traceback for debugging – in production you might
            # want to route this to an external logging system.
            print("[Automation] Unexpected error during processing:")
            traceback.print_exc()
        # Sleep for 10 minutes (600 seconds) before the next cycle.
        time.sleep(600)


if __name__ == "__main__":
    main()

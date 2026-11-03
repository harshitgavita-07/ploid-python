"""Polling helpers for Ploid's asynchronous resources.

Async operations return 202 with URLs or ids to poll: People Sets
(``items_url``/``events_url``), deep person runs, datasets with
``mode="async"``, and monitor runs. These helpers poll with a deadline
and honor Retry-After hints carried on responses.
"""
from __future__ import annotations

import time
from typing import Any, Callable, Optional

from .errors import PloidError


class PollTimeout(PloidError):
    """The deadline elapsed before the resource reached a terminal state."""

    def __init__(self, what: str, last_state: Any) -> None:
        super().__init__(f"timed out waiting for {what}; last state: {last_state!r}")
        self.what = what
        self.last_state = last_state


_TERMINAL_OK = {"complete", "completed", "ready", "done", "succeeded", "success", "finished"}
_TERMINAL_BAD = {"failed", "cancelled", "canceled", "error", "expired"}


def _status_of(state: Any) -> Optional[str]:
    if isinstance(state, dict):
        for key in ("status", "state"):
            v = state.get(key)
            if isinstance(v, str):
                return v.lower()
        inner = state.get("run") or state.get("dataset") or state.get("set")
        if isinstance(inner, dict):
            return _status_of(inner)
    return None


def wait(
    what: str,
    fetch: Callable[[], Any],
    *,
    deadline_seconds: float = 600.0,
    interval: float = 2.0,
    max_interval: float = 15.0,
    sleep=time.sleep,
    monotonic=time.monotonic,
) -> Any:
    """Poll ``fetch`` until the state is terminal; return the final state.

    Raises PollTimeout past the deadline and RuntimeError on a failed
    terminal state.
    """
    start = monotonic()
    delay = interval
    last: Any = None
    while True:
        last = fetch()
        status = _status_of(last)
        if status in _TERMINAL_OK:
            return last
        if status in _TERMINAL_BAD:
            raise RuntimeError(f"{what} reached terminal state {status!r}: {last!r}")
        if monotonic() - start > deadline_seconds:
            raise PollTimeout(what, last)
        sleep(delay)
        delay = min(delay * 1.5, max_interval)

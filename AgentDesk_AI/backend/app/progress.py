"""Progress lines and a cancel flag for long tools that run inside the server process (thread isolation).

The executor binds the running ACTION's id for the thread that runs the tool; the tool calls `say()` as it goes ("Reading 3 sources...") and `check()` between
steps. The page reads the lines from `GET /tasks/{id}/progress`. Cancelling the task sets the flag, `check()` raises `Cancelled`, and the tool stops at its
next step: a Python thread cannot be killed, so a tool that never calls `check()` simply finishes first (the executor says so).
Nothing here is stored on disk; lines are short, contain no file content, and are dropped when the action ends.
"""
from __future__ import annotations

import contextvars
import threading
import time

_current: contextvars.ContextVar[str | None] = contextvars.ContextVar("progress_action", default=None)
_lock = threading.Lock()
_lines: dict[str, list[dict]] = {}
_cancel: set[str] = set()
MAX_LINES = 40


class Cancelled(Exception):
    """The user cancelled the task while this tool was working."""


def bind(action_id: str | None):
    """Make `action_id` the current action of this thread / context. Returns a token for `unbind`."""
    if action_id:
        with _lock:
            _lines[action_id] = []
            _cancel.discard(action_id)
    return _current.set(action_id)


def unbind(token, action_id: str | None, keep_lines: bool = True) -> None:
    _current.reset(token)
    if action_id:
        with _lock:
            _cancel.discard(action_id)
            if not keep_lines:
                _lines.pop(action_id, None)


def say(text: str, step: int | None = None, of: int | None = None) -> None:
    """One short line for the person watching: what is happening now."""
    action_id = _current.get()
    if not action_id:
        return
    with _lock:
        lines = _lines.setdefault(action_id, [])
        lines.append({"at": round(time.time(), 1), "text": str(text)[:160], "step": step, "of": of})
        del lines[:-MAX_LINES]


def check() -> None:
    """Raise Cancelled if the user cancelled this action."""
    action_id = _current.get()
    if action_id and action_id in _cancel:
        raise Cancelled()


def request_cancel(action_ids: list[str]) -> None:
    with _lock:
        _cancel.update(action_ids)


def lines(action_id: str) -> list[dict]:
    with _lock:
        return list(_lines.get(action_id, []))

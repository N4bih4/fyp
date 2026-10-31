"""Task and action state machines: one authoritative transition table.

Every assignment to Task.status / Action.status is checked by an ORM attribute
listener, so an illegal transition (e.g. completed -> executing) raises
InvalidTransition at the point of the bug instead of corrupting history.
"""
from __future__ import annotations

from sqlalchemy import event

from .models import Action, ActionStatus as A, Task, TaskStatus as T

OBSERVED: set[tuple[str, str, str]] = set()  # (kind, old, new); used by tests only


class InvalidTransition(RuntimeError):
    pass


# Terminal states have no outgoing edges. Derived from the transitions observed
# in the test suite plus a read of executor.py / main.py. The agentic-loop edges
# (executing <-> awaiting_approval / waiting_retry) could not be exercised in the
# Phase 2 environment because the groq SDK is not installed (see Phase 2 report).
TASK_TRANSITIONS: dict[str, set[str]] = {
    T.CREATED: {T.PLANNED, T.AWAITING_APPROVAL, T.AWAITING_INPUT, T.APPROVED, T.EXECUTING, T.COMPLETED, T.FAILED, T.CANCELLED},
    T.PLANNED: {T.AWAITING_APPROVAL, T.APPROVED, T.REJECTED, T.CANCELLED, T.FAILED},
    T.AWAITING_APPROVAL: {T.APPROVED, T.REJECTED, T.CANCELLED, T.EXECUTING},
    T.APPROVED: {T.EXECUTING, T.REJECTED, T.CANCELLED},
    T.AWAITING_INPUT: {T.CANCELLED, T.REJECTED},
    T.EXECUTING: {T.COMPLETED, T.PARTIALLY_COMPLETED, T.FAILED, T.CANCELLED, T.AWAITING_APPROVAL, T.AWAITING_INPUT, T.WAITING_RETRY, T.PAUSED},
    T.PAUSED: {T.EXECUTING, T.CANCELLED, T.FAILED},
    T.WAITING_RETRY: {T.EXECUTING, T.CANCELLED, T.FAILED},
    T.COMPLETED: set(),
    T.PARTIALLY_COMPLETED: set(),
    T.FAILED: set(),
    T.CANCELLED: set(),
    T.REJECTED: set(),
}
ACTION_TRANSITIONS: dict[str, set[str]] = {
    A.PENDING: {A.APPROVED, A.REJECTED, A.CANCELLED},
    A.APPROVED: {A.RUNNING, A.SKIPPED, A.CANCELLED, A.REJECTED, A.FAILED},  # failed: approval void/expired
    A.RUNNING: {A.SUCCEEDED, A.FAILED, A.PAUSED, A.CANCELLED},  # paused/cancelled: worker was stopped
    A.PAUSED: {A.APPROVED, A.CANCELLED, A.SKIPPED},
    A.SUCCEEDED: set(),
    A.FAILED: set(),
    A.REJECTED: set(),
    A.SKIPPED: set(),
    A.CANCELLED: set(),
}


def can_transition(table: dict[str, set[str]], old: str | None, new: str) -> bool:
    return old is None or old == new or new in table.get(old, set())


def _listener(kind: str, table: dict[str, set[str]]):
    def on_set(target, value, oldvalue, initiator):
        old = oldvalue if isinstance(oldvalue, str) else None
        if not can_transition(table, old, value):
            raise InvalidTransition(f"Illegal {kind} transition {old!r} -> {value!r}")
        OBSERVED.add((kind, old or "", value))
    return on_set


event.listen(Task.status, "set", _listener("task", TASK_TRANSITIONS))
event.listen(Action.status, "set", _listener("action", ACTION_TRANSITIONS))

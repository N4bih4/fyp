"""Run several agents' jobs at the same time.

`submit` starts a request in its own thread (with its own database session) and returns the task as soon as it exists,
so the user can already speak the next request while Scout is still busy. Browser, file, terminal and system jobs run
side by side; jobs that drive the one shared mouse, keyboard and screen take turns (`ui_exclusive`), because two agents
clicking at once would wreck each other's work.
"""
from __future__ import annotations

import contextlib
import logging
import threading
import time
import uuid

from ..database import SessionLocal
from ..models import Task

log = logging.getLogger(__name__)

# Tools that move the shared mouse / keyboard or take over the foreground window. One at a time, whichever agent runs them.
UI_EXCLUSIVE_TOOLS = frozenset({"ui_act", "ui_inspect", "screen_act", "control_desktop", "take_screenshot", "open_application"})
_UI_LOCK = threading.RLock()


@contextlib.contextmanager
def ui_exclusive(tool_name: str):
    """Hold the shared-screen lock while a UI tool runs; other tools do not wait."""
    if tool_name in UI_EXCLUSIVE_TOOLS:
        with _UI_LOCK:
            yield
    else:
        yield


def _find(key: str) -> Task | None:
    with SessionLocal() as db:
        task = db.query(Task).filter(Task.idempotency_key == key).first()
        if task is not None:
            db.expunge(task)
        return task


def submit(command: str, idempotency_key: str | None, registry, settings, wait: float = 4.0) -> Task:
    """Start the request in the background; return its task (in whatever state it has reached) without waiting for it to finish."""
    from ..orchestration import executor

    key = idempotency_key or f"bg-{uuid.uuid4()}"
    box: dict = {}

    def work() -> None:
        try:
            with SessionLocal() as db:
                executor.start_task(db, command, key, registry, settings)
        except Exception as exc:  # noqa: BLE001 - reported to the caller if the task never appeared; otherwise the task shows the failure
            box["error"] = exc
            log.exception("background task failed")

    threading.Thread(target=work, name="agent-job", daemon=True).start()
    deadline = time.monotonic() + wait
    while time.monotonic() < deadline:
        task = _find(key)
        if task is not None:
            return task
        if "error" in box:
            raise RuntimeError(f"The task could not be started: {type(box['error']).__name__}")
        time.sleep(0.05)
    raise RuntimeError("The task did not start in time.")

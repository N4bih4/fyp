"""Run a tool (execute + verify) in a child process that can be killed.

A Python thread cannot be stopped, so a hung tool used to keep running after
its timeout. Here every action runs in a worker process:

- the parent sends {tool class, context, args}; the worker validates the
  args again, executes, verifies, and sends back result + verification;
- on timeout, pause or cancel the parent kills the worker AND every process
  the job started (e.g. a hung winget), then reports that the work was
  stopped. Processes started by earlier, finished jobs (an app the user
  opened) are left alone;
- workers are pooled, so the import cost is paid once, not per action.

The tool class is chosen by the parent from the registry. Nothing in a plan
can name a class path.
"""
from __future__ import annotations

import importlib
import multiprocessing
import threading
import time
import traceback
from dataclasses import dataclass, field
from typing import Any

from ..logging_setup import log_event, redact

STOP_TIMEOUT = "timeout"
STOP_PAUSE = "pause"
STOP_CANCEL = "cancel"


@dataclass
class WorkerOutcome:
    result: dict[str, Any] | None = None
    verification: dict[str, Any] | None = None
    stopped: str | None = None          # timeout | pause | cancel | crashed
    killed_pids: list[int] = field(default_factory=list)
    elapsed: float = 0.0
    worker_pid: int | None = None
    delivered: bool = False             # False: the job never reached the worker (safe to resend)


class StopControl:
    """Lets another request (pause/cancel) stop the action that is running now."""

    def __init__(self):
        self.event = threading.Event()
        self.reason: str | None = None

    def stop(self, reason: str) -> None:
        self.reason = reason
        self.event.set()


_running: dict[str, StopControl] = {}
_running_lock = threading.Lock()


def register(action_id: str) -> StopControl:
    control = StopControl()
    with _running_lock:
        _running[action_id] = control
    return control


def unregister(action_id: str) -> None:
    with _running_lock:
        _running.pop(action_id, None)


def request_stop(action_ids: list[str], reason: str) -> list[str]:
    """Stop the given actions if they are running in this server process."""
    stopped = []
    with _running_lock:
        for action_id in action_ids:
            control = _running.get(action_id)
            if control is not None:
                control.stop(reason)
                stopped.append(action_id)
    return stopped


# ------------------------------------------------------------------ child side
def _worker_main(conn) -> None:  # pragma: no cover - runs in the child process
    while True:
        try:
            job = conn.recv()
        except (EOFError, OSError):
            return
        if job is None:
            return
        try:
            module_name, _, class_name = job["tool_class"].partition(":")
            cls = getattr(importlib.import_module(module_name), class_name)
            tool = cls(job["ctx"])
            parsed = tool.validate_args(job["args"])
            result = tool.execute(parsed)
            if result.success:
                verification = tool.verify(parsed, result)
            else:
                from ..tools.base import Verification

                verification = Verification(passed=False, checks=[], details=result.error)
            conn.send({"result": result.model_dump(mode="json"), "verification": verification.model_dump(mode="json")})
        except Exception as exc:  # noqa: BLE001 - reported to the parent, never swallowed
            conn.send({"error": f"{type(exc).__name__}: {redact(str(exc), 300)}",
                       "trace": redact(traceback.format_exc(), 1200)})


# ------------------------------------------------------------------ parent side
def _children(pid: int) -> set[int]:
    import psutil

    try:
        return {p.pid for p in psutil.Process(pid).children(recursive=True)}
    except psutil.Error:
        return set()


def _kill(pids: list[int]) -> list[int]:
    import psutil

    killed = []
    procs = []
    for pid in pids:
        try:
            proc = psutil.Process(pid)
            proc.kill()
            procs.append(proc)
            killed.append(pid)
        except psutil.Error:
            continue
    psutil.wait_procs(procs, timeout=3)
    return killed


class ToolWorker:
    def __init__(self):
        context = multiprocessing.get_context("spawn")
        self._conn, child = context.Pipe()
        self.process = context.Process(target=_worker_main, args=(child,), daemon=True, name="agentdesk-tool-worker")
        self.process.start()
        child.close()
        self._dead = False

    @property
    def alive(self) -> bool:
        return not self._dead and self.process.is_alive()

    def run(self, job: dict[str, Any], timeout: float, control: StopControl | None = None) -> WorkerOutcome:
        started = time.monotonic()
        before = _children(self.process.pid)
        outcome = WorkerOutcome(worker_pid=self.process.pid)
        try:
            self._conn.send(job)
        except (BrokenPipeError, OSError, EOFError):
            self._dead = True
            outcome.stopped = "crashed"  # died while idle; the job was not delivered  # the worker died while idle; the caller retries on a fresh one
            outcome.elapsed = time.monotonic() - started
            return outcome
        outcome.delivered = True
        deadline = started + timeout
        while True:
            if self._conn.poll(0.05):
                try:
                    message = self._conn.recv()
                except (EOFError, OSError):
                    outcome.stopped = "crashed"
                    break
                if "error" in message:
                    outcome.result = {"success": False, "output": {}, "error": "Tool crashed: " + message["error"]}
                else:
                    outcome.result, outcome.verification = message["result"], message["verification"]
                break
            if not self.process.is_alive():
                outcome.stopped = "crashed"
                break
            reason = control.reason if control and control.event.is_set() else None
            if reason is None and time.monotonic() >= deadline:
                reason = STOP_TIMEOUT
            if reason:
                outcome.stopped = reason
                outcome.killed_pids = self.kill(keep=before)
                break
        outcome.elapsed = time.monotonic() - started
        return outcome

    def kill(self, keep: set[int] = frozenset()) -> list[int]:
        """Kill this worker and the processes its current job started.

        The worker itself is killed and reaped through multiprocessing (reaping it with
        psutil would hide its exit from multiprocessing); the job's own processes with psutil."""
        job_children = sorted(_children(self.process.pid) - set(keep))
        self._dead = True
        self.process.kill()
        self.process.join(timeout=5)
        killed = _kill(job_children)
        return ([self.process.pid] if not self.process.is_alive() else []) + killed

    def close(self) -> None:
        try:
            self._conn.send(None)
        except (OSError, BrokenPipeError):
            pass
        self.process.join(timeout=2)
        if self.process.is_alive():
            self.process.kill()


class WorkerPool:
    def __init__(self, max_idle: int = 2):
        self._idle: list[ToolWorker] = []
        self._lock = threading.Lock()
        self.max_idle = max_idle

    def acquire(self) -> ToolWorker:
        with self._lock:
            while self._idle:
                worker = self._idle.pop()
                if worker.alive:
                    return worker
        return ToolWorker()

    def release(self, worker: ToolWorker) -> None:
        if not worker.alive:
            return
        with self._lock:
            if len(self._idle) < self.max_idle:
                self._idle.append(worker)
                return
        worker.close()

    def warm(self) -> None:
        self.release(ToolWorker())

    def shutdown(self) -> None:
        with self._lock:
            workers, self._idle = self._idle, []
        for worker in workers:
            worker.close()


pool = WorkerPool()


def run_tool(tool, parsed_args, timeout: float, control: StopControl | None = None) -> WorkerOutcome:
    """Execute + verify `tool` in a pooled worker; kill it on timeout or stop request."""
    job = {"tool_class": f"{type(tool).__module__}:{type(tool).__qualname__}", "ctx": tool.ctx,
           "args": parsed_args.model_dump(mode="json")}
    for attempt in range(2):
        worker = pool.acquire()
        try:
            outcome = worker.run(job, timeout, control)
        finally:
            pool.release(worker)
        # Only a job that never reached the worker is sent again; a job that started is never repeated.
        if outcome.delivered or attempt == 1:
            break
    if outcome.stopped:
        log_event("tool_worker_stopped", level=30, tool=tool.name, status=outcome.stopped,
                  detail=f"killed {len(outcome.killed_pids)} process(es)", duration_ms=round(outcome.elapsed * 1000))
    return outcome

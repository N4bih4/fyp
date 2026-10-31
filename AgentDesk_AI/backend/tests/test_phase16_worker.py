"""Tool worker process: real child processes, real kills (no mocks)."""
from __future__ import annotations

import os
import threading
import time
from pathlib import Path

import psutil
import pytest

from app.orchestration import worker
from app.tools.base import ToolContext
from tests.helpers.slow_tool import QuickArgs, QuickTool, SlowArgs, SlowTool


def _gone(pid: int) -> bool:
    try:
        return psutil.Process(pid).status() == psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:
        return True


@pytest.fixture
def ctx(tmp_path):
    return ToolContext(allowed_directories=[tmp_path])


def test_tool_runs_and_verifies_in_another_process(ctx, tmp_path):
    tool = QuickTool(ctx)
    outcome = worker.run_tool(tool, QuickArgs(path=str(tmp_path / "out.txt")), timeout=30)
    assert outcome.stopped is None
    assert outcome.result["success"] and outcome.verification["passed"]
    assert outcome.verification["evidence"]["sha256"]
    assert outcome.result["output"]["worker_pid"] != os.getpid()


def test_timeout_kills_worker_and_the_processes_the_job_started(ctx, tmp_path):
    tool = SlowTool(ctx)
    args = SlowArgs(seconds=30, marker=str(tmp_path / "marker"), child_pid_file=str(tmp_path / "child.pid"))
    w = worker.ToolWorker()
    started = time.monotonic()
    outcome = w.run({"tool_class": "tests.helpers.slow_tool:SlowTool", "ctx": ctx, "args": args.model_dump()}, timeout=3)
    assert outcome.stopped == worker.STOP_TIMEOUT
    assert time.monotonic() - started < 10
    child_pid = int(Path(args.child_pid_file).read_text())
    assert outcome.worker_pid in outcome.killed_pids and child_pid in outcome.killed_pids
    assert _gone(outcome.worker_pid) and _gone(child_pid)
    time.sleep(1)
    assert not Path(args.marker).exists(), "the timed-out tool kept running"


def test_stop_request_cancels_a_running_tool(ctx, tmp_path):
    args = SlowArgs(seconds=30, marker=str(tmp_path / "marker"), child_pid_file=str(tmp_path / "child.pid"))
    control = worker.register("action-1")
    timer = threading.Timer(2.0, lambda: worker.request_stop(["action-1"], worker.STOP_CANCEL))
    timer.start()
    try:
        outcome = worker.run_tool(SlowTool(ctx), args, timeout=60, control=control)
    finally:
        worker.unregister("action-1")
        timer.cancel()
    assert outcome.stopped == worker.STOP_CANCEL and _gone(outcome.worker_pid)


def test_apps_started_by_earlier_jobs_survive_a_later_kill(ctx, tmp_path):
    w = worker.ToolWorker()
    first = w.run({"tool_class": "tests.helpers.slow_tool:QuickTool", "ctx": ctx,
                   "args": {"path": str(tmp_path / "a.txt"), "launch_child": True}}, timeout=30)
    app_pid = first.result["output"]["child_pid"]
    args = SlowArgs(seconds=30, marker=str(tmp_path / "marker"), child_pid_file=str(tmp_path / "child.pid"))
    second = w.run({"tool_class": "tests.helpers.slow_tool:SlowTool", "ctx": ctx, "args": args.model_dump()}, timeout=3)
    try:
        assert second.stopped == worker.STOP_TIMEOUT
        assert app_pid not in second.killed_pids and not _gone(app_pid)
        assert _gone(int(Path(args.child_pid_file).read_text()))
    finally:
        psutil.Process(app_pid).kill()


def test_crash_in_tool_is_reported_not_hidden(ctx, tmp_path):
    w = worker.ToolWorker()
    outcome = w.run({"tool_class": "tests.helpers.slow_tool:QuickTool", "ctx": ctx, "args": {"wrong": 1}}, timeout=30)
    assert outcome.result["success"] is False and "Tool crashed" in outcome.result["error"]
    w.close()


def test_worker_that_died_while_idle_is_replaced_and_job_runs_once(ctx, tmp_path):
    worker.pool.shutdown()
    idle = worker.ToolWorker()
    idle.process.kill()
    idle.process.join(5)
    worker.pool._idle.append(idle)
    worker.pool._idle[-1]._dead = False  # looks usable until a send fails
    outcome = worker.run_tool(QuickTool(ctx), QuickArgs(path=str(tmp_path / "once.txt")), timeout=30)
    assert outcome.delivered and outcome.result["success"]


def test_killed_worker_is_never_reused(ctx, tmp_path):
    args = SlowArgs(seconds=30, marker=str(tmp_path / "m"), child_pid_file=str(tmp_path / "c.pid"))
    first = worker.run_tool(SlowTool(ctx), args, timeout=2)
    assert first.stopped == worker.STOP_TIMEOUT
    second = worker.run_tool(QuickTool(ctx), QuickArgs(path=str(tmp_path / "q.txt")), timeout=30)
    assert second.result["success"] and second.worker_pid != first.worker_pid

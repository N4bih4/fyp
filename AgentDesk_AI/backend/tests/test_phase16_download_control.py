"""Download pause / resume / cancel through the real worker process and the executor."""
from __future__ import annotations

import hashlib
import json
import threading
import time
from pathlib import Path

import pytest

from app.ai.base import Plan, PlanAction
from app.config import Settings
from app.database import SessionLocal
from app.models import ActionStatus, TaskStatus
from app.orchestration import executor, worker
from app.tools.base import ToolContext
from app.tools.registry import ToolRegistry
from tests.helpers.local_download import PAYLOAD, PAYLOAD_SHA, LocalDownloadTool, serve


@pytest.fixture
def server():
    srv = serve()
    yield srv
    srv.shutdown()


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _job(tool, args):
    return {"tool_class": "tests.helpers.local_download:LocalDownloadTool", "ctx": tool.ctx, "args": args}


def _wait_for_part(part: Path, minimum: int = 1, timeout: float = 10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if part.exists() and part.stat().st_size >= minimum:
            return part.stat().st_size
        time.sleep(0.05)
    raise AssertionError("download did not start")


def test_pause_keeps_partial_file_and_resume_continues_with_range(server, tmp_path):
    tool = LocalDownloadTool(ToolContext(allowed_directories=[tmp_path]))
    dest = tmp_path / "big.bin"
    args = {"url": server.url, "output_path": str(dest), "save_as_webpage": False}
    part, meta = tool._partial_paths(dest)

    control = worker.StopControl()
    threading.Thread(target=lambda: (_wait_for_part(part, 200_000), control.stop(worker.STOP_PAUSE)), daemon=True).start()
    first = worker.ToolWorker().run(_job(tool, args), timeout=60, control=control)
    assert first.stopped == worker.STOP_PAUSE
    kept = part.stat().st_size
    assert 0 < kept < len(PAYLOAD) and not dest.exists()
    assert json.loads(meta.read_text())["etag"] == '"v1"'

    second = worker.run_tool(tool, tool.validate_args(args), timeout=60)
    assert second.stopped is None and second.result["success"], second.result
    assert second.result["output"]["resumed_from"] >= kept
    assert server.requests[-1].get("Range") == f"bytes={second.result['output']['resumed_from']}-"
    assert _sha(dest) == PAYLOAD_SHA and not part.exists() and not meta.exists()
    assert second.verification["passed"] and second.verification["evidence"]["sha256"] == PAYLOAD_SHA


def test_server_without_range_support_restarts_cleanly(tmp_path):
    srv = serve(delay=0.0, ranges=False)
    try:
        tool = LocalDownloadTool(ToolContext(allowed_directories=[tmp_path]))
        dest = tmp_path / "big.bin"
        part, meta = tool._partial_paths(dest)
        part.write_bytes(PAYLOAD[:1000])
        meta.write_text(json.dumps({"url": srv.url, "save_as_webpage": False, "etag": '"v1"'}))
        result = tool.execute(tool.validate_args({"url": srv.url, "output_path": str(dest)}))
        assert result.success and result.output["resumed_from"] == 0
        assert _sha(dest) == PAYLOAD_SHA
    finally:
        srv.shutdown()


def _download_task(db, registry, url, dest):
    task = executor.create_task(db, "download test file")
    plan = Plan(actions=[PlanAction(tool="download_web_content", args={"url": url, "output_path": str(dest)})])
    task = executor.plan_task(db, task, registry, Settings(), preplanned=plan)
    assert task.status == TaskStatus.AWAITING_APPROVAL  # high risk: approval is still required
    return executor.approve_task(db, task.id, [task.actions[0].id])  # high risk: named explicitly


def _run_in_thread(task_id, registry, settings):
    box = {}

    def target():
        session = SessionLocal()
        try:
            box["task"] = executor.run_task(session, task_id, registry, settings)
            box["status"] = box["task"].status
        finally:
            session.close()
    thread = threading.Thread(target=target)
    thread.start()
    return thread, box


@pytest.mark.parametrize("stop", ["pause", "cancel"])
def test_executor_pause_resume_and_cancel_a_running_download(db, server, tmp_path, stop):
    ctx = ToolContext(allowed_directories=[tmp_path])
    registry = ToolRegistry(ctx)
    registry._tools["download_web_content"] = LocalDownloadTool(ctx)
    settings = Settings(tool_isolation="process")
    dest = tmp_path / "big.bin"
    part, meta = LocalDownloadTool._partial_paths(dest)
    task = _download_task(db, registry, server.url, dest)

    thread, box = _run_in_thread(task.id, registry, settings)
    _wait_for_part(part, 200_000)
    other = SessionLocal()
    try:
        if stop == "pause":
            executor.pause_task(other, task.id, registry)
        else:
            executor.cancel_task(other, task.id, registry)
    finally:
        other.close()
    thread.join(30)
    assert not thread.is_alive()
    db.expire_all()
    task = executor._get_task(db, task.id)
    action = task.actions[0]

    if stop == "cancel":
        assert task.status == TaskStatus.CANCELLED and action.status == ActionStatus.CANCELLED
        assert not part.exists() and not meta.exists() and not dest.exists()
        return

    assert task.status == TaskStatus.PAUSED and action.status == ActionStatus.PAUSED
    kept = part.stat().st_size
    assert 0 < kept < len(PAYLOAD)
    task = executor.run_task(db, task.id, registry, settings)  # Resume
    assert task.status == TaskStatus.COMPLETED, task.error
    output = json.loads(task.actions[0].result_json)["output"]
    assert output["resumed_from"] >= kept and _sha(dest) == PAYLOAD_SHA
    assert json.loads(task.actions[0].verification_json)["evidence"]["sha256"] == PAYLOAD_SHA


def test_timed_out_task_is_stopped_and_reported(db, tmp_path):
    from tests.helpers.slow_tool import SlowTool

    ctx = ToolContext(allowed_directories=[tmp_path])
    registry = ToolRegistry(ctx)
    registry._tools["slow_test_tool"] = SlowTool(ctx)
    task = executor.create_task(db, "slow")
    plan = Plan(actions=[PlanAction(tool="slow_test_tool", args={
        "seconds": 30, "marker": str(tmp_path / "marker"), "child_pid_file": str(tmp_path / "child.pid")})])
    task = executor.plan_task(db, task, registry, Settings(), preplanned=plan)
    started = time.monotonic()
    task = executor.run_task(db, task.id, registry, Settings(tool_isolation="process", tool_timeout_seconds=2))
    assert time.monotonic() - started < 15
    assert task.status == TaskStatus.FAILED
    assert "Stopped after 2s" in task.actions[0].error
    import psutil
    child = int((tmp_path / "child.pid").read_text())
    assert not psutil.pid_exists(child) or psutil.Process(child).status() == psutil.STATUS_ZOMBIE
    time.sleep(1)
    assert not (tmp_path / "marker").exists()

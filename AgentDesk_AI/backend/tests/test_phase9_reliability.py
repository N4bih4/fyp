"""Phase 9: structured logging, redaction, restart recovery, retention, kill-during-execution."""
from __future__ import annotations

import json
import os
import socket
import sqlite3
import subprocess
import sys
import threading
import time
from datetime import timedelta
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.database import SessionLocal, engine
from app.logging_setup import JsonFormatter, log_dir, log_event, redact
from app.models import Action, ActionStatus, Task, TaskStatus, utcnow
from app.retention import prune

BACKEND = Path(__file__).resolve().parents[1]


def _log_lines() -> list[dict]:
    path = log_dir() / "agentdesk.log"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


# ------------------------------------------------------------------ redaction
@pytest.mark.parametrize("secret", [
    "gsk_" + "A1b2C3d4E5f6G7h8I9j0",
    "sk-" + "proj-abcdefghijklmnop1234",
    "AIza" + "SyD-abcdefghijklmnopqrstuvwxyz",
    "Bearer abcdefghijklmnopqrstuvwxyz0123456789",
    "token=" + "h3PWHZ85gXEa8fX71EkCet",
    "GROQ_API_KEY=" + "supersecretvalue123",
    "x" * 20 + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8S9",  # long opaque token
])
def test_redact_removes_secrets(secret):
    out = redact(f"failed calling provider with {secret} and more text")
    for fragment in ("gsk_A1b2", "sk-proj-abc", "AIzaSyD", "abcdefghijklmnopqrstuvwxyz0123", "h3PWHZ85", "supersecretvalue", "A1b2C3d4E5f6G7h8I9j0K1l2"):
        assert fragment not in out
    assert "REDACTED" in out


def test_redact_truncates_long_text_and_keeps_normal_text():
    assert redact("plain error: file not found") == "plain error: file not found"
    assert len(redact("word " * 500, limit=100)) <= 103


def test_formatter_emits_json_with_only_whitelisted_fields(tmp_path):
    import logging

    record = logging.LogRecord("agentdesk", logging.INFO, __file__, 1, "x", None, None)
    record.event = "action_end"
    record.task_id = "t1"
    record.detail = "Bearer abcdefghijklmnopqrstuvwxyz0123456789"
    record.command_text = "SHOULD NOT APPEAR"  # not a whitelisted field name
    line = json.loads(JsonFormatter().format(record))
    assert line["event"] == "action_end" and line["task_id"] == "t1"
    assert "abcdefghijklmnopqrstuvwxyz0123" not in line["detail"]
    assert "command_text" not in line


# ------------------------------------------------------------- real log output
def test_task_lifecycle_is_logged_without_commands_or_secrets(client):
    secret = "sk-" + "livekeyabcdefghijklmnop123456"
    task = client.post("/tasks", json={"command": f"Create a folder called log_probe in Documents (note {secret})"}).json()
    client.post(f"/tasks/{task['id']}/approve", json={})
    client.post(f"/tasks/{task['id']}/run")
    lines = _log_lines()
    events = [(l["event"], l.get("task_id")) for l in lines]
    assert ("task_approved", task["id"]) in events
    assert any(e == "action_start" and t == task["id"] for e, t in events)
    assert any(e == "action_end" and t == task["id"] for e, t in events)
    raw = (log_dir() / "agentdesk.log").read_text(encoding="utf-8")
    assert secret not in raw and "log_probe" not in raw and "Create a folder" not in raw
    end = next(l for l in lines if l["event"] == "action_end" and l.get("task_id") == task["id"])
    assert end["status"] == "succeeded" and end["tool"] == "create_folder"


def test_http_requests_logged_with_request_id_header(client):
    response = client.get("/tasks")
    request_id = response.headers["X-Request-Id"]
    assert len(request_id) == 12
    assert any(l["event"] == "http_request" and l.get("request_id") == request_id and l["path"] == "/tasks" and l["http_status"] == 200
               for l in _log_lines())


def test_failed_action_is_logged_as_warning_with_redacted_detail(db, tmp_path):
    from app.ai.base import Plan, PlanAction
    from app.config import get_settings
    from app.orchestration import executor
    from app.tools.base import ToolContext
    from app.tools.registry import ToolRegistry

    registry = ToolRegistry(ToolContext(allowed_directories=[tmp_path], test_dir=tmp_path))
    plan = Plan(actions=[PlanAction(tool="delete_file", args={"path": str(tmp_path / "missing.txt")})])
    task = executor.plan_task(db, executor.create_task(db, "x"), registry, get_settings(), preplanned=plan)
    task = executor.approve_task(db, task.id, [a.id for a in task.actions])
    task = executor.run_task(db, task.id, registry, get_settings())
    assert task.status == TaskStatus.FAILED
    ends = [l for l in _log_lines() if l["event"] == "action_end" and l.get("task_id") == task.id]
    assert ends and ends[0]["level"] == "WARNING" and ends[0]["status"] == "failed" and "does not exist" in ends[0]["detail"]


# ----------------------------------------------------------------- reliability
def test_sqlite_runs_in_wal_with_busy_timeout_and_foreign_keys():
    with engine.connect() as conn:
        raw = conn.connection
        assert raw.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        assert raw.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
        assert raw.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_concurrent_reads_while_writing_do_not_lock(client, db):
    errors = []

    def poll():
        try:
            for _ in range(30):
                assert client.get("/tasks").status_code == 200
        except Exception as exc:  # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=poll) for _ in range(3)]
    [t.start() for t in threads]
    for i in range(10):
        client.post("/tasks", json={"command": f"hello {i}"})
    [t.join() for t in threads]
    assert not errors


# ------------------------------------------------------------- restart recovery
def _restart():
    from app.main import app

    with TestClient(app):
        pass  # entering the lifespan runs startup recovery


def _task_with(db, status, *actions):
    task = Task(command="recovery probe", status=TaskStatus.CREATED)
    db.add(task)
    db.commit()
    for seq, (st, tool) in enumerate(actions):
        a = Action(task_id=task.id, seq=seq, tool_name=tool, args_json="{}", risk="medium", status=ActionStatus.PENDING)
        db.add(a)
        db.commit()
        a.status = ActionStatus.APPROVED
        db.commit()
        if st != ActionStatus.APPROVED:
            a.status = ActionStatus.RUNNING
            db.commit()
            if st != ActionStatus.RUNNING:
                a.status = st
                db.commit()
    task.status = TaskStatus.EXECUTING
    db.commit()
    if status != TaskStatus.EXECUTING:
        task.status = status
        db.commit()
    return task


def test_restart_fails_interrupted_task_honestly(db):
    task = _task_with(db, TaskStatus.EXECUTING,
                      (ActionStatus.SUCCEEDED, "create_folder"), (ActionStatus.RUNNING, "move_file"), (ActionStatus.APPROVED, "create_folder"))
    _restart()
    db.expire_all()
    task = db.get(Task, task.id)
    done, running, waiting = sorted(task.actions, key=lambda a: a.seq)
    assert task.status == TaskStatus.FAILED and "interrupt" in task.error
    assert done.status == ActionStatus.SUCCEEDED
    assert running.status == ActionStatus.FAILED and running.rollback_status == "unsupported"
    assert "unknown" in running.rollback_detail
    assert waiting.status == ActionStatus.SKIPPED  # never replayed after a restart
    assert any(l["event"] == "task_recovered_after_restart" and l["task_id"] == task.id for l in _log_lines())


@pytest.mark.parametrize("status", [TaskStatus.PAUSED, TaskStatus.AWAITING_APPROVAL, TaskStatus.WAITING_RETRY, TaskStatus.COMPLETED])
def test_restart_leaves_other_states_alone(db, status):
    task = Task(command="keep me", status=TaskStatus.CREATED)
    db.add(task)
    db.commit()
    if status == TaskStatus.COMPLETED:
        task.status = TaskStatus.COMPLETED
    elif status == TaskStatus.AWAITING_APPROVAL:
        task.status = TaskStatus.AWAITING_APPROVAL
    else:
        task.status = TaskStatus.EXECUTING
        db.commit()
        task.status = status
    db.commit()
    _restart()
    db.expire_all()
    assert db.get(Task, task.id).status == status


# ------------------------------------------------------------------- retention
def _old_task(db, days_old, with_backup_dir=None):
    task = Task(command="old", status=TaskStatus.COMPLETED, agent_state_json=json.dumps({"messages": ["private listing"]}))
    db.add(task)
    db.commit()
    plan = {"kind": "restore_backup", "path": "x", "backup": str(with_backup_dir / "content.bak"), "before_sha": "a", "after_sha": "b"} if with_backup_dir else {"kind": "nothing"}
    action = Action(task_id=task.id, seq=0, tool_name="write_text_file", args_json="{}", risk="medium", status=ActionStatus.PENDING,
                    rollback_json=json.dumps(plan), rollback_status="available")
    db.add(action)
    db.commit()
    task.updated_at = utcnow() - timedelta(days=days_old)
    db.commit()
    return task


def test_retention_is_off_by_default_and_deletes_nothing(db, tmp_path):
    backup = tmp_path / ".agentdesk_checkpoints" / "abc"
    backup.mkdir(parents=True)
    (backup / "content.bak").write_text("user data")
    task = _old_task(db, 400, backup)
    result = prune(db, Settings())
    assert result["enabled"] is False
    assert (backup / "content.bak").exists() and db.get(Task, task.id).agent_state_json


def test_retention_clears_old_conversation_and_backups_only(db, tmp_path):
    backup = tmp_path / ".agentdesk_checkpoints" / "abc"
    backup.mkdir(parents=True)
    (backup / "content.bak").write_text("user data")
    old = _old_task(db, 40, backup)
    recent_backup = tmp_path / ".agentdesk_checkpoints" / "new"
    recent_backup.mkdir(parents=True)
    (recent_backup / "content.bak").write_text("recent")
    recent = _old_task(db, 2, recent_backup)

    result = prune(db, Settings(retention_days=30))
    db.expire_all()
    assert result == {"enabled": True, "conversations_cleared": 1, "backups_removed": 1}
    old = db.get(Task, old.id)
    assert old.agent_state_json is None and old.status == TaskStatus.COMPLETED and len(old.actions) == 1  # history kept
    assert old.actions[0].rollback_status == "expired" and "retention" in old.actions[0].rollback_detail
    assert not backup.exists()
    recent = db.get(Task, recent.id)
    assert recent.agent_state_json and recent_backup.exists() and recent.actions[0].rollback_status == "available"


def test_retention_never_touches_unexpected_paths(db, tmp_path):
    victim = tmp_path / "important"
    victim.mkdir()
    (victim / "content.bak").write_text("not a checkpoint")  # right filename, wrong parent folder
    _old_task(db, 90, victim)
    prune(db, Settings(retention_days=30))
    assert (victim / "content.bak").exists()


def test_retention_skips_unfinished_tasks(db):
    task = Task(command="running", status=TaskStatus.CREATED, agent_state_json="{}")
    db.add(task)
    db.commit()
    task.status = TaskStatus.AWAITING_APPROVAL
    task.updated_at = utcnow() - timedelta(days=500)
    db.commit()
    prune(db, Settings(retention_days=30))
    db.expire_all()
    assert db.get(Task, task.id).agent_state_json == "{}"


# ------------------------------------------------- real kill during execution
def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_ready(port: int, timeout: float = 40) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if httpx.get(f"http://127.0.0.1:{port}/health", timeout=1).status_code == 200:
                return
        except httpx.HTTPError:
            time.sleep(0.3)
    raise AssertionError("server did not start")


def test_kill_during_execution_then_restart_reports_honestly(tmp_path):
    home = tmp_path / "home"
    (home / "Documents").mkdir(parents=True)
    db_file = tmp_path / "kill.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db_file}", "AI_PROVIDER": "mock",
           "AGENTDESK_ALLOWED_DIRECTORIES": str(home), "AGENTDESK_TEST_DIR": str(home), "AGENTDESK_MOCK_HOME": str(home),
           "AGENTDESK_REQUIRE_API_TOKEN": "0", "AGENTDESK_LOG_DIR": str(tmp_path / "logs"), "TOOL_TIMEOUT_SECONDS": "300"}
    port = _free_port()
    server = subprocess.Popen([sys.executable, str(BACKEND / "tests" / "helpers" / "slow_server.py"), str(port)], cwd=BACKEND, env=env,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    restarted = None
    try:
        _wait_ready(port)
        base = f"http://127.0.0.1:{port}"
        task = httpx.post(f"{base}/tasks", json={"command": "Create a folder called killed in Documents"}, timeout=10).json()
        httpx.post(f"{base}/tasks/{task['id']}/approve", json={}, timeout=10)
        runner = threading.Thread(target=lambda: _swallow(lambda: httpx.post(f"{base}/tasks/{task['id']}/run", timeout=60)))
        runner.start()
        target = home / "Documents" / "killed"
        deadline = time.time() + 20
        while time.time() < deadline and not target.exists():
            time.sleep(0.1)
        assert target.is_dir(), "the change must have happened before the kill"
        assert httpx.get(f"{base}/tasks/{task['id']}", timeout=10).json()["status"] == "executing"
        server.kill()  # hard kill: no cleanup runs
        server.wait(timeout=10)
        runner.join(timeout=20)

        port2 = _free_port()
        restarted = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port2), "--log-level", "warning"],
                                     cwd=BACKEND, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        _wait_ready(port2)
        after = httpx.get(f"http://127.0.0.1:{port2}/tasks/{task['id']}", timeout=10).json()
        assert after["status"] == "failed" and "interrupt" in after["error"]
        action = after["actions"][0]
        assert action["status"] == "failed" and action["rollback_status"] == "unsupported"
        assert target.is_dir()  # the real change survived; the report says the outcome is unknown, not "succeeded"
        assert "unknown" in action["rollback_detail"]
        # nothing is replayed: the action must still not be re-run, and the DB is intact
        assert httpx.post(f"http://127.0.0.1:{port2}/tasks/{task['id']}/run", timeout=10).json()["status"] == "failed"
        check = sqlite3.connect(db_file)
        assert check.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        check.close()
    finally:
        for proc in (server, restarted):
            if proc and proc.poll() is None:
                proc.kill()
                proc.wait(timeout=10)


def _swallow(fn):
    try:
        fn()
    except Exception:
        pass

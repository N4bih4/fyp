"""Parallel agents: a background request returns at once while the job keeps running, and UI tools take turns."""
from __future__ import annotations

import threading
import time

import pytest
from fastapi.testclient import TestClient

from app.agents import runner
from app.agents.runner import ui_exclusive
from app.database import SessionLocal, init_db
from app.main import app
from app.models import Task, TaskStatus
from app.orchestration import executor


@pytest.fixture()
def client():
    init_db()
    return TestClient(app)


def test_ui_tools_run_one_at_a_time_but_other_tools_do_not_wait():
    inside = []
    peak = [0]
    lock = threading.Lock()

    def job(name):
        with ui_exclusive(name):
            with lock:
                inside.append(name)
                peak[0] = max(peak[0], len(inside))
            time.sleep(0.05)
            with lock:
                inside.remove(name)

    threads = [threading.Thread(target=job, args=("ui_act",)) for _ in range(4)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert peak[0] == 1                                   # the shared mouse / keyboard is never used by two agents at once

    peak[0] = 0
    threads = [threading.Thread(target=job, args=("control_browser",)) for _ in range(4)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert peak[0] > 1                                    # browser, file and terminal work really runs side by side


def test_background_submit_returns_before_the_job_finishes(monkeypatch):
    init_db()
    release = threading.Event()

    def slow_start(db, command, key, registry, settings, auto_approve=False):
        task = executor.create_task(db, command, key)
        task.status = TaskStatus.EXECUTING
        db.commit()
        release.wait(5)
        task.status = TaskStatus.COMPLETED
        db.commit()
        return task

    monkeypatch.setattr(executor, "start_task", slow_start)
    started = time.monotonic()
    task = runner.submit("youtube kholo", "par-1", None, None)
    assert time.monotonic() - started < 2 and task.status == TaskStatus.EXECUTING   # returned while the job is still running
    release.set()
    for _ in range(50):
        with SessionLocal() as db:
            if db.query(Task).filter(Task.idempotency_key == "par-1").one().status == TaskStatus.COMPLETED:
                break
        time.sleep(0.05)
    else:
        pytest.fail("the background job never finished")


def test_two_agents_work_at_the_same_time_through_the_api(client, monkeypatch):
    gate = threading.Event()

    def slow_start(db, command, key, registry, settings, auto_approve=False):
        task = executor.create_task(db, command, key)
        task.status = TaskStatus.EXECUTING
        db.commit()
        gate.wait(5)
        task.status = TaskStatus.COMPLETED
        db.commit()
        return task

    monkeypatch.setattr(executor, "start_task", slow_start)
    from app.agents import dispatcher as d
    monkeypatch.setattr(d, "_dispatcher", None)
    a = client.post("/tasks?background=true", json={"command": "youtube kholo", "idempotency_key": "api-a"})
    b = client.post("/tasks?background=true", json={"command": "volume kam karo", "idempotency_key": "api-b"})
    assert a.status_code == b.status_code == 200
    assert a.headers["X-Agent"] == "Scout" and b.headers["X-Agent"] == "Atlas"
    rows = {r["name"]: r for r in client.get("/agents").json()}
    assert rows["Scout"]["busy"] and rows["Atlas"]["busy"] and not rows["Forge"]["busy"]
    c = client.post("/tasks?background=true", json={"command": "Scout, search chairs on daraz", "idempotency_key": "api-c"})
    assert c.headers["X-Agent"] != "Scout" and "busy" in c.headers["X-Agent-Note"]     # Scout is busy: Shadow moved the job
    gate.set()
    time.sleep(0.5)
    rows = {r["name"]: r for r in client.get("/agents").json()}
    assert not rows["Scout"]["busy"] and not rows["Atlas"]["busy"]

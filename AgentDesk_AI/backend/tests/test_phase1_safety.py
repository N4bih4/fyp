"""Phase 1 regression tests: approval bypass, timeout honesty, single execution, request guard."""
from __future__ import annotations

import os
import threading
import time

from app.models import Action, ActionStatus
from app.orchestration import executor
from app.tools.base import ToolResult


def _folder(name: str) -> str:
    return os.path.join(os.environ["AGENTDESK_MOCK_HOME"], "Documents", name)


def test_client_cannot_request_auto_approve(client):
    r = client.post("/tasks", json={"command": "Create a folder called p1_bypass in Documents", "auto_approve": True})
    assert r.status_code == 422
    assert not os.path.isdir(_folder("p1_bypass"))


def test_medium_risk_waits_for_approval(client):
    j = client.post("/tasks", json={"command": "Create a folder called p1_wait in Documents"}).json()
    assert j["status"] == "awaiting_approval"
    assert j["actions"][0]["status"] == "pending"
    assert not os.path.isdir(_folder("p1_wait"))


class _Slow:
    name = "slow"

    def execute(self, args):
        time.sleep(3)
        return ToolResult(success=True)


def test_timeout_returns_promptly_and_is_honest():
    start = time.time()
    result = executor._run_with_timeout(_Slow(), None, 1)
    assert time.time() - start < 2.0
    assert result.success is False
    assert result.output.get("timed_out") is True
    assert "verify" in result.error.lower()


def test_action_executes_only_once_under_concurrency(client, db, monkeypatch):
    j = client.post("/tasks", json={"command": "Create a folder called p1_once in Documents"}).json()
    client.post(f"/tasks/{j['id']}/approve", json={})
    calls = []
    real = executor._run_with_timeout

    def counted(tool, args, timeout):
        calls.append(1)
        time.sleep(0.3)
        return real(tool, args, timeout)

    monkeypatch.setattr(executor, "_run_with_timeout", counted)
    results = []
    threads = [threading.Thread(target=lambda: results.append(client.post(f"/tasks/{j['id']}/run").status_code)) for _ in range(3)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert len(calls) == 1
    assert os.path.isdir(_folder("p1_once"))
    db.expire_all()
    action = db.query(Action).filter(Action.task_id == j["id"]).one()
    assert action.status == ActionStatus.SUCCEEDED


def test_foreign_host_rejected(client):
    assert client.get("/health", headers={"host": "evil.example"}).status_code == 403
    assert client.get("/health", headers={"host": "127.0.0.1:8000"}).status_code == 200


def test_cross_site_post_rejected(client):
    r = client.post("/tasks", json={"command": "hello"}, headers={"origin": "https://evil.example"})
    assert r.status_code == 403
    r = client.post("/tasks", json={"command": "hello"}, headers={"origin": "http://127.0.0.1:8000"})
    assert r.status_code != 403


def test_same_origin_ui_on_any_port_is_allowed(client):
    r = client.post("/tasks", json={"command": "hello"}, headers={"host": "127.0.0.1:8765", "origin": "http://127.0.0.1:8765"})
    assert r.status_code != 403
    r = client.post("/tasks", json={"command": "hello"}, headers={"host": "127.0.0.1:8765", "origin": "http://127.0.0.1:9999"})
    assert r.status_code == 403

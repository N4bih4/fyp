"""Phase 5: approval binding, expiry, explicit high-risk approval, API token."""
from __future__ import annotations

import json
import os
from datetime import timedelta
from pathlib import Path

import pytest

from app import main as app_main
from app.ai.base import Plan, PlanAction
from app.config import get_settings
from app.models import Action, ActionStatus, TaskStatus, utcnow
from app.orchestration import executor
from app.security import approvals, token as token_mod
from app.tools.base import ToolContext
from app.tools.registry import ToolRegistry


def _home() -> Path:
    return Path(os.environ["AGENTDESK_MOCK_HOME"])


def _delete_task(client, name):
    target = _home() / name
    target.write_text("x")
    task = client.post("/tasks", json={"command": f"Delete the file {target}"}).json()
    assert task["status"] == "awaiting_approval"
    return task, target


# --------------------------------------------------------------- binding
def test_actions_get_a_binding_hash_on_creation(client, db):
    task, _ = _delete_task(client, "p5_bind.txt")
    action = db.query(Action).filter(Action.task_id == task["id"]).one()
    assert action.binding_hash == approvals.binding_for(action)
    assert len(action.binding_hash) == 64


def test_altered_args_before_approval_are_refused(client, db):
    task, target = _delete_task(client, "p5_alter_a.txt")
    other = _home() / "p5_alter_b.txt"
    other.write_text("precious")
    action = db.query(Action).filter(Action.task_id == task["id"]).one()
    action.args_json = json.dumps({"path": str(other)})  # swapped target after planning
    db.commit()
    result = client.post(f"/tasks/{task['id']}/approve", json={"action_ids": [task["actions"][0]["id"]]}).json()
    assert result["status"] == "rejected"
    assert other.exists() and target.exists()


def test_altered_args_after_approval_are_refused_at_execution(client, db):
    task, target = _delete_task(client, "p5_alter_c.txt")
    other = _home() / "p5_alter_d.txt"
    other.write_text("precious")
    aid = task["actions"][0]["id"]
    client.post(f"/tasks/{task['id']}/approve", json={"action_ids": [aid]})
    action = db.query(Action).filter(Action.id == aid).one()
    action.args_json = json.dumps({"path": str(other)})
    db.commit()
    result = client.post(f"/tasks/{task['id']}/run").json()
    assert result["status"] == "failed"
    assert "altered" in result["actions"][0]["error"]
    assert other.exists() and target.exists()


def test_expired_approval_is_refused(client, db):
    task, target = _delete_task(client, "p5_expire.txt")
    aid = task["actions"][0]["id"]
    client.post(f"/tasks/{task['id']}/approve", json={"action_ids": [aid]})
    action = db.query(Action).filter(Action.id == aid).one()
    assert action.approval_expires_at is not None
    action.approval_expires_at = utcnow() - timedelta(seconds=1)
    db.commit()
    result = client.post(f"/tasks/{task['id']}/run").json()
    assert result["status"] == "failed" and "expired" in result["actions"][0]["error"]
    assert target.exists()


def test_fresh_approval_runs_once_and_cannot_be_replayed(client):
    task, target = _delete_task(client, "p5_once.txt")
    aid = task["actions"][0]["id"]
    client.post(f"/tasks/{task['id']}/approve", json={"action_ids": [aid]})
    assert client.post(f"/tasks/{task['id']}/run").json()["status"] == "completed"
    assert not target.exists()
    again = client.post(f"/tasks/{task['id']}/approve", json={"action_ids": [aid]})
    assert again.status_code == 409  # finished tasks cannot be re-approved


def test_approval_for_another_tasks_action_id_is_ignored(client):
    a, ta = _delete_task(client, "p5_cross_a.txt")
    b, tb = _delete_task(client, "p5_cross_b.txt")
    client.post(f"/tasks/{a['id']}/approve", json={"action_ids": [b["actions"][0]["id"]]})
    result = client.post(f"/tasks/{a['id']}/run")
    assert result.status_code == 409
    assert ta.exists() and tb.exists()


def test_low_risk_actions_run_without_expiry(db, tmp_path):
    registry = ToolRegistry(ToolContext(allowed_directories=[tmp_path], test_dir=tmp_path))
    plan = Plan(actions=[PlanAction(tool="list_folder", args={"path": str(tmp_path)})])
    task = executor.plan_task(db, executor.create_task(db, "list"), registry, get_settings(), preplanned=plan)
    action = task.actions[0]
    assert action.risk == "low" and action.status == ActionStatus.APPROVED
    assert action.approval_expires_at is None and action.approved_at is not None


# ------------------------------------------------- explicit high-risk approval
def _two_action_task(db, tmp_path):
    registry = ToolRegistry(ToolContext(allowed_directories=[tmp_path], test_dir=tmp_path))
    target = tmp_path / "victim.txt"
    target.write_text("x")
    plan = Plan(actions=[
        PlanAction(tool="create_folder", args={"path": str(tmp_path / "newdir")}),
        PlanAction(tool="delete_file", args={"path": str(target)}),
    ])
    task = executor.create_task(db, "do two things")
    task = executor.plan_task(db, task, registry, get_settings(), preplanned=plan)
    return task, target


def test_approve_all_skips_high_risk_actions(db, tmp_path):
    task, target = _two_action_task(db, tmp_path)
    task = executor.approve_task(db, task.id)
    by_tool = {a.tool_name: a.status for a in task.actions}
    assert by_tool == {"create_folder": ActionStatus.APPROVED, "delete_file": ActionStatus.PENDING}
    assert task.status == TaskStatus.AWAITING_APPROVAL


def test_bare_yes_with_multiple_pending_including_high_does_not_approve_high(client, db, tmp_path):
    task, target = _two_action_task(db, tmp_path)
    response = client.post(f"/tasks/{task.id}/reply", json={"message": "yes"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "awaiting_approval"
    assert all(a["status"] == "pending" for a in body["actions"])
    assert target.exists()


def test_explicit_ids_approve_high_risk(db, tmp_path):
    task, _ = _two_action_task(db, tmp_path)
    task = executor.approve_task(db, task.id, [a.id for a in task.actions])
    assert task.status == TaskStatus.APPROVED


# --------------------------------------------------------------------- token
def test_token_is_created_once_with_enough_entropy(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTDESK_TOKEN_FILE", str(tmp_path / "t" / "api_token"))
    first = token_mod.load_or_create_token()
    assert len(first) >= 32 and token_mod.load_or_create_token() == first


@pytest.fixture()
def secured(monkeypatch):
    monkeypatch.setattr(app_main, "get_api_token", lambda: "s3cret-token-value")


def test_api_requires_bearer_token(client, secured):
    assert client.get("/tasks").status_code == 401
    assert client.get("/config/status").status_code == 401
    assert client.get("/tools").status_code == 401
    assert client.post("/tasks", json={"command": "hi"}).status_code == 401
    assert client.get("/tasks", headers={"authorization": "Bearer wrong"}).status_code == 401
    assert client.get("/tasks", headers={"authorization": "Basic s3cret-token-value"}).status_code == 401


def test_valid_token_is_accepted(client, secured):
    headers = {"authorization": "Bearer s3cret-token-value"}
    assert client.get("/tasks", headers=headers).status_code == 200
    assert client.get("/config/status", headers=headers).status_code == 200


def test_health_and_preflight_stay_open(client, secured):
    assert client.get("/health").status_code == 200
    r = client.options("/tasks", headers={"Origin": "http://127.0.0.1:5173", "Access-Control-Request-Method": "POST",
                                          "Access-Control-Request-Headers": "authorization,content-type"})
    assert r.status_code == 200


def test_every_task_route_requires_token(client, secured):
    assert client.get("/tasks/abc").status_code == 401
    for path in ("/tasks/abc/approve", "/tasks/abc/reject", "/tasks/abc/run", "/tasks/abc/cancel", "/tasks/abc/reply"):
        assert client.post(path, json={}).status_code == 401, path

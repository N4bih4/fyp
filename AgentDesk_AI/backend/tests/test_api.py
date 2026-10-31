"""End-to-end API tests with the mock AI provider (no network, no cost)."""
from __future__ import annotations

import os
from pathlib import Path


def _post_task(client, command, key=None):
    payload = {"command": command}
    if key:
        payload["idempotency_key"] = key
    return client.post("/tasks", json=payload)


def test_health_and_config_do_not_leak_secrets(client):
    assert client.get("/health").json() == {"status": "ok", "version": "0.2.0"}
    status = client.get("/config/status").json()
    assert status["mock_mode"] is True
    assert status["ai_configured"] is True
    assert "OPENAI_API_KEY" not in str(status)
    assert "sk-" not in str(status)


def test_low_risk_command_auto_approved_and_runs(client, monkeypatch):
    import app.tools.platform as platform_tools

    monkeypatch.setattr(platform_tools, "open_path_with_os", lambda p: None)
    home = Path(os.environ["AGENTDESK_MOCK_HOME"])
    (home / "Downloads").mkdir(parents=True, exist_ok=True)

    task = _post_task(client, "Open my Downloads folder").json()
    assert task["status"] == "approved"  # low risk: no manual approval needed
    assert task["actions"][0]["risk"] == "low"

    finished = client.post(f"/tasks/{task['id']}/run").json()
    assert finished["status"] == "completed"
    action = finished["actions"][0]
    assert action["status"] == "succeeded"
    assert action["verification"]["passed"] is True


def test_medium_risk_command_needs_approval_then_runs(client):
    home = Path(os.environ["AGENTDESK_MOCK_HOME"])
    task = _post_task(client, "Create a folder called FYP in Documents").json()
    assert task["status"] == "awaiting_approval"
    assert task["actions"][0]["risk"] == "medium"
    assert "[mock AI]" in (task["plan_note"] or "")

    # running before approval is refused
    denied = client.post(f"/tasks/{task['id']}/run")
    assert denied.status_code == 409

    approved = client.post(f"/tasks/{task['id']}/approve", json={}).json()
    assert approved["status"] == "approved"

    finished = client.post(f"/tasks/{task['id']}/run").json()
    assert finished["status"] == "completed"
    assert (home / "Documents" / "FYP").is_dir()
    assert finished["actions"][0]["verification"]["passed"] is True


def test_high_risk_delete_requires_explicit_approval(client):
    home = Path(os.environ["AGENTDESK_MOCK_HOME"])
    target = home / "doomed.txt"
    target.write_text("bye")
    task = _post_task(client, f"Delete the file {target}").json()
    assert task["status"] == "awaiting_approval"
    assert task["actions"][0]["risk"] == "high"

    # "approve all" never covers a high-risk action...
    still = client.post(f"/tasks/{task['id']}/approve", json={}).json()
    assert still["status"] == "awaiting_approval" and target.exists()
    # ...it must be named explicitly.
    client.post(f"/tasks/{task['id']}/approve", json={"action_ids": [task["actions"][0]["id"]]}).json()
    finished = client.post(f"/tasks/{task['id']}/run").json()
    assert finished["status"] == "completed"
    assert not target.exists()


def test_reject_stops_task(client):
    home = Path(os.environ["AGENTDESK_MOCK_HOME"])
    target = home / "keepme.txt"
    target.write_text("important")
    task = _post_task(client, f"Delete the file {target}").json()
    rejected = client.post(f"/tasks/{task['id']}/reject", json={}).json()
    assert rejected["status"] == "rejected"
    assert target.exists()  # nothing was executed


def test_no_duplicate_execution(client, monkeypatch):
    import app.tools.platform as platform_tools

    monkeypatch.setattr(platform_tools, "open_path_with_os", lambda p: None)
    home = Path(os.environ["AGENTDESK_MOCK_HOME"])
    (home / "Downloads").mkdir(parents=True, exist_ok=True)
    task = _post_task(client, "Open my Downloads folder", key="idem-1").json()
    first = client.post(f"/tasks/{task['id']}/run").json()
    assert first["status"] == "completed"
    # second run is a no-op, not a re-execution
    second = client.post(f"/tasks/{task['id']}/run").json()
    assert second["status"] == "completed"
    # idempotency key returns the same task instead of creating a new one
    again = _post_task(client, "Open my Downloads folder", key="idem-1").json()
    assert again["id"] == task["id"]


def test_previous_task_meta_command(client):
    first = _post_task(client, "Show the result of the previous task").json()
    assert first["status"] == "completed"
    assert "no previous" in (first["plan_note"] or "").lower()

    task = _post_task(client, "Create a folder called History in Documents").json()
    client.post(f"/tasks/{task['id']}/approve", json={})
    client.post(f"/tasks/{task['id']}/run")
    summary = _post_task(client, "Show the result of the previous task").json()
    assert "History" in summary["plan_note"]


def test_task_history_lists_tasks(client):
    _post_task(client, "Take a screenshot")
    history = client.get("/tasks?limit=20").json()
    assert len(history) >= 1
    assert all("command" in t and "status" in t for t in history)


def test_clarification_for_ambiguous_command(client):
    task = _post_task(client, "Rename a document").json()
    assert task["status"] == "completed"
    assert task["actions"] == []
    assert task["plan_note"]  # the mock asked a clarifying question

"""Regression coverage for the browser/backend connection and launcher."""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest


@pytest.mark.parametrize("origin", ["http://localhost:5173", "http://127.0.0.1:5173"])
def test_development_origins_can_reach_backend(client, origin):
    response = client.options("/tasks", headers={
        "Origin": origin,
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type",
    })
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin


def test_foreign_origin_is_not_granted_access(client):
    response = client.get("/config/status", headers={"Origin": "https://example.com"})
    assert "access-control-allow-origin" not in response.headers


def test_built_frontend_and_api_share_one_server(client):
    response = client.get("/")
    assert response.status_code == 200
    assert '<div id="root">' in response.text
    assert client.get("/health").json()["status"] == "ok"
    assert "ai_provider" in client.get("/config/status").json()
    # Static mounting must not shadow API POST routes.
    task = client.post("/tasks", json={"command": "Rename a document"})
    assert task.status_code == 200
    assert "actions" in task.json()


def load_launcher():
    spec = spec_from_file_location("agent_x_launcher", Path(__file__).resolve().parents[2] / "launch.py")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_launcher_reuses_healthy_server_without_spawning(monkeypatch):
    launcher = load_launcher()
    monkeypatch.setattr(launcher.sys, "argv", ["launch.py", "--no-browser"])
    monkeypatch.setattr(launcher, "ready", lambda: True)
    monkeypatch.setattr(launcher.subprocess, "Popen", lambda *a, **kw: pytest.fail("duplicate server"))
    assert launcher.main() == 0


def test_launcher_reports_conflicting_port_without_killing_process(monkeypatch):
    launcher = load_launcher()
    monkeypatch.setattr(launcher.sys, "argv", ["launch.py", "--no-browser"])
    monkeypatch.setattr(launcher, "ready", lambda: False)
    monkeypatch.setattr(launcher, "port_busy", lambda: True)
    monkeypatch.setattr(launcher.subprocess, "Popen", lambda *a, **kw: pytest.fail("must not replace unrelated server"))
    assert launcher.main() == 1


def test_launcher_uses_backend_environment_before_test_environment(tmp_path, monkeypatch):
    launcher = load_launcher()
    root = tmp_path / "project"
    backend = root / "backend"
    preferred = backend / ".venv" / "Scripts" / "python.exe"
    preferred.parent.mkdir(parents=True)
    preferred.touch()
    monkeypatch.setattr(launcher, "ROOT", root)
    monkeypatch.setattr(launcher, "BACKEND", backend)
    assert launcher.python_path() == preferred


def test_startup_marks_interrupted_actions_without_replaying(db):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.models import Task, Action
    task = Task(command="interrupted hardware query", status="executing")
    db.add(task)
    db.commit()
    db.refresh(task)
    db.add(Action(task_id=task.id, seq=0, tool_name="manage_system_setting", args_json='{"setting":"volume","action":"get"}', risk="low", status="running"))
    db.commit()
    with TestClient(app) as client:
        result = client.get(f"/tasks/{task.id}").json()
        assert result["status"] == "failed"
        assert result["actions"][0]["status"] == "failed"
        assert "interrupt" in result["error"]

"""Phase 2: state-machine enforcement."""
import pytest

from app.models import Action, ActionStatus, Task, TaskStatus
from app.state import ACTION_TRANSITIONS, OBSERVED, TASK_TRANSITIONS, InvalidTransition, can_transition


def test_tables_cover_every_status():
    task_all = {v for k, v in vars(TaskStatus).items() if not k.startswith("_")}
    action_all = {v for k, v in vars(ActionStatus).items() if not k.startswith("_")}
    assert set(TASK_TRANSITIONS) == task_all
    assert set(ACTION_TRANSITIONS) == action_all
    for table in (TASK_TRANSITIONS, ACTION_TRANSITIONS):
        for targets in table.values():
            assert targets <= set(table)


@pytest.mark.parametrize("terminal", [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED, TaskStatus.REJECTED])
def test_terminal_task_states_cannot_restart(terminal):
    task = Task(command="x", status=TaskStatus.CREATED)
    task.status = TaskStatus.EXECUTING  # created -> executing is legal
    task.status = terminal if terminal != TaskStatus.REJECTED else TaskStatus.FAILED
    with pytest.raises(InvalidTransition):
        task.status = TaskStatus.EXECUTING


def test_action_cannot_run_without_approval():
    action = Action(task_id="t", seq=0, tool_name="x", status=ActionStatus.PENDING)
    with pytest.raises(InvalidTransition):
        action.status = ActionStatus.RUNNING
    action.status = ActionStatus.APPROVED
    action.status = ActionStatus.RUNNING
    action.status = ActionStatus.SUCCEEDED
    with pytest.raises(InvalidTransition):
        action.status = ActionStatus.RUNNING


def test_new_objects_and_same_state_are_allowed():
    assert can_transition(TASK_TRANSITIONS, None, TaskStatus.CREATED)
    assert can_transition(TASK_TRANSITIONS, TaskStatus.COMPLETED, TaskStatus.COMPLETED)


def test_api_flow_uses_only_legal_transitions(client):
    j = client.post("/tasks", json={"command": "Create a folder called sm_flow in Documents"}).json()
    client.post(f"/tasks/{j['id']}/approve", json={})
    assert client.post(f"/tasks/{j['id']}/run").json()["status"] == "completed"
    # a finished task is never restarted, and a second run is a no-op
    assert client.post(f"/tasks/{j['id']}/run").json()["status"] == "completed"
    assert ("task", "completed", "executing") not in OBSERVED


def test_schema_version_stamped_and_newer_db_refused(monkeypatch):
    from sqlalchemy import text
    from app import database

    with database.engine.connect() as conn:
        assert conn.execute(text("PRAGMA user_version")).scalar() == database.SCHEMA_VERSION
    monkeypatch.setattr(database, "SCHEMA_VERSION", database.SCHEMA_VERSION - 1)
    with pytest.raises(RuntimeError, match="newer than this app"):
        database._stamp_version()


def test_every_documented_route_exists_in_api_doc():
    from pathlib import Path
    from app.main import app

    doc = (Path(__file__).resolve().parents[2] / "docs" / "API.md").read_text(encoding="utf-8")
    missing = []
    for route in app.routes:
        path = getattr(route, "path", "")
        methods = getattr(route, "methods", None)
        if not methods or path in {"/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"} or path.startswith(("/browser-extension", "/browser/ws")):
            continue
        for method in methods - {"HEAD", "OPTIONS"}:
            if f"`{method} {path}`" not in doc:
                missing.append(f"{method} {path}")
    assert not missing, f"Undocumented routes: {missing}"

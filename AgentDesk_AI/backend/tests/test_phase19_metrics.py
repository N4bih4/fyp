"""Pilot metrics: privacy-safe CSV, automatic append on finish, endpoint."""
from __future__ import annotations

import csv
import io

from app import metrics
from app.ai.base import Plan, PlanAction
from app.config import Settings, get_settings
from app.orchestration import executor
from app.tools.base import ToolContext
from app.tools.registry import ToolRegistry

SECRET_PATH_PART = "VerySecretFolderName"


def _run(db, tmp_path, command="create folder"):
    registry = ToolRegistry(ToolContext(allowed_directories=[tmp_path]))
    task = executor.create_task(db, command)
    plan = Plan(actions=[PlanAction(tool="create_folder", args={"path": str(tmp_path / SECRET_PATH_PART)})])
    task = executor.plan_task(db, task, registry, Settings(), preplanned=plan)
    task = executor.approve_task(db, task.id)
    return executor.run_task(db, task.id, registry, Settings())


def test_row_has_timings_and_no_private_text(db, tmp_path):
    task = _run(db, tmp_path, command="Ahmed ka folder banao, phone +923001234567")
    row = metrics.row_for(task)
    assert row["status"] == "completed" and row["tools"] == "create_folder" and row["verified_actions"] == 1
    assert row["approvals_required"] == 1 and row["approval_wait_s"] != "" and row["max_risk"] == "medium"
    assert row["language"] == "roman_ur" and row["command_chars"] > 10
    flat = ",".join(str(v) for v in row.values())
    for private in (SECRET_PATH_PART, "Ahmed", "+923001234567", str(tmp_path)):
        assert private not in flat


def test_endpoint_returns_csv_of_finished_tasks(client, db, tmp_path):
    _run(db, tmp_path)
    executor.create_task(db, "still pending")
    response = client.get("/metrics/tasks.csv")
    assert response.status_code == 200 and response.headers["content-type"].startswith("text/csv")
    rows = list(csv.DictReader(io.StringIO(response.text)))
    assert [r["status"] for r in rows] == ["completed"]
    assert list(rows[0]) == list(metrics.FIELDS)
    assert client.get("/metrics/tasks.csv?days=0").status_code == 422


def test_automatic_append_when_pilot_metrics_on(db, tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTDESK_PILOT_DIR", str(tmp_path / "pilot"))
    monkeypatch.setenv("PILOT_METRICS", "1")
    get_settings.cache_clear()
    try:
        task = _run(db, tmp_path)
        path = tmp_path / "pilot" / "task_metrics.csv"
        rows = list(csv.DictReader(path.open(encoding="utf-8")))
        assert [r["task_id"] for r in rows] == [task.id] and rows[0]["status"] == "completed"
        db.commit()  # later commits do not duplicate the row
        assert len(list(csv.DictReader(path.open(encoding="utf-8")))) == 1
    finally:
        monkeypatch.delenv("PILOT_METRICS")
        get_settings.cache_clear()


def test_no_file_when_pilot_metrics_off(db, tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTDESK_PILOT_DIR", str(tmp_path / "pilot"))
    _run(db, tmp_path)
    assert not (tmp_path / "pilot" / "task_metrics.csv").exists()


def test_error_categories():
    assert metrics.error_kind("Stopped after 30s: the tool process was killed") == "timeout"
    assert metrics.error_kind("Verification failed: folder exists: False") == "verification"
    assert metrics.error_kind("Path is outside the allowed folders") == "refused"
    assert metrics.error_kind(None) == ""


def test_not_understood_commands_are_counted(client, db):
    from app.config import Settings as S
    from app.tools.registry import ToolRegistry as R
    task = executor.start_task(db, "blorp the zibble quickly", None, R(), S(ai_provider="groq", groq_api_key=None))
    assert task.status == "awaiting_input"
    rows = list(csv.DictReader(io.StringIO(client.get("/metrics/tasks.csv").text)))
    assert rows and rows[-1]["status"] == "not_understood" and rows[-1]["actions"] == "0"
    assert metrics.error_kind("System brightness, volume, and Bluetooth controls are supported on Windows only.") == "unsupported_platform"


def test_write_and_overwrite_by_command_use_the_local_matcher(db, tmp_path):
    """FINDING-1 of the pilot: these needed cloud AI before."""
    from app.config import Settings as S
    note = tmp_path / "note.txt"
    registry = ToolRegistry(ToolContext(allowed_directories=[tmp_path]))
    settings = S(ai_provider="groq", groq_api_key=None)
    task = executor.start_task(db, f"write first version to {note}", None, registry, settings)
    assert task.status == "awaiting_approval" and task.actions[0].risk == "medium"
    task = executor.run_task(db, executor.approve_task(db, task.id).id, registry, settings)
    assert note.read_text() == "first version"
    task = executor.start_task(db, f"overwrite {note} with second version", None, registry, settings)
    assert task.actions[0].risk == "high"
    task = executor.approve_task(db, task.id, [task.actions[0].id])
    task = executor.run_task(db, task.id, registry, settings)
    assert task.status == "completed" and note.read_text() == "second version"
    task = executor.rollback_task(db, task.id, registry)
    assert note.read_text() == "first version" and task.actions[0].rollback_status == "done"

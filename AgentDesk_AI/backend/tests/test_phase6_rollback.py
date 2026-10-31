"""Phase 6: checkpoints, verified rollback, partial-completion reporting, pause/resume.

Only disposable pytest temp directories are touched.
"""
from __future__ import annotations

import os
import threading
import time
import zipfile
from pathlib import Path

import pytest

from app.ai.base import Plan, PlanAction
from app.config import get_settings
from app.models import ActionStatus, TaskStatus
from app.orchestration import executor, rollback
from app.tools.base import ToolContext
from app.tools.registry import ToolRegistry


def _registry(tmp_path):
    return ToolRegistry(ToolContext(allowed_directories=[tmp_path], test_dir=tmp_path))


def _run(db, tmp_path, *actions, approve=True):
    registry = _registry(tmp_path)
    plan = Plan(actions=[PlanAction(tool=t, args=a) for t, a in actions])
    task = executor.plan_task(db, executor.create_task(db, "phase6"), registry, get_settings(), preplanned=plan)
    if approve:
        task = executor.approve_task(db, task.id, [a.id for a in task.actions])
        task = executor.run_task(db, task.id, registry, get_settings())
    return task, registry


def _rollback(db, task, registry):
    return executor.rollback_task(db, task.id, registry)


def _only(task):
    return task.actions[0]


# ------------------------------------------------------------ per-tool rollback
def test_create_folder_rollback(db, tmp_path):
    target = tmp_path / "a" / "b"
    task, reg = _run(db, tmp_path, ("create_folder", {"path": str(target)}))
    assert task.status == TaskStatus.COMPLETED and target.is_dir()
    assert _only(task).rollback_status == "available"
    task = _rollback(db, task, reg)
    assert _only(task).rollback_status == "done"
    assert not (tmp_path / "a").exists()


def test_create_folder_rollback_refuses_non_empty(db, tmp_path):
    target = tmp_path / "keep"
    task, reg = _run(db, tmp_path, ("create_folder", {"path": str(target)}))
    (target / "user_file.txt").write_text("mine")
    task = _rollback(db, task, reg)
    assert _only(task).rollback_status == "failed" and "not empty" in _only(task).rollback_detail
    assert (target / "user_file.txt").exists()


def test_move_and_rename_rollback(db, tmp_path):
    src = tmp_path / "one.txt"
    src.write_text("data")
    task, reg = _run(db, tmp_path, ("move_file", {"source": str(src), "destination": str(tmp_path / "two.txt")}))
    assert not src.exists()
    task = _rollback(db, task, reg)
    assert _only(task).rollback_status == "done" and src.read_text() == "data"

    task, reg = _run(db, tmp_path, ("rename_file", {"path": str(src), "new_name": "renamed.txt"}))
    task = _rollback(db, task, reg)
    assert _only(task).rollback_status == "done" and src.exists() and not (tmp_path / "renamed.txt").exists()


def test_move_rollback_refuses_when_file_changed_afterwards(db, tmp_path):
    src = tmp_path / "doc.txt"
    src.write_text("v1")
    moved = tmp_path / "moved.txt"
    task, reg = _run(db, tmp_path, ("move_file", {"source": str(src), "destination": str(moved)}))
    moved.write_text("v2 edited by user")
    task = _rollback(db, task, reg)
    assert _only(task).rollback_status == "failed" and "changed" in _only(task).rollback_detail
    assert moved.read_text() == "v2 edited by user" and not src.exists()


def test_copy_rollback_removes_only_untouched_copy(db, tmp_path):
    src = tmp_path / "orig.txt"
    src.write_text("x")
    dst = tmp_path / "copy.txt"
    task, reg = _run(db, tmp_path, ("copy_file", {"source": str(src), "destination": str(dst)}))
    task = _rollback(db, task, reg)
    assert _only(task).rollback_status == "done" and not dst.exists() and src.exists()

    task, reg = _run(db, tmp_path, ("copy_file", {"source": str(src), "destination": str(dst)}))
    dst.write_text("edited")
    task = _rollback(db, task, reg)
    assert _only(task).rollback_status == "failed" and dst.read_text() == "edited"


def test_copy_folder_rollback(db, tmp_path):
    src = tmp_path / "dir"
    (src / "sub").mkdir(parents=True)
    (src / "sub" / "f.txt").write_text("1")
    task, reg = _run(db, tmp_path, ("copy_file", {"source": str(src), "destination": str(tmp_path / "dir2")}))
    task = _rollback(db, task, reg)
    assert _only(task).rollback_status == "done" and not (tmp_path / "dir2").exists() and src.exists()


def test_write_new_file_rollback_and_overwrite_restore(db, tmp_path):
    f = tmp_path / "note.txt"
    task, reg = _run(db, tmp_path, ("write_text_file", {"path": str(f), "content": "first"}))
    task = _rollback(db, task, reg)
    assert _only(task).rollback_status == "done" and not f.exists()

    f.write_text("ORIGINAL")
    task, reg = _run(db, tmp_path, ("write_text_file", {"path": str(f), "content": "replaced", "overwrite": True}))
    assert f.read_text() == "replaced"
    assert _only(task).rollback_status == "available"
    task = _rollback(db, task, reg)
    assert _only(task).rollback_status == "done" and f.read_text() == "ORIGINAL"


def test_overwrite_rollback_refuses_if_edited_after(db, tmp_path):
    f = tmp_path / "n.txt"
    f.write_text("ORIGINAL")
    task, reg = _run(db, tmp_path, ("write_text_file", {"path": str(f), "content": "new", "overwrite": True}))
    f.write_text("someone else edited")
    task = _rollback(db, task, reg)
    assert _only(task).rollback_status == "failed" and f.read_text() == "someone else edited"


def test_edit_text_file_rollback(db, tmp_path):
    f = tmp_path / "e.txt"
    f.write_text("hello world")
    task, reg = _run(db, tmp_path, ("edit_text_file", {"path": str(f), "old_text": "world", "new_text": "there"}))
    assert f.read_text() == "hello there"
    task = _rollback(db, task, reg)
    assert _only(task).rollback_status == "done" and f.read_text() == "hello world"


def test_overwrite_blocked_when_checkpoint_cannot_be_made(db, tmp_path, monkeypatch):
    f = tmp_path / "big.txt"
    f.write_text("ORIGINAL CONTENT")
    monkeypatch.setattr(rollback, "MAX_BACKUP_BYTES", 4)
    task, _ = _run(db, tmp_path, ("write_text_file", {"path": str(f), "content": "x", "overwrite": True}))
    assert task.status == TaskStatus.FAILED
    assert "checkpoint" in _only(task).error.lower()
    assert f.read_text() == "ORIGINAL CONTENT"  # never ran


def test_extract_rollback_keeps_preexisting_destination(db, tmp_path):
    archive = tmp_path / "a.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("x.txt", "X")
        z.writestr("sub/y.txt", "Y")
    dest = tmp_path / "out"
    dest.mkdir()
    task, reg = _run(db, tmp_path, ("extract_file", {"zip_path": str(archive), "destination": str(dest)}))
    assert (dest / "sub" / "y.txt").exists()
    task = _rollback(db, task, reg)
    assert _only(task).rollback_status == "done"
    assert dest.is_dir() and not (dest / "x.txt").exists() and not (dest / "sub").exists()


def test_extract_rollback_refuses_if_extracted_file_changed(db, tmp_path):
    archive = tmp_path / "b.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("x.txt", "X")
    dest = tmp_path / "out2"
    task, reg = _run(db, tmp_path, ("extract_file", {"zip_path": str(archive), "destination": str(dest)}))
    (dest / "x.txt").write_text("edited")
    task = _rollback(db, task, reg)
    assert _only(task).rollback_status == "failed" and (dest / "x.txt").read_text() == "edited"


def test_compress_rollback(db, tmp_path):
    folder = tmp_path / "pk"
    folder.mkdir()
    (folder / "f.txt").write_text("1")
    task, reg = _run(db, tmp_path, ("compress_folder", {"folder_path": str(folder)}))
    assert (tmp_path / "pk.zip").exists()
    task = _rollback(db, task, reg)
    assert _only(task).rollback_status == "done" and not (tmp_path / "pk.zip").exists() and folder.exists()


def test_delete_rollback_restores_from_trash(db, tmp_path):
    f = tmp_path / "gone.txt"
    f.write_text("important")
    task, reg = _run(db, tmp_path, ("delete_file", {"path": str(f)}))
    assert not f.exists()
    task = _rollback(db, task, reg)
    assert _only(task).rollback_status == "done" and f.read_text() == "important"


# ------------------------------------------------- honesty and partial results
def test_unsupported_action_is_marked_unsupported(db, tmp_path, monkeypatch):
    monkeypatch.setattr(rollback, "SUPPORTED_TOOLS", set())
    task, reg = _run(db, tmp_path, ("create_folder", {"path": str(tmp_path / "z")}))
    assert _only(task).rollback_status == "unsupported"
    with pytest.raises(ValueError, match="Nothing to roll back"):
        _rollback(db, task, reg)


def test_partial_failure_is_reported_and_rollbackable(db, tmp_path):
    target = tmp_path / "made"
    task, reg = _run(
        db, tmp_path,
        ("create_folder", {"path": str(target)}),
        ("move_file", {"source": str(tmp_path / "missing.txt"), "destination": str(tmp_path / "x.txt")}),
        ("create_folder", {"path": str(tmp_path / "never")}),
    )
    assert task.status == TaskStatus.PARTIALLY_COMPLETED  # step 1 verified, step 2 failed
    out = executor.task_out(task)
    assert out.partial["succeeded"] == 1 and out.partial["failed"] == 1 and out.partial["not_run"] == 1
    assert out.partial["changes_remain"] == ["create_folder"]
    assert len(out.partial["rollback_available"]) == 1
    assert not (tmp_path / "never").exists()
    task = _rollback(db, task, reg)
    assert not target.exists()
    assert executor.task_out(task).actions[0].rollback_status == "done"


def test_rollback_refused_while_not_finished(db, tmp_path):
    task, reg = _run(db, tmp_path, ("create_folder", {"path": str(tmp_path / "w")}), approve=False)
    with pytest.raises(ValueError, match="finish or cancel"):
        _rollback(db, task, reg)


def test_rollback_endpoint_end_to_end(client):
    home = Path(os.environ["AGENTDESK_MOCK_HOME"])
    task = client.post("/tasks", json={"command": "Create a folder called p6_api in Documents"}).json()
    client.post(f"/tasks/{task['id']}/approve", json={})
    done = client.post(f"/tasks/{task['id']}/run").json()
    assert done["status"] == "completed" and (home / "Documents" / "p6_api").is_dir()
    assert done["actions"][0]["rollback_status"] == "available"
    rolled = client.post(f"/tasks/{task['id']}/rollback").json()
    assert rolled["actions"][0]["rollback_status"] == "done"
    assert not (home / "Documents" / "p6_api").exists()
    assert client.post(f"/tasks/{task['id']}/rollback").status_code == 409  # nothing left to undo


# ----------------------------------------------------------------- pause/resume
def test_pause_takes_effect_before_next_action_and_resume_finishes(client, db, monkeypatch):
    from app.tools.filesystem import CreateFolderTool

    home = Path(os.environ["AGENTDESK_MOCK_HOME"]) / "p6_pause"
    home.mkdir(exist_ok=True)
    registry = ToolRegistry(ToolContext.from_settings())
    plan = Plan(actions=[PlanAction(tool="create_folder", args={"path": str(home / n)}) for n in ("one", "two", "three")])
    task = executor.plan_task(db, executor.create_task(db, "three folders"), registry, get_settings(), preplanned=plan)
    executor.approve_task(db, task.id, [a.id for a in task.actions])

    real = CreateFolderTool.execute

    def slow(self, args):
        time.sleep(0.6)
        return real(self, args)

    monkeypatch.setattr(CreateFolderTool, "execute", slow)
    result = {}
    runner = threading.Thread(target=lambda: result.update(client.post(f"/tasks/{task.id}/run").json()))
    runner.start()
    time.sleep(0.25)
    paused_req = client.post(f"/tasks/{task.id}/pause")
    assert paused_req.status_code == 200
    runner.join(timeout=20)
    assert result["status"] == "paused"
    assert (home / "one").is_dir() and not (home / "two").exists()
    assert result["partial"]["succeeded"] == 1 and result["partial"]["not_run"] == 2

    monkeypatch.setattr(CreateFolderTool, "execute", real)
    resumed = client.post(f"/tasks/{task.id}/run").json()
    assert resumed["status"] == "completed"
    assert all((home / n).is_dir() for n in ("one", "two", "three"))


def test_pause_rejected_when_not_running(client):
    task = client.post("/tasks", json={"command": "Create a folder called p6_nopause in Documents"}).json()
    assert client.post(f"/tasks/{task['id']}/pause").status_code == 409

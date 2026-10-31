"""Phase 16: no tool reports success without evidence from the real system.

Uses ScriptedProbe (strict): the verifier sees exactly the desktop/settings state the test sets.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import BaseModel

from app.ai.base import Plan, PlanAction
from app.config import Settings
from app.models import ActionStatus, TaskStatus
from app.orchestration import executor
from app.tools.base import BaseTool, ToolContext, ToolResult, Verification
from app.tools.desktop import DesktopControlArgs, DesktopControlTool
from app.tools.registry import ToolRegistry
from app.verification import WindowInfo, use_probe
from tests.helpers.fake_probe import ScriptedProbe


@pytest.fixture
def registry(tmp_path):
    return ToolRegistry(ToolContext(allowed_directories=[tmp_path], discovery_directories=[tmp_path]))


def win(hwnd=7, title="Untitled - Notepad", process="notepad.exe", **state):
    return WindowInfo(hwnd, title, 100, process, state.get("minimized", False), state.get("maximized", False),
                      state.get("foreground", False))


def test_every_registered_tool_has_its_own_verifier(registry):
    assert [n for n in registry.names() if type(registry.get(n)).verify is BaseTool.verify] == []


def test_default_verifier_never_passes():
    class Bare(BaseTool):
        name = "bare"

        def execute(self, args):
            return ToolResult(success=True)
    assert Bare(ToolContext()).verify(None, ToolResult(success=True)).passed is False


def test_executor_rejects_a_pass_without_evidence(db, registry, tmp_path, monkeypatch):
    tool = registry.get("create_folder")
    monkeypatch.setattr(tool, "verify", lambda args, result: Verification(passed=True, checks=["trust me"]))
    task = executor.create_task(db, "x")
    plan = Plan(actions=[PlanAction(tool="create_folder", args={"path": str(tmp_path / "new")})])
    task = executor.plan_task(db, task, registry, Settings(), preplanned=plan)
    task = executor.approve_task(db, task.id)
    task = executor.run_task(db, task.id, registry, Settings())
    assert task.status == TaskStatus.FAILED
    assert "no evidence" in task.actions[0].verification_json


@pytest.mark.parametrize("windows,passed", [([], False), ([win(process="calc.exe", title="Calculator")], False),
                                            ([win()], True)])
def test_open_application_needs_the_real_window(registry, windows, passed):
    tool = registry.get("open_application")
    args = tool.validate_args({"app_name": "notepad"})
    with use_probe(ScriptedProbe(windows=windows)):
        v = tool.verify(args, ToolResult(success=True, output={"app": "notepad", "pid": 100, "launched": True}))
    assert v.passed is passed and v.evidence


def test_open_folder_needs_an_explorer_window_showing_it(registry, tmp_path):
    folder = tmp_path / "Lab"
    folder.mkdir()
    tool = registry.get("open_folder")
    result = ToolResult(success=True, output={"path": str(folder), "launched": True})
    args = tool.validate_args({"path": str(folder)})
    with use_probe(ScriptedProbe(windows=[win(title="Lab", process="notepad.exe")])):
        assert not tool.verify(args, result).passed
    with use_probe(ScriptedProbe(windows=[win(title="Lab", process="explorer.exe")])):
        assert tool.verify(args, result).passed


@pytest.mark.parametrize("args,reported,observed,passed", [
    ({"setting": "volume", "action": "set", "value": 40}, {"value": 40}, {"value": 40, "muted": False}, True),
    ({"setting": "volume", "action": "set", "value": 40}, {"value": 40}, {"value": 35, "muted": False}, False),
    ({"setting": "volume", "action": "mute"}, {"muted": True}, {"value": 30, "muted": False}, False),
    ({"setting": "volume", "action": "mute"}, {"muted": True}, {"value": 30, "muted": True}, True),
    ({"setting": "brightness", "action": "increase"}, {"value": 60}, {"value": 61}, True),
    ({"setting": "bluetooth", "action": "off"}, {"enabled": False}, {"enabled": True}, False),
    ({"setting": "theme", "action": "dark"}, {"apps": "dark", "system": "dark"}, {"apps": "light", "system": "dark"}, False),
])
def test_system_settings_are_read_back_independently(registry, args, reported, observed, passed):
    tool = registry.get("manage_system_setting")
    parsed = tool.validate_args(args)
    with use_probe(ScriptedProbe(settings={args["setting"]: observed})):
        v = tool.verify(parsed, ToolResult(success=True, output={"setting": args["setting"], **reported}))
    assert v.passed is passed
    assert v.evidence["observed"] == observed


def test_read_back_failure_is_not_a_pass(registry):
    tool = registry.get("manage_system_setting")
    with use_probe(ScriptedProbe(settings={})):
        v = tool.verify(tool.validate_args({"setting": "volume", "action": "get"}),
                        ToolResult(success=True, output={"setting": "volume", "value": 3}))
    assert not v.passed


@pytest.mark.parametrize("action,state,passed", [
    ("minimize_window", {"minimized": False}, False), ("minimize_window", {"minimized": True}, True),
    ("maximize_window", {"maximized": True}, True), ("restore_window", {"minimized": True}, False),
    ("focus_window", {"foreground": True}, True), ("focus_window", {"foreground": False}, False),
])
def test_window_state_is_re_read(action, state, passed):
    tool = DesktopControlTool(ToolContext())
    args = DesktopControlArgs.model_validate({"target_window": "Notepad", "steps": [{"action": action}]})
    result = ToolResult(success=True, output={"completed_steps": [{"action": action, "window": "Untitled - Notepad", "hwnd": 7}]})
    with use_probe(ScriptedProbe(windows=[win(**state)])):
        assert tool.verify(args, result).passed is passed


def test_closed_window_must_be_gone(registry):
    tool = DesktopControlTool(ToolContext())
    args = DesktopControlArgs.model_validate({"target_window": "Notepad", "steps": [{"action": "close_window"}]})
    result = ToolResult(success=True, output={"completed_steps": [{"action": "close_window", "window": "Untitled - Notepad", "hwnd": 7}]})
    with use_probe(ScriptedProbe(windows=[win()])):
        assert not tool.verify(args, result).passed
    with use_probe(ScriptedProbe(windows=[])):
        assert tool.verify(args, result).passed


def test_unsaved_changes_prompt_is_detected_not_answered():
    with use_probe(ScriptedProbe(dialogs={100: ["Do you want to save changes to Untitled?", "Save", "Don't Save"]})):
        assert "save changes" in DesktopControlTool._save_prompt(100)
    with use_probe(ScriptedProbe(dialogs={100: ["Find", "Replace"]})):
        assert DesktopControlTool._save_prompt(100) is None


def test_list_and_read_detect_a_changed_disk(registry, tmp_path):
    (tmp_path / "a.txt").write_text("one")
    lister = registry.get("list_folder")
    args = lister.validate_args({"path": str(tmp_path)})
    result = lister.execute(args)
    assert lister.verify(args, result).passed
    (tmp_path / "b.txt").write_text("late")
    assert not lister.verify(args, result).passed
    reader = registry.get("read_text_file")
    rargs = reader.validate_args({"path": str(tmp_path / "a.txt")})
    rresult = reader.execute(rargs)
    assert reader.verify(rargs, rresult).evidence["sha256"]
    (tmp_path / "a.txt").write_text("changed")
    assert not reader.verify(rargs, rresult).passed


def test_resume_is_refused_when_the_verified_step_no_longer_holds(db, registry, tmp_path):
    folder = tmp_path / "Lab"
    plan = Plan(actions=[PlanAction(tool="create_folder", args={"path": str(folder)}),
                         PlanAction(tool="create_folder", args={"path": str(tmp_path / "Lab2")})])
    task = executor.create_task(db, "two folders")
    task = executor.plan_task(db, task, registry, Settings(), preplanned=plan)
    task = executor.approve_task(db, task.id)
    # Pause after the first verified step.
    original = executor._save_checkpoint

    def pause_after(db_, task_, action_):
        original(db_, task_, action_)
        state = json.loads(task_.agent_state_json)
        state["pause_requested"] = True
        task_.agent_state_json = json.dumps(state)
        db_.commit()
    executor._save_checkpoint = pause_after
    try:
        task = executor.run_task(db, task.id, registry, Settings())
    finally:
        executor._save_checkpoint = original
    assert task.status == TaskStatus.PAUSED and folder.is_dir()
    folder.rmdir()  # someone changed the PC while paused
    task = executor.run_task(db, task.id, registry, Settings())
    assert task.status == TaskStatus.FAILED and "Resume refused" in task.error
    assert not (tmp_path / "Lab2").exists()
    assert task.actions[1].status == ActionStatus.SKIPPED


def test_resume_continues_when_the_checkpoint_still_holds(db, registry, tmp_path):
    plan = Plan(actions=[PlanAction(tool="create_folder", args={"path": str(tmp_path / "A")}),
                         PlanAction(tool="create_folder", args={"path": str(tmp_path / "B")})])
    task = executor.create_task(db, "two folders")
    task = executor.plan_task(db, task, registry, Settings(), preplanned=plan)
    task = executor.approve_task(db, task.id)
    original = executor._save_checkpoint

    def pause_after(db_, task_, action_):
        original(db_, task_, action_)
        state = json.loads(task_.agent_state_json)
        state["pause_requested"] = True
        task_.agent_state_json = json.dumps(state)
        db_.commit()
    executor._save_checkpoint = pause_after
    try:
        task = executor.run_task(db, task.id, registry, Settings())
    finally:
        executor._save_checkpoint = original
    assert task.status == TaskStatus.PAUSED
    task = executor.run_task(db, task.id, registry, Settings())
    assert task.status == TaskStatus.COMPLETED and (tmp_path / "B").is_dir()

"""Agentic-loop tests: model proposes -> validate -> permission check ->
approval pause -> execute -> feed result back. Scripted fake Groq client,
real tools, real database. No network.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.ai.groq_provider import GroqProvider
from app.config import Settings
from app.models import ActionStatus, TaskStatus
from app.orchestration import executor
from app.tools.base import ToolContext
from app.tools.registry import ToolRegistry


# ------------------------------------------------------------------ fakes
class _FakeFunction:
    def __init__(self, name, arguments):
        self.name = name
        self.arguments = arguments


class _FakeToolCall:
    def __init__(self, call_id, name, arguments):
        self.id = call_id
        self.type = "function"
        self.function = _FakeFunction(name, arguments)


class _FakeMessage:
    def __init__(self, content=None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls or []


class _FakeResponse:
    def __init__(self, message):
        self.choices = [type("Choice", (), {"message": message})()]


class _FakeCompletions:
    def __init__(self, script):
        self.script = list(script)

    def create(self, **kwargs):
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class _FakeClient:
    def __init__(self, script):
        self.chat = type("Chat", (), {"completions": _FakeCompletions(script)})()


def _tc(call_id, name, args):
    return _FakeToolCall(call_id, name, json.dumps(args))


def _turn(*tool_calls, content=None):
    return _FakeResponse(_FakeMessage(content=content, tool_calls=list(tool_calls)))


def _loop_harness(db, tmp_path: Path, script, **settings_kw):
    ctx = ToolContext(
        allowed_directories=[tmp_path], approved_applications=["notepad"], test_dir=tmp_path
    )
    registry = ToolRegistry(ctx)
    settings = Settings(
        ai_provider="groq",
        groq_api_key="test-key",
        agent_max_steps=settings_kw.pop("agent_max_steps", 6),
        tool_timeout_seconds=10,
        **settings_kw,
    )
    provider = GroqProvider(
        api_key="test-key", model="test-model", client=_FakeClient(script), max_retries=0
    )
    return registry, settings, provider


# ------------------------------------------------------------------ tests
def test_low_risk_tool_auto_executes_then_model_finishes(db, tmp_path: Path):
    target = tmp_path / "docs"
    target.mkdir()
    (target / "a.txt").write_text("x")
    script = [
        _turn(_tc("c1", "list_folder", {"path": str(target)})),
        _turn(content="Found 1 file: a.txt."),
    ]
    registry, settings, provider = _loop_harness(db, tmp_path, script)
    task = executor.create_task(db, "List the files in docs")
    task = executor.start_agent_task(db, task, registry, provider, settings)

    assert task.status == TaskStatus.COMPLETED
    assert task.plan_note == "Found 1 file: a.txt."
    assert len(task.actions) == 1
    assert task.actions[0].status == ActionStatus.SUCCEEDED
    assert task.actions[0].risk == "low"
    # loop state persisted for audit
    state = json.loads(task.agent_state_json)
    assert state["provider"] == "groq" and state["steps"] == 2


def test_medium_risk_pauses_for_approval_then_resumes(db, tmp_path: Path):
    script = [
        _turn(_tc("c1", "create_folder", {"path": str(tmp_path / "FYP")})),
        _turn(content="Folder created."),
    ]
    registry, settings, provider = _loop_harness(db, tmp_path, script)
    task = executor.create_task(db, "Create a folder called FYP")
    task = executor.start_agent_task(db, task, registry, provider, settings)

    assert task.status == TaskStatus.AWAITING_APPROVAL
    assert task.actions[0].status == ActionStatus.PENDING
    assert task.actions[0].risk == "medium"

    executor.approve_task(db, task.id, None)
    task = executor.continue_agent_task(db, task.id, registry, provider, settings)
    assert task.status == TaskStatus.COMPLETED
    assert (tmp_path / "FYP").is_dir()
    assert task.actions[0].status == ActionStatus.SUCCEEDED


def test_unknown_tool_is_rejected_and_model_recovers(db, tmp_path: Path):
    script = [
        _turn(_tc("c1", "format_drive", {})),
        _turn(_tc("c2", "list_folder", {"path": str(tmp_path)})),
        _turn(content="Recovered."),
    ]
    registry, settings, provider = _loop_harness(db, tmp_path, script)
    task = executor.create_task(db, "Do something odd")
    task = executor.start_agent_task(db, task, registry, provider, settings)

    assert task.status == TaskStatus.COMPLETED
    # the unknown tool never became an action; the valid one did
    assert [a.tool_name for a in task.actions] == ["list_folder"]
    state = json.loads(task.agent_state_json)
    tool_msgs = [m for m in state["messages"] if m.get("role") == "tool"]
    assert any("Unknown tool" in m["content"] for m in tool_msgs)


def test_duplicate_tool_call_is_not_re_executed(db, tmp_path: Path):
    script = [
        _turn(_tc("c1", "create_folder", {"path": str(tmp_path / "Once")})),
        _turn(_tc("c2", "create_folder", {"path": str(tmp_path / "Once")})),
        _turn(content="Done."),
    ]
    registry, settings, provider = _loop_harness(db, tmp_path, script)
    task = executor.create_task(db, "Create it twice")
    task = executor.start_agent_task(db, task, registry, provider, settings)
    assert task.status == TaskStatus.AWAITING_APPROVAL
    executor.approve_task(db, task.id, None)
    task = executor.continue_agent_task(db, task.id, registry, provider, settings)

    assert task.status == TaskStatus.COMPLETED
    assert (tmp_path / "Once").is_dir()
    # only one real execution; the repeat was answered from the fingerprint log
    assert sum(1 for a in task.actions if a.status == ActionStatus.SUCCEEDED) == 1
    state = json.loads(task.agent_state_json)
    tool_msgs = [m for m in state["messages"] if m.get("role") == "tool"]
    assert any("Already executed" in m["content"] for m in tool_msgs)


def test_rejection_is_reported_back_to_model(db, tmp_path: Path):
    victim = tmp_path / "keep.txt"
    victim.write_text("important")
    script = [
        _turn(_tc("c1", "delete_file", {"path": str(victim)})),
        _turn(content="Understood, I will not delete it."),
    ]
    registry, settings, provider = _loop_harness(db, tmp_path, script)
    task = executor.create_task(db, "Delete keep.txt")
    task = executor.start_agent_task(db, task, registry, provider, settings)
    assert task.actions[0].risk == "high"

    executor.reject_task(db, task.id, None)
    # rejected tasks are terminal: nothing runs, file survives
    task = executor.continue_agent_task(db, task.id, registry, provider, settings)
    assert task.status == TaskStatus.REJECTED
    assert victim.exists()


def test_close_notepad_runs_named_close_without_approval(db, tmp_path: Path, monkeypatch):
    windows = []
    calls = []

    class FakeWindow:
        title = "Untitled - Notepad"

        def activate(self):
            calls.append(("activate", self.title))

    window = FakeWindow()
    windows.append(window)
    fake_pyautogui = SimpleNamespace(
        FAILSAFE=False,
        getActiveWindow=lambda: windows[0] if windows else None,
        getAllWindows=lambda: list(windows),
        size=lambda: (800, 600),
        hotkey=lambda *keys: (calls.append(("hotkey", *keys)), windows.clear()),
    )
    monkeypatch.setitem(sys.modules, "pyautogui", fake_pyautogui)
    monkeypatch.setattr("app.tools.desktop.time.sleep", lambda _seconds: None)

    script = [
        _turn(_tc("inspect", "control_desktop", {"steps": [{"action": "inspect"}]})),
        _turn(
            _tc(
                "close",
                "control_desktop",
                {"target_window": "Untitled - Notepad", "steps": [{"type": "key", "keys": "alt+f4"}]},
            )
        ),
        _turn(content="Notepad was closed."),
    ]
    registry, settings, provider = _loop_harness(db, tmp_path, script)
    task = executor.create_task(db, "Close Notepad")
    task = executor.start_agent_task(db, task, registry, provider, settings)

    assert task.status == TaskStatus.COMPLETED
    assert task.actions[0].tool_name == "control_desktop"
    assert task.actions[0].risk == "low"
    assert task.actions[0].status == ActionStatus.SUCCEEDED
    assert task.actions[1].risk == "low"
    assert task.actions[1].status == ActionStatus.SUCCEEDED
    assert json.loads(task.actions[1].verification_json)["passed"] is True
    assert not windows
    assert calls == [("activate", "Untitled - Notepad"), ("hotkey", "alt", "f4")]


def test_parallel_close_keeps_every_tool_call_answered(db, tmp_path: Path, monkeypatch):
    windows = []

    class FakeWindow:
        title = "Untitled - Notepad"

        def activate(self):
            return None

    windows.append(FakeWindow())
    fake_pyautogui = SimpleNamespace(
        FAILSAFE=False,
        getActiveWindow=lambda: windows[0] if windows else None,
        getAllWindows=lambda: list(windows),
        size=lambda: (800, 600),
        hotkey=lambda *keys: windows.clear(),
    )
    monkeypatch.setitem(sys.modules, "pyautogui", fake_pyautogui)
    monkeypatch.setattr("app.tools.desktop.time.sleep", lambda _seconds: None)

    script = [
        _turn(
            _tc("inspect", "control_desktop", {"steps": [{"action": "inspect"}]}),
            _tc(
                "close",
                "control_desktop",
                {"target_window": "Untitled - Notepad", "steps": [{"action": "close_window"}]},
            ),
            _tc("list", "list_folder", {"path": str(tmp_path)}),
        ),
        _turn(content="Notepad was closed."),
    ]
    registry, settings, provider = _loop_harness(db, tmp_path, script)
    task = executor.create_task(db, "Close Notepad")
    task = executor.start_agent_task(db, task, registry, provider, settings)
    assert task.status == TaskStatus.COMPLETED
    state = json.loads(task.agent_state_json)
    assistant = next(m for m in state["messages"] if m.get("tool_calls"))
    state = json.loads(task.agent_state_json)
    answered = {m.get("tool_call_id") for m in state["messages"] if m.get("role") == "tool"}
    for call in assistant["tool_calls"]:
        assert call["id"] in answered


def test_follow_up_command_includes_recent_conversation(db, tmp_path: Path):
    first = executor.create_task(db, "Open Microsft Edge")
    first.status = TaskStatus.COMPLETED
    first.plan_note = "Did you mean Microsoft Edge?"
    db.commit()
    script = [_turn(content="Opening Microsoft Edge now.")]
    registry, settings, provider = _loop_harness(db, tmp_path, script)
    task = executor.create_task(db, "Haan, woh wala")
    task = executor.start_agent_task(db, task, registry, provider, settings)
    state = json.loads(task.agent_state_json)
    user_text = state["messages"][1]["content"]
    assert "Open Microsft Edge" in user_text
    assert "Haan, woh wala" in user_text
    assert "Did you mean Microsoft Edge?" in user_text


def test_max_steps_bound_is_enforced(db, tmp_path: Path):
    script = [_turn(_tc(f"c{i}", "list_folder", {"path": str(tmp_path)})) for i in range(10)]
    registry, settings, provider = _loop_harness(db, tmp_path, script, agent_max_steps=2)
    task = executor.create_task(db, "Loop forever")
    task = executor.start_agent_task(db, task, registry, provider, settings)
    assert task.status == TaskStatus.FAILED
    assert "maximum" in task.error


def test_groq_failure_fails_loudly_without_mock_fallback(db, tmp_path: Path):
    from app.ai.base import AIError

    script = [AIError("Groq is down")]
    registry, settings, provider = _loop_harness(db, tmp_path, script)
    task = executor.create_task(db, "Anything")
    task = executor.start_agent_task(db, task, registry, provider, settings)
    assert task.status == TaskStatus.FAILED
    assert "Groq is down" in task.error
    assert task.plan_note != "[mock AI]"

import json
from types import SimpleNamespace

import pytest

from app.ai.base import AIConfigError, AIRateLimitError
from app.ai.local_commands import local_plan
from app.ai.tool_selection import tool_metadata
from app.ai.resilient_provider import CompatibleAgentProvider, ResilientProvider, _COOLDOWNS
from app.config import Settings
from app.models import TaskStatus
from app.orchestration import executor
from app.tools.base import ToolContext
from app.tools.registry import ToolRegistry
from tests.test_agent_loop import _loop_harness, _tc, _turn


@pytest.mark.parametrize("text,setting,action", [
    ("volume kam karo", "volume", "decrease"),
    ("मेरी ब्राइटनेस कम कर दो", "brightness", "decrease"),
    ("آواز کم کر دو", "volume", "decrease"),
    ("increase brightness", "brightness", "increase"),
    ("set volume to 35%", "volume", "set"),
])
def test_local_settings(text, setting, action):
    plan = local_plan(text)
    assert plan.actions[0].args["setting"] == setting
    assert plan.actions[0].args["action"] == action


@pytest.mark.parametrize("text", ["volume down then delete files", "set volume to 999", "open Chrome and send email", "delete lecture", "no, not that"])
def test_local_parser_does_not_guess_multistep_or_destructive_commands(text):
    assert local_plan(text) is None


def test_local_app_executes_without_configuring_ai(db, tmp_path, monkeypatch):
    monkeypatch.setattr(executor, "get_provider", lambda *_: pytest.fail("API provider constructed"))
    monkeypatch.setattr("app.tools.apps.OpenApplicationTool.execute", lambda *_: __import__("app.tools.base", fromlist=["ToolResult"]).ToolResult(success=True, output={"launched": True}))
    registry = ToolRegistry(ToolContext(allowed_directories=[tmp_path], approved_applications=["notepad"]))
    task = executor.start_task(db, "open notepad", None, registry, Settings(ai_provider="groq", groq_api_key=None))
    assert task.status == TaskStatus.COMPLETED
    assert task.actions[0].status == "succeeded"


class ScriptedProvider:
    name = "groq"
    _model = "test"
    _api_key = "unique-resilience-test-key"
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = 0
    def complete(self, messages, tools=None):
        self.calls += 1
        result = self.replies.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def test_backup_receives_same_tool_history_and_primary_cooldown_is_shared():
    _COOLDOWNS.clear()
    primary = ScriptedProvider([AIRateLimitError("limited", 60)])
    backup = ScriptedProvider([{"content": "ok", "tool_calls": []}] * 2)
    backup.name = "gemini"
    messages = [{"role": "tool", "tool_call_id": "done", "content": "already executed"}]
    router = ResilientProvider(primary, backup)
    assert router.complete(messages)["content"] == "ok"
    assert router.notice and "gemini" in router.notice
    assert ResilientProvider(primary, backup).complete(messages)["content"] == "ok"
    assert primary.calls == 1
    assert backup.calls == 2
    _COOLDOWNS.clear()


def test_authentication_error_does_not_silently_switch_provider():
    _COOLDOWNS.clear()
    primary = ScriptedProvider([AIConfigError("bad key")])
    backup = ScriptedProvider([])
    with pytest.raises(AIConfigError):
        ResilientProvider(primary, backup).complete([])
    assert backup.calls == 0


def test_rate_limited_task_resumes_without_repeating_completed_action(db, tmp_path, monkeypatch):
    target = tmp_path / "notes"
    registry, settings, provider = _loop_harness(db, tmp_path, [
        _turn(_tc("c1", "create_folder", {"path": str(target)})),
        AIRateLimitError("limited", 60),
        _turn(content="Folder created."),
    ])
    task = executor.create_task(db, "Create the notes folder")
    task = executor.start_agent_task(db, task, registry, provider, settings)
    executor.approve_task(db, task.id)
    task = executor.continue_agent_task(db, task.id, registry, provider, settings)
    assert task.status == TaskStatus.WAITING_RETRY
    assert target.is_dir()
    action_id = task.actions[0].id
    # Early resume cannot issue another model call or execute a desktop action.
    task = executor.continue_agent_task(db, task.id, registry, provider, settings)
    assert task.status == TaskStatus.WAITING_RETRY
    state = json.loads(task.agent_state_json)
    state["retry_at"] = 0
    task.agent_state_json = json.dumps(state)
    db.commit()
    monkeypatch.setattr(registry.get("create_folder"), "execute", lambda *_: pytest.fail("action replayed"))
    task = executor.continue_agent_task(db, task.id, registry, provider, settings)
    assert task.status == TaskStatus.COMPLETED
    assert len(task.actions) == 1 and task.actions[0].id == action_id


def test_compatible_backup_preserves_gemini_metadata():
    call = SimpleNamespace(id="one", function=SimpleNamespace(name="list_folder", arguments='{"path":"~/Documents"}'), extra_content={"google": {"thought_signature": "signature"}})
    response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="", tool_calls=[call]), finish_reason="tool_calls")])
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **_: response)))
    provider = CompatibleAgentProvider("test", "gemini-3.8-flash", "gemini", client=client)
    assert provider.complete([])["tool_calls"][0]["extra_content"] == call.extra_content


def test_tool_selection_keeps_discovery_and_destructive_approval_tools(tmp_path):
    registry = ToolRegistry(ToolContext(allowed_directories=[tmp_path]))
    selected = tool_metadata(registry, "Delete the lecture folder")
    names = {tool["name"] for tool in selected}
    assert {"find_paths", "open_folder", "delete_file", "list_trash"} <= names
    assert len(selected) < len(registry.metadata())
    assert tool_metadata(registry, "haan woh wala") == registry.metadata()

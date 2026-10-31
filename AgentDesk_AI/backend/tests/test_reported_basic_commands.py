import json
import pytest
from app.ai.local_commands import local_plan
from app.ai.browser_commands import browser_plan
from app.ai.window_commands import close_request, window_plan
from app.tools.base import ToolResult
from app.tools.registry import ToolRegistry
from app.orchestration import executor


@pytest.mark.parametrize("text,setting,action", [
    ("ٹرن ان بلو ت", "bluetooth", "on"),
    ("ٹرن آف بلو ت", "bluetooth", "off"),
    ("میوٹ پی سی", "volume", "mute"),
])
def test_actual_basic_transcripts(text, setting, action):
    assert local_plan(text).actions[0].args == {"setting": setting, "action": action}


@pytest.mark.parametrize("text", ["یوٹیوب کلوز", "YouTube tab off kar do", "یوٹیوب کا ٹیب اف کر دو"])
def test_close_youtube_goes_to_exact_tab_bridge(text):
    action = browser_plan(text).actions[0]
    assert action.tool == "control_browser"
    assert action.args["action"] == "close"
    assert action.args["target"].casefold() == "youtube"


@pytest.mark.parametrize("text,target", [
    ("ٹرن اف سیٹنگ", "settings"), ("اف سیٹنگ ونڈو", "settings"),
    ("settings off kar do", "settings"),
    ("کلوز لیب فولڈر", "لیب"), ("اف لیب فولڈر", "لیب"),
    ("chrome off kar do", "chrome"),
])
def test_window_close_language(text, target):
    assert close_request(text) == target


def test_window_plan_resolves_actual_title(db, ctx, monkeypatch):
    registry = ToolRegistry(ctx)
    tool = registry.get("control_desktop")
    monkeypatch.setattr(tool, "execute", lambda _: ToolResult(success=True, output={"completed_steps": [{"open_windows": ["Settings", "lab", "Chrome"]}]}))
    task = executor.create_task(db, "اف لیب فولڈر")
    plan = window_plan(task, registry)
    assert plan.actions[0].args == {"target_window": "lab", "steps": [{"action": "close_window"}]}


def test_duplicate_windows_need_choice(db, ctx, monkeypatch):
    registry = ToolRegistry(ctx)
    tool = registry.get("control_desktop")
    monkeypatch.setattr(tool, "execute", lambda _: ToolResult(success=True, output={"completed_steps": [{"open_windows": ["lab - One", "lab - Two"]}]}))
    task = executor.create_task(db, "close lab folder")
    plan = window_plan(task, registry)
    assert not plan.actions
    assert json.loads(task.agent_state_json)["window_choices"] == ["lab - One", "lab - Two"]


def test_clear_mute_command_supersedes_folder_clarification(client, db, tmp_path, monkeypatch):
    import app.main as main
    from app.config import Settings
    from app.tools.base import ToolContext
    registry = ToolRegistry(ToolContext(allowed_directories=[tmp_path]))
    monkeypatch.setattr(main, "_registry", lambda: registry)
    monkeypatch.setattr(main, "get_settings", lambda: Settings(ai_provider="groq", groq_api_key=None))
    muted = []
    tool = registry.get("manage_system_setting")
    monkeypatch.setattr(tool, "_require_windows", lambda: None)
    monkeypatch.setattr(tool, "_set_mute", muted.append)
    old = executor.start_task(db, "open folder missing_lab", None, registry, Settings(ai_provider="groq", groq_api_key=None))
    assert old.status == "awaiting_input"
    from app.verification import use_probe
    from tests.helpers.fake_probe import ScriptedProbe
    with use_probe(ScriptedProbe(settings={"volume": {"value": 30, "muted": True}})):
        response = client.post(f"/tasks/{old.id}/reply", json={"message": "میوٹ پی سی"})
    assert response.json()["status"] == "completed"
    assert response.json()["actions"][0]["tool_name"] == "manage_system_setting"
    assert muted == [True]

import pytest
from app.ai.command_intents import canonical_command
from app.ai.window_commands import all_powershell_request, window_plan
from app.ai.browser_commands import browser_plan
from app.orchestration import executor
from app.tools.registry import ToolRegistry
from app.tools.base import ToolResult


@pytest.mark.parametrize("name,opened,closed", [
    ("powershell", "open app powershell", "close powershell"),
    ("پاور شیل", "open app powershell", "close powershell"),
    ("power shell", "open app powershell", "close powershell"),
    ("chrome", "open app chrome", "close chrome"),
    ("settings", "open settings", "close settings"),
    ("سیٹنگ", "open settings", "close settings"),
    ("youtube", "open youtube", "close youtube"),
    ("یوٹیوب", "open youtube", "close youtube"),
    ("WhatsApp", "open whatsapp", "close whatsapp"),
])
def test_both_directions_for_every_target_type(name, opened, closed):
    assert canonical_command(f"{name} on kar do") == opened
    assert canonical_command(f"{name} off kar do") == closed
    assert canonical_command(f"آن {name}") == opened
    assert canonical_command(f"اف {name}") == closed


@pytest.mark.parametrize("name", ["یوٹیوب", "youtube"])
def test_site_browser_and_both_directions(name):
    opened = browser_plan(canonical_command(f"{name} کروم میں آن کرو"))
    closed = browser_plan(canonical_command(f"{name} کروم میں اف کرو"))
    assert opened.actions[0].args == {"url": "https://www.youtube.com", "browser": "chrome"}
    assert closed.actions[0].args == {"action": "close", "target": "youtube"}


@pytest.mark.parametrize("command", ["bluetooth on", "wifi off", "volume on", "don't open youtube", "YouTube off nahi karo"])
def test_device_semantics_and_negation_are_preserved(command):
    assert canonical_command(command) == command


def test_all_powershell_phrase_and_unrelated_windows(db, ctx, monkeypatch):
    command = "جتنی بھی پاور شیل کی ونڈو کھلی ہے سب بند کر"
    assert all_powershell_request(command)
    assert not all_powershell_request("تمام پاور شیل بند نہیں کرو")
    registry = ToolRegistry(ctx)
    metadata = [
        {"id": 11, "pid": 101, "title": "Windows PowerShell", "process": "conhost.exe"},
        {"id": 12, "pid": 102, "title": "Windows PowerShell", "process": "conhost.exe"},
        {"id": 13, "pid": 103, "title": "Chrome", "process": "chrome.exe"},
    ]
    monkeypatch.setattr(registry.get("control_desktop"), "execute", lambda _: ToolResult(success=True, output={"completed_steps": [{"windows": metadata}]}))
    plan = window_plan(executor.create_task(db, command), registry)
    assert len(plan.actions) == 2
    assert [action.args["target_window_id"] for action in plan.actions] == [11, 12]
    assert [action.args["target_process_id"] for action in plan.actions] == [101, 102]


def test_browser_title_does_not_become_powershell_close(db, ctx, monkeypatch):
    registry = ToolRegistry(ctx)
    monkeypatch.setattr(registry.get("control_desktop"), "execute", lambda _: ToolResult(success=True, output={"completed_steps": [{"windows": [{"id": 1, "pid": 2, "title": "PowerShell tutorial - Chrome", "process": "chrome.exe"}]}]}))
    plan = window_plan(executor.create_task(db, "close all powershell windows"), registry)
    assert not plan.actions


def test_powershell_app_gets_visible_console(monkeypatch):
    from app.tools import platform as native
    calls = []
    monkeypatch.setattr(native.platform, "system", lambda: "Windows")
    monkeypatch.setattr(native.subprocess, "CREATE_NEW_CONSOLE", 16, raising=False)
    monkeypatch.setattr(native.subprocess, "Popen", lambda command, **kwargs: calls.append((command, kwargs)))
    native.launch_program("powershell.exe")
    assert calls == [(["powershell.exe"], {"creationflags": 16})]


def test_followup_uses_only_immediate_successful_target():
    import json
    from types import SimpleNamespace
    from app.ai.command_intents import switch_followup
    action = SimpleNamespace(status="succeeded", tool_name="open_application", args_json=json.dumps({"app_name": "powershell"}))
    prior = SimpleNamespace(status="completed", actions=[action])
    assert switch_followup("off kar do", prior) == "close powershell"
    assert switch_followup("پھر آن کرو", prior) == "open app powershell"
    prior.status = "failed"
    assert switch_followup("on", prior) is None
    assert switch_followup("on", None) is None
    browser = SimpleNamespace(status="completed", command="YouTube Chrome mein off karo", actions=[SimpleNamespace(status="succeeded", tool_name="control_browser", args_json=json.dumps({"action": "close", "target": "youtube"}))])
    assert switch_followup("آن کرو", browser) == "open youtube in chrome"

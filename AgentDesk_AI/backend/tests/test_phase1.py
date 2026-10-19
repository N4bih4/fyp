import sys
import types
import pytest
from app.ai.local_commands import local_plan
from app.tools.system import ManageSystemSettingTool
from app.tools.settings_pages import OpenWindowsSettingsTool


@pytest.mark.parametrize("command,setting,action", [
    ("wi fi off kar do", "wifi", "off"),
    ("Wi-Fi on", "wifi", "on"),
    ("وائی فائی بند کر دو", "wifi", "off"),
    ("वाई फाई ऑन करो", "wifi", "on"),
    ("bluetooth off", "bluetooth", "off"),
])
def test_radio_commands(command, setting, action):
    assert local_plan(command).actions[0].args == {"setting": setting, "action": action}


@pytest.mark.parametrize("command,page", [
    ("open settings", "root"), ("open setting", "root"),
    ("windows update settings", "windowsupdate"),
    ("window update setting kholo", "windowsupdate"),
    ("screen ki setting khol do", "display"),
    ("open lock screen settings", "lockscreen"),
    ("bluetooth settings kholo", "bluetooth"),
    ("wifi setting open karo", "wifi"),
    ("sound settings", "sound"),
    ("سکرین کی سیٹنگ کھولو", "display"),
    ("स्क्रीन की सेटिंग खोल दो", "display"),
])
def test_direct_settings(command, page):
    plan = local_plan(command)
    assert plan and plan.actions
    assert plan.actions[0].tool == "open_windows_settings"
    assert plan.actions[0].args == {"page": page}


@pytest.mark.parametrize("command", ["don't open settings", "settings delete files", "wifi increase", "wifi on off"])
def test_uncertain_commands(command):
    assert local_plan(command) is None


def radio_api(monkeypatch, access=1, result=1, stuck=False):
    calls = []
    radio = types.SimpleNamespace(kind=2, state=1)
    async def request():
        calls.append("access")
        return access
    async def change(target):
        calls.append(target)
        if not stuck and result == 1:
            radio.state = target
        return result
    async def get():
        return [radio]
    radio.set_state_async = change
    api = types.ModuleType("winsdk.windows.devices.radios")
    api.Radio = types.SimpleNamespace(request_access_async=request, get_radios_async=get)
    api.RadioKind = types.SimpleNamespace(BLUETOOTH=2, WI_FI=3)
    api.RadioState = types.SimpleNamespace(ON=1, OFF=0)
    api.RadioAccessStatus = types.SimpleNamespace(ALLOWED=1)
    monkeypatch.setitem(sys.modules, "winsdk.windows.devices.radios", api)
    return radio, calls


def test_bluetooth_real_method_import_and_readback(monkeypatch):
    radio, calls = radio_api(monkeypatch)
    ManageSystemSettingTool._set_bluetooth(False)
    assert radio.state == 0 and calls == ["access", 0]
    assert ManageSystemSettingTool._bluetooth() is False


@pytest.mark.parametrize("access,result", [(2, 1), (1, 2)])
def test_radio_denials_do_not_report_success(monkeypatch, ctx, access, result):
    radio_api(monkeypatch, access, result)
    tool = ManageSystemSettingTool(ctx)
    monkeypatch.setattr(tool, "_require_windows", lambda: None)
    response = tool.execute(tool.validate_args({"setting": "bluetooth", "action": "off"}))
    assert not response.success
    assert "denied" in response.error or "rejected" in response.error


def test_wifi_does_not_change_bluetooth(monkeypatch):
    radio, calls = radio_api(monkeypatch)
    with pytest.raises(RuntimeError, match="did not find a wifi"):
        ManageSystemSettingTool._set_radio("wifi", False)
    assert radio.state == 1 and calls == []


def test_wifi_change_uses_wifi_radio_and_readback(monkeypatch):
    radio, calls = radio_api(monkeypatch)
    radio.kind = 3
    ManageSystemSettingTool._set_radio("wifi", False)
    assert ManageSystemSettingTool._radio_state("wifi") is False
    ManageSystemSettingTool._set_radio("wifi", True)
    assert ManageSystemSettingTool._radio_state("wifi") is True
    assert calls == ["access", 0, "access", 1]


def test_settings_allowlist_and_launch_failure(monkeypatch, ctx):
    tool = OpenWindowsSettingsTool(ctx)
    with pytest.raises(ValueError):
        tool.validate_args({"page": "ms-settings:arbitrary"})
    monkeypatch.setattr("app.tools.settings_pages.platform.system", lambda: "Windows")
    def fail(uri):
        raise OSError("handler unavailable")
    monkeypatch.setattr("app.tools.settings_pages.os.startfile", fail, raising=False)
    assert not tool.execute(tool.validate_args({"page": "display"})).success


def test_bound_folder_choice_preserves_delete_and_requires_approval(client, db, tmp_path, monkeypatch):
    import app.main as main
    from app.config import Settings
    from app.orchestration import executor
    from app.tools.base import ToolContext
    from app.tools.registry import ToolRegistry
    for parent in ("one", "two"):
        (tmp_path / parent / "lab").mkdir(parents=True)
    registry = ToolRegistry(ToolContext(allowed_directories=[tmp_path]))
    monkeypatch.setattr(main, "_registry", lambda: registry)
    task = executor.start_task(db, "delete folder lab", None, registry, Settings(ai_provider="groq", groq_api_key=None))
    assert task.status == "awaiting_input"
    response = client.post(f"/tasks/{task.id}/reply", json={"message": "2"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "awaiting_approval"
    assert body["actions"][0]["tool_name"] == "delete_file"
    assert len(list(tmp_path.rglob("lab"))) == 2


def test_incorrect_readback_is_failure(ctx, monkeypatch):
    tool = ManageSystemSettingTool(ctx)
    monkeypatch.setattr(tool, "_require_windows", lambda: None)
    monkeypatch.setattr(tool, "_brightness", lambda: 50)
    monkeypatch.setattr(tool, "_set_brightness", lambda value: None)
    result = tool.execute(tool.validate_args({"setting": "brightness", "action": "decrease"}))
    assert not result.success and "reports 50" in result.error


def test_radio_state_must_reach_target(monkeypatch):
    radio, calls = radio_api(monkeypatch, stuck=True)
    async def immediate(_):
        pass
    monkeypatch.setattr("app.tools.system.asyncio.sleep", immediate)
    with pytest.raises(RuntimeError, match="did not apply"):
        ManageSystemSettingTool._set_bluetooth(False)
    assert radio.state == 1


def test_volume_up_unmutes_and_changes_real_endpoint_contract(ctx, monkeypatch):
    state = {"volume": 0.5, "muted": True}
    class Endpoint:
        def GetMasterVolumeLevelScalar(self): return state["volume"]
        def SetMasterVolumeLevelScalar(self, value, _): state["volume"] = value
        def GetMute(self): return state["muted"]
        def SetMute(self, value, _): state["muted"] = bool(value)
    tool = ManageSystemSettingTool(ctx)
    monkeypatch.setattr(tool, "_require_windows", lambda: None)
    monkeypatch.setattr(tool, "_volume_endpoint", lambda: Endpoint())
    # Class methods use the class's endpoint factory.
    monkeypatch.setattr(ManageSystemSettingTool, "_volume_endpoint", staticmethod(lambda: Endpoint()))
    result = tool.execute(tool.validate_args({"setting": "volume", "action": "increase"}))
    assert result.success and result.output["value"] == 60
    assert state["muted"] is False


def test_mute_failure_is_not_reported_as_success(ctx, monkeypatch):
    class Endpoint:
        def SetMute(self, *_): pass
        def GetMute(self): return True
    monkeypatch.setattr(ManageSystemSettingTool, "_volume_endpoint", staticmethod(lambda: Endpoint()))
    tool = ManageSystemSettingTool(ctx)
    monkeypatch.setattr(tool, "_require_windows", lambda: None)
    result = tool.execute(tool.validate_args({"setting": "volume", "action": "unmute"}))
    assert not result.success and "mute state" in result.error

import json
from pathlib import Path
import pytest
from app.ai.local_commands import local_plan
from app.config import Settings
from app.models import TaskStatus
from app.orchestration import executor
from app.tools.base import ToolContext, ToolResult
from app.tools.registry import ToolRegistry
from app.tools.system import ManageSystemSettingTool


@pytest.mark.parametrize("text,setting,action,value", [
    ("volume volume down", "volume", "decrease", 10),
    ("vol ume up", "volume", "increase", 10),
    ("valume kam kar do", "volume", "decrease", 10),
    ("volumme down", "volume", "decrease", 10),
    ("please meri brightness zyada karo", "brightness", "increase", 10),
    ("bright ness de crease", "brightness", "decrease", 10),
    ("decrease volume by 20 percent", "volume", "decrease", 20),
    ("set brightness to 45%", "brightness", "set", 45),
    ("वॉल्यूम ज्यादा करो", "volume", "increase", 10),
    ("ब्राइटनेस कम कर दो", "brightness", "decrease", 10),
    ("والیوم کم کر دو", "volume", "decrease", 10),
    ("blue tooth on kar do", "bluetooth", "on", None),
    ("bluetooth off", "bluetooth", "off", None),
    ("ब्लूटूथ बंद कर दो", "bluetooth", "off", None),
    ("بلوٹوتھ آن کر دو", "bluetooth", "on", None),
    ("dark mode kar do", "theme", "dark", None),
    ("light mode", "theme", "light", None),
    ("डार्क मोड में कर दो", "theme", "dark", None),
    ("लाइट मोड कर दो", "theme", "light", None),
    ("volume band kar do", "volume", "mute", None),
])
def test_spoken_variants(text, setting, action, value):
    plan = local_plan(text)
    assert plan is not None and len(plan.actions) == 1, text
    assert plan.actions[0].args == {"setting": setting, "action": action, **({"value": value} if value is not None else {})}


@pytest.mark.parametrize("text", ["don't turn volume up", "volume down up", "brightness -20", "volume down and delete files", "volume 20 40", "bluetooth increase", "dark mode delete folder"])
def test_uncertain_or_compound_commands_are_not_guessed(text):
    assert local_plan(text) is None


def start(db, registry, command):
    return executor.start_task(db, command, None, registry, Settings(ai_provider="groq", groq_api_key=None))


def test_local_discovery_preview_and_delete_without_api(db, tmp_path, monkeypatch):
    for name in ("lab", "college"):
        (tmp_path / name / "lecture").mkdir(parents=True)
    registry = ToolRegistry(ToolContext(allowed_directories=[tmp_path]))
    monkeypatch.setattr(executor, "get_provider", lambda *_: pytest.fail("cloud used for local workflow"))
    monkeypatch.setattr("app.tools.platform.open_path_with_os", lambda _: None)
    task = start(db, registry, "delete folder lecture")
    assert task.status == TaskStatus.AWAITING_INPUT and not task.actions
    assert len(json.loads(task.agent_state_json)["workflow"]["candidates"]) == 2
    preview = start(db, registry, "preview 1")
    assert preview.status == TaskStatus.COMPLETED
    assert preview.actions[0].tool_name == "open_folder"
    confirmed = start(db, registry, "haan")
    assert confirmed.status == TaskStatus.AWAITING_APPROVAL
    assert confirmed.actions[0].tool_name == "delete_file"
    assert len(list(tmp_path.rglob("lecture"))) == 2
    executor.approve_task(db, confirmed.id, [a.id for a in confirmed.actions])
    finished = executor.run_task(db, confirmed.id, registry, Settings(ai_provider="groq", groq_api_key=None))
    assert finished.status == TaskStatus.COMPLETED
    assert len(list(tmp_path.rglob("lecture"))) == 1


def test_local_create_asks_for_destination(db, tmp_path, monkeypatch):
    registry = ToolRegistry(ToolContext(allowed_directories=[tmp_path]))
    monkeypatch.setattr(executor, "get_provider", lambda *_: pytest.fail("cloud used"))
    first = start(db, registry, "create folder Study")
    assert not first.actions
    second = start(db, registry, str(tmp_path))
    assert second.status == TaskStatus.AWAITING_APPROVAL
    assert json.loads(second.actions[0].args_json)["path"] == str(tmp_path / "Study")


def test_unknown_pc_command_requests_clarification_without_api(db, tmp_path, monkeypatch):
    registry = ToolRegistry(ToolContext(allowed_directories=[tmp_path]))
    monkeypatch.setattr(executor, "get_provider", lambda *_: pytest.fail("cloud used"))
    monkeypatch.setattr(registry.get("control_desktop"), "execute", lambda *_: ToolResult(success=True, output={"completed_steps": [{"open_windows": []}]}))
    task = start(db, registry, "close something")
    assert task.status == TaskStatus.AWAITING_INPUT
    assert not task.actions


def test_theme_tool_reads_back_actual_state(ctx, monkeypatch):
    monkeypatch.setattr(ManageSystemSettingTool, "_require_windows", staticmethod(lambda: None))
    monkeypatch.setattr(ManageSystemSettingTool, "_set_theme", lambda self, mode: {"apps": mode, "system": mode})
    tool = ManageSystemSettingTool(ctx)
    result = tool.execute(tool.validate_args({"setting": "theme", "action": "dark"}))
    assert result.success and result.output == {"setting": "theme", "apps": "dark", "system": "dark"}


def test_explicit_package_download_is_not_misread_as_search(db, tmp_path, monkeypatch):
    registry = ToolRegistry(ToolContext(allowed_directories=[tmp_path]))
    monkeypatch.setattr(executor, "get_provider", lambda *_: pytest.fail("cloud used"))
    task = start(db, registry, "download package Microsoft.VisualStudioCode")
    assert task.status == TaskStatus.AWAITING_APPROVAL
    assert json.loads(task.actions[0].args_json)["action"] == "download"


def test_local_multistep_request_does_not_need_provider(db, tmp_path, monkeypatch):
    registry = ToolRegistry(ToolContext(allowed_directories=[tmp_path]))
    calls = []
    def execute(args):
        calls.append(args.setting)
        return ToolResult(success=True, output={"setting": args.setting, "value": 40})
    monkeypatch.setattr(registry.get("manage_system_setting"), "execute", execute)
    monkeypatch.setattr(executor, "get_provider", lambda *_: pytest.fail("cloud used"))
    from app.verification import use_probe
    from tests.helpers.fake_probe import ScriptedProbe
    probe = ScriptedProbe(settings={"volume": {"value": 40}, "brightness": {"value": 40}})
    with use_probe(probe):
        task = start(db, registry, "volume down aur brightness up")
        assert task.status == TaskStatus.COMPLETED
        assert calls == ["volume", "brightness"]
        followup = start(db, registry, "aur kam karo")
    assert followup.status == TaskStatus.COMPLETED
    assert json.loads(followup.actions[0].args_json)["setting"] == "brightness"

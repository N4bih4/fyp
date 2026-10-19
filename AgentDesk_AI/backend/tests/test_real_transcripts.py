"""Regression tests from the user's actual failed voice transcripts."""
import json
import pytest
from app.ai.command_language import command_grammar
from app.ai.local_commands import local_plan
from app.config import Settings
from app.models import TaskStatus
from app.orchestration import executor
from app.tools.base import ToolContext
from app.tools.registry import ToolRegistry


@pytest.mark.parametrize("transcript,setting,action", [
    ("میوٹ پی سی", "volume", "mute"),
    ("ان میوٹ پی سی", "volume", "unmute"),
    ("ان میوٹ کرو", "volume", "unmute"),
    ("انمیوٹ پی سی", "volume", "unmute"),
    ("ہیں کلوز بلو ت", "bluetooth", "off"),
    ("ٹرن اف بلوٹوتھ", "bluetooth", "off"),
    ("کلوز بلو ت", "bluetooth", "off"),
    ("close blue tooth", "bluetooth", "off"),
    ("wifi close kar do", "wifi", "off"),
    ("والیوم اپ", "volume", "increase"),
    ("پی سی کی بلیوٹوتھ اف کرو", "bluetooth", "off"),
    ("ڈکریز برائٹنس", "brightness", "decrease"),
    ("والیوم پی سی کا بولیم 50 پرسنٹ کر دو", "volume", "set"),
])
def test_actual_setting_transcripts(transcript, setting, action):
    plan = local_plan(transcript)
    assert plan and plan.actions
    assert plan.actions[0].args["setting"] == setting
    assert plan.actions[0].args["action"] == action


@pytest.mark.parametrize("text", ["بلو", "close blue", "bluetooth close nahi karo", "close bluetooth folder", "ہیں کلوز بلو ت اور فائل ڈیلیٹ کرو"])
def test_radio_alias_does_not_guess_other_targets_or_negation(text):
    assert local_plan(text) is None


@pytest.mark.parametrize("spoken,canonical", [
    ("سک سمسٹر کا فولڈر ان اوپن کرو", "open folder سک سمسٹر"),
    ("میرا لیکچر کا فولڈر کھول دو", "open folder لیکچر"),
    ("لیکچر فولڈر اوپن کر دو", "open folder لیکچر"),
    ("मेरा लेक्चर का फोल्डर ओपन करो", "open folder लेक्चर"),
    ("میرا نوٹ پیڈ اوپن کرو", "open app نوٹ پیڈ"),
    ("اوپن یوٹیوب", "open app یوٹیوب"),
    ("lecture ka folder open karo", "open folder lecture"),
    ("لیب کا فولڈر ڈیلیٹ کر دو", "delete folder لیب"),
])
def test_script_grammar_preserves_target_name(spoken, canonical):
    assert command_grammar(spoken) == canonical


def test_screenshot_transcript_resolves_to_real_candidate_without_cloud(db, tmp_path, monkeypatch):
    folder = tmp_path / "6th sem"
    folder.mkdir()
    registry = ToolRegistry(ToolContext(allowed_directories=[tmp_path]))
    settings = Settings(ai_provider="groq", groq_api_key=None)
    monkeypatch.setattr(executor, "get_provider", lambda *_: pytest.fail("cloud called"))
    opened = []
    monkeypatch.setattr("app.tools.platform.open_path_with_os", opened.append)
    task = executor.start_task(db, "سک سمسٹر کا فولڈر ان اوپن کرو", None, registry, settings)
    assert task.status == TaskStatus.AWAITING_INPUT
    workflow = json.loads(task.agent_state_json)["workflow"]
    assert workflow["candidates"] == [str(folder)]
    assert str(folder) in task.plan_note
    assert opened == []
    result = executor.start_task(db, "1", None, registry, settings)
    assert result.status == TaskStatus.COMPLETED
    assert opened == [str(folder)]
    assert result.actions[0].status == "succeeded"


def test_unmatched_urdu_folder_retains_local_workflow(db, tmp_path, monkeypatch):
    registry = ToolRegistry(ToolContext(allowed_directories=[tmp_path]))
    monkeypatch.setattr(executor, "get_provider", lambda *_: pytest.fail("cloud called"))
    task = executor.start_task(db, "نامعلوم کا فولڈر اوپن کرو", None, registry, Settings(ai_provider="groq", groq_api_key=None))
    assert task.status == TaskStatus.AWAITING_INPUT
    assert json.loads(task.agent_state_json)["workflow"]["source"] == "نامعلوم"
    assert "exact path" in task.plan_note


def test_user_provided_discovery_root_is_found_without_mutation_access(tmp_path):
    from app.tools.filesystem import FindPathsTool
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    external = tmp_path / "6th sem"
    external.mkdir()
    context = ToolContext(allowed_directories=[allowed], discovery_directories=[allowed, external])
    tool = FindPathsTool(context)
    result = tool.execute(tool.validate_args({"name": "سک سمسٹر", "kind": "folder"}))
    assert result.output["candidates"] == [str(external)]
    assert external not in context.allowed_directories


@pytest.mark.parametrize("failure", [False, True])
def test_hardware_worker_is_bounded_and_native_failure_is_contained(ctx, monkeypatch, failure):
    from types import SimpleNamespace
    from app.tools.system import ManageSystemSettingTool
    ctx.isolate_system_controls = True
    monkeypatch.setattr("app.tools.system.platform.system", lambda: "Windows")
    def run(command, **options):
        assert options["shell"] is False
        assert options["timeout"] == 20
        assert command[-1] == "app.tools.system_worker"
        return SimpleNamespace(returncode=1 if failure else 0, stdout='AGENTX_RESULT={"success":true,"output":{"setting":"volume","value":42}}\n')
    monkeypatch.setattr("app.tools.system.subprocess.run", run)
    tool = ManageSystemSettingTool(ctx)
    result = tool.execute(tool.validate_args({"setting": "volume", "action": "get"}))
    assert result.success is not failure


def test_hardware_worker_timeout_does_not_hang_api(ctx, monkeypatch):
    import subprocess
    from app.tools.system import ManageSystemSettingTool
    ctx.isolate_system_controls = True
    monkeypatch.setattr("app.tools.system.platform.system", lambda: "Windows")
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("worker", 20)
    monkeypatch.setattr("app.tools.system.subprocess.run", timeout)
    tool = ManageSystemSettingTool(ctx)
    result = tool.execute(tool.validate_args({"setting": "brightness", "action": "get"}))
    assert not result.success and "20 seconds" in result.error


def test_relative_correction_repairs_the_reported_wrapped_request(client, db, tmp_path, monkeypatch):
    import app.main as main
    semester = tmp_path / "6th sem"
    lab = semester / "cn" / "lab"
    lab.mkdir(parents=True)
    registry = ToolRegistry(ToolContext(allowed_directories=[tmp_path], discovery_directories=[semester]))
    monkeypatch.setattr(main, "_registry", lambda: registry)
    opened = []
    monkeypatch.setattr("app.tools.platform.open_path_with_os", opened.append)
    original = executor.create_task(db, "Original request: اوپن لیب\nUser correction/clarification: 6th sem/cn/lab\nThe previous proposal was cancelled. Clarify or propose the corrected action.")
    original.status = TaskStatus.AWAITING_INPUT
    db.commit()
    result = client.post(f"/tasks/{original.id}/reply", json={"message": "6th sem/cn/lab"})
    assert result.status_code == 200
    assert result.json()["status"] == "completed"
    assert result.json()["command"] == "6th sem/cn/lab"
    assert opened == [str(lab)]


def test_relative_paths_are_scoped_to_discovery_roots(tmp_path):
    from app.orchestration.local_agent import relative_candidates
    semester = tmp_path / "6th sem"
    lab = semester / "cn" / "lab"
    lab.mkdir(parents=True)
    registry = ToolRegistry(ToolContext(allowed_directories=[semester]))
    assert relative_candidates("6th sem/cn/lab", registry) == [lab]
    assert relative_candidates("cn/lab", registry) == [lab]
    assert relative_candidates("../", registry) == []

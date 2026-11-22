"""Rules found by the coverage matrix (docs/COVERAGE.md): settings pages and the Control Panel, known folders, sites, media keys, theme, Hindi device and YouTube commands."""
from __future__ import annotations

import pytest

from app.ai import coverage_commands as cc
from app.tools.registry import ToolRegistry
from app.tools.settings_pages import PAGES


def first(text):
    plan = cc.coverage_plan(text)
    return (plan.actions[0].tool, plan.actions[0].args) if plan else None


@pytest.mark.parametrize("text,page", [
    ("open settings", "root"), ("open display settings", "display"), ("sound settings kholo", "sound"), ("open control panel", "controlpanel"),
    ("device manager kholo", "devicemanager"), ("कंट्रोल पैनल खोलो", "controlpanel"), ("windows update kholo", "windowsupdate"), ("open installed apps", "apps"),
    ("battery settings kholo", "battery"), ("open power options", "poweroptions"), ("डिस्प्ले सेटिंग्स खोलो", "display"), ("open programs and features", "programsfeatures"),
])
def test_settings_and_control_panel_pages(text, page):
    assert first(text) == ("open_windows_settings", {"page": page})


@pytest.mark.parametrize("text", ["turn wifi off", "set the volume to 30", "increase brightness", "turn bluetooth on", "open wifi", "wifi band karo", "open notepad", "open chrome"])
def test_a_change_or_an_app_is_not_a_settings_page(text):
    assert first(text) is None or first(text)[0] != "open_windows_settings"


def test_every_page_the_rules_name_exists_in_the_tool():
    assert {page for page, _, _ in cc.PAGES} <= set(PAGES)
    tool = ToolRegistry().get("open_windows_settings")
    for page in PAGES:
        tool.validate_args({"page": page})


@pytest.mark.parametrize("text,tool", [
    ("downloads kholo", "explorer_navigate"), ("डाउनलोड खोलो", "explorer_navigate"), ("what is in my downloads", "list_folder"), ("downloads mein kya hai", "list_folder"),
    ("github kholo", "open_url"), ("गिटहब खोलो", "open_url"), ("open a new tab", "open_url"), ("nayi tab kholo", "open_url"), ("reopen my last closed tab", "control_browser"),
    ("what windows are open", "control_desktop"), ("pause the music", "media_control"), ("agla gana", "media_control"), ("dark mode lagao", "manage_system_setting"),
    ("पीसी लॉक करो", "device_control"), ("पीसी रीस्टार्ट करो", "device_control"), ("अगला वीडियो", "control_browser"), ("10 सेकंड आगे करो", "control_browser"),
    ("open a terminal", "open_terminal"), ("powershell kholo", "open_terminal"),
])
def test_clear_sentences_get_a_local_plan(text, tool):
    assert first(text)[0] == tool


def test_show_desktop_does_not_open_the_desktop_folder():
    assert first("show desktop") is None and first("desktop dikhao") is None
    assert first("open desktop folder")[0] == "explorer_navigate"


def test_window_state_points_at_the_window_in_front_and_never_at_ours(monkeypatch):
    monkeypatch.setattr(cc, "active_window_title", lambda: "Untitled - Notepad")
    assert first("minimize this window") == ("control_desktop", {"target_window": "Untitled - Notepad", "steps": [{"action": "minimize_window"}]})
    monkeypatch.setattr(cc, "active_window_title", lambda: None)             # the front window is ours (or unknown): the cloud planner inspects first
    assert first("close this window") is None


def test_a_longer_sentence_is_left_to_the_other_parsers():
    assert first("open the control panel and then change my wallpaper to blue please") is None
    assert first("what is in my downloads folder that is bigger than ten megabytes") is None


# ---- found in the live session: drive sentences with "ko ... karo", "Explorer mein", and an Explorer "profile" that is the Windows user folder
def _first(text):
    from app.ai.profile_commands import drive_plan, profile_plan
    plan = profile_plan(text) or drive_plan(text)
    return (plan.actions[0].tool, plan.actions[0].args) if plan else None


def test_drive_sentences_are_understood_however_they_are_put():
    for text in ["C drive ko open karo.", "Explorer mein C drive open karo", "Mac, C drive open,", "go to the C drive please", "C drive kholo"]:
        assert _first(text) == ("explorer_navigate", {"path": "C:\\"}), text


def test_google_drive_and_actions_in_a_drive_are_not_navigation():
    assert _first("open google drive") is None and _first("create a file in C drive") is None


def test_a_profile_said_with_explorer_is_the_windows_user_folder_not_a_browser_profile():
    tool, args = _first("File Explorer mein meri profile kholo")
    assert tool == "explorer_navigate" and args["path"].lower().startswith("c:\\users")
    assert _first("chrome zain profile kholo")[0] == "open_browser_profile"


def test_a_drive_that_is_not_on_this_pc_is_named_in_the_answer(monkeypatch):
    from app.tools.base import ToolContext
    from app.tools.explorer_view import ExplorerNavigateTool
    assert _first("D drive kholo") == ("explorer_navigate", {"path": "D:" + chr(92)})
    tool = ExplorerNavigateTool(ToolContext())
    out = tool.execute(tool.validate_args({"path": "Q:" + chr(92)}))
    assert not out.success and "no Q: drive" in out.error and "C:" in out.error


def test_roman_urdu_louder_and_quieter_are_local_commands(db):
    from app.orchestration import executor, local_agent
    from app.tools.registry import ToolRegistry
    registry = ToolRegistry()
    for text, setting, action in (("volume thora barha do", "volume", "increase"), ("awaaz barha do", "volume", "increase"), ("volume ghata do", "volume", "decrease"),
                                  ("thori awaaz kam karo", "volume", "decrease"), ("roshni barhao", "brightness", "increase")):
        task = executor.create_task(db, text)
        plan = local_agent.prepare_local_request(db, task, registry)
        args = plan.actions[0].args
        assert plan.actions[0].tool == "manage_system_setting" and args["setting"] == setting and args["action"] == action, text


def test_battery_questions_in_roman_urdu_are_local_commands():
    from app.ai.device_commands import device_plan
    for text in ["battery kitni hai", "charge kitna hai", "battery kitne percent hai", "battery status batao", "charging status"]:
        plan = device_plan(text)
        assert plan is not None and plan.actions[0].tool == "device_control" and plan.actions[0].args == {"action": "battery"}, text


def test_asking_how_loud_or_bright_it_is_reads_the_setting_and_never_changes_it(db):
    from app.orchestration import executor, local_agent
    from app.tools.registry import ToolRegistry
    registry = ToolRegistry()
    for text, setting in (("volume kitni hai", "volume"), ("awaaz kitni hai", "volume"), ("brightness kitni hai", "brightness")):
        plan = local_agent.prepare_local_request(db, executor.create_task(db, text), registry)
        assert plan.actions[0].args == {"setting": setting, "action": "get"}, text
    plan = local_agent.prepare_local_request(db, executor.create_task(db, "volume kitni karni hai"), registry)
    assert not plan.actions                                  # "how much should it be?" is a question back to the user, not a change


def test_a_window_listed_twice_under_one_title_is_one_choice_not_a_question():
    """Soak test: "calculator band karo" asked "which one? 1. Calculator 2. Calculator" because Windows lists the Calculator frame and window."""
    from types import SimpleNamespace as NS
    from app.ai import window_commands
    from app.tools.base import ToolResult

    class Control:
        def validate_args(self, a):
            return a

        def execute(self, a):
            return ToolResult(success=True, output={"completed_steps": [{"open_windows": ["Calculator", "Calculator", "Notepad"]}]})

    class Registry:
        def get(self, name):
            return Control()
    plan = window_commands.window_plan(NS(command="calculator band karo", agent_state_json=None), Registry(), "calculator band karo")
    assert plan.actions and plan.actions[0].args["target_window"] == "Calculator"

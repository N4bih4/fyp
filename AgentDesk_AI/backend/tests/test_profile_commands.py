import pytest

from app.ai.profile_commands import profile_plan


@pytest.mark.parametrize("text,profile,browser", [
    ("open chrome with the Work profile", "work", "chrome"),
    ("Zain wali profile kholo", "zain", "chrome"),
    ("edge profile 2 kholo", "2", "edge"),
    ("open the Mary profile", "mary", "chrome"),
    ("chrome mein muhammad zain profile kholo", "muhammad zain", "chrome"),
])
def test_profile_commands(text, profile, browser):
    plan = profile_plan(text)
    assert plan and plan.actions[0].tool == "open_browser_profile"
    assert plan.actions[0].args == {"profile": profile, "browser": browser}


@pytest.mark.parametrize("text", ["open chrome", "open notepad", "profile", "what is my profile picture of ali on instagram and facebook and twitter, " * 3])
def test_other_commands_are_left_alone(text):
    assert profile_plan(text) is None


def _asked(*candidates):
    import json
    import types
    act = types.SimpleNamespace(tool_name="open_browser_profile", status="failed", args_json='{"browser": "chrome"}',
                                result_json=json.dumps({"output": {"candidates": list(candidates)}}))
    return types.SimpleNamespace(actions=[act])


@pytest.mark.parametrize("reply,profile", [("second", "5"), ("profile 3", "3"), ("pehla", "3"), ("5", "5"), ("Work", "work")])
def test_the_answer_to_which_profile(reply, profile):
    from app.ai.profile_commands import profile_answer
    plan = profile_answer(_asked("Muhammad Zain (Profile 3)", "Muhammad Zain (Profile 5)"), reply)
    assert plan.actions[0].args == {"profile": profile, "browser": "chrome"}


def test_a_reply_to_some_other_question_is_not_taken():
    import types
    from app.ai.profile_commands import profile_answer
    other = types.SimpleNamespace(actions=[types.SimpleNamespace(tool_name="open_application", status="failed", args_json="{}", result_json="{}")])
    assert profile_answer(other, "second") is None


@pytest.mark.parametrize("text", ["C drive kholo", "open C drive", "c drive", "drive c kholo"])
def test_a_drive_opens_in_file_explorer(text):
    from app.ai.profile_commands import drive_plan
    plan = drive_plan(text)
    assert plan and plan.actions[0].tool == "explorer_navigate" and plan.actions[0].args == {"path": "C:\\"}


def test_a_missing_drive_or_other_sentence_is_left_alone():
    from app.ai.profile_commands import drive_plan
    assert drive_plan("open notepad") is None
    assert drive_plan("Q drive kholo").actions[0].args == {"path": "Q:" + chr(92)}      # a drive that is not here still gets a plan: the tool says which drives exist


# ---- "I want to open another profile in Chrome": show Chrome's own profile screen, then the user names one there
def _plan(text):
    from app.ai.profile_commands import profile_plan
    plan = profile_plan(text)
    return (plan.actions[0].tool, plan.actions[0].args) if plan else None


def test_another_profile_without_a_name_shows_the_profile_screen():
    for text in ["open another profile", "chrome mein koi aur profile open karni hai", "chrome profile kholo", "profile kholni hai", "show me the chrome profiles"]:
        assert _plan(text) == ("open_browser_profile", {"profile": "", "browser": "chrome", "picker": True}), text
    assert _plan("chrome zain profile kholo")[1] == {"profile": "zain", "browser": "chrome"}


def test_a_short_answer_after_the_profile_screen_opens_that_profile(monkeypatch):
    import json
    from types import SimpleNamespace as NS
    from app.ai import profile_commands
    monkeypatch.setattr("app.tools.browser_profiles.list_profiles", lambda b, data_dir=None: [
        {"dir": "Default", "name": "CH Zain", "account": "", "email_name": ""}, {"dir": "Profile 10", "name": "Work", "account": "", "email_name": ""},
        {"dir": "Profile 2", "name": "Nabiha Zainab", "account": "", "email_name": ""}])
    shown = NS(actions=[NS(tool_name="open_browser_profile", status="succeeded", args_json=json.dumps({"browser": "chrome", "picker": True}),
                           result_json=json.dumps({"output": {"picker": True}}))])
    plan = profile_commands.profile_followup("Work wali", shown)
    assert plan.actions[0].args == {"profile": "10", "browser": "chrome"}
    assert profile_commands.profile_followup("Work", NS(actions=[NS(tool_name="open_url", status="succeeded", args_json="{}", result_json="{}")])) is None


def test_the_picker_opens_the_browsers_profile_screen_and_an_unknown_name_falls_back_to_it(monkeypatch, tmp_path):
    from app.tools import browser_profiles as bp
    from app.tools.base import ToolContext
    launched = []
    profiles = [{"dir": "Default", "name": "CH Zain", "account": "", "email_name": ""}]
    monkeypatch.setattr(bp, "list_profiles", lambda b, data_dir=None: profiles)
    monkeypatch.setattr(bp, "find_executable", lambda b: tmp_path / "chrome.exe")
    monkeypatch.setattr(bp._platform, "launch_program", lambda exe, args=None: launched.append((exe, list(args or []))))
    monkeypatch.setattr(bp.platform, "system", lambda: "Windows")
    tool = bp.OpenBrowserProfileTool(ToolContext())
    out = tool.execute(tool.validate_args({"picker": True}))
    assert out.success and out.output["picker"] and launched[-1][1] == ["chrome://profile-picker/"]
    out = tool.execute(tool.validate_args({"profile": "xyzzy plugh"}))                 # no such profile: the screen is shown instead of a question
    assert out.success and out.output["picker"] and "could not find a profile called xyzzy plugh" in out.output["spoken"]

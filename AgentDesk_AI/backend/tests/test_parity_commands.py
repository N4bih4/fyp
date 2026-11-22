"""P1 of docs/STONIC_PARITY_PLAN.md: local parsers for the sentences that went to the cloud in all three languages.

Every positive case is the English / Roman Urdu / Hindi sentence of a row in scripts/coverage_rows.py (plus variants); every parser also has
negative cases, because a new parser that misroutes is worse than a missing one.
"""
from __future__ import annotations

import pytest

from app.ai import parity_commands as pc
from app.ai.base import Plan
from app.orchestration import local_agent
from app.tools import desktop
from app.tools.base import RiskLevel
from app.tools.registry import ToolRegistry


def first(text):
    plan = pc.parity_plan(text)
    return (plan.actions[0].tool, plan.actions[0].args) if plan else None


# ------------------------------------------------------------------------------------------------ one finished plan
@pytest.mark.parametrize("text", ["show what I deleted", "jo delete kiya woh dikhao", "जो डिलीट किया वह दिखाओ", "show the recycle bin", "what did I delete"])
def test_show_deleted_lists_the_trash(text):
    assert first(text) == ("list_trash", {})


@pytest.mark.parametrize("text", ["run git status", "git status", "git status chalao", "git status चलाओ"])
def test_git_status_is_one_read_only_command(text):
    assert first(text) == ("run_terminal_command", {"command": "git status"})


@pytest.mark.parametrize("text", ["git status and then delete everything", "run git push", "git status karke push karo", "delete the git folder"])
def test_git_status_is_not_any_other_git_or_shell_command(text):
    assert first(text) is None or first(text)[1] != {"command": "git status"}


@pytest.mark.parametrize("text", ["show desktop", "desktop dikhao", "डेस्कटॉप दिखाओ", "minimize all windows"])
def test_show_desktop_needs_no_window_name(text):
    assert first(text) == ("control_desktop", {"steps": [{"action": "show_desktop"}]})


@pytest.mark.parametrize("text", ["open desktop folder", "what is on my desktop", "delete the desktop shortcut", "desktop wallpaper change karo"])
def test_show_desktop_is_not_the_desktop_folder_or_anything_longer(text):
    assert first(text) is None or first(text)[1] != {"steps": [{"action": "show_desktop"}]}


@pytest.mark.parametrize("text,app", [("switch to chrome", "chrome"), ("chrome pe jao", "chrome"), ("क्रोम पर जाओ", "chrome"), ("go to notepad", "notepad"),
                                      ("notepad par jao", "notepad")])
def test_switch_to_a_known_app_brings_its_window_to_the_front(text, app):
    assert first(text) == ("control_desktop", {"target_window": app, "steps": [{"action": "focus_window"}]})


@pytest.mark.parametrize("text", ["go to youtube", "switch to the next tab", "go to sleep", "switch to something unknown", "ye window pe jao", "switch to it", "go to the page"])
def test_switch_never_guesses_an_unknown_app(text):
    assert first(text) is None or first(text)[0] != "control_desktop"


@pytest.mark.parametrize("text,args", [
    ("message ahmed on whatsapp I am late", {"contact": "ahmed", "text": "i am late"}),
    ("whatsapp pe ahmed ko likho main late hoon", {"contact": "ahmed", "text": "main late hoon"}),
    ("व्हाट्सएप पर अहमद को लिखो मैं लेट हूँ", {"contact": "अहमद", "text": "मैं लेट हूँ"}),
    ("send a whatsapp message to +92 300 1234567 saying hello", {"phone": "+923001234567", "text": "hello"}),
    ("message sara on whatsapp", {"contact": "sara", "text": ""}),
])
def test_whatsapp_opens_a_draft_chat_and_never_sends(text, args):
    assert first(text) == ("whatsapp_open_chat", args)


@pytest.mark.parametrize("text", ["open whatsapp", "message on whatsapp", "whatsapp kholo", "message someone on whatsapp hi", "close whatsapp"])
def test_whatsapp_needs_a_named_person(text):
    assert first(text) is None or first(text)[0] != "whatsapp_open_chat"


@pytest.mark.parametrize("text,args", [
    ("what is my locker number", {"topic": "locker number"}),
    ("mera locker number kya hai", {"topic": "locker number"}),
    ("मेरा लॉकर नंबर क्या है", {"topic": "लॉकर नंबर"}),
    ("what do you remember about me", {}),
    ("what is in my memory", {}),
])
def test_recall_reads_the_users_own_notes(text, args):
    assert first(text) == ("memory_recall", args)


@pytest.mark.parametrize("text", ["what is my battery level", "what is my ip address", "what is my screen resolution", "mera battery kya hai", "what is the capital of australia",
                                  "what is my name and where do i live and what do i like to eat", "what is my time"])
def test_recall_leaves_live_facts_and_world_questions_alone(text):
    assert first(text) is None


@pytest.mark.parametrize("text,name", [
    ("find my resume file", "resume"), ("mera resume file dhundo", "resume"), ("मेरी रिज्यूमे फाइल ढूंढो", "रिज्यूमे"),
    ("find report.txt", "report.txt"), ("where is my cv", "cv"),
])
def test_find_a_file_by_name(text, name):
    assert first(text) == ("find_files", {"name": name})


@pytest.mark.parametrize("text", ["google pe python tutorial search karo", "find app vlc", "find a package for vlc", "find cats on youtube", "find the best laptop and buy it",
                                  "search for python", "find", "where is"])
def test_find_is_not_a_web_search_an_app_search_or_a_chain(text):
    assert first(text) is None or first(text)[0] != "find_files"


# ------------------------------------------------------------------------------------------------ file workflows
@pytest.mark.parametrize("text,intent", [
    ("copy report.txt to documents", {"op": "copy", "kind": "file", "source": "report.txt", "destination": "Documents"}),
    ("report.txt ko documents mein copy karo", {"op": "copy", "kind": "file", "source": "report.txt", "destination": "Documents"}),
    ("report.txt को डॉक्यूमेंट्स में कॉपी करो", {"op": "copy", "kind": "file", "source": "report.txt", "destination": "Documents"}),
    ("move report.txt to desktop", {"op": "move", "kind": "file", "source": "report.txt", "destination": "Desktop"}),
    ("report.txt ko desktop pe move karo", {"op": "move", "kind": "file", "source": "report.txt", "destination": "Desktop"}),
    ("report.txt को डेस्कटॉप पर ले जाओ", {"op": "move", "kind": "file", "source": "report.txt", "destination": "Desktop"}),
    ("copy the folder photos to downloads", {"op": "copy", "kind": "folder", "source": "photos", "destination": "Downloads"}),
    ("rename report.txt to final.txt", {"op": "rename", "kind": "file", "source": "report.txt", "new_name": "final.txt"}),
    ("report.txt ka naam final.txt karo", {"op": "rename", "kind": "file", "source": "report.txt", "new_name": "final.txt"}),
    ("report.txt का नाम final.txt करो", {"op": "rename", "kind": "file", "source": "report.txt", "new_name": "final.txt"}),
    ("read notes.txt", {"op": "read", "kind": "file", "source": "notes.txt"}),
    ("notes.txt parho", {"op": "read", "kind": "file", "source": "notes.txt"}),
    ("notes.txt पढ़ो", {"op": "read", "kind": "file", "source": "notes.txt"}),
])
def test_file_sentences_become_workflow_intents(text, intent):
    assert pc.parity_intent(text) == intent


@pytest.mark.parametrize("text", ["read this page", "read the email", "read it", "rename report.txt to ../x/final.txt", "copy report.txt", "move to desktop",
                                  "open notes.txt", "delete report.txt", "read my mind"])
def test_file_workflow_rules_do_not_fire_on_other_sentences(text):
    assert pc.parity_intent(text) is None


class _FakeFindPaths:
    def __init__(self, candidates):
        self.candidates = candidates

    def validate_args(self, args):
        return args

    def execute(self, args):
        from app.tools.base import ToolResult
        return ToolResult(success=True, output={"candidates": self.candidates, "exact": len(self.candidates) == 1, "confident": len(self.candidates) == 1})


class _FakeRegistry:
    def __init__(self, candidates):
        self.tool = _FakeFindPaths(candidates)

    def get(self, name):
        assert name == "find_paths"
        return self.tool


class _Task:
    agent_state_json = None


def _resolve(text, candidates):
    intent = pc.parity_intent(text)
    return local_agent._resolve(_Task(), intent, _FakeRegistry(candidates))


@pytest.mark.parametrize("text,tool,key", [
    ("copy report.txt to documents", "copy_file", "source"), ("report.txt ko desktop pe move karo", "move_file", "source"),
    ("rename report.txt to final.txt", "rename_file", "path"), ("notes.txt parho", "read_text_file", "path"),
])
def test_one_match_becomes_a_real_tool_call_with_the_found_path(text, tool, key):
    found = str(__import__("pathlib").Path.home() / "Documents" / "report.txt")
    plan = _resolve(text, [found])
    assert [a.tool for a in plan.actions] == [tool] and plan.actions[0].args[key] == found


def test_copy_goes_to_the_real_documents_folder():
    plan = _resolve("copy report.txt to documents", [str(__import__("pathlib").Path.home() / "x" / "report.txt")])
    assert plan.actions[0].args["destination"].endswith("Documents")


@pytest.mark.parametrize("text", ["copy report.txt to documents", "rename report.txt to final.txt"])
def test_several_matches_or_none_ask_instead_of_changing_a_file(text):
    several = _resolve(text, ["C:/a/report.txt", "C:/b/report.txt"])
    none = _resolve(text, [])
    assert isinstance(several, Plan) and not several.actions and several.note
    assert isinstance(none, Plan) and not none.actions and none.note


def test_reading_the_only_match_needs_no_question():
    assert _resolve("read notes.txt", ["C:/a/notes.txt"]).actions[0].tool == "read_text_file"


# ------------------------------------------------------------------------------------------------ show_desktop in the tool
def test_show_desktop_step_needs_no_target_and_is_low_risk():
    tool = ToolRegistry().get("control_desktop")
    args = tool.validate_args({"steps": [{"action": "show_desktop"}]})
    assert tool.risk_for_args(args) == RiskLevel.LOW
    assert tool.risk_for_user_command(args, "show desktop") == RiskLevel.LOW


def test_other_steps_still_need_a_target_and_stay_high_risk():
    tool = ToolRegistry().get("control_desktop")
    with pytest.raises(Exception):
        tool.validate_args({"steps": [{"action": "click", "x": 1, "y": 1}]})
    with pytest.raises(Exception):
        tool.validate_args({"steps": [{"action": "show_desktop"}, {"action": "close_window"}]})   # a close still needs its target
    assert tool.risk_for_args(tool.validate_args({"target_window": "Notes", "steps": [{"action": "close_window"}]})) == RiskLevel.HIGH


def test_show_desktop_presses_win_d_only_when_the_desktop_is_not_already_showing(monkeypatch):
    import sys
    import types
    pressed = []
    fake = types.SimpleNamespace(FAILSAFE=True, hotkey=lambda *keys: pressed.append(keys))
    monkeypatch.setitem(sys.modules, "pyautogui", fake)
    tool = ToolRegistry().get("control_desktop")
    args = tool.validate_args({"steps": [{"action": "show_desktop"}]})
    monkeypatch.setattr(desktop, "_desktop_in_front", lambda: False)
    result = tool.execute(args)
    assert result.success and pressed == [("win", "d")]
    pressed.clear()
    monkeypatch.setattr(desktop, "_desktop_in_front", lambda: True)
    result = tool.execute(args)
    assert result.success and pressed == [] and result.output["completed_steps"][0]["already_showing"] is True


def test_show_desktop_is_verified_from_the_real_foreground_window(monkeypatch):
    tool = ToolRegistry().get("control_desktop")
    args = tool.validate_args({"steps": [{"action": "show_desktop"}]})
    from app.tools.base import ToolResult
    result = ToolResult(success=True, output={"completed_steps": [{"action": "show_desktop", "already_showing": False}]})
    monkeypatch.setattr(desktop, "_desktop_in_front", lambda: False)
    assert tool.verify(args, result).passed is False
    monkeypatch.setattr(desktop, "_desktop_in_front", lambda: True)
    assert tool.verify(args, result).passed is True


# ------------------------------------------------------------------------------------------------ an e-mail address in a sentence
@pytest.mark.parametrize("text", [
    "draft an email to zainujutt00@gmail.com asking for help in study",
    "zainujutt00@gmail.com ko email draft karo study mein help ke liye",
    "write a mail to sara@example.com about the lab",
])
def test_a_sentence_with_an_email_address_is_a_command_not_noise(text):
    from app.voice.junk import junk_reason
    assert junk_reason(text) is None


@pytest.mark.parametrize("text", ["zainujutt00@gmail.com", "www.example.com", "subtitles by example.com"])
def test_a_bare_address_is_still_noise(text):
    from app.voice.junk import junk_reason
    assert junk_reason(text) is not None


# ------------------------------------------------------------------------------------------------ "draft an email to a@gmail.com asking for help in study"
@pytest.mark.parametrize("text,purpose", [
    ("draft an email to zainujutt00@gmail.com asking for help in study", "help in study"),
    ("email draft karo zainujutt00@gmail.com ko study mein help ke liye", "study mein help ke liye"),
    ("zainujutt00@gmail.com ko email likho ke mujhe study mein help chahiye", "mujhe study mein help chahiye"),
])
def test_an_email_address_is_the_recipient_and_the_rest_is_the_subject(text, purpose):
    from app.orchestration import mail_flow
    assert mail_flow.parse_start(text) == (True, "zainujutt00@gmail.com")
    assert mail_flow.address_and_purpose(text) == ("zainujutt00@gmail.com", purpose)


@pytest.mark.parametrize("text,name", [("write an email to Ali", "Ali"), ("Ali ko email bhejo", "Ali"), ("email ali", "ali")])
def test_a_plain_name_is_still_a_name(text, name):
    from app.orchestration import mail_flow
    assert mail_flow.parse_start(text) == (True, name)
    assert mail_flow.address_and_purpose(text) == ("", "")


# ------------------------------------------------------------------------------------------------ Gmail's compose window
def test_gmail_compose_url_fills_the_fields_and_cannot_send():
    from urllib.parse import parse_qs, urlsplit
    from app.mail.compose import gmail_compose_url
    url = gmail_compose_url("zainujutt00@gmail.com", "Help in study", "Dear Zainu,\nI need help & advice.")
    parts = urlsplit(url)
    assert parts.netloc == "mail.google.com" and parse_qs(parts.query)["view"] == ["cm"]
    q = parse_qs(parts.query)
    assert q["to"] == ["zainujutt00@gmail.com"] and q["su"] == ["Help in study"] and q["body"] == ["Dear Zainu,\nI need help & advice."]
    assert "send" not in parts.query.casefold()


def test_the_compose_window_plan_for_an_address(monkeypatch):
    from app.mail import compose
    monkeypatch.setattr(compose, "write_body", lambda purpose, settings, db=None: ("Dear Zainu, I need help with my study.", ""))
    plan = pc.gmail_draft_plan("draft an email to zainujutt00@gmail.com asking for help in study")
    action = plan.actions[0]
    assert action.tool == "open_url" and action.args["new_tab"] is True
    assert "to=zainujutt00%40gmail.com" in action.args["url"] or "to=zainujutt00@gmail.com" in action.args["url"]
    assert "su=Help%20in%20study" in action.args["url"] and "body=Dear%20Zainu" in action.args["url"]


def test_without_cloud_text_the_window_still_opens_with_address_and_subject(monkeypatch):
    from app.mail import compose
    monkeypatch.setattr(compose, "write_body", lambda purpose, settings, db=None: ("", "turn on cloud answers"))
    plan = pc.gmail_draft_plan("email draft karo zainujutt00@gmail.com ko study mein help ke liye")
    assert "su=Study%20mein%20help%20ke%20liye" in plan.actions[0].args["url"] and "body=" not in plan.actions[0].args["url"]
    assert "turn on cloud answers" in plan.note


@pytest.mark.parametrize("text", ["write an email to Ali", "Ali ko email bhejo", "open gmail", "send zainujutt00@gmail.com the report", "zainujutt00@gmail.com"])
def test_no_compose_window_without_an_email_command_and_an_address(text):
    assert pc.gmail_draft_plan(text) is None


def test_the_dictation_flow_leaves_address_commands_to_the_compose_window(db):
    """With an address in the sentence mail_flow returns None (so local_agent opens Gmail); with a name it still starts the dictation flow."""
    from app.config import get_settings
    from app.orchestration import executor, mail_flow
    task = executor.create_task(db, "draft an email to zainujutt00@gmail.com asking for help in study")
    assert mail_flow.try_handle(db, task, task.command, None, get_settings()) is None
    task = executor.create_task(db, "write an email to Ali")
    assert mail_flow.try_handle(db, task, task.command, None, get_settings()) is not None


def test_body_is_empty_with_a_reason_when_cloud_answers_are_off(db):
    from app.mail.compose import write_body
    from app.preferences import get_preferences
    assert get_preferences(db).cloud_answers is not True
    body, why = write_body("help in study", None, db)
    assert body == "" and "cloud answers" in why


@pytest.mark.parametrize("address", ["uzma.kiran@riphah.edu.pk", "a.b.c@mail.example.com", "zainujutt00@gmail.com"])
def test_an_address_with_dots_in_the_name_is_still_the_recipient(address):
    from app.orchestration import mail_flow
    text = f"draft an email to {address} asking my supervisor to review my FYP report"
    assert mail_flow.parse_start(text) == (True, address)
    assert mail_flow.address_and_purpose(text) == (address, "my supervisor to review my FYP report")
    plan = pc.gmail_draft_plan(text)
    assert plan is not None and plan.actions[0].tool == "open_url"


def test_gmail_compose_window_titles_count_as_the_site():
    from app.tools.apps import _site_title_hints
    hints = _site_title_hints("https://mail.google.com/mail/?view=cm&fs=1&to=a@b.com")
    assert any(h in "compose mail - me@gmail.com - gmail - google chrome" for h in hints)
    assert any(h in "mail.google.com/mail/?view=cm&fs=1 - google chrome" for h in hints)

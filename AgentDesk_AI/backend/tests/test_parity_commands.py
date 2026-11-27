"""P1 of docs/STONIC_PARITY_PLAN.md: local parsers for the sentences that went to the cloud in all three languages.

Every positive case is the English / Roman Urdu / Hindi sentence of a row in scripts/coverage_rows.py (plus variants); every parser also has
negative cases, because a new parser that misroutes is worse than a missing one.
"""
from __future__ import annotations

from pathlib import Path

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
                                  "open notes.txt", "read my mind"])
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


# ------------------------------------------------------------------------------------------------ screenshots are saved where the user looks
def test_screenshot_default_folder_is_pictures_not_the_hidden_test_folder(tmp_path):
    from pathlib import Path
    from app.tools.base import ToolContext
    from app.tools.system import TakeScreenshotTool
    tool = TakeScreenshotTool(ToolContext(allowed_directories=[Path.home()], test_dir=tmp_path))
    assert tool._default_path().parent == Path.home() / "Pictures" / "AgentDesk Screenshots"


def test_screenshot_falls_back_to_the_test_folder_when_pictures_is_not_allowed(tmp_path):
    from app.tools.base import ToolContext
    from app.tools.system import TakeScreenshotTool
    tool = TakeScreenshotTool(ToolContext(allowed_directories=[tmp_path], test_dir=tmp_path))
    assert tool._default_path().parent == tmp_path / "screenshots"


# ------------------------------------------------------------------------------------------------ "FIP folder" means FYP
@pytest.mark.parametrize("heard,meant", [("fip", "fyp"), ("FIP", "fyp"), ("fib", "fyp"), ("f y p", "fyp"), ("एफ आई पी", "fyp"), ("devpos", None)])
def test_mis_heard_names_get_sound_alike_variants(heard, meant):
    variants = pc.spoken_variants(heard)
    assert (meant in variants) if meant else variants == []


def test_long_or_odd_names_get_no_variants():
    assert pc.spoken_variants("my semester six lecture notes") == [] and pc.spoken_variants("") == []


class _OnlyFyp(_FakeFindPaths):
    def execute(self, args):
        from app.tools.base import ToolResult
        found = ["E:/fyp"] if args["name"].casefold() == "fyp" else []
        return ToolResult(success=True, output={"candidates": found, "exact": bool(found), "confident": bool(found)})


class _OnlyFypRegistry(_FakeRegistry):
    def __init__(self):
        self.tool = _OnlyFyp([])


def test_open_fip_folder_opens_the_fyp_folder_and_says_so():
    intent = {"op": "open", "kind": "folder", "source": "fip"}
    plan = local_agent._resolve(_Task(), intent, _OnlyFypRegistry())
    assert plan.actions[0].tool == "open_folder" and plan.actions[0].args["path"] == "E:/fyp".replace("/", "\\") or plan.actions[0].args["path"] == "E:/fyp"
    assert "fyp" in plan.note.casefold() and "fip" in plan.note.casefold()


def test_a_guessed_spelling_never_deletes_without_asking():
    intent = {"op": "delete", "kind": "folder", "source": "fip", "include_contents": False}
    plan = local_agent._resolve(_Task(), intent, _OnlyFypRegistry())
    assert not plan.actions and "fyp" in plan.note.casefold()


def test_an_exact_name_is_not_rewritten():
    intent = {"op": "open", "kind": "folder", "source": "fyp"}
    plan = local_agent._resolve(_Task(), intent, _OnlyFypRegistry())
    assert plan.actions and "samjha" not in (plan.note or "")


# ------------------------------------------------------------------------------------------------ delete: noun after the name, "is zip" means IS.zip
@pytest.mark.parametrize("text,source,kind", [
    ("delete is zip folder", "is.zip", "file"),
    ("delete IS dot zip", "IS.zip", "file"),
    ("delete notes.txt", "notes.txt", "file"),
    ("delete the old photos folder", "old photos", "folder"),
    ("report.txt delete karo", "report.txt", "file"),
    ("photos folder delete karo", "photos", "folder"),
    ("report.txt डिलीट करो", "report.txt", "file"),
])
def test_delete_sentences_become_a_delete_workflow(text, source, kind):
    intent = pc.parity_intent(text)
    assert intent is not None and intent["op"] == "delete" and intent["kind"] == kind
    assert intent["source"].casefold() == source.casefold() and intent["include_contents"] is False


@pytest.mark.parametrize("text", ["delete it", "delete this", "delete everything", "delete all files", "delete", "delete that file"])
def test_delete_never_guesses_what_it_or_everything_means(text):
    assert pc.parity_intent(text) is None


def test_delete_of_a_found_zip_still_needs_the_approval_card():
    plan = _resolve("delete is zip folder", ["E:/7th sem/IS.zip"])
    assert [a.tool for a in plan.actions] == ["delete_file"]
    from app.tools.registry import ToolRegistry
    tool = ToolRegistry().get("delete_file")
    assert tool.risk_for_args(tool.validate_args(plan.actions[0].args)).value in {"high", "medium"}


@pytest.mark.parametrize("text", ["Deleted IS zip folder", "deleting is zip folder", "removed notes.txt", "Delete IS zip folder."])
def test_delete_is_understood_when_speech_to_text_changes_the_tense(text):
    intent = pc.parity_intent(text)
    assert intent is not None and intent["op"] == "delete"


@pytest.mark.parametrize("heard,fixed", [
    ("Turn of Bluetooth", "Turn off Bluetooth"), ("switch of wifi", "switch off wifi"), ("Bluetooth of", "Bluetooth off"),
    ("wi-fi of", "wi-fi off"), ("turn off bluetooth", "turn off bluetooth"), ("the turn of events", "the turn of events"), ("kitchen of", "kitchen of"),
])
def test_of_is_heard_for_off_only_on_device_commands(heard, fixed):
    from app.ai.speech_commands import fix_misheard
    assert fix_misheard(heard) == fixed


# ------------------------------------------------------------------------------------------------ closing by a SIMILAR name, with the user's yes
def test_similar_window_titles_are_found_for_a_mis_heard_name():
    from app.ai.window_commands import similar_titles
    titles = ["diagrams - File Explorer", "Calculator", "AgentDesk AI - Google Chrome", "DevOps - File Explorer"]
    assert similar_titles("diagramms", titles) == ["diagrams - File Explorer"]
    assert similar_titles("devops", titles)[:1] == ["DevOps - File Explorer"]
    assert similar_titles("zzzz", titles) == [] and similar_titles("ab", titles) == []


class _Windows:
    def __init__(self, titles):
        self.titles = titles

    def validate_args(self, args):
        return args

    def execute(self, args):
        from app.tools.base import ToolResult
        return ToolResult(success=True, output={"completed_steps": [{"action": "inspect", "open_windows": self.titles, "windows": []}]})


class _WindowRegistry:
    def __init__(self, titles):
        self.tool = _Windows(titles)

    def get(self, name):
        return self.tool


def test_a_near_identical_window_name_is_closed_without_a_question():
    from app.ai.window_commands import window_plan
    plan = window_plan(_Task(), _WindowRegistry(["diagrams - File Explorer", "Calculator"]), "diagramms folder close")
    assert plan.actions and plan.actions[0].args["target_window"] == "diagrams - File Explorer" and plan.actions[0].confirm is False


def test_a_looser_window_name_closes_only_through_the_approval_popup():
    from app.ai.window_commands import window_plan
    plan = window_plan(_Task(), _WindowRegistry(["DevOps - File Explorer", "Calculator"]), "devopz folder close")
    assert plan.actions and plan.actions[0].confirm is True
    assert plan.actions[0].args["target_window"] == "DevOps - File Explorer" and "Approve" in plan.note


def test_several_look_alike_windows_are_chosen_by_number():
    import json
    from app.ai.window_commands import window_plan
    task = _Task()
    plan = window_plan(task, _WindowRegistry(["lab one - File Explorer", "lab two - File Explorer"]), "lab folder close")
    assert not plan.actions and len(json.loads(task.agent_state_json)["window_choices"]) == 2


def test_haan_confirms_the_single_guess_and_a_number_picks_one():
    import json
    from types import SimpleNamespace
    state = json.dumps({"provider": "local", "window_choices": ["diagrams - File Explorer"]})
    original = SimpleNamespace(agent_state_json=state, actions=[], command="diagramms folder close")
    for reply in ("haan", "yes", "1"):
        registry = SimpleNamespace(ctx=SimpleNamespace(discovery_directories=[], allowed_directories=[]))
        plan = local_agent.correction_plan(_Task(), original, reply, registry)
        assert plan is not None and plan.actions[0].args["target_window"] == "diagrams - File Explorer"
        assert plan.actions[0].args["steps"] == [{"action": "close_window"}]


def test_an_exact_named_window_is_still_closed_directly():
    from app.ai.window_commands import window_plan
    plan = window_plan(_Task(), _WindowRegistry(["diagrams - File Explorer"]), "close diagrams folder")
    assert plan.actions and plan.actions[0].args["target_window"] == "diagrams - File Explorer"


def test_which_youtube_tab_is_answered_by_number():
    import json
    from types import SimpleNamespace
    from app.ai.clarify_answers import browser_answer
    tabs = [{"id": 11, "title": "Lo Maan Liya Humne"}, {"id": 22, "title": "GUZARISH - SATINDER"}]
    action = SimpleNamespace(tool_name="control_browser", status="failed", args_json=json.dumps({"action": "close", "target": "youtube"}),
                             result_json=json.dumps({"success": False, "output": {"candidates": tabs, "needs_confirmation": True}}))
    original = SimpleNamespace(actions=[action])
    plan = browser_answer(original, "2")
    assert plan.actions[0].args == {"action": "close", "target": "youtube", "tab_id": 22}
    assert browser_answer(original, "guzarish").actions[0].args["tab_id"] == 22
    assert browser_answer(original, "something else") is None


# ------------------------------------------------------------------------------------------------ "close my drive tab": a similar tab is offered, never closed on a guess
def test_similar_tabs_say_whether_the_user_plainly_meant_them():
    from app.tools.browser import similar_tabs
    tabs = [{"id": 1, "title": "My Drive - Google Drive"}, {"id": 2, "title": "AgentDesk AI"}, {"id": 3, "title": "GUZARISH - SATINDER"}]
    assert [(t["id"], plain) for t, plain in similar_tabs(tabs, "my drive")] == [(1, True)]
    assert [(t["id"], plain) for t, plain in similar_tabs(tabs, "google drive")] == [(1, True)]
    assert [(t["id"], plain) for t, plain in similar_tabs(tabs, "guzarish")] == [(3, True)]
    assert [(t["id"], plain) for t, plain in similar_tabs(tabs, "agentdesc")] == [(2, False)]
    assert similar_tabs(tabs, "calendar") == [] and similar_tabs(tabs, "") == [] and similar_tabs(tabs, "a") == []


def test_a_single_guessed_tab_needs_a_yes_and_then_runs_on_that_tab_id():
    import json
    from types import SimpleNamespace
    from app.ai.clarify_answers import browser_answer
    action = SimpleNamespace(tool_name="control_browser", status="failed", args_json=json.dumps({"action": "close", "target": "my drive"}),
                             result_json=json.dumps({"success": False, "output": {"candidates": [{"id": 7, "title": "My Drive - Google Drive"}], "needs_confirmation": True}}))
    original = SimpleNamespace(actions=[action])
    for reply in ("haan", "yes", "1"):
        assert browser_answer(original, reply).actions[0].args == {"action": "close", "target": "my drive", "tab_id": 7}
    assert browser_answer(original, "no") is None and browser_answer(original, "nahi") is None


# ------------------------------------------------------------------------------------------------ the Approve / Reject popup for a guess
def test_a_plan_action_marked_confirm_always_waits_for_the_popup(db):
    from app.ai.base import Plan, PlanAction
    from app.config import get_settings
    from app.orchestration import executor
    registry = ToolRegistry()
    asked = executor.plan_task(db, executor.create_task(db, "show what I deleted"), registry, get_settings(),
                               preplanned=Plan(actions=[PlanAction(tool="list_trash", args={}, confirm=True)]))
    assert asked.status == "awaiting_approval" and asked.actions[0].status == "pending" and asked.actions[0].risk == "medium"
    plain = executor.plan_task(db, executor.create_task(db, "show what I deleted"), registry, get_settings(),
                               preplanned=Plan(actions=[PlanAction(tool="list_trash", args={})]))
    assert plain.status != "awaiting_approval"


def _tab_world(monkeypatch):
    from app.browser_bridge import bridge
    tabs = [{"id": 5, "title": "AgentDesk AI", "url": "http://127.0.0.1:8000/", "active": True, "audible": False}]
    asked = []

    def request(action, **kwargs):
        asked.append(action)
        if action == "close":
            tabs.clear()                                         # the tab is really gone afterwards (the tool re-reads the list to verify)
        return {"success": True, "tabs": list(tabs)} if action == "inspect" else {"success": True, "closed": True}

    monkeypatch.setattr(bridge, "request", request)
    return asked


def test_a_plainly_named_tab_is_closed_and_a_looser_spelling_is_only_offered(monkeypatch):
    from app.tools.base import ToolContext
    from app.tools.browser import BrowserControlTool
    asked = _tab_world(monkeypatch)
    tool = BrowserControlTool(ToolContext.from_settings())
    assert tool.execute(tool.validate_args({"action": "close", "target": "agentdesk"})).success and "close" in asked
    asked = _tab_world(monkeypatch)                              # a fresh browser: the first test closed its tab
    offered = tool.execute(tool.validate_args({"action": "close", "target": "agentdesc"}))
    assert not offered.success and offered.output["guess"]["id"] == 5 and "close" not in asked


def test_a_guessed_tab_becomes_a_pending_close_with_the_real_tab_id(db, monkeypatch):
    from app.ai.base import Plan, PlanAction
    from app.config import get_settings
    from app.orchestration import executor
    asked = _tab_world(monkeypatch)
    registry = ToolRegistry()
    task = executor.plan_task(db, executor.create_task(db, "close agentdesc tab"), registry, get_settings(),
                              preplanned=Plan(actions=[PlanAction(tool="control_browser", args={"action": "close", "target": "agentdesc"})]))
    task = executor.run_task(db, task.id, registry, get_settings())
    assert task.status == "awaiting_approval" and "AgentDesk AI" in task.plan_note
    pending = [a for a in task.actions if a.status == "pending"]
    assert len(pending) == 1 and pending[0].risk == "medium" and '"tab_id": 5' in pending[0].args_json
    assert "close" not in asked                                   # nothing was closed before the user approves
    approved = executor.approve_task(db, task.id, [pending[0].id])
    done = executor.run_task(db, approved.id, registry, get_settings())
    assert "close" in asked and done.actions[-1].status == "succeeded"


# ------------------------------------------------------------------------------------------------ "close gmail" with two Gmail tabs open: both are closed
@pytest.mark.parametrize("text,target", [
    ("close gmail", "gmail"), ("close gmail tab", "gmail"), ("close gmail tabs", "gmail"), ("close the gmail tabs", "gmail"), ("close both gmail tabs", "gmail"),
    ("close all gmail tabs", "gmail"), ("gmail tab band karo", "gmail"), ("gmail ke tabs band karo", "gmail"), ("gmail ke dono tab band karo", "gmail"),
    ("sab gmail tab band kar do", "gmail"), ("जीमेल के टैब बंद करो", "gmail"), ("जीमेल टैब बंद करो", "gmail"),
    ("close youtube", "youtube"), ("close all youtube tabs", "youtube"), ("youtube band karo", "youtube"),
    ("close my drive tab", "drive"), ("close google drive", "google drive"), ("close example domain tab", "example domain"),
])
def test_close_tab_sentences_name_the_tabs_not_the_quantity(text, target):
    from app.ai.browser_commands import browser_plan
    plan = browser_plan(text)
    assert plan is not None and plan.actions[0].args == {"action": "close", "target": target}


def _browser(monkeypatch, tabs):
    """A fake browser: close removes the tab, inspect lists what is open."""
    from app.browser_bridge import bridge
    log = []

    def request(action, **kwargs):
        if action == "inspect":
            return {"success": True, "tabs": [dict(t) for t in tabs]}
        if action == "close":
            log.append(kwargs["tab_id"])
            tabs[:] = [t for t in tabs if t["id"] != kwargs["tab_id"]]
            return {"success": True, "closed": True}
        return {"success": False, "error": "not used"}

    monkeypatch.setattr(bridge, "request", request)
    return log


def _open_tabs():
    def tab(i, title, url):
        return {"id": i, "title": title, "url": url, "active": False, "audible": False}
    return [tab(1, "Inbox (567) - me@gmail.com - Gmail", "https://mail.google.com/mail/u/0/"), tab(2, "Inbox (567) - me@gmail.com - Gmail", "https://mail.google.com/mail/u/0/"),
            tab(3, "Lo Maan Liya Humne - YouTube", "https://www.youtube.com/watch"), tab(4, "GUZARISH - YouTube", "https://www.youtube.com/watch"),
            tab(5, "My Drive - Google Drive", "https://drive.google.com/drive/my-drive"), tab(6, "AgentDesk AI", "http://127.0.0.1:8000/"),
            tab(7, "N4bih4/fyp", "https://github.com/N4bih4/fyp")]


def _close(monkeypatch, target):
    from app.tools.base import ToolContext
    from app.tools.browser import BrowserControlTool
    tabs = _open_tabs()
    log = _browser(monkeypatch, tabs)
    tool = BrowserControlTool(ToolContext.from_settings())
    args = tool.validate_args({"action": "close", "target": target})
    result = tool.execute(args)
    return tool, args, result, log, tabs


@pytest.mark.parametrize("target,closed", [
    ("gmail", {1, 2}), ("youtube", {3, 4}), ("drive", {5}), ("my drive", {5}), ("google drive", {5}), ("github", {7}),
    ("gmial", {1, 2}), ("yutube", {3, 4}), ("gogle drive", {5}), ("githb", {7}), ("agentdesk", {6}), ("guzarish", {4}), ("inbox", {1, 2}),
])
def test_every_tab_that_plainly_matches_the_name_is_closed_without_a_question(monkeypatch, target, closed):
    tool, args, result, log, tabs = _close(monkeypatch, target)
    assert result.success and set(log) == closed
    assert tool.verify(args, result).passed is True
    assert {t["id"] for t in tabs}.isdisjoint(closed)


@pytest.mark.parametrize("target", ["jimail", "agentdesc"])
def test_a_looser_spelling_is_never_closed_without_the_popup(monkeypatch, target):
    tool, args, result, log, tabs = _close(monkeypatch, target)
    assert not result.success and result.output["needs_confirmation"] is True and log == []


@pytest.mark.parametrize("target", ["calendar", "netflix", "zzzz"])
def test_a_name_nothing_looks_like_closes_nothing(monkeypatch, target):
    tool, args, result, log, tabs = _close(monkeypatch, target)
    assert not result.success and log == [] and len(tabs) == 7


def test_closing_several_tabs_never_includes_this_apps_own_tab(monkeypatch):
    from app.tools.base import ToolContext
    from app.tools.browser import BrowserControlTool
    tabs = [{"id": 1, "title": "Gmail helper", "url": "https://mail.google.com/", "active": False, "audible": False},
            {"id": 2, "title": "AgentDesk Gmail", "url": "http://127.0.0.1:8000/", "active": True, "audible": False},
            {"id": 3, "title": "Gmail", "url": "https://mail.google.com/mail/u/1/", "active": False, "audible": False}]
    log = _browser(monkeypatch, tabs)
    tool = BrowserControlTool(ToolContext.from_settings())
    result = tool.execute(tool.validate_args({"action": "close", "target": "gmail"}))
    assert result.success and set(log) == {1, 3} and [t["id"] for t in tabs] == [2]


def test_more_than_eight_matching_tabs_ask_instead_of_closing_them_all(monkeypatch):
    from app.tools.base import ToolContext
    from app.tools.browser import BrowserControlTool
    tabs = [{"id": i, "title": f"Video {i} - YouTube", "url": "https://www.youtube.com/watch", "active": False, "audible": False} for i in range(1, 11)]
    log = _browser(monkeypatch, tabs)
    tool = BrowserControlTool(ToolContext.from_settings())
    result = tool.execute(tool.validate_args({"action": "close", "target": "youtube"}))
    assert not result.success and log == [] and len(tabs) == 10


# ------------------------------------------------------------------------------------------------ "open gmail" must not replace the AgentDesk tab
@pytest.mark.parametrize("title,own", [
    ("AgentDesk AI - Google Chrome", True), ("127.0.0.1:8000 - Google Chrome", True), ("agentdesk ai", True),
    ("Inbox (3) - me@gmail.com - Gmail - Google Chrome", False), ("My Drive - Google Drive - Google Chrome", False), ("", False),
])
def test_the_assistants_own_browser_tab_is_recognised(title, own):
    from app.tools.browser_choice import is_this_app
    assert is_this_app(title) is own


def test_navigate_in_place_never_types_into_the_agentdesk_window(monkeypatch):
    from types import SimpleNamespace
    import importlib.util
    from app.tools import browser_choice as stubbed, coding_agent, screen, uia
    # conftest replaces navigate_in_place for every test; load a private copy of the real module to test the real function
    spec = importlib.util.spec_from_file_location("app.tools._browser_choice_real", stubbed.__file__)
    browser_choice = importlib.util.module_from_spec(spec)
    browser_choice.__package__ = "app.tools"
    import sys
    sys.modules[spec.name] = browser_choice                  # dataclasses look the module up by name
    try:
        spec.loader.exec_module(browser_choice)
    finally:
        sys.modules.pop(spec.name, None)
    browser_choice._foreground_title = lambda: "Some Other Page - Google Chrome"      # the test must not depend on what is in front on the machine running it
    typed = []
    window = SimpleNamespace(process="chrome.exe", title="AgentDesk AI - Google Chrome", handle=1)
    service = SimpleNamespace(backend=SimpleNamespace(windows=lambda: [window]), window=lambda _=None: window)
    monkeypatch.setattr(uia, "get_service", lambda: service)
    monkeypatch.setattr(screen, "get_screen", lambda: SimpleNamespace(focus=lambda w: None))
    monkeypatch.setattr(coding_agent, "press", lambda *keys: typed.append(keys))
    monkeypatch.setattr(coding_agent, "set_clipboard", lambda text: typed.append(text))
    monkeypatch.setattr(coding_agent, "get_clipboard", lambda: "")
    chrome = SimpleNamespace(key="chrome")
    assert browser_choice.navigate_in_place(chrome, "https://mail.google.com") is False and typed == []
    window.title = "Some Other Page - Google Chrome"
    assert browser_choice.navigate_in_place(chrome, "https://mail.google.com") is True and typed      # other pages still use the one-window behaviour


# ------------------------------------------------------------------------------------------------ a slow app (Word) that closes 2 seconds after the request is a SUCCESS
def test_a_window_that_closes_after_a_couple_of_seconds_is_not_reported_as_still_open(monkeypatch):
    clock = {"now": 0.0}
    monkeypatch.setattr(desktop.time, "sleep", lambda seconds: clock.__setitem__("now", clock["now"] + seconds))
    monkeypatch.setattr(desktop.DesktopControlTool, "_window_is_open", classmethod(lambda cls, window, title, pyautogui: clock["now"] < 2.0))
    assert desktop.DesktopControlTool._wait_until_closed(object(), "Document1 - Word", None, 6.0) is False
    assert 2.0 <= clock["now"] < 2.5                               # it stopped waiting as soon as the window was gone


def test_a_window_that_never_closes_is_still_reported_after_the_wait(monkeypatch):
    clock = {"now": 0.0}
    monkeypatch.setattr(desktop.time, "sleep", lambda seconds: clock.__setitem__("now", clock["now"] + seconds))
    monkeypatch.setattr(desktop.DesktopControlTool, "_window_is_open", classmethod(lambda cls, window, title, pyautogui: True))
    assert desktop.DesktopControlTool._wait_until_closed(object(), "Unsaved - Word", None, 6.0) is True
    assert 6.0 <= clock["now"] <= 6.5


def test_closing_word_after_a_slow_shutdown_succeeds_end_to_end(monkeypatch):
    """The whole close step: the request is posted, the window is still there at first, gone after 2 s, and Alt+F4 is never needed."""
    import sys
    import types
    clock = {"now": 0.0}
    monkeypatch.setattr(desktop.time, "sleep", lambda seconds: clock.__setitem__("now", clock["now"] + seconds))
    window = types.SimpleNamespace(title="Document1 - Word", _hWnd=77)
    fake = types.SimpleNamespace(FAILSAFE=True, getAllWindows=lambda: [window] if clock["now"] < 2.0 else [], getActiveWindow=lambda: window)
    monkeypatch.setitem(sys.modules, "pyautogui", fake)
    tool = ToolRegistry().get("control_desktop")
    hotkeys = []
    monkeypatch.setattr(desktop.DesktopControlTool, "_resolve_window", classmethod(lambda cls, pg, title: window))
    monkeypatch.setattr(desktop.DesktopControlTool, "_request_window_close", classmethod(lambda cls, w: True))
    monkeypatch.setattr(desktop.DesktopControlTool, "_hotkey_on_target", classmethod(lambda cls, w, pg, *keys: hotkeys.append(keys) or False))
    monkeypatch.setattr(desktop.DesktopControlTool, "_window_is_open", classmethod(lambda cls, w, title, pg: clock["now"] < 2.0))
    monkeypatch.setattr(desktop.DesktopControlTool, "_window_metadata", classmethod(lambda cls, w: {"pid": 1}))
    monkeypatch.setattr(desktop.DesktopControlTool, "_window_hwnd", classmethod(lambda cls, w: 77))
    args = tool.validate_args({"target_window": "Document1 - Word", "steps": [{"action": "close_window"}]})
    result = tool.execute(args)
    assert result.success, result.error
    assert hotkeys == []                                            # nothing was pressed: the close request alone was enough
    assert result.output["completed_steps"][0]["closed"] is True


# ------------------------------------------------------------------------------------------------ "open World" means Word: near spellings open, doubtful ones ask through the popup
def _app_tool(monkeypatch, labels):
    from pathlib import Path
    from app.tools.apps import OpenApplicationTool
    from app.tools.base import ToolContext
    tool = OpenApplicationTool(ToolContext.from_settings())
    monkeypatch.setattr(tool, "_start_menu_shortcuts", lambda: [Path(f"{label}.lnk") for label in labels])
    return tool


START_MENU = ["Word 2016", "WinRAR help", "WinRAR", "Readme", "Visual Studio Code", "Excel 2016", "PowerPoint 2016", "Google Chrome", "Notepad"]


@pytest.mark.parametrize("heard,opens", [
    ("world", "Word 2016"), ("word", "Word 2016"), ("wurd", "Word 2016"), ("excell", "Excel 2016"), ("exel", "Excel 2016"),
    ("power point", "PowerPoint 2016"), ("note pad", "Notepad"),
])
def test_a_near_spelling_of_an_installed_app_opens_that_app(monkeypatch, heard, opens):
    tool = _app_tool(monkeypatch, START_MENU)
    found = tool._match_start_menu_shortcut(heard)
    assert found is not None and found.stem == opens


def test_an_unrelated_name_does_not_open_a_guess(monkeypatch):
    tool = _app_tool(monkeypatch, START_MENU)
    assert tool._match_start_menu_shortcut("zzqqxx") is None


def test_one_clearly_best_doubtful_app_is_offered_not_opened(monkeypatch):
    from pathlib import Path
    tool = _app_tool(monkeypatch, START_MENU)
    monkeypatch.setattr(tool, "_rank_start_menu_shortcuts", lambda name: [(0.55, [Path("Word 2016.lnk")]), (0.30, [Path("WinRAR.lnk")])])
    assert tool._best_app_guess("zork") == "Word 2016"
    monkeypatch.setattr(tool, "_rank_start_menu_shortcuts", lambda name: [(0.55, [Path("Word 2016.lnk")]), (0.52, [Path("WinRAR.lnk")])])
    assert tool._best_app_guess("zork") is None                      # two look alike: the user picks from a list
    monkeypatch.setattr(tool, "_rank_start_menu_shortcuts", lambda name: [(0.40, [Path("Word 2016.lnk")])])
    assert tool._best_app_guess("zork") is None                      # too weak to even suggest


def test_a_doubtful_app_name_becomes_an_approve_popup_with_the_real_app_name(db, monkeypatch):
    from pathlib import Path
    from app.ai.base import Plan, PlanAction
    from app.config import get_settings
    from app.orchestration import executor
    from app.tools.apps import OpenApplicationTool
    registry = ToolRegistry()
    tool = registry.get("open_application")
    monkeypatch.setattr(OpenApplicationTool, "_find_executable", lambda self, app: None)
    monkeypatch.setattr(OpenApplicationTool, "_activate_running_app", lambda self, app: None)
    monkeypatch.setattr(OpenApplicationTool, "_match_start_menu_shortcut", lambda self, app: None)
    monkeypatch.setattr(OpenApplicationTool, "_rank_start_menu_shortcuts", lambda self, name: [(0.55, [Path("Word 2016.lnk")]), (0.30, [Path("WinRAR.lnk")])])
    task = executor.plan_task(db, executor.create_task(db, "open zorkword"), registry, get_settings(),
                              preplanned=Plan(actions=[PlanAction(tool="open_application", args={"app_name": "zorkword"})]))
    if task.status == "awaiting_approval":                          # the tool's own risk may already ask first; approve that one
        task = executor.approve_task(db, task.id, [a.id for a in task.actions if a.status == "pending"])
    task = executor.run_task(db, task.id, registry, get_settings())
    assert task.status == "awaiting_approval" and "Word 2016" in task.plan_note
    pending = [a for a in task.actions if a.status == "pending"]
    assert len(pending) == 1 and '"app_name": "Word 2016"' in pending[0].args_json and pending[0].risk in {"medium", "high"}


# ------------------------------------------------------------------------------------------------ "close Axel 316" / "کلوز ایکسل" / "close exsel" all mean Excel
@pytest.mark.parametrize("spoken", ["Axel 316", "axel", "exel", "Excell", "exsel", "एक्सेल", "ایکسل", "microsoft excel", "ms-excel", "Excel 316", "Excel"])
def test_every_spoken_form_of_excel_closes_the_excel_window(spoken):
    from app.ai.window_commands import window_plan
    plan = window_plan(_Task(), _WindowRegistry(["Book1 - Excel", "AgentDesk AI - Google Chrome"]), f"close {spoken}")
    assert plan.actions and plan.actions[0].args["target_window"] == "Book1 - Excel", spoken


@pytest.mark.parametrize("spoken,title", [("world", "Document1 - Word"), ("Ward 12", "Document1 - Word"), ("वर्ड", "Document1 - Word"), ("ورڈ", "Document1 - Word"),
                                           ("power point", "Presentation1 - PowerPoint"), ("پاور پوائنٹ", "Presentation1 - PowerPoint")])
def test_word_and_powerpoint_in_any_spelling_or_script(spoken, title):
    from app.ai.window_commands import window_plan
    plan = window_plan(_Task(), _WindowRegistry([title, "Calculator"]), f"close {spoken}")
    assert plan.actions and plan.actions[0].args["target_window"] == title, spoken


def test_spoken_app_name_drops_the_numbers_speech_to_text_appends():
    from app.ai.window_commands import spoken_app_name
    assert spoken_app_name("Axel 316") == "excel" and spoken_app_name("316") == "316" and spoken_app_name("Notepad 2") == "Notepad"


# ------------------------------------------------------------------------------------------------ websites by name or by address
@pytest.mark.parametrize("text,url", [
    ("open facebook", "https://www.facebook.com"), ("facebook kholo", "https://www.facebook.com"), ("open the facebook website", "https://www.facebook.com"),
    ("open instagram", "https://www.instagram.com"), ("go to linkedin", "https://www.linkedin.com"), ("visit google", "https://google.com"),
    ("open J.Website", "https://www.junaidjamshed.com"), ("open j.website", "https://www.junaidjamshed.com"), ("j dot ki website kholo", "https://www.junaidjamshed.com"), ("open j dot website", "https://www.junaidjamshed.com"), ("open j. website", "https://www.junaidjamshed.com"),
    ("open daraz dot pk", "https://daraz.pk"), ("open daraz.pk", "https://daraz.pk"), ("open example.com", "https://example.com"),
])
def test_a_website_named_or_spelled_out_is_opened(text, url):
    plan = pc.parity_plan(text)
    assert plan is not None and plan.actions[0].tool == "open_url" and plan.actions[0].args == {"url": url}


@pytest.mark.parametrize("text", ["open notepad", "open word", "open discord", "open outlook", "open fyp folder", "open report.txt", "open dev ops", "open camera roll", "open my drive"])
def test_apps_folders_and_files_are_not_taken_for_websites(text):
    plan = pc.parity_plan(text)
    assert plan is None or plan.actions[0].tool != "open_url"


# ------------------------------------------------------------------------------------------------ create a folder
@pytest.mark.parametrize("text,name,where", [
    ("create semester six folder", "semester six", ""), ("create a folder called semester six", "semester six", ""), ("make new folder photos", "photos", ""),
    ("create a folder called lab in documents", "lab", "Documents"), ("create lab folder on desktop", "lab", "Desktop"),
    ("lab folder banao", "lab", ""), ("documents mein lab folder banao", "lab", "Documents"), ("लैब फोल्डर बनाओ", "लैब", ""),
])
def test_create_folder_sentences_give_a_name_and_an_optional_place(text, name, where):
    intent = pc.parity_intent(text)
    assert intent == {"op": "create", "name": name, "destination": where}


@pytest.mark.parametrize("text", ["create folder", "new folder", "create it", "create a folder called a/b", "make folder c:x"])
def test_create_needs_a_simple_name(text):
    intent = pc.parity_intent(text)
    assert intent is None or not any(c in intent["name"] for c in "/\\:")


def test_a_folder_with_no_place_named_is_created_in_the_open_folder_or_on_the_desktop(tmp_path, monkeypatch):
    plan = local_agent._resolve(_Task(), {"op": "create", "name": "semester six", "destination": ""}, _FakeRegistry([]))
    assert plan.actions[0].tool == "create_folder" and plan.actions[0].args["path"].endswith("semester six")
    assert "Approve" in plan.note and ("Desktop" in plan.note or "folder" in plan.note)
    explicit = local_agent._resolve(_Task(), {"op": "create", "name": "lab", "destination": "Documents"}, _FakeRegistry([]))
    assert explicit.actions[0].args["path"].endswith("Documents\\lab") and not explicit.note.startswith("'lab' folder Desktop")


def test_deleting_a_folder_moves_it_with_its_contents_to_the_trash_behind_the_approval_card(tmp_path):
    folder = tmp_path / "semester six"
    folder.mkdir()
    (folder / "notes.txt").write_text("x")
    plan = local_agent._resolve(_Task(), {"op": "delete", "kind": "folder", "source": str(folder)}, _FakeRegistry([str(folder)]))
    assert plan.actions[0].tool == "delete_file" and plan.actions[0].args == {"path": str(folder), "include_contents": True}
    tool = ToolRegistry().get("delete_file")
    assert tool.risk_for_args(tool.validate_args(plan.actions[0].args)).value == "high"           # so it always waits for Approve
    file_plan = local_agent._resolve(_Task(), {"op": "delete", "kind": "file", "source": str(folder / "notes.txt")}, _FakeRegistry([]))
    assert file_plan.actions[0].args["include_contents"] is False


# ------------------------------------------------------------------------------------------------ delete / remove, however it was heard
@pytest.mark.parametrize("text", [
    "delete, six folder,", "delete six folder", "Delete, semester six folder.", "dilete six folder", "delet six folder", "delite the six folder", "deleat folder six",
    "dalete six folder", "remove six folder", "removed six folder", "rimoov six folder", "remove folder six", "six folder delete karo", "six folder dilete karo",
    "six folder hata do", "six folder hatao", "six folder mita do", "सिक्स फोल्डर डिलीट करो", "सिक्स फोल्डर हटाओ",
])
def test_every_way_of_saying_delete_or_remove_a_folder_is_the_delete_workflow(text):
    intent = pc.parity_intent(text)
    assert intent is not None and intent["op"] == "delete" and intent["kind"] == "folder"
    assert intent["source"].casefold() in {"six", "semester six", "सिक्स"}


@pytest.mark.parametrize("text", ["delivery six folder", "select six folder", "deliver the six folder", "delete it", "delete everything", "delete all files",
                                  "delete", "remove this", "hata do", "mita do"])
def test_look_alike_verbs_and_unclear_targets_are_never_a_delete(text):
    assert pc.parity_intent(text) is None


@pytest.mark.parametrize("text", ["move six folder to desktop", "move report.txt to documents", "report.txt ko desktop pe move karo", "copy six folder to downloads", "rename six folder to seven",
                                  "remove" , "moved six folder", "mover six folder"])
def test_move_copy_and_rename_are_never_mistaken_for_delete(text):
    intent = pc.parity_intent(text)
    assert intent is None or intent["op"] != "delete"


# ------------------------------------------------------------------------------------------------ what Whisper REALLY wrote for this user's "delete folder"
@pytest.mark.parametrize("text,source", [
    ("Delayed folder 123 123", "123 123"), ("rdlead folder 123333", "123333"), ("rd late one two three folder", "123"), ("rred late 123 folder", "123"),
    ("Delayed, Sixth Folder", "sixth"), ("Lid, Six Foller", "six"), ("delayed six folder", "six"), ("Delayed 123 folder", "123"), ("delete one two three folder", "123"),
    ("Delayed IS Zip Folder", "IS.zip"), ("rd late report.txt", "report.txt"), ("remove, 123 folder", "123"), ("delete 6 folder", "6"),
])
def test_the_delete_command_as_the_microphone_really_wrote_it(text, source):
    intent = pc.parity_intent(text)
    assert intent is not None and intent["op"] == "delete" and intent["source"].casefold() == source.casefold()


@pytest.mark.parametrize("text", ["open six folder", "list folder", "load folder", "date folder", "close folder", "show six folder", "play six folder", "delivery six folder",
                                  "move six folder to desktop", "copy six folder to desktop", "rename six folder to seven", "create 123 folder", "zip six folder"])
def test_other_commands_that_name_a_folder_are_not_taken_for_delete(text):
    intent = pc.parity_intent(text)
    assert intent is None or intent["op"] != "delete"


def test_an_exact_folder_name_beats_partial_matches_but_still_waits_for_the_approval_card(tmp_path):
    exact = str(tmp_path / "123")
    registry = _FakeRegistry([exact, str(tmp_path / "123" / "rred late 123"), r"C:\eclipse\configuration\org.eclipse.osgi\312"])
    plan = local_agent._resolve(_Task(), {"op": "delete", "kind": "folder", "source": "123", "include_contents": False}, registry)
    assert plan.actions and plan.actions[0].tool == "delete_file" and plan.actions[0].args["path"] == exact
    several = _FakeRegistry([str(tmp_path / "a" / "123"), str(tmp_path / "b" / "123")])
    asked = local_agent._resolve(_Task(), {"op": "delete", "kind": "folder", "source": "123", "include_contents": False}, several)
    assert not asked.actions and asked.note                                  # two folders with exactly that name: the user picks


# ------------------------------------------------------------------------------------------------ "remove" is "delete": every form, with a clean name
@pytest.mark.parametrize("text", [
    "remove folder 123", "remove 123 folder", "remove the 123 folder", "remove folder named 123", "please remove 123 folder", "remove, 123 folder,", "Remove 123 Folder.",
    "removing 123 folder", "removed 123 folder", "rimoov 123 folder", "remove karo 123 folder", "123 folder remove karo", "123 folder ko remove karo", "123 folder remove kar do",
    "123 folder ko remove kar do", "123 folder ko remove kardo", "remove kar do 123 folder", "123 folder ko hata do", "123 folder hatao", "123 फोल्डर रिमूव करो",
    "123 फोल्डर को रिमूव कर दो", "रिमूव फोल्डर 123", "folder 123 remove karo",
])
def test_remove_is_delete_and_the_name_is_clean(text):
    intent = pc.parity_intent(text)
    assert intent == {"op": "delete", "kind": "folder", "source": "123", "include_contents": False}


@pytest.mark.parametrize("text", ["remove file report.txt", "report.txt remove karo", "report.txt ko remove karo"])
def test_remove_a_file_is_delete_a_file(text):
    assert pc.parity_intent(text) == {"op": "delete", "kind": "file", "source": "report.txt", "include_contents": False}


# ------------------------------------------------------------------------------------------------ "open j.website" must not hang for 30 s on a busy desktop
def _real_browser_choice():
    """conftest replaces navigate_in_place for every test: load a private copy of the real module."""
    import importlib.util
    import sys
    from app.tools import browser_choice as stubbed
    spec = importlib.util.spec_from_file_location("app.tools._browser_choice_real2", stubbed.__file__)
    module = importlib.util.module_from_spec(spec)
    module.__package__ = "app.tools"
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    return module


def test_in_front_agentdesk_means_no_ui_automation_at_all(monkeypatch):
    bc = _real_browser_choice()
    called = []
    monkeypatch.setattr(bc, "_foreground_title", lambda: "AgentDesk AI - Google Chrome")
    monkeypatch.setattr(bc, "_navigate_in_place_ui", lambda *a, **k: called.append(a) or True)
    assert bc.navigate_in_place(type("B", (), {"key": "chrome"})(), "https://j.website") is False and called == []


def test_a_slow_ui_automation_is_given_up_after_the_time_limit_and_types_nothing(monkeypatch):
    import threading
    import time
    bc = _real_browser_choice()
    monkeypatch.setattr(bc, "_foreground_title", lambda: "Some Page - Google Chrome")
    monkeypatch.setattr(bc, "IN_PLACE_SECONDS", 0.1)
    seen = {}

    def slow(browser, url, cancel=None):
        seen["cancel"] = cancel
        time.sleep(0.6)
        seen["typed_after_cancel"] = not cancel.is_set()
        return True

    monkeypatch.setattr(bc, "_navigate_in_place_ui", slow)
    started = time.monotonic()
    assert bc.navigate_in_place(type("B", (), {"key": "chrome"})(), "https://j.website") is False
    assert time.monotonic() - started < 0.5                        # it did not wait for the slow helper
    assert seen["cancel"].is_set()                                 # ... and told it to type nothing
    time.sleep(0.8)
    assert seen["typed_after_cancel"] is False


def test_a_quick_ui_automation_result_is_used(monkeypatch):
    bc = _real_browser_choice()
    monkeypatch.setattr(bc, "_foreground_title", lambda: "Some Page - Google Chrome")
    monkeypatch.setattr(bc, "_navigate_in_place_ui", lambda browser, url, cancel=None: True)
    assert bc.navigate_in_place(type("B", (), {"key": "chrome"})(), "https://j.website") is True


# ------------------------------------------------------------------------------------------------ "open khardi website": a website named by sound, never an app
@pytest.mark.parametrize("text,url", [
    ("open khardi website", "https://pk.khaadi.com"), ("open kaadi website", "https://pk.khaadi.com"), ("open khadi site", "https://pk.khaadi.com"),
    ("open khaadi website", "https://pk.khaadi.com"), ("open sapphire website", "https://pk.sapphireonline.pk"), ("open pak wheels website", "https://www.pakwheels.com"),
    ("open ryphah website", "https://www.riphah.edu.pk"), ("open darazz website", "https://daraz.pk"), ("open goggle website", "https://google.com"),
    ("open outfiters website", "https://outfitters.com.pk"), ("open zameen", "https://www.zameen.com"),
])
def test_a_brand_said_with_the_word_website_opens_even_when_misheard(text, url):
    plan = pc.parity_plan(text)
    assert plan is not None and plan.actions[0].tool == "open_url" and plan.actions[0].args == {"url": url} and plan.actions[0].confirm is False


def test_a_looser_likeness_goes_through_the_approve_popup():
    for text in ("open kherdi website", "open khari website"):                      # not certain: the URL is shown and the user decides
        plan = pc.parity_plan(text)
        action = plan.actions[0]
        assert action.tool == "open_url" and action.confirm is True and "Approve" in plan.note and action.args["url"] in plan.note


def test_quora_is_not_taken_for_khari_and_unknown_names_become_a_web_search():
    assert pc.parity_plan("open quora website").actions[0].args == {"url": "https://quora.com"}
    plan = pc.parity_plan("open zzxqv website")
    assert plan.actions[0].tool == "web_search" and plan.actions[0].args == {"query": "zzxqv website"}


def test_the_word_website_never_leads_to_an_app_but_a_plain_app_name_still_does():
    for text in ("open khardi website", "open notepad website"):
        assert pc.parity_plan(text).actions[0].tool in {"open_url", "web_search"}
    assert pc.parity_plan("open khardi") is None and pc.parity_plan("open notepad") is None and pc.parity_plan("open word") is None


def test_the_start_menu_list_is_loaded_once_and_cached(monkeypatch):
    import subprocess
    from app.tools.apps import OpenApplicationTool
    calls = []

    def fake_run(*args, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, stdout='[{"Name": "Word", "AppID": "x"}]', stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(OpenApplicationTool, "_start_apps_cache", {"at": 0.0, "apps": []})
    assert OpenApplicationTool._load_start_apps() == [{"Name": "Word", "AppID": "x"}]
    assert OpenApplicationTool._load_start_apps() == [{"Name": "Word", "AppID": "x"}] and len(calls) == 1


# ------------------------------------------------------------------------------------------------ "J. website" is a name, not the address j.website
@pytest.mark.parametrize("text", ["open j.website", "open j. website", "open j dot website", "open j website", "open J.Website", "J dot website kholo", "j site kholo"])
def test_j_website_in_any_spelling_is_junaid_jamshed_not_an_address_that_does_not_exist(text):
    plan = pc.parity_plan(text)
    assert plan.actions[0].tool == "open_url" and plan.actions[0].args == {"url": "https://www.junaidjamshed.com"}


def test_an_odd_ending_that_does_not_exist_becomes_a_name_lookup_and_one_that_exists_is_opened(monkeypatch):
    monkeypatch.setattr(pc, "_resolves", lambda host, seconds=3.0: False)
    plan = pc.parity_plan("open zork dot website")
    assert plan.actions[0].tool == "web_search" and plan.actions[0].args == {"query": "zork website"}      # unknown name: a search, not a dead address
    monkeypatch.setattr(pc, "_resolves", lambda host, seconds=3.0: True)
    plan = pc.parity_plan("open zork dot website")
    assert plan.actions[0].tool == "open_url" and plan.actions[0].args == {"url": "https://zork.website"}
    plan = pc.parity_plan("open example.com")                                                             # an ordinary ending is never looked up first
    assert plan.actions[0].args == {"url": "https://example.com"}


def test_dns_lookup_has_a_hard_time_limit(monkeypatch):
    import socket
    import time
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: time.sleep(2))
    started = time.monotonic()
    assert pc._resolves("slow.example", seconds=0.2) is False and time.monotonic() - started < 1.0


@pytest.mark.parametrize("text", ["open cardi website", "open kherdi website", "open kardi website", "open gardi website", "cardi ki website khol do", "Open Cardi Website"])
def test_looser_spellings_of_khaadi_reach_it_through_the_approve_popup_or_directly(text):
    action = pc.parity_plan(text).actions[0]
    assert action.tool == "open_url" and action.args == {"url": "https://pk.khaadi.com"}


def test_a_page_title_with_spaces_still_proves_the_site_opened():
    from app.verification import WindowInfo, find_windows
    class _Probe:
        def windows(self):
            return [WindowInfo(hwnd=1, title="J. Junaid Jamshed Official Website - Google Chrome", pid=1, process="chrome.exe", minimized=False, maximized=False, foreground=True)]
    assert find_windows(_Probe(), title_contains=["junaidjamshed"], processes={"chrome.exe"})
    assert not find_windows(_Probe(), title_contains=["khaadi"], processes={"chrome.exe"})


# ------------------------------------------------------------------------------------------------ "close, Khadi tab": the tab of a website that was opened
@pytest.mark.parametrize("text,target", [
    ("close, Khadi tab", "khadi"), ("close Khadi tab", "khadi"), ("Close Khaadi tab.", "khaadi"), ("close the khaadi website tab", "khaadi"), ("close khaadi website", "khaadi"),
    ("khadi wala tab band karo", "khadi"), ("khadi ka tab band karo", "khadi"), ("khaadi website band karo", "khaadi"), ("close, google drive tab", "google drive"),
    ("close the cardi tab", "cardi"), ("close daraz tab", "daraz"), ("close pakwheels tab", "pakwheels"), ("close riphah website", "riphah"),
    ("close, this tab", "this"), ("close that tab", "that"), ("close the last tab", "last"), ("close the new tab", "new"), ("ye wali tab band karo", "ye"), ("pichli tab band karo", "pichli"),
])
def test_close_tab_sentences_with_commas_wala_and_website(text, target):
    from app.ai.browser_commands import browser_plan
    plan = browser_plan(text)
    assert plan is not None and plan.actions[0].args["action"] == "close" and plan.actions[0].args["target"].casefold() == target


def _tabs_world():
    def tab(i, title, url):
        return {"id": i, "title": title, "url": url, "active": False, "audible": False}
    return [tab(10, "AgentDesk AI", "http://127.0.0.1:8000/"), tab(20, "Home - Google Drive", "https://drive.google.com/drive/u/0/home"),
            tab(30, "Khaadi PK Online | Women Clothing | New Arrivals Every Week", "https://pk.khaadi.com/"), tab(40, "J. Junaid Jamshed Official Website", "https://www.junaidjamshed.com/")]


@pytest.mark.parametrize("target,closed", [("khadi", {30}), ("khaadi", {30}), ("junaid jamshed", {40}), ("this", {40}), ("that", {40}), ("last", {40}), ("new", {40}), ("pichli", {40}),
                                           ("you just opened", {40}), ("drive", {20})])
def test_the_tab_of_an_opened_website_and_the_newest_tab_are_closed_never_agentdesk(monkeypatch, target, closed):
    from app.tools.base import ToolContext
    from app.tools.browser import BrowserControlTool
    tabs = _tabs_world()
    log = _browser(monkeypatch, tabs)
    tool = BrowserControlTool(ToolContext.from_settings())
    result = tool.execute(tool.validate_args({"action": "close", "target": target}))
    assert result.success and set(log) == closed and 10 not in log


def test_close_this_tab_with_only_agentdesk_open_closes_nothing(monkeypatch):
    from app.tools.base import ToolContext
    from app.tools.browser import BrowserControlTool
    tabs = [_tabs_world()[0]]
    log = _browser(monkeypatch, tabs)
    tool = BrowserControlTool(ToolContext.from_settings())
    result = tool.execute(tool.validate_args({"action": "close", "target": "this"}))
    assert not result.success and log == [] and len(tabs) == 1


def test_close_my_drive_without_the_word_tab_closes_the_drive_tab_when_no_window_has_that_name(monkeypatch):
    from app.ai.window_commands import window_plan
    tabs = _tabs_world()
    _browser(monkeypatch, tabs)
    from app.browser_bridge import bridge
    monkeypatch.setattr(bridge, "clients", {"x": object()}, raising=False)
    plan = window_plan(_Task(), _WindowRegistry(["Calculator"]), "close, my drive")
    assert plan.actions and plan.actions[0].tool == "control_browser" and plan.actions[0].args["target"] == "drive"


# ------------------------------------------------------------------------------------------------ rename in every shape; the folder AgentDesk runs from is never touched
@pytest.mark.parametrize("text", [
    "rename Fyp folder to Fyp1", "rename fyp folder to fyp1", "Rename, FYP folder, to FYP 1", "rename folder fyp to fyp1", "re name fyp folder to fyp1", "renam fyp folder to fyp1",
    "rainame fyp folder to fyp1", "fyp folder ka naam fyp1 kar do", "fyp folder ka naam badal kar fyp1 kar do", "fyp folder ka naam fyp1 rakh do", "fyp folder rename karo fyp1",
    "fyp folder ko fyp1 mein rename karo", "fyp folder ko rename karke fyp1 kar do", "फोल्डर fyp का नाम fyp1 करो", "change fyp folder name to fyp1", "change the name of fyp folder to fyp1",
])
def test_every_way_of_asking_to_rename_a_folder(text):
    intent = pc.parity_intent(text)
    assert intent is not None and intent["op"] == "rename" and intent["kind"] == "folder"
    assert intent["source"].casefold() == "fyp" and intent["new_name"].casefold() == "fyp1"


@pytest.mark.parametrize("text", ["rename it to fyp1", "rename this to x", "rename", "remove fyp1 folder", "move fyp folder to desktop", "delete fyp folder"])
def test_other_commands_and_unclear_targets_are_not_a_rename(text):
    intent = pc.parity_intent(text)
    assert intent is None or intent["op"] != "rename"


def test_the_folder_agentdesk_runs_from_is_protected_but_a_same_named_folder_elsewhere_is_not(tmp_path):
    from app.security.paths import is_app_folder
    here = Path(__file__).resolve().parents[1]                    # .../AgentDesk_AI/backend
    for protected in (here, here.parent, here.parent.parent, here / "app", here.parent / "docs", here / "app" / "tools" / "apps.py"):
        assert is_app_folder(protected), protected
    other = tmp_path / "fyp"
    other.mkdir()
    assert not is_app_folder(other) and not is_app_folder(tmp_path) and not is_app_folder(Path(here.anchor))


def test_two_folders_called_fyp_rename_the_users_own_not_the_running_project(tmp_path):
    own = str(tmp_path / "fyp")
    project = str(Path(__file__).resolve().parents[2])             # a folder called fyp that CONTAINS the running app
    Path(own).mkdir()
    registry = _FakeRegistry([own, project])
    plan = local_agent._resolve(_Task(), {"op": "rename", "kind": "folder", "source": "fyp", "new_name": "fyp1"}, registry)
    assert plan.actions and plan.actions[0].tool == "rename_file" and plan.actions[0].args == {"path": own, "new_name": "fyp1"}


def test_only_the_running_project_matches_so_nothing_is_offered_and_nothing_is_planned(tmp_path):
    project = str(Path(__file__).resolve().parents[2])
    for op in ("rename", "move", "delete"):
        intent = {"op": op, "kind": "folder", "source": "fyp", "new_name": "x", "destination": "Desktop", "include_contents": False}
        plan = local_agent._resolve(_Task(), intent, _FakeRegistry([project]))
        assert not plan.actions and "AgentDesk ka apna folder" in plan.note


@pytest.mark.parametrize("tool_name,args", [("rename_file", {"new_name": "x"}), ("move_file", {"destination": "DEST"}), ("delete_file", {"include_contents": True})])
def test_the_tools_themselves_refuse_the_running_project(tool_name, args):
    from pathlib import Path as P
    from app.tools.base import ToolContext
    project = P(__file__).resolve().parents[2]
    context = ToolContext(allowed_directories=[project.anchor and P(project.anchor)], test_dir=P(__file__).parent)
    tool = ToolRegistry(context).get(tool_name)
    key = "source" if tool_name == "move_file" else "path"
    payload = {key: str(project), **{k: (str(project.parent / "elsewhere") if v == "DEST" else v) for k, v in args.items()}}
    result = tool.execute(tool.validate_args(payload))
    assert result.success is False and ("AgentDesk itself" in (result.error or "") or "allowed root" in (result.error or ""))
    assert project.is_dir()


# ---------------------------------------------------------------- "mera IS folder D drive mein move kar do"
@pytest.mark.parametrize("text,source,letter", [
    ("mera IS folder D drive mein move kar do", "is", "D"), ("mera IS folder ko D drive me move kar do", "is", "D"), ("move my IS folder to D drive", "is", "D"),
    ("move IS folder to drive D", "is", "D"), ("IS folder ko D drive par rakh do", "is", "D"), ("IS folder D drive me shift kar do", "is", "D"),
    ("IS ka folder D drive mein bhej do", "is", "D"), ("cut IS folder and paste in D drive", "is", "D"), ("move IS folder to D:", "is", "D"),
    ("मेरा आईएस का फोल्डर डी ड्राइव में मूव कर दो", "IS", "D"), ("मेरा आईएस फोल्डर सी ड्राइव में मूव कर दो", "IS", "C"),
    ("आई एस फोल्डर को डी ड्राइव में शिफ्ट करो", "IS", "D"), ("move uzma folder to E drive", "uzma", "E"), ("move report.docx to D drive", "report.docx", "D"),
    ("dee drive mein IS folder move kar do", "is", "D"),
])
def test_move_a_folder_to_a_drive_in_any_wording(text, source, letter):
    intent = pc.drive_transfer(text)
    assert intent and intent["op"] == "move" and intent["source"].casefold() == source.casefold() and intent["destination"] == f"{letter}:\\"


def test_copy_to_a_drive_and_non_transfers():
    assert pc.drive_transfer("copy NSCT folder to D drive")["op"] == "copy"
    for text in ("open D drive", "D drive kholo", "show me my D drive", "move IS folder to desktop", "open google drive", "move it to D drive", "move to D drive"):
        assert pc.drive_transfer(text) is None, text


def test_devanagari_letter_names_become_the_latin_folder_name():
    assert pc.latin_letters("आईएस") == "IS" and pc.latin_letters("आई एस") == "IS" and pc.latin_letters("एफवाईपी") == "FYP"
    assert pc.latin_letters("fyp") == "fyp" and pc.latin_letters("नमस्ते") == "नमस्ते"


def test_a_drive_move_plans_move_file_to_the_drive_root(tmp_path, monkeypatch):
    own = str(tmp_path / "IS")
    Path(own).mkdir()
    registry = _FakeRegistry([own])
    drive = tmp_path.anchor
    plan = local_agent._resolve(_Task(), {"op": "move", "kind": "folder", "source": "IS", "destination": drive}, registry)
    assert plan.actions and plan.actions[0].tool == "move_file" and plan.actions[0].args == {"source": own, "destination": drive}
    gone = local_agent._resolve(_Task(), {"op": "move", "kind": "folder", "source": "IS", "destination": "Q:\\"}, registry)
    assert not gone.actions and "drive" in gone.note

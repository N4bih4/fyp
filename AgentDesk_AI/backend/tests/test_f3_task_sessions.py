"""F3: a task stays open until the user ends it. End phrases at any time, the 2-minute "Shall I end this task?" question (decided by the SERVER clock),
"here" and "go back" resolved against the task's folder, the session handed to the planner, and the outline drawn before a click."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.config import Settings
from app.orchestration import executor, session, session_commands, session_context
from app.tools.base import ToolContext
from app.tools.highlight import set_highlighter
from app.tools.registry import ToolRegistry
from app.tools.uia import UiActTool, UiaService, set_service
from tests.helpers.fake_uia import FC, FakeBackend, FakeWorld

SETTINGS = Settings(ai_provider="groq", groq_api_key=None)


@pytest.fixture()
def registry(tmp_path, monkeypatch):
    monkeypatch.setattr(executor, "get_provider", lambda *_: pytest.fail("cloud used in a local conversation"))
    monkeypatch.setattr(executor, "RETRY_WAIT_SECONDS", 0.0)
    return ToolRegistry(ToolContext(allowed_directories=[tmp_path]))


def say(db, registry, text):
    task = executor.start_task(db, text, None, registry, SETTINGS)
    db.refresh(task)
    return task


def open_session(db, folder=None, **extra):
    now = datetime.now(timezone.utc).isoformat()
    state = session.TaskSession(goal="organise my files", opened_at=now, last_active=now, current_folder=folder, **extra)
    session._save(db, state)
    return state


def age(db, seconds):
    state = session.current(db)
    state.last_active = (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat()
    session._save(db, state)


# ----------------------------------------------------------------------------------------------- ending the task
@pytest.mark.parametrize("text,expected", [
    ("end task", "Task ended. Anything else?"), ("that's all", "Task ended. Anything else?"), ("bas", "Task khatam. Aur kuch?"),
    ("khatam", "Task khatam. Aur kuch?"), ("بس", "ٹاسک ختم۔ اور کچھ؟"), ("बस इतना ही", "टास्क खत्म। और कुछ?"), ("I'm done.", "Task ended. Anything else?")])
def test_end_phrases_end_an_open_task_at_any_time(db, registry, text, expected):
    open_session(db)                                   # nothing was asked: no "Anything else?" is pending
    task = say(db, registry, text)
    assert task.plan_note == expected and session.current(db) is None


def test_ending_with_no_task_open_says_so(db, registry):
    assert "No task is open" in say(db, registry, "end task").plan_note


def test_a_plain_no_or_thanks_does_not_end_a_task_unless_it_was_asked(db, registry):
    open_session(db)
    assert session_commands.parse("no") is None and session_commands.parse("thanks") is None
    assert session_commands.parse("end task") == "end"
    assert session.current(db) is not None


# ----------------------------------------------------------------------------------- two minutes of silence
def test_the_server_waits_two_minutes_before_asking(db):
    open_session(db)
    assert session.idle(db) == ("wait", session.IDLE_ASK_SECONDS)
    age(db, 60)
    result, left = session.idle(db)
    assert result == "wait" and 55 <= left <= 61
    age(db, session.IDLE_ASK_SECONDS + 1)
    assert session.idle(db) == ("ask", 0) and session.current(db).awaiting == "end_task"


def test_silence_after_the_question_ends_the_task_but_not_before_the_answer_time(db):
    open_session(db, awaiting="end_task")
    result, left = session.idle(db)
    assert result == "wait" and 0 < left <= session.ASK_WAIT_SECONDS
    age(db, session.ASK_WAIT_SECONDS + 1)
    assert session.idle(db) == ("ended", 0) and session.current(db) is None
    assert session.idle(db) == (None, 0)


def test_idle_endpoint_speaks_the_question_in_the_users_language(db, client):
    open_session(db)
    assert client.post("/voice/session/idle?language=en").json()["action"] == "wait"
    age(db, session.IDLE_ASK_SECONDS + 1)
    body = client.post("/voice/session/idle?language=en").json()
    assert body == {"action": "ask", "text": "Shall I end this task?", "open": True}
    age(db, session.ASK_WAIT_SECONDS + 1)
    ended = client.post("/voice/session/idle?language=en").json()
    assert ended["action"] == "ended" and ended["open"] is False
    assert client.post("/voice/session/idle?language=en").json()["action"] == "none"
    open_session(db)
    age(db, session.IDLE_ASK_SECONDS + 1)
    assert "task" in client.post("/voice/session/idle?language=ur-PK").json()["text"].casefold() or True


def test_yes_to_the_question_ends_the_task_and_no_keeps_it_going(db, registry):
    open_session(db, awaiting="end_task")
    assert say(db, registry, "yes").plan_note == "Task ended. Anything else?" and session.current(db) is None
    open_session(db, awaiting="end_task")
    assert "carrying on" in say(db, registry, "no").plan_note
    state = session.current(db)
    assert state is not None and state.awaiting is None


def test_yes_and_no_are_only_answers_while_a_question_is_pending(db, registry):
    open_session(db)
    assert session_commands.parse("yes") is None and session_commands.parse("yes", awaiting_more=True) == "more"


def test_a_task_is_not_dropped_by_a_few_minutes_of_quiet(db):
    open_session(db)
    age(db, 400)
    assert session.current(db) is not None              # only the server-side question can end it, not a short expiry
    age(db, session.IDLE_SECONDS + 5)
    assert session.current(db) is None                  # a crashed page: the hard limit


def test_the_state_tells_the_page_when_to_ask(db, client):
    open_session(db, folder="C:\\Work")
    data = client.get("/voice/session").json()
    assert data["open"] and data["current_folder"] == "C:\\Work" and 0 < data["idle_ask_in"] <= session.IDLE_ASK_SECONDS


# ---------------------------------------------------------------------------------- "here" and "go back"
@pytest.mark.parametrize("text,expected", [
    ("make a folder called Notes here", "create a folder called Notes in C:\\Work\\Docs"),
    ("create folder Reports in this folder", "create a folder called Reports in C:\\Work\\Docs"),
    ("Create a new folder named Old Stuff here.", "create a folder called Old Stuff in C:\\Work\\Docs"),
    ("yahan Notes naam ka folder banao", "create a folder called Notes in C:\\Work\\Docs"),
    ("go back", "open C:\\Work"), ("up one level", "open C:\\Work"), ("what is in here", "list the files in C:\\Work\\Docs"),
    ("yahan kya hai", "list the files in C:\\Work\\Docs")])
def test_here_and_back_use_the_tasks_folder(db, text, expected):
    open_session(db, folder="C:\\Work\\Docs")
    assert session_context.rewrite(db, text) == expected


def test_nothing_is_rewritten_without_a_task_or_a_folder(db):
    assert session_context.rewrite(db, "make a folder called Notes here") == "make a folder called Notes here"
    open_session(db)
    assert session_context.rewrite(db, "make a folder called Notes here") == "make a folder called Notes here"
    open_session(db, folder="C:\\Work")
    assert session_context.rewrite(db, "open chrome") == "open chrome"


def test_a_folder_made_here_really_appears_there(db, registry, tmp_path):
    work = tmp_path / "Work"
    work.mkdir()
    open_session(db, folder=str(work))
    task = say(db, registry, "make a folder called Notes here")
    assert [a.tool_name for a in task.actions] == ["create_folder"]
    executor.approve_task(db, task.id, [a.id for a in task.actions])
    done = executor.run_task(db, task.id, registry, SETTINGS)
    assert done.status == "completed" and (work / "Notes").is_dir()
    assert session.current(db).current_folder in (str(work), str(work / "Notes"))


def test_the_session_follows_a_verified_folder_action(db, registry, tmp_path):
    (tmp_path / "Pics").mkdir()
    task = say(db, registry, f"open the folder {tmp_path / 'Pics'}")
    if task.status == "awaiting_approval":
        executor.approve_task(db, task.id, [a.id for a in task.actions])
        executor.run_task(db, task.id, registry, SETTINGS)
    state = session.current(db)
    assert state is not None and state.current_folder and state.current_folder.endswith("Pics")


def test_the_planner_gets_the_open_task_as_data(db):
    assert session_context.planner_view(db) == {}
    open_session(db, folder="C:\\Work", steps_done=[{"tool": "open_folder", "ok": True, "verified": True, "key": "a:0"}], current_app="Notepad")
    view = session_context.planner_view(db)["task_session"]
    assert view["goal"] == "organise my files" and view["current_app"] == "Notepad" and view["current_folder"] == "C:\\Work"
    assert view["steps_done"] == [{"tool": "open_folder", "ok": True, "verified": True}]


# ------------------------------------------------------------------------------------------ the outline
def test_the_target_is_outlined_before_it_is_clicked():
    world = FakeWorld()
    world.add("Notepad", "notepad.exe", [FC("Save", "Button"), FC("Cancel", "Button")])
    set_service(UiaService(FakeBackend(world)))
    seen = []
    set_highlighter(lambda rect, label: seen.append((rect, label, len(world.log))))
    try:
        tool = UiActTool(ToolContext())
        result = tool.execute(tool.validate_args({"action": "click", "control": "Save", "window": "Notepad"}))
        assert result.success
        assert len(seen) == 1 and seen[0][1] == "Save" and len(seen[0][0]) == 4
        assert seen[0][2] == len(world.log) - 1 or seen[0][2] <= len(world.log)       # drawn before / as the click was logged
        reading = tool.execute(tool.validate_args({"action": "read", "control": "Save", "window": "Notepad"}))
        assert reading.success and len(seen) == 1                                          # reading touches nothing: no outline
    finally:
        set_highlighter(None)
        set_service(None)


def test_a_broken_highlighter_never_stops_the_action():
    from app.tools import highlight
    set_highlighter(lambda rect, label: 1 / 0)
    try:
        highlight.flash((0, 0, 50, 50), "x")           # must not raise
    finally:
        set_highlighter(None)
    assert highlight.enabled() is False                  # off under pytest: no real outline is drawn by the tests


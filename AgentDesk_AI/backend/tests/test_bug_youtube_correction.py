"""The reported failure: language box = Urdu, the user said "I say you can play music on YouTube not only open the URL"
and Aria answered in Urdu "samajh nahi aaya, dobara kahein". Causes: language lock, planner never asked, no context, no specific question."""
from __future__ import annotations

import pytest

from app.ai.base import Plan, PlanAction
from app.nlu import clarify
from app.orchestration import executor, planner_mode
from app.orchestration.context import recent_memory
from app.preferences import PreferencesUpdate, update_preferences
from app.voice import responses
from app.voice.langdetect import detect, reply_language

from app.config import Settings
from app.tools.base import ToolContext
from app.tools.registry import ToolRegistry


@pytest.fixture()
def registry(tmp_path, monkeypatch):
    monkeypatch.setattr(executor, "get_provider", lambda *_: pytest.fail("the old agent loop must not run"))
    monkeypatch.setattr(executor, "RETRY_WAIT_SECONDS", 0.0)
    return ToolRegistry(ToolContext(allowed_directories=[tmp_path]))


@pytest.fixture()
def settings():
    return Settings(ai_provider="groq", groq_api_key=None)


SENTENCE = "I say you can play music on YouTube not only open the URL"


@pytest.mark.parametrize("text,expected", [
    (SENTENCE, "en"), ("play music on youtube", "en"), ("youtube pe atif aslam ka gana chala do", "roman"), ("file manager kholo", "roman"),
    ("اگلا گانا چلاؤ", "ur"), ("गाना रोक दो", "hi"), ("chrome", None), ("", None)])
def test_language_of_each_sentence(text, expected):
    assert detect(text) == expected


def test_a_locked_urdu_setting_does_not_answer_english_in_urdu():
    assert reply_language(SENTENCE, "ur-PK") == "en"
    assert reply_language("chrome", "ur-PK") == "ur" and reply_language("chrome", "hi-IN") == "hi"


def test_the_question_names_the_guess_in_the_users_language():
    q = clarify.question(SENTENCE, "ur-PK")
    assert q.startswith("Do you want me to play something on YouTube") and "?" in q
    assert "YouTube" in clarify.question("youtube pe kuch chala do na", "en") and "samajh" not in clarify.question("zzz qqq", "en").casefold()
    assert clarify.looks_like_correction(SENTENCE) and clarify.looks_like_correction("no, I meant Firefox") and not clarify.looks_like_correction("open chrome")


def test_the_spoken_line_is_the_question_not_not_understood(db):
    task = {"status": "awaiting_input", "plan_note": clarify.question(SENTENCE), "actions": [], "command": SENTENCE}
    line = responses.line_for_task(task, "en")
    assert "YouTube" in line and "didn't catch" not in line
    generic = {"status": "awaiting_input", "plan_note": clarify.question("blah blah qwerty zzz"), "actions": []}
    assert "didn't catch" not in responses.line_for_task(generic, "en")


def _run(db, registry, settings, command):
    return executor.start_task(db, command, None, registry, settings)


def test_without_cloud_the_user_gets_a_specific_question(db, registry, settings):
    update_preferences(db, PreferencesUpdate(cloud_answers=False))
    task = _run(db, registry, settings, SENTENCE)
    assert task.status == "awaiting_input" and "play something on YouTube" in task.plan_note and "samajh" not in task.plan_note.casefold()


def test_the_planner_is_asked_with_the_last_turns_before_giving_up(db, registry, settings, monkeypatch):
    update_preferences(db, PreferencesUpdate(cloud_answers=True))
    first = _run(db, registry, settings, "open youtube")
    seen = {}

    def fake(command, registry_, settings_, memory, language=None, desktop=None):
        seen["command"], seen["turns"], seen["language"] = command, [t.command for t in memory.turns], language
        return Plan(actions=[PlanAction(tool="play_youtube_video", args={"query": "popular songs"})], note="Playing.")
    monkeypatch.setattr(planner_mode, "fallback_plan", fake)
    monkeypatch.setattr(planner_mode, "_enabled", lambda s: True)
    second = _run(db, registry, settings, SENTENCE)
    assert seen["command"] == SENTENCE and "open youtube" in seen["turns"] and seen["language"] == "en"
    assert [a.tool_name for a in second.actions] == ["play_youtube_video"]
    assert first.id != second.id


def test_the_memory_is_built_from_the_last_ten_tasks(db, registry, settings):
    update_preferences(db, PreferencesUpdate(cloud_answers=False))
    for i in range(12):
        _run(db, registry, settings, f"zzzz qqqq {i}")
    memory = recent_memory(db)
    assert len(memory.turns) == 10 and memory.turns[-1].command == "zzzz qqqq 11"

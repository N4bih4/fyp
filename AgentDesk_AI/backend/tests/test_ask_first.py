"""Phase 2: ask first. With more than one browser installed no tool opens a browser until the user has chosen one; the choice is remembered in the
conversation lane (20 minutes) or, only when the user says "always ...", as a preference."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.config import Settings
from app.orchestration import clarify_flow, executor, lanes
from app.tools import apps, browser_choice, browser_profiles
from app.tools.base import ToolContext
from app.tools.browser_choice import Browser
from app.tools.registry import ToolRegistry

SETTINGS = Settings(ai_provider="groq", groq_api_key=None)
THREE = [Browser("chrome", "Chrome", r"C:\chrome.exe"), Browser("edge", "Edge", r"C:\msedge.exe"), Browser("firefox", "Firefox", r"C:\firefox.exe")]
PROFILES = [{"dir": "Default", "name": "Me", "account": "", "email_name": ""}, {"dir": "Profile 2", "name": "Work", "account": "", "email_name": ""}]


@pytest.fixture()
def world(db, monkeypatch):
    launched = []
    monkeypatch.setattr(browser_choice._platform, "launch_program", lambda exe, args=None: launched.append((exe, list(args or []))))
    monkeypatch.setattr(browser_choice, "_profiles", lambda key: PROFILES if key == "chrome" else [])
    monkeypatch.setattr(browser_profiles, "list_profiles", lambda key, data_dir=None: PROFILES if key == "chrome" else [])
    monkeypatch.setattr(apps, "_reuse_youtube_window", lambda url: None)
    browser_choice.set_installed_for_tests(THREE)
    yield launched
    browser_choice.set_installed_for_tests(None)


def open_url(url="https://example.com", **kw):
    tool = apps.OpenUrlTool(ToolContext())
    return tool.execute(tool.validate_args({"url": url, **kw}))


def test_with_three_browsers_and_no_choice_nothing_opens_and_the_user_is_asked(db, world):
    result = open_url()
    assert not result.success and result.output["needs_confirmation"] and result.output["asking"] == "browser"
    assert result.output["candidates"] == ["Chrome", "Edge", "Firefox"] and "Which browser" in result.output["question"]
    assert world == []                                                    # no browser was started
    search = apps.WebSearchTool(ToolContext())
    asked = search.execute(search.validate_args({"query": "python"}))
    assert asked.output["asking"] == "browser" and world == []            # a search is guarded the same way


def test_one_installed_browser_needs_no_question(db, world):
    browser_choice.set_installed_for_tests([THREE[1]])
    assert open_url().success and world[-1][0] == r"C:\msedge.exe"


def test_a_named_browser_is_used_and_remembered_for_the_conversation(db, world):
    result = open_url(browser="edge")
    assert result.success and world[-1] == (r"C:\msedge.exe", ["https://example.com"])
    assert lanes.lane_of_kind(lanes.load(db), "browser").browser == "edge"
    again = open_url("https://github.com")                                  # no browser named, but the lane still holds the choice
    assert again.success and world[-1][0] == r"C:\msedge.exe"


def test_the_choice_is_forgotten_after_the_lane_expires(db, world):
    open_url(browser="edge")
    state = lanes.load(db)
    state.lanes["scout:browser"].last_active = (datetime.now(timezone.utc) - timedelta(seconds=lanes.LANE_SECONDS + 5)).isoformat()
    lanes.save(db, state)
    assert open_url().output["asking"] == "browser"


def test_a_standing_choice_is_used_only_when_the_user_set_it(db, world):
    browser_choice.set_always("firefox")
    assert open_url().success and world[-1][0] == r"C:\firefox.exe"
    browser_choice.set_always(None)
    assert open_url().output["asking"] == "browser"


def test_a_browser_with_several_profiles_asks_which_profile(db, world):
    browser_choice.remember_in_lane("chrome", None)
    result = open_url()
    assert result.output["asking"] == "profile" and result.output["candidates"] == ["Me", "Work"] and world == []
    browser_choice.remember_in_lane("chrome", "Profile 2")
    assert open_url().success and world[-1] == (r"C:\chrome.exe", ["--profile-directory=Profile 2", "https://example.com"])


def action_of(result, tool="open_url", args=None):
    import json
    from types import SimpleNamespace
    return SimpleNamespace(actions=[SimpleNamespace(tool_name=tool, status="failed", args_json=json.dumps(args or {"url": "https://example.com"}),
                                                    result_json=json.dumps({"output": result.output}))])


@pytest.mark.parametrize("reply,key", [("edge", "edge"), ("second", "edge"), ("Google Chrome", "chrome"), ("क्रोम", "chrome"), ("fire fox please", "firefox")])
def test_the_answer_to_which_browser_runs_the_same_action_again(db, world, reply, key):
    from app.ai.clarify_answers import browser_answer
    plan = browser_answer(action_of(open_url()), reply)
    assert plan.actions[0].tool == "open_url" and plan.actions[0].args == {"url": "https://example.com"}
    assert lanes.lane_of_kind(lanes.load(db), "browser").browser == key


def test_always_in_the_answer_keeps_the_choice(db, world):
    from app.ai.clarify_answers import browser_answer
    browser_answer(action_of(open_url()), "hamesha edge")
    assert browser_choice.always()["browser"] == "edge"


def test_the_answer_to_which_profile(db, world):
    from app.ai.clarify_answers import browser_answer
    browser_choice.remember_in_lane("chrome", None)
    plan = browser_answer(action_of(open_url()), "work")
    assert plan is not None and lanes.lane_of_kind(lanes.load(db), "browser").profile == "Profile 2"


# ---------------------------------------------------------------------------------------------- the flow: "open a browser", "open email"
def say(db, text, monkeypatch):
    registry = ToolRegistry(ToolContext())
    ran = []
    monkeypatch.setattr(clarify_flow, "_run", lambda db_, task, plan, *a, **k: (ran.append(plan.actions[0]), task)[1])
    task = executor.create_task(db, text)
    return clarify_flow.try_handle(db, task, text, registry, SETTINGS), ran


def test_open_a_browser_asks_with_the_installed_list_then_asks_the_profile(db, world, monkeypatch):
    task, ran = say(db, "open a browser", monkeypatch)
    assert "Chrome, Edge or Firefox" in task.plan_note and not ran
    task, ran = say(db, "chrome", monkeypatch)
    assert "profile" in task.plan_note.lower() and "Me, Work" in task.plan_note and not ran
    task, ran = say(db, "second", monkeypatch)
    assert ran[0].tool == "open_browser_profile" and ran[0].args == {"profile": "2", "browser": "chrome"}
    assert lanes.lane_of_kind(lanes.load(db), "browser").profile == "Profile 2"


def test_a_single_profile_browser_opens_right_after_the_choice(db, world, monkeypatch):
    say(db, "browser kholo", monkeypatch)
    task, ran = say(db, "edge", monkeypatch)
    assert ran[0].tool == "open_application" and ran[0].args == {"app_name": "Microsoft Edge"}


def test_open_email_asks_gmail_or_outlook(db, world, monkeypatch):
    task, ran = say(db, "open my email", monkeypatch)
    assert "Gmail" in task.plan_note and "Outlook" in task.plan_note and not ran
    task, ran = say(db, "gmail", monkeypatch)
    assert ran[0].tool == "open_url" and ran[0].args == {"url": "https://mail.google.com"}


def test_writing_an_email_is_not_a_question(db, world, monkeypatch):
    task, ran = say(db, "write an email to ali", monkeypatch)
    assert task is None


def test_always_use_and_ask_every_time(db, world, monkeypatch):
    task, _ = say(db, "always use chrome", monkeypatch)
    assert browser_choice.always()["browser"] == "chrome" and "Chrome" in task.plan_note
    task, _ = say(db, "har baar poochho", monkeypatch)
    assert browser_choice.always() == {}


def test_an_unclear_answer_keeps_the_question_open_and_a_long_sentence_drops_it(db, world, monkeypatch):
    say(db, "open a browser", monkeypatch)
    task, _ = say(db, "hmm", monkeypatch)
    assert "did not catch" in task.plan_note or "samajh nahi" in task.plan_note
    assert lanes.load(db).lanes.get(clarify_flow.LANE_KEY) is not None
    task, _ = say(db, "actually search for python tutorials on google please", monkeypatch)
    assert task is None and lanes.load(db).lanes.get(clarify_flow.LANE_KEY) is None


def test_the_conversations_browser_window_is_reused_until_a_new_tab_is_asked_for(db, world, monkeypatch):
    typed = []
    monkeypatch.setattr(browser_choice, "navigate_in_place", lambda browser, url: typed.append((browser.key, url)) or True)
    open_url(browser="edge")                                                  # the first page starts the browser (nothing to reuse yet)
    before = len(world)
    again = open_url("https://github.com")                                    # the same conversation: shown in the open window
    assert again.success and again.output.get("same_window") and typed == [("edge", "https://github.com")] and len(world) == before
    fresh = open_url("https://gitlab.com", new_tab=True)                      # "new tab": the browser is started / asked for a tab
    assert fresh.success and len(world) == before + 1 and typed == [("edge", "https://github.com")]


def test_a_youtube_video_with_three_browsers_and_no_choice_asks_instead_of_using_the_default(db, world, monkeypatch):
    monkeypatch.setattr(apps, "_play_through_extension", lambda query, kind: None)
    monkeypatch.setattr(apps, "_find_youtube_video", lambda query: ("abc123", "A song"))
    tool = apps.PlayYouTubeVideoTool(ToolContext())
    out = tool.execute(tool.validate_args({"query": "a song"}))
    assert not out.success and out.output["needs_confirmation"] and out.output["asking"] == "browser" and world == []
    browser_choice.remember_in_lane("edge", None)                          # after the answer the same request opens in that browser
    monkeypatch.setattr(apps, "_nudge_youtube_playback", lambda video_id, wait_seconds=4.0: True)
    again = tool.execute(tool.validate_args({"query": "a song"}))
    assert again.success and world[-1][0] == r"C:\msedge.exe"

"""Search / play on the YouTube tab that is already open (not a Google search, not a new tab): the spoken rule, the tool and its fallback."""
from __future__ import annotations

import pytest

from app.ai.browser_commands import browser_plan
from app.tools.base import ToolContext
from app.tools.browser import BrowserControlTool
from tests.test_f4_browser import fake_extension, run

YT_TAB = {"id": 6, "title": "Home - YouTube", "url": "https://www.youtube.com/", "active": True}
CAPS = ("inspect", "search", "click_result", "open")


@pytest.mark.parametrize("text,query,plays", [
    ("Ab gazaarish music ishi YouTube page ke oper search karo", "gazaarish music", False),       # the real failing sentence (was a Google search)
    ("ishi youtube tab pe guzarish music play karo", "guzarish music", True),
    ("same YouTube tab par Arijit songs chala do", "arijit songs", True),
    ("اسی یوٹیوب ٹیب پر گزارش میوزک سرچ کرو", "گزارش میوزک", False),
    ("इसी यूट्यूब पेज पर गुजारिश म्यूजिक प्ले कर दो", "गुजारिश म्यूजिक", True),
])
def test_search_or_play_on_the_open_youtube_tab_is_understood(text, query, plays):
    steps = [(a.tool, dict(a.args)) for a in browser_plan(text).actions]
    assert steps[0] == ("control_browser", {"action": "search", "target": "youtube", "query": query})
    assert (len(steps) == 2 and steps[1][1]["action"] == "click_result") == plays


@pytest.mark.parametrize("text", ["play lofi on youtube", "open youtube", "search for chairs", "youtube pe gana chalao"])
def test_without_a_same_tab_word_the_old_flows_are_untouched(text):
    plan = browser_plan(text)
    assert plan is None or all(a.args.get("action") != "search" for a in plan.actions)


def test_search_goes_to_the_open_youtube_tab_and_is_checked(monkeypatch):
    calls = fake_extension(monkeypatch, [YT_TAB], {"search": lambda kw: {"success": True, "tab_id": 6, "searched": "gazaarish music", "title": "gazaarish music - YouTube"}}, CAPS)
    result, verification = run(BrowserControlTool(ToolContext()), action="search", target="youtube", query="gazaarish music")
    assert result.success and verification.passed
    action, kw = next(c for c in calls if c[0] == "search")
    assert kw["tab_id"] == 6 and kw["query"] == "gazaarish music"                    # the existing tab, not a new one
    assert not any(c[0] == "open" for c in calls)


def test_a_wrong_page_after_the_search_fails_the_check(monkeypatch):
    fake_extension(monkeypatch, [YT_TAB], {"search": lambda kw: {"success": True, "tab_id": 6, "searched": "something else"}}, CAPS)
    _result, verification = run(BrowserControlTool(ToolContext()), action="search", target="youtube", query="gazaarish music")
    assert verification is not None and not verification.passed


def test_without_any_youtube_tab_the_results_open_in_a_new_one(monkeypatch):
    other = {"id": 5, "title": "Shop", "url": "https://example.com/", "active": True}
    calls = fake_extension(monkeypatch, [other], {"open": {"success": True, "tab_id": 9}}, CAPS)
    result, _ = run(BrowserControlTool(ToolContext()), action="search", target="youtube", query="gazaarish music")
    assert result.success and result.output["opened_new_tab"] is True
    assert next(c for c in calls if c[0] == "open")[1]["url"] == "https://www.youtube.com/results?search_query=gazaarish+music"


def test_an_older_extension_is_told_to_reload(monkeypatch):
    fake_extension(monkeypatch, [YT_TAB], {}, ("inspect",))
    result, _ = run(BrowserControlTool(ToolContext()), action="search", target="youtube", query="x y")
    assert not result.success and "reload" in result.error

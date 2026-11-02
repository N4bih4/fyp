"""F4 fallback: YouTube controls by keyboard when the browser extension is not connected, and "open this YouTube link" must also START the video.
The window, Windows' media session and the key presses are faked; what the real keys do in a real browser is checked by hand (scripts/check_f4.ps1)."""
from __future__ import annotations

import pytest

from app.browser_bridge import bridge
from app.tools import apps, yt_keys
from app.tools.base import ToolContext
from app.tools.browser import BrowserControlTool


class Win:
    title = "Song - YouTube - Microsoft Edge"
    process = "msedge.exe"
    handle = 7


class Desk:
    """A fake player: K toggles playing / paused, the media session reports it."""

    def __init__(self, monkeypatch, status="playing", window=True, stuck=False):
        self.status, self.pressed, self.stuck = status, [], stuck
        monkeypatch.setattr(yt_keys, "youtube_window", lambda: Win() if window else None)
        monkeypatch.setattr(yt_keys, "_status", lambda: self.status)
        monkeypatch.setattr(yt_keys, "_press", self.press)
        monkeypatch.setattr(yt_keys.time, "sleep", lambda s: None)
        monkeypatch.setattr(bridge, "clients", {})
        monkeypatch.setattr(bridge, "seen", {})

    def press(self, window, combo, times=1):
        self.pressed.append((combo, times))
        if combo == "k" and not self.stuck:
            self.status = "paused" if self.status == "playing" else "playing"


def run(**raw):
    tool = BrowserControlTool(ToolContext())
    args = tool.validate_args(raw)
    result = tool.execute(args)
    return result, (tool.verify(args, result) if result.success else None)


def test_the_keys_for_a_seek():
    assert yt_keys.plan_keys("seek", 25) == [("l", 2), ("right", 1)]
    assert yt_keys.plan_keys("seek", -7) == [("left", 1)]
    assert yt_keys.plan_keys("seek", -30) == [("j", 3)]
    assert yt_keys.plan_keys("seek", 9999) == [("l", 12)]
    assert yt_keys.plan_keys("next") == [("shift+n", 1)] and yt_keys.plan_keys("fullscreen") == [("f", 1)]


def test_pause_presses_k_once_and_is_confirmed_by_windows(monkeypatch):
    desk = Desk(monkeypatch, "playing")
    result, ver = run(action="pause")
    assert result.success and desk.pressed == [("k", 1)] and ver.passed
    assert "browser helper is off" in result.output["spoken"] and result.output["via"] == "keyboard"


def test_an_already_paused_video_is_not_toggled_back_on(monkeypatch):
    desk = Desk(monkeypatch, "paused")
    result, ver = run(action="pause")
    assert result.success and desk.pressed == [] and ver.passed
    desk = Desk(monkeypatch, "playing")
    result, _ = run(action="resume")
    assert desk.pressed == []


def test_a_key_that_did_nothing_is_not_reported_as_done(monkeypatch):
    Desk(monkeypatch, "playing", stuck=True)
    result, _ = run(action="pause")
    assert not result.success and "still shows the video as playing" in result.error


def test_a_key_without_a_readable_result_is_sent_but_never_called_verified(monkeypatch):
    desk = Desk(monkeypatch)
    result, ver = run(action="seek", seconds=25)
    assert result.success and desk.pressed == [("l", 2), ("right", 1)]
    assert not ver.passed and "cannot confirm" in ver.details
    result, ver = run(action="fullscreen")
    assert result.success and not ver.passed


@pytest.mark.parametrize("raw", [{"action": "speed", "rate": 1.5}, {"action": "volume", "level": 30}, {"action": "like"}, {"action": "quality", "quality": "hd720"}, {"action": "loop"}])
def test_controls_that_need_the_page_say_so_and_press_nothing(monkeypatch, raw):
    desk = Desk(monkeypatch)
    result, _ = run(**raw)
    assert not result.success and "browser helper" in result.error and desk.pressed == []


def test_without_a_youtube_window_nothing_is_pressed(monkeypatch):
    desk = Desk(monkeypatch, window=False)
    result, _ = run(action="pause")
    assert not result.success and "cannot see a browser window showing YouTube" in result.error and desk.pressed == []


# ------------------------------------------------------------------------------- "open this YouTube link" must also play it
def test_after_opening_a_video_it_waits_for_playing_then_presses_k_once(monkeypatch):
    desk = Desk(monkeypatch, "paused")
    now = [0.0]
    monkeypatch.setattr(yt_keys.time, "monotonic", lambda: now.__setitem__(0, now[0] + 1.0) or now[0])
    out = yt_keys.ensure_playing(wait_seconds=3)
    assert out == {"playing": True, "pressed": True, "status": "playing"} and desk.pressed == [("k", 1)]


def test_a_video_that_already_plays_is_left_alone(monkeypatch):
    desk = Desk(monkeypatch, "playing")
    assert yt_keys.ensure_playing(wait_seconds=3) == {"playing": True, "pressed": False} and desk.pressed == []


class FakeArgs:
    def __init__(self, url):
        self._url = url

    def model_dump(self):
        return {"url": self._url}


def open_link(monkeypatch, url, started):
    monkeypatch.setattr(apps, "_reuse_youtube_window", lambda u: None)
    monkeypatch.setattr(apps.webbrowser, "open", lambda u: True)
    monkeypatch.setattr(apps, "_nudge_youtube_playback", lambda video_id, wait_seconds=4.0: started)
    monkeypatch.setattr(apps, "window_check", lambda **kw: (True, {"windows": ["x"]}))
    tool = apps.OpenUrlTool(ToolContext())
    args = tool.validate_args({"url": url})
    result = tool.execute(args)
    return result, tool.verify(args, result)


def test_a_watch_link_is_opened_and_started(monkeypatch):
    result, ver = open_link(monkeypatch, "https://www.youtube.com/watch?v=abc123", started=True)
    assert result.output["is_video"] and result.output["playback_started"] and ver.passed


def test_a_watch_link_that_did_not_start_is_not_called_done(monkeypatch):
    result, ver = open_link(monkeypatch, "https://www.youtube.com/watch?v=abc123", started=False)
    assert result.success and not ver.passed and "did not start" in ver.details


def test_the_youtube_home_page_and_other_sites_are_just_opened(monkeypatch):
    for url in ("https://www.youtube.com/", "https://example.com/watch?v=1"):
        result, ver = open_link(monkeypatch, url, started=False)
        assert "is_video" not in result.output and ver.passed

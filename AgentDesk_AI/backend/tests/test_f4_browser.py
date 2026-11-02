"""F4: the rebuilt browser bridge. Spoken commands for the new YouTube / website controls, the tool's checks, which browser the app talks to when two are
connected, the native-messaging host, and "play X on YouTube" through the extension. The real extension in a real Edge is scripts via frontend/e2e/f4_live.mjs."""
from __future__ import annotations

import json
import os
import struct
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from app.ai.browser_commands import youtube_player_plan
from app.browser_bridge import STALE_SECONDS, bridge
from app.tools import apps
from app.tools.base import RiskLevel, ToolContext
from app.tools.browser import BrowserControlArgs, BrowserControlTool, QUALITIES

ROOT = Path(__file__).resolve().parents[2]


def plan(text):
    p = youtube_player_plan(text)
    if p is None:
        return None
    a = p.actions[0]
    assert a.tool == "control_browser"
    return {k: v for k, v in a.args.items() if k != "target"}, a.args["target"]


# ------------------------------------------------------------------------------------------------ spoken commands
@pytest.mark.parametrize("text,expected", [
    ("previous video", {"action": "previous"}), ("play the previous video", {"action": "previous"}), ("pichli video chalao", {"action": "previous"}),
    ("theatre mode", {"action": "theatre", "enable": True}), ("turn off theater mode", {"action": "theatre", "enable": False}),
    ("turn on captions", {"action": "captions", "enable": True}), ("subtitles off", {"action": "captions", "enable": False}),
    ("set quality to 1080p", {"action": "quality", "quality": "hd1080"}), ("quality auto", {"action": "quality", "quality": "auto"}), ("play in 720p", {"action": "quality", "quality": "hd720"}),
    ("loop this video", {"action": "loop", "enable": True}), ("turn off loop", {"action": "loop", "enable": False}),
    ("skip the ad", {"action": "skip_ad"}), ("like this video", {"action": "like"}), ("subscribe to this channel", {"action": "subscribe"}),
    ("what's playing", {"action": "now_playing"}), ("which song is this", {"action": "now_playing"}), ("yeh kaun sa gana hai", {"action": "now_playing"}),
])
def test_youtube_extras_are_understood(text, expected):
    got, target = plan(text)
    assert got == expected and target == "youtube"


@pytest.mark.parametrize("text,expected", [
    ("read this page", {"action": "read_page"}), ("click the link Sign In", {"action": "click_link", "name": "Sign In"}),
    ("fill Zain Bilal in the name field", {"action": "fill", "field": "name", "text": "Zain Bilal"}),
    ("fill the Search box with Hello World.", {"action": "fill", "field": "Search", "text": "Hello World"}),
    ("open result 3 on google", {"action": "web_click_result", "index": 3}), ("read the google search results", {"action": "web_results"}),
    ("scroll down the page", {"action": "web_scroll", "amount": 1}), ("scroll up this page", {"action": "web_scroll", "amount": -1}),
    ("find bookmarks for python", {"action": "bookmarks", "query": "python"}), ("search my history for biryani", {"action": "history", "query": "biryani"}),
    ("reopen the last closed tab", {"action": "reopen"})])
def test_website_commands_target_the_tab_in_front(text, expected):
    got, target = plan(text)
    assert got == expected and target == "active"


@pytest.mark.parametrize("text", ["open chrome", "volume down", "scroll down", "scroll up", "click save", "type hello", "fill it in", "delete this page", "close the tab"])
def test_ordinary_system_commands_are_not_taken_by_the_browser(text):
    assert plan(text) is None or plan(text)[0]["action"] not in {"web_scroll", "fill", "click_link", "read_page"}


# ---------------------------------------------------------------------------------------------------- the tool
def test_arguments_need_what_the_action_needs():
    for bad in ({"action": "quality"}, {"action": "quality", "quality": "ultra"}, {"action": "fill", "field": "name"}, {"action": "click_link"}, {"action": "web_scroll"},
                {"action": "web_click_result"}):
        with pytest.raises(ValueError):
            BrowserControlArgs.model_validate(bad)
    ok = BrowserControlArgs.model_validate({"action": "read_page"})
    assert ok.target == "active", "a website action works on the tab in front, not the YouTube default"
    assert BrowserControlArgs.model_validate({"action": "quality", "quality": "hd720"}).quality in QUALITIES


def test_risk_subscribing_filling_and_clicking_ask_first_the_rest_do_not():
    tool = BrowserControlTool(ToolContext())
    risk = lambda **kw: tool.risk_for_args(tool.validate_args(kw))   # noqa: E731
    assert risk(action="like") == RiskLevel.LOW and risk(action="read_page") == RiskLevel.LOW and risk(action="theatre") == RiskLevel.LOW
    assert risk(action="subscribe") == RiskLevel.MEDIUM and risk(action="fill", field="name", text="x") == RiskLevel.MEDIUM
    assert risk(action="click_link", name="Pricing") == RiskLevel.MEDIUM


def fake_extension(monkeypatch, tabs, replies, capabilities=("inspect", "like", "read_page", "fill", "bookmarks", "reopen", "history", "web_scroll", "click_link")):
    calls = []

    def request(action, **kw):
        calls.append((action, kw))
        if action == "inspect":
            return {"success": True, "tabs": tabs}
        reply = replies.get(action)
        return reply(kw) if callable(reply) else (reply or {"success": False, "error": "unexpected " + action})
    monkeypatch.setattr(bridge, "request", request)
    monkeypatch.setattr(bridge, "clients", {"c": None})
    monkeypatch.setattr(bridge, "info", {"c": {"version": "2.0.0", "capabilities": list(capabilities)}})
    monkeypatch.setattr(bridge, "seen", {})
    return calls


TABS = [{"id": 5, "title": "Shop", "url": "https://example.com/form", "active": True}, {"id": 6, "title": "Video", "url": "https://www.youtube.com/watch?v=a", "active": False}]


def run(tool, **raw):
    args = tool.validate_args(raw)
    result = tool.execute(args)
    return result, (tool.verify(args, result) if result.success else None)


def test_a_website_action_goes_to_the_active_tab_and_is_checked_from_the_page(monkeypatch):
    calls = fake_extension(monkeypatch, TABS, {"fill": {"success": True, "filled_chars": 10, "field": "name", "url": "https://example.com/form"}})
    tool = BrowserControlTool(ToolContext())
    result, ver = run(tool, action="fill", field="name", text="Zain Bilal")
    assert result.success and ver.passed
    sent = next(kw for action, kw in calls if action == "fill")
    assert sent["tab_id"] == 5 and sent["field"] == "name" and sent["text"] == "Zain Bilal"
    result, ver = run(tool, action="fill", field="name", text="Zain")          # the page says 9 characters are in the field, not 4
    assert result.success and not ver.passed


def test_liking_needs_a_youtube_tab_and_the_page_to_show_it_liked(monkeypatch):
    fake_extension(monkeypatch, TABS, {"like": {"success": True, "liked": True, "already_liked": False}})
    tool = BrowserControlTool(ToolContext())
    result, ver = run(tool, action="like")
    assert result.success and ver.passed and result.output["spoken"] == "Liked."
    fake_extension(monkeypatch, [TABS[0]], {"like": {"success": True, "liked": True}})
    result, _ = run(tool, action="like")
    assert not result.success                                                  # no YouTube tab: nothing else is touched


def test_an_old_extension_is_told_to_update_for_the_new_controls(monkeypatch):
    fake_extension(monkeypatch, TABS, {}, capabilities=("inspect", "seek"))
    result, _ = run(BrowserControlTool(ToolContext()), action="read_page")
    assert not result.success and "older than" in result.error


def test_bookmarks_and_history_need_results_to_be_called_done(monkeypatch):
    fake_extension(monkeypatch, TABS, {"bookmarks": {"success": True, "results": [{"title": "Python", "url": "https://python.org"}]}, "history": {"success": False, "error": "Nothing in the history matches."}})
    tool = BrowserControlTool(ToolContext())
    result, ver = run(tool, action="bookmarks", query="python")
    assert result.success and ver.passed and "Python" in result.output["spoken"]
    result, _ = run(tool, action="history", query="zzz")
    assert not result.success and "Nothing" in result.error


# -------------------------------------------------------------------------------- which browser the app talks to
def two_browsers(monkeypatch, edge_focus=None, chrome_focus=None, ages=None):
    monkeypatch.setattr(bridge, "clients", {"edge": ("s", None), "chrome": ("s", None)})
    monkeypatch.setattr(bridge, "info", {"edge": {"browser": "edge", "version": "2.0.0", "focused_at": edge_focus}, "chrome": {"browser": "chrome", "version": "2.0.0", "focused_at": chrome_focus}})
    now = time.monotonic()
    monkeypatch.setattr(bridge, "seen", {"edge": now - (ages or {}).get("edge", 1), "chrome": now - (ages or {}).get("chrome", 1)})


def test_with_two_browsers_the_one_used_last_is_chosen(monkeypatch):
    two_browsers(monkeypatch, edge_focus=1000, chrome_focus=2000)
    assert bridge.choose() == "chrome"
    two_browsers(monkeypatch, edge_focus=3000, chrome_focus=2000)
    assert bridge.choose() == "edge"


def test_a_named_browser_wins_and_an_undecidable_pair_is_refused(monkeypatch):
    two_browsers(monkeypatch, edge_focus=1000, chrome_focus=2000)
    assert bridge.choose("edge") == "edge"
    two_browsers(monkeypatch)
    assert bridge.choose() is None
    assert "Multiple" in bridge.request("inspect")["error"]


def test_a_silent_client_is_dropped(monkeypatch):
    two_browsers(monkeypatch, edge_focus=1000, chrome_focus=2000, ages={"chrome": STALE_SECONDS + 5})
    assert bridge.choose() == "edge" and set(bridge.clients) == {"edge"}


def test_status_lists_every_browser(client, monkeypatch):
    two_browsers(monkeypatch, edge_focus=1000, chrome_focus=2000)
    data = client.get("/browser/status").json()
    assert data["connected"] and data["profiles"] == 2 and {c["browser"] for c in data["clients"]} == {"edge", "chrome"} and data["ambiguous"] is False
    two_browsers(monkeypatch)
    assert client.get("/browser/status").json()["ambiguous"] is True


# ------------------------------------------------------------------------------------ play X on YouTube
def test_play_through_the_extension_clicks_the_first_real_result(monkeypatch):
    seen = []

    def request(action, **kw):
        seen.append((action, kw))
        if action == "open":
            return {"success": True, "tab_id": 9}
        if action == "inspect":
            return {"success": True, "tabs": [{"id": 9, "url": "https://www.youtube.com/results?search_query=atif+aslam"}]}
        if action == "results":
            return {"success": True, "results": ["Atif Aslam - Tera Hone Laga Hoon", "Other"]}
        if action == "click_result":
            return {"success": True, "clicked_title": "Atif Aslam - Tera Hone Laga Hoon", "playing": True, "url": "https://www.youtube.com/watch", "video_id": "abc"}
    monkeypatch.setattr(bridge, "request", request)
    monkeypatch.setattr(bridge, "clients", {"c": None})
    monkeypatch.setattr(bridge, "info", {"c": {"version": "2.0.0", "capabilities": ["open", "click_result", "results"]}})
    out = apps._play_through_extension("atif aslam songs", "video")
    assert out["via"] == "extension" and out["playback_confirmed"] is True and out["title"].startswith("Atif Aslam")
    assert [a for a, _ in seen] == ["open", "inspect", "results", "click_result"] and seen[3][1]["index"] == 1
    assert "search_query=atif+aslam+songs" in seen[0][1]["url"]
    assert "sp=EgIQAw%3D%3D" in (lambda: (seen.clear(), apps._play_through_extension("lofi", "playlist"), seen[0][1]["url"])[2])()


def test_without_a_usable_extension_the_older_way_is_used(monkeypatch):
    monkeypatch.setattr(bridge, "clients", {})
    assert apps._play_through_extension("x song", "video") is None
    monkeypatch.setattr(bridge, "clients", {"c": None})
    monkeypatch.setattr(bridge, "info", {"c": {"capabilities": ["inspect"]}})
    assert apps._play_through_extension("x song", "video") is None


# ---------------------------------------------------------------------------------------- the native host
def frame(message) -> bytes:
    data = json.dumps(message).encode()
    return struct.pack("<I", len(data)) + data


def test_the_native_host_is_a_pipe_with_the_extensions_origin():
    websockets_sync = pytest.importorskip("websockets.sync.server")
    seen = {}
    ready = threading.Event()

    def handler(ws):
        seen["origin"] = ws.request.headers.get("Origin")
        seen["first"] = json.loads(ws.recv())
        ws.send(json.dumps({"ready": True}))
        ws.send(json.dumps({"id": "1", "action": "inspect"}))
        seen["reply"] = json.loads(ws.recv())

    server = websockets_sync.serve(handler, "127.0.0.1", 0)
    port = server.socket.getsockname()[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    env = {**os.environ, "AGENTDESK_WS": f"ws://127.0.0.1:{port}/browser/ws"}
    host = subprocess.Popen([sys.executable, str(ROOT / "browser-extension" / "native" / "agentdesk_host.py"), "chrome-extension://abcdefghijklmnop/"],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, env=env)
    try:
        host.stdin.write(frame({"token": "t", "version": "2.0.0", "capabilities": ["inspect"]}))
        host.stdin.flush()

        def read():
            header = host.stdout.read(4)
            return json.loads(host.stdout.read(struct.unpack("<I", header)[0]))
        assert read() == {"ready": True}
        assert read() == {"id": "1", "action": "inspect"}
        host.stdin.write(frame({"id": "1", "result": {"success": True}}))
        host.stdin.flush()
        deadline = time.time() + 5
        while "reply" not in seen and time.time() < deadline:
            time.sleep(0.05)
        assert seen["origin"] == "chrome-extension://abcdefghijklmnop" and seen["first"]["token"] == "t"
        assert seen["reply"] == {"id": "1", "result": {"success": True}}
    finally:
        host.kill()
        server.shutdown()


def test_the_native_host_says_why_when_the_app_is_not_running():
    env = {**os.environ, "AGENTDESK_WS": "ws://127.0.0.1:1/browser/ws"}
    host = subprocess.run([sys.executable, str(ROOT / "browser-extension" / "native" / "agentdesk_host.py"), "chrome-extension://x/"], input=frame({"token": "t"}),
                          capture_output=True, env=env, timeout=30)
    size = struct.unpack("<I", host.stdout[:4])[0]
    assert "cannot reach" in json.loads(host.stdout[4:4 + size])["host_error"] and host.returncode == 2


def test_the_extension_id_in_the_native_manifest_comes_from_the_key():
    import base64
    import hashlib
    key = json.loads((ROOT / "browser-extension" / "manifest.json").read_text(encoding="utf-8"))["key"]
    digest = hashlib.sha256(base64.b64decode(key)).digest()[:16]
    ident = "".join(chr(97 + (b >> 4)) + chr(97 + (b & 15)) for b in digest)
    assert len(ident) == 32 and ident.isalpha() and ident == "ibfgillldmdknbebbfplonomofpmakio"

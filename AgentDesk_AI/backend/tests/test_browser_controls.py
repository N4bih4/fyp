import concurrent.futures
import pytest
from starlette.websockets import WebSocketDisconnect
from app.ai.browser_commands import browser_plan
from app.browser_bridge import bridge
from app.tools.browser import BrowserControlTool, select_tabs


@pytest.mark.parametrize("text,action,target", [
    ("یوٹیوب کروم میں کلی ہوئی ہے وہ والا ٹیب بند کرو", "close", "youtube"),
    ("youtube chrome mein khuli hui hai woh wala tab band kar do", "close", "youtube"),
    ("YouTube in Chrome tab close", "close", "youtube"),
    ("video pause kar do", "pause", "youtube"),
    ("video rok do", "pause", "youtube"),
    ("video chala do", "resume", "youtube"),
    ("یہ ویڈیو روک دو", "pause", "youtube"),
    ("वीडियो चला दो", "resume", "youtube"),
    ("Google Drive ka tab band kar do", "close", "google drive"),
    ("YouTube ka tab band kar do", "close", "youtube"),
    ("گوگل ڈرائیو کا ٹیب بند کر دو", "close", "google drive"),
    ("गूगल ड्राइव का टैब बंद कर दो", "close", "google drive"),
])
def test_local_browser_command_variants(text, action, target):
    plan = browser_plan(text)
    assert plan and plan.actions[0].tool == "control_browser"
    assert plan.actions[0].args == {"action": action, "target": target}


@pytest.mark.parametrize("target", ["YouTube lecture", "YouTube and Gmail", "YouTube private video", "YouTube 123"])
def test_tab_descriptors_do_not_discard_meaningful_target_words(target):
    from app.ai.browser_commands import tab_target
    assert tab_target(target) == target


@pytest.mark.parametrize("command", ["اوپن یوٹیوب ان کروم", "open youtube in chrome", "یوٹیوب کروم میں کھولو", "ओपन यूट्यूब इन क्रोम"])
def test_explicit_chrome_open(command):
    # Hindi uses 'इन' for spoken English in.
    plan = browser_plan(command)
    assert plan and plan.actions[0].tool == "open_url"
    assert plan.actions[0].args == {"url": "https://www.youtube.com", "browser": "chrome"}


def test_chrome_open_uses_separate_arguments(ctx, monkeypatch):
    from app.tools.apps import OpenApplicationTool, OpenUrlTool
    calls = []
    monkeypatch.setattr(OpenApplicationTool, "_find_executable", lambda *_: "C:/Chrome/chrome.exe")
    monkeypatch.setattr("app.tools.apps._platform.launch_program", lambda executable, args: calls.append((executable, args)))
    tool = OpenUrlTool(ctx)
    result = tool.execute(tool.validate_args({"url": "https://www.youtube.com", "browser": "chrome"}))
    assert result.success
    assert calls == [("C:/Chrome/chrome.exe", ["https://www.youtube.com"])]


def test_explicit_chrome_missing_does_not_claim_default_browser_success(ctx, monkeypatch):
    from app.tools.apps import OpenApplicationTool, OpenUrlTool
    monkeypatch.setattr(OpenApplicationTool, "_find_executable", lambda *_: None)
    tool = OpenUrlTool(ctx)
    result = tool.execute(tool.validate_args({"url": "https://www.youtube.com", "browser": "chrome"}))
    assert not result.success and "Chrome" in result.error


def test_connected_old_extension_requires_reload_instead_of_wrong_profile_fallback(ctx, monkeypatch):
    from app.tools.apps import OpenUrlTool
    monkeypatch.setattr(bridge, "clients", {"test": object()})
    monkeypatch.setattr(bridge, "request", lambda *_args, **_kwargs: {"success": False, "error": "Unsupported browser command"})
    tool = OpenUrlTool(ctx)
    result = tool.execute(tool.validate_args({"url": "https://www.youtube.com", "browser": "chrome"}))
    assert not result.success and "Reload" in result.error


def test_named_video_uses_local_youtube_lookup():
    plan = browser_plan("play Python tutorial on youtube")
    assert plan.actions[0].tool == "play_youtube_video"
    assert plan.actions[0].args == {"query": "Python tutorial"}


TABS = [
    {"id": 1, "title": "Drive", "url": "https://drive.google.com/drive/u/0/", "active": False},
    {"id": 2, "title": "Gmail", "url": "https://mail.google.com/mail/u/0/", "active": True},
    {"id": 3, "title": "Fake Drive", "url": "https://drive.google.com.evil.example/"},
]


def test_drive_matching_does_not_close_gmail_or_lookalike_domain():
    assert [t["id"] for t in select_tabs(TABS, "google drive")] == [1]


def test_close_uses_exact_inspected_id_and_url(ctx, monkeypatch):
    calls = []
    def request(action, **args):
        calls.append((action, args))
        return {"success": True, "tabs": TABS} if action == "inspect" else {"success": True, "closed": True}
    monkeypatch.setattr(bridge, "request", request)
    tool = BrowserControlTool(ctx)
    result = tool.execute(tool.validate_args({"action": "close", "target": "google drive"}))
    assert result.success
    assert calls[1] == ("close", {"tab_id": 1, "expected_url": TABS[0]["url"]})


def test_multiple_youtube_close_needs_choice(ctx, monkeypatch):
    calls = []
    def request(action, **args):
        calls.append(action)
        return {"success": True, "tabs": [{"id": i, "url": f"https://www.youtube.com/watch?v={i}", "title": str(i)} for i in (4, 5)]}
    monkeypatch.setattr(bridge, "request", request)
    tool = BrowserControlTool(ctx)
    result = tool.execute(tool.validate_args({"action": "close", "target": "youtube"}))
    assert not result.success and result.output["needs_confirmation"]
    assert calls == ["inspect"]


def test_disconnected_browser_never_falls_back_to_blind_hotkey(ctx, monkeypatch):
    monkeypatch.setattr(bridge, "request", lambda *_: {"success": False, "error": "extension not connected"})
    tool = BrowserControlTool(ctx)
    result = tool.execute(tool.validate_args({"action": "pause"}))
    assert not result.success and "extension" in result.error


def test_bridge_websocket_roundtrip_is_authenticated(client):
    token = client.get("/browser/connect-token", headers={"X-AgentX-Bridge": "1"}).json()["token"]
    assert client.get("/browser/connect-token").status_code == 403
    with client.websocket_connect("/browser/ws", headers={"Origin": "chrome-extension://test-extension"}) as socket:
        socket.send_json({"token": token})
        assert socket.receive_json() == {"ready": True}
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            result = pool.submit(bridge.request, "inspect")
            command = socket.receive_json()
            socket.send_json({"id": command["id"], "result": {"success": True, "tabs": TABS}})
            assert result.result(timeout=2)["tabs"] == TABS


def test_web_pages_cannot_connect_as_extension(client):
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/browser/ws", headers={"Origin": "https://example.com"}):
            pass


def test_local_tab_close_never_constructs_ai_provider(db, ctx, monkeypatch):
    from app.config import Settings
    from app.orchestration import executor
    from app.tools.registry import ToolRegistry
    monkeypatch.setattr(executor, "get_provider", lambda *_: pytest.fail("API used for tab close"))
    calls = []
    open_tabs = list(TABS)
    def request(action, **args):
        calls.append(action)
        if action == "close":
            open_tabs[:] = [t for t in open_tabs if t["id"] != args["tab_id"]]
            return {"success": True, "closed": True}
        return {"success": True, "tabs": list(open_tabs)}
    monkeypatch.setattr(bridge, "request", request)
    task = executor.start_task(db, "Google Drive ka tab band kar do", None, ToolRegistry(ctx), Settings(ai_provider="groq", groq_api_key=None))
    assert task.status == "completed"
    assert calls == ["inspect", "close", "inspect"]  # verify re-inspects: the tab must really be gone

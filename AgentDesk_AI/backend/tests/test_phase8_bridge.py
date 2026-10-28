"""Phase 8: bridge trust model and data handling. Uses mocked extension traffic only."""
from __future__ import annotations

import pytest
from starlette.websockets import WebSocketDisconnect

from app import main as app_main
from app.browser_bridge import bridge
from app.tools.browser import BrowserControlTool, _clean_tabs, public_tab


@pytest.fixture()
def secured(monkeypatch):
    monkeypatch.setattr(app_main, "get_api_token", lambda: "s3cret-token-value")


# ------------------------------------------------------------- bridge token
def test_connect_token_requires_api_token_when_auth_enabled(client, secured):
    header = {"X-AgentX-Bridge": "1"}
    assert client.get("/browser/connect-token", headers=header).status_code == 401
    assert client.get("/browser/connect-token", headers={**header, "Authorization": "Bearer wrong"}).status_code == 401
    ok = client.get("/browser/connect-token", headers={**header, "Authorization": "Bearer s3cret-token-value"})
    assert ok.status_code == 200 and len(ok.json()["token"]) >= 32


def test_connect_token_still_needs_bridge_header_even_with_api_token(client, secured):
    r = client.get("/browser/connect-token", headers={"Authorization": "Bearer s3cret-token-value"})
    assert r.status_code == 403


def test_bridge_status_remains_readable_without_token(client, secured):
    assert client.get("/browser/status").status_code == 200


def test_websocket_rejects_non_local_host(client):
    token = client.get("/browser/connect-token", headers={"X-AgentX-Bridge": "1"}).json()["token"]
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/browser/ws", headers={"Origin": "chrome-extension://x", "Host": "evil.example"}) as s:
            s.send_json({"token": token})
            s.receive_json()


def test_websocket_rejects_wrong_bridge_token(client):
    with client.websocket_connect("/browser/ws", headers={"Origin": "chrome-extension://x"}) as socket:
        socket.send_json({"token": "not-the-token"})
        with pytest.raises(WebSocketDisconnect):
            socket.receive_json()


# ------------------------------------------------------- spoofed / bad data
def test_clean_tabs_drops_malformed_records():
    raw = [
        {"id": 1, "title": "ok", "url": "https://a.example/x"},
        {"id": "2", "title": "string id"},
        {"id": True, "title": "bool id"},
        {"title": "no id"},
        "not a dict",
        None,
        {"id": 3, "title": "t" * 1000, "url": "u" * 5000},
    ]
    cleaned = _clean_tabs(raw)
    assert [t["id"] for t in cleaned] == [1, 3]
    assert len(cleaned[1]["title"]) == 300 and len(cleaned[1]["url"]) == 2000
    assert _clean_tabs("garbage") == [] and _clean_tabs(None) == []


def test_spoofed_malformed_inspect_does_not_crash_tool(ctx, monkeypatch):
    monkeypatch.setattr(bridge, "request", lambda action, **a: {"success": True, "tabs": [{"title": "no id"}, 5, None]})
    tool = BrowserControlTool(ctx)
    result = tool.execute(tool.validate_args({"action": "close", "target": "youtube"}))
    assert result.success is False and "Matching tab nahi mila" in result.error


def test_public_tab_strips_query_and_fragment():
    tab = public_tab({"id": 1, "title": "x", "url": "https://mail.example/inbox?token=SECRET&q=private#frag"})
    assert tab["url"] == "https://mail.example/inbox"
    assert "SECRET" not in str(tab)
    assert public_tab({"id": 2, "url": "not a url"})["url"] == ""


def test_inspect_output_hides_query_but_close_uses_full_url(ctx, monkeypatch):
    full = "https://www.youtube.com/watch?v=abc&session=SECRET"
    sent = []

    def request(action, **args):
        sent.append((action, args))
        if action == "inspect":
            return {"success": True, "tabs": [{"id": 9, "title": "Video", "url": full}]}
        return {"success": True, "closed": True, "internal_debug": "should not leak"}

    monkeypatch.setattr(bridge, "request", request)
    tool = BrowserControlTool(ctx)
    inspected = tool.execute(tool.validate_args({"action": "inspect"}))
    assert inspected.output["tabs"][0]["url"] == "https://www.youtube.com/watch"
    assert "SECRET" not in str(inspected.output)

    closed = tool.execute(tool.validate_args({"action": "close", "target": "youtube"}))
    assert closed.success
    assert sent[-1] == ("close", {"tab_id": 9, "expected_url": full})  # exact URL still guards the close
    assert "internal_debug" not in closed.output and "SECRET" not in str(closed.output)


def test_unverified_close_is_reported_as_failure(ctx, monkeypatch):
    def request(action, **args):
        if action == "inspect":
            return {"success": True, "tabs": [{"id": 1, "title": "Drive", "url": "https://drive.google.com/"}]}
        return {"success": True}  # extension claims success without confirming `closed`

    monkeypatch.setattr(bridge, "request", request)
    tool = BrowserControlTool(ctx)
    result = tool.execute(tool.validate_args({"action": "close", "target": "google drive"}))
    assert result.success is False and "verify" in result.error


def test_bridge_refuses_when_two_profiles_connected(monkeypatch):
    monkeypatch.setattr(bridge, "clients", {"a": object(), "b": object()})
    result = bridge.request("inspect")
    assert result["success"] is False and "Multiple" in result["error"]

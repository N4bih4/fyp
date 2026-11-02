"""Authenticated local connection to the user-installed browser extension."""
import asyncio
import concurrent.futures
import json
import secrets
import threading
import time
import uuid
from functools import lru_cache
from fastapi import APIRouter, Header, HTTPException, WebSocket, WebSocketDisconnect

from .logging_setup import log_event

router = APIRouter(prefix="/browser")


@lru_cache(maxsize=1)
def expected_version() -> str:
    """Version of the extension files shipped with this backend (browser-extension/manifest.json)."""
    from .runtime import resource_root

    try:
        return json.loads((resource_root() / "browser-extension" / "manifest.json").read_text(encoding="utf-8"))["version"]
    except (OSError, ValueError, KeyError):
        return "0"


def _version_tuple(value: str) -> tuple[int, ...]:
    try:
        return tuple(int(part) for part in str(value).split("."))
    except ValueError:
        return (0,)


STALE_SECONDS = 60   # the extension pings every 15 s; a client silent for a minute is gone (its worker slept or the browser closed)


class BrowserBridge:
    def __init__(self):
        self.token = secrets.token_urlsafe(32)
        self.clients = {}
        self.info = {}  # client_id -> {"version", "capabilities", "browser", "focused_at"} sent by the extension when it connects and with each heartbeat
        self.seen = {}  # client_id -> monotonic time of the last message (a client silent for STALE_SECONDS is dropped)
        self.pending = {}
        self.lock = threading.RLock()

    def _drop_stale(self) -> None:
        now = time.monotonic()
        for client_id in [c for c, t in self.seen.items() if now - t > STALE_SECONDS and c in self.clients]:
            self.clients.pop(client_id, None)
            self.info.pop(client_id, None)
            self.seen.pop(client_id, None)

    def choose(self, browser: str | None = None):
        """The client to talk to: the only one; else the requested browser; else the browser the user focused last. None = cannot decide."""
        with self.lock:
            self._drop_stale()
            if len(self.clients) == 1:
                return next(iter(self.clients))
            if len(self.clients) < 2:
                return None
            if browser:
                same = [c for c in self.clients if (self.info.get(c) or {}).get("browser") == browser]
                if len(same) == 1:
                    return same[0]
            focus = {c: (self.info.get(c) or {}).get("focused_at") for c in self.clients}
            known = {c: t for c, t in focus.items() if isinstance(t, (int, float))}
            if known:
                best = max(known.values())
                winners = [c for c, t in known.items() if t == best]
                if len(winners) == 1:
                    return winners[0]
            return None

    def client_info(self) -> dict:
        """Version/capabilities of the extension in use ({} if none or ambiguous).
        Extensions older than 1.1 send neither: they support inspect/close/pause/resume only."""
        with self.lock:
            chosen = self.choose()
            return dict(self.info.get(chosen, {})) if chosen is not None else {}

    def supports(self, capability: str) -> bool:
        return capability in self.client_info().get("capabilities", ())

    def outdated(self) -> bool:
        info = self.client_info()
        return bool(info) and _version_tuple(info.get("version", "0")) < _version_tuple(expected_version())

    def request(self, action, browser=None, wait=8, **args):
        with self.lock:
            self._drop_stale()
            if not self.clients:
                return {"success": False, "error": "Browser extension connect nahi hai. Chrome/Edge mein Agent X Browser Bridge load karein (popup mein status dekhein)."}
            client_id = self.choose(browser)
            if client_id is None:
                return {"success": False, "error": "Multiple browser profiles connected hain aur main nahi jaan sakta kaun sa use karna hai: jis browser mein kaam karna hai usay ek baar click karke front mein layein, ya ek hi mein extension on rakhein."}
            socket, loop = self.clients[client_id]
            call_id = uuid.uuid4().hex
            future = concurrent.futures.Future()
            self.pending[call_id] = (client_id, future)
        async def send():
            try:
                await socket.send_json({"id": call_id, "action": action, **args})
            except Exception:
                if not future.done():
                    future.set_result({"success": False, "error": "Browser disconnect ho gaya; command repeat nahi hui."})
        asyncio.run_coroutine_threadsafe(send(), loop)
        try:
            return future.result(timeout=wait)
        except concurrent.futures.TimeoutError:
            return {"success": False, "error": "Browser response timeout. Tab state check karein; action automatically repeat nahi hui."}
        finally:
            with self.lock:
                self.pending.pop(call_id, None)


bridge = BrowserBridge()


@router.get("/status")
def status():
    """What the diagnostics (scripts/diagnose_extension.ps1) and the Settings page read: every connected browser with its version and how recently it was heard."""
    with bridge.lock:
        bridge._drop_stale()
        now = time.monotonic()
        clients = [{"browser": (bridge.info.get(c) or {}).get("browser"), "version": (bridge.info.get(c) or {}).get("version"),
                    "heard_seconds_ago": round(now - bridge.seen.get(c, now), 1), "focused": (bridge.info.get(c) or {}).get("focused_at") is not None}
                   for c in bridge.clients]
    info = bridge.client_info()
    return {"connected": bool(clients), "profiles": len(clients), "clients": clients, "version": info.get("version"),
            "expected_version": expected_version(), "outdated": bridge.outdated(), "ambiguous": len(clients) > 1 and not info}


@router.get("/connect-token")
def connect_token(x_agentx_bridge: str | None = Header(default=None)):
    # Custom header blocks simple cross-site requests; existing CORS policy
    # permits only the local app. Installed extensions require localhost access.
    if x_agentx_bridge != "1":
        raise HTTPException(status_code=403, detail="Extension connection only")
    return {"token": bridge.token}


@router.websocket("/ws")
async def browser_socket(socket: WebSocket):
    origin = socket.headers.get("origin", "")
    raw_host = socket.headers.get("host", "")
    host = raw_host.rsplit(":", 1)[0] if not raw_host.startswith("[") else "[::1]"
    if not origin.startswith("chrome-extension://") or host.lower() not in {"127.0.0.1", "localhost", "[::1]", "testserver"}:
        await socket.close(code=1008)
        return
    await socket.accept()
    client_id = uuid.uuid4().hex
    try:
        auth = await asyncio.wait_for(socket.receive_json(), timeout=5)
        if not secrets.compare_digest(str(auth.get("token", "")), bridge.token):
            await socket.close(code=1008)
            return
        capabilities = auth.get("capabilities") if isinstance(auth.get("capabilities"), list) else ["inspect", "close", "pause", "resume"]
        info = {"version": str(auth.get("version") or "1.0.0")[:20], "capabilities": [str(c)[:20] for c in capabilities[:40]],
                "browser": str(auth.get("browser") or "")[:10] or None,
                "focused_at": auth.get("focused_at") if isinstance(auth.get("focused_at"), (int, float)) else None}
        with bridge.lock:
            bridge.clients[client_id] = (socket, asyncio.get_running_loop())
            bridge.info[client_id] = info
            bridge.seen[client_id] = time.monotonic()
        await socket.send_json({"ready": True})
        if _version_tuple(info["version"]) < _version_tuple(expected_version()) and "reload" in info["capabilities"]:
            # Updated extension files are on disk: ask the extension to load them (no manual Reload click).
            log_event("browser_extension_reload_requested", detail=f"{info['version']} -> {expected_version()}")
            await socket.send_json({"id": uuid.uuid4().hex, "action": "reload"})
        while True:
            message = await socket.receive_json()
            with bridge.lock:
                bridge.seen[client_id] = time.monotonic()
            if message.get("heartbeat"):
                if isinstance(message.get("focused_at"), (int, float)):
                    with bridge.lock:
                        bridge.info.get(client_id, {})["focused_at"] = message["focused_at"]
                await socket.send_json({"heartbeat": True})
                continue
            with bridge.lock:
                pending = bridge.pending.get(message.get("id"))
                if pending and pending[0] == client_id and not pending[1].done():
                    result = message.get("result")
                    pending[1].set_result(result if isinstance(result, dict) else {"success": False, "error": "Invalid browser response"})
    except (WebSocketDisconnect, asyncio.TimeoutError, ValueError):
        pass
    finally:
        with bridge.lock:
            bridge.clients.pop(client_id, None)
            bridge.info.pop(client_id, None)
            bridge.seen.pop(client_id, None)
            for owner, future in list(bridge.pending.values()):
                if owner == client_id and not future.done():
                    future.set_result({"success": False, "error": "Browser disconnected; action state verify karein."})

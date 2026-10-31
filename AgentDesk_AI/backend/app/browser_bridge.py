"""Authenticated local connection to the user-installed browser extension."""
import asyncio
import concurrent.futures
import json
import secrets
import threading
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


class BrowserBridge:
    def __init__(self):
        self.token = secrets.token_urlsafe(32)
        self.clients = {}
        self.info = {}  # client_id -> {"version", "capabilities"} sent by the extension when it connects
        self.pending = {}
        self.lock = threading.RLock()

    def client_info(self) -> dict:
        """Version/capabilities of the single connected extension ({} if none or ambiguous).
        Extensions older than 1.1 send neither: they support inspect/close/pause/resume only."""
        with self.lock:
            if len(self.clients) != 1:
                return {}
            return dict(self.info.get(next(iter(self.clients)), {}))

    def supports(self, capability: str) -> bool:
        return capability in self.client_info().get("capabilities", ())

    def outdated(self) -> bool:
        info = self.client_info()
        return bool(info) and _version_tuple(info.get("version", "0")) < _version_tuple(expected_version())

    def request(self, action, **args):
        with self.lock:
            if len(self.clients) != 1:
                return {"success": False, "error": "Browser extension connect nahi hai. Chrome/Edge mein Agent X Browser Bridge load karein." if not self.clients else "Multiple browser profiles connected hain. Sirf intended browser profile mein extension on rakhein."}
            client_id, (socket, loop) = next(iter(self.clients.items()))
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
            return future.result(timeout=8)
        except concurrent.futures.TimeoutError:
            return {"success": False, "error": "Browser response timeout. Tab state check karein; action automatically repeat nahi hui."}
        finally:
            with self.lock:
                self.pending.pop(call_id, None)


bridge = BrowserBridge()


@router.get("/status")
def status():
    info = bridge.client_info()
    return {"connected": len(bridge.clients) == 1, "profiles": len(bridge.clients),
            "version": info.get("version"), "expected_version": expected_version(), "outdated": bridge.outdated()}


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
        info = {"version": str(auth.get("version") or "1.0.0")[:20], "capabilities": [str(c)[:20] for c in capabilities[:20]]}
        with bridge.lock:
            bridge.clients[client_id] = (socket, asyncio.get_running_loop())
            bridge.info[client_id] = info
        await socket.send_json({"ready": True})
        if _version_tuple(info["version"]) < _version_tuple(expected_version()) and "reload" in info["capabilities"]:
            # Updated extension files are on disk: ask the extension to load them (no manual Reload click).
            log_event("browser_extension_reload_requested", detail=f"{info['version']} -> {expected_version()}")
            await socket.send_json({"id": uuid.uuid4().hex, "action": "reload"})
        while True:
            message = await socket.receive_json()
            if message.get("heartbeat"):
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
            for owner, future in list(bridge.pending.values()):
                if owner == client_id and not future.done():
                    future.set_result({"success": False, "error": "Browser disconnected; action state verify karein."})

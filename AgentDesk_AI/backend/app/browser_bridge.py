"""Authenticated local connection to the user-installed browser extension."""
import asyncio
import concurrent.futures
import secrets
import threading
import uuid
from fastapi import APIRouter, Header, HTTPException, WebSocket, WebSocketDisconnect

router = APIRouter(prefix="/browser")


class BrowserBridge:
    def __init__(self):
        self.token = secrets.token_urlsafe(32)
        self.clients = {}
        self.pending = {}
        self.lock = threading.RLock()

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
    return {"connected": len(bridge.clients) == 1, "profiles": len(bridge.clients)}


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
        with bridge.lock:
            bridge.clients[client_id] = (socket, asyncio.get_running_loop())
        await socket.send_json({"ready": True})
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
            for owner, future in list(bridge.pending.values()):
                if owner == client_id and not future.done():
                    future.set_result({"success": False, "error": "Browser disconnected; action state verify karein."})

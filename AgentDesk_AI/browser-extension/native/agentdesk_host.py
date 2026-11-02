#!/usr/bin/env python3
"""Native messaging host for the Agent X Browser Bridge.

The browser starts this program when the extension calls connectNative('com.agentdesk.bridge') and keeps the extension's service worker alive while the
connection is open. It is a plain pipe: JSON messages from the extension (length-prefixed on stdin) go to the app's WebSocket, and the app's messages go back
(length-prefixed on stdout). It decides nothing and holds no secret: the pairing token is inside the extension's first message, and the app checks it.

    agentdesk_host.py chrome-extension://<id>/       (the browser passes the caller's origin; the app only accepts extension origins)
Environment: AGENTDESK_WS overrides the address (default ws://127.0.0.1:8000/browser/ws).
"""
from __future__ import annotations

import json
import os
import struct
import sys
import threading

URL = os.environ.get("AGENTDESK_WS", "ws://127.0.0.1:8000/browser/ws")
MAX_MESSAGE = 1024 * 1024


def read_message(stream=None):
    stream = stream or sys.stdin.buffer
    header = stream.read(4)
    if len(header) < 4:
        return None
    (length,) = struct.unpack("<I", header)
    if length > MAX_MESSAGE:
        return None
    body = stream.read(length)
    return json.loads(body.decode("utf-8")) if len(body) == length else None


def write_message(message, stream=None) -> None:
    stream = stream or sys.stdout.buffer
    data = json.dumps(message, ensure_ascii=False).encode("utf-8")
    stream.write(struct.pack("<I", len(data)) + data)
    stream.flush()


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    origin = next((a for a in argv if a.startswith("chrome-extension://")), "").rstrip("/")
    first = read_message()
    if first is None:
        return 1
    try:
        from websockets.sync.client import connect
        ws = connect(URL, additional_headers={"Origin": origin} if origin else None, open_timeout=5, max_size=MAX_MESSAGE)
    except Exception as exc:  # noqa: BLE001 - tell the extension why, then end: it falls back to its own WebSocket
        write_message({"host_error": f"cannot reach {URL}: {type(exc).__name__}"})
        return 2
    ws.send(json.dumps(first))

    def from_extension() -> None:
        try:
            while True:
                message = read_message()
                if message is None:
                    break
                ws.send(json.dumps(message))
        except Exception:  # noqa: BLE001
            pass
        finally:
            try:
                ws.close()
            except Exception:  # noqa: BLE001
                pass

    threading.Thread(target=from_extension, daemon=True).start()
    try:
        for raw in ws:
            write_message(json.loads(raw))
    except Exception:  # noqa: BLE001 - the app closed the link
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Test-only: a slow local file server with HTTP Range support, and a download tool
that may reach it (the product tool refuses local hosts; this subclass is never registered)."""
from __future__ import annotations

import hashlib
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from app.tools import web
from app.tools.web import DownloadWebContentTool

PAYLOAD = bytes(range(256)) * 8192          # 2 MiB, deterministic
PAYLOAD_SHA = hashlib.sha256(PAYLOAD).hexdigest()
CHUNK = 64 * 1024


class LocalDownloadTool(DownloadWebContentTool):
    def execute(self, args):
        with patch.object(web, "_validate_public_url", lambda url: None), \
                patch.object(web, "_require_public_peer", lambda response: None):
            return super().execute(args)


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):  # noqa: N802
        server = self.server
        server.requests.append(dict(self.headers))
        start = 0
        rng = self.headers.get("Range")
        if rng and server.ranges:
            start = int(rng.split("=")[1].split("-")[0])
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{len(PAYLOAD) - 1}/{len(PAYLOAD)}")
        else:
            self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(len(PAYLOAD) - start))
        self.send_header("ETag", '"v1"')
        self.end_headers()
        try:
            for offset in range(start, len(PAYLOAD), CHUNK):
                self.wfile.write(PAYLOAD[offset:offset + CHUNK])
                self.wfile.flush()
                time.sleep(server.delay)
        except (BrokenPipeError, ConnectionResetError):
            pass


def serve(delay: float = 0.05, ranges: bool = True) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    server.delay, server.ranges, server.requests = delay, ranges, []
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    server.url = f"http://127.0.0.1:{server.server_address[1]}/big.bin"
    return server

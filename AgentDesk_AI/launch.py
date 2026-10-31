"""Single-click local startup; serves the built UI and API together."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import Request, urlopen
import webbrowser

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
LOGS = ROOT / "logs"
URL = "http://127.0.0.1:8000"


def api_token() -> str:
    """Per-user local API token (same file the backend reads)."""
    sys.path.insert(0, str(BACKEND))
    from app.security.token import load_or_create_token
    return load_or_create_token()


def ui_url() -> str:
    # The token travels in the URL fragment, which browsers never send to the server.
    return URL + "/#token=" + api_token()


def ready() -> bool:
    try:
        with urlopen(URL + "/health", timeout=2) as response:
            if json.load(response).get("status") != "ok":
                return False
        request = Request(URL + "/config/status", headers={"Authorization": "Bearer " + api_token()})
        with urlopen(request, timeout=2) as response:
            data = json.load(response)
            if "ai_provider" not in data:
                return False
        with urlopen(URL + "/", timeout=2) as response:
            return b'<div id="root">' in response.read(65536)
    except (OSError, URLError, ValueError):
        return False


def port_busy() -> bool:
    with socket.socket() as sock:
        sock.settimeout(1)
        return sock.connect_ex(("127.0.0.1", 8000)) == 0


def python_path() -> Path:
    # The backend environment contains the Windows hardware dependencies;
    # the workspace/test environment may have only API and test packages.
    for candidate in (BACKEND / ".venv" / "Scripts" / "python.exe", ROOT.parent / ".venv" / "Scripts" / "python.exe", ROOT / ".venv" / "Scripts" / "python.exe", Path(sys.executable)):
        if candidate.is_file():
            return candidate
    raise RuntimeError("Python runtime nahi mila. Virtual environment setup karein.")


def supervise() -> int:
    """Hold a local lock, restart a crashed server, and keep diagnostic logs."""
    # A separate port is a process-lifetime lock, released automatically on exit.
    with socket.socket() as lock:
        try:
            lock.bind(("127.0.0.1", 18000))
        except OSError:
            return 0
        lock.listen(1)
        if port_busy():
            return 0
        LOGS.mkdir(exist_ok=True)
        for attempt in range(4):
            with (LOGS / "backend.log").open("a", encoding="utf-8") as log:
                log.write(f"\nStarting backend, attempt {attempt + 1}\n")
                log.flush()
                child = subprocess.Popen([str(python_path()), "-u", "run_server.py"], cwd=BACKEND,
                                         stdout=log, stderr=log, stdin=subprocess.DEVNULL,
                                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                result = child.wait()
                log.write(f"Backend exited with code {result}\n")
            if result == 0 or port_busy():
                return result
            time.sleep(min(2 ** attempt, 8))
    return 1


def ensure_backend(timeout: float = 45) -> bool:
    """Start the supervised backend if needed and wait until it serves the UI. Shared by the
    browser launcher and the desktop shell (desktop/shell.py)."""
    if ready():
        return True
    if port_busy():
        return False
    LOGS.mkdir(exist_ok=True)
    flags = 0
    if os.name == "nt":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    with (LOGS / "launcher.log").open("a", encoding="utf-8") as log:
        subprocess.Popen([str(python_path()), str(Path(__file__).resolve()), "--supervise"], cwd=ROOT,
                         stdout=log, stderr=log, stdin=subprocess.DEVNULL, creationflags=flags)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if ready():
            return True
        time.sleep(1)
    return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--supervise", action="store_true")
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    if args.supervise:
        return supervise()
    if not (ROOT / "frontend" / "dist" / "index.html").is_file():
        print("Frontend build nahi mila. frontend folder mein npm.cmd run build chalayein.")
        return 1
    if ensure_backend():
        print("Agent X AI ready: " + URL)
        if not args.no_browser:
            webbrowser.open(ui_url())
        return 0
    if port_busy() and not ready():
        print("Port 8000 par koi purana ya doosra server chal raha hai. Use band karke dobara launcher kholein.")
        return 1
    print("Backend start nahi ho saka. logs/backend.log aur logs/launcher.log check karein.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

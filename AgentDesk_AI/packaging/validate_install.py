"""Validate a freshly INSTALLED copy of the app by running the shipped START_AGENT_X.cmd.

    python packaging/validate_install.py <path-to-extracted-AgentDesk-AI-folder> [--keep]

The server runs with USERPROFILE/HOME/LOCALAPPDATA redirected into a scratch folder, so "Documents",
the API token and the logs land there and nothing in the real user profile is touched. Uses port 8000
(the shipped port) and refuses to run if it is already in use. Needs `httpx` (any Python that has it).
Prints a PASS/FAIL line per check and exits non-zero on any failure. No Wi-Fi/Bluetooth/hardware actions.
"""
from __future__ import annotations

import argparse
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:8000"
results: list[tuple[bool, str]] = []


def check(ok: bool, label: str, detail: str = "") -> bool:
    results.append((ok, label))
    print(("PASS  " if ok else "FAIL  ") + label + (f"  [{detail}]" if detail and not ok else ""))
    return ok


def port_free(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) != 0


def stop_server(install: Path) -> None:
    """Kill only processes whose command line belongs to THIS install folder."""
    marker = str(install).replace("'", "''")
    script = ("Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -and $_.CommandLine.Contains('" + marker + "') -and "
              "$_.Name -match 'python' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }")
    subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True)
    time.sleep(1.5)


def start(install: Path, env: dict) -> subprocess.CompletedProcess:
    return subprocess.run(["cmd", "/c", str(install / "START_AGENT_X.cmd"), "--no-browser"], cwd=install, env=env,
                          capture_output=True, text=True, timeout=120, stdin=subprocess.DEVNULL)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("install")
    parser.add_argument("--keep", action="store_true")
    args = parser.parse_args()
    install = Path(args.install).resolve()
    if not (install / "START_AGENT_X.cmd").is_file() or not (install / "AgentDesk_AI" / "backend" / ".venv" / "Scripts" / "python.exe").is_file():
        print("Not an installed AgentDesk-AI folder (run INSTALL.cmd first).")
        return 2
    if not port_free(8000):
        print("Port 8000 is in use; stop the other instance first.")
        return 2

    sandbox = Path(tempfile.mkdtemp(prefix="agentdesk_clean_"))
    home, local = sandbox / "home", sandbox / "localappdata"
    (home / "Documents").mkdir(parents=True)
    local.mkdir()
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith(("AGENTDESK_", "AI_", "GROQ_", "OPENAI_", "GEMINI_", "DATABASE_"))}
    env.update(USERPROFILE=str(home), HOME=str(home), LOCALAPPDATA=str(local), APPDATA=str(sandbox / "roaming"))
    real_dir = Path(os.environ.get("LOCALAPPDATA", "")) / "AgentDesk"
    real_before = sorted(p.name for p in real_dir.rglob("*")) if real_dir.exists() else None
    backend = install / "AgentDesk_AI" / "backend"
    try:
        # 1. start through the shipped launcher
        started = start(install, env)
        check(started.returncode == 0, "START_AGENT_X.cmd --no-browser exits 0 once the server is ready", (started.stdout + started.stderr)[-300:])
        health = httpx.get(BASE + "/health", timeout=5)
        check(health.status_code == 200 and health.json()["status"] == "ok", "GET /health ok")
        page = httpx.get(BASE + "/", timeout=5)
        check(page.status_code == 200 and '<div id="root">' in page.text, "web UI is served from the install (prebuilt frontend)")
        asset = [p for p in page.text.split('"') if p.startswith("/assets/") and p.endswith(".js")]
        check(bool(asset) and httpx.get(BASE + asset[0], timeout=5).status_code == 200, "UI JavaScript bundle loads")

        # 2. access control with the token the installer-created setup generated
        token_file = local / "AgentDesk" / "api_token"
        check(token_file.is_file() and len(token_file.read_text().strip()) >= 32, "API token created in the (redirected) per-user folder")
        token = token_file.read_text().strip()
        auth = {"Authorization": f"Bearer {token}"}
        check(httpx.get(BASE + "/tasks", timeout=5).status_code == 401, "API refuses requests without the token")
        check(httpx.get(BASE + "/tasks", headers=auth, timeout=5).status_code == 200, "API accepts the token")
        config = httpx.get(BASE + "/config/status", headers=auth, timeout=5).json()
        check(config["ai_provider"] == "groq" and config["ai_configured"] is False, "default config: cloud AI present but NOT configured (no key shipped)")
        check(not any("gsk_" in str(v) for v in config.values()), "config response contains no key")

        # 3. a real local command end to end (no cloud AI needed), inside the sandbox home
        task = httpx.post(BASE + "/tasks", headers=auth, json={"command": "Create a folder called clean_install in Documents"}, timeout=30).json()
        check(task["status"] == "awaiting_approval" and task["actions"][0]["tool_name"] == "create_folder", "local command planned and waits for approval")
        target = home / "Documents" / "clean_install"
        check(not target.exists(), "nothing created before approval")
        httpx.post(f"{BASE}/tasks/{task['id']}/approve", headers=auth, json={"action_ids": [a["id"] for a in task["actions"]]}, timeout=30)
        done = httpx.post(f"{BASE}/tasks/{task['id']}/run", headers=auth, timeout=60).json()
        check(done["status"] == "completed" and target.is_dir(), "approved action executed and verified on disk", str(done.get("error")))
        check(done["actions"][0]["rollback_status"] == "available", "undo is available for the change")
        undone = httpx.post(f"{BASE}/tasks/{task['id']}/rollback", headers=auth, timeout=30).json()
        check(undone["actions"][0]["rollback_status"] == "done" and not target.exists(), "undo removed the folder (verified)")

        # 4. an unmatched command must not crash or call the cloud without a key
        joke = httpx.post(BASE + "/tasks", headers=auth, json={"command": "tell me something unrelated"}, timeout=30)
        check(joke.status_code == 200 and joke.json()["status"] in {"awaiting_input", "completed", "failed"}, "unmatched command handled gracefully", joke.text[:200])

        # 5. data lives inside the install / redirected profile
        db = backend / "agentdesk.db"
        check(db.is_file(), "database created next to the backend")
        check((local / "AgentDesk" / "logs" / "agentdesk.log").is_file(), "log file created in the (redirected) per-user folder")
        log_text = (local / "AgentDesk" / "logs" / "agentdesk.log").read_text(encoding="utf-8")
        check("clean_install" not in log_text and token not in log_text, "log has no command text and no token")
        check(sqlite3.connect(db).execute("PRAGMA user_version").fetchone()[0] >= 5, "database schema stamped")

        # 6. restart: history persists, second launch reuses nothing stale
        stop_server(install)
        check(port_free(8000), "server stops cleanly")
        started = start(install, env)
        check(started.returncode == 0, "restart through the launcher works")
        listing = httpx.get(BASE + "/tasks", headers=auth, timeout=5).json()
        check(any(t["id"] == task["id"] for t in listing), "task history survived the restart")

        # 7. nothing leaked into the real user profile
        real_after = sorted(p.name for p in real_dir.rglob("*")) if real_dir.exists() else None
        check(real_before == real_after, "real %LOCALAPPDATA%\\AgentDesk was not modified")
    finally:
        stop_server(install)
        if not args.keep:
            shutil.rmtree(sandbox, ignore_errors=True)
    failed = [label for ok, label in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

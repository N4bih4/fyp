#!/usr/bin/env python3
"""Server-side latency of local commands: POST /tasks round trip (understand + plan + validate + risk +,
for low risk, execute and verify), 30 runs, p50/p90. Speech recognition and speech output are NOT included.

    python scripts/latency_check.py [--runs 30]
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

COMMANDS = ["volume 40 kar do", "create a folder called Lat{i} in Documents", "notepad kholo", "dark mode laga do",
            "youtube band kar do", "brightness kam karo", "show trash", "downloads folder kholo",
            "close notepad", "ڈیسک ٹاپ پر کیا ہے دکھاؤ", "आवाज़ बढ़ाओ", "list tabs"]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=30)
    args = parser.parse_args(argv)
    root = Path(tempfile.mkdtemp(prefix="agentdesk_latency_"))
    home = root / "home"
    for sub in ("Documents", "Desktop", "Downloads"):
        (home / sub).mkdir(parents=True)
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    env = dict(os.environ, HOME=str(home), USERPROFILE=str(home), DATABASE_URL=f"sqlite:///{root / 'l.db'}",
               AGENTDESK_ALLOWED_DIRECTORIES=str(home), AGENTDESK_TOKEN_FILE=str(root / "tok"),
               AGENTDESK_LOG_DIR=str(root / "logs"), AI_PROVIDER="groq", GROQ_API_KEY="")
    server = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(port), "--log-level", "warning"],
                              cwd=Path(__file__).resolve().parents[1], env=env)
    url = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            try:
                if httpx.get(url + "/health").status_code == 200 and (root / "tok").exists():
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.2)
        headers = {"Authorization": "Bearer " + (root / "tok").read_text().strip()}
        times, statuses = [], {}
        for i in range(args.runs):
            command = COMMANDS[i % len(COMMANDS)].format(i=i)
            started = time.perf_counter()
            task = httpx.post(url + "/tasks", json={"command": command}, headers=headers, timeout=60).json()
            times.append(time.perf_counter() - started)
            statuses[task["status"]] = statuses.get(task["status"], 0) + 1
        times.sort()
        result = {"runs": len(times), "p50_s": round(statistics.median(times), 3),
                  "p90_s": round(times[int(0.9 * len(times)) - 1], 3), "max_s": round(times[-1], 3),
                  "under_2_5_s": sum(t < 2.5 for t in times), "statuses": statuses}
        print(json.dumps(result))
        return 0
    finally:
        server.terminate()
        server.wait(10)


if __name__ == "__main__":
    sys.exit(main())

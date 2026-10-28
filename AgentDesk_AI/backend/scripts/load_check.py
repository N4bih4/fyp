"""Repeatable load/latency check against a REAL server process (throwaway data, mock AI).

Usage:  python scripts/load_check.py
Starts uvicorn on a free local port with a temporary database and folders, runs the checks
below, prints a JSON summary and stops the server. Nothing outside the temp folder is touched.
Numbers describe this machine only; they are a baseline, not a guarantee.
"""
from __future__ import annotations

import concurrent.futures as cf
import json
import os
import socket
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import httpx

BACKEND = Path(__file__).resolve().parents[1]


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def pct(values: list[float], p: float) -> float:
    ordered = sorted(values)
    return round(ordered[min(len(ordered) - 1, int(len(ordered) * p))] * 1000, 1)


def summarise(times: list[float]) -> dict:
    return {"n": len(times), "p50_ms": pct(times, 0.5), "p95_ms": pct(times, 0.95), "max_ms": round(max(times) * 1000, 1)}


def main() -> int:
    work = Path(tempfile.mkdtemp(prefix="agentdesk_load_"))
    home = work / "home"
    (home / "Documents").mkdir(parents=True)
    db = work / "load.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db}", "AI_PROVIDER": "mock", "AGENTDESK_ALLOWED_DIRECTORIES": str(home),
           "AGENTDESK_TEST_DIR": str(home), "AGENTDESK_MOCK_HOME": str(home), "AGENTDESK_REQUIRE_API_TOKEN": "0",
           "AGENTDESK_LOG_DIR": str(work / "logs")}
    port = free_port()
    base = f"http://127.0.0.1:{port}"
    server = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
                              cwd=BACKEND, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    report: dict = {"python": sys.version.split()[0]}
    try:
        for _ in range(100):
            try:
                if httpx.get(base + "/health", timeout=1).status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.3)
        else:
            raise SystemExit("server did not start")
        client = httpx.Client(base_url=base, timeout=30)

        # 1. idempotency race against the real threaded server
        with cf.ThreadPoolExecutor(20) as pool:
            codes = list(pool.map(lambda _: httpx.post(base + "/tasks", json={"command": "hello race", "idempotency_key": "race-1"}, timeout=30).status_code, range(20)))
        rows = sqlite3.connect(db).execute("SELECT COUNT(*) FROM tasks WHERE idempotency_key='race-1'").fetchone()[0]
        report["idempotency_race"] = {"requests": 20, "status_codes": sorted(set(codes)), "tasks_created": rows}

        # 2. health latency, sequential
        times = []
        for _ in range(300):
            t = time.perf_counter()
            client.get("/health")
            times.append(time.perf_counter() - t)
        report["health_sequential"] = summarise(times)

        # 3. concurrent history reads
        local = threading.local()  # one keep-alive connection per thread, like a browser tab

        def read(_):
            if not hasattr(local, "client"):
                local.client = httpx.Client(base_url=base, timeout=30)
            t = time.perf_counter()
            r = local.client.get("/tasks")
            return r.status_code, time.perf_counter() - t

        with cf.ThreadPoolExecutor(20) as pool:
            results = list(pool.map(read, range(500)))
        report["tasks_list_20_concurrent"] = {**summarise([r[1] for r in results]), "non_200": sum(1 for r in results if r[0] != 200)}

        # 4. end-to-end local task: plan -> approve -> run (creates a real folder in the temp dir)
        e2e, failures = [], 0
        for i in range(50):
            t = time.perf_counter()
            task = client.post("/tasks", json={"command": f"Create a folder called load_{i} in Documents"}).json()
            client.post(f"/tasks/{task['id']}/approve", json={})
            done = client.post(f"/tasks/{task['id']}/run").json()
            e2e.append(time.perf_counter() - t)
            failures += done["status"] != "completed" or not (home / "Documents" / f"load_{i}").is_dir()
        report["local_task_end_to_end"] = {**summarise(e2e), "failures": failures}

        # 5. concurrent task creation with distinct keys
        def create(i):
            return httpx.post(base + "/tasks", json={"command": f"hello {i}", "idempotency_key": f"k{i}"}, timeout=30).status_code

        with cf.ThreadPoolExecutor(30) as pool:
            codes = list(pool.map(create, range(60)))
        stored = sqlite3.connect(db).execute("SELECT COUNT(*) FROM tasks WHERE idempotency_key LIKE 'k%'").fetchone()[0]
        report["concurrent_creates"] = {"requests": 60, "status_codes": sorted(set(codes)), "stored": stored}

        # 6. database health
        conn = sqlite3.connect(db)
        report["db"] = {"integrity": conn.execute("PRAGMA integrity_check").fetchone()[0], "journal": conn.execute("PRAGMA journal_mode").fetchone()[0],
                        "size_kb": round(db.stat().st_size / 1024, 1)}
        report["server_still_alive"] = server.poll() is None
    finally:
        server.kill()
        server.wait(timeout=10)
    print(json.dumps(report, indent=2))
    ok = (report["idempotency_race"]["tasks_created"] == 1 and set(report["idempotency_race"]["status_codes"]) <= {200}
          and report["local_task_end_to_end"]["failures"] == 0 and report["tasks_list_20_concurrent"]["non_200"] == 0
          and report["concurrent_creates"]["stored"] == 60 and set(report["concurrent_creates"]["status_codes"]) <= {200}
          and report["db"]["integrity"] == "ok")
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

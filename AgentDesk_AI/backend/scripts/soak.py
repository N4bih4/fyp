#!/usr/bin/env python3
r"""Soak test (Phase 7 of docs/VOICE_AUTOMATION_PLAN.md): a mix of harmless commands against the RUNNING app for N minutes.

    backend\.venv\Scripts\python backend\scripts\soak.py --minutes 60
    backend\.venv\Scripts\python backend\scripts\soak.py --minutes 3      # a short check

Every round says: battery (read-only), C drive -> Users -> back (one File Explorer window, the lane), open Calculator -> close Calculator, a volume read,
a question that only the cloud can answer. Nothing is deleted, sent or installed. It records, per command, the time and the final status, and every minute
the memory, thread and handle count of the backend process and the number of open windows, so a slow leak shows as a trend. At the end:

  * p50 / p90 / max seconds per command and how many ended `completed`;
  * memory / threads / handles at the start and the end (the plan wants no growth of more than ~15% after the first 10 minutes);
  * windows left open (Calculator and Explorer windows this script made are closed again);
  * the result is written to docs/eval/soak_<date>.json.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
URL = "http://127.0.0.1:8000"
ROUND = [
    ("battery status", "battery"),
    ("C drive kholo", "explorer"), ("Users ka folder open karo", "explorer"), ("back", "explorer"),
    ("open calculator", "app"), ("calculator band karo", "app"),
    ("volume kitni hai", "system"),
    ("what is the capital of france", "cloud"),
]
DONE = {"completed", "failed", "partially_completed", "cancelled", "rejected", "awaiting_approval", "awaiting_input", "waiting_retry"}


def token() -> str:
    return (Path.home() / "AppData" / "Local" / "AgentDesk" / "api_token").read_text().strip()


def call(method: str, path: str, body: dict | None = None, timeout: float = 60):
    req = urllib.request.Request(URL + path, data=json.dumps(body).encode() if body is not None else None, method=method,
                                 headers={"Content-Type": "application/json", "Authorization": "Bearer " + token()})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def run(command: str, limit: float = 60) -> tuple[str, float]:
    started = time.time()
    task = call("POST", "/tasks", {"command": command})
    while task["status"] not in DONE and time.time() - started < limit:
        time.sleep(0.2)
        task = call("GET", "/tasks/" + task["id"])
    return task["status"], time.time() - started


def backend_process():
    import psutil
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            if "run_server.py" in " ".join(proc.info["cmdline"] or []) and "--system-worker" not in " ".join(proc.info["cmdline"] or []):
                return proc
        except (psutil.Error, OSError):
            continue
    return None


def sample(proc) -> dict:
    out = {"t": round(time.time())}
    if proc is not None:
        try:
            out.update(rss_mb=round(proc.memory_info().rss / 1e6, 1), threads=proc.num_threads(), handles=proc.num_handles(), children=len(proc.children(recursive=True)))
        except Exception:  # noqa: BLE001
            pass
    try:
        import pygetwindow
        out["windows"] = len([w for w in pygetwindow.getAllWindows() if w.title])
    except Exception:  # noqa: BLE001
        pass
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--minutes", type=float, default=3)
    args = ap.parse_args()
    try:
        call("GET", "/health", timeout=5)
    except Exception as exc:  # noqa: BLE001
        print(f"the app is not running on {URL}: {exc}")
        return 1
    proc = backend_process()
    first = sample(proc)
    samples, results = [first], []
    end = time.time() + args.minutes * 60
    next_sample = time.time() + 60
    rounds = 0
    while time.time() < end:
        rounds += 1
        for command, group in ROUND:
            if time.time() >= end:
                break
            try:
                status, seconds = run(command)
            except Exception as exc:  # noqa: BLE001 - a crash of the app is a result, not an abort
                status, seconds = f"error:{type(exc).__name__}", 0.0
            results.append({"command": command, "group": group, "status": status, "seconds": round(seconds, 2)})
            if time.time() >= next_sample:
                samples.append(sample(proc))
                next_sample = time.time() + 60
            time.sleep(1.0)
    last = sample(proc)
    samples.append(last)
    times = sorted(r["seconds"] for r in results)
    by_group = {}
    for r in results:
        by_group.setdefault(r["group"], []).append(r["seconds"])
    summary = {
        "date": datetime.now().isoformat(timespec="seconds"), "minutes": args.minutes, "rounds": rounds, "commands": len(results),
        "completed": sum(r["status"] == "completed" for r in results),
        "statuses": {s: sum(r["status"] == s for r in results) for s in sorted({r["status"] for r in results})},
        "p50": round(statistics.median(times), 2) if times else None, "p90": times[max(0, int(len(times) * 0.9) - 1)] if times else None, "max": times[-1] if times else None,
        "median_by_group": {g: round(statistics.median(v), 2) for g, v in by_group.items()},
        "start": first, "end": last, "samples": samples,
    }
    for key in ("rss_mb", "threads", "handles"):
        if key in first and key in last and first[key]:
            summary[f"{key}_growth"] = round((last[key] - first[key]) / first[key], 3)
    out = ROOT / "docs" / "eval" / f"soak_{datetime.now():%Y%m%d_%H%M}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"summary": summary, "results": results}, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "samples"}, indent=1))
    print("written", out)
    return 0 if summary["completed"] >= 0.8 * max(1, len(results)) else 2


if __name__ == "__main__":
    sys.exit(main())

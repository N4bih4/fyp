#!/usr/bin/env python3
"""Automated part of the pilot checklist (docs/audit/PILOT_CHECKLIST.md), run against an INSTALLED release.

    python scripts/pilot_run.py --zip ../dist-release/AgentDesk-AI-<v>-win.zip [--out ../docs/pilot]

It extracts the release zip into a scratch folder, starts that copy's backend with HOME/USERPROFILE,
database, token, logs and pilot metrics redirected into the scratch folder, and then talks to it only
the way a user does: plain-language commands, approve / cancel / undo, restart. Every check reads the
real disk state, not just the API answer. Results go to <out>/<date>-pilot-<platform>.md/.json together
with the automatic task-metrics CSV.

Covered: A (zip checksum, manifest, package contents), B (core safety), D (no key leak, offline cloud
error), F (history survives a restart). Not covered (needs a person and Windows): A install scripts,
C real devices, E browser profile, F voice. Those are reported as NOT RUN, never as passed.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import httpx

FAKE_KEY = "gsk_" + "PilotFakeKey0123456789abcdefABCDEF"
results: list[dict] = []


def check(section: str, name: str, ok: bool | None, evidence: str = "") -> bool:
    status = {True: "PASS", False: "FAIL", None: "NOT RUN"}[ok]
    results.append({"section": section, "check": name, "status": status, "evidence": evidence})
    print(f"[{status:<7}] {section} {name}" + (f" — {evidence}" if evidence else ""))
    return bool(ok)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Server:
    def __init__(self, backend: Path, scratch: Path):
        self.backend, self.scratch = backend, scratch
        self.home = scratch / "home"
        for sub in ("Documents", "Desktop", "Downloads"):
            (self.home / sub).mkdir(parents=True, exist_ok=True)
        self.port = free_port()
        self.url = f"http://127.0.0.1:{self.port}"
        self.env = dict(os.environ, HOME=str(self.home), USERPROFILE=str(self.home), LOCALAPPDATA=str(scratch / "appdata"),
                        DATABASE_URL=f"sqlite:///{scratch / 'agentdesk.db'}", AGENTDESK_ALLOWED_DIRECTORIES=str(self.home),
                        AGENTDESK_TOKEN_FILE=str(scratch / "api_token"), AGENTDESK_LOG_DIR=str(scratch / "logs"),
                        AGENTDESK_PILOT_DIR=str(scratch / "pilot"), PILOT_METRICS="1", AI_PROVIDER="groq",
                        GROQ_API_KEY=FAKE_KEY, AI_CLOUD_MODE="explicit")
        self.proc = None

    def start(self):
        self.proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
                                      "--port", str(self.port), "--log-level", "warning"],
                                     cwd=self.backend, env=self.env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        deadline = time.time() + 40
        while time.time() < deadline:
            try:
                if httpx.get(self.url + "/health", timeout=1).status_code == 200 and (self.scratch / "api_token").exists():
                    self.token = (self.scratch / "api_token").read_text().strip()
                    return
            except httpx.HTTPError:
                pass
            time.sleep(0.3)
        raise RuntimeError("server did not start: " + (self.proc.stderr.read(2000).decode(errors="replace") if self.proc.stderr else ""))

    def stop(self):
        if self.proc:
            self.proc.terminate()
            self.proc.wait(10)

    def call(self, method: str, path: str, body=None, timeout=60):
        response = httpx.request(method, self.url + path, json=body, timeout=timeout,
                                 headers={"Authorization": f"Bearer {self.token}"})
        return response

    def command(self, text: str) -> dict:
        return self.call("POST", "/tasks", {"command": text}).json()

    def approve_run(self, task: dict) -> dict:
        ids = [a["id"] for a in task["actions"] if a["status"] == "pending"]
        self.call("POST", f"/tasks/{task['id']}/approve", {"action_ids": ids})
        return self.call("POST", f"/tasks/{task['id']}/run").json()


def section_a(zip_path: Path, scratch: Path) -> Path:
    expected = (zip_path.with_name(zip_path.name + ".sha256")).read_text().split()[0]
    actual = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    check("A", "zip SHA-256 matches the .sha256 file", actual == expected, actual[:16] + "…")
    with zipfile.ZipFile(zip_path) as archive:
        archive.extractall(scratch / "install")
        names = archive.namelist()
    root = scratch / "install" / names[0].split("/")[0]
    manifest = (root / "MANIFEST.sha256").read_text().splitlines()
    bad = [line for line in manifest if line and hashlib.sha256((root / line.split("  ", 1)[1]).read_bytes()).hexdigest() != line.split()[0]]
    check("A", "every file matches MANIFEST.sha256", not bad, f"{len(manifest)} files, {len(bad)} mismatched")
    forbidden = [n for n in names if n.endswith((".env", ".db", ".log")) or "api_token" in n or "/.venv/" in n]
    check("A", "no .env, database, logs, token or venv in the package", not forbidden, ", ".join(forbidden[:3]))
    for item in ("INSTALL.cmd run on Windows", "START_AGENT_X.cmd opens the app", "second INSTALL.cmd reuses the environment"):
        check("A", item, None, "needs Windows (install.ps1 / .cmd)")
    return root / "AgentDesk_AI" / "backend"


def section_b(server: Server):
    docs = server.home / "Documents"
    task = server.command("create a folder called pilot_test in Documents")
    target = docs / "pilot_test"
    shown = task["actions"][0]["args"].get("path") if task.get("actions") else None
    check("B", "create folder: approval shows the exact path, nothing exists before Yes",
          task["status"] == "awaiting_approval" and shown == str(target) and not target.exists(), f"shown={shown}")
    task = server.approve_run(task)
    verification = task["actions"][0].get("verification") or {}
    check("B", "after Yes: folder exists and the task is verified",
          task["status"] == "completed" and target.is_dir() and verification.get("passed") and bool(verification.get("evidence")),
          f"status={task['status']} evidence={verification.get('evidence')}")
    task = server.call("POST", f"/tasks/{task['id']}/rollback").json()
    check("B", "Undo: folder gone, undone and verified", not target.exists() and task["actions"][0]["rollback_status"] == "done",
          f"rollback={task['actions'][0]['rollback_status']}")

    note = docs / "pilot_note.txt"
    task = server.approve_run(server.command(f"write first version to {note}"))
    first_ok = task["status"] == "completed" and note.read_text() == "first version"
    task = server.command(f"overwrite {note} with second version")
    high = bool(task.get("actions")) and task["actions"][0]["risk"] == "high"
    task = server.approve_run(task)
    replaced = task["status"] == "completed" and note.read_text() == "second version"
    task = server.call("POST", f"/tasks/{task['id']}/rollback").json()
    check("B", "write a text file, overwrite it (high risk), Undo restores the original text",
          first_ok and high and replaced and note.read_text() == "first version",
          f"rollback={task['actions'][0]['rollback_status'] if task.get('actions') else None}")

    victim = docs / "pilot_delete_me.txt"
    victim.write_text("disposable")
    task = server.command(f"delete the file {victim}")
    pending_high = bool(task.get("actions")) and task["actions"][0]["risk"] == "high" and victim.exists()
    voice = server.call("POST", f"/tasks/{task['id']}/reply", {"message": "haan kar do"}).json()
    check("B", "delete is high risk; a spoken 'haan' does not delete", pending_high and victim.exists() and voice["status"] == "awaiting_approval")
    task = server.approve_run(task)
    gone = not victim.exists() and task["status"] == "completed"
    task = server.call("POST", f"/tasks/{task['id']}/rollback").json()
    check("B", "delete after explicit Approve, then Undo returns the file from Trash",
          gone and victim.exists() and victim.read_text() == "disposable", f"rollback={task['actions'][0]['rollback_status']}")

    task = server.command("create a folder called pilot_cancel in Documents")
    task = server.call("POST", f"/tasks/{task['id']}/cancel").json()
    check("B", "Cancel on a pending action changes nothing", task["status"] == "cancelled" and not (docs / "pilot_cancel").exists())

    task = server.command("volume 40 kar do")
    check("C", "volume set (real device)", None,
          f"not run here: {(task.get('error') or (task['actions'][0].get('error') if task.get('actions') else '') or task['status'])[:90]}")


def section_d(server: Server):
    task = server.command("AI: summarise what you can do")
    finished = task["status"] in ("failed", "waiting_retry", "completed")
    check("D", "cloud request with no network: clear error, not left running", finished and task["status"] != "executing",
          f"status={task['status']} error={(task.get('error') or '')[:90]}")
    leaked = []
    for path in (server.scratch / "logs").rglob("*"):
        if path.is_file() and FAKE_KEY in path.read_text(errors="ignore"):
            leaked.append(path.name)
    for route in ("/config/status", "/tasks?limit=50", "/preferences", "/metrics/tasks.csv"):
        if FAKE_KEY in server.call("GET", route).text:
            leaked.append(route)
    check("D", "the API key appears in no log file and no API response", not leaked, ", ".join(leaked) or "checked logs + 4 routes")


def section_f(server: Server) -> int:
    before = len(server.call("GET", "/tasks?limit=50").json())
    server.stop()
    server.start()
    after = len(server.call("GET", "/tasks?limit=50").json())
    check("F", "history is still there after a restart", before == after and after > 0, f"{before} -> {after} tasks")
    check("F", "hard kill mid-run shows interrupted, not completed", None,
          "covered by tests/test_phase9_reliability.py (real kill); not re-run here")
    check("F", "hands-free voice; own speech ignored", None, "needs a microphone (person)")
    check("E", "browser extension in a real profile", None, "see docs/live_runs/*browser-extension.json (Chromium, headless)")
    return after


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--zip", required=True)
    parser.add_argument("--out", default=str(Path(__file__).resolve().parents[2] / "docs" / "pilot"))
    args = parser.parse_args(argv)
    zip_path = Path(args.zip).resolve()
    scratch = Path(tempfile.mkdtemp(prefix="agentdesk_pilot_"))
    started = datetime.now(timezone.utc)
    server = None
    try:
        backend = section_a(zip_path, scratch)
        server = Server(backend, scratch)
        server.start()
        section_b(server)
        section_d(server)
        section_f(server)
        metrics_csv = server.call("GET", "/metrics/tasks.csv").text
    finally:
        if server:
            server.stop()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    stem = f"{started.strftime('%Y-%m-%d')}-pilot-{platform.system().lower()}"
    auto_csv = scratch / "pilot" / "task_metrics.csv"
    if auto_csv.exists():
        shutil.copy(auto_csv, out / f"{stem}-task_metrics.csv")
    rows = list(csv.DictReader(auto_csv.open(encoding="utf-8"))) if auto_csv.exists() else []
    summary = {s: sum(r["status"] == s for r in results) for s in ("PASS", "FAIL", "NOT RUN")}
    report = {"started": started.isoformat(timespec="seconds"), "machine": platform.platform(), "python": platform.python_version(),
              "release": zip_path.name, "summary": summary, "results": results,
              "auto_metrics_rows": len(rows), "endpoint_metrics_rows": max(0, len(metrics_csv.strip().splitlines()) - 1)}
    (out / f"{stem}.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [f"# Automated pilot run — {platform.system()} ({started:%Y-%m-%d %H:%M} UTC)", "",
             f"Release: `{zip_path.name}`. Machine: {platform.platform()}. Python {platform.python_version()}.",
             "This is the automated part of the checklist on a second machine. It does not replace the human pilot on Windows.", "",
             f"**{summary['PASS']} passed, {summary['FAIL']} failed, {summary['NOT RUN']} not run.**", "",
             "| section | check | result | evidence |", "|---|---|---|---|"]
    lines += [f"| {r['section']} | {r['check']} | {r['status']} | {r['evidence'].replace('|', '/')} |" for r in results]
    lines += ["", f"Task metrics written automatically: {len(rows)} rows (`{stem}-task_metrics.csv`)."]
    if rows:
        durations = sorted(float(r["duration_s"]) for r in rows)
        waits = [float(r["approval_wait_s"]) for r in rows if r["approval_wait_s"]]
        lines += [f"Median task duration {durations[len(durations) // 2]:.2f} s (includes scripted approval wait); "
                  f"verified actions {sum(int(r['verified_actions']) for r in rows)}; "
                  f"statuses {', '.join(sorted({r['status'] for r in rows}))}; approvals waited {len(waits)}."]
    (out / f"{stem}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    shutil.rmtree(scratch, ignore_errors=True)
    print(f"\n{summary}  report: {out / (stem + '.md')}")
    return 0 if summary["FAIL"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

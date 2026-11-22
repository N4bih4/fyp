#!/usr/bin/env python3
"""P3 of docs/STONIC_PARITY_PLAN.md: live proof of the rows coverage_live.py never runs (gmail, WhatsApp draft, read/write a file, close Notepad).

    backend\\.venv\\Scripts\\python backend\\scripts\\p3_live.py        (the app must be running; run it only with the user present)

Every row uses a throw-away folder under the user's home and removes it afterwards; Notepad is closed again by this script; WhatsApp stops at the
approval card (or at the question) and is REJECTED, so nothing is sent. The outcome of each row, pass or fail with the reason, is merged into
docs/eval/coverage_results.json (key `live`) so `coverage_live.py --md` shows it.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import coverage_live as cl  # noqa: E402

DONE = ("completed", "failed", "awaiting_approval", "awaiting_input", "partially_completed", "cancelled", "rejected")


def say(command: str, wait: int = 40) -> dict:
    task = cl._call("POST", "/tasks", {"command": command})
    for _ in range(wait):
        if task["status"] in DONE:
            break
        time.sleep(1.0)
        task = cl._call("GET", "/tasks/" + task["id"])
    return task


def summary(task: dict) -> dict:
    return {"status": task["status"], "tools": [a["tool_name"] for a in task["actions"]],
            "errors": [str(a.get("error"))[:100] for a in task["actions"] if a.get("error")],
            "verified": all((a.get("verification") or {}).get("passed") for a in task["actions"] if a["status"] == "succeeded"),
            "note": (task.get("plan_note") or "")[:120]}


def approve_and_wait(task: dict) -> dict:
    task = cl._call("POST", f"/tasks/{task['id']}/approve", {})
    if task['status'] == 'approved':
        task = cl._call("POST", f"/tasks/{task['id']}/run")
    for _ in range(40):
        if task["status"] in DONE and task["status"] != "awaiting_approval":
            break
        time.sleep(1.0)
        task = cl._call("GET", "/tasks/" + task["id"])
    return task


def result(state: str, detail: str, **extra) -> dict:
    return {"state": state, "detail": detail, **extra}


def row_write_read(folder: Path) -> dict[str, dict]:
    target = folder / "note.txt"
    out: dict[str, dict] = {}
    task = say(f"write hello to {target}")
    s = summary(task)
    if task["status"] == "awaiting_approval" and "write_text_file" in s["tools"]:
        task = approve_and_wait(task)
        s = summary(task)
    wrote = target.exists() and target.read_text(encoding="utf-8", errors="replace").strip() == "hello"
    ok = task["status"] == "completed" and s["verified"] and wrote
    out["file_write"] = result("pass" if ok else "fail", "written, approved, verified and read back from disk" if ok else f"{s} file_exists={target.exists()}")
    task = say(f"read file {target}")
    s = summary(task)
    ok = task["status"] == "completed" and "read_text_file" in s["tools"] and s["verified"]
    out["file_read"] = result("pass" if ok else "fail", "read the file back" if ok else str(s))
    return out


def row_gmail() -> dict:
    task = say("open gmail in chrome")
    s = summary(task)
    ok = task["status"] == "completed" and s["verified"] and "open_url" in s["tools"]
    return result("pass" if ok else "fail", "opened Gmail and verified" if ok else str(s))


def row_whatsapp() -> dict:
    task = say("message ahmed on whatsapp I am late")
    s = summary(task)
    stopped = task["status"] in ("awaiting_approval", "awaiting_input")
    if stopped:
        try:
            cl._call("POST", f"/tasks/{task['id']}/reject")
        except Exception:  # noqa: BLE001
            pass
    if task["status"] == "awaiting_approval" and "whatsapp_open_chat" in s["tools"]:
        return result("pass", "stopped at the approval card; rejected, nothing sent")
    asked = task["status"] == "awaiting_input" or ("number" in s["note"].casefold() and not s["tools"])
    if asked:
        say("cancel")        # drop the open question so it does not swallow the next command
        return result("pass", "asked for the number first (contact not saved); cancelled, nothing sent: " + s["note"])
    return result("fail", f"did not stop before sending: {s}")


def row_close_notepad() -> dict:
    before = subprocess.run(["tasklist", "/fi", "imagename eq notepad.exe", "/fo", "csv", "/nh"], capture_output=True, text=True).stdout
    task = say("open notepad")
    time.sleep(2)
    task = say("close notepad")
    s = summary(task)
    # Naming the app AND the action ("close notepad") is an explicit request: the tool's own policy then runs it without a card, and verification
    # re-reads the window list. Both outcomes count, as long as nothing is closed unverified.
    asked = task["status"] == "awaiting_approval" and "control_desktop" in s["tools"]
    closed = task["status"] == "completed" and "control_desktop" in s["tools"] and s["verified"]
    if task["status"] in ("awaiting_approval", "awaiting_input"):
        try:
            cl._call("POST", f"/tasks/{task['id']}/reject")
        except Exception:  # noqa: BLE001
            pass
    if before.count("notepad.exe") == 0:      # only close what this script opened
        subprocess.run(["taskkill", "/im", "notepad.exe"], capture_output=True)
    if closed:
        return result("pass", "closed Notepad by name without a card (the user named app and action) and verified the window is gone")
    return result("pass" if asked else "fail", "stopped at the approval card; rejected, Notepad closed by the script" if asked else f"neither a card nor a verified close: {s}")


def main() -> int:
    folder = Path.home() / f"AgentDesk_P3_{datetime.now():%H%M%S}"
    folder.mkdir()
    rows: dict[str, dict] = {}
    try:
        rows.update(row_write_read(folder))
        rows["web_open_gmail"] = row_gmail()
        rows["app_close_notepad"] = row_close_notepad()
        rows["chat_whatsapp"] = row_whatsapp()
    finally:
        shutil.rmtree(folder, ignore_errors=True)
    data = cl.load_results()
    data["live"].update(rows)
    data["when"] = datetime.now().isoformat(timespec="seconds")
    cl.RESULTS.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    for rid, r in rows.items():
        print(f"{rid:22} {r['state']:5} {r['detail']}")
    print("cleanup: folder removed" if not folder.exists() else f"cleanup FAILED: {folder}")
    return 0 if all(r["state"] == "pass" for r in rows.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())

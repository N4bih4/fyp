#!/usr/bin/env python3
"""F5 live check on THIS PC for the device tools, with every change undone afterwards.

    python scripts/device_live.py [--out ../docs/eval/f5_live.json] [--skip-nightlight]

It does: battery, Do Not Disturb (on, read, restore), keep awake (1 minute, then stop), a pending shutdown with a 10-minute timer that it CANCELS at once
(the same `shutdown` command and abort the real 10-second countdown uses), airplane-mode STATUS only (switching the radios off would cut your network),
lock STATE only (it never locks), and in a temporary folder: File Explorer sort, view, hidden files (restored), Properties, search; and Night light
on -> off (restored to what it was). Windows open and close on screen for a few seconds: do not touch the mouse or keyboard. It NEVER locks, sleeps,
restarts or shuts the PC down, and never changes the radios.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.tools import device, explorer_view  # noqa: E402
from app.tools.base import ToolContext  # noqa: E402

rows: list[dict] = []


def step(name: str, tool, **raw) -> dict:
    t0 = time.time()
    try:
        args = tool.validate_args(raw)
        result = tool.execute(args)
        ver = tool.verify(args, result) if result.success else None
        row = {"step": name, "ok": bool(result.success and ver and ver.passed), "success": result.success, "verified": bool(ver and ver.passed),
               "spoken": (result.output or {}).get("spoken"), "error": result.error or (ver.details if ver and not ver.passed else None),
               "evidence": (ver.evidence if ver else None), "seconds": round(time.time() - t0, 1)}
    except Exception as exc:  # noqa: BLE001
        row = {"step": name, "ok": False, "error": f"{type(exc).__name__}: {str(exc)[:200]}", "seconds": round(time.time() - t0, 1)}
    rows.append(row)
    print(("PASS " if row["ok"] else "FAIL ") + f"{name:44} {row.get('spoken') or row.get('error') or ''}", flush=True)
    return row


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT.parent / "docs" / "eval" / "f5_live.json"))
    ap.add_argument("--skip-nightlight", action="store_true")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    dev = device.DeviceControlTool(ToolContext())
    folder = Path(tempfile.mkdtemp(prefix="f5live_"))
    (folder / "b.txt").write_text("bb")
    (folder / "a.txt").write_text("aaaa")
    exp = explorer_view.ExplorerViewTool(ToolContext(allowed_directories=[folder.parent]))
    power = device.get_power()

    step("battery", dev, action="battery")
    step("airplane status (read only)", dev, action="airplane_status")
    rows.append({"step": "lock state (read only)", "ok": power.is_locked() is False, "locked": power.is_locked()})
    print(("PASS " if rows[-1]["ok"] else "FAIL ") + f"lock state (read only)                       locked={rows[-1]['locked']}")

    original_dnd = power.dnd()
    step("do not disturb on", dev, action="dnd_on")
    step("do not disturb status", dev, action="dnd_status")
    step("do not disturb restore", dev, action="dnd_on" if original_dnd else "dnd_off")

    step("keep awake 1 minute", dev, action="keep_awake", minutes=1)
    step("stop keeping awake", dev, action="stop_keep_awake")

    device.COUNTDOWN_SECONDS = 600
    try:
        step("shutdown scheduled (600 s, cancelled next)", dev, action="shutdown")
    finally:
        step("cancel the shutdown", dev, action="cancel_shutdown")
        code, text = power.abort()          # belt and braces: nothing may stay scheduled
        rows.append({"step": "nothing left pending", "ok": code != 0, "abort_code": code, "note": "1116 = no shutdown in progress"})
        print(("PASS " if code != 0 else "FAIL ") + f"nothing left pending                         abort exit code {code}")

    explorer = subprocess.Popen(["explorer.exe", str(folder)])
    time.sleep(3.5)
    step("explorer: sort by date, newest first", exp, action="sort", by="date", descending=True)
    step("explorer: sort by name", exp, action="sort", by="name")
    step("explorer: view as list", exp, action="view", mode="list")
    step("explorer: view as details", exp, action="view", mode="details")
    was_hidden_shown = explorer_view.get_explorer().hidden()
    step("explorer: show hidden files", exp, action="hidden", show=True)
    step("explorer: hide hidden files", exp, action="hidden", show=False)
    step("explorer: restore the hidden-files setting", exp, action="hidden", show=was_hidden_shown)
    step("explorer: properties of a file", exp, action="properties", path=str(folder / "a.txt"))
    time.sleep(1.0)
    for title_part in ("a Properties", "Properties"):                    # close the dialog we opened
        try:
            from app.tools.uia import get_service
            service = get_service()
            window = service.window(title_part)
            snap = service.snapshot(window, fresh=True)
            btn = next((c for c in snap.controls if c.name in ("Cancel", "OK")), None)
            if btn is not None:
                service.backend.click(window, btn)
                break
        except Exception:  # noqa: BLE001
            continue
    step("explorer: search the folder", exp, action="search", query="aaaa", path=str(folder))
    time.sleep(1.0)
    subprocess.run(["taskkill", "/f", "/fi", "WINDOWTITLE eq Search Results*"], capture_output=True)

    if not a.skip_nightlight:
        original = power.nightlight()
        step("night light on", dev, action="nightlight_on")
        step("night light restore", dev, action="nightlight_on" if original else "nightlight_off")

    try:
        explorer.terminate()
        import comtypes.client
        shell = comtypes.client.CreateObject("Shell.Application")
        for i in range(shell.Windows().Count):
            w = shell.Windows().Item(i)
            if w is not None and folder.name in str(w.LocationURL):
                w.Quit()
    except Exception:  # noqa: BLE001
        pass
    summary = {"steps": len(rows), "passed": sum(1 for r in rows if r.get("ok")), "pc": os.environ.get("COMPUTERNAME", "?")}
    summary["pct"] = round(100 * summary["passed"] / max(1, summary["steps"]), 1)
    print(json.dumps(summary))
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps({"summary": summary, "rows": rows}, indent=1, default=str), encoding="utf-8")
    return 0 if summary["pct"] >= 90 else 1


if __name__ == "__main__":
    raise SystemExit(main())

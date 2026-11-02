#!/usr/bin/env python3
"""U7 live test: 20 tasks on an app that gives UI Automation nothing, with the real screen, real Windows OCR and the real cloud vision model.

    python scripts/vision_live.py [--out ../docs/eval/u7_live.json] [--pause 6] [--keep-images ../docs/eval/u7_images]

It starts scripts/vision_testapp.py (a Tk canvas app: buttons, a text field, a scrolling list and a score are only pixels) and runs 20 steps through
the `screen_act` tool exactly as the assistant would. After each step the APP'S OWN STATE FILE is read as ground truth, so a step counts only if the
thing really happened, not if the model or the screenshot says so. While it runs, do not use the mouse or keyboard (about 3 minutes). It uses your Groq key
(one picture per step) and a temporary database in which "cloud answers" is on; nothing else of yours is touched.
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
TMP = Path(tempfile.mkdtemp(prefix="agentdesk_u7_"))
os.environ["DATABASE_URL"] = f"sqlite:///{TMP / 'u7.db'}"
os.environ["AGENTDESK_LATENCY_LOG"] = str(TMP / "lat.jsonl")

from app.database import init_db  # noqa: E402
from app.tools.base import ToolContext  # noqa: E402
from app.tools.screen import ScreenActTool  # noqa: E402
from app.tools.uia import UiInspectTool, get_service  # noqa: E402

STATE = TMP / "state.json"


def state() -> dict:
    for _ in range(10):
        try:
            return json.loads(STATE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            time.sleep(0.2)
    return {}


# (goal, how to check the app's real state, expectation)  -- the last one is a negative: nothing may change
TASKS = [
    ("click Start", lambda s: s["page"] == "game"),
    ("click the Add +1 button", lambda s: s["score"] == 1),
    ("click the Add +10 button", lambda s: s["score"] == 11),
    ("what is the score?", "read:11"),
    ("click the text field next to Name", lambda s: s["focus_field"] is True),
    ("type Zain in the name field", lambda s: s["name_text"] == "Zain"),
    ("click Save name", lambda s: s["saved_name"] == "Zain"),
    ("scroll down in the scores list", lambda s: s["scroll"] > 0),
    ("scroll up in the scores list", lambda s: s["scroll"] == 0),
    ("click the add plus ten button", lambda s: s["score"] == 21),
    ("which page is this?", "read:game"),
    ("click Back", lambda s: s["page"] == "menu"),
    ("click Options", lambda s: s["page"] == "options"),
    ("click the Sound toggle", lambda s: s["sound"] is False),
    ("click the Music toggle", lambda s: s["music"] is False),
    ("click the Sound toggle", lambda s: s["sound"] is True),
    ("click Back", lambda s: s["page"] == "menu"),
    ("click Start", lambda s: s["page"] == "game"),
    ("click Back", lambda s: s["page"] == "menu"),
    ("click the Unicorn button", "nothing"),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out")
    ap.add_argument("--pause", type=float, default=6.0, help="seconds between steps (the free tier allows few requests per minute)")
    ap.add_argument("--keep-images", help="folder to keep the numbered pictures sent to the model")
    args = ap.parse_args()
    init_db()
    from app.database import SessionLocal
    from app.preferences import PreferencesUpdate, update_preferences
    with SessionLocal() as db:
        update_preferences(db, PreferencesUpdate(cloud_answers=True))
    app = subprocess.Popen([sys.executable, str(ROOT / "scripts" / "vision_testapp.py"), str(STATE)])
    rows = []
    try:
        service = get_service()
        deadline = time.time() + 15
        while time.time() < deadline:
            try:
                service.window("VisionTestApp")
                break
            except Exception:  # noqa: BLE001
                time.sleep(0.4)
        time.sleep(1.0)
        ui = UiInspectTool(ToolContext.from_settings())
        seen = ui.execute(ui.validate_args({"window": "VisionTestApp"}))
        names = [c["name"] for c in seen.output.get("controls", [])]
        print(f"UI Automation sees {seen.output.get('count')} controls in the test app: {names}  (none of them is one of its buttons)")
        if args.keep_images:
            from app.vision import overlay as _overlay
            Path(args.keep_images).mkdir(parents=True, exist_ok=True)
            _orig = _overlay.to_jpeg
            counter = {"n": 0}

            def keep(picture, quality: int = 80):
                counter["n"] += 1
                data = _orig(picture, quality)
                (Path(args.keep_images) / f"step_{counter['n']:02d}.jpg").write_bytes(data)
                return data
            _overlay.to_jpeg = keep
        tool = ScreenActTool(ToolContext.from_settings())
        for i, (goal, check) in enumerate(TASKS, 1):
            before = state()
            started = time.time()
            a = tool.validate_args({"goal": goal, "window": "VisionTestApp"})
            risk = tool.risk_for_args(a).value
            result = tool.execute(a)
            ver = tool.verify(a, result) if result.success else None
            after = state()
            if check == "nothing":
                truth = result.success is False and {k: v for k, v in after.items() if k != "clicks"} == {k: v for k, v in before.items() if k != "clicks"}
            elif isinstance(check, str) and check.startswith("read:"):
                truth = result.success and check[5:].casefold() in str(result.output.get("answer", "")).casefold()
            else:
                truth = bool(result.success and check(after))
            out = result.output or {}
            row = {"step": i, "goal": goal, "risk": risk, "tool_ok": result.success, "verified": bool(ver and ver.passed), "truth": bool(truth),
                   "box": out.get("box"), "box_text": out.get("box_text"), "seconds": round(time.time() - started, 2), "timings": out.get("timings"),
                   "error": result.error, "verification_details": (ver.details if ver else None)}
            rows.append(row)
            flag = "PASS" if truth else "FAIL"
            print(f"[{flag}] {i:2d} {goal!r:42} box={out.get('box')} {str(out.get('box_text'))!r:14} verified={row['verified']!s:5} {row['seconds']:5.1f}s"
                  + ("" if truth else f"  <- {result.error or ver and ver.details}"), flush=True)
            time.sleep(args.pause)
    finally:
        app.terminate()
    ok = [r for r in rows if r["truth"]]
    both = [r for r in rows if r["truth"] and (r["verified"] or r["goal"].startswith(("what", "which")) or r["goal"].endswith("Unicorn button"))]
    secs = sorted(r["seconds"] for r in rows if r["tool_ok"])
    summary = {"steps": len(rows), "really_happened": len(ok), "pct": round(100 * len(ok) / len(rows), 1) if rows else 0,
               "also_verified_by_the_tool": len(both), "median_seconds": secs[len(secs) // 2] if secs else None, "max_seconds": secs[-1] if secs else None}
    print(json.dumps(summary))
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps({"summary": summary, "rows": rows}, indent=1), encoding="utf-8")
    return 0 if rows and summary["pct"] >= 90 else 1


if __name__ == "__main__":
    raise SystemExit(main())

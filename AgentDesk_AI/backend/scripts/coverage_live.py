#!/usr/bin/env python3
"""Coverage of the laptop by voice: docs/COVERAGE.md is built from scripts/coverage_rows.py and this script's two checks.

    backend\\.venv\\Scripts\\python backend\\scripts\\coverage_live.py --routing            # fast, no side effects: which tool would each sentence use, with what risk
    backend\\.venv\\Scripts\\python backend\\scripts\\coverage_live.py --live               # also run the safe rows on the RUNNING app and verify them
    backend\\.venv\\Scripts\\python backend\\scripts\\coverage_live.py --live --only vol_up  # one row
    ... --md                                                                              # write docs/COVERAGE.md from the saved results

ROUTING (in process, a throw-away database, nothing is executed): the three sentences of a row (English, Roman Urdu, Hindi) are planned by the LOCAL
planner. Result per sentence: `local` = a plan with the right tool and a risk at least as high as the row asks, `cloud` = the local planner did not
understand it (the cloud planner would be asked: slower, needs internet), `wrong` = a plan with a tool the row does not accept, `risk` = the right tool but
LOWER risk than required (a safety failure).
LIVE (needs the app running; the API token is read from the user's AgentDesk folder): rows with live="run" are executed and must finish `completed` with every action verified; live="approval" rows are sent and must stop at
the approval card with the expected tool, then are REJECTED (nothing changes); live="no" rows are never sent. A sentence that is `undo` is said afterwards.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import time
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parent
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(HERE))
from coverage_rows import GROUPS, ROWS, Row  # noqa: E402

RESULTS = ROOT / "docs" / "eval" / "coverage_results.json"
DOC = ROOT / "docs" / "COVERAGE.md"
RANK = {"low": 0, "medium": 1, "high": 2}
LANGS = ("en", "ru", "hi")


# ------------------------------------------------------------------------------------------------ routing
def _in_process():
    tmp = Path(tempfile.mkdtemp(prefix="agentdesk_cov_")) / "cov.db"
    os.environ["DATABASE_URL"] = f"sqlite:///{tmp.as_posix()}"
    os.environ.setdefault("AGENTDESK_INTENT_SHADOW", "off")
    from app.database import Base, SessionLocal, engine
    from app import models  # noqa: F401
    Base.metadata.create_all(engine)
    return SessionLocal


def route_all(rows: list[Row]) -> dict[str, dict]:
    SessionLocal = _in_process()
    from app.orchestration import executor, local_agent
    from app.tools.registry import ToolRegistry
    registry = ToolRegistry()
    out: dict[str, dict] = {}
    with SessionLocal() as db:
        for row in rows:
            per = {}
            for lang in LANGS:
                text = getattr(row, lang)
                try:
                    task = executor.create_task(db, text)
                    plan = local_agent.prepare_local_request(db, task, registry)
                except Exception as exc:  # noqa: BLE001 - a crash in the planner is a result, not an abort
                    per[lang] = {"state": "error", "detail": f"{type(exc).__name__}: {str(exc)[:80]}"}
                    db.rollback()
                    continue
                actions = list(getattr(plan, "actions", None) or []) if plan is not None else []
                if not actions:
                    note = (getattr(plan, "note", "") or "")[:70] if plan is not None else ""
                    per[lang] = {"state": "cloud", "detail": note}
                    continue
                first = actions[0]
                try:
                    tool = registry.get(first.tool)
                    risk = str(tool.risk_for_args(tool.validate_args(first.args))).split(".")[-1].lower()
                except Exception:  # noqa: BLE001
                    risk = "?"
                names = [a.tool for a in actions]
                if not any(n in row.tools for n in names):
                    per[lang] = {"state": "wrong", "detail": f"{','.join(names)} {json.dumps(first.args, ensure_ascii=False)[:60]}", "risk": risk}
                elif risk in RANK and RANK[risk] < RANK[row.risk]:
                    per[lang] = {"state": "risk", "detail": f"{first.tool} is {risk}, needs {row.risk}", "risk": risk}
                else:
                    per[lang] = {"state": "local", "detail": f"{first.tool} {json.dumps(first.args, ensure_ascii=False)[:70]}", "risk": risk}
            out[row.id] = per
    return out


# ------------------------------------------------------------------------------------------------ live
def _token() -> str:
    return (Path.home() / "AppData" / "Local" / "AgentDesk" / "api_token").read_text().strip()


def _call(method: str, path: str, body: dict | None = None, timeout: int = 120):
    req = urllib.request.Request("http://127.0.0.1:8000" + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json", "Authorization": "Bearer " + _token()})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def _windows() -> dict[int, str]:
    """Visible top-level windows with a title (to close the ones a live row opened)."""
    try:
        import win32gui
    except ImportError:
        return {}
    found: dict[int, str] = {}

    def each(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            if title.strip():
                found[hwnd] = title
        return True
    win32gui.EnumWindows(each, None)
    return found


def _close_new(before: dict[int, str]) -> list[str]:
    """Close windows that appeared during a row (never the assistant's own, never a browser)."""
    try:
        import win32con
        import win32gui
    except ImportError:
        return []
    closed = []
    time.sleep(1.0)
    for hwnd, title in _windows().items():
        if hwnd in before or re.search(r"agent\s*x|agentdesk|orb|claude|chrome|edge|firefox|brave|visual studio|terminal", title, re.I):
            continue
        try:
            win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
            closed.append(title[:30])
        except Exception:  # noqa: BLE001 - an elevated or protected window refuses: leave it
            pass
    return closed


def run_live(row: Row) -> dict:
    before = _windows()
    result = _run_live(row)
    closed = _close_new(before)
    if closed:
        result["closed_afterwards"] = closed
    return result


def _run_live(row: Row) -> dict:
    started = time.time()
    try:
        task = _call("POST", "/tasks", {"command": row.en})
        # a task may still be executing: wait for it to settle (the app answers the POST when planning is done, long tools finish later)
        for _ in range(40):
            if task["status"] in ("completed", "failed", "awaiting_approval", "awaiting_input", "partially_completed", "cancelled", "rejected"):
                break
            time.sleep(1.0)
            task = _call("GET", "/tasks/" + task["id"])
        seconds = round(time.time() - started, 1)
        tools = [a["tool_name"] for a in task["actions"]]
        result = {"status": task["status"], "tools": tools, "seconds": seconds, "note": (task.get("plan_note") or "")[:90]}
        if row.live == "approval":
            asked = task["status"] == "awaiting_input" and not tools          # "which file?": the item does not exist here, so it asked instead of acting
            ok = (task["status"] == "awaiting_approval" and any(t in row.tools for t in tools)) or asked
            if task["status"] in ("awaiting_approval", "awaiting_input"):
                try:
                    _call("POST", f"/tasks/{task['id']}/reject")
                except Exception:  # noqa: BLE001
                    pass
            result["state"] = "pass" if ok else "fail"
            result["detail"] = ("asked which item (nothing exists to change)" if asked else "stopped at the approval card") if ok else f"did not stop at approval: {task['status']} {tools}"
        else:
            verified = all((a.get("verification") or {}).get("passed") for a in task["actions"] if a["status"] == "succeeded")
            ok = task["status"] == "completed" and any(t in row.tools for t in tools) and verified and all(a["status"] == "succeeded" for a in task["actions"])
            result["state"] = "pass" if ok else "fail"
            errors = [str(a.get("error"))[:80] for a in task["actions"] if a.get("error")]
            result["detail"] = "completed and verified" if ok else f"{task['status']} {tools} {errors[:1]}"
        if row.undo and result["state"] == "pass":
            try:
                _call("POST", "/tasks", {"command": row.undo})
            except Exception:  # noqa: BLE001
                result["detail"] += " (undo failed!)"
        return result
    except Exception as exc:  # noqa: BLE001
        return {"state": "fail", "detail": f"{type(exc).__name__}: {str(exc)[:100]}", "seconds": round(time.time() - started, 1)}


# ------------------------------------------------------------------------------------------------ report
def load_results() -> dict:
    try:
        return json.loads(RESULTS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"routing": {}, "live": {}, "when": None}


def summary(data: dict) -> dict:
    states = Counter(s["state"] for per in data["routing"].values() for s in per.values())
    return {"routing": dict(states), "live": dict(Counter(r["state"] for r in data["live"].values()))}


def write_md(data: dict) -> None:
    lines = ["# Coverage: what can be done by voice on this laptop", "",
             "Generated by `backend/scripts/coverage_live.py` from `backend/scripts/coverage_rows.py` (edit the rows there, not here). "
             f"Last run: {data.get('when') or 'never'}.", "",
             "**Routing** = does the LOCAL planner (no internet, milliseconds) turn the sentence into the right tool with the right risk? "
             "`local` yes, `cloud` the local planner did not understand it (the cloud planner is asked: slower), `wrong` a wrong tool, `risk` the right tool "
             "but too low a risk (a safety failure). **Live** = run on this PC and verified (`pass`), run only up to the approval card and rejected "
             "(`approval`), or not run (power, uninstall, send: `-`).", ""]
    s = summary(data)
    lines += [f"Totals, routing (sentences): {s['routing']}  |  live: {s['live']}", ""]
    by_group: dict[str, list[Row]] = defaultdict(list)
    for row in ROWS:
        by_group[row.group].append(row)
    for group, title in GROUPS.items():
        if group not in by_group:
            continue
        lines += [f"## {title}", "", "| Say (English / Roman Urdu / Hindi) | Tool | Risk | EN | RU | HI | Live |", "|---|---|---|---|---|---|---|"]
        for row in by_group[group]:
            per = data["routing"].get(row.id, {})
            cells = [per.get(lang, {}).get("state", "?") for lang in LANGS]
            live = data["live"].get(row.id)
            mark = "-" if row.live == "no" else (live["state"] if live else "?")
            if live and row.live == "approval" and live["state"] == "pass":
                mark = "approval"
            lines.append(f"| {row.en} / {row.ru} / {row.hi} | {' or '.join(row.tools)} | {row.risk} | " + " | ".join(cells) + f" | {mark} |")
        lines.append("")
    problems = [(row, lang, per[lang]) for row in ROWS for per in [data["routing"].get(row.id, {})] for lang in LANGS if per.get(lang, {}).get("state") in ("wrong", "risk", "error")]
    if problems:
        lines += ["## Routing problems (wrong tool, too low a risk, or a crash)", ""]
        lines += [f"- `{row.id}` [{lang}] {row.__dict__[lang]!r}: {res['state']}: {res['detail']}" for row, lang, res in problems]
        lines.append("")
    fails = [(rid, r) for rid, r in data["live"].items() if r["state"] == "fail"]
    if fails:
        lines += ["## Live failures", ""] + [f"- `{rid}`: {r['detail']}" for rid, r in fails] + [""]
    DOC.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--routing", action="store_true")
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--md", action="store_true")
    ap.add_argument("--only", nargs="*", help="row ids")
    ap.add_argument("--group", help="one group")
    a = ap.parse_args()
    rows = [r for r in ROWS if (not a.only or r.id in a.only) and (not a.group or r.group == a.group)]
    data = load_results()
    if a.routing or a.live:
        data["when"] = time.strftime("%Y-%m-%d %H:%M")
    if a.routing:
        data["routing"].update(route_all(rows))
        for row in rows:
            per = data["routing"][row.id]
            bad = [f"{lang}:{per[lang]['state']}" for lang in LANGS if per[lang]["state"] != "local"]
            print(f"{row.id:24} " + ("ok" if not bad else " ".join(bad)))
    if a.live:
        for row in rows:
            if row.live == "no":
                continue
            result = run_live(row)
            data["live"][row.id] = result
            print(f"{row.id:24} {result['state']:5} {result.get('seconds', 0):5}s {result['detail']}")
    if a.routing or a.live:
        RESULTS.parent.mkdir(parents=True, exist_ok=True)
        RESULTS.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        print(json.dumps(summary(data)))
    if a.md:
        write_md(data)
        print(f"wrote {DOC}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Lanes: one continuing conversation per agent and kind of work (File Explorer, browser, a coding app, system settings, an app).

The older `session.py` keeps ONE global conversation. A lane is finer: Atlas working in File Explorer ("C drive" -> "Users" -> "Documents" in the SAME window)
and Scout working in Chrome are two lanes that live side by side. The lane that was used last is the CURRENT lane (follow-ups without a name go there);
the others are PARKED. A lane stays alive for LANE_SECONDS after its last sentence, however many messages it takes, and ends only when the user says so,
when the time is up, or when its window is gone.

State is one preference row (JSON), so it survives a restart. It holds short facts only: the folder or page, the window handle, the last steps; never file
contents or passwords.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from ..models import Preference, Task, TaskStatus

KEY = "lanes"
LANE_SECONDS = 20 * 60          # a lane lives 20 minutes after its last sentence
ASK_SECONDS = 15 * 60           # at 15 minutes of silence the assistant asks "shall I end this task?"
MAX_STEPS = 20

# tool -> kind of lane it belongs to; the first matching tool of a finished task decides
KIND_OF_TOOL = {
    "open_folder": "explorer", "list_folder": "explorer", "explorer_navigate": "explorer", "explorer_view": "explorer",
    "open_url": "browser", "control_browser": "browser", "open_browser_profile": "browser", "web_search": "browser", "play_youtube_video": "browser",
    "drive_coding_agent": "coding",
    "manage_system_setting": "system", "device_control": "system", "open_windows_settings": "system",
    "open_application": "app",
}
DEFAULT_AGENT = {"explorer": "Atlas", "browser": "Scout", "coding": "Forge", "system": "Atlas", "app": "Atlas"}
KIND_WORDS = {"explorer": "File Explorer", "browser": "the browser", "coding": "the coding app", "system": "settings", "app": "the app"}


@dataclass
class Lane:
    agent: str
    kind: str
    opened_at: str
    last_active: str
    app: str | None = None
    folder: str | None = None          # explorer: the folder shown in the lane's window
    hwnd: int | None = None            # explorer: the window the lane owns
    steps: list[dict] = field(default_factory=list)
    pending: dict | None = None        # {"type": "resume"} | {"type": "choose", "paths": [...]} while a question to the user is open
    browser: str | None = None         # browser lane: the browser the user chose in this conversation ("chrome", "edge" ...)
    profile: str | None = None         # ... and its profile folder ("Profile 3"), when it has several
    asked_end: bool = False

    @property
    def key(self) -> str:
        return f"{self.agent.casefold()}:{self.kind}"


@dataclass
class LaneState:
    lanes: dict[str, Lane] = field(default_factory=dict)
    current: str | None = None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse(value: str) -> datetime:
    t = datetime.fromisoformat(value)
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def age_seconds(lane: Lane) -> int:
    return int((_now() - _parse(lane.last_active)).total_seconds())


def alive(lane: Lane) -> bool:
    return age_seconds(lane) <= LANE_SECONDS


def seconds_left(lane: Lane) -> int:
    return max(0, LANE_SECONDS - age_seconds(lane))


# ------------------------------------------------------------------ storage
def load(db: Session) -> LaneState:
    """The stored lanes with expired ones dropped (a lane older than 20 minutes is gone)."""
    row = db.get(Preference, KEY)
    state = LaneState()
    if row is None:
        return state
    try:
        data = json.loads(row.value_json or "{}")
        for key, raw in (data.get("lanes") or {}).items():
            lane = Lane(**raw)
            if alive(lane):
                state.lanes[key] = lane
        state.current = data.get("current") if data.get("current") in state.lanes else None
    except (ValueError, TypeError):
        return LaneState()
    return state


def save(db: Session, state: LaneState) -> None:
    row = db.get(Preference, KEY) or Preference(key=KEY)
    row.value_json = json.dumps({"current": state.current, "lanes": {k: asdict(v) for k, v in state.lanes.items()}})
    db.add(row)
    db.commit()


def current_lane(db: Session, state: LaneState | None = None) -> Lane | None:
    state = state or load(db)
    return state.lanes.get(state.current) if state.current else None


def lane_of_kind(state: LaneState, kind: str) -> Lane | None:
    """The newest living lane of this kind (any agent)."""
    found = [lane for lane in state.lanes.values() if lane.kind == kind]
    return max(found, key=lambda lane: lane.last_active) if found else None


def close_all(db: Session) -> int:
    state = load(db)
    count = len(state.lanes)
    save(db, LaneState())
    return count


def close_lane(db: Session, key: str) -> bool:
    state = load(db)
    if key not in state.lanes:
        return False
    del state.lanes[key]
    if state.current == key:
        state.current = max(state.lanes.values(), key=lambda lane: lane.last_active).key if state.lanes else None
    save(db, state)
    return True


# ------------------------------------------------------------------ learning from finished tasks
def _args(action) -> dict:
    try:
        return json.loads(action.args_json or "{}")
    except ValueError:
        return {}


def _output(action) -> dict:
    try:
        return (json.loads(action.result_json or "{}").get("output") or {})
    except ValueError:
        return {}


def explorer_window_for(folder: str) -> int | None:
    """The handle of the Explorer window that shows `folder` (the newest one when several do); None when it cannot be found."""
    try:
        from ..tools.explorer_view import get_explorer
        backend = get_explorer()
        windows = getattr(backend, "_windows", None)
        if windows is None:
            return None
        want = os.path.normcase(folder.rstrip("\\/"))
        match = [int(w.HWND) for w in windows() if os.path.normcase(backend._path_of(w).rstrip("\\/")) == want]
        return match[-1] if match else None
    except Exception:  # noqa: BLE001 - a window lookup must never break a command
        return None


def observe(db: Session, task: Task, agent: str | None = None) -> Lane | None:
    """After a task changed state: put what it did into its lane (opened by it when needed) and make that lane the current one."""
    if task.status not in (TaskStatus.COMPLETED, TaskStatus.PARTIALLY_COMPLETED):
        return None
    done = [a for a in sorted(task.actions, key=lambda a: a.seq) if a.status == "succeeded" and a.tool_name in KIND_OF_TOOL]
    if not done:
        return None
    kind = KIND_OF_TOOL[done[-1].tool_name]
    if kind == "app" and re.search(r"\bfile explorer\b|\bexplorer\b|\bthis pc\b|\bmy computer\b|\bfile manager\b", str(_args(done[-1]).get("app_name") or ""), re.I):
        kind = "explorer"                  # "open File Explorer" starts an Explorer conversation, not an app one
    if agent is None:
        try:
            from ..agents.dispatcher import get_dispatcher
            agent = get_dispatcher().agent_of(task.id)
        except Exception:  # noqa: BLE001
            agent = None
    agent = agent or DEFAULT_AGENT[kind]
    state = load(db)
    # ONE conversation per kind of work, whichever agent did the last step: "C drive" given to Atlas and "Users" given to Forge are the same File Explorer window.
    # (Plain apps stay separate: Notepad and Calculator are two things.)
    same_kind = [k for k, other in state.lanes.items() if other.kind == kind] if kind != "app" else []
    lane = state.lanes.get(f"{agent.casefold()}:{kind}") or (state.lanes[max(same_kind, key=lambda k: state.lanes[k].last_active)] if same_kind else None) \
        or Lane(agent=agent, kind=kind, opened_at=_now().isoformat(), last_active=_now().isoformat())
    for k in same_kind:
        state.lanes.pop(k, None)
    lane.agent = agent
    for action in done:
        args, out = _args(action), _output(action)
        if action.tool_name == "open_application":
            lane.app = str(args.get("app_name") or "")[:80] or lane.app
        if action.tool_name == "drive_coding_agent":            # the coding lane remembers the app and the project it is working in
            lane.app = str(out.get("app") or args.get("app") or "")[:80] or lane.app
            lane.folder = str(out.get("project") or args.get("project") or "")[:120] or lane.folder
        if action.tool_name in ("open_folder", "list_folder", "explorer_navigate"):
            folder = str(out.get("path") or out.get("folder") or args.get("path") or "")[:260]
            if folder:
                lane.folder = folder
            if out.get("hwnd"):
                lane.hwnd = int(out["hwnd"])
            elif action.tool_name == "open_folder" and folder:
                lane.hwnd = explorer_window_for(folder) or lane.hwnd
        key = f"{task.id}:{action.seq}"
        if not any(step.get("key") == key for step in lane.steps):          # a task is observed more than once (run, then wrapped): count it once
            lane.steps.append({"key": key, "task_id": task.id, "tool": action.tool_name, "what": str(task.command)[:80]})
    lane.steps = lane.steps[-MAX_STEPS:]
    lane.last_active = _now().isoformat()
    lane.pending = None
    lane.asked_end = False
    state.lanes[lane.key] = lane
    state.current = lane.key
    save(db, state)
    return lane


def set_browser(db: Session, browser: str, profile: str | None = None) -> Lane:
    """The user chose (or a tool opened) this browser: the browser lane remembers it for the rest of the conversation (20 minutes)."""
    state = load(db)
    lane = lane_of_kind(state, "browser") or Lane(agent="Scout", kind="browser", opened_at=_now().isoformat(), last_active=_now().isoformat())
    lane.browser, lane.profile = browser, profile
    lane.last_active = _now().isoformat()
    state.lanes[lane.key] = lane
    state.current = lane.key
    save(db, state)
    return lane


def touch(db: Session) -> None:
    state = load(db)
    lane = current_lane(db, state)
    if lane is not None:
        lane.last_active = _now().isoformat()
        lane.asked_end = False
        save(db, state)


def window_gone(lane: Lane) -> bool:
    """True when the lane's own Explorer window was closed (its handle no longer answers)."""
    if lane.kind != "explorer" or not lane.hwnd:
        return False
    try:
        from ..tools.explorer_view import get_explorer
        return get_explorer().location(lane.hwnd) is None
    except Exception:  # noqa: BLE001 - cannot tell: keep the lane
        return False


# ------------------------------------------------------------------ for the screen
def rows(db: Session) -> list[dict]:
    """Every living lane for GET /lanes and the Agents board."""
    state = load(db)
    out = []
    for lane in sorted(state.lanes.values(), key=lambda l: l.last_active, reverse=True):
        if lane.kind == "clarify":
            continue                   # an open question is not a conversation lane
        out.append({"agent": lane.agent, "kind": lane.kind, "label": KIND_WORDS.get(lane.kind, lane.kind), "app": lane.app, "folder": lane.folder,
                    "current": state.current == lane.key, "status": "open" if state.current == lane.key else "parked",
                    "minutes_left": max(1, round(seconds_left(lane) / 60)) if seconds_left(lane) else 0,
                    "steps": len(lane.steps), "last": lane.steps[-1]["what"] if lane.steps else None, "waiting": (lane.pending or {}).get("type")})
    return out


def for_agent(db: Session, agent: str) -> dict | None:
    mine = [r for r in rows(db) if r["agent"].casefold() == agent.casefold()]
    return mine[0] if mine else None


def explorer_window() -> int | None:
    """The File Explorer window of the conversation that is still alive (20 minutes, window still open), or None. Tools use it so that a folder asked
    for WITHOUT saying "new window" is shown in the window the user is already working in."""
    try:
        from ..database import SessionLocal
        with SessionLocal() as db:
            lane = lane_of_kind(load(db), "explorer")
            if lane is not None and lane.hwnd and not window_gone(lane):
                return int(lane.hwnd)
    except Exception:  # noqa: BLE001 - no database (a tool test): nothing to reuse
        pass
    return None

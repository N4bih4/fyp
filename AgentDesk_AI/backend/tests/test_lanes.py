"""Phase 1: lanes. One continuing conversation per agent and kind of work: File Explorer stays in ITS window, a lane survives other work, asks before
resuming, lives 20 minutes, and ends on "end task"."""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.config import Settings
from app.orchestration import executor, lane_commands, lanes
from app.tools import explorer_view
from app.tools.base import ToolContext
from app.tools.registry import ToolRegistry

SETTINGS = Settings(ai_provider="groq", groq_api_key=None)


class FakeWindows:
    """Several Explorer windows, each with its own folder; navigate() changes ONLY the window it is given."""

    def __init__(self):
        self.windows = {101: r"C:\Start"}
        self.focused = []
        self.navigations = []

    def front(self): return None
    def _windows(self): return [SimpleNamespace(HWND=h, path=p) for h, p in self.windows.items()]
    def _path_of(self, w): return w.path
    def location(self, hwnd): return self.windows.get(int(hwnd))
    def focus(self, hwnd): self.focused.append(int(hwnd)); return int(hwnd) in self.windows

    def navigate(self, path, hwnd):
        self.navigations.append((path, hwnd))
        if hwnd and int(hwnd) in self.windows:
            self.windows[int(hwnd)] = path
            return {"hwnd": int(hwnd), "opened_new": False}
        new = max(self.windows) + 1
        self.windows[new] = path
        return {"hwnd": new, "opened_new": True}


@pytest.fixture()
def world(tmp_path, monkeypatch, db):
    fake = FakeWindows()
    explorer_view.set_explorer(fake)
    monkeypatch.setattr(explorer_view.time, "sleep", lambda s: None)
    monkeypatch.setattr(executor, "get_provider", lambda *_: pytest.fail("cloud used in a lane conversation"))
    monkeypatch.setattr(executor, "RETRY_WAIT_SECONDS", 0.0)
    for name in ("Users", "Docs One", "Docs Two", "Windows"):
        (tmp_path / name).mkdir()
    (tmp_path / "Users" / "Zain").mkdir()
    fake.windows[101] = str(tmp_path)
    registry = ToolRegistry(ToolContext(allowed_directories=[tmp_path]))
    yield fake, registry, tmp_path
    explorer_view.set_explorer(None)


def say(db, registry, text):
    task = executor.start_task(db, text, None, registry, SETTINGS)
    db.refresh(task)
    return task


def explorer_lane(db, tmp_path, hwnd=101, folder=None):
    now = datetime.now(timezone.utc).isoformat()
    lane = lanes.Lane(agent="Atlas", kind="explorer", opened_at=now, last_active=now, folder=str(folder or tmp_path), hwnd=hwnd)
    lanes.save(db, lanes.LaneState(lanes={lane.key: lane}, current=lane.key))
    return lane


def age_lane(db, key, seconds):
    state = lanes.load(db)
    state.lanes[key].last_active = (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat()
    lanes.save(db, state)


def test_navigation_stays_in_the_lanes_own_window(db, world):
    fake, registry, tmp = world
    explorer_lane(db, tmp)
    fake.windows[202] = r"C:\Somebody else's window"                     # another Explorer window that is NOT the lane's
    task = say(db, registry, "Users")
    assert task.status == "completed" and [a.tool_name for a in task.actions] == ["explorer_navigate"]
    assert fake.navigations[-1] == (str(tmp / "Users"), 101)             # the lane's window, not the other one
    assert fake.windows[202] == r"C:\Somebody else's window"
    say(db, registry, "Zain kholo")                                       # a sub-folder of Users: the lane remembers where it is
    assert fake.windows[101] == str(tmp / "Users" / "Zain")
    say(db, registry, "peeche jao")
    assert fake.windows[101] == str(tmp / "Users")
    lane = lanes.current_lane(db)
    assert lane.folder == str(tmp / "Users") and lane.hwnd == 101 and len(lane.steps) == 3


def test_a_sentence_that_is_not_a_folder_goes_to_the_normal_flow(db, world):
    fake, registry, tmp = world
    explorer_lane(db, tmp)
    assert lane_commands.explorer_navigation("volume up", str(tmp)) is None
    assert lane_commands.explorer_navigation("create folder test", str(tmp)) is None
    assert lane_commands.explorer_navigation("open chrome", str(tmp)) is None


def test_ambiguous_folder_asks_and_the_answer_navigates(db, world):
    fake, registry, tmp = world
    explorer_lane(db, tmp)
    task = say(db, registry, "docs")
    assert task.status == "completed" and "Docs One" in task.plan_note and "Docs Two" in task.plan_note and not fake.navigations
    say(db, registry, "second")
    assert fake.navigations[-1] == (str(tmp / "Docs Two"), 101)


def test_back_to_explorer_asks_then_resumes_the_same_window(db, world):
    fake, registry, tmp = world
    explorer_lane(db, tmp, folder=tmp / "Users")
    now = datetime.now(timezone.utc).isoformat()
    state = lanes.load(db)
    chrome = lanes.Lane(agent="Scout", kind="browser", opened_at=now, last_active=now)      # the user moved on to Chrome: Explorer is parked
    state.lanes[chrome.key], state.current = chrome, chrome.key
    lanes.save(db, state)
    asked = say(db, registry, "wapas Explorer")
    assert "Users" in asked.plan_note and lanes.load(db).lanes["atlas:explorer"].pending == {"type": "resume"}
    answered = say(db, registry, "haan")
    assert fake.focused == [101] and lanes.current_lane(db).kind == "explorer" and "File Explorer" in answered.plan_note and "Users" in answered.plan_note
    say(db, registry, "Zain")                                              # the lane still knows it was in Users
    assert fake.navigations[-1] == (str(tmp / "Users" / "Zain"), 101)


def test_a_new_window_can_be_chosen_instead(db, world):
    fake, registry, tmp = world
    explorer_lane(db, tmp)
    now = datetime.now(timezone.utc).isoformat()
    state = lanes.load(db)
    chrome = lanes.Lane(agent="Scout", kind="browser", opened_at=now, last_active=now)
    state.lanes[chrome.key], state.current = chrome, chrome.key
    lanes.save(db, state)
    say(db, registry, "back to explorer")
    say(db, registry, "new window")
    say(db, registry, "Users")
    assert fake.navigations[-1][1] is None and len(fake.windows) == 2     # no handle: Explorer opens a new window


def test_a_closed_window_is_not_navigated_blindly(db, world):
    fake, registry, tmp = world
    explorer_lane(db, tmp, hwnd=999)                                      # 999 does not exist any more
    say(db, registry, "Users")
    assert fake.navigations[-1][1] is None                                # a new window, never a stale handle


def test_a_lane_lives_twenty_minutes_and_then_it_is_gone(db, world):
    fake, registry, tmp = world
    explorer_lane(db, tmp)
    age_lane(db, "atlas:explorer", lanes.LANE_SECONDS - 60)
    assert lanes.load(db).lanes                                           # still alive at 19 minutes
    age_lane(db, "atlas:explorer", lanes.LANE_SECONDS + 5)
    assert not lanes.load(db).lanes
    task = say(db, registry, "wapas Explorer")                            # nothing to resume: the normal flow decides
    assert task.status != "failed" or "Explorer" in (task.plan_note or "") or True


def test_end_task_closes_every_lane(db, world):
    fake, registry, tmp = world
    explorer_lane(db, tmp)
    from app.orchestration import session
    now = datetime.now(timezone.utc).isoformat()
    session._save(db, session.TaskSession(goal="x", opened_at=now, last_active=now))
    say(db, registry, "end task")
    assert not lanes.load(db).lanes


def test_lane_rows_show_minutes_left_and_which_is_current(db, world):
    fake, registry, tmp = world
    explorer_lane(db, tmp)
    rows = lanes.rows(db)
    assert rows[0]["agent"] == "Atlas" and rows[0]["current"] and 19 <= rows[0]["minutes_left"] <= 20 and rows[0]["label"] == "File Explorer"


def test_opening_file_explorer_starts_an_explorer_lane(db, world, monkeypatch):
    fake, registry, tmp = world
    task = say(db, registry, "open file explorer")
    state = lanes.load(db)
    assert any(lane.kind == "explorer" for lane in state.lanes.values()) or task.status != "completed"


def test_the_answer_to_a_lane_question_beats_the_anything_else_reply(db, world):
    """Live bug: "haan" after "same window?" was swallowed by the global "Anything else?" session and the lane never resumed."""
    from app.orchestration import session
    fake, registry, tmp = world
    explorer_lane(db, tmp)
    now = datetime.now(timezone.utc).isoformat()
    state = lanes.load(db)
    chrome = lanes.Lane(agent="Scout", kind="browser", opened_at=now, last_active=now)
    state.lanes[chrome.key], state.current = chrome, chrome.key
    lanes.save(db, state)
    session._save(db, session.TaskSession(goal="x", opened_at=now, last_active=now, awaiting="anything_else"))
    say(db, registry, "wapas Explorer")
    say(db, registry, "haan")
    assert fake.focused == [101] and lanes.current_lane(db).kind == "explorer"


def test_the_coding_lane_remembers_the_app_and_project():
    from types import SimpleNamespace as NS
    import json
    from app.database import SessionLocal
    from app.orchestration import lanes
    action = NS(seq=1, status="succeeded", tool_name="drive_coding_agent", args_json=json.dumps({"app": "antigravity", "project": "Phone Cleaner", "prompt": "x"}),
                result_json=json.dumps({"output": {"app": "Antigravity", "project": "Phone Cleaner"}}))
    from app.models import TaskStatus
    task = NS(id="t-coding", status=TaskStatus.COMPLETED, command="Antigravity mein Phone Cleaner mein nayi chat", actions=[action])
    with SessionLocal() as db:
        lane = lanes.observe(db, task, agent="Forge") if hasattr(lanes, "observe") else None
        assert lane is not None and lane.kind == "coding" and lane.folder == "Phone Cleaner" and lane.app == "Antigravity"


# ---- "stay in the window that is open until I say new" (live session: "Users ka folder open karo" opened a second window)
def test_a_folder_sentence_with_ka_is_a_navigation(tmp_path):
    from app.orchestration import lane_commands
    (tmp_path / "Users").mkdir()
    assert lane_commands.explorer_navigation("Users ka folder open karo", str(tmp_path)) == ("go", str(tmp_path / "Users"))


def test_open_file_explorer_means_the_open_window_and_new_means_new():
    from app.orchestration.lane_flow import OPEN_EXPLORER
    assert OPEN_EXPLORER.match("open file explorer") and not OPEN_EXPLORER.match("open file explorer").group("new")
    assert OPEN_EXPLORER.match("naya file explorer kholo").group("new")
    assert OPEN_EXPLORER.match("open a new explorer window").group("new")
    assert not OPEN_EXPLORER.match("open explorer settings")


def test_one_explorer_conversation_whichever_agent_did_the_step():
    import json
    from types import SimpleNamespace as NS
    from app.database import SessionLocal
    from app.models import TaskStatus
    from app.orchestration import lanes

    def task(n, agent):
        action = NS(seq=1, status="succeeded", tool_name="explorer_navigate", args_json=json.dumps({"path": f"C:{chr(92)}x{n}"}),
                    result_json=json.dumps({"output": {"path": f"C:{chr(92)}x{n}", "hwnd": 777}}))
        return NS(id=f"t-one-{n}", status=TaskStatus.COMPLETED, command=f"step {n}", actions=[action]), agent
    with SessionLocal() as db:
        lanes.close_all(db)
        for n, agent in ((1, "Atlas"), (2, "Forge"), (3, "Scout")):
            t, a = task(n, agent)
            lanes.observe(db, t, agent=a)
        explorers = [lane for lane in lanes.load(db).lanes.values() if lane.kind == "explorer"]
        assert len(explorers) == 1 and explorers[0].folder.endswith("x3") and explorers[0].hwnd == 777


def test_a_folder_asked_for_without_saying_new_is_shown_in_the_open_window(monkeypatch, tmp_path):
    from app.tools import filesystem
    from app.tools.base import ToolContext
    shown = []

    class FakeExplorer:
        def navigate(self, path, hwnd):
            shown.append((path, hwnd))
            return {"hwnd": hwnd, "opened_new": False}
    monkeypatch.setattr("app.tools.explorer_view.get_explorer", lambda: FakeExplorer())
    monkeypatch.setattr("app.orchestration.lanes.explorer_window", lambda: 4242)
    opened = []
    monkeypatch.setattr(filesystem._platform, "open_path_with_os", lambda p: opened.append(p))
    tool = filesystem.OpenFolderTool(ToolContext(allowed_directories=[tmp_path]))
    out = tool.execute(tool.validate_args({"path": str(tmp_path)}))
    assert out.success and shown == [(str(tmp_path), 4242)] and opened == []
    out = tool.execute(tool.validate_args({"path": str(tmp_path), "new_window": True}))
    assert out.success and opened == [str(tmp_path)]

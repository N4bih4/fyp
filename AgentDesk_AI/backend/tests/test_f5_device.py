"""F5: whole-PC control (lock, sleep, restart / shutdown with a cancellable countdown, keep awake, battery, airplane, Do Not Disturb, night light), the honest
"unlock" answer, "welcome back" after an unlock, and the File Explorer window controls. The OS is replaced by fakes; the real PC is exercised, with every change undone,
by scripts/device_live.py (docs/eval/f5_live.json)."""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from app.ai.device_commands import device_plan
from app.tools import device, explorer_view
from app.tools.base import RiskLevel, ToolContext
from app.tools.device import DeviceControlTool, KeepAwake, LockWatcher
from app.tools.explorer_view import ExplorerViewTool


class FakePower:
    def __init__(self):
        self.calls, self.locked, self.shutdown_code, self.abort_code = [], False, 0, 0
        self.radio_state = {"wi_fi": True, "bluetooth": True}
        self._dnd, self._night = False, False
        self.battery_info = {"percent": 80, "plugged": False, "minutes_left": 95}

    def lock(self): self.calls.append("lock"); self.locked = True
    def is_locked(self): return self.locked
    def sleep(self): self.calls.append("sleep")

    def schedule(self, kind, seconds, comment):
        self.calls.append((kind, seconds))
        return self.shutdown_code, "access denied" if self.shutdown_code else ""

    def abort(self):
        self.calls.append("abort")
        return self.abort_code, ""

    def battery(self): return self.battery_info
    def radios(self): return dict(self.radio_state)
    def set_radios(self, wanted): self.radio_state.update(wanted)
    def dnd(self): return self._dnd
    def set_dnd(self, on): self._dnd = on
    def nightlight(self): return self._night
    def set_nightlight(self, on): self._night = on; return True


@pytest.fixture()
def power(monkeypatch, tmp_path):
    fake = FakePower()
    device.set_power(fake)
    device._pending.clear()
    monkeypatch.setattr(device, "data_root", lambda: tmp_path)
    monkeypatch.setattr(device.time, "sleep", lambda s: None)
    yield fake
    device.set_power(None)
    device._pending.clear()
    device.keep_awake.cancel()


def run(tool, **raw):
    args = tool.validate_args(raw)
    result = tool.execute(args)
    return result, (tool.verify(args, result) if result.success else None)


# ------------------------------------------------------------------------------------------------- power
def test_risk_levels():
    tool = DeviceControlTool(ToolContext())
    risk = lambda **kw: tool.risk_for_args(tool.validate_args(kw))   # noqa: E731
    assert risk(action="restart") == RiskLevel.HIGH and risk(action="shutdown") == RiskLevel.HIGH
    assert risk(action="lock") == RiskLevel.MEDIUM and risk(action="sleep") == RiskLevel.MEDIUM and risk(action="airplane_on") == RiskLevel.MEDIUM
    assert risk(action="battery") == RiskLevel.LOW and risk(action="keep_awake") == RiskLevel.LOW and risk(action="cancel_shutdown") == RiskLevel.LOW


def test_there_is_no_unlock_action_and_minutes_belong_to_keep_awake():
    assert not any("unlock" in a for a in device.ACTIONS)
    with pytest.raises(ValueError):
        DeviceControlTool(ToolContext()).validate_args({"action": "unlock"})
    with pytest.raises(ValueError):
        DeviceControlTool(ToolContext()).validate_args({"action": "lock", "minutes": 5})


def test_lock_is_verified_by_the_lock_screen_being_up(power):
    result, ver = run(DeviceControlTool(ToolContext()), action="lock")
    assert result.success and ver.passed and power.calls == ["lock"]
    power.lock = lambda: power.calls.append("lock")           # Windows accepts but the desktop stays unlocked
    power.locked = False
    result, ver = run(DeviceControlTool(ToolContext()), action="lock")
    assert result.success and not ver.passed and "still unlocked" in ver.details


def test_sleep_is_accepted_not_claimed_verified(power):
    result, ver = run(DeviceControlTool(ToolContext()), action="sleep")
    assert result.success and ver.passed and power.calls == ["sleep"]
    assert "cannot be observed" in ver.details


def test_shutdown_counts_down_ten_seconds_and_cancel_stops_it(power):
    tool = DeviceControlTool(ToolContext())
    result, ver = run(tool, action="shutdown")
    assert power.calls == [("shutdown", 10)] and result.output["spoken"] == "Shutting down in 10 seconds. Say cancel to stop it." and ver.passed
    result, ver = run(tool, action="cancel_shutdown")
    assert result.success and power.calls[-1] == "abort" and ver.passed and not device._pending
    result, _ = run(tool, action="restart")
    assert power.calls[-2:] == [("restart", 10)] or ("restart", 10) in power.calls


def test_a_refused_shutdown_is_not_reported(power):
    power.shutdown_code = 5
    result, _ = run(DeviceControlTool(ToolContext()), action="shutdown")
    assert not result.success and "would not schedule" in result.error and not device._pending


def test_cancel_with_nothing_pending_says_so(power):
    power.abort_code = 1116
    result, _ = run(DeviceControlTool(ToolContext()), action="cancel_shutdown")
    assert not result.success and "no shutdown" in result.error.lower()


def test_the_spoken_stop_or_cancel_aborts_a_pending_shutdown(power, db):
    from app.config import Settings
    from app.orchestration import executor
    from app.tools.registry import ToolRegistry
    tool = DeviceControlTool(ToolContext())
    run(tool, action="shutdown")
    task = executor.start_task(db, "cancel", None, ToolRegistry(ToolContext()), Settings(ai_provider="groq", groq_api_key=None))
    db.refresh(task)
    assert task.plan_note == "Cancelled. The PC stays on." and "abort" in power.calls and not device._pending


def test_unlock_is_explained_and_nothing_is_tried(power, db):
    from app.config import Settings
    from app.orchestration import executor
    from app.tools.registry import ToolRegistry
    for text in ("unlock my pc", "pc unlock karo", "unlock the computer"):
        task = executor.start_task(db, text, None, ToolRegistry(ToolContext()), Settings(ai_provider="groq", groq_api_key=None))
        db.refresh(task)
        assert "can't unlock Windows" in task.plan_note or "unlock nahi" in task.plan_note
    assert power.calls == []


def test_keep_awake_holds_then_releases():
    calls = []
    held = KeepAwake()
    assert held.start(1, call=lambda flags: calls.append(flags) or 1)
    assert held.active and held.minutes_left in (1, 0)
    held.cancel()
    assert not held.active and calls[0] & device.ES_SYSTEM_REQUIRED and calls[-1] == device.ES_CONTINUOUS


def test_keep_awake_tool_checks_the_holder(power, monkeypatch):
    monkeypatch.setattr(device, "_execution_state", lambda flags: 1)
    monkeypatch.setattr(device, "keep_awake", KeepAwake())
    tool = DeviceControlTool(ToolContext())
    result, ver = run(tool, action="keep_awake", minutes=30)
    assert result.success and ver.passed and "30 minutes" in result.output["spoken"]
    result, ver = run(tool, action="stop_keep_awake")
    assert result.success and ver.passed
    result, _ = run(tool, action="stop_keep_awake")
    assert not result.success


def test_battery_reads_and_has_no_battery_case(power):
    result, ver = run(DeviceControlTool(ToolContext()), action="battery")
    assert result.success and ver.passed and "80 percent" in result.output["spoken"] and "95 minutes" in result.output["spoken"]
    power.battery_info = None
    result, _ = run(DeviceControlTool(ToolContext()), action="battery")
    assert not result.success and "no battery" in result.error


def test_airplane_mode_remembers_what_to_switch_back_on(power, tmp_path):
    tool = DeviceControlTool(ToolContext())
    power.radio_state = {"wi_fi": True, "bluetooth": False, "mobilebroadband": False}
    result, ver = run(tool, action="airplane_on")
    assert result.output["airplane"] is True and ver.passed and power.radio_state == {"wi_fi": False, "bluetooth": False, "mobilebroadband": False}
    assert json.loads((tmp_path / "airplane_state.json").read_text()) == {"wi_fi": True}
    result, ver = run(tool, action="airplane_off")
    assert power.radio_state["wi_fi"] is True and power.radio_state["bluetooth"] is False     # only what was on before is switched back on
    status, _ = run(tool, action="airplane_status")
    assert status.output["airplane"] is False


def test_dnd_and_night_light_are_read_back(power):
    tool = DeviceControlTool(ToolContext())
    result, ver = run(tool, action="dnd_on")
    assert power._dnd and ver.passed
    result, ver = run(tool, action="dnd_off")
    assert not power._dnd and ver.passed
    result, ver = run(tool, action="nightlight_on")
    assert power._night and ver.passed and result.output["spoken"] == "Night light is on."
    power.set_nightlight = lambda on: False                         # the Settings button did not change
    result, _ = run(tool, action="nightlight_off")
    assert not result.success and "did not switch" in result.error


# ----------------------------------------------------------------------------------------- welcome back
def test_the_watcher_notices_an_unlock_once_and_only_after_a_while():
    state = {"locked": False}
    watcher = LockWatcher(is_locked=lambda: state["locked"])
    watcher.poll(now=100)
    state["locked"] = True
    watcher.poll(now=110)
    state["locked"] = False
    watcher.poll(now=190)
    assert watcher.consume() == 80 and watcher.consume() is None
    state["locked"] = True
    watcher.poll(now=200)
    state["locked"] = False
    watcher.poll(now=205)
    assert watcher.consume() is None                                # five seconds locked: no greeting


def test_welcome_endpoint_speaks_once_and_respects_the_setting(client, db):
    from app.preferences import PreferencesUpdate, update_preferences
    update_preferences(db, PreferencesUpdate(welcome_back=True))
    device.lock_watcher.pending_seconds = 300
    assert client.get("/voice/welcome").json()["text"].startswith("Welcome back")
    assert client.get("/voice/welcome").json() == {"text": ""}
    update_preferences(db, PreferencesUpdate(welcome_back=False))
    device.lock_watcher.pending_seconds = 300
    assert client.get("/voice/welcome").json() == {"text": ""}
    update_preferences(db, PreferencesUpdate(welcome_back=True))


# ----------------------------------------------------------------------------------------- spoken commands
@pytest.mark.parametrize("text,expected", [
    ("lock my pc", ("device_control", {"action": "lock"})), ("mere pc ko lock kar do", ("device_control", {"action": "lock"})),
    ("put the laptop to sleep", ("device_control", {"action": "sleep"})), ("restart my computer", ("device_control", {"action": "restart"})),
    ("shut down the pc", ("device_control", {"action": "shutdown"})), ("computer band kar do", ("device_control", {"action": "shutdown"})),
    ("cancel the shutdown", ("device_control", {"action": "cancel_shutdown"})),
    ("keep the pc awake for 2 hours", ("device_control", {"action": "keep_awake", "minutes": 120})),
    ("don't let it sleep for 30 minutes", ("device_control", {"action": "keep_awake", "minutes": 30})),
    ("how much battery is left", ("device_control", {"action": "battery"})), ("turn on airplane mode", ("device_control", {"action": "airplane_on"})),
    ("do not disturb off", ("device_control", {"action": "dnd_off"})), ("turn on night light", ("device_control", {"action": "nightlight_on"})),
    ("sort by date newest first", ("explorer_view", {"action": "sort", "by": "date", "descending": True})),
    ("sort by name", ("explorer_view", {"action": "sort", "by": "name", "descending": False})),
    ("show as details", ("explorer_view", {"action": "view", "mode": "details"})), ("show hidden files", ("explorer_view", {"action": "hidden", "show": True})),
    ("search this folder for fyp", ("explorer_view", {"action": "search", "query": "fyp"})),
    (r"properties of C:\Users\HP\Documents\a.txt", ("explorer_view", {"action": "properties", "path": r"C:\Users\HP\Documents\a.txt"}))])
def test_spoken_commands(text, expected):
    plan = device_plan(text)
    assert plan is not None and (plan.actions[0].tool, plan.actions[0].args) == expected


@pytest.mark.parametrize("text", ["open chrome", "turn off the light", "volume 40", "restart the game", "lock the door", "sleep well", "sort my life out", "battery"])
def test_other_sentences_are_left_alone(text):
    plan = device_plan(text)
    assert plan is None or text == "battery"          # "battery" alone is a question about the battery: that one is meant


def test_the_new_tools_are_registered_and_shortlisted():
    from app.nlu.shortlist import shortlist_tools
    from app.tools.registry import ToolRegistry
    registry = ToolRegistry(ToolContext())
    names = registry.model_names()
    assert "device_control" in names and "explorer_view" in names
    assert "device_control" in shortlist_tools("lock my pc", names) and "explorer_view" in shortlist_tools("sort by date", names)
    assert "device_control" not in shortlist_tools("open notepad", names)


# ------------------------------------------------------------------------------------------ File Explorer
class FakeExplorer:
    def __init__(self, window=True):
        self.window = {"path": r"C:\Work", "title": "Work"} if window else None
        self.sort_value, self.view_value, self.hidden_value, self.titles, self.opened = "prop:System.ItemNameDisplay;", 4, False, [], []

    def front(self): return self.window
    def set_sort(self, c): self.sort_value = c
    def sort(self): return self.sort_value
    def set_view(self, m): self.view_value = m
    def view(self): return self.view_value
    def hidden(self): return self.hidden_value
    def set_hidden(self, show): self.hidden_value = show
    def properties(self, path): self.opened.append(path); self.titles = [f"{Path(path).stem} Properties"]
    def window_titles(self): return self.titles
    def search(self, folder, query): self.opened.append((folder, query)); self.titles = ["Search Results in Work - File Explorer"]


@pytest.fixture()
def explorer(monkeypatch, tmp_path):
    fake = FakeExplorer()
    explorer_view.set_explorer(fake)
    monkeypatch.setattr(explorer_view.time, "sleep", lambda s: None)
    yield fake, ExplorerViewTool(ToolContext(allowed_directories=[tmp_path])), tmp_path
    explorer_view.set_explorer(None)


def test_sort_and_view_are_read_back_from_the_folder_view(explorer):
    fake, tool, _ = explorer
    result, ver = run(tool, action="sort", by="date", descending=True)
    assert fake.sort_value == "prop:-System.DateModified;" and ver.passed and "Sorted by date" in result.output["spoken"]
    result, ver = run(tool, action="view", mode="list")
    assert fake.view_value == 3 and ver.passed
    fake.set_view = lambda m: None                                 # Explorer ignored it
    result, ver = run(tool, action="view", mode="icons")
    assert result.success and not ver.passed


def test_without_an_explorer_window_it_says_so(explorer):
    fake, tool, _ = explorer
    fake.window = None
    result, _ = run(tool, action="sort", by="name")
    assert not result.success and "No File Explorer window" in result.error


def test_hidden_files_is_a_setting_so_it_asks_and_it_is_read_back(explorer):
    fake, tool, _ = explorer
    assert tool.risk_for_args(tool.validate_args({"action": "hidden", "show": True})) == RiskLevel.MEDIUM
    assert tool.risk_for_args(tool.validate_args({"action": "sort", "by": "name"})) == RiskLevel.LOW
    result, ver = run(tool, action="hidden", show=True)
    assert fake.hidden_value is True and ver.passed and result.output["was"] is False


def test_properties_needs_a_real_path_inside_the_allowed_folders_and_the_dialog_must_open(explorer):
    fake, tool, tmp = explorer
    file = tmp / "report.docx"
    file.write_text("x")
    result, ver = run(tool, action="properties", path=str(file))
    assert result.success and ver.passed and fake.opened == [str(file)]                  # "report Properties": Windows hides the extension
    result, _ = run(tool, action="properties", path=str(tmp / "missing.txt"))
    assert not result.success and "does not exist" in result.error
    result, _ = run(tool, action="properties", path=r"C:\Windows\System32\config\SAM")
    assert not result.success


def test_search_opens_the_results_window_and_rejects_odd_characters(explorer):
    fake, tool, tmp = explorer
    result, ver = run(tool, action="search", query="fyp report", path=str(tmp))
    assert result.success and ver.passed and fake.opened == [(str(tmp), "fyp report")]
    for bad in ('a"b', "a|b", "a\\b"):
        with pytest.raises(ValueError):
            tool.validate_args({"action": "search", "query": bad})


def test_each_action_needs_its_own_argument():
    tool = ExplorerViewTool(ToolContext())
    for bad in ({"action": "sort"}, {"action": "view"}, {"action": "hidden"}, {"action": "properties"}, {"action": "search"}):
        with pytest.raises(ValueError):
            tool.validate_args(bad)

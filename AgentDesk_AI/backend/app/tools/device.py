"""Whole-PC controls beyond volume / brightness: lock, sleep, restart / shutdown with a countdown that can be cancelled, keep awake, battery,
airplane mode, Do Not Disturb, night light.

Honest limits, enforced here and in the answers:
 - UNLOCK is not possible for any program: Windows shows the lock screen on a protected desktop that no app may control. This tool has no unlock action;
   a spoken "unlock my PC" gets an explanation (orchestration/session_commands.py). `keep_awake` stops the PC sleeping, and `LockWatcher` greets you after you unlock.
 - Sleep cannot be observed afterwards (the PC sleeps): it is reported as "accepted by Windows", never "verified".
 - Restart / shutdown are HIGH risk (a click on Approve), then Windows' own timer counts COUNTDOWN_SECONDS seconds in which "cancel" aborts it.
 - Night light is switched through the Settings page (there is no supported API): it needs the English Settings, and is read back from the same button.
Everything the OS does is behind `PowerBackend`, so the tests run on a fake.
"""
from __future__ import annotations

import ctypes
import json
import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field, model_validator

from ..runtime import data_root
from .base import BaseTool, RiskLevel, ToolResult, Verification

COUNTDOWN_SECONDS = 10
ES_CONTINUOUS, ES_SYSTEM_REQUIRED, ES_DISPLAY_REQUIRED = 0x80000000, 0x00000001, 0x00000002
NOTIFY_KEY = r"Software\Microsoft\Windows\CurrentVersion\Notifications\Settings"
NOTIFY_VALUE = "NOC_GLOBAL_SETTING_TOASTS_ENABLED"

ACTIONS = ("lock", "sleep", "restart", "shutdown", "cancel_shutdown", "keep_awake", "stop_keep_awake", "battery", "airplane_on", "airplane_off",
           "airplane_status", "dnd_on", "dnd_off", "dnd_status", "nightlight_on", "nightlight_off", "nightlight_status")


class PowerBackend(Protocol):
    def lock(self) -> None: ...
    def is_locked(self) -> bool: ...
    def sleep(self) -> None: ...
    def schedule(self, kind: str, seconds: int, comment: str) -> tuple[int, str]: ...
    def abort(self) -> tuple[int, str]: ...
    def battery(self) -> dict | None: ...
    def radios(self) -> dict[str, bool]: ...
    def set_radios(self, wanted: dict[str, bool]) -> None: ...
    def dnd(self) -> bool: ...
    def set_dnd(self, on: bool) -> None: ...
    def nightlight(self) -> bool | None: ...
    def set_nightlight(self, on: bool) -> bool: ...


# ------------------------------------------------------------------------------------------------ keep awake
class KeepAwake:
    """SetThreadExecutionState lasts only while the thread that called it lives: one daemon thread holds it until the deadline or until stopped."""

    def __init__(self):
        self.thread: threading.Thread | None = None
        self.stop = threading.Event()
        self.until = 0.0
        self.accepted = False

    def start(self, minutes: int, call=None) -> bool:
        self.cancel()
        call = call or _execution_state
        self.stop = threading.Event()
        self.until = time.time() + minutes * 60
        started = threading.Event()

        def hold():
            self.accepted = bool(call(ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED))
            started.set()
            while not self.stop.wait(1.0) and time.time() < self.until:
                pass
            call(ES_CONTINUOUS)

        self.thread = threading.Thread(target=hold, daemon=True, name="keep-awake")
        self.thread.start()
        started.wait(3)
        return self.accepted

    def cancel(self) -> bool:
        was = self.active
        self.stop.set()
        if self.thread is not None:
            self.thread.join(timeout=3)
        self.thread = None
        return was

    @property
    def active(self) -> bool:
        return self.thread is not None and self.thread.is_alive() and time.time() < self.until

    @property
    def minutes_left(self) -> int:
        return max(0, int((self.until - time.time()) / 60 + 0.5)) if self.active else 0


def _execution_state(flags: int) -> int:
    return int(ctypes.windll.kernel32.SetThreadExecutionState(ctypes.c_uint(flags)))


keep_awake = KeepAwake()
_pending: dict[str, Any] = {}          # the shutdown / restart that is counting down: {"kind", "at"}


# ------------------------------------------------------------------------------------------------ the real PC
class WindowsPower:
    def lock(self) -> None:
        if not ctypes.windll.user32.LockWorkStation():
            raise OSError("Windows refused to lock the workstation")

    def is_locked(self) -> bool:
        """The input desktop is the secure one (not switchable to) while the lock screen is up."""
        user32 = ctypes.windll.user32
        desk = user32.OpenInputDesktop(0, False, 0x0100)
        if not desk:
            return True
        try:
            return not user32.SwitchDesktop(desk)
        finally:
            user32.CloseDesktop(desk)

    def sleep(self) -> None:
        ctypes.windll.powrprof.SetSuspendState(0, 0, 0)       # sleep, not hibernate; do not force

    def schedule(self, kind: str, seconds: int, comment: str) -> tuple[int, str]:
        flag = "/r" if kind == "restart" else "/s"
        done = subprocess.run(["shutdown", flag, "/t", str(seconds), "/c", comment], capture_output=True, text=True, timeout=15,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return done.returncode, (done.stderr or done.stdout).strip()[:200]

    def abort(self) -> tuple[int, str]:
        done = subprocess.run(["shutdown", "/a"], capture_output=True, text=True, timeout=15, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return done.returncode, (done.stderr or done.stdout).strip()[:200]

    def battery(self) -> dict | None:
        import psutil
        b = psutil.sensors_battery()
        if b is None:
            return None
        return {"percent": int(round(b.percent)), "plugged": bool(b.power_plugged), "minutes_left": None if b.secsleft in (-1, -2) else int(b.secsleft // 60)}

    # -- radios (airplane mode = every Wi-Fi / Bluetooth / mobile radio off)
    def radios(self) -> dict[str, bool]:
        import asyncio
        from winsdk.windows.devices.radios import Radio, RadioState

        async def read():
            out = {}
            for r in await Radio.get_radios_async():
                out.setdefault(str(r.kind).split(".")[-1].lower(), r.state == RadioState.ON)
                if r.state == RadioState.ON:
                    out[str(r.kind).split(".")[-1].lower()] = True
            return out
        return asyncio.run(asyncio.wait_for(read(), timeout=8))

    def set_radios(self, wanted: dict[str, bool]) -> None:
        import asyncio
        from winsdk.windows.devices.radios import Radio, RadioAccessStatus, RadioState

        async def change():
            if await Radio.request_access_async() != RadioAccessStatus.ALLOWED:
                raise PermissionError("Windows did not allow changing the radios")
            for r in await Radio.get_radios_async():
                kind = str(r.kind).split(".")[-1].lower()
                if kind in wanted:
                    await r.set_state_async(RadioState.ON if wanted[kind] else RadioState.OFF)
        asyncio.run(asyncio.wait_for(change(), timeout=15))

    # -- Do Not Disturb (the "get notifications" master switch, the same value the Notification centre toggle writes)
    def dnd(self) -> bool:
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, NOTIFY_KEY) as key:
                return winreg.QueryValueEx(key, NOTIFY_VALUE)[0] == 0
        except FileNotFoundError:
            return False

    def set_dnd(self, on: bool) -> None:
        import winreg
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, NOTIFY_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, NOTIFY_VALUE, 0, winreg.REG_DWORD, 0 if on else 1)

    # -- night light, through the Settings page's own button
    def _night_page(self):
        from .uia import get_service
        os.startfile("ms-settings:nightlight")             # noqa: S606 - a fixed Windows URI
        service = get_service()
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            try:
                window = service.window("Settings")
                snap = service.snapshot(window, fresh=True)
                if any(c.name in ("Turn on now", "Turn off now") for c in snap.controls):
                    return service, window, snap
            except Exception:  # noqa: BLE001 - the page is still opening
                pass
            time.sleep(0.5)
        raise RuntimeError("The Night light page did not open (it needs the English Windows Settings).")

    def nightlight(self) -> bool | None:
        service, window, snap = self._night_page()
        try:
            return any(c.name == "Turn off now" for c in snap.controls)
        finally:
            self._close_settings(service, window, snap)

    def set_nightlight(self, on: bool) -> bool:
        service, window, snap = self._night_page()
        try:
            want, now = ("Turn on now", "Turn off now") if on else ("Turn off now", "Turn on now")
            button = next((c for c in snap.controls if c.name == want), None)
            if button is None:
                return any(c.name == now for c in snap.controls) == on          # already in the requested state
            service.backend.click(window, button)
            deadline = time.monotonic() + 4
            while time.monotonic() < deadline:
                time.sleep(0.4)
                snap = service.snapshot(window, fresh=True)
                if any(c.name == now for c in snap.controls):
                    return True
            return False
        finally:
            try:
                self._close_settings(service, window, service.snapshot(window, fresh=True))
            except Exception:  # noqa: BLE001
                pass

    @staticmethod
    def _close_settings(service, window, snap) -> None:
        close = next((c for c in snap.controls if c.name == "Close Settings"), None)
        if close is not None:
            service.backend.click(window, close)


_backend: PowerBackend | None = None


def get_power() -> PowerBackend:
    global _backend
    if _backend is None:
        _backend = WindowsPower()
    return _backend


def set_power(backend: PowerBackend | None) -> None:
    global _backend
    _backend = backend


def abort_pending() -> bool:
    """Cancel a counting-down shutdown / restart. True if one was cancelled (also used by the spoken 'cancel' / 'stop')."""
    if not _pending:
        return False
    code, _ = get_power().abort()
    _pending.clear()
    return code == 0


# ------------------------------------------------------------------------------------------------ the tool
class DeviceControlArgs(BaseModel):
    action: Literal["lock", "sleep", "restart", "shutdown", "cancel_shutdown", "keep_awake", "stop_keep_awake", "battery", "airplane_on", "airplane_off",
                    "airplane_status", "dnd_on", "dnd_off", "dnd_status", "nightlight_on", "nightlight_off", "nightlight_status"]
    minutes: int | None = Field(default=None, ge=1, le=720, description="keep_awake: how long")

    @model_validator(mode="after")
    def _minutes(self):
        if self.action == "keep_awake" and self.minutes is None:
            self.minutes = 60
        if self.action != "keep_awake" and self.minutes is not None:
            raise ValueError("minutes is only used by keep_awake")
        return self


class DeviceControlTool(BaseTool):
    name = "device_control"
    description = ("PC power and modes: lock, sleep, restart / shutdown (asks, 10 s countdown, can be cancelled), keep awake N minutes, battery, airplane mode, "
                   "Do Not Disturb, night light (on / off / status). It cannot unlock Windows: nothing can.")
    args_schema = DeviceControlArgs
    risk_level = RiskLevel.MEDIUM
    isolation = "thread"        # keep-awake and the pending shutdown live in the server process
    timeout_seconds = 40

    def risk_for_args(self, args: BaseModel | None) -> RiskLevel:
        action = getattr(args, "action", None)
        if action in ("restart", "shutdown"):
            return RiskLevel.HIGH
        if action in ("lock", "sleep", "airplane_on", "airplane_off"):
            return RiskLevel.MEDIUM
        return RiskLevel.LOW

    # ---------------------------------------------------------------------------------------------- run
    def execute(self, args: BaseModel) -> ToolResult:
        a = DeviceControlArgs.model_validate(args.model_dump())
        power = get_power()
        try:
            if a.action == "lock":
                power.lock()
                return ToolResult(success=True, output={"action": "lock", "spoken": "Locking the PC."})
            if a.action == "sleep":
                power.sleep()
                return ToolResult(success=True, output={"action": "sleep", "spoken": "Going to sleep."})
            if a.action in ("restart", "shutdown"):
                code, text = power.schedule(a.action, COUNTDOWN_SECONDS, f"Agent X: {a.action} in {COUNTDOWN_SECONDS} seconds. Say cancel to stop it.")
                if code != 0:
                    return ToolResult(success=False, error=f"Windows would not schedule the {a.action}: {text or 'exit code ' + str(code)}")
                _pending.update(kind=a.action, at=time.time() + COUNTDOWN_SECONDS)
                word = "Restarting" if a.action == "restart" else "Shutting down"
                return ToolResult(success=True, output={"action": a.action, "seconds": COUNTDOWN_SECONDS, "cancellable": True,
                                                        "spoken": f"{word} in {COUNTDOWN_SECONDS} seconds. Say cancel to stop it."})
            if a.action == "cancel_shutdown":
                if abort_pending():
                    return ToolResult(success=True, output={"action": a.action, "cancelled": True, "spoken": "Cancelled. The PC stays on."})
                code, _ = power.abort()
                if code == 0:
                    return ToolResult(success=True, output={"action": a.action, "cancelled": True, "spoken": "Cancelled. The PC stays on."})
                return ToolResult(success=False, error="There is no shutdown or restart counting down.")
            if a.action == "keep_awake":
                ok = keep_awake.start(a.minutes or 60)
                if not ok:
                    return ToolResult(success=False, error="Windows did not accept the keep-awake request.")
                return ToolResult(success=True, output={"action": a.action, "minutes": a.minutes, "spoken": f"I will keep the PC awake for {a.minutes} minutes."})
            if a.action == "stop_keep_awake":
                if not keep_awake.cancel():
                    return ToolResult(success=False, error="I was not keeping the PC awake.")
                return ToolResult(success=True, output={"action": a.action, "spoken": "The PC may sleep again."})
            if a.action == "battery":
                b = power.battery()
                if b is None:
                    return ToolResult(success=False, error="This PC has no battery to read.")
                left = f", about {b['minutes_left']} minutes left" if b.get("minutes_left") and not b["plugged"] else ""
                return ToolResult(success=True, output={"action": a.action, **b, "spoken": f"Battery is at {b['percent']} percent, {'charging' if b['plugged'] else 'not charging'}{left}."})
            if a.action.startswith("airplane"):
                return self._airplane(a.action, power)
            if a.action.startswith("dnd"):
                if a.action != "dnd_status":
                    power.set_dnd(a.action == "dnd_on")
                on = power.dnd()
                return ToolResult(success=True, output={"action": a.action, "dnd": on, "spoken": "Do Not Disturb is on." if on else "Do Not Disturb is off."})
            on = power.nightlight() if a.action == "nightlight_status" else (a.action == "nightlight_on")
            if a.action != "nightlight_status" and not power.set_nightlight(on):
                return ToolResult(success=False, error="Windows did not switch Night light (the Settings page did not change).")
            return ToolResult(success=True, output={"action": a.action, "nightlight": on, "spoken": "Night light is on." if on else "Night light is off."})
        except Exception as exc:  # noqa: BLE001 - the OS has many ways to say no; keep the message short
            return ToolResult(success=False, error=f"{a.action.replace('_', ' ').capitalize()} failed: {type(exc).__name__}: {str(exc)[:120]}")

    @staticmethod
    def _airplane(action: str, power: PowerBackend) -> ToolResult:
        state_file = Path(data_root()) / "airplane_state.json"
        radios = power.radios()
        if action == "airplane_status":
            on = bool(radios) and not any(radios.values())
            return ToolResult(success=True, output={"action": action, "airplane": on, "radios": radios, "spoken": "Airplane mode is on." if on else "Airplane mode is off."})
        if action == "airplane_on":
            if any(radios.values()):
                state_file.write_text(json.dumps({k: v for k, v in radios.items() if v}), encoding="utf-8")   # what to switch back on later
            power.set_radios({k: False for k in radios})
            now = power.radios()
            return ToolResult(success=True, output={"action": action, "airplane": not any(now.values()), "radios": now,
                                                    "spoken": "Airplane mode is on. Wi-Fi and Bluetooth are off."})
        try:
            saved = json.loads(state_file.read_text(encoding="utf-8"))          # exactly what was on before airplane mode
        except (OSError, ValueError):
            saved = {k: True for k in radios if k in ("wi_fi", "bluetooth")}       # no record: Wi-Fi and Bluetooth come back
        power.set_radios({k: bool(saved.get(k, False)) for k in radios})
        now = power.radios()
        return ToolResult(success=True, output={"action": action, "airplane": not any(now.values()), "radios": now, "spoken": "Airplane mode is off."})

    # ---------------------------------------------------------------------------------------------- verify
    def verify(self, args: BaseModel, result: ToolResult) -> Verification:
        if not result.success:
            return Verification(passed=False, checks=["action done"], details=result.error)
        a = DeviceControlArgs.model_validate(args.model_dump())
        out, power = result.output, get_power()
        try:
            if a.action == "lock":
                deadline = time.monotonic() + 4
                while time.monotonic() < deadline:
                    if power.is_locked():
                        return Verification(passed=True, checks=["the lock screen is up"], evidence={"locked": True})
                    time.sleep(0.3)
                return Verification(passed=False, checks=["the lock screen is up"], details="Windows accepted the request but the desktop is still unlocked.")
            if a.action == "sleep":
                return Verification(passed=True, checks=["Windows accepted the sleep request"], evidence={"observable_afterwards": False},
                                    details="A sleeping PC cannot be observed; Windows accepted the request.")
            if a.action in ("restart", "shutdown"):
                still = bool(_pending) and _pending.get("kind") == a.action
                return Verification(passed=still, checks=[f"Windows scheduled the {a.action}"], evidence={"seconds": out.get("seconds"), "cancellable": True})
            if a.action == "cancel_shutdown":
                return Verification(passed=not _pending, checks=["no shutdown is counting down"], evidence={"cancelled": out.get("cancelled")})
            if a.action == "keep_awake":
                return Verification(passed=keep_awake.active, checks=["the keep-awake request is held"], evidence={"minutes_left": keep_awake.minutes_left})
            if a.action == "stop_keep_awake":
                return Verification(passed=not keep_awake.active, checks=["the keep-awake request is released"])
            if a.action == "battery":
                b = power.battery()
                return Verification(passed=b is not None and abs(b["percent"] - out.get("percent", -99)) <= 2, checks=["the battery was read again"], evidence={"now": b})
            if a.action.startswith("airplane"):
                now = power.radios()
                want = {"airplane_on": True, "airplane_off": False}.get(a.action, out.get("airplane"))
                return Verification(passed=(bool(now) and not any(now.values())) is want, checks=["the radios were read again"], evidence={"radios": now})
            if a.action.startswith("dnd"):
                want = {"dnd_on": True, "dnd_off": False}.get(a.action, out.get("dnd"))
                return Verification(passed=power.dnd() is want, checks=["the notification switch was read again"], evidence={"dnd": power.dnd()})
            now = power.nightlight()
            want = {"nightlight_on": True, "nightlight_off": False}.get(a.action, out.get("nightlight"))
            return Verification(passed=now is want, checks=["the Night light button was read again"], evidence={"nightlight": now})
        except Exception as exc:  # noqa: BLE001
            return Verification(passed=False, checks=["read back"], details=f"{type(exc).__name__}: {str(exc)[:120]}")


# ------------------------------------------------------------------------------------------------ welcome back after unlock
class LockWatcher:
    """Notices locked -> unlocked and remembers it once, for the page to greet the user ("Welcome back")."""

    def __init__(self, is_locked=None):
        self.is_locked = is_locked or (lambda: get_power().is_locked())
        self.was_locked = False
        self.locked_at = 0.0
        self.pending_seconds: int | None = None

    def poll(self, now: float | None = None) -> None:
        now = now if now is not None else time.time()
        locked = bool(self.is_locked())
        if locked and not self.was_locked:
            self.locked_at = now
        if self.was_locked and not locked:
            self.pending_seconds = int(now - self.locked_at)
        self.was_locked = locked

    def consume(self, min_seconds: int = 20) -> int | None:
        """Seconds the PC was locked, once, if long enough to deserve a greeting; else None."""
        seconds, self.pending_seconds = self.pending_seconds, None
        return seconds if seconds is not None and seconds >= min_seconds else None

    def start(self, interval: float = 3.0) -> threading.Thread:
        def loop():
            while True:
                try:
                    self.poll()
                except Exception:  # noqa: BLE001 - a watcher must never die
                    pass
                time.sleep(interval)
        thread = threading.Thread(target=loop, daemon=True, name="lock-watcher")
        thread.start()
        return thread


lock_watcher = LockWatcher()


def device_tools(ctx) -> list[BaseTool]:
    return [DeviceControlTool(ctx)]

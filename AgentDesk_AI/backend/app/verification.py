"""Independent checks of real system state, used by every tool's verify().

A verifier must look at the system again, not at what the tool said it did:
- files: exists + size + SHA-256 (bounded),
- processes: psutil,
- windows: Win32 enumeration (fast, for polling) and pywinauto UIA (dialog
  text, e.g. an unsaved-changes prompt),
- volume / mute: a fresh pycaw read in the isolated system worker,
- brightness: WMI first (screen_brightness_control method="wmi"), then the
  library default for external monitors,
- theme: HKCU Personalize registry values,
- radios: a fresh WinRT read in the system worker.

`current()` returns the active probe. Tests install a fake with
`use_probe(...)`, so verifiers are exercised without Windows.
"""
from __future__ import annotations

import contextlib
import hashlib
import sys
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Iterator

HASH_LIMIT_BYTES = 64 * 1024 * 1024
BROWSER_PROCESSES = {"chrome.exe", "msedge.exe", "firefox.exe", "brave.exe", "opera.exe", "vivaldi.exe"}
MAIL_PROCESSES = {"outlook.exe", "olk.exe", "hxoutlook.exe", "thunderbird.exe", "mailclient.exe"}


class ProbeUnavailable(RuntimeError):
    """The check cannot run here (wrong OS, missing library). Never counts as a pass."""


@dataclass
class WindowInfo:
    hwnd: int | None
    title: str
    pid: int | None = None
    process: str | None = None
    minimized: bool | None = None
    maximized: bool | None = None
    foreground: bool = False

    def as_evidence(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


# ------------------------------------------------------------------ files
def file_evidence(path: str | Path, with_hash: bool = True) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return {"path": str(p), "exists": False}
    if p.is_dir():
        return {"path": str(p), "exists": True, "is_dir": True}
    size = p.stat().st_size
    out: dict[str, Any] = {"path": str(p), "exists": True, "is_dir": False, "size": size}
    if with_hash and size <= HASH_LIMIT_BYTES:
        digest = hashlib.sha256()
        with p.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                digest.update(chunk)
        out["sha256"] = digest.hexdigest()
    return out


def text_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def wait_until(check: Callable[[], Any], timeout: float = 4.0, interval: float = 0.25) -> tuple[bool, Any]:
    """Poll `check` until it returns a truthy value or time runs out."""
    deadline = time.monotonic() + timeout
    last: Any = None
    while True:
        try:
            last = check()
        except ProbeUnavailable:
            raise
        except Exception as exc:  # noqa: BLE001 - a failing read is "not yet"
            last = exc
        if last and not isinstance(last, Exception):
            return True, last
        if time.monotonic() >= deadline:
            return False, last
        time.sleep(interval)


# ------------------------------------------------------------------ probe
class SystemProbe:
    """Real probe. Windows-only methods raise ProbeUnavailable elsewhere."""

    poll_timeout = 4.0

    @staticmethod
    def _require_windows() -> None:
        if sys.platform != "win32":
            raise ProbeUnavailable("This check needs Windows.")

    # processes -------------------------------------------------------
    def process_alive(self, pid: int) -> bool:
        import psutil

        try:
            return psutil.Process(pid).is_running() and psutil.Process(pid).status() != psutil.STATUS_ZOMBIE
        except psutil.Error:
            return False

    def processes_named(self, names: set[str]) -> list[int]:
        import psutil

        wanted = {n.casefold() for n in names}
        return [p.info["pid"] for p in psutil.process_iter(["pid", "name"])
                if (p.info.get("name") or "").casefold() in wanted]

    # windows ---------------------------------------------------------
    def windows(self) -> list[WindowInfo]:
        self._require_windows()
        import ctypes
        from ctypes import wintypes

        import psutil

        user32 = ctypes.windll.user32
        foreground = int(user32.GetForegroundWindow() or 0)
        found: list[WindowInfo] = []
        names: dict[int, str | None] = {}

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def callback(hwnd, _):
            if not user32.IsWindowVisible(hwnd):
                return True
            length = user32.GetWindowTextLengthW(hwnd)
            if length == 0:
                return True
            buffer = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buffer, length + 1)
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value not in names:
                try:
                    names[pid.value] = psutil.Process(pid.value).name()
                except psutil.Error:
                    names[pid.value] = None
            found.append(WindowInfo(int(hwnd), buffer.value, pid.value, names[pid.value],
                                    bool(user32.IsIconic(hwnd)), bool(user32.IsZoomed(hwnd)),
                                    int(hwnd) == foreground))
            return True

        user32.EnumWindows(callback, 0)
        return found

    def window(self, hwnd: int) -> WindowInfo | None:
        return next((w for w in self.windows() if w.hwnd == hwnd), None)

    def dialog_texts(self, pid: int) -> list[str]:
        """Text of dialogs owned by a process (pywinauto UIA), e.g. 'Do you want to save?'."""
        self._require_windows()
        try:
            from pywinauto import Desktop
        except ImportError as exc:
            raise ProbeUnavailable("pywinauto is not installed.") from exc
        texts: list[str] = []
        for win in Desktop(backend="uia").windows(process=pid):
            try:
                for child in win.descendants(control_type="Text")[:20]:
                    if child.window_text():
                        texts.append(child.window_text())
                for child in win.descendants(control_type="Button")[:10]:
                    if child.window_text():
                        texts.append(child.window_text())
                for child in win.descendants(control_type="Edit")[:10] + win.descendants(control_type="Document")[:5]:
                    value = child.window_text() or getattr(child, "get_value", lambda: "")()
                    if value:
                        texts.append(str(value))
            except Exception:  # noqa: BLE001 - a vanished window has no text
                continue
        return texts

    # settings --------------------------------------------------------
    def read_setting(self, setting: str) -> dict[str, Any]:
        """Fresh read in a separate worker process (COM state is not shared with the setter)."""
        self._require_windows()
        from .tools.base import ToolContext
        from .tools.system import ManageSystemSettingArgs, ManageSystemSettingTool

        tool = ManageSystemSettingTool(ToolContext(isolate_system_controls=True))
        if setting == "brightness":
            return self.brightness()
        result = tool.execute(ManageSystemSettingArgs(setting=setting, action="get"))
        if not result.success:
            raise RuntimeError(result.error or f"could not read {setting}")
        return dict(result.output)

    def brightness(self) -> dict[str, Any]:
        self._require_windows()
        import screen_brightness_control as sbc

        for method in ("wmi", None):
            try:
                values = sbc.get_brightness(display=0, method=method) if method else sbc.get_brightness(display=0)
            except Exception:  # noqa: BLE001 - external monitors have no WMI method
                continue
            if values:
                return {"setting": "brightness", "value": int(round(float(values[0]))), "method": method or "default"}
        raise RuntimeError("No display reported a brightness level.")

    def find_windows(self, **criteria) -> list[WindowInfo]:
        return find_windows(self, **criteria)

    def wait_for_window(self, timeout: float | None = None, **criteria) -> tuple[bool, list[WindowInfo]]:
        ok, value = wait_until(lambda: self.find_windows(**criteria), timeout or self.poll_timeout)
        return ok, value if isinstance(value, list) else []

    def media_session(self) -> dict[str, Any] | None:
        """Current Windows media session (SMTC): app, title, artist, status. None if no app reports one."""
        self._require_windows()
        import asyncio

        try:
            from winsdk.windows.media.control import GlobalSystemMediaTransportControlsSessionManager as Manager
        except ImportError as exc:
            raise ProbeUnavailable("winsdk media control is not installed.") from exc

        async def read():
            manager = await Manager.request_async()
            session = manager.get_current_session()
            if session is None:
                return None
            props = await session.try_get_media_properties_async()
            status = int(session.get_playback_info().playback_status)
            names = {0: "closed", 1: "opened", 2: "changing", 3: "stopped", 4: "playing", 5: "paused"}
            return {"app": session.source_app_user_model_id, "title": props.title or "", "artist": props.artist or "",
                    "status": names.get(status, str(status))}
        return asyncio.run(read())

    def theme(self) -> dict[str, str]:
        self._require_windows()
        from .tools.system import ManageSystemSettingTool

        return ManageSystemSettingTool._theme()


_probe: SystemProbe = SystemProbe()
_lock = threading.Lock()


def current() -> SystemProbe:
    return _probe


@contextlib.contextmanager
def use_probe(probe: Any) -> Iterator[Any]:
    global _probe
    with _lock:
        old, _probe = _probe, probe
    try:
        yield probe
    finally:
        with _lock:
            _probe = old


# ------------------------------------------------------------------ window matching
def find_windows(probe: SystemProbe, *, title_contains: list[str] | None = None,
                 processes: set[str] | None = None, pid: int | None = None,
                 match: str = "all") -> list[WindowInfo]:
    """Windows meeting the given criteria; match="all" (AND) or "any" (OR)."""
    needles = [n.casefold() for n in (title_contains or []) if n]
    procs = {p.casefold() for p in (processes or set())}
    out = []
    for w in probe.windows():
        checks = []
        if needles:
            checks.append(any(n in (w.title or "").casefold() for n in needles))
        if procs:
            checks.append((w.process or "").casefold() in procs)
        if pid:
            checks.append(w.pid == pid)
        if checks and (all(checks) if match == "all" else any(checks)):
            out.append(w)
    return out


# ------------------------------------------------------------------ verdict helpers
def verdict(checks: list[tuple[str, bool]], evidence: dict[str, Any], details: str | None = None):
    """Build a Verification: passes only if every check holds AND evidence exists."""
    from .tools.base import Verification

    passed = bool(checks) and all(ok for _, ok in checks) and bool(evidence)
    return Verification(passed=passed, checks=[f"{name}: {ok}" for name, ok in checks],
                        evidence=evidence, details=details)


def failed_result(result) -> Any:
    from .tools.base import Verification

    return Verification(passed=False, checks=[], details=result.error or "tool reported failure")


def window_check(timeout: float | None = None, **criteria) -> tuple[bool, dict[str, Any]]:
    """Wait for a window matching `criteria` on the real desktop; evidence lists what was seen."""
    probe = current()
    try:
        ok, found = probe.wait_for_window(timeout=timeout, **criteria)
    except ProbeUnavailable as exc:
        return False, {"window_probe": "unavailable", "reason": str(exc)}
    return ok, {"windows": [w.as_evidence() for w in found[:3]],
                "criteria": {k: (sorted(v) if isinstance(v, set) else v) for k, v in criteria.items()}}

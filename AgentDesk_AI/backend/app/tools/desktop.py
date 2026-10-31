"""Bounded keyboard and mouse control for the currently focused desktop."""
from __future__ import annotations

import ctypes
import re
import sys
import time
from difflib import SequenceMatcher
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..verification import ProbeUnavailable, current, failed_result, verdict
from .base import BaseTool, RiskLevel, ToolResult, Verification

_NAMED_KEYS = {
    "alt", "backspace", "ctrl", "delete", "down", "end", "enter", "esc",
    "home", "insert", "left", "pagedown", "pageup", "right", "shift", "space",
    "tab", "up", "win",
}
_NAMED_KEYS.update(f"f{number}" for number in range(1, 13))

_WM_CLOSE = 0x0010
_WM_SYSCOMMAND = 0x0112
_SC_CLOSE = 0xF060
_SW_RESTORE = 9


# Typed input into a shell is arbitrary command execution, which this product
# never allows an LLM to perform, even with user approval. Closing, minimising
# and inspecting these windows remains supported.
_INPUT_ACTIONS = {"click", "type_text", "press_key", "hotkey", "scroll"}
_WINDOW_STATE_ACTIONS = {"minimize_window", "maximize_window", "restore_window", "focus_window"}
_SAVE_PROMPT_WORDS = ("save", "don't save", "dont save", "محفوظ", "सहेज", "सेव")
_SHELL_PROCESSES = {
    "powershell.exe", "pwsh.exe", "cmd.exe", "windowsterminal.exe", "wt.exe", "conhost.exe",
    "openconsole.exe", "wsl.exe", "wslhost.exe", "bash.exe", "mintty.exe", "regedit.exe",
    "mmc.exe", "taskmgr.exe", "python.exe", "pythonw.exe", "py.exe",
}
_SHELL_TITLE_WORDS = {"powershell", "pwsh", "cmd", "terminal", "bash", "wsl", "ubuntu", "mingw", "regedit", "mintty", "conhost"}
_SHELL_TITLE_PHRASES = ("command prompt", "registry editor", "task manager", "windows terminal", "git bash", "computer management", "user account control")


def is_shell_target(title: str | None, process: str | None = None) -> bool:
    """True when a window is a shell/console/admin tool that must not receive typed input."""
    if process and process.casefold() in _SHELL_PROCESSES:
        return True
    text = (title or "").casefold()
    if text.strip() == "run":
        return True
    return any(phrase in text for phrase in _SHELL_TITLE_PHRASES) or bool(
        _SHELL_TITLE_WORDS & set(re.split(r"[^a-z0-9]+", text))
    )


def _valid_key(key: str) -> bool:
    return key in _NAMED_KEYS or bool(re.fullmatch(r"[a-z0-9]", key))


def _is_benign_win32_error(exc: BaseException) -> bool:
    """pygetwindow raises even when GetLastError is 0 ('operation completed successfully')."""
    text = str(exc).casefold()
    return "error code from windows: 0" in text or (
        "error code from windows:" in text and "completed successfully" in text
    )


class DesktopStep(BaseModel):
    model_config = ConfigDict(extra="ignore")

    action: (
        Literal[
            "inspect", "close_window", "close_tab", "minimize_window", "maximize_window", "restore_window", "focus_window",
            "click", "type_text", "press_key", "hotkey", "scroll",
        ]
        | None
    ) = None
    type: (
        Literal[
            "inspect", "close_window", "close_tab", "minimize_window", "maximize_window", "restore_window", "focus_window",
            "click", "type_text", "press_key", "hotkey", "scroll", "key", "text",
        ]
        | None
    ) = None
    x: int | None = Field(default=None, ge=0, le=10000)
    y: int | None = Field(default=None, ge=0, le=10000)
    text: str | None = Field(default=None, max_length=1000)
    key: str | None = None
    keys: list[str] | str | None = None
    amount: int | None = Field(default=None, ge=-10, le=10)

    @model_validator(mode="before")
    @classmethod
    def normalize_model_action_shapes(cls, value):
        if not isinstance(value, dict):
            return value
        normalized = dict(value)
        action = normalized.get("action")
        legacy_type = normalized.get("type")
        keys = normalized.get("keys")

        if action is None:
            if legacy_type == "key":
                chord = keys if isinstance(keys, str) else ""
                if "+" in chord or (isinstance(keys, list) and len(keys) > 1):
                    normalized["action"] = "hotkey"
                    normalized["keys"] = chord.split("+") if isinstance(keys, str) else keys
                else:
                    normalized["action"] = "press_key"
                    normalized["key"] = keys[0] if isinstance(keys, list) and keys else keys
                    normalized.pop("keys", None)
            elif legacy_type == "text":
                normalized["action"] = "type_text"
            elif legacy_type is not None:
                normalized["action"] = legacy_type
        elif legacy_type is not None:
            raise ValueError("Use either action or type, not both")
        normalized.pop("type", None)

        if isinstance(normalized.get("keys"), str) and normalized.get("action") == "hotkey":
            normalized["keys"] = normalized["keys"].split("+")
        keys = normalized.get("keys")
        if normalized.get("action") == "hotkey" and isinstance(keys, list):
            lowered = [key.lower() for key in keys]
            if lowered == ["alt", "f4"]:
                normalized["action"] = "close_window"
                normalized.pop("keys")
            elif lowered == ["ctrl", "w"]:
                normalized["action"] = "close_tab"
                normalized.pop("keys")
        return normalized

    @model_validator(mode="after")
    def validate_action_fields(self):
        if self.action is None or self.type is not None:
            raise ValueError("Provide one supported action")
        required = {
            "inspect": set(),
            "close_window": set(),
            "close_tab": set(),
            "minimize_window": set(),
            "maximize_window": set(),
            "restore_window": set(),
            "focus_window": set(),
            "click": {"x", "y"},
            "type_text": {"text"},
            "press_key": {"key"},
            "hotkey": {"keys"},
            "scroll": {"amount"},
        }[self.action]
        values = {
            "x": self.x,
            "y": self.y,
            "text": self.text,
            "key": self.key,
            "keys": self.keys,
            "amount": self.amount,
        }
        provided = {name for name, value in values.items() if value is not None}
        if provided != required:
            fields = ", ".join(sorted(required)) or "none"
            raise ValueError(f"{self.action} requires exactly these fields: {fields}")
        if self.key is not None and not _valid_key(self.key.lower()):
            raise ValueError("key must be a single letter, digit, or supported key name")
        if isinstance(self.keys, list) and not 2 <= len(self.keys) <= 4:
            raise ValueError("hotkey must contain between two and four keys")
        if self.keys is not None and not all(_valid_key(key.lower()) for key in self.keys):
            raise ValueError("hotkey contains an unsupported key")
        return self


class DesktopControlArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")

    target_window: str | None = Field(default=None, max_length=160)
    target_window_id: int | None = Field(default=None, ge=1)
    target_process_id: int | None = Field(default=None, ge=1)
    steps: list[DesktopStep] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def require_target_for_input(self):
        needs_target = any(step.action != "inspect" for step in self.steps)
        if needs_target and not (self.target_window and self.target_window.strip()):
            raise ValueError("target_window is required for keyboard and mouse actions")
        if any(step.action in _WINDOW_STATE_ACTIONS | {"close_window", "close_tab"} for step in self.steps[:-1]):
            raise ValueError("close_window, close_tab, and window state actions must be the final desktop action")
        return self


class DesktopControlTool(BaseTool):
    name = "control_desktop"
    description = (
        "Inspect the active window and list open titles; close one uniquely identified tab "
        "(close_tab / Ctrl+W) or app window (close_window / Alt+F4); minimize (minimize_window); "
        "maximize (maximize_window); restore (restore_window); bring to front (focus_window); "
        "or perform a short bounded mouse/keyboard sequence. "
        "Inspect first and pass a listed title as target_window. Never substitute a different "
        "window when the requested app/site is not listed; Ctrl+W closes the active tab in the matched window."
    )
    risk_level = RiskLevel.HIGH
    args_schema = DesktopControlArgs

    def risk_for_args(self, args: BaseModel | None) -> RiskLevel:
        if args is None:
            return RiskLevel.HIGH
        parsed = DesktopControlArgs.model_validate(args.model_dump())
        if all(step.action in {"inspect"} | _WINDOW_STATE_ACTIONS for step in parsed.steps):
            return RiskLevel.LOW
        return RiskLevel.HIGH

    @staticmethod
    def risk_for_user_command(args: BaseModel, user_command: str) -> RiskLevel:
        """Auto-approve bounded input only when the user named its target app and action."""
        parsed = DesktopControlArgs.model_validate(args.model_dump())
        if parsed.target_window_id is not None and any(step.action == "close_window" for step in parsed.steps):
            return RiskLevel.HIGH  # batch/window-ID closes require explicit review
        if all(step.action in {"inspect"} | _WINDOW_STATE_ACTIONS for step in parsed.steps):
            return RiskLevel.LOW
        if not parsed.target_window:
            return RiskLevel.HIGH
        if is_shell_target(parsed.target_window) and any(step.action in _INPUT_ACTIONS for step in parsed.steps):
            return RiskLevel.HIGH  # never auto-approve input aimed at a shell

        normalized_command = user_command.casefold()
        for spoken_name in ("google charmin honor", "charmin honor"):
            normalized_command = normalized_command.replace(spoken_name, "chrome")
        command = re.sub(r"[^a-z0-9]+", " ", normalized_command).split()
        target = re.sub(r"[^a-z0-9]+", " ", parsed.target_window.casefold()).split()
        ignored = {
            "a", "an", "the", "app", "application", "program", "window", "desktop",
            "open", "please", "in", "on", "at", "to", "with", "and", "my", "this",
            "google", "microsoft", "cisco", "inc", "untitled", "new", "tab",
        }
        target_names = {word for word in target if len(word) > 2 and word not in ignored}
        command_names = {word for word in command if len(word) > 2 and word not in ignored}
        if not target_names.intersection(command_names):
            return RiskLevel.HIGH

        intents = {
            "search", "find", "play", "watch", "type", "click", "press", "enter",
            "scroll", "navigate", "visit", "browse", "close", "quit", "exit", "tab",
            "off", "shut", "kill", "stop",
            "minimize", "maximize", "restore", "chota", "bada", "kam",
            "khol", "kholo", "kholen", "chala", "chalao", "bajao", "dhundo",
            "dhoondo", "band", "karo", "bandh", "bandkaro",
        }
        if not intents.intersection(command_names):
            return RiskLevel.HIGH
        return RiskLevel.LOW

    @staticmethod
    def _type_text(pyautogui, text: str) -> None:
        if text.isascii():
            pyautogui.write(text, interval=0.01)
            return
        if sys.platform != "win32":
            raise ValueError("Non-ASCII desktop typing is supported on Windows only.")

        from ctypes import wintypes

        class KeyboardInput(ctypes.Structure):
            _fields_ = [
                ("virtual_key", wintypes.WORD),
                ("scan_code", wintypes.WORD),
                ("flags", wintypes.DWORD),
                ("time", wintypes.DWORD),
                ("extra_info", ctypes.c_size_t),
            ]

        class InputUnion(ctypes.Union):
            _fields_ = [("keyboard", KeyboardInput)]

        class Input(ctypes.Structure):
            _anonymous_ = ("data",)
            _fields_ = [("type", wintypes.DWORD), ("data", InputUnion)]

        key_up = 0x0002
        unicode_key = 0x0004
        events = []
        for character in text:
            codepoint = ord(character)
            units = (
                (codepoint,)
                if codepoint <= 0xFFFF
                else (
                    0xD800 + ((codepoint - 0x10000) >> 10),
                    0xDC00 + ((codepoint - 0x10000) & 0x3FF),
                )
            )
            for unit in units:
                events.append(Input(type=1, keyboard=KeyboardInput(0, unit, unicode_key, 0, 0)))
                events.append(Input(type=1, keyboard=KeyboardInput(0, unit, unicode_key | key_up, 0, 0)))
        buffer = (Input * len(events))(*events)
        sent = ctypes.windll.user32.SendInput(len(events), buffer, ctypes.sizeof(Input))
        if sent != len(events):
            raise ctypes.WinError()

    @staticmethod
    def _window_titles(windows: list[Any]) -> list[str]:
        return [window.title for window in windows if getattr(window, "title", None)]

    @classmethod
    def _resolve_window(cls, pyautogui, title: str):
        requested = title.strip()
        windows = [window for window in pyautogui.getAllWindows() if getattr(window, "title", None)]
        if not requested:
            raise ValueError("target_window is required")
        needle = requested.casefold()
        matches = [window for window in windows if needle in window.title.casefold()]
        if len(matches) == 1:
            return matches[0]
        active = pyautogui.getActiveWindow()
        if len(matches) > 1 and active in matches:
            return active
        if not matches:
            scored = sorted(
                (
                    (SequenceMatcher(None, needle, window.title.casefold()).ratio(), window)
                    for window in windows
                ),
                key=lambda item: item[0],
                reverse=True,
            )
            if scored and scored[0][0] >= 0.62 and (
                len(scored) == 1 or scored[0][0] - scored[1][0] >= 0.08
            ):
                return scored[0][1]
        listed = ", ".join(cls._window_titles(windows)[:12]) or "(none)"
        raise ValueError(
            f"Expected one window matching {requested!r}; found {len(matches)}. "
            f"Open windows: {listed}. Do not substitute another window; ask the user to open "
            "the target or identify the intended window."
        )

    @staticmethod
    def _window_hwnd(window: Any) -> int | None:
        hwnd = getattr(window, "_hWnd", None)
        if hwnd is None:
            return None
        try:
            return int(hwnd)
        except (TypeError, ValueError):
            return None

    @classmethod
    def _window_metadata(cls, window):
        from ctypes import wintypes
        hwnd = cls._window_hwnd(window)
        info = {"title": getattr(window, "title", ""), "id": hwnd, "pid": None, "process": None}
        if sys.platform != "win32" or not hwnd:
            return info
        pid = wintypes.DWORD()
        ctypes.windll.user32.GetWindowThreadProcessId(wintypes.HWND(hwnd), ctypes.byref(pid))
        info["pid"] = pid.value
        kernel = ctypes.windll.kernel32
        opener = kernel.OpenProcess
        opener.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        opener.restype = wintypes.HANDLE
        handle = opener(0x1000, False, pid.value)
        if not handle:
            return info
        try:
            query = kernel.QueryFullProcessImageNameW
            query.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
            size = wintypes.DWORD(32768)
            path = ctypes.create_unicode_buffer(size.value)
            if query(handle, 0, path, ctypes.byref(size)):
                info["process"] = path.value.replace("\\", "/").rsplit("/", 1)[-1].casefold()
        finally:
            kernel.CloseHandle.argtypes = [wintypes.HANDLE]
            kernel.CloseHandle(handle)
        return info

    @classmethod
    def _win32_force_foreground(cls, hwnd: int) -> None:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        from ctypes import wintypes

        user32.ShowWindow(hwnd, _SW_RESTORE)
        user32.BringWindowToTop(hwnd)
        foreground = user32.GetForegroundWindow()
        if foreground and foreground != hwnd:
            current = kernel32.GetCurrentThreadId()
            other_pid = wintypes.DWORD()
            other = user32.GetWindowThreadProcessId(foreground, ctypes.byref(other_pid))
            attached = False
            if other and other != current:
                attached = bool(user32.AttachThreadInput(current, other, True))
            user32.SetForegroundWindow(hwnd)
            if attached:
                user32.AttachThreadInput(current, other, False)
        else:
            user32.SetForegroundWindow(hwnd)

    @classmethod
    def _activate_window(cls, window: Any, pyautogui) -> None:
        hwnd = cls._window_hwnd(window)
        if sys.platform == "win32" and hwnd:
            try:
                cls._win32_force_foreground(hwnd)
                return
            except Exception:
                pass
        try:
            window.activate()
        except Exception as exc:
            if not _is_benign_win32_error(exc):
                raise

    @classmethod
    def _foreground_matches(cls, window: Any, pyautogui) -> bool:
        hwnd = cls._window_hwnd(window)
        if sys.platform == "win32" and hwnd:
            try:
                return int(ctypes.windll.user32.GetForegroundWindow()) == hwnd
            except Exception:
                pass
        active = pyautogui.getActiveWindow()
        if not active:
            return False
        active_hwnd = cls._window_hwnd(active)
        target_hwnd = cls._window_hwnd(window)
        if active_hwnd is not None and target_hwnd is not None:
            return active_hwnd == target_hwnd
        return getattr(active, "title", None) == getattr(window, "title", None)

    @classmethod
    def _hotkey_on_target(cls, window: Any, pyautogui, *keys: str) -> bool:
        """Send a hotkey only if the target window is actually in the foreground."""
        cls._activate_window(window, pyautogui)
        time.sleep(0.2)
        if not cls._foreground_matches(window, pyautogui):
            return False
        pyautogui.hotkey(*keys)
        return True

    @classmethod
    def _request_window_close(cls, window: Any) -> bool:
        hwnd = cls._window_hwnd(window)
        if sys.platform == "win32" and hwnd:
            user32 = ctypes.windll.user32
            posted = user32.PostMessageW(hwnd, _WM_CLOSE, 0, 0) != 0
            posted = user32.PostMessageW(hwnd, _WM_SYSCOMMAND, _SC_CLOSE, 0) != 0 or posted
            if posted:
                return True
            last_error = ctypes.windll.kernel32.GetLastError()
            if last_error == 0:
                return True
            raise OSError(f"Could not send close to window (Win32 error {last_error})")
        closer = getattr(window, "close", None)
        if closer is None:
            return False
        try:
            closer()
            return True
        except Exception as exc:
            if _is_benign_win32_error(exc):
                return True
            raise

    @classmethod
    def _window_is_open(cls, window: Any, title: str, pyautogui) -> bool:
        hwnd = cls._window_hwnd(window)
        if sys.platform == "win32" and hwnd:
            try:
                if ctypes.windll.user32.IsWindow(hwnd) == 0:
                    return False
                if ctypes.windll.user32.IsWindowVisible(hwnd) == 0:
                    return False
            except Exception:
                pass
        needle = title.casefold()
        return any(
            getattr(item, "title", None) and item.title.casefold() == needle
            for item in pyautogui.getAllWindows()
        )

    @staticmethod
    def _save_prompt(pid: int | None) -> str | None:
        """Text of an unsaved-changes dialog owned by the app, read with UI Automation."""
        if not pid:
            return None
        try:
            texts = current().dialog_texts(pid)
        except (ProbeUnavailable, Exception):  # noqa: BLE001 - no dialog evidence
            return None
        hits = [t for t in texts if any(w in t.casefold() for w in _SAVE_PROMPT_WORDS)]
        return hits[0][:160] if hits else None

    def verify(self, args: BaseModel, result: ToolResult) -> Verification:
        """Re-read each touched window's real state (exists, minimized, maximized, foreground)."""
        if not result.success:
            return failed_result(result)
        probe = current()
        steps = result.output.get("completed_steps", [])
        checks: list[tuple[str, bool]] = []
        evidence: dict[str, Any] = {"steps": []}
        try:
            for step in steps:
                action, hwnd = step.get("action"), step.get("hwnd") or step.get("foreground_hwnd")
                if hwnd:
                    seen = probe.window(hwnd)
                else:  # no handle (non-Win32 backend): fall back to the exact title
                    title = step.get("window")
                    seen = next((w for w in probe.windows() if title and w.title == title), None)
                record = {"action": action, "hwnd": hwnd, "now": seen.as_evidence() if seen else None}
                if action == "inspect":
                    windows = probe.windows()
                    record["windows_now"] = len(windows)
                    checks.append(("desktop windows re-read", bool(windows)))
                elif action == "close_window":
                    checks.append((f"window {hwnd or step.get('window')!r} is gone", seen is None))
                elif action == "close_tab":
                    checks.append(("tab closed (window gone or title changed)",
                                   seen is None or seen.title != step.get("title_before")))
                elif action == "minimize_window":
                    checks.append(("window is minimized", bool(seen and seen.minimized)))
                elif action == "maximize_window":
                    checks.append(("window is maximized", bool(seen and seen.maximized)))
                elif action == "restore_window":
                    checks.append(("window is restored", bool(seen and not seen.minimized and not seen.maximized)))
                elif action == "focus_window":
                    checks.append(("window is in the foreground", bool(seen and seen.foreground)))
                elif action in _INPUT_ACTIONS:
                    # The effect of free input cannot be read back generally; the evidence is
                    # that the target window existed and had focus when the input was sent.
                    checks.append(("input went to the target window", seen is not None))
                evidence["steps"].append(record)
        except ProbeUnavailable as exc:
            return Verification(passed=False, checks=["window state could not be re-read"], details=str(exc))
        return verdict(checks, evidence)

    def execute(self, args: BaseModel) -> ToolResult:
        try:
            parsed = DesktopControlArgs.model_validate(args.model_dump())
        except Exception as exc:
            return ToolResult(success=False, error=f"Invalid desktop actions: {exc}")

        try:
            import pyautogui
        except ImportError as exc:
            return ToolResult(
                success=False,
                error="Desktop control dependency is missing. Install backend requirements and restart.",
            )

        pyautogui.FAILSAFE = True
        completed = []
        input_hwnd = None
        try:
            for step in parsed.steps:
                if step.action != "inspect":
                    title = parsed.target_window.strip()
                    if parsed.target_window_id is not None:
                        identified = [window for window in pyautogui.getAllWindows() if self._window_hwnd(window) == parsed.target_window_id and getattr(window, "title", "") == title]
                        if len(identified) != 1:
                            raise ValueError("Selected window changed or closed; inspect again.")
                        target = identified[0]
                        if parsed.target_process_id is not None and self._window_metadata(target)["pid"] != parsed.target_process_id:
                            raise ValueError("Selected window process changed; inspect again.")
                    else:
                        target = self._resolve_window(pyautogui, title)
                    if step.action in {"close_window", "close_tab"}:
                        # Closing must use the exact, still-unique inspected title.
                        # Never fall through to a fuzzy/active-window substitute.
                        exact = [window for window in pyautogui.getAllWindows() if getattr(window, "title", "").casefold() == title.casefold() and (parsed.target_window_id is None or self._window_hwnd(window) == parsed.target_window_id)]
                        if len(exact) != 1:
                            raise ValueError("Close target changed or is ambiguous. Select the current exact window title again.")
                        target = exact[0]
                        if step.action == "close_tab":
                            if not self._hotkey_on_target(target, pyautogui, "ctrl", "w"):
                                active = pyautogui.getActiveWindow()
                                raise ValueError(
                                    f"Refused Ctrl+W; foreground is "
                                    f"{active.title if active else None!r}, not {target.title!r}."
                                )
                            time.sleep(0.4)
                            completed.append(
                                {
                                    "action": "close_tab",
                                    "window": target.title,
                                    "title_before": title,
                                    "hwnd": self._window_hwnd(target),
                                    "closed_tab": True,
                                }
                            )
                            continue
                        closed_title = target.title
                        posted = self._request_window_close(target)
                        time.sleep(0.6)
                        still_open = self._window_is_open(target, closed_title, pyautogui)
                        used_hotkey = False
                        if still_open:
                            used_hotkey = self._hotkey_on_target(target, pyautogui, "alt", "f4")
                            if used_hotkey:
                                time.sleep(0.75)
                                still_open = self._window_is_open(target, closed_title, pyautogui)
                        meta = self._window_metadata(target)
                        completed.append(
                            {
                                "action": "close_window",
                                "window": closed_title,
                                "hwnd": self._window_hwnd(target),
                                "pid": meta.get("pid"),
                                "closed": not still_open,
                                "posted_close": posted,
                            }
                        )
                        if still_open:
                            prompt = self._save_prompt(meta.get("pid"))
                            if prompt:
                                return ToolResult(
                                    success=False,
                                    output={"completed_steps": completed, "needs_confirmation": True, "save_prompt": prompt},
                                    error=(f"{closed_title!r} is asking whether to save changes ({prompt!r}). "
                                           "Choose Save or Don't Save yourself; AgentDesk will not pick for you."),
                                )
                            if not used_hotkey:
                                active = pyautogui.getActiveWindow()
                                raise ValueError(
                                    f"Window {closed_title!r} is still open, and Alt+F4 was not sent "
                                    f"because the foreground window is "
                                    f"{active.title if active else None!r}. "
                                    "Ask the user to click that app, then try close again."
                                )
                            raise ValueError(
                                f"Window {closed_title!r} is still open. It may have an unsaved-changes prompt."
                            )
                        continue
                    if step.action in _WINDOW_STATE_ACTIONS:
                        self._activate_window(target, pyautogui)
                        time.sleep(0.25)
                        if step.action == "minimize_window":
                            try:
                                target.minimize()
                            except Exception:
                                if self._foreground_matches(target, pyautogui):
                                    pyautogui.hotkey("win", "down")
                        elif step.action == "maximize_window":
                            try:
                                target.maximize()
                            except Exception:
                                if self._foreground_matches(target, pyautogui):
                                    pyautogui.hotkey("win", "up")
                        elif step.action == "restore_window":
                            try:
                                target.restore()
                            except Exception:
                                pass
                        elif step.action == "focus_window" and not self._foreground_matches(target, pyautogui):
                            raise ValueError(f"Windows did not bring {target.title!r} to the front.")
                        time.sleep(0.2)
                        completed.append({"action": step.action, "window": target.title, "hwnd": self._window_hwnd(target)})
                        continue
                    active = pyautogui.getActiveWindow()
                    if not active or active.title != target.title:
                        raise ValueError(
                            f"Foreground window {active.title if active else None!r} does not match "
                            f"target {target.title!r}; no input was sent."
                        )
                    input_hwnd = self._window_hwnd(target)
                    if step.action in _INPUT_ACTIONS and is_shell_target(
                        target.title, self._window_metadata(target).get("process")
                    ):
                        raise ValueError(
                            f"Refused: typed input into the shell/system window {target.title!r} is not "
                            "allowed. Open the app yourself or use a dedicated tool."
                        )
                if step.action == "inspect":
                    window = pyautogui.getActiveWindow()
                    observed = [item for item in pyautogui.getAllWindows() if getattr(item, "title", "")]
                    completed.append(
                        {
                            "action": "inspect",
                            "active_window": window.title if window else None,
                            "open_windows": self._window_titles(list(pyautogui.getAllWindows()))[:30],
                            "windows": [self._window_metadata(item) for item in observed[:100]],
                            "windows_truncated": len(observed) > 100,
                            "screen_size": list(pyautogui.size()),
                        }
                    )
                elif step.action == "click":
                    width, height = pyautogui.size()
                    if step.x >= width or step.y >= height:
                        raise ValueError(f"Click coordinates must be within the {width}x{height} screen.")
                    pyautogui.click(step.x, step.y)
                    completed.append({"action": "click", "x": step.x, "y": step.y, "foreground_hwnd": input_hwnd})
                elif step.action == "type_text":
                    self._type_text(pyautogui, step.text)
                    completed.append({"action": "type_text", "characters": len(step.text), "foreground_hwnd": input_hwnd})
                elif step.action == "press_key":
                    pyautogui.press(step.key.lower())
                    completed.append({"action": "press_key", "key": step.key.lower(), "foreground_hwnd": input_hwnd})
                elif step.action == "hotkey":
                    keys = [key.lower() for key in step.keys]
                    pyautogui.hotkey(*keys)
                    completed.append({"action": "hotkey", "keys": keys, "foreground_hwnd": input_hwnd})
                elif step.action == "scroll":
                    pyautogui.scroll(step.amount)
                    completed.append({"action": "scroll", "amount": step.amount, "foreground_hwnd": input_hwnd})
        except Exception as exc:
            return ToolResult(
                success=False,
                output={"completed_steps": completed},
                error=f"Desktop control stopped after {len(completed)} step(s): {exc}",
            )
        return ToolResult(success=True, output={"completed_steps": completed})

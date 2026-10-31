"""Probes for tests: verifiers run without Windows.

`AgreeableProbe` is the session default: it reports that a requested window
exists and re-reads settings in-process (where tests patch the tool's
internals), so tests about other behaviour are not blocked by the platform.
`ScriptedProbe` is strict: it returns exactly the desktop state a test sets,
and is what the verification tests use.
"""
from __future__ import annotations

from app.verification import SystemProbe, WindowInfo


class AgreeableProbe(SystemProbe):
    poll_timeout = 0.01

    def __init__(self):
        self.window_states: dict[int, WindowInfo | None] = {}
        self.extra_windows: list[WindowInfo] = []

    def windows(self):
        return list(self.extra_windows) or [WindowInfo(4242, "Test Window", 1, "test.exe", False, False, True)]

    def window(self, hwnd):
        if hwnd in self.window_states:
            return self.window_states[hwnd]
        return WindowInfo(hwnd, "Test Window", 1, "test.exe", False, False, True)

    def find_windows(self, **criteria):
        hint = (criteria.get("title_contains") or ["window"])[0]
        return [WindowInfo(4242, f"{hint} (test)", 1, "test.exe", False, False, True)]

    def process_alive(self, pid):
        return True

    def dialog_texts(self, pid):
        return []

    def media_session(self):
        return {"app": "test", "title": "YouTube (test)", "artist": "", "status": "playing"}

    def read_setting(self, setting):
        from app.tools.base import ToolContext
        from app.tools.system import ManageSystemSettingArgs, ManageSystemSettingTool

        result = ManageSystemSettingTool(ToolContext())._execute(ManageSystemSettingArgs(setting=setting, action="get"))
        if not result.success:
            raise RuntimeError(result.error)
        return dict(result.output)


class ScriptedProbe(SystemProbe):
    poll_timeout = 0.01

    def __init__(self, windows=None, settings=None, alive=(), dialogs=None, media=None):
        self._windows = list(windows or [])
        self.media = list(media or [])  # successive media_session() readings; the last one repeats
        self.settings = dict(settings or {})
        self.alive = set(alive)
        self.dialogs = dict(dialogs or {})

    def windows(self):
        return list(self._windows)

    def process_alive(self, pid):
        return pid in self.alive

    def dialog_texts(self, pid):
        return list(self.dialogs.get(pid, []))

    def read_setting(self, setting):
        if setting not in self.settings:
            raise RuntimeError(f"no {setting} reading")
        return dict(self.settings[setting])

    def media_session(self):
        if not self.media:
            return None
        return self.media.pop(0) if len(self.media) > 1 else self.media[0]

"""Start AgentDesk at Windows sign-in through the per-user Run key (no admin rights needed).

HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run\\AgentDesk = "<python or exe>" "<shell.py>" --minimized
Only this one value is ever written or deleted. `registry` is injectable for tests.
"""
from __future__ import annotations

import sys
from pathlib import Path

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "AgentDesk"


def _winreg(registry=None):
    if registry is not None:
        return registry
    if sys.platform != "win32":
        raise OSError("Autostart is only available on Windows.")
    import winreg

    return winreg


def command_line() -> str:
    """The exact command Windows runs at sign-in (packaged exe, or pythonw + this shell)."""
    if getattr(sys, "frozen", False):
        # The packaged exe does not bundle the desktop shell yet; do not register a command that cannot run.
        raise OSError("Autostart needs the source install with the desktop shell (START_AGENT_X_DESKTOP.cmd).")
    python = Path(sys.executable)
    windowless = python.with_name("pythonw.exe")
    runner = windowless if windowless.is_file() else python
    shell = Path(__file__).resolve().with_name("shell.py")
    return f'"{runner}" "{shell}" --minimized'


def is_enabled(registry=None) -> bool:
    reg = _winreg(registry)
    try:
        with reg.OpenKey(reg.HKEY_CURRENT_USER, RUN_KEY, 0, reg.KEY_READ) as key:
            value, _ = reg.QueryValueEx(key, VALUE_NAME)
            return bool(value)
    except FileNotFoundError:
        return False


def set_enabled(enabled: bool, registry=None) -> bool:
    reg = _winreg(registry)
    with reg.CreateKeyEx(reg.HKEY_CURRENT_USER, RUN_KEY, 0, reg.KEY_SET_VALUE) as key:
        if enabled:
            reg.SetValueEx(key, VALUE_NAME, 0, reg.REG_SZ, command_line())
        else:
            try:
                reg.DeleteValue(key, VALUE_NAME)
            except FileNotFoundError:
                pass
    return is_enabled(registry)

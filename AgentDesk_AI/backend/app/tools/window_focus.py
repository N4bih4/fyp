"""Put a window in FRONT of everything, where the user can see it.

Windows refuses `SetForegroundWindow` from a background process and then only flashes the window's taskbar button (the orange blinking the user saw
instead of the app). The ways around it, in order: restore a minimised window, tap the Alt key (it lifts the foreground lock for this process), attach
to the foreground window's input thread, call SetForegroundWindow, and, if it still is not in front, make it topmost for an instant. Returns True only
when the window really is the foreground window afterwards.
"""
from __future__ import annotations

import ctypes
import platform
import time

_SW_RESTORE, _SW_SHOW = 9, 5
_VK_MENU, _KEYEVENTF_KEYUP = 0x12, 0x0002
_HWND_TOPMOST, _HWND_NOTOPMOST, _FLAGS = -1, -2, 0x0001 | 0x0002 | 0x0040      # NOSIZE | NOMOVE | SHOWWINDOW


def is_front(hwnd: int) -> bool:
    try:
        return int(ctypes.windll.user32.GetForegroundWindow()) == int(hwnd)
    except Exception:  # noqa: BLE001
        return False


def bring_to_front(hwnd: int | None) -> bool:
    if not hwnd or platform.system() != "Windows":
        return False
    hwnd = int(hwnd)
    user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
    try:
        if not user32.IsWindow(hwnd):
            return False
        user32.ShowWindow(hwnd, _SW_RESTORE if user32.IsIconic(hwnd) else _SW_SHOW)
        if is_front(hwnd):
            return True
        user32.keybd_event(_VK_MENU, 0, 0, 0)                      # an Alt tap: the foreground lock does not apply to a process that just had input
        user32.keybd_event(_VK_MENU, 0, _KEYEVENTF_KEYUP, 0)
        from ctypes import wintypes
        current = kernel32.GetCurrentThreadId()
        front = user32.GetForegroundWindow()
        other = user32.GetWindowThreadProcessId(front, ctypes.byref(wintypes.DWORD())) if front else 0
        attached = bool(other and other != current and user32.AttachThreadInput(current, other, True))
        try:
            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)
        finally:
            if attached:
                user32.AttachThreadInput(current, other, False)
        if not is_front(hwnd):                                    # last resort: topmost for a moment, then back to normal
            user32.SetWindowPos(hwnd, _HWND_TOPMOST, 0, 0, 0, 0, _FLAGS)
            user32.SetWindowPos(hwnd, _HWND_NOTOPMOST, 0, 0, 0, 0, _FLAGS)
            user32.SetForegroundWindow(hwnd)
        time.sleep(0.05)
        return is_front(hwnd)
    except Exception:  # noqa: BLE001 - showing a window is a courtesy; the command itself already succeeded
        return False

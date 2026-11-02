"""Show where the assistant is about to click: a coloured outline around the target for a third of a second, then the click.

Drawn straight onto the screen with GDI (no window of its own, nothing to close) and erased by asking Windows to repaint that rectangle. It is a visual
courtesy only: any failure is swallowed and never blocks or changes the action. Off under pytest, off elsewhere than Windows, and
`AGENTDESK_HIGHLIGHT=0` turns it off. Tests install a recorder with `set_highlighter`.
"""
from __future__ import annotations

import os
import time
from typing import Callable

SECONDS = 0.3
_override: Callable[[tuple[int, int, int, int], str], None] | None = None


def set_highlighter(fn: Callable[[tuple[int, int, int, int], str], None] | None) -> None:
    global _override
    _override = fn


def enabled() -> bool:
    return os.name == "nt" and os.environ.get("AGENTDESK_HIGHLIGHT", "1") != "0" and "PYTEST_CURRENT_TEST" not in os.environ


def flash(rect: tuple[int, int, int, int], label: str = "", seconds: float = SECONDS) -> None:
    """Outline `rect` (screen pixels left, top, right, bottom) for `seconds`. Never raises."""
    try:
        if _override is not None:
            _override(rect, label)
            return
        if not enabled():
            return
        l, t, r, b = (int(v) for v in rect)
        if r - l < 4 or b - t < 4:
            return
        _draw(l, t, r, b, seconds)
    except Exception:  # noqa: BLE001 - decoration only
        pass


def _draw(l: int, t: int, r: int, b: int, seconds: float) -> None:
    import ctypes
    from ctypes import wintypes

    user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
    NULL_BRUSH, PS_SOLID = 5, 0
    colour = 0x00D7FF     # amber (BGR): visible on dark and light windows
    end = time.monotonic() + seconds
    pad = 3
    while True:
        dc = user32.GetDC(0)
        pen = gdi32.CreatePen(PS_SOLID, 4, colour)
        old_pen, old_brush = gdi32.SelectObject(dc, pen), gdi32.SelectObject(dc, gdi32.GetStockObject(NULL_BRUSH))
        gdi32.Rectangle(dc, l - pad, t - pad, r + pad, b + pad)
        gdi32.SelectObject(dc, old_pen)
        gdi32.SelectObject(dc, old_brush)
        gdi32.DeleteObject(pen)
        user32.ReleaseDC(0, dc)
        if time.monotonic() >= end:
            break
        time.sleep(0.05)        # drawn again every 50 ms: a window repainting underneath does not wipe it for the whole third of a second
    area = wintypes.RECT(l - 12, t - 12, r + 12, b + 12)
    RDW_INVALIDATE, RDW_UPDATENOW, RDW_ALLCHILDREN = 0x1, 0x100, 0x80
    user32.RedrawWindow(None, ctypes.byref(area), None, RDW_INVALIDATE | RDW_UPDATENOW | RDW_ALLCHILDREN)

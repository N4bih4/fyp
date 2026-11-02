"""YouTube without the browser extension: the player's own keyboard shortcuts, sent to the browser window that shows YouTube.

This is the slower fallback (the extension reads the page; this only presses keys). What it can and cannot promise:
 - pause / resume: it reads Windows' media session first (is it playing?), presses K only if the state must change, and reads the session again.
 - seek, next, previous, full screen, theatre, captions, mute: it presses the key once and says so; it CANNOT confirm the result, so a task using it is
   reported as "done, not confirmed", never as verified.
 - exact speed, exact volume, quality, loop, like, subscribe, skip ad: need the page; the answer says to connect the browser helper.
The window must have the page focused (not the address bar); the keys go to the front YouTube browser window, nothing else.
"""
from __future__ import annotations

import time
from typing import Any

from ..verification import BROWSER_PROCESSES, ProbeUnavailable, current

# action -> keys (the notation of tools/uia_backend.to_send_keys); the number is how many times
KEY_ACTIONS = {"pause", "resume", "seek", "mute", "unmute", "fullscreen", "theatre", "captions", "next", "previous"}
NEEDS_PAGE = {"speed", "volume", "quality", "loop", "like", "subscribe", "skip_ad", "results", "click_result", "now_playing", "read_page"}


def youtube_window():
    """The browser window showing YouTube (the front one if several), or None."""
    from .uia import get_service
    service = get_service()
    windows = [w for w in service.backend.windows() if "youtube" in (w.title or "").casefold() and (w.process or "").casefold() in BROWSER_PROCESSES]
    if not windows:
        return None
    front = service.backend.foreground()
    return next((w for w in windows if front is not None and w.handle == front.handle), windows[0])


def _status() -> str | None:
    """'playing' / 'paused' from Windows' media session, or None when it cannot be read."""
    try:
        state = current().media_session()
    except ProbeUnavailable:
        return None
    except Exception:  # noqa: BLE001
        return None
    return str(state.get("status", "")).casefold() if state else None


def _press(window, combo: str, times: int = 1) -> None:
    from .uia import get_service
    backend = get_service().backend
    for _ in range(times):
        backend.press_keys(window, combo)
        time.sleep(0.12)


def plan_keys(action: str, seconds: int | None = None) -> list[tuple[str, int]]:
    """The key presses for an action: [(combo, times), ...]. Seeking uses J / L (10 s) and the arrow keys (5 s)."""
    if action in ("pause", "resume"):
        return [("k", 1)]
    if action == "seek":
        s = int(seconds or 0)
        back = s < 0
        s = min(abs(s), 120)
        tens, fives = s // 10, (s % 10) // 5
        out = []
        if tens:
            out.append(("j" if back else "l", tens))
        if fives:
            out.append(("left" if back else "right", fives))
        return out
    return [{"mute": ("m", 1), "unmute": ("m", 1), "fullscreen": ("f", 1), "theatre": ("t", 1), "captions": ("c", 1), "next": ("shift+n", 1), "previous": ("shift+p", 1)}[action]]


def act(action: str, seconds: int | None = None) -> dict[str, Any]:
    """Do one control by keyboard. {'success', 'confirmed', 'error'?, 'status_before', 'status_after', 'sent'}."""
    if action in NEEDS_PAGE or action not in KEY_ACTIONS:
        return {"success": False, "confirmed": False, "error": "That control needs the browser helper (the Agent X extension): it is not connected. Connect it, or press the control yourself."}
    window = youtube_window()
    if window is None:
        return {"success": False, "confirmed": False, "error": "I cannot see a browser window showing YouTube."}
    if action == "seek" and not seconds:
        return {"success": False, "confirmed": False, "error": "How many seconds?"}
    before = _status() if action in ("pause", "resume") else None
    if action == "pause" and before == "paused" or action == "resume" and before == "playing":
        return {"success": True, "confirmed": True, "already": True, "status_before": before, "status_after": before, "sent": [], "window": window.title}
    sent = plan_keys(action, seconds)
    try:
        for combo, times in sent:
            _press(window, combo, times)
    except Exception as exc:  # noqa: BLE001 - UIA / focus errors are many; the message stays short
        return {"success": False, "confirmed": False, "error": f"I could not send the key to '{window.title[:50]}': {type(exc).__name__}"}
    after = None
    if action in ("pause", "resume"):
        want = "paused" if action == "pause" else "playing"
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            after = _status()
            if after == want or after is None:
                break
            time.sleep(0.3)
        confirmed = after == want
        return {"success": confirmed or after is None, "confirmed": confirmed, "status_before": before, "status_after": after,
                "sent": sent, "window": window.title,
                **({} if confirmed else {"error": "I pressed K but Windows still shows the video as " + str(after or "unknown") + "."} if after else {})}
    return {"success": True, "confirmed": False, "status_before": None, "status_after": None, "sent": sent, "window": window.title}


def ensure_playing(wait_seconds: float = 8.0) -> dict[str, Any]:
    """After a YouTube video was opened: if Windows does not report it playing within a few seconds, press K once. Returns what happened."""
    deadline = time.monotonic() + wait_seconds
    status = None
    while time.monotonic() < deadline:
        status = _status()
        if status == "playing":
            return {"playing": True, "pressed": False}
        time.sleep(0.5)
    window = youtube_window()
    if window is None or status is None and not wait_seconds:
        return {"playing": False, "pressed": False, "why": "no YouTube window to press play in"}
    try:
        _press(window, "k")
    except Exception as exc:  # noqa: BLE001
        return {"playing": False, "pressed": False, "why": f"could not press play: {type(exc).__name__}"}
    time.sleep(1.5)
    return {"playing": _status() == "playing", "pressed": True, "status": _status()}

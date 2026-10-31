"""Music/media control with the keyboard media keys, verified through Windows media sessions.

The keys work for any player (Spotify, YouTube in a browser, Groove, VLC...). The real outcome is read
from the System Media Transport Controls (the same source as the Windows volume flyout): status for
play/pause/stop, track title for next/previous. A player that reports no session cannot be verified,
and the task says so instead of claiming success.
"""
from __future__ import annotations

import sys
import time
from typing import Literal

from pydantic import BaseModel

from ..verification import ProbeUnavailable, current, failed_result, verdict, wait_until
from .base import BaseTool, RiskLevel, ToolResult, Verification

VK = {"play_pause": 0xB3, "play": 0xB3, "pause": 0xB3, "next": 0xB0, "previous": 0xB1, "stop": 0xB2}
KEYEVENTF_EXTENDEDKEY, KEYEVENTF_KEYUP = 0x0001, 0x0002


class MediaControlArgs(BaseModel):
    action: Literal["play_pause", "play", "pause", "next", "previous", "stop"]


def press_media_key(vk: int) -> None:
    """Send one media key press (down + up). Tests replace this function."""
    if sys.platform != "win32":
        raise OSError("Media keys need Windows.")
    import ctypes

    user32 = ctypes.windll.user32
    user32.keybd_event(vk, 0, KEYEVENTF_EXTENDEDKEY, 0)
    user32.keybd_event(vk, 0, KEYEVENTF_EXTENDEDKEY | KEYEVENTF_KEYUP, 0)


class MediaControlTool(BaseTool):
    name = "media_control"
    description = ("Control the music/video that is playing on the PC with media keys: play, pause, "
                   "play_pause, next, previous, stop. Works with Spotify, YouTube in a browser and other players.")
    risk_level = RiskLevel.LOW
    args_schema = MediaControlArgs
    interruptible = True

    def execute(self, args: BaseModel) -> ToolResult:
        a = MediaControlArgs.model_validate(args.model_dump())
        try:
            before = current().media_session()
        except ProbeUnavailable:
            before = None
        except Exception:  # noqa: BLE001 - state is optional before the key press
            before = None
        # play/pause are idempotent: do not toggle a player that is already in the requested state.
        if before and a.action in {"play", "pause"} and before.get("status") == ("playing" if a.action == "play" else "paused"):
            return ToolResult(success=True, output={"action": a.action, "before": before, "key_sent": False,
                                                    "note": f"Already {before['status']}."})
        try:
            press_media_key(VK[a.action])
        except OSError as exc:
            return ToolResult(success=False, error=f"Could not send the media key: {exc}")
        return ToolResult(success=True, output={"action": a.action, "before": before, "key_sent": True})

    def verify(self, args: BaseModel, result: ToolResult) -> Verification:
        if not result.success:
            return failed_result(result)
        a = MediaControlArgs.model_validate(args.model_dump())
        before = result.output.get("before") or {}
        expected_status = {"play": "playing", "pause": "paused", "stop": {"stopped", "closed", "paused"}}.get(a.action)

        def observed():
            state = current().media_session()
            if not state:
                return None
            if a.action == "play_pause":
                return state if before and state["status"] != before.get("status") else None
            if a.action in {"next", "previous"}:
                return state if before and state["title"] != before.get("title") else None
            want = expected_status if isinstance(expected_status, set) else {expected_status}
            return state if state["status"] in want else None

        try:
            ok, state = wait_until(observed, timeout=current().poll_timeout, interval=0.3)
            last = current().media_session() if not ok else state
        except ProbeUnavailable as exc:
            return Verification(passed=False, checks=["media session unavailable"], details=str(exc))
        evidence = {"before": before or None, "after": last}
        if not before and a.action in {"play_pause", "next", "previous"}:
            return Verification(passed=False, checks=["no media session before the key"], evidence=evidence,
                                details="No player reported its state to Windows, so the change cannot be confirmed.")
        check = {"next": "track changed", "previous": "track changed", "play_pause": "playback state changed"}.get(
            a.action, f"player is {a.action}d" if a.action != "stop" else "player stopped")
        return verdict([(check, bool(ok))], evidence)


def media_tools(ctx=None) -> list[BaseTool]:
    return [MediaControlTool(ctx)]

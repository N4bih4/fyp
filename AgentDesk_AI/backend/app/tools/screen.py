"""`screen_act`: layer 3, for an app that gives no accessibility information (a game, a canvas, some custom-drawn windows).

One step: take a picture of THAT window, find what can be pointed at (UI Automation controls and Windows OCR text), draw numbered boxes on it, and let a
vision model choose a box number and an action. The program then acts on the centre of the box it detected and looks again. Order of the stack:
native tools first, then `ui_act` (layer 2), only then this (layer 3); every answer says which layer was used.

  * the model only ever names a box NUMBER; a missing number, an invented one or any coordinate is refused (vision/boxes.py);
  * the picture goes to the cloud vision model, so it needs the same permission as cloud answers; only the chosen window is captured, nothing is saved;
  * text in the picture is data: the model is told so, and a box that looks like a password, a payment, a delete or a send control is refused
    unless the user's goal names it (then the risk is high and a click is needed), exactly as for `ui_act`;
  * shell windows and password managers are never looked at or typed into;
  * "done" needs evidence: the window is photographed again and must have changed (a click), shown the typed text (typing) or moved (scroll).
"""
from __future__ import annotations

import re
import time
from collections import OrderedDict
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from ..ai.base import AIRateLimitError
from ..vision import overlay
from ..vision.boxes import Box, build_boxes
from ..vision.model import get_vision
from ..vision.ocr import OcrUnavailable, get_ocr
from .base import BaseTool, RiskLevel, ToolResult, Verification
from .desktop import is_shell_target
from .uia import _SECRET, get_service, is_dangerous
from .uia_backend import UiaError, WindowRef

NOTICE = "This app needs me to look at the screen, a few seconds."
_PRIVATE_APPS = ("keepass", "bitwarden", "1password", "lastpass", "dashlane", "keeper", "enpass", "credential manager", "windows security")
_REMEMBERED = 5
# Console and admin windows. A Python program with a window of its own (Tk, Qt, pygame) is an ordinary app here: only its console would be a shell.
_SHELL_PROCESSES = {"cmd.exe", "powershell.exe", "pwsh.exe", "windowsterminal.exe", "wt.exe", "conhost.exe", "openconsole.exe", "wsl.exe", "wslhost.exe",
                    "bash.exe", "mintty.exe", "regedit.exe", "mmc.exe", "taskmgr.exe"}


def is_shell_window(title: str, process: str = "") -> bool:
    return process.casefold() in _SHELL_PROCESSES or is_shell_target(title, None)
_CHANGED_PIXELS = 0.004          # share of the window's pixels that must differ for "the screen reacted"


class ScreenBackend(Protocol):
    def window_rect(self, window: WindowRef) -> tuple[int, int, int, int]: ...
    def focus(self, window: WindowRef) -> None: ...
    def grab(self, rect: tuple[int, int, int, int]): ...
    def click(self, x: int, y: int, double: bool = False) -> None: ...
    def type_text(self, text: str) -> None: ...
    def scroll(self, x: int, y: int, amount: int) -> None: ...


class RealScreen:
    """Screen, mouse and keyboard on Windows. Coordinates are physical pixels (the process is DPI aware through pyautogui / pywinauto)."""

    def window_rect(self, window: WindowRef) -> tuple[int, int, int, int]:
        r = window.ref.rectangle
        return int(r.left), int(r.top), int(r.right), int(r.bottom)

    def focus(self, window: WindowRef) -> None:
        from pywinauto.controls.uiawrapper import UIAWrapper
        try:
            UIAWrapper(window.ref).set_focus()
        except Exception as exc:  # noqa: BLE001
            raise UiaError(f"Could not bring '{window.title}' to the front: {type(exc).__name__}") from exc
        time.sleep(0.25)

    def grab(self, rect):
        from PIL import ImageGrab
        return ImageGrab.grab(bbox=rect, all_screens=True)

    def click(self, x: int, y: int, double: bool = False) -> None:
        import pyautogui
        pyautogui.click(x, y, clicks=2 if double else 1)

    def type_text(self, text: str) -> None:
        from ..tools.uia_backend import escape_for_send_keys
        from pywinauto.keyboard import send_keys
        send_keys(escape_for_send_keys(text), with_spaces=True, pause=0.01)

    def scroll(self, x: int, y: int, amount: int) -> None:
        import pyautogui
        pyautogui.moveTo(x, y)
        pyautogui.scroll(-int(amount) * 400)


_screen: ScreenBackend | None = None


def get_screen() -> ScreenBackend:
    global _screen
    if _screen is None:
        _screen = RealScreen()
    return _screen


def set_screen(screen: ScreenBackend | None) -> None:
    global _screen
    _screen = screen


class ScreenActArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")

    goal: str = Field(min_length=2, max_length=300, description='What to do on screen, e.g. "click Start", "type milk in the search box", "scroll down", "what is the score?"')
    window: str | None = Field(default=None, max_length=160, description="Part of the window title or the app name; empty = the window in front")


# what verify() needs from the moment before the action
_before: "OrderedDict[str, dict[str, Any]]" = OrderedDict()


def _words(lines) -> set[str]:
    return {w.casefold() for line in lines for w in re.findall(r"\w{2,}", line.text)}


def _line_texts(lines) -> set[str]:
    """Each OCR line as one string (digits and one-letter words included): a score going from "Score: 0" to "Score: 1" changes a line, not a word."""
    return {" ".join(line.text.casefold().split()) for line in lines if line.text.strip()}


def _small(image):
    from PIL import Image
    return image.convert("L").resize((240, max(1, round(240 * image.height / max(1, image.width)))), Image.BILINEAR)


def changed_share(a, b) -> float:
    """Share of pixels that differ clearly between two pictures of the same window (0..1)."""
    from PIL import ImageChops
    x, y = _small(a), _small(b)
    if x.size != y.size:
        y = y.resize(x.size)
    diff = ImageChops.difference(x, y).point(lambda v: 255 if v > 24 else 0)
    return diff.histogram()[255] / (x.width * x.height)


def _cloud_allowed() -> bool:
    from ..database import SessionLocal
    from ..preferences import get_preferences
    with SessionLocal() as db:
        return get_preferences(db).cloud_answers is True


class ScreenActTool(BaseTool):
    name = "screen_act"
    description = ("Layer 3, for an app with no accessibility information: look at the window, point at a detected box and click / type / scroll, or read "
                   "what is on screen. Slow (a few seconds); use ui_act first and native tools before that. Sends a picture of that window to the cloud AI. "
                   "One step per call; say the goal plainly.")
    risk_level = RiskLevel.MEDIUM
    args_schema = ScreenActArgs
    isolation = "thread"
    timeout_seconds = 60

    def risk_for_args(self, args: BaseModel | None) -> RiskLevel:
        if args is None:
            return RiskLevel.MEDIUM
        a = ScreenActArgs.model_validate(args.model_dump())
        if is_dangerous(a.goal) or is_shell_window(a.window or ""):
            return RiskLevel.HIGH
        if re.match(r"(?i)^\s*(?:what|read|which|who|how many|how much|is there|does|tell me)\b", a.goal):
            return RiskLevel.LOW      # a question about the screen: nothing is touched
        return RiskLevel.MEDIUM

    # ---------------------------------------------------------------------------------------------------- execute
    def execute(self, args: BaseModel) -> ToolResult:
        from ..config import get_settings
        a = ScreenActArgs.model_validate(args.model_dump())
        timings: dict[str, int] = {}
        started = time.perf_counter()
        if not _cloud_allowed():
            return ToolResult(success=False, error="Looking at the screen sends a picture of that window to the cloud AI. Turn on cloud answers in Settings first.")
        service, screen = get_service(), get_screen()
        try:
            window = service.window(a.window)
        except UiaError as exc:
            return ToolResult(success=False, error=str(exc))
        title = f"{window.title} {window.process}".casefold()
        if is_shell_window(window.title, window.process) or any(p in title for p in _PRIVATE_APPS):
            return ToolResult(success=False, error=f"'{window.title}' is a shell, an admin tool or a password manager: I do not look at it or type into it.")
        try:
            screen.focus(window)
            rect = screen.window_rect(window)
            t = time.perf_counter()
            image = screen.grab(rect)
            timings["capture_ms"] = round((time.perf_counter() - t) * 1000)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(success=False, error=f"I could not take a picture of '{window.title}': {type(exc).__name__}: {str(exc)[:100]}")
        t = time.perf_counter()
        try:
            lines = get_ocr().recognize(image)
        except OcrUnavailable:
            lines = []
        timings["ocr_ms"] = round((time.perf_counter() - t) * 1000)
        boxes = build_boxes(image.size, lines, self._uia_boxes(service, window, rect))
        if not boxes:
            return ToolResult(success=False, error=f"I found nothing I could point at in '{window.title}' (no text and no controls).")
        picture, scale = overlay.draw(image, boxes)
        t = time.perf_counter()
        jpeg = overlay.to_jpeg(picture)
        try:
            try:
                choice = get_vision(get_settings()).choose(jpeg, boxes, a.goal, window.title)
            except AIRateLimitError as limited:     # the vision model's rate limit is short: wait it out once instead of failing the step
                time.sleep(min(float(getattr(limited, "retry_after", None) or 5), 20.0))
                timings["waited_for_limit"] = 1
                choice = get_vision(get_settings()).choose(jpeg, boxes, a.goal, window.title)
        except Exception as exc:  # noqa: BLE001 - config, network, rate limit: all readable
            return ToolResult(success=False, error=str(exc)[:200] or type(exc).__name__)
        timings["model_ms"] = round((time.perf_counter() - t) * 1000)
        base = {"layer": 3, "notice": NOTICE, "window": window.title, "handle": window.handle, "boxes": len(boxes), "goal": a.goal, "timings": timings}
        if choice.action == "read":
            return ToolResult(success=True, output={**base, "action": "read", "answer": choice.answer, "spoken": choice.answer or "I could not read that.",
                                                    "screen_text": [ln.text for ln in lines][:12]})
        if choice.action == "none" or choice.box is None:
            return ToolResult(success=False, output=base, error=f"I looked at '{window.title}' but could not tell where to {a.goal.rstrip('.')}: {choice.reason or 'nothing fit'}.")
        box = next((b for b in boxes if b.id == choice.box), None)
        if box is None:
            return ToolResult(success=False, output=base, error=f"The vision model named box {choice.box}, which does not exist. Nothing was done.")
        refusal = self._refuse(a, choice, box)
        if refusal:
            return ToolResult(success=False, output={**base, "box": box.id}, error=refusal)
        before = {"image": image.copy(), "words": _words(lines), "lines": _line_texts(lines), "rect": rect, "action": choice.action, "text": choice.text}
        run_id = f"{window.handle}:{time.monotonic_ns()}"
        t = time.perf_counter()
        try:
            self._act(screen, rect, box, choice)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(success=False, output={**base, "box": box.id}, error=f"The click or typing did not go through: {type(exc).__name__}: {str(exc)[:100]}")
        timings["act_ms"] = round((time.perf_counter() - t) * 1000)
        _before[run_id] = before
        while len(_before) > _REMEMBERED:
            _before.popitem(last=False)
        timings["total_ms"] = round((time.perf_counter() - started) * 1000)
        return ToolResult(success=True, output={**base, "run_id": run_id, "action": choice.action, "box": box.id, "box_text": box.text[:60],
                                                "typed_chars": len(choice.text) if choice.action == "type" else 0, "amount": choice.amount,
                                                "model": get_vision(get_settings()).name, "reason": choice.reason,
                                                "spoken": self._said(choice, box)})

    @staticmethod
    def _said(choice, box: Box) -> str:
        label = (box.text or "it")[:40]
        return {"click": f"Clicked {label}.", "double_click": f"Opened {label}.", "type": "Typed it.", "scroll": "Scrolled."}.get(choice.action, "Done.")

    @staticmethod
    def _uia_boxes(service, window: WindowRef, rect) -> list[dict]:
        """What UI Automation does report for this window (little or nothing for a canvas app), in picture coordinates."""
        try:
            snap = service.snapshot(window, fresh=True)
        except Exception:  # noqa: BLE001
            return []
        left, top = rect[0], rect[1]
        return [{"rect": (c.rect[0] - left, c.rect[1] - top, c.rect[2] - left, c.rect[3] - top), "name": c.name, "type": c.type, "enabled": c.enabled, "password": c.password}
                for c in snap.controls if c.type in ("Button", "Edit", "ComboBox", "CheckBox", "RadioButton", "Hyperlink", "ListItem", "MenuItem", "TabItem", "Slider")]

    @staticmethod
    def _refuse(a: ScreenActArgs, choice, box: Box) -> str | None:
        text = box.text or ""
        if box.password or (_SECRET.search(text) and choice.action == "type"):
            return f"'{text[:40]}' looks like a password or a secret: I never type those. Type it yourself."
        if choice.action in ("click", "double_click") and is_dangerous(text) and not is_dangerous(a.goal):
            return f"The box '{text[:40]}' sends, pays, deletes or installs. Say its name in the command, so it is approved as such."
        if not box.enabled:
            return f"'{text[:40]}' is disabled right now."
        if choice.action == "type" and not choice.text:
            return "There was nothing to type."
        return None

    @staticmethod
    def _act(screen: ScreenBackend, rect, box: Box, choice) -> None:
        x, y = box.center[0] + rect[0], box.center[1] + rect[1]     # the centre of the DETECTED box, back in screen coordinates
        if choice.action in ("click", "double_click"):
            screen.click(x, y, double=choice.action == "double_click")
        elif choice.action == "type":
            screen.click(x, y)
            time.sleep(0.15)
            screen.type_text(choice.text)
        elif choice.action == "scroll":
            screen.scroll(x, y, max(-10, min(10, choice.amount or 3)))

    # ---------------------------------------------------------------------------------------------------- verify
    def verify(self, args: BaseModel, result: ToolResult) -> Verification:
        if not result.success:
            return Verification(passed=False, checks=["screen action done"], details=result.error)
        out = result.output
        if out.get("action") == "read":
            ok = bool(out.get("answer"))
            return Verification(passed=ok, checks=["the screen was read"], evidence={"layer": 3, "chars": len(out.get("answer") or ""), "screen_text": out.get("screen_text", [])[:5]},
                                details=None if ok else "The model could not read an answer from the screen.")
        before = _before.get(out.get("run_id", ""))
        if before is None:
            return Verification(passed=False, checks=["the window was photographed before"], details="The picture from before the action is gone, so I cannot compare.")
        screen = get_screen()
        time.sleep(0.9)       # let the app react
        try:
            window = next(w for w in get_service().backend.windows() if w.handle == out.get("handle"))
            after = screen.grab(screen.window_rect(window))
            lines = get_ocr().recognize(after)
        except StopIteration:
            return Verification(passed=True, checks=["the window closed"], evidence={"layer": 3, "window_gone": True})   # closing it was the effect
        except OcrUnavailable:
            lines = []
        except Exception as exc:  # noqa: BLE001
            return Verification(passed=False, checks=["window photographed again"], details=f"I could not look again: {type(exc).__name__}")
        share = changed_share(before["image"], after)
        now = _words(lines)
        added, removed = sorted(now - before["words"]), sorted(before["words"] - now)
        line_changes = len(_line_texts(lines) ^ before["lines"])
        action = before["action"]
        if action == "type":
            typed = {w.casefold() for w in re.findall(r"\w{2,}", before["text"])}
            seen = typed & now
            ok = bool(typed) and len(seen) >= max(1, round(0.6 * len(typed)))
            checks, why = [("the typed text is visible on screen", ok)], f"I could not see \"{before['text'][:30]}\" on the screen after typing."
        elif action == "scroll":
            ok = share >= 0.02 or len(added) + len(removed) >= 3 or line_changes >= 3
            checks, why = [("the content moved", ok)], "The content did not move (already at the end?)."
        else:
            ok = share >= _CHANGED_PIXELS or len(added) + len(removed) >= 2 or line_changes >= 1
            checks, why = [("the screen reacted", ok)], "Nothing on the screen changed after the click, so I cannot say it worked."
        return Verification(passed=ok, checks=[f"{n}: {v}" for n, v in checks], details=None if ok else why,
                            evidence={"layer": 3, "box": out.get("box"), "box_text": out.get("box_text"), "changed_pct": round(share * 100, 2), "lines_changed": line_changes,
                                      "words_added": added[:6], "words_removed": removed[:6], "seconds": round((out.get("timings") or {}).get("total_ms", 0) / 1000, 2)})


def screen_tools(ctx=None) -> list[BaseTool]:
    return [ScreenActTool(ctx)]

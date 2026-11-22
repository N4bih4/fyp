"""drive_coding_agent: give a prompt to a coding agent app (Antigravity ...) and watch it work until it stops.

Those apps are Electron windows: UI Automation sees only their title bar, so the tool works from the picture and the keyboard:
bring the window to the front, click the prompt box (a known place per app), paste the prompt (clipboard, so any language works and the
user's own clipboard is put back), press Enter, then look at the window every few seconds. While the picture keeps changing the agent
is still working; when it has stayed the same for `settle_seconds` it is done, and the text on screen is read back (Windows OCR) so
the user hears what it did. The mouse and keyboard are used only while typing, so other agents can use them between the checks.
"""
from __future__ import annotations

import ctypes
import difflib
import re
import time
from contextlib import nullcontext
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .. import progress
from ..vision.ocr import OcrUnavailable, get_ocr
from .base import BaseTool, RiskLevel, ToolResult, Verification
from .screen import changed_share, get_screen
from .uia import get_service
from .uia_backend import UiaError

# Where the prompt box and the "new conversation" button are, as a share of the window (x, y). Antigravity is measured on a real window;
# the others are best guesses until someone checks them (the tool says so in its result).
# `input` / `new_chat`: where the prompt box and the "new conversation" button are, as a share of the window (x, y); the backup when the prompt box
# cannot be found on screen. `hints`: text the empty prompt box shows (found by OCR first, because the box moves when side panels open or close).
# Antigravity and Claude were measured on real windows of this PC. Codex, Cursor and ChatGPT are not installed here: their hints and places are
# best guesses, and the tool says so in its result.
PROFILES: dict[str, dict[str, Any]] = {
    "antigravity": {"title": "Antigravity", "input": (0.58, 0.89), "new_chat": (0.08, 0.118), "chat_left": 0.17, "verified": True,
                    "hints": ["ask anything"], "projects": True},
    "claude": {"title": "Claude", "input": (0.52, 0.915), "new_chat": None, "chat_left": 0.2, "verified": True,
               "hints": ["enter to send", "reply to claude", "message claude", "how can i help", "queue for later"]},
    "codex": {"title": "Codex", "input": (0.5, 0.9), "new_chat": None, "chat_left": 0.0, "verified": False,
              "hints": ["ask codex", "ask anything", "describe a task", "message codex"]},
    "cursor": {"title": "Cursor", "input": (0.85, 0.9), "new_chat": None, "chat_left": 0.7, "verified": False,
               "hints": ["plan, @ for context", "add a follow-up", "ask anything", "@ to mention"]},
    "chatgpt": {"title": "ChatGPT", "input": (0.5, 0.9), "new_chat": None, "chat_left": 0.0, "verified": False,
                "hints": ["ask anything", "message chatgpt"]},
}
POLL_SECONDS = 2.5
CHANGED = 0.004                    # share of the window's pixels that must differ for "still working"
MAX_PROMPT = 4000


class CodingAgentArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")

    app: str = Field(min_length=2, max_length=30, description="antigravity, claude, codex, cursor or chatgpt")
    prompt: str = Field(min_length=1, max_length=MAX_PROMPT, description="The exact prompt to give the coding agent, in the user's own words")
    new_conversation: bool = Field(default=False, description="Start a fresh conversation first")
    project: str | None = Field(default=None, max_length=120, description="Antigravity only: the project (as it is named in its sidebar) the conversation must belong to. "
                                "A new conversation is started in it and checked on screen before the prompt is sent.")
    wait_seconds: int = Field(default=180, ge=5, le=900, description="Watch it for at most this long")
    settle_seconds: int = Field(default=10, ge=3, le=60, description="The screen must stay the same this long to count as finished")


# ---- the machine: small functions so tests can replace them
def _clipboard_api():
    """user32 / kernel32 with 64-bit safe signatures (a handle is a pointer, not an int)."""
    from ctypes import wintypes
    user32, kernel32 = ctypes.WinDLL("user32", use_last_error=True), ctypes.WinDLL("kernel32", use_last_error=True)
    user32.OpenClipboard.argtypes, user32.OpenClipboard.restype = [wintypes.HWND], wintypes.BOOL
    user32.CloseClipboard.restype = wintypes.BOOL
    user32.EmptyClipboard.restype = wintypes.BOOL
    user32.GetClipboardData.argtypes, user32.GetClipboardData.restype = [wintypes.UINT], ctypes.c_void_p
    user32.SetClipboardData.argtypes, user32.SetClipboardData.restype = [wintypes.UINT, ctypes.c_void_p], ctypes.c_void_p
    kernel32.GlobalAlloc.argtypes, kernel32.GlobalAlloc.restype = [wintypes.UINT, ctypes.c_size_t], ctypes.c_void_p
    kernel32.GlobalLock.argtypes, kernel32.GlobalLock.restype = [ctypes.c_void_p], ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes, kernel32.GlobalUnlock.restype = [ctypes.c_void_p], wintypes.BOOL
    return user32, kernel32


def set_clipboard(text: str) -> None:
    """Windows clipboard, unicode text."""
    CF_UNICODETEXT, GMEM_MOVEABLE = 13, 0x0002
    user32, kernel32 = _clipboard_api()
    data = text.encode("utf-16-le") + b"\x00\x00"
    for _ in range(10):
        if user32.OpenClipboard(None):
            break
        time.sleep(0.05)
    else:
        raise RuntimeError("The clipboard is busy.")
    try:
        user32.EmptyClipboard()
        handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
        ptr = kernel32.GlobalLock(handle)
        ctypes.memmove(ptr, data, len(data))
        kernel32.GlobalUnlock(handle)
        user32.SetClipboardData(CF_UNICODETEXT, handle)
    finally:
        user32.CloseClipboard()


def get_clipboard() -> str | None:
    CF_UNICODETEXT = 13
    user32, kernel32 = _clipboard_api()
    if not user32.OpenClipboard(None):
        return None
    try:
        handle = user32.GetClipboardData(CF_UNICODETEXT)
        if not handle:
            return None
        ptr = kernel32.GlobalLock(handle)
        try:
            return ctypes.wstring_at(ptr)
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()


def press(*keys: str) -> None:
    import pyautogui
    pyautogui.hotkey(*keys) if len(keys) > 1 else pyautogui.press(keys[0])


def ui_lock():
    """The shared mouse / keyboard turn (see agents.runner); a no-op where that module is not loaded."""
    try:
        from ..agents.runner import _UI_LOCK
        return _UI_LOCK
    except Exception:  # noqa: BLE001
        return nullcontext()


USE_PRINTWINDOW = True


def capture_window(handle: int):
    """The window's own picture, even when other windows cover it (PrintWindow with PW_RENDERFULLCONTENT; works for Electron / Chromium
    windows). None when the window is minimised, gone, or the picture is blank."""
    if not handle:
        return None
    import platform
    if platform.system() != "Windows":
        return None
    from ctypes import wintypes

    from PIL import Image
    user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
    if user32.IsIconic(handle):
        return None
    rect = wintypes.RECT()
    if not user32.GetWindowRect(handle, ctypes.byref(rect)):
        return None
    width, height = rect.right - rect.left, rect.bottom - rect.top
    if width <= 0 or height <= 0:
        return None

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
                    ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD), ("biSizeImage", wintypes.DWORD),
                    ("biXPelsPerMeter", wintypes.LONG), ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
                    ("biClrImportant", wintypes.DWORD)]

    hdc = user32.GetWindowDC(handle)
    mem = gdi32.CreateCompatibleDC(hdc)
    bitmap = gdi32.CreateCompatibleBitmap(hdc, width, height)
    try:
        gdi32.SelectObject(mem, bitmap)
        if not user32.PrintWindow(handle, mem, 2):
            return None
        header = BITMAPINFOHEADER(40, width, -height, 1, 32, 0, 0, 0, 0, 0, 0)
        buffer = ctypes.create_string_buffer(width * height * 4)
        gdi32.GetDIBits(mem, bitmap, 0, height, buffer, ctypes.byref(header), 0)
        image = Image.frombuffer("RGBA", (width, height), buffer, "raw", "BGRA", 0, 1).convert("RGB")
    finally:
        gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(mem)
        user32.ReleaseDC(handle, hdc)
    low, high = image.convert("L").getextrema()
    return image if high - low > 8 else None          # all one colour = a window that did not draw itself


def find_prompt_box(image, hints: list[str]) -> tuple[float, float] | None:
    """Where the empty prompt box is, as (x, y) shares of the picture, by reading its placeholder text. Only the lower 45% is searched, and the
    lowest match wins (a chat that quotes the placeholder text above must not be clicked). None when OCR is unavailable or nothing matches."""
    try:
        lines = get_ocr().recognize(image)
    except Exception:  # noqa: BLE001 - no OCR language, no winsdk: the measured place is used instead
        return None
    floor = image.height * 0.55
    hits = [l for l in lines if l.rect[1] >= floor and any(h in " ".join(l.text.casefold().split()) for h in hints)]
    if not hits:
        return None
    best = max(hits, key=lambda l: l.rect[1])
    return ((best.rect[0] + best.rect[2]) / 2 / image.width, (best.rect[1] + best.rect[3]) / 2 / image.height)


def _rect_at(rect: tuple[int, int, int, int], fx: float, fy: float) -> tuple[int, int]:
    left, top, right, bottom = rect
    return int(left + (right - left) * fx), int(top + (bottom - top) * fy)


def _chat_area(rect: tuple[int, int, int, int], left_share: float) -> tuple[int, int, int, int]:
    left, top, right, bottom = rect
    return int(left + (right - left) * left_share), top + 50, right, bottom


def read_screen_text(image, max_chars: int = 1800) -> str:
    """The text on screen, top to bottom; the end of it is kept (the newest part of a chat)."""
    lines = get_ocr().recognize(image)
    text = "\n".join(line.text for line in sorted(lines, key=lambda l: (l.rect[1], l.rect[0])) if line.text.strip())
    return text[-max_chars:]


def _name_key(text: str) -> str:
    """"Photo Translator" / "photo-translator" / "Photo_Translator" -> "photo translator"."""
    return " ".join(re.sub(r"[-_./\\]+", " ", str(text or "")).casefold().split())


def _name_match(wanted: str, seen: str) -> float:
    a, b = _name_key(wanted), _name_key(seen)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if b.startswith(a) or a.startswith(b):
        return 0.9
    if re.search(r"(?<![a-z0-9])" + re.escape(a) + r"(?![a-z0-9])", b):
        return 0.9                      # "el downloads v": the name with an icon and an arrow around it
    return difflib.SequenceMatcher(None, a, b).ratio()


def _lines(image) -> list:
    try:
        return list(get_ocr().recognize(image))
    except Exception:  # noqa: BLE001 - no OCR: the caller reports that it cannot see
        return []


def project_pill(image, chat_left: float) -> tuple[tuple[float, float], str] | None:
    """The project chooser on a new conversation: a chip on the row just above the prompt box ("[folder] Downloads v   [laptop] Local Checkout v", the
    second chip changes to the git branch once a project is chosen). Found as the left-most text on that row, the row being located from the prompt
    box's placeholder ("Ask anything, @ to mention"). ((x, y) shares of the picture, its text), None when it is not on screen."""
    h, w = image.height, image.width
    top, left = int(h * 0.6), int(w * chat_left)
    lines = _lines(image.crop((left, top, w, h)))
    box = next((l for l in lines if "ask anything" in l.text.casefold() or "to mention" in l.text.casefold()), None)
    if box is None:
        return None
    mid = (box.rect[1] + box.rect[3]) / 2
    height = max(box.rect[3] - box.rect[1], 12)
    row = [l for l in lines if l is not box and l.text.strip() and mid - height * 5 <= (l.rect[1] + l.rect[3]) / 2 <= mid - height * 1.5]
    if not row:
        return None
    pill = min(row, key=lambda l: l.rect[0])
    r = pill.rect
    return (((r[0] + r[2]) / 2 + left) / w, ((r[1] + r[3]) / 2 + top) / h), pill.text.strip()


def popup_open(image) -> bool:
    """The chooser list is showing (its fixed entries "New Project" / "No Project" are on screen)."""
    h, w = image.height, image.width
    text = " ".join(l.text.casefold() for l in _lines(image.crop((int(w * 0.3), int(h * 0.35), int(w * 0.6), int(h * 0.84)))))
    return "new project" in text or "no project" in text or "search projects" in text


def find_in_popup(image, wanted: str, chat_left: float) -> tuple[float, float] | None:
    """A project's row in the open chooser list (it opens above the pill): (x, y) shares, or None when no row reads like `wanted`."""
    h, w = image.height, image.width
    box = (int(w * 0.3), int(h * 0.35), int(w * 0.6), int(h * 0.84))
    rows = sorted((l for l in _lines(image.crop(box)) if l.text.strip()), key=lambda l: l.rect[1])
    rows = rows[1:]                                  # the first line is the search box itself: what was typed there must never be clicked
    skip = ("recent", "this computer", "ssh host", "new project", "no project", "no matching")
    best = max(((_name_match(wanted, l.text), l) for l in rows if not any(k in l.text.casefold() for k in skip)),
               key=lambda p: p[0], default=(0.0, None))
    if best[1] is None or best[0] < 0.8:
        return None
    r = best[1].rect
    return (((r[0] + r[2]) / 2 + box[0]) / w, ((r[1] + r[3]) / 2 + box[1]) / h)


def _same_window(window, front) -> bool:
    """The app's own window is in front. By handle or process, never by title: Antigravity renames its window to the conversation's name."""
    if window.handle and front.handle:
        return window.handle == front.handle
    if window.process and front.process:
        return window.process.casefold() == front.process.casefold()
    return window.title.casefold() in front.title.casefold()


class CodingAgentTool(BaseTool):
    name = "drive_coding_agent"
    description = ("Give a prompt to a coding agent app that is already open (Antigravity, Claude, Codex, Cursor, ChatGPT) and watch it until it stops, "
                   "then report what it says on screen. Open the app first with open_application. The prompt is typed for the user, so it needs approval.")
    risk_level = RiskLevel.MEDIUM
    args_schema = CodingAgentArgs
    isolation = "thread"            # it reports progress lines and shares the mouse / keyboard lock with the other agents
    timeout_seconds = 960

    def execute(self, args: BaseModel) -> ToolResult:
        a = CodingAgentArgs.model_validate(args.model_dump())
        profile = PROFILES.get(a.app.casefold().strip())
        if profile is None:
            return ToolResult(success=False, error=f"I do not know how to drive '{a.app}'. Known: {', '.join(PROFILES)}.")
        name = profile["title"]
        service, screen = get_service(), get_screen()
        try:
            window = service.window(profile["title"])
        except UiaError:
            return ToolResult(success=False, error=f"{name} is not open. Open it first, then give it the prompt.")
        old_clip = None
        try:
            with ui_lock():
                screen.focus(window)
                rect = screen.window_rect(window)
                if a.project:
                    problem = self._enter_project(screen, window, rect, a.project, profile)
                    if problem:
                        return ToolResult(success=False, error=problem)
                elif a.new_conversation and profile["new_chat"]:
                    screen.click(*_rect_at(rect, *profile["new_chat"]))
                    time.sleep(0.8)
                before = screen.grab(rect)
                found = find_prompt_box(before, profile["hints"])
                box = found or profile["input"]
                box_found_by = "ocr" if found else "measured place"
                screen.click(*_rect_at(rect, *box))
                time.sleep(0.3)
                old_clip = get_clipboard()
                set_clipboard(a.prompt)
                press("ctrl", "v")
                time.sleep(0.6)
                typed = changed_share(before, screen.grab(rect))
                if typed < 0.0003:
                    return ToolResult(success=False, error=f"I clicked where {name}'s prompt box should be, but nothing appeared there. Click the box once and try again.")
                press("enter")
                if a.project:                                       # the new-conversation screen (with its project chip) must give way to the conversation
                    for _ in range(10):
                        time.sleep(0.6)
                        if project_pill(screen.grab(rect), profile["chat_left"]) is None:
                            break
                    else:
                        return ToolResult(success=False, error=f"I pressed Enter but {name} still shows the new-conversation screen, so I cannot say the prompt was sent. Check it.")
        except UiaError as exc:
            return ToolResult(success=False, error=str(exc))
        finally:
            if old_clip is not None:
                try:
                    set_clipboard(old_clip)
                except Exception:  # noqa: BLE001 - the user's clipboard is a courtesy, not a result
                    pass
        progress.say(f"Prompt sent to {name}. Watching it work.")
        finished, seconds, steady, last = self._watch(service, screen, window, a, profile)
        text = ""
        try:
            rect = screen.window_rect(window)
            image = capture_window(window.handle) if USE_PRINTWINDOW else None
            if image is None:
                with ui_lock():
                    screen.focus(window)
                    image = screen.grab(rect)
            left = int(image.width * profile["chat_left"])
            text = read_screen_text(image.crop((left, min(50, image.height // 10), image.width, image.height)))
        except (OcrUnavailable, UiaError, OSError):
            pass
        return ToolResult(success=True, output={
            "app": name, "prompt_sent": a.prompt[:200], "finished": finished, "watched_seconds": round(seconds),
            "still_working_when_stopped_watching": not finished, "screen_text": text, "layout_verified": profile["verified"], "prompt_box_found_by": box_found_by, **({"project": a.project} if a.project else {}),
            **({"note": "This app's prompt box position is a guess, not measured."} if not profile["verified"] else {})})

    @staticmethod
    def _enter_project(screen, window, rect, project: str, profile) -> str | None:
        """New conversation, then the project chooser under the prompt box is set to `project` and read back to prove it (Antigravity's chooser has a
        "Search Projects" box). Returns a sentence when it could not be done: the prompt is then NOT sent."""
        if not profile.get("projects") or not profile["new_chat"]:
            return f"{profile['title']} has no project list I can drive yet. Open the project in it yourself, then give the prompt."
        left, title = profile["chat_left"], profile["title"]
        screen.click(*_rect_at(rect, *profile["new_chat"]))
        pill = None
        for _ in range(8):                                         # the new conversation takes a moment to draw
            time.sleep(0.6)
            pill = project_pill(screen.grab(rect), left)
            if pill is not None:
                break
        if pill is None:
            return f"I cannot see {title}'s project chooser on the new conversation, so I cannot tell which project it is in. I did not send the prompt."
        if _name_match(project, pill[1]) >= 0.8:
            return None
        for _ in range(3):                                         # a click can only focus the chip: look, and click again until the list is open
            screen.click(*_rect_at(rect, *pill[0]))
            time.sleep(0.9)
            if popup_open(screen.grab(rect)):
                break
        else:
            return f"I could not open {title}'s project list. I did not send the prompt."
        row = find_in_popup(screen.grab(rect), project, left)
        if row is None:                                            # not among the recent ones: type it into the chooser's search box
            screen.type_text(next((w for w in re.split(r"[\s_.-]+", project) if len(w) >= 3), project))   # one word: "Phone" finds "Phone-Cleaner"
            time.sleep(0.8)
            row = find_in_popup(screen.grab(rect), project, left)
        if row is None:
            press("escape")
            return f"I cannot find a project called '{project}' in {title}'s chooser. Say the name as it is written there. I did not send the prompt."
        screen.click(*_rect_at(rect, *row))
        time.sleep(0.8)
        after = project_pill(screen.grab(rect), left)
        if after is None or _name_match(project, after[1]) < 0.8:
            return f"I chose '{project}' but {title} shows '{after[1] if after else 'no project'}'. I did not send the prompt."
        return None

    @staticmethod
    def _watch(service, screen, window, a: CodingAgentArgs, profile) -> tuple[bool, float, float, Any]:
        """Look every few seconds. Returns (finished, seconds watched, seconds steady, last picture)."""
        start = time.monotonic()
        last = None
        steady_since = start
        next_say = start + 20
        while time.monotonic() - start < a.wait_seconds:
            progress.check()
            time.sleep(POLL_SECONDS)
            rect = screen.window_rect(window)
            image = capture_window(window.handle) if USE_PRINTWINDOW else None
            if image is None:
                try:
                    front = service.window(None)
                except UiaError:
                    front = None
                if front is None or not _same_window(window, front):
                    steady_since = time.monotonic()    # it cannot draw itself while covered: a screen picture would show the window on top
                    continue
            picture = image if image is not None else screen.grab(rect)
            if last is not None and changed_share(last, picture) >= CHANGED:
                steady_since = time.monotonic()
            last = picture
            now = time.monotonic()
            if now >= next_say:
                progress.say(f"{profile['title']} is still working ({round(now - start)} s).")
                next_say = now + 25
            if last is not None and now - steady_since >= a.settle_seconds:
                return True, now - start, now - steady_since, last
        return False, time.monotonic() - start, time.monotonic() - steady_since, last

    def verify(self, args: BaseModel, result: ToolResult) -> Verification:
        if not result.success:
            return Verification(passed=False, checks=["prompt delivered"], details=result.error)
        out = result.output
        ok = bool(out.get("prompt_sent"))
        return Verification(passed=ok, checks=["the prompt box changed after the paste", "the window was watched"],
                            evidence={"app": out.get("app"), "finished": out.get("finished"), "watched_seconds": out.get("watched_seconds"),
                                      "text_chars": len(out.get("screen_text", ""))})


def coding_agent_tools(ctx=None) -> list[BaseTool]:
    return [CodingAgentTool(ctx)]

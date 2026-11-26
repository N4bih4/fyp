"""Which browser opens a website: never a silent guess when the PC has more than one.

The rule (docs/VOICE_AUTOMATION_PLAN.md, Phase 2): a tool that must open a browser asks `resolve()`. The answer is, in order:
  1. a browser the sentence named (the tool's `browser` argument);
  2. the user's standing choice ("always use Chrome": the preference `browser_always`, set only when the user says it);
  3. the browser of the conversation lane that is still alive (the user chose one a few minutes ago; the lane lives 20 minutes);
  4. the only installed browser, when there is just one;
  5. otherwise NOTHING is opened: a question comes back ("Which browser: Chrome, Edge or Firefox?"), and after the browser, if that browser has several
     profiles, a second question ("Which profile?").
The question is a normal tool result with `needs_confirmation`, so the executor turns it into a waiting task and the answer is read by
`ai/clarify_answers.py`. This is the single place that decides; the tools open the browser through `open_in()`.
"""
from __future__ import annotations

import os
import platform
import shutil
import time
from dataclasses import dataclass
from pathlib import Path

from . import platform as _platform
from .base import ToolResult

KEY = "browser_always"
SPOKEN = {
    "chrome": ("chrome", "google chrome", "क्रोम", "کروم", "krom"), "edge": ("edge", "microsoft edge", "एज", "ایج"),
    "firefox": ("firefox", "fire fox", "फ़ायरफ़ॉक्स", "फायरफॉक्स", "فائر فاکس"), "brave": ("brave", "ब्रेव", "بریو"), "opera": ("opera", "ओपेरा"),
}


@dataclass(frozen=True)
class Browser:
    key: str
    name: str
    exe: str


_SPECS = {
    "chrome": ("Chrome", ("Google", "Chrome", "Application", "chrome.exe"), "chrome"),
    "edge": ("Edge", ("Microsoft", "Edge", "Application", "msedge.exe"), "msedge"),
    "firefox": ("Firefox", ("Mozilla Firefox", "firefox.exe"), "firefox"),
    "brave": ("Brave", ("BraveSoftware", "Brave-Browser", "Application", "brave.exe"), "brave"),
    "opera": ("Opera", ("Programs", "Opera", "opera.exe"), "opera"),
}
_cache: tuple[float, list[Browser]] | None = None


def _find(key: str) -> str | None:
    _, parts, command = _SPECS[key]
    found = shutil.which(command)
    if found:
        return found
    for root in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
        base = os.environ.get(root)
        if base and Path(base, *parts).is_file():
            return str(Path(base, *parts))
    return None


def installed(refresh: bool = False) -> list[Browser]:
    """The browsers really installed on this PC (looked up once a minute)."""
    global _cache
    if not refresh and _cache and time.monotonic() - _cache[0] < 60:
        return list(_cache[1])
    found = []
    if platform.system() == "Windows":
        for key, (name, _, _) in _SPECS.items():
            exe = _find(key)
            if exe:
                found.append(Browser(key, name, exe))
    _cache = (time.monotonic(), found)
    return list(found)


def set_installed_for_tests(browsers: list[Browser] | None) -> None:
    global _cache
    _cache = None if browsers is None else (time.monotonic() + 3600, list(browsers))


def key_of(spoken: str) -> str | None:
    """"Google Chrome" / "क्रोम" / "edge" -> "chrome" / "edge"; None when it names no browser."""
    low = " ".join(str(spoken or "").casefold().split())
    for key, names in SPOKEN.items():
        if any(low == n.casefold() or (len(n) > 3 and n.casefold() in low) or low.split()[:1] == [n.casefold()] for n in names):
            return key
    return None


# ------------------------------------------------------------------ the standing choice and the lane's choice
def _stored() -> dict:
    try:
        import json

        from ..database import SessionLocal
        from ..models import Preference
        with SessionLocal() as db:
            row = db.get(Preference, KEY)
            return json.loads(row.value_json) if row and row.value_json else {}
    except Exception:  # noqa: BLE001 - no database (a tool test): nothing remembered
        return {}


def always() -> dict:
    """{"browser": "chrome", "profile": "Profile 3" | None} when the user said "always use ...", else {}."""
    data = _stored()
    return data if data.get("browser") else {}


def set_always(browser: str | None, profile: str | None = None) -> None:
    import json

    from ..database import SessionLocal
    from ..models import Preference
    with SessionLocal() as db:
        row = db.get(Preference, KEY) or Preference(key=KEY)
        row.value_json = json.dumps({"browser": browser, "profile": profile} if browser else {})
        db.add(row)
        db.commit()
        if not browser:                    # "ask me every time" also forgets what the conversation had chosen
            from ..orchestration import lanes
            state = lanes.load(db)
            lane = lanes.lane_of_kind(state, "browser")
            if lane is not None and lane.browser:
                lane.browser = lane.profile = None
                lanes.save(db, state)


def lane_choice() -> dict:
    """The browser (and profile) chosen in the browser lane that is still alive, or {}."""
    try:
        from ..database import SessionLocal
        from ..orchestration import lanes
        with SessionLocal() as db:
            lane = lanes.lane_of_kind(lanes.load(db), "browser")
            if lane is not None and lane.browser:
                return {"browser": lane.browser, "profile": lane.profile}
    except Exception:  # noqa: BLE001
        pass
    return {}


def remember_in_lane(browser: str, profile: str | None) -> None:
    try:
        from ..database import SessionLocal
        from ..orchestration import lanes
        with SessionLocal() as db:
            lanes.set_browser(db, browser, profile)
    except Exception:  # noqa: BLE001
        pass


# ------------------------------------------------------------------ the decision
@dataclass
class Choice:
    browser: Browser | None = None
    profile: str | None = None           # a profile folder ("Profile 3"), when one was chosen
    ask: ToolResult | None = None        # set when the user must answer first


def _question(kind: str, names: list[str], text: str, **extra) -> ToolResult:
    return ToolResult(success=False, output={"candidates": names, "needs_confirmation": True, "question": text, "asking": kind, **extra}, error=text)


def resolve(requested: str | None = None) -> Choice:
    """See the module docstring. `requested` is the tool's own `browser` argument ("default" / None = nothing named)."""
    have = installed()
    by_key = {b.key: b for b in have}
    if requested and requested != "default":
        return Choice(browser=by_key.get(requested))
    if not have:
        return Choice()
    choice = always() or lane_choice()
    if choice.get("browser") in by_key:
        browser = by_key[choice["browser"]]
        profile = choice.get("profile")
        if profile or browser.key not in ("chrome", "edge"):
            return Choice(browser=browser, profile=profile)
        profiles = _profiles(browser.key)
        if len(profiles) > 1:
            names = [p["name"] if [q["name"] for q in profiles].count(p["name"]) == 1 else f"{p['name']} ({p['dir']})" for p in profiles]
            return Choice(browser=browser, ask=_question("profile", names, f"Which {browser.name} profile: {', '.join(names[:5])}?", browser=browser.key))
        return Choice(browser=browser, profile=profiles[0]["dir"] if profiles else None)
    if len(have) == 1:
        return Choice(browser=have[0])
    names = [b.name for b in have]
    return Choice(ask=_question("browser", names, f"Which browser: {', '.join(names[:-1])} or {names[-1]}?"))


def _profiles(browser: str) -> list[dict]:
    from .browser_profiles import list_profiles
    return list_profiles(browser)


def open_in(browser: Browser, url: str | None = None, profile: str | None = None) -> None:
    """Start this browser (in this profile) on a page; the browser itself reuses a running window."""
    args = []
    if profile and browser.key in ("chrome", "edge"):
        args.append(f"--profile-directory={profile}")
    if url:
        args.append(url)
    _platform.launch_program(browser.exe, args)


_PROCESS = {"chrome": "chrome.exe", "edge": "msedge.exe", "firefox": "firefox.exe", "brave": "brave.exe", "opera": "opera.exe"}


def is_this_app(title: str) -> bool:
    """True for the browser window whose front tab is AgentDesk itself (its page title, or its address in the title). Typing an address into THAT window
    would replace the assistant's own page: "open gmail" turned the AgentDesk tab into Gmail."""
    text = (title or "").casefold()
    return "agentdesk" in text or "127.0.0.1:8000" in text or "localhost:8000" in text


def _foreground_title() -> str:
    """The title of the window in front, read with one cheap Win32 call (no UI Automation: that can take many seconds on a busy desktop)."""
    try:
        import ctypes
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        buffer = ctypes.create_unicode_buffer(512)
        user32.GetWindowTextW(hwnd, buffer, 512)
        return buffer.value
    except Exception:  # noqa: BLE001 - not Windows / no window: nothing known
        return ""


IN_PLACE_SECONDS = 8.0


def navigate_in_place(browser: Browser, url: str) -> bool:
    """The one-window behaviour with a hard time limit: if the window in front is AgentDesk itself (the usual case: the user talks to it) nothing is
    typed and the caller opens a new tab at once; the UI Automation work runs in a helper thread and is given up after IN_PLACE_SECONDS (a slow desktop
    made "open j.website" hang for the tool's whole 30 s). A late helper types nothing: it checks a cancel flag before every key."""
    if is_this_app(_foreground_title()):
        return False
    import threading
    cancel = threading.Event()
    done: list[bool] = [False]

    def work() -> None:
        done[0] = _navigate_in_place_ui(browser, url, cancel)

    worker = threading.Thread(target=work, daemon=True)
    worker.start()
    worker.join(IN_PLACE_SECONDS)
    if worker.is_alive():
        cancel.set()
        return False
    return done[0]


def _navigate_in_place_ui(browser: Browser, url: str, cancel=None) -> bool:
    """Show `url` in the window the browser already has open (Ctrl+L, the address, Enter) instead of opening one more tab: the conversation stays in
    one browser window until the user says "new tab". False (nothing typed) when the browser has no window, or its window could not be brought to the front."""
    import time
    try:
        from .coding_agent import get_clipboard, press, set_clipboard, ui_lock
        from .screen import get_screen
        from .uia import get_service
        from .uia_backend import UiaError
        service, screen = get_service(), get_screen()
        wanted = _PROCESS.get(browser.key, "")
        windows = [w for w in service.backend.windows() if w.process.casefold() == wanted and w.title]
        if not windows:
            return False
        try:
            front = service.window(None)
        except UiaError:
            front = None
        target = front if front is not None and front.process.casefold() == wanted else windows[0]
        if is_this_app(getattr(target, "title", "")):
            return False                       # never replace the page the assistant itself runs in: the caller opens a NEW tab
        old_clip = None
        with ui_lock():
            if cancel is not None and cancel.is_set():
                return False                   # the caller gave up and opened a new tab: type nothing now
            screen.focus(target)
            time.sleep(0.25)
            if service.window(None).handle != target.handle or (cancel is not None and cancel.is_set()):       # never type into a window that is not the browser
                return False
            old_clip = get_clipboard()
            set_clipboard(url)
            press("ctrl", "l")
            time.sleep(0.2)
            press("ctrl", "v")
            time.sleep(0.15)
            press("enter")
        if old_clip is not None:
            try:
                set_clipboard(old_clip)
            except Exception:  # noqa: BLE001 - the clipboard is a courtesy
                pass
        return True
    except Exception:  # noqa: BLE001 - any trouble: the caller opens a new tab the ordinary way
        return False

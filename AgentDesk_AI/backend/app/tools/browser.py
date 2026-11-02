"""Exact browser tab matching and idempotent YouTube pause/resume."""
from typing import Literal
from urllib.parse import urlsplit
from pydantic import BaseModel, Field, model_validator
from ..browser_bridge import bridge
from ..verification import failed_result, verdict
from .base import BaseTool, RiskLevel, ToolResult, Verification

SITES = {
    "youtube": {"youtube.com"}, "google drive": {"drive.google.com"}, "drive": {"drive.google.com"},
    "gmail": {"mail.google.com"}, "whatsapp": {"web.whatsapp.com"},
    "openai": {"openai.com"}, "chatgpt": {"chatgpt.com"},
}


def select_tabs(tabs, target):
    target = target.strip().casefold()
    if target in SITES:
        domains = SITES[target]
        return [t for t in tabs if any((urlsplit(t.get("url", "")).hostname or "").casefold() == host or (urlsplit(t.get("url", "")).hostname or "").casefold().endswith("." + host) for host in domains)]
    # Exact title or URL only for unfamiliar names; never arbitrary substring closing.
    return [t for t in tabs if target and target in {t.get("title", "").casefold(), t.get("url", "").casefold()}]


def _clean_tabs(raw) -> list[dict]:
    """The extension is outside this process; accept only well-formed tab records."""
    tabs = []
    for item in raw if isinstance(raw, list) else []:
        if isinstance(item, dict) and isinstance(item.get("id"), int) and not isinstance(item.get("id"), bool):
            tabs.append({
                "id": item["id"],
                "title": str(item.get("title") or "")[:300],
                "url": str(item.get("url") or "")[:2000],
                "active": bool(item.get("active")),
                "audible": bool(item.get("audible")),
            })
    return tabs


def public_tab(tab: dict) -> dict:
    """Tab info that may leave the backend (UI, AI prompts): URLs lose query and fragment,
    which often carry session tokens or private search text."""
    parts = urlsplit(tab.get("url", ""))
    shown = f"{parts.scheme}://{parts.netloc}{parts.path}" if parts.scheme and parts.netloc else ""
    return {**tab, "url": shown}


# What each new action needs, and what the page must show afterwards (the extension reads the page again and sends what it saw).
PAGE_ACTIONS = {"seek", "speed", "volume", "mute", "unmute", "fullscreen", "next", "results", "click_result", "scroll", "previous", "theatre",
                "captions", "quality", "loop", "skip_ad", "like", "subscribe", "now_playing"}
YOUTUBE_ONLY = PAGE_ACTIONS | {"pause", "resume"}
# Seconds the app waits for the extension's answer: these actions wait for the page itself (a video to load, a player to settle) on slow connections.
SLOW_ACTIONS = {"next": 40, "previous": 40, "click_result": 75, "resume": 20, "pause": 20, "quality": 25, "results": 20, "click_link": 20, "web_click_result": 20, "subscribe": 20, "like": 20}
WEB_ACTIONS = {"read_page", "click_link", "fill", "web_results", "web_click_result", "web_scroll"}      # on any http(s) tab (the active one by default)
BROWSER_WIDE = {"reopen", "bookmarks", "history"}                                                       # need no tab
QUALITIES = ("auto", "tiny", "small", "medium", "large", "hd720", "hd1080", "hd1440", "hd2160", "highres")


class BrowserControlArgs(BaseModel):
    action: Literal["inspect", "close", "pause", "resume", "switch", "read", "seek", "speed", "volume", "mute", "unmute", "fullscreen", "next",
                    "results", "click_result", "scroll", "previous", "theatre", "captions", "quality", "loop", "skip_ad", "like", "subscribe", "now_playing",
                    "read_page", "click_link", "fill", "web_results", "web_click_result", "web_scroll", "reopen", "bookmarks", "history"]
    target: str = Field(default="youtube", max_length=500)
    tab_id: int | None = Field(default=None, ge=0)
    seconds: int | None = Field(default=None, ge=-3600, le=3600, description="seek: seconds forward (+) or back (-)")
    position: int | None = Field(default=None, ge=0, le=86400, description="seek: go to this second of the video")
    rate: float | None = Field(default=None, ge=0.25, le=4, description="speed: playback speed, 1 = normal")
    level: int | None = Field(default=None, ge=0, le=100, description="volume: the video player's volume, 0-100")
    index: int | None = Field(default=None, ge=1, le=20, description="click_result: which search result, counting from 1")
    amount: int | None = Field(default=None, ge=-10, le=10, description="scroll: pages down (+) or up (-)")
    exit: bool = Field(default=False, description="fullscreen: true leaves full screen")
    kind: Literal["video", "playlist"] = "video"
    enable: bool = True
    quality: str | None = Field(default=None, description="auto, hd720, hd1080 ...")
    name: str | None = Field(default=None, max_length=120, description="words of the link or result")
    field: str | None = Field(default=None, max_length=80, description="fill: field label")
    text: str | None = Field(default=None, max_length=2000, description="fill: text (never a password)")
    query: str | None = Field(default=None, max_length=100)
    days: int | None = Field(default=None, ge=1, le=365)
    max_chars: int | None = Field(default=None, ge=200, le=20000)

    @model_validator(mode="after")
    def _needs(self):
        need = {"seek": (self.seconds is not None) or (self.position is not None), "speed": self.rate is not None, "volume": self.level is not None,
                "click_result": self.index is not None, "scroll": bool(self.amount), "quality": self.quality in QUALITIES,
                "click_link": bool(self.name), "fill": bool(self.field) and self.text is not None, "web_scroll": bool(self.amount),
                "web_click_result": bool(self.name) or self.index is not None}
        if self.action in need and not need[self.action]:
            raise ValueError(f"{self.action} needs " + {"seek": "seconds or position", "speed": "rate", "volume": "level", "click_result": "index",
                                                        "scroll": "a non-zero amount", "quality": "quality (" + ", ".join(QUALITIES) + ")",
                                                        "click_link": "name", "fill": "field and text", "web_scroll": "a non-zero amount",
                                                        "web_click_result": "index or name"}[self.action])
        if self.action in WEB_ACTIONS and self.target.strip().casefold() in ("", "youtube"):
            self.target = "active"      # the default target belongs to the YouTube controls: a web action works on the tab in front
        return self


def _spoken(a: BrowserControlArgs, out: dict) -> str:
    """One short sentence to say aloud. Only what the page showed, never what was merely asked."""
    title = str(out.get("title") or "")[:70]
    if a.action == "seek":
        return f"At {int(out.get('time') or 0) // 60}:{int(out.get('time') or 0) % 60:02d}."
    if a.action == "speed":
        return f"Speed is {out.get('rate'):g}x."
    if a.action == "volume":
        return f"Video volume is {out.get('volume')} percent."
    if a.action in {"mute", "unmute"}:
        return "The video is muted." if out.get("muted") else "The video is unmuted."
    if a.action == "fullscreen":
        return "Full screen." if out.get("fullscreen") else "Back to normal size."
    if a.action == "next":
        return f"Playing: {title}."
    if a.action == "click_result":
        return f"Playing: {str(out.get('clicked_title') or title)[:70]}."
    if a.action == "results":
        names = [str(x)[:40] for x in (out.get("results") or [])[:3]]
        return "Top results: " + "; ".join(f"{i}. {n}" for i, n in enumerate(names, 1)) + "." if names else "No results found."
    if a.action in {"scroll", "web_scroll"}:
        return "Scrolled."
    if a.action == "previous":
        return f"Playing: {title}."
    if a.action in {"theatre", "captions", "loop"}:
        flag = out.get({"theatre": "theatre", "captions": "captions", "loop": "loop"}[a.action])
        return f"{a.action.capitalize()} is {'on' if flag else 'off'}."
    if a.action == "quality":
        return f"Quality is {out.get('quality') or a.quality}."
    if a.action == "skip_ad":
        return "Skipped the ad."
    if a.action == "like":
        return "You already liked this video." if out.get("already_liked") else "Liked."
    if a.action == "subscribe":
        return f"Subscribed to {str(out.get('channel') or 'the channel')[:50]}."
    if a.action == "now_playing":
        return f"{str(out.get('video_title') or title)[:80]}" + (f", by {str(out.get('channel'))[:40]}." if out.get("channel") else ".")
    if a.action == "read_page":
        heads = [str(h)[:60] for h in (out.get("headings") or [])[:2]]
        return f"The page is {title}." + (" It says: " + "; ".join(heads) + "." if heads else "")
    if a.action == "click_link":
        return f"Clicked {str(out.get('clicked') or 'it')[:60]}."
    if a.action == "web_click_result":
        return f"Opened {str(out.get('clicked_title') or '')[:70]}."
    if a.action == "web_results":
        names = [str(x)[:40] for x in (out.get("results") or [])[:3]]
        return "Top results: " + "; ".join(f"{i}. {n}" for i, n in enumerate(names, 1)) + "." if names else "No results found."
    if a.action == "fill":
        return "Filled it in."
    if a.action in {"bookmarks", "history"}:
        names = [str(r.get("title") or r.get("url"))[:40] for r in (out.get("results") or [])[:3] if isinstance(r, dict)]
        return ("I found: " + "; ".join(names) + ".") if names else "Nothing matches."
    if a.action == "reopen":
        return f"Reopened {str(out.get('reopened') or 'the last closed tab')[:60]}."
    if a.action == "switch":
        return f"Switched to {title}."
    if a.action == "read":
        return f"The page is called {title}."
    return ""


class BrowserControlTool(BaseTool):
    name = "control_browser"
    description = ("Browser tabs and the page in front: inspect, close or switch to one exact tab, read the title or page; YouTube: pause, resume, seek, speed, "
                   "volume, mute, fullscreen, next/previous, results, click result N, theatre, captions, quality, loop, skip ad, like, subscribe, now playing; "
                   "websites: click a link, fill a field, scroll, bookmarks, history, reopen a tab. Needs the Agent X Browser Bridge extension "
                   "(YouTube pause/resume/seek also work by keyboard without it). Never touches an unrelated tab.")
    args_schema = BrowserControlArgs
    risk_level = RiskLevel.LOW
    isolation = "thread"  # the extension socket lives in the server process

    def risk_for_args(self, args):
        """Liking and reading are low; subscribing, filling a field and clicking a link on a website ask first (the page may also refuse)."""
        if args is None:
            return self.risk_level
        action = getattr(args, "action", None) or (args.get("action") if isinstance(args, dict) else None)
        if action in {"subscribe", "fill", "click_link"}:
            return RiskLevel.MEDIUM
        return RiskLevel.LOW

    def execute(self, args):
        a = BrowserControlArgs.model_validate(args.model_dump())
        if a.action in BROWSER_WIDE:
            if not bridge.supports(a.action):
                return ToolResult(success=False, error="The browser extension is older than 2.0: reload it at chrome://extensions, then repeat.")
            reply = bridge.request(a.action, query=a.query or "", days=a.days or 30)
            if not reply.get("success"):
                return ToolResult(success=False, error=reply.get("error", "Browser action failed"))
            output = {"action": a.action, **{k: v for k, v in reply.items() if k in {"results", "reopened", "url"}}}
            output["spoken"] = _spoken(a, output)
            return ToolResult(success=True, output=output)
        observed = bridge.request("inspect")
        if not observed.get("success") and "connect nahi" in str(observed.get("error", "")) and a.action in YOUTUBE_ONLY:
            return self._by_keyboard(a)         # the extension is not connected: the player's own keyboard shortcuts, said plainly
        if not observed.get("success"):
            return ToolResult(success=False, error=observed.get("error", "Browser inspect failed"))
        tabs = _clean_tabs(observed.get("tabs"))
        if a.action == "inspect":
            return ToolResult(success=True, output={"tabs": [public_tab(t) for t in tabs]})
        if (a.action in PAGE_ACTIONS or a.action in WEB_ACTIONS) and not bridge.supports(a.action):
            return ToolResult(success=False, error="The browser extension is older than 1.2 (2.0 for the newest controls): reload it at chrome://extensions "
                                                   "(it updates itself when connected), then repeat.")
        if a.action in {"read", *WEB_ACTIONS} and a.tab_id is None and a.target.strip().casefold() in ("", "active", "this", "current"):
            matches = [t for t in tabs if t.get("active")]
        else:
            matches = [t for t in tabs if t["id"] == a.tab_id] if a.tab_id is not None else select_tabs(tabs, a.target)
        if a.action in YOUTUBE_ONLY:
            matches = select_tabs(matches, "youtube")
            # For media only, an unambiguous audible (or the one active) YouTube tab is a meaningful target.
            audible = [t for t in matches if t.get("audible")]
            active = [t for t in matches if t.get("active")]
            if len(matches) > 1 and len(audible) == 1:
                matches = audible
            elif len(matches) > 1 and len(active) == 1:
                matches = active
        if len(matches) != 1:
            shown = "; ".join(f"tab {t['id']}: {t.get('title', '')}" for t in matches)
            return ToolResult(success=False, output={"candidates": [public_tab(t) for t in matches], "needs_confirmation": True}, error="Matching tab nahi mila; unrelated tab ko touch nahi kiya." if not matches else "Multiple matching tabs. Exact title ya tab ID batayein: " + shown)
        tab = matches[0]
        extra = {k: v for k, v in a.model_dump().items() if k in {"seconds", "position", "rate", "level", "index", "amount", "exit", "name", "field", "text", "max_chars"}
                 and v is not None and v is not False}
        if a.action in {"results", "click_result"}:
            extra["kind"] = a.kind
        if a.action in {"theatre", "captions", "loop"}:
            extra["enable"] = a.enable
        if a.action == "quality":
            extra["level"] = a.quality
        if a.action in SLOW_ACTIONS:
            extra["wait"] = SLOW_ACTIONS[a.action]       # how long the app waits for the page (a slow connection); the default is 8 s
        result = bridge.request(a.action, tab_id=tab["id"], expected_url=tab.get("url", ""), **extra)
        if not result.get("success"):
            return ToolResult(success=False, error=result.get("error", "Browser action failed"))
        if a.action in {"close", "pause", "resume"}:
            verified = result.get("closed") is True if a.action == "close" else result.get("paused") is (a.action == "pause")
            if not verified:
                return ToolResult(success=False, error="Browser ne requested tab/video state verify nahi ki.")
        keep = {"success", "closed", "paused", "error", "title", "url", "active", "time", "duration", "rate", "volume", "muted", "fullscreen", "video_id",
                "previous_video_id", "changed", "target", "results", "clicked_title", "wanted_video_id", "moved", "scroll_y", "scroll_max",
                "playing", "theatre", "captions", "quality", "requested", "available", "loop", "ad_gone", "liked", "already_liked", "subscribed",
                "already_subscribed", "channel", "video_title", "text", "headings", "chars", "clicked", "navigated", "field", "filled_chars", "matches"}
        output = {"action": a.action, "tab_id": tab["id"], "title": tab.get("title"), **{k: v for k, v in result.items() if k in keep}}
        output["spoken"] = _spoken(a, output)
        return ToolResult(success=True, output=output)

    @staticmethod
    def _by_keyboard(a: BrowserControlArgs) -> ToolResult:
        """Slower fallback without the extension (tools/yt_keys.py): press the YouTube shortcut in the browser window that shows YouTube."""
        from . import yt_keys
        out = yt_keys.act(a.action, a.seconds)
        if not out.get("success"):
            return ToolResult(success=False, error=out.get("error", "The keyboard fallback failed."))
        said = {"pause": "Paused.", "resume": "Playing.", "seek": "Skipped.", "mute": "Mute pressed.", "unmute": "Mute pressed.", "fullscreen": "Full screen pressed.",
                "theatre": "Theatre mode pressed.", "captions": "Captions pressed.", "next": "Next video pressed.", "previous": "Previous video pressed."}[a.action]
        note = " The browser helper is off, so I used a slower method" + ("." if out.get("confirmed") else " and could not check the result.")
        return ToolResult(success=True, output={"action": a.action, "via": "keyboard", "confirmed": bool(out.get("confirmed")), "window": out.get("window"),
                                                "paused": out.get("status_after") == "paused" if out.get("status_after") else None, "spoken": said + note})

    def verify(self, args, result: ToolResult) -> Verification:
        """Evidence comes from the browser extension (a separate process that reads the real tabs)."""
        if not result.success:
            return failed_result(result)
        a = BrowserControlArgs.model_validate(args.model_dump())
        if result.output.get("via") == "keyboard":
            confirmed = bool(result.output.get("confirmed"))
            return Verification(passed=confirmed, checks=["Windows reports the new playback state" if a.action in ("pause", "resume") else "key sent to the YouTube window"],
                                evidence={"via": "keyboard", "window": result.output.get("window")},
                                details=None if confirmed else "I pressed the key but cannot confirm the result without the browser helper.")
        if a.action == "inspect":
            tabs = result.output.get("tabs", [])
            return verdict([("extension returned the tab list", isinstance(tabs, list))], {"tabs": len(tabs)})
        observed = bridge.request("inspect")
        if not observed.get("success"):
            return Verification(passed=False, checks=["could not re-inspect tabs"], details=observed.get("error"))
        fresh = _clean_tabs(observed.get("tabs"))
        ids = {t["id"] for t in fresh}
        if a.action in BROWSER_WIDE:
            out = result.output
            ok = bool(out.get("reopened")) or bool(out.get("results"))
            return verdict([({"reopen": "a closed tab was restored", "bookmarks": "bookmarks were found", "history": "history entries were found"}[a.action], ok)],
                           {"count": len(out.get("results") or []), "reopened": out.get("reopened")})
        if a.action in PAGE_ACTIONS | WEB_ACTIONS | {"switch", "read"}:
            return self._verify_page(a, result.output, fresh, ids)
        tab_id = result.output.get("tab_id")
        evidence = {"tab_id": tab_id, "tabs_now": len(ids), "extension_reply": {k: result.output.get(k) for k in ("closed", "paused")}}
        if a.action == "close":
            return verdict([("extension confirmed close", result.output.get("closed") is True), ("tab is gone", tab_id not in ids)], evidence)
        return verdict([("extension confirmed video state", result.output.get("paused") is (a.action == "pause")),
                        ("tab still open", tab_id in ids)], evidence)

    @staticmethod
    def _verify_page(a: BrowserControlArgs, out: dict, tabs: list[dict], ids: set) -> Verification:
        """What the page showed AFTER the action (read by the extension from the DOM) must match what was asked; the tab must still be there."""
        tab = next((t for t in tabs if t["id"] == out.get("tab_id")), None)
        evidence = {k: out.get(k) for k in ("tab_id", "title", "time", "rate", "volume", "muted", "fullscreen", "video_id", "scroll_y", "active") if out.get(k) is not None}
        checks = [("tab still open", tab is not None)]
        if a.action == "seek":
            want = out.get("target")
            checks.append(("the video is at the requested time", want is not None and out.get("time") is not None and abs(out["time"] - want) <= 2))
        elif a.action == "speed":
            checks.append(("the player runs at the requested speed", out.get("rate") is not None and abs(out["rate"] - a.rate) < 0.01))
        elif a.action == "volume":
            checks.append(("the player volume is the requested level", out.get("volume") is not None and abs(out["volume"] - a.level) <= 1 and out.get("muted") is False))
        elif a.action in {"mute", "unmute"}:
            checks.append(("the player is " + ("muted" if a.action == "mute" else "unmuted"), out.get("muted") is (a.action == "mute")))
        elif a.action == "fullscreen":
            checks.append(("the video is " + ("full screen" if not a.exit else "back to normal"), out.get("fullscreen") is (not a.exit)))
        elif a.action == "next":
            checks.append(("a different video is playing", bool(out.get("video_id")) and out.get("video_id") != out.get("previous_video_id")))
        elif a.action == "click_result":
            if out.get("wanted_video_id"):
                checks.append(("the chosen result's video opened", out.get("video_id") == out.get("wanted_video_id")))
            else:
                checks.append(("the chosen playlist opened", bool(out.get("video_id"))))
            if a.kind == "video" and "playing" in out:
                checks.append(("the player is running", out.get("playing") is True))
        elif a.action == "previous":
            checks.append(("a different video is playing", bool(out.get("video_id")) and out.get("video_id") != out.get("previous_video_id")))
        elif a.action == "theatre":
            checks.append(("theatre mode is " + ("on" if a.enable else "off"), out.get("theatre") is a.enable))
        elif a.action == "captions":
            checks.append(("captions are " + ("on" if a.enable else "off"), out.get("captions") is a.enable))
        elif a.action == "loop":
            checks.append(("looping is " + ("on" if a.enable else "off"), out.get("loop") is a.enable))
        elif a.action == "quality":
            checks.append(("the player reports the quality", a.quality == "auto" or out.get("quality") == a.quality))
        elif a.action == "skip_ad":
            checks.append(("the skip button is gone", out.get("ad_gone") is True))
        elif a.action == "like":
            checks.append(("the video shows as liked", out.get("liked") is True))
        elif a.action == "subscribe":
            checks.append(("the channel shows as subscribed", out.get("subscribed") is True))
        elif a.action == "now_playing":
            checks.append(("a title was read from the page", bool(out.get("video_title") or out.get("title"))))
        elif a.action == "read_page":
            checks.append(("text was read from the page", bool(out.get("chars"))))
        elif a.action == "click_link":
            checks.append(("the page accepted the click", out.get("success") is not False and bool(out.get("clicked"))))
        elif a.action == "web_click_result":
            checks.append(("a result was opened", bool(out.get("clicked_title"))))
        elif a.action == "web_results":
            checks.append(("results were read from the page", bool(out.get("results"))))
        elif a.action == "fill":
            checks.append(("the field now holds the text", out.get("filled_chars") == len(a.text or "")))
        elif a.action == "web_scroll":
            checks.append(("the page moved", out.get("moved") is True))
        elif a.action == "scroll":
            checks.append(("the page moved", out.get("moved") is True))
        elif a.action == "results":
            checks.append(("results were read from the page", bool(out.get("results"))))
        elif a.action == "switch":
            checks.append(("the tab is now the active one", tab is not None and tab.get("active") is True))
        elif a.action == "read":
            checks.append(("the tab's title was read", bool(out.get("title"))))
        return verdict(checks, evidence)



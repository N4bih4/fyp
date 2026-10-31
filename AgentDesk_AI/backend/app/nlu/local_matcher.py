"""Local fast path: normalised tokens -> NLUPlan with a confidence score.

No network, no filesystem access. The matcher only proposes; the plan still
goes through `validate_plan` and the server's risk policy like any LLM plan.

Confidence starts at 0.95 for a full rule match and is lowered for each
fuzzy-corrected word and each word the rule could not explain. Below the
threshold (0.85 by default) the caller should ask the LLM planner instead.
Unknown requests return confidence 0 (never a guess).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .memory import ConversationMemory, Turn
from .normalizer import EMAIL, FILLER, PATHLIKE, URLLIKE, Normalized, Token, normalize
from .schema import NLUPlan, PlanStep

THRESHOLD = 0.85
BASE = 0.95
NEGATIONS = {"not", "don't", "dont", "never", "nahi", "nahin", "mat", "نہیں", "مت", "नहीं", "मत"}
LOCATIONS = {"DESKTOP": "~/Desktop", "DOCUMENTS": "~/Documents", "DOWNLOADS": "~/Downloads"}
SITE_URLS = {"youtube": "https://www.youtube.com", "gmail": "https://mail.google.com",
             "whatsapp": "https://web.whatsapp.com", "chatgpt": "https://chatgpt.com",
             "google drive": "https://drive.google.com"}
SITE_DOMAINS = {"youtube": "youtube.com"}
APP_DISPLAY = {"calc": "calculator"}
SETTINGS_TOKENS = {"VOLUME": "volume", "BRIGHTNESS": "brightness", "BLUETOOTH": "bluetooth", "WIFI": "wifi"}
# Harmless verbs people add around commands; they do not lower confidence.
SOFT_WORDS = {"turn", "set", "switch", "make", "go", "check", "kya", "hai", "please", "again", "right",
              "now", "show", "me", "can", "you", "for", "new", "a", "an", "the", "called", "named",
              "with", "by", "level", "ab", "phir", "abhi", "wala", "wali", "one", "bit", "little"}

REPLIES = {
    "en": {"ok": "Okay, doing that now.", "clarify_target": "Which one should I use? Please say its name.",
           "clarify_value": "What should I do with {x}: up, down, on, off or a number?",
           "clarify_email": "Which e-mail address should the draft go to?", "clarify_where": "Where should I create it?",
           "unsupported": "I can't do that safely yet.", "chat": "Hi! Tell me what to do on your PC."},
    "roman_ur": {"ok": "Theek hai, kar raha hoon.", "clarify_target": "Kaunsa? Naam bata dein.",
                 "clarify_value": "{x} ke liye kya karun: kam, zyada, on, off ya number?",
                 "clarify_email": "Draft kis email address par banaun?", "clarify_where": "Kahan banaun?",
                 "unsupported": "Yeh kaam abhi safely nahi kar sakta.", "chat": "Ji! Batayein PC par kya karna hai."},
    "ur": {"ok": "ٹھیک ہے، کر رہا ہوں۔", "clarify_target": "کون سا؟ نام بتا دیں۔",
           "clarify_value": "{x} کے لیے کیا کروں: کم، زیادہ، آن، آف یا نمبر؟",
           "clarify_email": "ڈرافٹ کس ای میل ایڈریس پر بناؤں؟", "clarify_where": "کہاں بناؤں؟",
           "unsupported": "یہ کام ابھی محفوظ طریقے سے نہیں کر سکتا۔", "chat": "جی! بتائیں پی سی پر کیا کرنا ہے۔"},
    "hi": {"ok": "ठीक है, कर रहा हूँ।", "clarify_target": "कौन सा? नाम बता दीजिए।",
           "clarify_value": "{x} के लिए क्या करूँ: कम, ज़्यादा, ऑन, ऑफ या नंबर?",
           "clarify_email": "ड्राफ्ट किस ईमेल पते पर बनाऊँ?", "clarify_where": "कहाँ बनाऊँ?",
           "unsupported": "यह काम अभी सुरक्षित तरीके से नहीं कर सकता।", "chat": "जी! बताइए पीसी पर क्या करना है।"},
}


@dataclass
class MatchResult:
    plan: NLUPlan | None
    confidence: float
    rule: str = "none"
    notes: list[str] = field(default_factory=list)

    @property
    def confident(self) -> bool:
        return self.plan is not None and self.confidence >= THRESHOLD


def step(tool: str, depends_on: int | None = None, **args) -> PlanStep:
    return PlanStep(tool=tool, args=args, depends_on=depends_on)


class _Ctx:
    """Tokens of one (sub)command plus the helpers rules share."""

    def __init__(self, norm: Normalized, tokens: list[Token], memory: ConversationMemory):
        self.norm = norm
        self.lang = norm.language
        self.memory = memory
        self.all_tokens = tokens
        self.tokens = [t for t in tokens if t.canon not in FILLER and t.canon != ","]
        self.canons = [t.canon for t in self.tokens]
        self.set = set(self.canons)
        self.text = " ".join(t.text for t in tokens)

    def has(self, *canons: str) -> bool:
        return any(c in self.set for c in canons)

    def prefixed(self, prefix: str) -> list[str]:
        return [c.split(":", 1)[1] for c in self.canons if c.startswith(prefix)]

    def numbers(self) -> list[int]:
        return [int(c) for c in self.canons if c.isdigit()]

    def first(self, *canons: str) -> str | None:
        return next((c for c in self.canons if c in canons), None)

    def location(self) -> str | None:
        loc = self.first(*LOCATIONS)
        return LOCATIONS[loc] if loc else None

    def path(self) -> str | None:
        return next((t.text for t in self.tokens if PATHLIKE.search(t.text)), None)

    def url(self) -> str | None:
        return next((t.text.rstrip(",.") for t in self.tokens if URLLIKE.match(t.text.rstrip(",."))), None)

    def name(self, structural: set[str]) -> str:
        """Surface words left after removing structural tokens (names, queries)."""
        words = [t.text for t in self.tokens
                 if t.canon not in structural and not t.canon.startswith(("APP:", "SITE:"))
                 and t.canon not in LOCATIONS]
        return " ".join(words).strip(" ,")

    def unexplained(self, explained: set[str]) -> int:
        count = 0
        for t in self.tokens:
            c = t.canon
            if c in explained or c.isdigit() or c.lower() in SOFT_WORDS or c in {"PERCENT", "TO", "IN", "BIT"} \
                    or c in LOCATIONS:
                continue
            if c.startswith(("APP:", "SITE:", "PKG:")) and c.split(":")[0] + ":*" in explained:
                continue
            count += 1
        return count

    def reply(self, key: str, **kw) -> str:
        return REPLIES.get(self.lang, REPLIES["en"])[key].format(**kw)


def _plan(ctx: _Ctx, intent: str, steps: list[PlanStep], conf: float, rule: str) -> MatchResult:
    conf -= 0.04 * sum(t.fuzzy for t in ctx.tokens)
    plan = NLUPlan(intent=intent, language=ctx.lang, confidence=round(max(conf, 0.0), 3),
                   steps=steps, reply=ctx.reply("ok"))
    return MatchResult(plan, plan.confidence, rule)


def _special(ctx: _Ctx, intent: str, key: str, rule: str, conf: float = BASE, **kw) -> MatchResult:
    text = ctx.reply(key, **kw)
    plan = NLUPlan(intent=intent, language=ctx.lang, confidence=conf, needs_clarification=intent == "clarify",
                   clarifying_question=text if intent == "clarify" else None, steps=[], reply=text)
    return MatchResult(plan, conf, rule)


def _penalty(ctx: _Ctx, explained: set[str]) -> float:
    return 0.06 * ctx.unexplained(explained)


# ------------------------------------------------------------------ rules
_WHATSAPP = (
    r"^send (?:a |an )?whatsapp (?:message|msg) to (?P<who>[^,]+?)(?: (?:saying|that|with the text|:) (?P<text>.+))?$",
    r"^(?P<who>.+?) ko whatsapp (?:pe|par|per) (?:message|msg|ye message) (?:bhejo|bhej do|karo|kar do|likho)(?: (?:ke|keh|ki|kay) (?P<text>.+))?$",
    r"^(?P<who>.+?) کو واٹس ایپ (?:پر|پہ) (?:پیغام|میسج) (?:بھیجو|بھیج دو|کرو)(?: (?:کہ|کے) (?P<text>.+))?$",
    r"^(?P<who>.+?) को व्हाट्सएप (?:पर|पे) (?:मैसेज|संदेश) (?:भेजो|भेज दो|करो)(?: (?:कि|के) (?P<text>.+))?$",
)


def r_whatsapp(ctx: _Ctx):
    """WhatsApp messages are pre-filled in WhatsApp Desktop; the user presses Send (rule 8)."""
    if "whatsapp" not in ctx.prefixed("SITE:") or not ctx.has("SEND", "MESSAGE"):
        return None
    text = ctx.norm.text.strip()
    for pattern in _WHATSAPP:
        m = re.match(pattern, text, re.I)
        if m:
            who = m.group("who").strip()
            message = (m.group("text") or "").strip()
            target = {"phone": who.replace(" ", "")} if re.fullmatch(r"\+?[\d\s-]{8,20}", who) else {"contact": who}
            return _plan(ctx, "whatsapp_draft", [step("whatsapp_open_chat", text=message, **target)], BASE, "whatsapp")
    return _special(ctx, "clarify", "clarify_target", "whatsapp.no_contact")


def r_media(ctx: _Ctx):
    """Music/media keys: next/previous track, play/pause music. YouTube and videos stay with the browser rules."""
    if ctx.prefixed("SITE:") or ctx.has("VIDEO", "TAB"):
        return None
    if not ctx.has("MUSIC", "NEXT", "PREVIOUS"):
        return None
    if ctx.has("NEXT"):
        action = "next"
    elif ctx.has("PREVIOUS"):
        action = "previous"
    elif ctx.has("PAUSE", "CLOSE", "OFF"):
        action = "pause"
    elif ctx.has("RESUME", "PLAY", "RUN", "ON", "OPEN"):
        action = "play"
    else:
        return _special(ctx, "clarify", "clarify_value", "media.no_action", x="music")
    explained = {"MUSIC", "NEXT", "PREVIOUS", "PAUSE", "CLOSE", "OFF", "RESUME", "PLAY", "RUN", "ON", "OPEN", "WALA"}
    return _plan(ctx, "media_control", [step("media_control", action=action)], BASE - _penalty(ctx, explained), "media")


def r_unsupported(ctx: _Ctx):
    if (ctx.has("FORMAT") and ctx.has("DRIVE")) or \
            (ctx.has("COMMAND") and ("powershell" in ctx.prefixed("APP:") or "run" in ctx.set)):
        return _special(ctx, "unsupported", "unsupported", "unsupported")
    return None


def r_chat(ctx: _Ctx):
    social = {"GREETING", "THANKS", "HOWAREYOU"}
    if ctx.set & social and len(ctx.set - social - {"WHAT"}) <= 1 and not any(c.isupper() and c not in social for c in ctx.set - {"WHAT"}):
        return _special(ctx, "chat", "chat", "chat")
    return None


def r_email(ctx: _Ctx):
    if not ctx.has("EMAIL"):
        return None
    address = next((t.text.rstrip(",.") for t in ctx.tokens if EMAIL.match(t.text.rstrip(",."))), None)
    if address is None:
        return _special(ctx, "clarify", "clarify_email", "email.no_address")
    exact = re.search(r"subject (.+?) and body (.+)$", ctx.text, re.I)
    if exact:
        return _plan(ctx, "email_draft", [step("compose_email", to=address, subject=exact.group(1).strip(),
                                               body=exact.group(2).strip())], BASE, "email.exact")
    return MatchResult(None, 0.4, "email.needs_drafting", ["subject/body must be drafted by the LLM"])


def r_settings_page(ctx: _Ctx):
    page = None
    if ctx.has("WINDOWS") and ctx.has("UPDATE"):
        page = "windowsupdate"
    elif ctx.has("SETTINGS"):
        for canon, value in (("DISPLAY", "display"), ("LOCKSCREEN", "lockscreen"), ("BLUETOOTH", "bluetooth"),
                             ("WIFI", "wifi"), ("VOLUME", "sound"), ("UPDATE", "windowsupdate")):
            if ctx.has(canon):
                page = value
                break
        page = page or "root"
    if page is None or ctx.numbers():
        return None
    explained = {"SETTINGS", "OPEN", "SHOW", "WINDOWS", "UPDATE", "DISPLAY", "LOCKSCREEN", "BLUETOOTH", "WIFI", "VOLUME"}
    return _plan(ctx, "settings_page", [step("open_windows_settings", page=page)], BASE - _penalty(ctx, explained),
                 "settings_page")


def r_device(ctx: _Ctx):
    settings = [SETTINGS_TOKENS[c] for c in ctx.canons if c in SETTINGS_TOKENS]
    louder = any(t.text.casefold() in {"louder", "quieter", "softer"} for t in ctx.tokens)
    if ctx.has("DARK", "LIGHT"):
        settings.append("theme")
    if not settings and (louder or (ctx.has("MUTE", "UNMUTE") and len(ctx.set - {"MUTE", "UNMUTE"}) == 0)):
        settings = ["volume"]
    settings = list(dict.fromkeys(settings))
    if len(settings) != 1:
        return None
    setting = settings[0]
    nums = ctx.numbers()
    question = ctx.norm.question or ctx.has("GET") or (ctx.tokens and ctx.norm.text.casefold().startswith("is "))
    action, value = None, None
    if setting == "theme":
        action = "dark" if ctx.has("DARK") else "light" if ctx.has("LIGHT") else "get" if question else None
    elif ctx.has("UNMUTE"):
        action = "unmute"
    elif ctx.has("MUTE"):
        action = "mute"
    elif setting in {"bluetooth", "wifi"}:
        if question:
            action = "get"
        elif ctx.has("ON", "OPEN"):
            action = "on"
        elif ctx.has("OFF", "CLOSE"):
            action = "off"
    else:
        if ctx.has("MAX"):
            action, value = "set", 100
        elif ctx.has("HALF"):
            action, value = "set", 50
        elif ctx.has("UP") or louder:
            action, value = "increase", nums[0] if nums else 10
        elif ctx.has("DOWN"):
            action, value = "decrease", nums[0] if nums else 10
        elif setting == "volume" and ctx.has("CLOSE", "OFF"):
            action = "mute"
        elif setting == "volume" and ctx.has("ON") and not nums:
            action = "unmute"
        elif nums:
            action, value = "set", nums[0]
        elif question:
            action = "get"
    if action is None:
        if len(ctx.set - {c for c in ctx.set if c.lower() in SOFT_WORDS}) == 1:
            return _special(ctx, "clarify", "clarify_value", "device.no_action", x=setting)
        return None
    if value is not None and not (0 <= value <= 100) or (action in {"increase", "decrease"} and value == 0):
        return None
    if len(nums) > 1:
        return None
    args = {"setting": setting, "action": action}
    if value is not None:
        args["value"] = value
    explained = {"VOLUME", "BRIGHTNESS", "BLUETOOTH", "WIFI", "DARK", "LIGHT", "MODE", "UP", "DOWN", "ON", "OFF",
                 "MUTE", "UNMUTE", "MAX", "HALF", "GET", "CLOSE", "OPEN", "SCREEN", "IT", "WHAT"}
    explained |= {t.canon for t in ctx.tokens if t.text.casefold() in {"louder", "quieter", "softer"}}
    return _plan(ctx, "system_setting", [step("manage_system_setting", **args)], BASE - _penalty(ctx, explained),
                 "device")


def r_followup(ctx: _Ctx):
    if ctx.path() or ctx.has("WRITE"):
        return None  # "write first version to C:\\x.txt": an explicit target is never a reference to earlier results
    memory = ctx.memory
    ordinal = ctx.first("FIRST", "SECOND", "THIRD")
    if ordinal:
        resolved = memory.resolve_ordinal(ordinal)
        if resolved is None:
            return _special(ctx, "clarify", "clarify_target", "followup.no_results")
        item, kind = resolved
        if ctx.has("DELETE"):
            return _plan(ctx, "delete", [step("delete_file", path=item, include_contents=False)], BASE, "followup.ordinal")
        if ctx.has("OPEN", "SHOW", "RUN"):
            if kind == "file":
                return _plan(ctx, "open_file", [step("open_file", path=item)], BASE, "followup.ordinal")
            return _plan(ctx, "open_folder", [step("open_folder", path=item)], BASE, "followup.ordinal")
        return None
    adjust = ctx.has("UP", "DOWN") or (ctx.has("BIT") and ctx.has("AND"))
    rest = ctx.set - {"UP", "DOWN", "BIT", "AND", "IT"} - {c for c in ctx.set if c.lower() in SOFT_WORDS}
    if adjust and not rest:
        setting = memory.last_setting()
        if setting in {"volume", "brightness"}:
            action = "decrease" if ctx.has("DOWN") else "increase"
            return _plan(ctx, "system_setting", [step("manage_system_setting", setting=setting, action=action, value=10)],
                         BASE, "followup.adjust")
        return _special(ctx, "clarify", "clarify_target", "followup.no_setting")
    verbs = ctx.set & {"OPEN", "CLOSE", "DELETE", "RUN"}
    bare = len(verbs) == 1 and not (ctx.set - verbs - {"IT"} - {c for c in ctx.set if c.lower() in SOFT_WORDS})
    if not (ctx.has("IT") or bare) or len(verbs) != 1:
        return None
    verb = verbs.pop()
    target = memory.last_target()
    if target is None:
        return _special(ctx, "clarify", "clarify_target", "followup.no_target")
    if verb == "CLOSE":
        if target.kind == "app":
            return _plan(ctx, "close_window", [step("control_desktop", target_window=APP_DISPLAY.get(target.value, target.value),
                                                    steps=[{"action": "close_window"}])], BASE, "followup.close_app")
        if target.kind == "site":
            return _plan(ctx, "browser_tab", [step("control_browser", action="close", target=target.value)], BASE,
                         "followup.close_site")
        if target.kind == "window":
            return _plan(ctx, "close_window", [step("control_desktop", target_window=target.value,
                                                    steps=[{"action": "close_window"}])], BASE, "followup.close_window")
    if verb in {"OPEN", "RUN"}:
        if target.kind == "folder":
            return _plan(ctx, "open_folder", [step("open_folder", path=target.value)], BASE, "followup.open")
        if target.kind == "file":
            return _plan(ctx, "open_file", [step("open_file", path=target.value)], BASE, "followup.open")
        if target.kind == "app":
            return _plan(ctx, "open_app", [step("open_application", app_name=target.value)], BASE, "followup.open")
    return _special(ctx, "clarify", "clarify_target", "followup.unclear")


def r_browser(ctx: _Ctx):
    sites = ctx.prefixed("SITE:")
    text = ctx.norm.text
    if ctx.has("TAB") and ctx.has("SHOW", "OPEN") and not sites and not ctx.has("CLOSE"):
        return _plan(ctx, "browser_tab", [step("control_browser", action="inspect", target="youtube")], BASE, "tabs.inspect")
    media = not (ctx.set - {"VIDEO", "PAUSE", "RESUME", "RUN", "PLAY", "SITE:youtube", "TAB", "IT"}
                 - {c for c in ctx.set if c.lower() in SOFT_WORDS})
    if media and (ctx.has("VIDEO") or sites == ["youtube"]):
        if ctx.has("PAUSE"):
            return _plan(ctx, "browser_tab", [step("control_browser", action="pause", target="youtube")], BASE, "media.pause")
        if ctx.has("RESUME", "RUN", "PLAY"):
            return _plan(ctx, "browser_tab", [step("control_browser", action="resume", target="youtube")], BASE, "media.resume")
    if ctx.has("CLOSE") and len(sites) == 1 and not ctx.has("APP:chrome"):
        explained = {"CLOSE", "TAB", "SITE:*", "IT"}
        return _plan(ctx, "browser_tab", [step("control_browser", action="close", target=sites[0])],
                     BASE - _penalty(ctx, explained), "tab.close")
    for pattern in (r"^play (.+?) on youtube$", r"^youtube (?:par|pe|per) (.+?) (?:chala do|chalao|chala|laga do|lagao|play karo)$",
                    r"^یوٹیوب (?:پر|پہ) (.+?) (?:چلا دو|چلاؤ|لگا دو|لگاؤ)$", r"^यूट्यूब (?:पर|पे) (.+?) (?:चला दो|चलाओ|लगा दो|लगाओ)$"):
        m = re.match(pattern, text, re.I)
        if m:
            return _plan(ctx, "play_youtube", [step("play_youtube_video", query=m.group(1).strip())], BASE, "youtube.play")
    m = re.match(r"^search youtube for (.+)$", text, re.I)
    if m:
        return _plan(ctx, "web_search", [step("web_search", query=m.group(1).strip(), site="youtube.com")], BASE, "search.site")
    # Roman Urdu/Urdu/Hindi forms first: "google pe X search karo" must not read as English "google X".
    for pattern in (r"^(?:google (?:pe|par) )?(.+?) (?:search|google) (?:karo|kar do|kro|kijiye)$",
                    r"^(?:گوگل (?:پر|پہ) )?(.+?) سرچ (?:کرو|کر دو|کریں)$",
                    r"^(?:गूगल (?:पर|पे) )?(.+?) सर्च (?:करो|कर दो|कीजिए)$",
                    r"^(?:search for|search|google|look-up) (?:the )?(.+)$"):
        m = re.match(pattern, text, re.I)
        if m and m.group(1).strip():
            return _plan(ctx, "web_search", [step("web_search", query=m.group(1).strip())], BASE, "search")
    return None


def r_website(ctx: _Ctx):
    sites = ctx.prefixed("SITE:")
    url = ctx.url()
    opening = ctx.has("OPEN") or "go" in ctx.set
    if url and opening and not ctx.has("DOWNLOAD"):
        full = url if url.startswith(("http://", "https://")) else "https://" + url
        return _plan(ctx, "open_website", [step("open_url", url=full)], BASE, "website.url")
    if len(sites) == 1 and (opening or ctx.has("RUN")) and not ctx.has("CLOSE"):
        args = {"url": SITE_URLS[sites[0]]}
        if "chrome" in ctx.prefixed("APP:"):
            args["browser"] = "chrome"
        explained = {"OPEN", "RUN", "IN", "SITE:*", "APP:*"}
        return _plan(ctx, "open_website", [step("open_url", **args)], BASE - _penalty(ctx, explained), "website.site")
    return None


def r_simple(ctx: _Ctx):
    if ctx.has("SCREENSHOT"):
        return _plan(ctx, "screenshot", [step("take_screenshot")], BASE - _penalty(ctx, {"SCREENSHOT", "SCREEN"}), "screenshot")
    if ctx.has("TRASH") and not ctx.has("DELETE", "MOVE", "COPY"):
        return _plan(ctx, "list_trash", [step("list_trash")], BASE - _penalty(ctx, {"TRASH", "SHOW", "WHAT", "GET", "IN"}), "trash")
    m = re.match(r"^install (?:package|app) ([A-Za-z0-9][A-Za-z0-9._+-]+\.[A-Za-z0-9._+-]+)$", ctx.norm.text.strip(), re.I)
    if m:  # exact WinGet ID only; anything vaguer is searched first
        return _plan(ctx, "app_install", [step("winget_install", package_id=m.group(1))], BASE, "install.exact")
    if ctx.has("DOWNLOAD", "INSTALL"):
        url = ctx.url()
        if url and url.startswith(("http://", "https://")):
            return _plan(ctx, "download", [step("download_web_content", url=url)], BASE, "download.url")
        packages = ctx.prefixed("PKG:")
        name = packages[0] if packages else ctx.name({"DOWNLOAD", "INSTALL", "FIND", "AND", "APP:*"})
        apps = ctx.prefixed("APP:")
        if not name and apps:
            name = apps[0]
        if name and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 ._+()-]*", name):
            return _plan(ctx, "package_search", [step("application_package", action="search", query=name)], BASE, "package")
        return MatchResult(None, 0.3, "package.non_ascii", ["package name needs transliteration"])
    return None


_FILE_EXT = re.compile(r"\.\w{1,5}$")


def r_paths(ctx: _Ctx):
    path = ctx.path()
    if not path:
        return None
    if ctx.has("WRITE"):
        m = re.match(r"^write (.+?) (?:to|in|into) (\S+)$", ctx.norm.text, re.I)
        if m:
            return _plan(ctx, "write_file", [step("write_text_file", path=m.group(2), content=m.group(1), overwrite=False)],
                         BASE, "path.write")
        m = re.match(r"^(?:overwrite|replace the text of|replace) (\S+) with (.+)$", ctx.norm.text, re.I)
        if m:  # replacing existing content is high risk (server policy) and can be undone from the checkpoint
            return _plan(ctx, "write_file", [step("write_text_file", path=m.group(1), content=m.group(2), overwrite=True)],
                         BASE, "path.overwrite")
        return None
    explained = {"READ", "ZIP", "EXTRACT", "DELETE", "OPEN", "FILE", "FOLDER", "IN", "TO"}
    conf = BASE - _penalty(ctx, explained | {path.casefold()})
    if ctx.has("READ"):
        return _plan(ctx, "read_file", [step("read_text_file", path=path)], conf, "path.read")
    if ctx.has("ZIP"):
        return _plan(ctx, "compress", [step("compress_folder", folder_path=path)], conf, "path.zip")
    if ctx.has("EXTRACT"):
        return _plan(ctx, "extract", [step("extract_file", zip_path=path)], conf, "path.extract")
    if ctx.has("DELETE"):
        return _plan(ctx, "delete", [step("delete_file", path=path, include_contents=ctx.has("CONTENTS"))], conf, "path.delete")
    if ctx.has("OPEN"):
        if _FILE_EXT.search(path):
            return _plan(ctx, "open_file", [step("open_file", path=path)], conf, "path.open_file")
        return _plan(ctx, "open_folder", [step("open_folder", path=path)], conf, "path.open_folder")
    return None


STRUCT = {"ON", "OPEN", "CLOSE", "DELETE", "COPY", "MOVE", "RENAME", "CREATE", "NEW", "NAME", "FOLDER", "FILE", "IN", "TO",
          "SHOW", "FIND", "WHERE", "WHAT", "INCLUDING", "CONTENTS", "IT", "AND", "RUN", "WINDOW", "SEND", "READ"}


def _kind(ctx: _Ctx, name: str) -> str | None:
    if ctx.has("FOLDER"):
        return "folder"
    if ctx.has("FILE") or _FILE_EXT.search(name):
        return "file"
    return None


def r_files(ctx: _Ctx):
    # Work on the first clause only: "delete x, it's approved so don't ask" names x, nothing else.
    canons = [t.canon for t in ctx.all_tokens]
    if "," in canons:
        sub = _Ctx(ctx.norm, ctx.all_tokens[:canons.index(",")], ctx.memory)
        ctx = sub if sub.tokens else ctx
    if ctx.set & NEGATIONS:
        return None
    location = ctx.location()
    if ctx.has("CREATE") and ctx.has("FOLDER"):
        name = ctx.name(STRUCT)
        if not name:
            return _special(ctx, "clarify", "clarify_target", "create.no_name")
        if not location:
            return _special(ctx, "clarify", "clarify_where", "create.no_location")
        return _plan(ctx, "create_folder", [step("create_folder", path=f"{location}/{name}")], BASE, "create")
    if ctx.has("RENAME") or ctx.has("NAME") and not ctx.has("CREATE"):
        for pattern in (r"^rename (?:the )?(?:(?:file|folder) )?(.+?) to (.+)$",
                        r"^(.+?) (?:ka|ki|کا|کی|का|की) (?:naam|نام|नाम) (.+?) (?:kar do|karo|rakh do|rakho|کر دو|رکھ دو|कर दो|रख दो)$"):
            m = re.match(pattern, ctx.norm.text, re.I)
            if m:
                old, new = m.group(1).strip(), m.group(2).strip()
                kind = "folder" if re.search(r"\bfolder\b", m.group(0), re.I) else "file" if _FILE_EXT.search(old) else "folder"
                return _plan(ctx, "rename", [step("find_paths", name=old, kind=kind),
                                             step("rename_file", 0, path="$0", new_name=new)], BASE, "rename")
        return None
    if ctx.has("COPY", "MOVE"):
        op = "copy" if ctx.has("COPY") else "move"
        name = ctx.name(STRUCT)
        kind = _kind(ctx, name)
        if not name or not kind:
            return _special(ctx, "clarify", "clarify_target", f"{op}.no_name")
        if not location:
            return _special(ctx, "clarify", "clarify_where", f"{op}.no_destination")
        return _plan(ctx, op, [step("find_paths", name=name, kind=kind),
                               step(f"{op}_file", 0, source="$0", destination=location)], BASE, op)
    if ctx.has("DELETE"):
        name = ctx.name(STRUCT)
        kind = _kind(ctx, name)
        if not name or not kind:
            return _special(ctx, "clarify", "clarify_target", "delete.no_name")
        return _plan(ctx, "delete", [step("find_paths", name=name, kind=kind),
                                     step("delete_file", 0, path="$0", include_contents=ctx.has("CONTENTS"))], BASE, "delete")
    if ctx.has("OPEN", "RUN") and ctx.has("FOLDER"):
        if location:
            return _plan(ctx, "open_folder", [step("open_folder", path=location)], BASE - _penalty(ctx, STRUCT), "open_folder.place")
        name = ctx.name(STRUCT)
        if not name:
            return _special(ctx, "clarify", "clarify_target", "open_folder.no_name")
        return _plan(ctx, "open_folder", [step("open_folder", path=name)], BASE, "open_folder.name")
    if ctx.has("OPEN") and ctx.has("FILE"):
        name = ctx.name(STRUCT)
        if not name:
            return _special(ctx, "clarify", "clarify_target", "open_file.no_name")
        return _plan(ctx, "open_file", [step("open_file", path=name)], BASE, "open_file")
    if location and (ctx.has("SHOW", "WHAT") or ctx.has("FILE") and ctx.has("IN")):
        return _plan(ctx, "list_folder", [step("list_folder", path=location)], BASE - _penalty(ctx, STRUCT), "list_folder")
    if ctx.has("FIND", "WHERE"):
        name = ctx.name(STRUCT)
        if not name:
            return _special(ctx, "clarify", "clarify_target", "find.no_name")
        return _plan(ctx, "find_files", [step("find_files", name=name)], BASE, "find")
    if ctx.has("OPEN") and location and len(ctx.set - {"OPEN"} - set(LOCATIONS)) == 0:
        return _plan(ctx, "open_folder", [step("open_folder", path=location)], 0.9, "open_folder.bare_place")
    return None


def r_apps(ctx: _Ctx):
    apps = ctx.prefixed("APP:")
    verb = "OPEN" if ctx.has("OPEN", "RUN") else "CLOSE" if ctx.has("CLOSE") else None
    if verb is None:
        return None
    explained = {"OPEN", "RUN", "CLOSE", "WINDOW", "APP:*"}
    if len(apps) == 1:
        conf = BASE - _penalty(ctx, explained)
        if verb == "OPEN":
            return _plan(ctx, "open_app", [step("open_application", app_name=apps[0])], conf, "app.open")
        return _plan(ctx, "close_window", [step("control_desktop", target_window=APP_DISPLAY.get(apps[0], apps[0]),
                                                steps=[{"action": "close_window"}])], conf, "app.close")
    name = ctx.name(STRUCT | {"WINDOW"})
    if not name:
        return None
    if verb == "OPEN":
        # Unknown app name: plausible, but let the LLM (with desktop context) decide.
        return _plan(ctx, "open_app", [step("open_application", app_name=name)], 0.8, "app.open_unknown")
    return _plan(ctx, "close_window", [step("control_desktop", target_window=name, steps=[{"action": "close_window"}])],
                 0.88, "app.close_named")


def r_window(ctx: _Ctx):
    """minimize / maximize / bring to front a named app window."""
    action = {"MINIMIZE": "minimize_window", "MAXIMIZE": "maximize_window", "FOCUS": "focus_window"}
    verb = ctx.first(*action)
    if verb is None:
        return None
    apps = ctx.prefixed("APP:")
    target = APP_DISPLAY.get(apps[0], apps[0]) if len(apps) == 1 else ctx.name(STRUCT | set(action) | {"WINDOW"})
    if not target:
        return _special(ctx, "clarify", "clarify_target", "window.no_target")
    conf = BASE if apps else 0.88
    return _plan(ctx, "window_control", [step("control_desktop", target_window=target, steps=[{"action": action[verb]}])],
                 conf - _penalty(ctx, set(action) | {"WINDOW", "APP:*"}), "window." + action[verb])


def r_clarify(ctx: _Ctx):
    verbs = ctx.set & {"OPEN", "CLOSE", "DELETE", "RUN", "SEND"}
    rest = ctx.set - verbs - {"FILE", "FOLDER", "IT", "EMAIL"} - {c for c in ctx.set if c.lower() in SOFT_WORDS}
    if verbs and not rest:
        return _special(ctx, "clarify", "clarify_target", "clarify.bare_verb")
    return None


RULES = (r_whatsapp, r_unsupported, r_chat, r_email, r_settings_page, r_device, r_followup, r_media, r_browser, r_website,
         r_simple, r_paths, r_files, r_window, r_apps, r_clarify)


def _match_ctx(ctx: _Ctx) -> MatchResult:
    if not ctx.tokens:
        return _special(ctx, "clarify", "clarify_target", "empty")
    for rule in RULES:
        result = rule(ctx)
        if result is not None:
            return result
    return MatchResult(None, 0.0, "no_rule")


def _split_and(tokens: list[Token]) -> list[list[Token]]:
    parts, current = [], []
    for token in tokens:
        if token.canon == "AND":
            parts.append(current)
            current = []
        else:
            current.append(token)
    parts.append(current)
    return parts


def _multi(norm: Normalized, memory: ConversationMemory) -> MatchResult | None:
    parts = _split_and(norm.tokens)
    if not 2 <= len(parts) <= 4 or any(not [t for t in p if t.canon not in FILLER] for p in parts):
        return None
    scratch = ConversationMemory(list(memory.turns))
    steps: list[PlanStep] = []
    confidence = 1.0
    for part in parts:
        result = _match_ctx(_Ctx(norm, part, scratch))
        if result.plan is None or not result.plan.steps or result.confidence < THRESHOLD:
            return None
        offset = len(steps)
        produced_by = {}
        for s in result.plan.steps:
            moved = s.model_copy(deep=True)
            if moved.depends_on is not None:
                moved.depends_on += offset
                moved.args = {k: (f"${int(v[1:]) + offset}" if isinstance(v, str) and re.fullmatch(r"\$\d+", v) else v)
                              for k, v in moved.args.items()}
            steps.append(moved)
        if result.rule.startswith("followup") and offset:
            # "... and open it": depends on the step that produced the target.
            steps[offset].depends_on = offset - 1
        produced_by = {"steps": [s.model_dump() for s in result.plan.steps]}
        scratch.add(Turn(command="", steps=produced_by["steps"], status="completed"))
        confidence = min(confidence, result.confidence)
    plan = NLUPlan(intent="multi", language=norm.language, confidence=confidence, steps=steps,
                   reply=REPLIES.get(norm.language, REPLIES["en"])["ok"])
    return MatchResult(plan, confidence, "multi")


def match(text: str, memory: ConversationMemory | None = None) -> MatchResult:
    """Best local plan for `text`, or confidence 0 when no rule applies."""
    memory = memory or ConversationMemory()
    norm = normalize(text)
    whole = _Ctx(norm, norm.tokens, memory)
    for rule in (r_whatsapp, r_unsupported, r_chat, r_email):
        result = rule(whole)
        if result is not None:
            return result
    if "AND" in whole.set:
        multi = _multi(norm, memory)
        if multi is not None:
            return multi
    return _match_ctx(whole)

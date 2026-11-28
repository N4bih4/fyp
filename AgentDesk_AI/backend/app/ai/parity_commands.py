"""Local parsers for the sentences that still went to the cloud planner in all three languages (docs/STONIC_PARITY_PLAN.md, phase P1).

The coverage matrix (backend/scripts/coverage_live.py --routing) showed these rows with no local parser at all. Each rule here turns one clear,
whole sentence (English, Roman Urdu, Hindi in Devanagari) into a plan for a tool that already exists; the tool still decides the risk and asks
for approval. A rule never fires on a fragment of a longer sentence.

  parity_plan(text)    -> Plan | None       one finished plan
      "what did I delete"            list_trash                    "show desktop"          control_desktop show_desktop
      "switch to chrome"             control_desktop focus_window  "run git status"        run_terminal_command (read-only)
      "message ahmed on whatsapp .." whatsapp_open_chat (draft)    "what is my locker no"  memory_recall
      "find my resume file"          find_files
  parity_intent(text)  -> dict | None       a file workflow that local_agent._resolve turns into a plan (it finds the real path first and asks
                                            when the name is missing or ambiguous): copy, move, rename and read without the words "file"/"folder".

Closing an app ("close notepad") is not here: local_agent already inspects the open windows and asks when the title is not unique.
"""
from __future__ import annotations

import re
import unicodedata

from .base import Plan, PlanAction

NOTE = "Local agent ne plan tayyar kiya; cloud API use nahi hui."
_NUKTA = "़"
_FILE_EXT = re.compile(r"\.\w{1,5}$")
_FILLER = r"(?:(?:please|plz|zara|jara|meri|mera|mere|my|the|मेरी|मेरा|मेरे|ज़रा|जरा|प्लीज़|प्लीज)\s+)*"
_PLACES = {"desktop": "Desktop", "documents": "Documents", "document": "Documents", "downloads": "Downloads", "download": "Downloads",
           "डेस्कटॉप": "Desktop", "डॉक्यूमेंट्स": "Documents", "डॉक्यूमेंट": "Documents", "डाउनलोड्स": "Downloads", "डाउनलोड": "Downloads"}
_PHONE = re.compile(r"\+?[\d\s-]{8,20}")
_WHATSAPP = r"(?:whats\s?app|व्हाट्स\s?[एऐ]प|वॉट्स\s?[एऐ]प|वाट्स\s?[एऐ]प|व्हॉट्स\s?[एऐ]प)"


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFC", str(text or "")).replace(_NUKTA, "")
    text = text.replace("’", "'")
    return " ".join(text.split()).strip(" .!?,;:।۔")


def _plan(tool: str, args: dict) -> Plan:
    return Plan(actions=[PlanAction(tool=tool, args=args)], note=NOTE)


def _place(word: str) -> str:
    """"documents" / "डॉक्यूमेंट्स" -> "Documents"; anything else is kept as typed (local_agent resolves or asks)."""
    return _PLACES.get(_norm(word).casefold(), _norm(word))


# ------------------------------------------------------------------------------------------------ one finished plan
def trash_plan(low: str) -> Plan | None:
    patterns = (
        r"(?:show|list|open|what(?:'s| is) in)\s+(?:me\s+)?(?:what\s+i\s+(?:have\s+)?deleted|(?:my\s+|the\s+)?deleted\s+(?:files|items|stuff)|(?:my\s+|the\s+)?(?:recycle\s+bin|trash))",
        r"what\s+(?:did|have)\s+i\s+(?:delete|deleted)",
        r"jo\s+(?:maine\s+)?delete\s+kiya\s+(?:woh|wo|vo|usse?|wohi)?\s*(?:dikhao|dikha\s+do|batao|dekho)",
        r"(?:deleted\s+(?:files|items)|recycle\s+bin|trash)\s+(?:dikhao|dikha\s+do|kholo|khol\s+do)",
        r"जो\s+(?:मैंने\s+)?डिलीट\s+किया\s+(?:वह|वो|उसे)?\s*(?:दिखाओ|दिखा\s+दो|बताओ|देखो)",
        r"(?:रीसायकल\s+बिन|डिलीट\s+की\s+हुई\s+फाइलें)\s+(?:दिखाओ|दिखा\s+दो|खोलो)",
    )
    return _plan("list_trash", {}) if any(re.fullmatch(_FILLER + p, low) for p in patterns) else None


def git_status_plan(low: str) -> Plan | None:
    if re.fullmatch(r"(?:please\s+)?(?:(?:run|show|check|get|do)\s+)?(?:the\s+)?git\s+status|git\s+status\s+(?:chalao|chala\s+do|dikhao|dikha\s+do|dekho|check\s+karo)|"
                    r"git\s+status\s+(?:चलाओ|चला\s+दो|दिखाओ|दिखा\s+दो|देखो)", low):
        return _plan("run_terminal_command", {"command": "git status"})
    return None


def show_desktop_plan(low: str) -> Plan | None:
    if re.fullmatch(r"(?:please\s+)?(?:(?:show|go\s+to|get\s+to)\s+(?:me\s+)?(?:the\s+|my\s+)?desktop|minimi[sz]e\s+all(?:\s+windows)?|hide\s+all\s+windows)|"
                    r"desktop\s+(?:dikhao|dikha\s+do|par\s+jao|pe\s+jao)|(?:sab|saari|saare)\s+windows?\s+(?:chhoti|choti|minimize)\s+(?:karo|kar\s+do)|"
                    r"डेस्कटॉप\s+(?:दिखाओ|दिखा\s+दो|पर\s+जाओ)|सभी\s+विंडो\s+(?:छोटी|मिनिमाइज)\s+(?:करो|कर\s+दो)", low):
        return _plan("control_desktop", {"steps": [{"action": "show_desktop"}]})
    return None


def _known_apps() -> set[str]:
    from ..tools.apps import APP_ALIASES, APP_TARGETS
    return {name.casefold() for name in set(APP_TARGETS) | set(APP_ALIASES)} | {"whatsapp", "visual studio code"}


def _app_name(raw: str) -> str | None:
    """The canonical name of a KNOWN app ("क्रोम" -> chrome), or None: unknown names are never guessed."""
    from .command_language import TARGET_ALIASES
    aliases = {_norm(k).casefold(): v for k, v in TARGET_ALIASES.items()}
    name = _norm(raw)
    if re.search(r"\b(?:this|that|it|window|tab|screen)\b|यह|इस", name, re.I):
        return None
    name = re.sub(r"^(?:the|my|app|application)\s+|\s+(?:app|application)$", "", name, flags=re.I)
    name = aliases.get(name.casefold(), name).casefold()
    return name if name in _known_apps() else None


def switch_app_plan(low: str) -> Plan | None:
    m = (re.fullmatch(_FILLER + r"(?:switch\s+to|go\s+to|bring\s+up|focus(?:\s+on)?|jump\s+to)\s+(.+)", low)
         or re.fullmatch(r"(.+?)\s+(?:pe|par|per)\s+(?:jao|jaao|chalo|switch\s+karo|switch\s+kar\s+do)", low)
         or re.fullmatch(r"(.+?)\s+(?:पर|पे)\s+(?:जाओ|चलो|स्विच\s+करो|स्विच\s+कर\s+दो)", low))
    app = _app_name(m.group(1)) if m else None
    return _plan("control_desktop", {"target_window": app, "steps": [{"action": "focus_window"}]}) if app else None


def whatsapp_plan(low: str) -> Plan | None:
    """A WhatsApp chat is opened with the text pre-filled; the user presses Send (the tool never sends)."""
    m = (re.fullmatch(rf"(?:send\s+)?(?:a\s+)?(?:message|msg|text)(?:\s+to)?\s+(.+?)\s+(?:on|via|in)\s+{_WHATSAPP}(?:\s+(?:saying|that|:))?\s*(.*)", low, re.I)
         or re.fullmatch(rf"send\s+(?:a\s+)?{_WHATSAPP}\s+(?:message|msg)\s+to\s+(.+?)(?:\s+(?:saying|that|with\s+the\s+text)\s+(.+))?", low, re.I)
         or re.fullmatch(rf"{_WHATSAPP}\s+(?:pe|par|per)\s+(.+?)\s+ko\s+(?:likho|bhejo|bhej\s+do|message\s+karo|msg\s+karo|bolo)(?:\s+(.+))?", low, re.I)
         or re.fullmatch(rf"{_WHATSAPP}\s+(?:पर|पे)\s+(.+?)\s+को\s+(?:लिखो|भेजो|भेज\s+दो|मैसेज\s+करो|संदेश\s+भेजो|बोलो)(?:\s+(.+))?", low, re.I))
    if not m:
        return None
    who = _norm(m.group(1))
    text = _norm(m.group(2) or "")
    if not who or len(who) > 60 or len(text) > 1000 or re.fullmatch(r"(?:him|her|them|someone|somebody|kisi|koi|उसे|किसी)", who, re.I):
        return None
    target = {"phone": re.sub(r"[\s-]", "", who)} if _PHONE.fullmatch(who) else {"contact": who}
    return _plan("whatsapp_open_chat", {**target, "text": text})


# What is my X: only for personal facts. Live questions about the PC or the world are not memory (they have their own tools or the cloud).
_NOT_MEMORY = re.compile(r"\b(?:battery|storage|disk|ram|cpu|memory\s+usage|ip|ip\s+address|location|screen|volume|brightness|wi-?fi|bluetooth|time|date|day|"
                         r"network|speed|status|weather|balance|schedule|version|resolution|username|computer\s+name|pc\s+name|windows|os|processor)\b|"
                         r"बैटरी|वॉल्यूम|ब्राइटनेस|समय|तारीख|मौसम|स्टोरेज", re.I)


def recall_plan(low: str) -> Plan | None:
    if re.fullmatch(r"(?:what\s+(?:do\s+you|did\s+i\s+ask\s+you\s+to)\s+remember(?:\s+about\s+me)?|what(?:'s|\s+is)\s+in\s+(?:my\s+)?memory|"
                    r"show\s+(?:me\s+)?(?:my\s+)?(?:memory|memories|saved\s+notes)|kya\s+yaad\s+hai|tumhe\s+kya\s+yaad\s+hai|"
                    r"तुम्हें\s+क्या\s+याद\s+है|मेरी\s+मेमोरी\s+दिखाओ)", low):
        return _plan("memory_recall", {})
    m = (re.fullmatch(r"what(?:'s|\s+is|\s+was)\s+my\s+(.+)", low)
         or re.fullmatch(r"(?:mera|meri|mere)\s+(.+?)\s+kya\s+(?:hai|tha)", low)
         or re.fullmatch(r"(?:मेरा|मेरी|मेरे)\s+(.+?)\s+क्या\s+(?:है|था)", low))
    if not m:
        return None
    topic = _norm(m.group(1))
    if not topic or len(topic.split()) > 4 or _NOT_MEMORY.search(topic):
        return None
    return _plan("memory_recall", {"topic": topic})


def find_plan(low: str) -> Plan | None:
    m = (re.fullmatch(_FILLER + r"(?:find|look\s+for|locate)\s+" + _FILLER + r"(.+)", low)
         or re.fullmatch(r"where\s+(?:is|are)\s+" + _FILLER + r"(.+)", low)
         or re.fullmatch(_FILLER + r"(.+?)\s+(?:dhundo|dhoondo|dhund\s+do|dhoond\s+do|talash\s+karo|talaash\s+karo|khojo)", low)
         or re.fullmatch(_FILLER + r"(.+?)\s+(?:ढूंढो|ढूँढो|ढूंढ\s+दो|खोजो|खोज\s+दो|तलाश\s+करो)", low))
    if not m:
        return None
    name = _norm(m.group(1))
    name = re.sub(r"\s+(?:file|folder|document|फाइल|फोल्डर)$|^(?:the|my|file|folder|a)\s+", "", name, flags=re.I).strip()
    name = re.sub(r"\s+(?:file|folder|फाइल|फोल्डर)$", "", name, flags=re.I).strip()
    # not a file hunt: an app/package, a web or YouTube search, a person, a question
    if not name or len(name) > 200 or re.match(r"(?:app|apps|application|package|pkg|vlc|on\s+(?:youtube|google|the\s+web))\b|.*\b(?:on|in|par|pe|per)\s+(?:youtube|google|web|internet)$", name, re.I):
        return None
    if re.search(r"\b(?:and|aur|then|phir)\b|और", name):
        return None
    return _plan("find_files", {"name": name})


def gmail_draft_plan(text: str, db=None) -> Plan | None:
    """"draft an email to a@gmail.com asking for help in study" -> open Gmail's compose window filled in (nothing is sent; the user presses Send there)."""
    from ..mail import compose
    from ..orchestration import mail_flow
    start = mail_flow.parse_start(text)
    address, purpose = mail_flow.address_and_purpose(text)
    if start is None or not address or start[1] != address:
        return None
    from ..config import get_settings
    body, why = compose.write_body(purpose, get_settings(), db)
    subject = (purpose[0].upper() + purpose[1:]) if purpose else ""
    note = "Gmail mein draft khol raha hoon; bhejna aap ke haath mein hai." + (" " + why if why else "")
    return Plan(actions=[PlanAction(tool="open_url", args={"url": compose.gmail_compose_url(address, subject, body), "new_tab": True})], note=note)


# Pure websites (an app of the same name would be a different thing, so Discord, Spotify, Zoom, Telegram and WhatsApp are NOT here).
_WEBSITES = {
    "facebook": "facebook.com", "fb": "facebook.com", "instagram": "instagram.com", "insta": "instagram.com", "twitter": "twitter.com",
    "linkedin": "linkedin.com", "snapchat": "snapchat.com", "netflix": "netflix.com", "amazon": "amazon.com", "daraz": "daraz.pk", "olx": "olx.com.pk",
    "google": "google.com", "bing": "bing.com", "yahoo": "yahoo.com", "reddit": "reddit.com", "pinterest": "pinterest.com", "tiktok": "tiktok.com",
    "quora": "quora.com", "medium": "medium.com", "fiverr": "fiverr.com", "upwork": "upwork.com", "udemy": "udemy.com", "coursera": "coursera.org",
    "wikipedia": "wikipedia.org", "kaggle": "kaggle.com", "geeksforgeeks": "geeksforgeeks.org", "w3schools": "w3schools.com",
    "yahoo mail": "mail.yahoo.com", "google maps": "maps.google.com", "maps": "maps.google.com", "google drive": "drive.google.com",
    "google docs": "docs.google.com", "google sheets": "sheets.google.com", "google classroom": "classroom.google.com", "classroom": "classroom.google.com",
    "google meet": "meet.google.com", "youtube music": "music.youtube.com", "twitch": "twitch.tv", "imdb": "imdb.com", "ebay": "ebay.com", "alibaba": "alibaba.com",
    "aliexpress": "aliexpress.com", "booking": "booking.com", "uber": "uber.com", "careem": "careem.com", "ptcl": "ptcl.com.pk", "hec": "hec.gov.pk",
}
# Brands and sites people in Pakistan name aloud ("khaadi", "sapphire", "pakwheels", "riphah"); URLs are the real front pages.
_BRANDS = {
    "khaadi": "https://pk.khaadi.com", "sapphire": "https://pk.sapphireonline.pk", "outfitters": "https://outfitters.com.pk", "gul ahmed": "https://www.gulahmedshop.com",
    "alkaram": "https://www.alkaramstudio.com", "junaid jamshed": "https://www.junaidjamshed.com", "j": "https://www.junaidjamshed.com", "j dot": "https://www.junaidjamshed.com",
    "sana safinaz": "https://www.sanasafinaz.com", "breakout": "https://breakout.com.pk", "bonanza satrangi": "https://www.bonanzasatrangi.com", "nishat": "https://nishatlinen.com",
    "ideas": "https://www.ideas.com.pk", "pakwheels": "https://www.pakwheels.com", "pak wheels": "https://www.pakwheels.com", "zameen": "https://www.zameen.com",
    "foodpanda": "https://www.foodpanda.pk", "food panda": "https://www.foodpanda.pk", "telenor": "https://www.telenor.com.pk", "jazz": "https://jazz.com.pk",
    "ufone": "https://www.ufone.com", "zong": "https://www.zong.com.pk", "hbl": "https://www.hbl.com", "meezan bank": "https://www.meezanbank.com", "ubl": "https://www.ubl.com.pk",
    "easypaisa": "https://www.easypaisa.com.pk", "easy paisa": "https://www.easypaisa.com.pk", "jazzcash": "https://www.jazzcash.com.pk", "jazz cash": "https://www.jazzcash.com.pk",
    "nadra": "https://www.nadra.gov.pk", "riphah": "https://www.riphah.edu.pk", "virtual university": "https://www.vu.edu.pk", "lums": "https://lums.edu.pk",
    "nust": "https://nust.edu.pk", "comsats": "https://www.comsats.edu.pk", "air university": "https://www.au.edu.pk", "k electric": "https://www.ke.com.pk",
    "cricinfo": "https://www.espncricinfo.com", "dawn": "https://www.dawn.com", "geo": "https://www.geo.tv", "ary news": "https://arynews.tv", "express": "https://www.express.pk",
}
_TLDS = {"com", "org", "net", "edu", "gov", "pk", "io", "co", "in", "uk", "us", "info", "biz", "website", "site", "online", "app", "dev", "ai", "xyz", "me", "tv", "shop",
         "store", "tech", "blog", "cloud", "page", "link", "live", "life", "world", "club", "top"}


def website_url(spoken: str) -> str | None:
    """"facebook" -> https://www.facebook.com, "j dot website" -> https://j.website, "daraz.pk" -> https://daraz.pk; None when it is not clearly a website."""
    low = re.sub(r"^(?:the\s+|my\s+)", "", _norm(spoken).casefold())
    low = re.sub(r"\.\s+", " ", low)                                  # speech-to-text writes "j. website": a full stop before a space is not a dot in an address
    for candidate in (low, re.sub(r"\s+(?:website|site|web\s*site)$", "", low)):          # "j dot website": the word website is the ending of the address
        candidate = re.sub(r"^(?:website|site|web\s*site)\s+", "", candidate)
        if candidate in _WEBSITES:
            www = candidate in {"facebook", "fb", "instagram", "insta", "twitter", "linkedin", "netflix", "amazon", "reddit", "pinterest"}
            return ("https://www." if www else "https://") + _WEBSITES[candidate]
        if candidate in _BRANDS or re.fullmatch(r"j(?:(?:\.|\s+dot\s+|\s+)(?:website|site))?", candidate):          # "j.website" / "j dot website" / "j website": Junaid Jamshed's J.
            return _BRANDS[candidate if candidate in _BRANDS else "j"]
        domain = re.sub(r"\s+", "", re.sub(r"\s*\b(?:dot|dott|dat)\b\s*", ".", candidate))
        m = re.fullmatch(r"(?:https?://)?(?:www\.)?([a-z0-9][a-z0-9-]*(?:\.[a-z0-9][a-z0-9-]*)*\.([a-z]{2,24}))(?:/\S*)?", domain)
        if m and m.group(2) in _TLDS:
            return "https://" + m.group(0).removeprefix("https://").removeprefix("http://")
    return None


def nearest_brand(name: str) -> tuple[str, str, bool] | None:
    """(brand, url, sure) for a name that SOUNDS or is spelled like a known site ("khardi" -> khaadi); sure=False for a looser likeness (ask first); None if nothing is close."""
    import difflib
    from ..nlu.phonetic import phonetic_key
    word = re.sub(r"\s+", " ", _norm(name).casefold())
    if not word or len(word) < 3:
        return None
    pool = {**{k: "https://" + ("www." if k in {"facebook", "fb", "instagram", "insta", "twitter", "linkedin", "netflix", "amazon", "reddit", "pinterest"} else "") + v
               for k, v in _WEBSITES.items()}, **_BRANDS}
    def fold(text: str) -> str:
        text = text.replace(" ", "")
        for old, new in (("kh", "k"), ("gh", "g"), ("ph", "f"), ("aa", "a"), ("ee", "i"), ("oo", "u"), ("ck", "k"), ("c", "k"), ("q", "k"), ("w", "v"), ("z", "j")):
            text = text.replace(old, new)
        return re.sub(r"(.)\1+", r"\1", text)

    best, best_score = None, 0.0
    for brand, url in pool.items():
        squashed, target = word.replace(" ", ""), brand.replace(" ", "")
        # a likeness found only after folding sound-alike letters ("cardi" = "khaadi") is never "sure": it is offered through the Approve popup
        score = max(difflib.SequenceMatcher(None, squashed, target).ratio(), min(0.79, difflib.SequenceMatcher(None, fold(squashed), fold(target)).ratio() * 0.97))
        if score >= 0.6 and len(squashed) >= 4 and phonetic_key(squashed) == phonetic_key(target):
            score = max(score, 0.9)                                     # the same sound AND spelled alike: "khadi" / "khaadi" / "kaadi" (not "khari" / "quora")
        if score > best_score:
            best, best_score = (brand, url), score
    if best is None or best_score < 0.62:
        return None
    return best[0], best[1], best_score >= 0.8


_ODD_TLDS = {"website", "site", "online", "xyz", "top", "club", "live", "life", "world", "shop", "store", "tech", "blog", "cloud", "page", "link", "me", "tv"}


def _resolves(host: str, seconds: float = 3.0) -> bool:
    """Does this host name exist in DNS? (3 s at most; only asked for odd endings such as .website, where speech-to-text turns "J. website" into j.website.)"""
    import socket
    import threading
    found: list[bool] = []

    def lookup() -> None:
        try:
            socket.getaddrinfo(host, 443)
            found.append(True)
        except OSError:
            found.append(False)

    worker = threading.Thread(target=lookup, daemon=True)
    worker.start()
    worker.join(seconds)
    return bool(found and found[0])


def website_plan(low: str, original: str = "") -> Plan | None:
    m = re.fullmatch(_FILLER + r"(?:open|visit|go\s+to|launch|browse|kholo|khol\s+do|show)\s+(.+)", low) \
        or re.fullmatch(_FILLER + r"(.+?)\s+(?:kholo|khol\s+do|khol\s+dein|open\s+karo|open\s+kar\s+do|chalao|dikhao|par\s+jao|pe\s+jao)", low) \
        or re.fullmatch(_FILLER + r"(.+?)\s+(?:खोलो|खोल\s+दो|चलाओ)", low)
    if not m:
        return None
    tail = re.sub(r"\s+(?:kholo|khol\s+do|khol\s+dein|open\s+karo|par\s+jao|pe\s+jao)$", "", m.group(1))
    url = website_url(tail)
    if url:
        from urllib.parse import urlsplit
        host = urlsplit(url).hostname or ""
        if host.rsplit(".", 1)[-1] not in _ODD_TLDS or _resolves(host):
            return _plan("open_url", {"url": url})
        tail = host.split(".")[0] + " website"                  # "jay.website" does not exist: it was "jay website", a NAME
        url = website_url(tail)
        if url:
            return _plan("open_url", {"url": url})
    # "open khardi website": the user said WEBSITE, so it is never an app. A known brand that sounds like the name is opened (a looser likeness asks
    # first, through the Approve popup); a name nobody knows becomes a web search for it.
    said_website = re.search(r"\b(?:website|site|web\s*site)\b", tail) is not None
    name = re.sub(r"\s*\b(?:website|site|web\s*site)\b\s*", " ", tail).strip()
    name = re.sub(r"\s+(?:ki|ka|ke|ko|की|का|के|को)$", "", name).strip()            # "cardi ki website": the name is "cardi"
    if said_website and name:
        found = nearest_brand(name)
        if found:
            _, brand_url, sure = found
            plan = _plan("open_url", {"url": brand_url})
            if not sure:
                plan.actions[0].confirm = True
                plan.note = f"'{name}' naam ki website nahi mili; milti-julti: {brand_url}. Approve karein to yahi khulegi."
            return plan
        return _plan("web_search", {"query": f"{name} website"})
    return None


def parity_plan(text: str) -> Plan | None:
    """The first rule that understands the whole sentence, or None."""
    low = _norm(text).casefold()
    if not low or len(low.split()) > 16:
        return None
    for rule in (trash_plan, git_status_plan, show_desktop_plan, switch_app_plan, whatsapp_plan, recall_plan, website_plan, find_plan):
        plan = rule(low)
        if plan is not None:
            return plan
    return None


# ------------------------------------------------------------------------------------------------ how a name was probably meant
# Speech-to-text writes what it HEARD: "FIP folder" for FYP, "dev ops" for DevOps. A short name that matches nothing is retried with the usual
# sound-alike letters; the caller only ever opens/reads such a match (anything that changes a file asks first).
_ACRONYMS = {"fip": "fyp", "fib": "fyp", "fyb": "fyp", "fyip": "fyp", "fep": "fyp", "phyp": "fyp", "fyp": "fyp", "f y p": "fyp", "f i p": "fyp",
             "ef wai pee": "fyp", "ef y p": "fyp", "एफवाईपी": "fyp", "एफआईपी": "fyp",
             "एफ वाई पी": "fyp", "एफ आई पी": "fyp"}
_SOUND_ALIKES = {"i": "y", "y": "i", "b": "p", "p": "b", "v": "w", "w": "v", "d": "t", "t": "d", "k": "q", "q": "k", "e": "a", "a": "e", "s": "z", "z": "s"}


def spoken_variants(name: str) -> list[str]:
    """Other spellings of a name that was probably mis-heard, most likely first ("fip" -> "fyp"); [] for a long or odd name."""
    word = _norm(name).casefold()
    if not word or len(word) > 40:
        return []
    found: list[str] = []
    meant = {_norm(k).casefold(): v for k, v in _ACRONYMS.items()}.get(word)   # keys go through the same clean-up as the heard word
    if meant and meant != word:
        found.append(meant)
    if re.fullmatch(r"[a-z]{2,5}", word):
        for i, letter in enumerate(word):
            swap = _SOUND_ALIKES.get(letter)
            if swap:
                candidate = word[:i] + swap + word[i + 1:]
                if candidate != word and candidate not in found:
                    found.append(candidate)
    return found[:12]


# ------------------------------------------------------------------------------------------------ file workflows for local_agent._resolve
def _kind(noun: str | None, name: str) -> str:
    if noun:
        return "folder" if noun.casefold() in {"folder", "फोल्डर"} else "file"
    return "file" if _FILE_EXT.search(name) else "folder"


def _archive_name(name: str) -> str:
    """"is zip" / "IS dot zip" -> "IS.zip": speech-to-text puts a space where the dot is."""
    return re.sub(r"^(.+?)\s+(?:dot\s+)?zip$", r"\1.zip", name.strip(), flags=re.I)


_DELETE_WORDS = {"delete", "deleted", "deleting", "deletes", "remove", "removed", "removing", "erase", "erased", "dilete", "delet", "delit", "delite", "deleat", "dalete",
                 "delate", "dilit", "dilet", "dileet", "deliit", "rimoov", "rimuv", "remuv", "remov", "rimove", "डिलीट", "डिलिट", "डीलीट", "रिमूव", "रिमूव", "हटाओ", "हटा", "मिटाओ",
                 "ڈیلیٹ", "ڈلیٹ", "ریموو", "ہٹاؤ", "ہٹا", "مٹاؤ", "hatao", "hata", "mitao", "mita", "hatana", "mitana"}


def is_delete_word(word: str) -> bool:
    """True for "delete" / "remove" in any plausible mis-hearing: a listed spelling, or one that looks like it (difflib >= 0.8, 4+ letters)."""
    import difflib
    w = word.casefold().strip(".,!?;:")
    if w in _DELETE_WORDS:
        return True
    if len(w) < 4 or not re.fullmatch(r"[a-z]+", w):
        return False
    # the first letter must agree: "move" is 80% like "remove" and must NEVER be taken for it (move / copy / rename are other commands)
    return max(difflib.SequenceMatcher(None, w, v).ratio() for v in ("delete", "remove", "erase") if v[0] == w[0]) >= 0.8 if w[0] in "dre" else False


_NOT_DELETE = {"move", "moved", "mover", "copy", "open", "close", "create", "make", "show", "list", "read", "rename", "zip", "unzip", "play", "start", "stop", "edit", "cut",
               "date", "let", "lit", "load", "mode", "mood", "made", "meet", "melt", "rest", "run", "new", "add", "find", "go", "switch", "launch", "look", "kholo", "band"}
_DIGIT_WORDS = {"zero": "0", "one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9", "to": "2", "too": "2",
                "for": "4", "ek": "1", "do": "2", "teen": "3", "char": "4", "panch": "5", "chhe": "6", "che": "6", "saat": "7", "aath": "8", "nau": "9"}


def _skeleton(word: str) -> str:
    """The consonants of a word with doubles collapsed: delete -> dlt, delayed -> dld, "rd late" -> rdlt. Whisper keeps these and changes the vowels."""
    s = re.sub(r"[^a-z]", "", word.casefold())
    s = re.sub(r"[aeiouywh]", "", s)
    return re.sub(r"(.)\1+", r"\1", s)


def _distance(a: str, b: str) -> int:
    row = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        prev, row[0] = row[0], i
        for j, cb in enumerate(b, 1):
            prev, row[j] = row[j], min(row[j] + 1, row[j - 1] + 1, prev + (ca != cb))
    return row[-1]


def sounds_like_delete(word: str) -> bool:
    """For a sentence that also names a folder or file: a first word whose consonants are those of "delete" (+/- one) is "delete" ("Delayed folder 123")."""
    w = word.casefold().strip(".,!?;:")
    if w in _NOT_DELETE or not re.fullmatch(r"[a-z]+", w):
        return False
    if w in {"lid", "delayed", "delay", "rdlead", "dilait"}:                 # heard for this user's "delete" (the consonant check alone misses "lid")
        return True
    s = _skeleton(w)
    if len(s) < 2:
        return False
    options = {s} | ({s[1:]} if s.startswith("r") and len(s) > 3 else set())          # "rdlead": a stray r in front
    return any(_distance(o, "dlt") <= 1 for o in options)


def _spoken_digits(name: str) -> str:
    """"one two three" -> "123", "semester six" stays: only a name made of digit words alone (or ending in them after a word) is turned into digits."""
    words = name.split()
    tail = []
    while words and words[-1].casefold() in _DIGIT_WORDS and words[-1].casefold() not in {"to", "too", "for", "do", "char", "che"} | set():
        tail.insert(0, _DIGIT_WORDS[words.pop().casefold()])
    if len(tail) >= 2:                                           # one digit word alone ("six") stays a word: the folder search treats six and 6 alike
        return " ".join(words + ["".join(tail)]) if words else "".join(tail)
    return name


def _delete_parts(raw: str) -> tuple[str, str | None] | None:
    """(name, noun) of "delete the six folder" / "six folder delete karo" / "six folder hata do"; None when it is not a delete sentence."""
    text = re.sub(_FILLER, "", raw, count=1)
    text = re.sub(r"\b(?:foller|foler|folda|folde|fodler|follder|fouldar|foldar|folders)\b", "folder", text, flags=re.I)         # "Six Foller" is "six folder"
    words = text.split()
    has_noun = bool(re.search(r"\b(?:file|folder)\b|फाइल|फोल्डर", text, re.I)) or bool(re.search(r"\.[a-z0-9]{1,5}\b", text))
    name_part = None
    verb_words = 0
    if len(words) >= 2 and (is_delete_word(words[0]) or (has_noun and sounds_like_delete(words[0]))):
        verb_words = 1
    elif len(words) >= 3 and has_noun and len(words[0]) <= 4 and sounds_like_delete(words[0] + words[1]) and words[0].casefold() not in _NOT_DELETE:
        verb_words = 2                                          # "rd late folder", "rred late 123 folder": the verb came out as two words
    if verb_words:
        name_part = " ".join(words[verb_words:])
    else:
        m = re.fullmatch(r"(.+?)\s+(\S+)\s+(?:karo|kar\s+do|kro|kardo|kijiye|kar\s+dein|करो|कर\s+दो|dena|दो)", text)
        if m and is_delete_word(m.group(2)):
            name_part = m.group(1)
        else:
            m = re.fullmatch(r"(.+?)\s+(?:hata\s+do|hata\s+dein|hatao|mita\s+do|mitao|हटा\s+दो|हटाओ|मिटा\s+दो|مٹا\s+دو|ہٹا\s+دو)", text)
            if m:
                name_part = m.group(1)
    if not name_part:
        return None
    particle = r"(?:ko|ka|ke|ki|को|का|के|की|کو|کا|کے|کی)"
    name_part = name_part.strip()
    for _ in range(2):                                         # "karo 123 folder", "the 123 folder ko", "kar do six folder": the filler words are not part of the name
        name_part = re.sub(r"^(?:karo|kar\s+do|kardo|kro|kar\s+dein|dena|do|dein|please|plz|the|this|that|my|aap|ap)\s+", "", name_part, flags=re.I)
        name_part = re.sub(rf"\s+{particle}$", "", name_part, flags=re.I)
    m = re.fullmatch(r"(?:(file|folder|फाइल|फोल्डर)\s+(?:(?:named|called|naam(?:\s+ka)?)\s+)?)?(.+?)(?:\s+(file|folder|फाइल|फोल्डर))?", name_part, re.I)
    if not m:
        return None
    name = re.sub(rf"\s+{particle}$", "", m.group(2).strip(), flags=re.I)
    name = re.sub(r"^(?:named|called|naam(?:\s+ka)?)\s+", "", name, flags=re.I)
    return _spoken_digits(name), (m.group(1) or m.group(3))


_PRONOUN = re.compile(r"(?:it|this|that|these|those|ise|isko|usko|ye|yeh|woh|wo|इसे|इसको|उसे|यह|वह)", re.I)


def is_rename_word(word: str) -> bool:
    """"rename" however Whisper wrote it: re name, renam, rainame, raname, rinem (consonants r-n-m, +/- one)."""
    w = word.casefold().strip(".,!?;:")
    if w in {"rename", "renamed", "renaming", "re-name"}:
        return True
    if len(w) < 4 or not re.fullmatch(r"[a-z]+", w) or w[0] != "r" or w in {"remove", "removed", "rimoov", "remuv"}:
        return False
    return _distance(_skeleton(w), "rnm") <= 1 and _skeleton(w) not in {"rmv", "rm"}


_CLIPPED_RENAME = {"named", "name", "naming", "nayme", "naymed", "naimed", "namd", "ranamed", "reamed", "rainamed", "re-named", "renamed", "reamed"}


def _rename_parts(raw: str) -> tuple[str, str | None, str] | None:
    """(source, noun, new name) of every way of asking for a rename; None when it is not one."""
    text = re.sub(_FILLER, "", raw, count=1)
    text = re.sub(r"\b(?:foller|foler|folda|folde|fodler|follder|fouldar|foldar)\b", "folder", text, flags=re.I)
    words = text.split()
    verb = 0
    if words and is_rename_word(words[0]):
        verb = 1
    elif len(words) >= 2 and words[0].casefold() in {"re", "ri", "ra"} and is_rename_word(words[0] + words[1]):
        verb = 2                                                  # "re name"
    noun = r"(?:file|folder|फाइल|फोल्डर)"
    # Whisper often drops the "re": "named Supervisor folder to Ms. Uzma". With a file/folder and a "to ..." that is still a rename.
    if not verb and words and words[0].casefold().strip(".,") in _CLIPPED_RENAME and re.search(rf"\b{noun}\b.*\s(?:to|as|into)\s+\S", " ".join(words[1:]), re.I):
        verb = 1
    source = new = found_noun = None
    if verb:
        m = re.fullmatch(rf"(?:the\s+)?(?:({noun})\s+)?(.+?)(?:\s+({noun}))?\s+(?:to|as|into|ko)\s+(.+)", " ".join(words[verb:]), re.I)
        if m:
            source, found_noun, new = m.group(2), (m.group(1) or m.group(3)), m.group(4)
    if source is None:
        patterns = (
            rf"change\s+(?:the\s+)?name\s+of\s+(?:the\s+)?(?:({noun})\s+)?(.+?)(?:\s+({noun}))?\s+to\s+(.+)",
            rf"change\s+(?:the\s+)?(?:({noun})\s+)?(.+?)(?:\s+({noun}))?\s+name\s+to\s+(.+)",
            rf"(?:({noun})\s+)?(.+?)(?:\s+({noun}))?\s+(?:ka|ki|ke)\s+(?:naam|name)\s+(?:badal\s+(?:kar|ke)\s+)?(.+?)\s+(?:kar\s+do|karo|kro|kardo|rakh\s+do|rakho|rakh\s+dein|kar\s+dein)",
            rf"(?:({noun})\s+)?(.+?)(?:\s+({noun}))?\s+(?:ko\s+)?(.+?)\s+(?:mein|me|main)\s+rename\s+(?:karo|kar\s+do|kro|kardo)",
            rf"(?:({noun})\s+)?(.+?)(?:\s+({noun}))?\s+(?:ko\s+)?rename\s+(?:karke\s+|kar\s+ke\s+)?(.+?)(?:\s+(?:kar\s+do|karo|kar\s+dein))?",
        )
        for pattern in patterns:
            m = re.fullmatch(pattern, text, re.I)
            if m:
                source, found_noun, new = m.group(2), (m.group(1) or m.group(3)), m.group(4)
                break
    if not source or not new:
        return None
    source = re.sub(rf"\s+(?:ko|ka|ki|ke)$", "", source.strip(), flags=re.I)
    source = re.sub(rf"\s+{noun}$", "", source, flags=re.I).strip()                 # "Fyp folder": the folder is called Fyp
    new = re.sub(r"^(?:ko\s+|naam\s+|name\s+)", "", new.strip().strip('"'), flags=re.I)
    new = re.sub(r"^(?:karo|kar\s+do|kro|kardo)\s+", "", new, flags=re.I)
    new = re.sub(r"\s+(?:kar\s+do|karo|kro|kardo|please)$", "", new, flags=re.I).strip()
    # "FYP 1" for the folder called FYP: the user means FYP1
    merged = re.fullmatch(r"(?i)(\w+)\s+(\d+)", new)
    if merged and re.fullmatch(r"\w+", source) and merged.group(1).casefold() == source.casefold():
        new = merged.group(1) + merged.group(2)
    if not source or _PRONOUN.fullmatch(source) or not new or re.search(r"[\\/:]", new) or len(new) > 120:
        return None
    return source, found_noun, new


# ------------------------------------------------------------------------------------------ "move my IS folder to D drive"
_LETTER_NAMES = {"डब्ल्यू": "W", "क्यू": "Q", "एक्स": "X", "वाई": "Y", "जेड": "Z", "आई": "I", "एफ": "F", "एच": "H", "एल": "L", "एम": "M", "एन": "N", "एस": "S",
                 "ए": "A", "बी": "B", "सी": "C", "डी": "D", "ई": "E", "जी": "G", "जे": "J", "के": "K", "ओ": "O", "पी": "P", "आर": "R", "टी": "T", "यू": "U", "वी": "V"}
_LETTER_TOKENS = sorted(_LETTER_NAMES, key=len, reverse=True)
_SPELLED = {"dee": "D", "di": "D", "dii": "D", "see": "C", "sea": "C", "si": "C", "ef": "F", "eff": "F", "gee": "G", "ee": "E", "aitch": "H"}
_DRIVE_WORD = r"(?:drive|disk|disc|ड्राइव|ड्राईव|डिस्क|ڈرائیو)"
_DRIVE_LETTER = r"(?:[a-z]|dee|dii|di|see|sea|si|eff|ef|gee|ee|aitch|" + "|".join(_LETTER_TOKENS) + r")"
_DRIVE_PHRASES = (
    rf"(?<![\w])(?:local\s+)?{_DRIVE_WORD}\s+(?:letter\s+)?({_DRIVE_LETTER}):?(?![\w])",
    rf"(?<![\w])({_DRIVE_LETTER}):?\s*{_DRIVE_WORD}(?![\w])",
    r"(?<![\w])([a-z]):(?:\\|/)?(?![\w])",
)
_MOVE_VERBS = (r"move|moved|shift|transfer|bhej|bhejo|bhejna|rakh|rakho|daal|dal|dalo|dalna|le\s*jao|le\s*jana|le\s*ja|cut|paste|put|send|मूव|शिफ्ट|ट्रांसफर|भेज|भेजो|रख|रखो|डाल|डालो|ले\s*जाओ|ले\s*जा|कट|पेस्ट")
_COPY_VERBS = r"copy|kopy|backup|कॉपी|कापी|बैकअप"
_LEAD_WORDS = {"please", "plz", "zara", "jara", "meri", "mera", "mere", "my", "the", "this", "that", "ye", "yeh", "woh", "wo", "mujhe", "मेरी", "मेरा", "मेरे", "ज़रा", "जरा", "प्लीज़", "प्लीज",
               "यह", "ये", "वो", "वह", "can", "you", "could", "i", "want", "to", "need", "aap", "tum", "agent", "ko", "को", "se", "से", "ab", "abhi", "अब"}
_TAIL_WORDS = {"in", "into", "to", "on", "at", "inside", "under", "mein", "me", "main", "par", "pe", "per", "ko", "ka", "ki", "ke", "and", "then", "please", "plz", "karo", "kar", "do", "kro",
               "kardo", "kijiye", "dena", "dijiye", "dein", "de", "diya", "kijie", "se", "में", "पर", "पे", "को", "का", "की", "के", "और", "करो", "कर", "दो", "दीजिए", "दीजिये", "करना", "से",
               "andar", "ander", "अंदर", "tak", "तक", "wale", "wala", "wali", "वाला", "वाली", "ya", "या"}
_NOUN_WORDS = {"folder": "folder", "directory": "folder", "फोल्डर": "folder", "फ़ोल्डर": "folder", "file": "file", "फाइल": "file", "फ़ाइल": "file"}


def latin_letters(name: str) -> str:
    """"आईएस" / "आई एस" / "एफवाईपी" -> "IS" / "FYP": a name spelled out letter by letter in Devanagari. Anything else comes back unchanged."""
    text = _norm(name)
    if not text or not re.fullmatch(r"[\u0900-\u097F\s]+", text):
        return name
    compact = re.sub(r"\s+", "", text)
    out = []
    while compact:
        for token in _LETTER_TOKENS:
            if compact.startswith(token):
                out.append(_LETTER_NAMES[token])
                compact = compact[len(token):]
                break
        else:
            return name
    return "".join(out) if len(out) >= 2 else name


def drive_of(text: str) -> tuple[str, str] | None:
    """The drive a sentence names ("D drive", "drive D", "डी ड्राइव", "d:") and the sentence without that phrase; None when it names none."""
    low = " ".join(unicodedata.normalize("NFC", str(text or "")).replace(_NUKTA, "").split()).casefold().rstrip(".!?,;।۔")   # keeps the colon of "D:"
    for pattern in _DRIVE_PHRASES:
        m = re.search(pattern, low)
        if not m:
            continue
        word = m.group(1)
        letter = _LETTER_NAMES.get(word) or _SPELLED.get(word) or (word.upper() if len(word) == 1 else None)
        if letter:
            return letter, _norm(low[:m.start()] + " " + low[m.end():])
    return None


def drive_transfer(text: str) -> dict | None:
    """"mera IS folder D drive mein move kar do", "move uzma to C drive", "आईएस फोल्डर डी ड्राइव में मूव कर दो", "copy NSCT folder to drive E": move/copy something to a drive.
    Returns the intent local_agent._resolve understands (destination = the drive's root), or None when the sentence is not that."""
    found = drive_of(text)
    if not found:
        return None
    letter, rest = found
    verb = None
    for op, pattern in (("copy", _COPY_VERBS), ("move", _MOVE_VERBS)):
        m = re.search(rf"(?<![\w])(?:{pattern})(?![\w])", rest)
        if m:
            verb = op
            rest = _norm(re.sub(rf"(?<![\w])(?:{pattern})(?![\w])", " ", rest))      # "cut X and paste in D drive": every verb word goes
            break
    if verb is None:
        return None
    tokens = rest.split()
    kind = None
    changed = True
    while changed and tokens:
        changed = False
        if tokens[0] in _LEAD_WORDS or (len(tokens) > 1 and tokens[0] in _TAIL_WORDS):
            tokens.pop(0); changed = True
        elif tokens[-1] in _TAIL_WORDS:
            tokens.pop(); changed = True
        elif tokens[-1] in _NOUN_WORDS and len(tokens) > 1:
            kind = _NOUN_WORDS[tokens.pop()]; changed = True
        elif tokens[0] in _NOUN_WORDS and len(tokens) > 1:
            kind = _NOUN_WORDS[tokens.pop(0)]; changed = True
    name = latin_letters(" ".join(tokens))
    if not name or len(tokens) > 6 or _PRONOUN.fullmatch(name) or name.casefold() in _NOUN_WORDS or re.search(r"[\\/:]", name):
        return None
    return {"op": verb, "kind": _kind(kind, name), "source": name, "destination": f"{letter}:\\"}



def parity_intent(text: str) -> dict | None:
    """copy / move / rename / read written without "file"/"folder" -> the intent dict local_agent._resolve understands."""
    raw = re.sub(r"\s*[,;\u060c]\s*", " ", _norm(text))               # "delete, six folder," -> "delete six folder"
    noun = r"(?:(file|folder|फाइल|फोल्डर)\s+)?"
    m = re.fullmatch(_FILLER + rf"(copy|move)\s+(?:the\s+)?{noun}(.+?)\s+(?:to|into|in)\s+(.+)", raw, re.I)
    if m:
        return {"op": m.group(1).casefold(), "kind": _kind(m.group(2), m.group(3)), "source": m.group(3).strip(), "destination": _place(m.group(4))}
    for verb, op in (("copy|kopy", "copy"), ("move|shift|le\\s+jao", "move")):
        m = re.fullmatch(_FILLER + rf"{noun}(.+?)\s+(?:ko\s+)?(.+?)\s+(?:mein|me|main|par|pe|per)\s+(?:{verb})\s+(?:karo|kar\s+do|kro|kardo|kijiye)", raw, re.I)
        if m:
            return {"op": op, "kind": _kind(m.group(1), m.group(2)), "source": m.group(2).strip(), "destination": _place(m.group(3))}
    for verb, op in ((r"कॉपी", "copy"), (r"मूव|ले\s+जाओ|ले\s+जा", "move")):
        m = re.fullmatch(_FILLER + rf"{noun}(.+?)\s+(?:को\s+)?(.+?)\s+(?:में|पर|पे)\s+(?:{verb})(?:\s+(?:करो|कर\s+दो))?", raw, re.I)
        if m:
            return {"op": op, "kind": _kind(m.group(1), m.group(2)), "source": m.group(2).strip(), "destination": _place(m.group(3))}
    renamed = _rename_parts(raw)
    if renamed:
        source, found_noun, new_name = renamed
        return {"op": "rename", "kind": _kind(found_noun, source), "source": source, "new_name": new_name}
    m = (re.fullmatch(_FILLER + rf"rename\s+(?:the\s+)?{noun}(.+?)\s+to\s+(.+)", raw, re.I)
         or re.fullmatch(_FILLER + rf"{noun}(.+?)\s+(?:ka|ki)\s+(?:naam|name)\s+(.+?)\s+(?:karo|kar\s+do|kro|kardo|rakh\s+do|rakho)", raw, re.I)
         or re.fullmatch(_FILLER + rf"{noun}(.+?)\s+(?:का|की)\s+नाम\s+(.+?)\s+(?:करो|कर\s+दो|रखो|रख\s+दो)", raw, re.I))
    if m and not _PRONOUN.fullmatch(m.group(2).strip()):
        new_name = m.group(3).strip().strip('"')
        if new_name and not re.search(r"[\\/:]", new_name):
            return {"op": "rename", "kind": _kind(m.group(1), m.group(2)), "source": m.group(2).strip(), "new_name": new_name}
        return None
    # create: "create semester six folder", "make a folder called lab in documents", "lab folder banao", "documents mein lab folder banao", "लैब फोल्डर बनाओ"
    en = re.fullmatch(_FILLER + r"(?:create|make|new|add)\s+(?:a\s+|an\s+)?(?:new\s+)?(?:folder\s+(?:called\s+|named\s+|with\s+(?:the\s+)?name\s+)?(.+?)|(.+?)\s+folder)"
                              r"(?:\s+(?:in|on|at|inside|under)\s+(.+))?", raw, re.I)
    other = None if en else (re.fullmatch(_FILLER + r"(?:(.+?)\s+(?:mein|me|main|par|pe|per)\s+)?(.+?)\s+(?:naam\s+(?:ka|se)\s+)?folder\s+(?:banao|bana\s+do|bnao|bana\s+dena|bana\s+dein|create\s+karo|create\s+kar\s+do)", raw, re.I)
                             or re.fullmatch(_FILLER + r"(?:(.+?)\s+(?:में|पर)\s+)?(.+?)\s+(?:नाम\s+का\s+)?फोल्डर\s+(?:बनाओ|बना\s+दो|बनाइए)", raw, re.I))
    if en or other:
        if en:
            name, where = (en.group(1) or en.group(2) or ""), (en.group(3) or "")
        else:                                      # Roman Urdu / Hindi: (where) (name) folder banao
            where, name = (other.group(1) or ""), (other.group(2) or "")
        name = re.sub(r"^(?:the|my|a|an|naya|naye|new)\s+", "", _norm(name), flags=re.I).strip()
        if name and not re.search(r"[\\/:]", name) and name.casefold() not in {"folder", "a", "new"} and len(name) <= 80:
            return {"op": "create", "name": name, "destination": _place(where) if where else ""}
        return None
    # delete / remove, however it was heard ("dilete", "delet", "delite", "rimoov", "हटाओ"), the verb before the name or after it
    found = _delete_parts(raw)
    if found is not None:
        name, noun = found
        name = _archive_name(name)
        if name and name.casefold() not in {"file", "folder", "फाइल", "फोल्डर", "do", "dein", "karo", "kar", "kro", "dena", "दो", "करो"} and not _PRONOUN.fullmatch(name) and not re.search(r"\b(?:everything|all|sab|सब)\b", name, re.I):
            kind = "file" if name.casefold().endswith(".zip") else _kind(noun, name)   # a zip is a file even when the user says "folder"
            return {"op": "delete", "kind": kind, "source": name, "include_contents": False}
        return None
    m = (re.fullmatch(_FILLER + rf"(?:read|read\s+out|open\s+and\s+read)\s+(?:the\s+)?{noun}(.+)", raw, re.I)
         or re.fullmatch(_FILLER + rf"{noun}(.+?)\s+(?:ko\s+)?(?:parho|padho|parh\s+do|padh\s+do|parh\s+kar\s+sunao|padh\s+kar\s+sunao)", raw, re.I)
         or re.fullmatch(_FILLER + rf"{noun}(.+?)\s+(?:को\s+)?(?:पढ़ो|पढो|पढ़\s+दो|पढ\s+दो|पढ़कर\s+सुनाओ|पढकर\s+सुनाओ)", raw, re.I))
    if m:
        name = m.group(2).strip()
        if m.group(1) or _FILE_EXT.search(name):          # "read the page" / "read this" is not a file
            if not re.search(r"\b(?:page|tab|screen|this|that|it|email|mail|message)\b", name, re.I):
                return {"op": "read", "kind": "file", "source": name}
    return None

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
_TLDS = {"com", "org", "net", "edu", "gov", "pk", "io", "co", "in", "uk", "us", "info", "biz", "website", "site", "online", "app", "dev", "ai", "xyz", "me", "tv", "shop",
         "store", "tech", "blog", "cloud", "page", "link", "live", "life", "world", "club", "top"}


def website_url(spoken: str) -> str | None:
    """"facebook" -> https://www.facebook.com, "j dot website" -> https://j.website, "daraz.pk" -> https://daraz.pk; None when it is not clearly a website."""
    low = re.sub(r"^(?:the\s+|my\s+)", "", _norm(spoken).casefold())
    for candidate in (low, re.sub(r"\s+(?:website|site|web\s*site)$", "", low)):          # "j dot website": the word website is the ending of the address
        candidate = re.sub(r"^(?:website|site|web\s*site)\s+", "", candidate)
        if candidate in _WEBSITES:
            www = candidate in {"facebook", "fb", "instagram", "insta", "twitter", "linkedin", "netflix", "amazon", "reddit", "pinterest"}
            return ("https://www." if www else "https://") + _WEBSITES[candidate]
        domain = re.sub(r"\s+", "", re.sub(r"\s*\b(?:dot|dott|dat)\b\s*", ".", candidate))
        m = re.fullmatch(r"(?:https?://)?(?:www\.)?([a-z0-9][a-z0-9-]*(?:\.[a-z0-9][a-z0-9-]*)*\.([a-z]{2,24}))(?:/\S*)?", domain)
        if m and m.group(2) in _TLDS:
            return "https://" + m.group(0).removeprefix("https://").removeprefix("http://")
    return None


def website_plan(low: str, original: str = "") -> Plan | None:
    m = re.fullmatch(_FILLER + r"(?:open|visit|go\s+to|launch|browse|kholo|khol\s+do|show)\s+(.+)", low) \
        or re.fullmatch(_FILLER + r"(.+?)\s+(?:kholo|khol\s+do|khol\s+dein|open\s+karo|open\s+kar\s+do|chalao|dikhao|par\s+jao|pe\s+jao)", low) \
        or re.fullmatch(_FILLER + r"(.+?)\s+(?:खोलो|खोल\s+दो|चलाओ)", low)
    if not m:
        return None
    tail = re.sub(r"\s+(?:kholo|khol\s+do|khol\s+dein|open\s+karo|par\s+jao|pe\s+jao)$", "", m.group(1))
    url = website_url(tail)
    return _plan("open_url", {"url": url}) if url else None


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
    m = (re.fullmatch(_FILLER + rf"rename\s+(?:the\s+)?{noun}(.+?)\s+to\s+(.+)", raw, re.I)
         or re.fullmatch(_FILLER + rf"{noun}(.+?)\s+(?:ka|ki)\s+(?:naam|name)\s+(.+?)\s+(?:karo|kar\s+do|kro|kardo|rakh\s+do|rakho)", raw, re.I)
         or re.fullmatch(_FILLER + rf"{noun}(.+?)\s+(?:का|की)\s+नाम\s+(.+?)\s+(?:करो|कर\s+दो|रखो|रख\s+दो)", raw, re.I))
    if m:
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

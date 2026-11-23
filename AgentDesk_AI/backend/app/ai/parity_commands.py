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


def parity_plan(text: str) -> Plan | None:
    """The first rule that understands the whole sentence, or None."""
    low = _norm(text).casefold()
    if not low or len(low.split()) > 16:
        return None
    for rule in (trash_plan, git_status_plan, show_desktop_plan, switch_app_plan, whatsapp_plan, recall_plan, find_plan):
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


_PRONOUN = re.compile(r"(?:it|this|that|these|those|ise|isko|usko|ye|yeh|woh|wo|इसे|इसको|उसे|यह|वह)", re.I)


def parity_intent(text: str) -> dict | None:
    """copy / move / rename / read written without "file"/"folder" -> the intent dict local_agent._resolve understands."""
    raw = _norm(text)
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
    # delete: "delete is zip folder", "delete notes.txt", "report.txt delete karo", "report.txt डिलीट करो" (the noun may come before or after the name)
    m = (re.fullmatch(_FILLER + r"(?:delete[ds]?|deleting|remove[ds]?|removing)\s+(?:the\s+|this\s+|that\s+)?(?:(file|folder)\s+)?(.+?)(?:\s+(file|folder))?", raw, re.I)
         or re.fullmatch(_FILLER + r"(?:(file|folder|फाइल|फोल्डर)\s+)?(.+?)(?:\s+(file|folder|फाइल|फोल्डर))?\s+(?:delete|dilete)\s+(?:karo|kar\s+do|kro|kardo|kijiye)", raw, re.I)
         or re.fullmatch(_FILLER + r"(?:(file|folder|फाइल|फोल्डर)\s+)?(.+?)(?:\s+(file|folder|फाइल|फोल्डर))?\s+डिलीट\s+(?:करो|कर\s+दो)", raw, re.I))
    if m:
        name = _archive_name(m.group(2))
        noun = m.group(1) or m.group(3)
        if name and name.casefold() not in {"file", "folder", "फाइल", "फोल्डर"} and not _PRONOUN.fullmatch(name) and not re.search(r"\b(?:everything|all|sab|सब)\b", name, re.I):
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

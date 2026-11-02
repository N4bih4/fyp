"""Spoken commands for work documents (tools/documents.py): research, plans, notes from files, and the answer to the one clarifying question.

"Research solar energy and make me a file" / "write a report on climate change" / "make a study plan for my exams" / "summarise the 3 PDFs in Downloads into notes".
Words about size (short, brief, detailed), language (in Urdu, Roman Urdu, Hindi, English) and format (as PDF, as markdown) are taken out of the topic.
"""
from __future__ import annotations

import re
import unicodedata

from .base import Plan, PlanAction

_NUMBERS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8}
ASKED = "is a wide subject. How detailed should it be"          # the start of tools/documents.question_for(): how a follow-up recognises the question
_DEPTH = [(r"\b(?:brief(?:ly)?|short|quick|one[- ]page)\b", "brief"), (r"\b(?:detailed|long|in detail|in depth|thorough|comprehensive)\b", "detailed"), (r"\bstandard\b", "standard")]
_LANG = [(r"\b(?:in )?roman urdu\b", "roman"), (r"\b(?:in )?urdu\b", "ur"), (r"\b(?:in )?hindi\b", "hi"), (r"\b(?:in )?english\b", "en")]
_FORMAT = [(r"\b(?:as |in )?(?:a )?pdf\b", "pdf"), (r"\b(?:as |in )?(?:markdown|md)\b", "md"), (r"\b(?:as |in )?(?:a )?(?:word|docx)(?: file| document)?\b", "docx")]


def _norm(raw: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", raw).strip().rstrip(".!?۔।"))


def _take(text: str, table) -> tuple[str, str | None]:
    found = None
    for pattern, value in table:
        if re.search(pattern, text, re.I):
            found = found or value
            text = re.sub(pattern, " ", text, flags=re.I)
    return re.sub(r"\s+", " ", text).strip(" ,"), found


def _args(kind: str, topic: str, whole: str, **extra) -> dict:
    topic, depth = _take(topic, _DEPTH)
    topic, lang = _take(topic, _LANG)
    topic, fmt = _take(topic, _FORMAT)
    _, depth2 = _take(whole, _DEPTH)                                  # "a detailed report on X": the word may sit outside the topic
    _, lang2 = _take(whole, _LANG)
    _, fmt2 = _take(whole, _FORMAT)
    if kind == "notes" and not re.search(r"(?:as|in|into|to) (?:a )?(?:pdf|markdown|md|word|docx)", whole):
        fmt = fmt2 = None                                              # "report.pdf" names a file; it is not the wanted format
    topic = re.sub(r"^(?:the |a |an )", "", topic).strip(" ,")
    args: dict = {"kind": kind, "topic": topic[:300], **extra}
    for key, value in (("depth", depth or depth2), ("language", lang or lang2), ("format", fmt or fmt2)):
        if value:
            args[key] = value
    return args


def _plan(args: dict) -> Plan:
    return Plan(actions=[PlanAction(tool="make_document", args=args)])


def document_plan(raw: str) -> Plan | None:
    text = _norm(raw)
    low = text.casefold()
    deliverable = r"(?:file|document|doc|report|notes?|summary|essay|pdf|word file)"
    # ---- notes from files
    m = re.fullmatch(r"(?:please )?(?:summari[sz]e|make notes (?:from|of)|turn) (?:these |the |my |those )?(\d+|one|two|three|four|five|six|seven|eight)? ?(?:latest |newest |recent )?(pdfs?|documents?|files|word files)"
                     r"(?: (?:in|from) (?:my |the )?([\w ]{2,40}?)(?: folder)?)?(?: into| as| to)? ?(?:notes|a summary|summary)?", low)
    if m and (m.group(3) or m.group(1)) and ("note" in low or "summari" in low):
        count = m.group(1)
        count = int(count) if count and count.isdigit() else _NUMBERS.get(count or "", 3)
        return _plan(_args("notes", f"Notes from {m.group(2)}", low, folder=(m.group(3) or "Documents").strip(), count=min(count, 8)))
    m = re.fullmatch(r"(?:please )?(?:summari[sz]e|make notes (?:from|of)) (.+?\.(?:pdf|docx|txt|md))(?: and (.+?\.(?:pdf|docx|txt|md)))*(?: into| as)? ?(?:notes)?", text, re.I)
    if m:
        files = re.findall(r"[\w \-().]+?\.(?:pdf|docx|txt|md)", re.sub(r"^(?:please )?(?:summari[sz]e|make notes (?:from|of)) ", "", text, flags=re.I).replace(" and ", ",").replace(" into notes", "").replace(" as notes", ""), re.I)
        files = [f.strip(" ,") for f in files if f.strip(" ,")]
        if files:
            return _plan(_args("notes", "Notes", low, files=files[:8]))
    # ---- a plan
    m = re.fullmatch(r"(?:please )?(?:make|create|prepare|write|give|draw up) (?:me )?(?:a |an )?((?:detailed |short |brief )?(?:study |revision |exam |weekly |daily |work |project |workout |fitness )?plan) (?:for|to|of) (.+)", text, re.I)
    if m:
        return _plan(_args("plan", f"{m.group(1)} for {m.group(2)}".strip(), low))
    m = re.fullmatch(r"(.+?) (?:ka|ki|ke liye) (?:study |revision )?plan (?:banao|bana do|banado|likho)", low)
    if m:
        return _plan(_args("plan", f"study plan for {m.group(1)}", low, language="roman"))
    # ---- research
    m = re.fullmatch(rf"(?:please )?research (.+?) and (?:make|write|create|prepare|give|put together) (?:me )?(?:a |an )?(?:\w+ )?{deliverable}(?: (?:on|about) (?:it|that|this))?(?: .*)?", text, re.I)
    if m:
        return _plan(_args("research", m.group(1), low))
    m = re.fullmatch(rf"(?:please )?(?:write|make|prepare|create|give me|put together) (?:me )?(?:a |an )?(?:\w+ )?{deliverable} (?:on|about) (.+)", text, re.I)
    if m:
        return _plan(_args("research", m.group(1), low))
    m = re.fullmatch(r"(.+?) (?:par|pe|ke bare mein) (?:research karke |tahqeeq karke )?(?:file|report|document|notes?) (?:bana do|banao|likho|banado)", low)
    if m:
        return _plan(_args("research", m.group(1), low, language="roman"))
    return None


def document_followup(raw: str, recent) -> Plan | None:
    """The answer to "How detailed should it be, and in which language?": 'standard, in English', 'brief', 'detailed in Urdu', 'short'."""
    if recent is None or ASKED not in str(getattr(recent, "plan_note", "") or ""):
        return None
    text = _norm(raw).casefold()
    text, depth = _take(text, _DEPTH)
    text, lang = _take(text, _LANG)
    text, fmt = _take(text, _FORMAT)
    leftover = re.sub(r"\b(?:please|and|in|it|make|the|a|an|file|document|ok|okay|yes|with|should|be|to)\b|[,.]", " ", text).strip()
    if not (depth or lang) or len(leftover.split()) > 2:
        return None
    base = document_plan(recent.command)
    if base is None:
        return None
    args = dict(base.actions[0].args)
    args.update({k: v for k, v in (("depth", depth or args.get("depth") or "standard"), ("language", lang or args.get("language") or "en"), ("format", fmt or args.get("format"))) if v})
    args["confirmed"] = True
    return _plan(args)

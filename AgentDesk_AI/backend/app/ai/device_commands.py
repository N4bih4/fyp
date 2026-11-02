"""Spoken commands for the whole PC (tools/device.py) and the File Explorer window (tools/explorer_view.py).

Each pattern needs the thing it acts on ("the pc", "airplane mode", "night light", "battery", "hidden files") so it can never be confused with an app
command; "sort by date" works on the Explorer window in front (the tool says so when none is open). English, Roman Urdu, Urdu and Hindi.
"""
from __future__ import annotations

import re
import unicodedata

from .base import Plan, PlanAction

_PC = r"(?:the |my |mera |mere |apna |اپنا |میرا |मेरा |अपना )?(?:pc|p\.c\.|computer|laptop|system|پی ?سی|کمپیوٹر|لیپ ?ٹاپ|पीसी|कंप्यूटर|लैपटॉप)"
_ON = r"(on|off|karo|band|chalu|start|بند|آن|آف|चालू|बंद)"


def _norm(raw: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[,!?۔।]", " ", unicodedata.normalize("NFKC", raw).casefold())).strip().rstrip(".")


def _device(action, **args) -> Plan:
    return Plan(actions=[PlanAction(tool="device_control", args={"action": action, **args})])


def _explorer(action, **args) -> Plan:
    return Plan(actions=[PlanAction(tool="explorer_view", args={"action": action, **args})])


def _is_on(word: str) -> bool:
    return word in ("on", "karo", "chalu", "start", "آن", "चालू") or word.startswith("on")


def device_plan(raw: str) -> Plan | None:
    t = _norm(raw)
    # ---- power
    if re.fullmatch(rf"(?:please )?lock {_PC}(?: screen)?|lock (?:the )?screen|{_PC} (?:ko )?lock (?:karo|kar do|kardo)|screen lock (?:karo|kar do)|لاک (?:کرو|کر دو)|{_PC} لاک (?:کرو|کر دو)|लॉक करो|{_PC} लॉक कर दो", t):
        return _device("lock")
    if re.fullmatch(rf"(?:please )?(?:put |send )?{_PC} (?:to )?sleep|(?:put |send )?{_PC} (?:in)?to sleep(?: mode)?|sleep mode|{_PC} (?:ko )?(?:sula do|sleep (?:karo|kar do))|go to sleep mode", t):
        return _device("sleep")
    if re.fullmatch(rf"(?:please )?(?:restart|reboot) {_PC}|{_PC} (?:ko )?(?:restart|reboot) (?:karo|kar do)|{_PC} (?:ko )?dobara start (?:karo|kar do)|restart {_PC} now|ری ?اسٹارٹ کرو|रीस्टार्ट करो", t):
        return _device("restart")
    if re.fullmatch(rf"(?:please )?(?:shut ?down|power off|turn off|switch off) {_PC}|shut ?down|{_PC} (?:ko )?(?:shut ?down|band|off) (?:karo|kar do|kardo)|{_PC} band kar do|{_PC} بند کر دو|{_PC} बंद कर दो|{_PC} off kar do", t):
        return _device("shutdown")
    if re.fullmatch(r"(?:cancel|abort|stop|undo) (?:the |my )?(?:shut ?down|restart|reboot|power ?off)|(?:shut ?down|restart) (?:cancel|band) (?:karo|kar do)|shutdown (?:cancel|rok) (?:karo|do)", t):
        return _device("cancel_shutdown")
    m = re.fullmatch(rf"(?:please )?keep {_PC} awake(?: for (\d{{1,3}}) ?(minutes?|mins?|hours?|hrs?))?|(?:do not|don't|dont) let (?:it|{_PC}) sleep(?: for (\d{{1,3}}) ?(minutes?|mins?|hours?|hrs?))?|"
                     rf"(\d{{1,3}}) ?(minutes?|mins?|minute|hours?|ghante|ghanta) (?:tak )?{_PC} (?:ko )?(?:jagaye rakho|jagta rakho|awake rakho)", t)
    if m:
        groups = [g for g in m.groups() if g]
        number, unit = (int(groups[0]), groups[1]) if len(groups) >= 2 else (60, "minutes")
        minutes = number * (60 if unit.startswith(("hour", "hr", "ghant")) else 1)
        return _device("keep_awake", minutes=max(1, min(720, minutes)))
    if re.fullmatch(rf"stop keeping {_PC} awake|let {_PC} sleep again|{_PC} ko sone do|keep awake (?:off|stop)", t):
        return _device("stop_keep_awake")
    if re.fullmatch(r"(?:how much )?battery(?: is left| left| status| percentage| level)?|what(?:'s| is) (?:my )?battery(?: level| percentage)?|is (?:my )?(?:laptop|pc) charging|battery (?:kitni|kitna) (?:reh gayi|bachi|bacha) hai|battery ka status batao|battery kitne percent hai|بیٹری کتنی رہ گئی ہے|बैटरी कितनी बची है", t):
        return _device("battery")
    # ---- modes
    m = re.fullmatch(rf"(?:turn|switch|put) (on|off) (?:the )?(?:airplane|aeroplane|flight) mode|(?:airplane|aeroplane|flight) mode {_ON}(?: karo| kar do)?|(?:airplane|aeroplane|flight) mode (?:ko )?{_ON} (?:karo|kar do)", t)
    if m:
        word = next(g for g in m.groups() if g)
        return _device("airplane_on" if _is_on(word) else "airplane_off")
    if re.fullmatch(r"is (?:the )?(?:airplane|aeroplane|flight) mode on|(?:airplane|aeroplane|flight) mode status", t):
        return _device("airplane_status")
    m = re.fullmatch(rf"(?:turn|switch|put) (on|off) (?:the )?(?:do not disturb|dnd|focus mode)|(?:do not disturb|dnd) {_ON}(?: karo| kar do)?|(?:do not disturb|dnd) (?:ko )?{_ON} (?:karo|kar do)", t)
    if m:
        word = next(g for g in m.groups() if g)
        return _device("dnd_on" if _is_on(word) else "dnd_off")
    if re.fullmatch(r"is (?:do not disturb|dnd) on|(?:do not disturb|dnd) status", t):
        return _device("dnd_status")
    m = re.fullmatch(rf"(?:turn|switch|put) (on|off) (?:the )?night ?light|night ?light {_ON}(?: karo| kar do)?|night ?light (?:ko )?{_ON} (?:karo|kar do)", t)
    if m:
        word = next(g for g in m.groups() if g)
        return _device("nightlight_on" if _is_on(word) else "nightlight_off")
    if re.fullmatch(r"is (?:the )?night ?light on|night ?light status", t):
        return _device("nightlight_status")
    # ---- File Explorer, the window in front
    m = re.fullmatch(r"sort(?: (?:the )?(?:files|folder|list))? by (name|date|size|type)(?: (descending|newest first|largest first|reverse|z to a))?|"
                     r"(name|date|size|type) (?:ke hisab se|se) sort (?:karo|kar do)", t)
    if m:
        by = m.group(1) or m.group(3)
        desc = bool(m.group(2)) and m.group(2) != "ascending"
        return _explorer("sort", by=by, descending=desc or (by in ("date", "size") and bool(m.group(2))))
    m = re.fullmatch(r"(?:show|view|switch to|change (?:the )?view to) (?:files |them |it )?(?:as |in )?(details|list|icons|small icons|large icons|tiles)(?: view)?", t)
    if m:
        return _explorer("view", mode=m.group(1).replace(" ", "_"))
    if re.fullmatch(r"show (?:the )?hidden (?:files|items|folders)|hidden files (?:dikhao|show karo)|chhupi hui files dikhao", t):
        return _explorer("hidden", show=True)
    if re.fullmatch(r"hide (?:the )?hidden (?:files|items|folders)|hidden files (?:chhupao|hide karo)", t):
        return _explorer("hidden", show=False)
    p = re.fullmatch(r"(?:show |open )?properties of ([A-Za-z]:\\[^\"<>|]{2,300})", re.sub(r"\s+", " ", raw.strip().rstrip(".")))
    if p:
        return _explorer("properties", path=p.group(1).strip())
    m = re.fullmatch(r"search (?:this folder|here|file explorer|this pc) for (.{2,100})|find (.{2,100}) in this folder", t)
    if m:
        return _explorer("search", query=(m.group(1) or m.group(2)).strip())
    return None

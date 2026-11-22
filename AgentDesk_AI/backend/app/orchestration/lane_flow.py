"""The conversation inside a lane: what a sentence means when the user is already "in" File Explorer, coming back to it, or answering its question.

Called from `executor._start_task` right after the session words ("stop", "bas", "end task") and before the normal parsers:
  * a question the lane asked is open ("same window or a new one?", "which folder: A or B?") -> this sentence is its answer;
  * "back to Explorer" / "explorer pe wapas" -> the lane is resumed after one question (the user may want a NEW window instead);
  * the current lane is File Explorer and the sentence is a navigation ("C drive", "Users", "peeche jao") -> `explorer_navigate` in THE LANE'S window.
Anything else returns None and the normal flow runs. Only File Explorer lanes have navigation so far; other kinds only keep their state (lanes.py).
"""
from __future__ import annotations

import json
import os
import re

from sqlalchemy.orm import Session

from ..ai.base import Plan, PlanAction
from ..config import Settings
from ..models import Task, TaskStatus, utcnow
from ..nlu.normalizer import detect_language
from ..tools.registry import ToolRegistry
from . import lane_commands, lanes

SAYS: dict[str, dict[str, str]] = {
    "resume_ask": {"en": "Go back to the File Explorer window you were in ({folder}), or open a new one?",
                   "roman_ur": "Pehli wali File Explorer window ({folder}) mein wapas jaun, ya nayi kholun?",
                   "ur": "پہلی والی فائل ایکسپلورر ونڈو ({folder}) میں واپس جاؤں، یا نئی کھولوں؟",
                   "hi": "पहले वाली फ़ाइल एक्सप्लोरर विंडो ({folder}) में वापस जाऊँ, या नई खोलूँ?"},
    "resume_yes": {"en": "Okay, back in File Explorer: {folder}. What next?", "roman_ur": "Theek hai, File Explorer mein wapas: {folder}. Aage kya?",
                   "ur": "ٹھیک ہے، فائل ایکسپلورر میں واپس: {folder}۔ آگے کیا؟", "hi": "ठीक है, फ़ाइल एक्सप्लोरर में वापस: {folder}। आगे क्या?"},
    "resume_new": {"en": "Okay, a new File Explorer window. Which folder?", "roman_ur": "Theek hai, nayi File Explorer window. Kaun sa folder?",
                   "ur": "ٹھیک ہے، نئی فائل ایکسپلورر ونڈو۔ کون سا فولڈر؟", "hi": "ठीक है, नई फ़ाइल एक्सप्लोरर विंडो। कौन सा फ़ोल्डर?"},
    "resume_gone": {"en": "That File Explorer conversation has ended (it was idle for 20 minutes). Say 'open File Explorer' to start again.",
                    "roman_ur": "Woh File Explorer wali baat cheet khatam ho chuki hai (20 minute se zyada khamoshi). 'File Explorer kholo' bol kar dobara shuru karein.",
                    "ur": "وہ فائل ایکسپلورر والی بات چیت ختم ہو چکی ہے۔ 'فائل ایکسپلورر کھولو' بول کر دوبارہ شروع کریں۔",
                    "hi": "वह फ़ाइल एक्सप्लोरर वाली बातचीत खत्म हो चुकी है। 'फ़ाइल एक्सप्लोरर खोलो' बोलकर फिर शुरू करें।"},
    "window_closed": {"en": "That File Explorer window was closed, so I'll open a new one.", "roman_ur": "Woh File Explorer window band ho chuki thi, nayi khol raha hoon.",
                      "ur": "وہ فائل ایکسپلورر ونڈو بند ہو چکی تھی، نئی کھول رہا ہوں۔", "hi": "वह फ़ाइल एक्सप्लोरर विंडो बंद हो चुकी थी, नई खोल रहा हूँ।"},
    "choose_ask": {"en": "Which one: {names}?", "roman_ur": "Kaun sa: {names}?", "ur": "کون سا: {names}؟", "hi": "कौन सा: {names}?"},
}
RESUME = re.compile(r"(?:\b(?:back to|go back to|return to|switch back to|wapas|phir se|dobara)\s+(?:the\s+)?(?:file\s+)?explorer\b|"
                    r"\bexplorer\s+(?:pe|par|mein|me)\s+(?:wapas|phir|dobara)(?:\s+jao)?\b|एक्सप्लोरर\s+(?:पर|में)\s+वापस|ایکسپلورر\s+(?:پر|میں)\s+واپس)", re.I)
OPEN_EXPLORER = re.compile(r"^(?:please\s+)?(?:(?:open|launch|start|kholo|khol\s+do|chalao)\s+)?(?:(?P<new>(?:a\s+)?(?:new|naya|nayi|nai|doosra|doosri)\s+)?(?:file\s+)?explorer(?:\s+window)?)(?:\s+(?:open|kholo|khol\s+do|karo|kar\s+do|chalao))*$", re.I)
YES = {"yes", "yeah", "yep", "same", "same one", "same window", "haan", "han", "ji", "ji haan", "wahi", "wohi", "usi mein", "isi mein", "pehli wali", "ok", "okay", "sure",
       "हाँ", "हां", "वही", "ہاں", "جی", "وہی"}
NEW = {"no", "nope", "new", "a new one", "new window", "nahi", "nahin", "naya", "nayi", "nai", "nayi window", "naya window", "doosri", "नहीं", "नई", "नया", "نہیں", "نئی", "نیا"}


def _lang(text: str) -> str:
    lang = detect_language(text)
    if lang == "en":
        from ..voice.langdetect import detect
        lang = "roman_ur" if detect(text) == "roman" else "en"
    return lang


def _say(key: str, lang: str, **slots: str) -> str:
    from ..voice.reply_script import reply_lang
    table = SAYS[key]
    return table.get(reply_lang(lang), table["en"]).format(**slots)


def _done(db: Session, task: Task, text: str) -> Task:
    """A reply that is only words (like session_commands): a finished task with no actions; the session is not told about it."""
    task.agent_state_json = json.dumps({"provider": "local", "matcher": "session"})
    task.plan_note, task.status, task.error = text, TaskStatus.COMPLETED, None
    task.updated_at = utcnow()
    db.commit()
    db.refresh(task)
    return task


def _run(db: Session, task: Task, plan: Plan, registry: ToolRegistry, settings: Settings, auto_approve: bool) -> Task:
    from . import executor
    task.agent_state_json = json.dumps({"provider": "local", "matcher": "lane"})
    task = executor.plan_task(db, task, registry, settings, auto_approve=auto_approve, preplanned=plan)
    if task.status == TaskStatus.APPROVED:
        return executor.run_task(db, task.id, registry, settings)
    return task


def _navigate_plan(path: str, hwnd: int | None, new_window: bool = False) -> Plan:
    args: dict = {"path": path}
    if hwnd:
        args["window"] = int(hwnd)
    if new_window:
        args["new_window"] = True
    return Plan(actions=[PlanAction(tool="explorer_navigate", args=args)], note="Lane: same File Explorer window.")


def _norm(text: str) -> str:
    return re.sub(r"[\s.,;:!?،۔।؟…\"'`]+", " ", (text or "").casefold()).strip()


def try_handle(db: Session, task: Task, command: str, registry: ToolRegistry, settings: Settings, auto_approve: bool = False) -> Task | None:
    state = lanes.load(db)
    if not state.lanes:
        return None
    said = _norm(command)
    lang = _lang(command)

    # 1) a question this lane asked is waiting for its answer
    waiting = next((lane for lane in state.lanes.values() if lane.pending and lane.pending.get("type") in ("resume", "choose")), None)
    if waiting is not None:
        kind = waiting.pending.get("type")
        if kind == "resume":
            if said in {_norm(w) for w in YES}:
                waiting.pending = None
                if lanes.window_gone(waiting):
                    waiting.hwnd = None
                    state.current = waiting.key
                    lanes.save(db, state)
                    return _done(db, task, _say("window_closed", lang))
                try:
                    from ..tools.explorer_view import get_explorer
                    if waiting.hwnd:
                        get_explorer().focus(waiting.hwnd)
                except Exception:  # noqa: BLE001 - bringing the window to the front is a courtesy
                    pass
                waiting.last_active = lanes._now().isoformat()
                state.current = waiting.key
                lanes.save(db, state)
                return _done(db, task, _say("resume_yes", lang, folder=waiting.folder or ""))
            if said in {_norm(w) for w in NEW}:
                waiting.pending, waiting.hwnd = None, None
                waiting.last_active = lanes._now().isoformat()
                state.current = waiting.key
                lanes.save(db, state)
                return _done(db, task, _say("resume_new", lang))
            waiting.pending = None                      # something else was said: the question is dropped, the sentence is a normal command
            lanes.save(db, state)
            return None
        if kind == "choose":
            paths = list(waiting.pending.get("paths") or [])
            chosen = lane_commands.pick_from(paths, command)
            waiting.pending = None
            lanes.save(db, state)
            if chosen:
                return _run(db, task, _navigate_plan(chosen, waiting.hwnd), registry, settings, auto_approve)
            return None

    # 2) "back to Explorer"
    if RESUME.search(command or "") and len(said.split()) <= 7:
        lane = lanes.lane_of_kind(state, "explorer")
        if lane is None:
            return _done(db, task, _say("resume_gone", lang))
        if state.current == lane.key:                   # already there: nothing to ask
            lane.last_active = lanes._now().isoformat()
            lanes.save(db, state)
            return _done(db, task, _say("resume_yes", lang, folder=lane.folder or ""))
        lane.pending = {"type": "resume"}
        lanes.save(db, state)
        return _done(db, task, _say("resume_ask", lang, folder=lane.folder or "File Explorer"))

    # 2b) "open File Explorer": the open window is brought forward; only "NEW File Explorer window" makes another one
    wants = OPEN_EXPLORER.match(said)
    if wants:
        lane = lanes.lane_of_kind(state, "explorer")
        new = bool(wants.group("new"))
        if lane is not None and (new or (lane.hwnd and not lanes.window_gone(lane))):
            if new:
                lane.hwnd = None                         # the next navigation opens a fresh window, which the lane then keeps
                lane.last_active = lanes._now().isoformat()
                state.current = lane.key
                lanes.save(db, state)
                return _run(db, task, _navigate_plan(lane.folder or os.path.expanduser("~"), None, new_window=True), registry, settings, auto_approve)
            try:
                from ..tools.explorer_view import get_explorer
                get_explorer().focus(lane.hwnd)
            except Exception:  # noqa: BLE001
                pass
            lane.last_active = lanes._now().isoformat()
            state.current = lane.key
            lanes.save(db, state)
            return _done(db, task, _say("resume_yes", lang, folder=lane.folder or ""))

    # 3) navigation inside the current Explorer lane
    lane = lanes.current_lane(db, state)
    if lane is not None and lane.kind == "explorer":
        found = lane_commands.explorer_navigation(command, lane.folder)
        if found is None:
            return None
        verb, value = found
        if verb == "ask":
            lane.pending = {"type": "choose", "paths": value}
            lanes.save(db, state)
            names = ", ".join(p.rsplit("\\", 1)[-1] for p in value)
            return _done(db, task, _say("choose_ask", lang, names=names))
        hwnd = lane.hwnd
        if hwnd and lanes.window_gone(lane):
            hwnd = None
        return _run(db, task, _navigate_plan(value, hwnd), registry, settings, auto_approve)
    return None

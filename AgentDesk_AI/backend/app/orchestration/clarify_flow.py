"""Ask-first (Phase 2 of docs/VOICE_AUTOMATION_PLAN.md): a request that does not say WHICH app to use is answered with a question, never a guess.

Handled here, before any parser or planner:
  * "open a browser" / "browser kholo"  -> "Which browser: Chrome, Edge or Firefox?" (the browsers really installed), then "Which profile?" when that browser has several;
  * "open email" / "mail kholo"          -> "Gmail, Outlook app or Outlook on the web?" (only what exists on this PC);
  * the answer to such a question: by name, number or ordinal, or with "always ..." ("hamesha Chrome") to keep it;
  * "always use Chrome" / "har baar poochho": the standing choice is set or cleared (the default is to ask every time).
A website, a search or a video opened WITHOUT a named browser is guarded in the tools themselves (tools/browser_choice.py), so this also holds for the cloud agent.
The open question lives in a lane of kind "clarify" so it survives a restart and times out with the other lanes.
"""
from __future__ import annotations

import json
import re

from sqlalchemy.orm import Session

from ..ai.base import Plan, PlanAction
from ..ai.clarify_answers import pick_index, split_always
from ..config import Settings
from ..models import Task, TaskStatus, utcnow
from ..tools import browser_choice
from ..tools.registry import ToolRegistry
from . import lanes
from .lane_flow import _done, _lang, _run

LANE_KEY = "shadow:clarify"
SAYS: dict[str, dict[str, str]] = {
    "which_browser": {"en": "Which browser should I open: {names}?", "roman_ur": "Kaun sa browser kholun: {names}?"},
    "which_profile": {"en": "Which {browser} profile: {names}?", "roman_ur": "{browser} ki kaun si profile: {names}?"},
    "which_mail": {"en": "Which mail: {names}?", "roman_ur": "Kaun si mail kholun: {names}?"},
    "always_on": {"en": "Okay, I will always use {browser}. Say 'ask me every time' to change that.",
                  "roman_ur": "Theek hai, main hamesha {browser} istemal karunga. Badalne ke liye 'har baar poochho' bolein."},
    "always_off": {"en": "Okay, I will ask which browser every time.", "roman_ur": "Theek hai, main har baar poochhunga ke kaun sa browser."},
    "no_choice": {"en": "I did not catch which one. Say the name or 'first', 'second'.", "roman_ur": "Mujhe samajh nahi aaya kaun sa. Naam ya 'pehla', 'doosra' bolein."},
    "cancelled": {"en": "Okay, cancelled.", "roman_ur": "Theek hai, cancel kar diya."},
}
OPEN = r"(?:open|launch|start|run|check|show|kholo|khol\s+do|kholna|dikhao|chalao|चेक\s+करो|खोलो|खोल\s+दो|दिखाओ)"
BROWSER_ASK = re.compile(rf"^(?:please\s+)?(?:{OPEN}\s+)?(?:a\s+|the\s+|my\s+|any\s+)?(?:web\s+)?(?:browser|internet|ब्राउज़र|ब्राउजर|براؤزر)(?:\s+{OPEN})?$", re.I)
MAIL_ASK = re.compile(rf"^(?:please\s+)?(?:{OPEN}\s+)?(?:my\s+|the\s+)?(?:e-?mails?|mails?|inbox|ईमेल|मेल|ای\s*میل)(?:\s+{OPEN})?$", re.I)
ALWAYS_SET = re.compile(r"^(?:always\s+use|always|hamesha|हमेशा)\s+(.+?)(?:\s+(?:for\s+(?:websites|browsing|everything)|use\s+karo|istemal\s+karo))?$", re.I)
ASK_EVERY_TIME = re.compile(r"^(?:ask\s+me\s+every\s+time|always\s+ask|har\s+baar\s+(?:poochho|puchho|pucho|poocho)|ab\s+se\s+poochna|forget\s+(?:my\s+)?(?:browser|choice)(?:\s+choice)?)$", re.I)


def _say(key: str, lang: str, **slots: str) -> str:
    from ..voice.reply_script import reply_lang
    table = SAYS[key]
    return table.get(reply_lang(lang), table["en"]).format(**slots)


def _norm(text: str) -> str:
    return " ".join(str(text or "").casefold().strip(" .!?,;:।۔").split())


def _outlook_app(registry: ToolRegistry) -> bool:
    try:
        return registry.get("open_application")._match_start_menu_shortcut("outlook") is not None
    except Exception:  # noqa: BLE001
        return False


def mail_options(registry: ToolRegistry) -> list[dict]:
    options = [{"label": "Gmail", "plan": {"tool": "open_url", "args": {"url": "https://mail.google.com"}}}]
    if _outlook_app(registry):
        options.append({"label": "Outlook app", "plan": {"tool": "open_application", "args": {"app_name": "outlook"}}})
    options.append({"label": "Outlook on the web", "plan": {"tool": "open_url", "args": {"url": "https://outlook.live.com/mail/"}}})
    return options


def _ask(db: Session, task: Task, topic: str, options: list[dict], text: str) -> Task:
    state = lanes.load(db)
    now = lanes._now().isoformat()
    lane = lanes.Lane(agent="Shadow", kind="clarify", opened_at=now, last_active=now, pending={"type": "clarify", "topic": topic, "options": options})
    state.lanes[LANE_KEY] = lane
    lanes.save(db, state)
    return _done(db, task, text)


def _clear(db: Session) -> None:
    state = lanes.load(db)
    if LANE_KEY in state.lanes:
        del state.lanes[LANE_KEY]
        lanes.save(db, state)


def _plan(spec: dict) -> Plan:
    return Plan(actions=[PlanAction(tool=spec["tool"], args=spec["args"])], note="Local agent ne plan tayyar kiya; cloud API use nahi hui.")


def _open_browser_plan(browser: browser_choice.Browser, profile: str | None) -> dict:
    if profile:
        return {"tool": "open_browser_profile", "args": {"profile": profile.replace("Profile ", "") if profile.startswith("Profile ") else profile, "browser": browser.key}}
    return {"tool": "open_application", "args": {"app_name": browser.name if browser.key != "edge" else "Microsoft Edge"}}


def _profile_question(db: Session, task: Task, browser: browser_choice.Browser, lang: str) -> Task | None:
    from ..tools.browser_profiles import list_profiles
    profiles = list_profiles(browser.key) if browser.key in ("chrome", "edge") else []
    if len(profiles) <= 1:
        return None
    labels = [p["name"] if [q["name"] for q in profiles].count(p["name"]) == 1 else f"{p['name']} ({p['dir']})" for p in profiles]
    options = [{"label": label, "browser": browser.key, "profile": p["dir"], "plan": _open_browser_plan(browser, p["dir"])} for label, p in zip(labels, profiles)]
    return _ask(db, task, "profile", options, _say("which_profile", lang, browser=browser.name, names=", ".join(labels[:6])))


def try_handle(db: Session, task: Task, command: str, registry: ToolRegistry, settings: Settings, auto_approve: bool = False) -> Task | None:
    said = _norm(command)
    lang = _lang(command)
    state = lanes.load(db)
    lane = state.lanes.get(LANE_KEY)

    # 1) the answer to a question asked here
    if lane is not None and lane.pending and lane.pending.get("type") == "clarify":
        options = lane.pending["options"]
        topic = lane.pending["topic"]
        if said in {"no", "nahi", "nahin", "cancel", "rehne do", "नहीं", "نہیں"}:
            _clear(db)
            return _done(db, task, _say("cancelled", lang))
        always, spoken = split_always(command)
        labels = [o["label"] for o in options]
        index = pick_index(labels, spoken)
        if index is None and topic == "browser":
            key = browser_choice.key_of(spoken)
            index = next((i for i, o in enumerate(options) if o.get("browser") == key), None) if key else None
        if index is None and (BROWSER_ASK.match(said) or MAIL_ASK.match(said)):
            _clear(db)                                               # a new question of the same kind replaces the open one
            return try_handle(db, task, command, registry, settings, auto_approve)
        if index is None:
            if len(said.split()) <= 4:
                return _done(db, task, _say("no_choice", lang))      # still waiting: the question stays open
            _clear(db)
            return None                                              # a different, longer request: the question is dropped
        chosen = options[index]
        _clear(db)
        if topic == "browser":
            browser = next((b for b in browser_choice.installed() if b.key == chosen["browser"]), None)
            if browser is None:
                return None
            browser_choice.remember_in_lane(browser.key, None)
            if always:
                browser_choice.set_always(browser.key, None)
            asked = _profile_question(db, task, browser, lang)
            if asked is not None:
                return asked
            return _run(db, task, _plan(_open_browser_plan(browser, None)), registry, settings, auto_approve)
        if topic == "profile":
            browser_choice.remember_in_lane(chosen["browser"], chosen["profile"])
            if always:
                browser_choice.set_always(chosen["browser"], chosen["profile"])
        return _run(db, task, _plan(chosen["plan"]), registry, settings, auto_approve)

    # 2) the standing choice
    if ASK_EVERY_TIME.match(said):
        browser_choice.set_always(None)
        lane_b = lanes.lane_of_kind(state, "browser")
        if lane_b is not None:
            lane_b.browser = lane_b.profile = None
            lanes.save(db, state)
        return _done(db, task, _say("always_off", lang))
    m = ALWAYS_SET.match(said)
    if m:
        key = browser_choice.key_of(m.group(1))
        if key and key in {b.key for b in browser_choice.installed()}:
            browser_choice.set_always(key)
            return _done(db, task, _say("always_on", lang, browser=key.capitalize()))

    # 3) a request that does not say which app
    if BROWSER_ASK.match(said):
        have = browser_choice.installed()
        if len(have) < 2:
            return None
        choice = browser_choice.always() or browser_choice.lane_choice()
        if choice.get("browser") in {b.key for b in have}:
            browser = next(b for b in have if b.key == choice["browser"])
            if not choice.get("profile"):
                asked = _profile_question(db, task, browser, lang)
                if asked is not None:
                    return asked
            return _run(db, task, _plan(_open_browser_plan(browser, choice.get("profile"))), registry, settings, auto_approve)
        options = [{"label": b.name, "browser": b.key, "plan": _open_browser_plan(b, None)} for b in have]
        return _ask(db, task, "browser", options, _say("which_browser", lang, names=", ".join(o["label"] for o in options[:-1]) + (" or " if len(options) > 1 else "") + options[-1]["label"]))
    if MAIL_ASK.match(said) and "to " not in f" {said} ":
        options = mail_options(registry)
        return _ask(db, task, "mail", options, _say("which_mail", lang, names=", ".join(o["label"] for o in options[:-1]) + " or " + options[-1]["label"]))
    return None

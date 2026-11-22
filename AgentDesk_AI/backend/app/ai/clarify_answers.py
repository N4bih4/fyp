"""The user's answer to a question a TOOL asked ("Which browser: Chrome, Edge or Firefox?", "Which Chrome profile: ...?").

The tool (tools/browser_choice.py) stopped without opening anything and left `candidates` and `asking` in its result. The answer picks one: by name ("edge",
"google chrome", "क्रोम"), by number or ordinal ("second", "pehla", "2"), or with a standing choice ("always chrome", "hamesha chrome"). The choice is stored (the
conversation lane remembers it for 20 minutes; "always" stores it as a preference) and the ORIGINAL action runs again unchanged: the tool then finds the
choice and opens the browser. A profile question follows when the chosen browser has several profiles.
"""
from __future__ import annotations

import json
import re

from .base import Plan, PlanAction

ALWAYS = re.compile(r"^(?:always|hamesha|hameshaa|har\s+baar|हमेशा|ہمیشہ)\s+(?:use\s+|istemal\s+karo\s+)?(.+?)(?:\s+(?:use\s+karo|istemal\s+karo|mein|me|pe|par))?$", re.I)
ORDINALS = {"first": 0, "pehla": 0, "pehli": 0, "1": 0, "one": 0, "second": 1, "doosra": 1, "dusra": 1, "doosri": 1, "2": 1, "two": 1,
            "third": 2, "teesra": 2, "teesri": 2, "3": 2, "three": 2, "fourth": 3, "chautha": 3, "4": 3}


def split_always(reply: str) -> tuple[bool, str]:
    text = " ".join(str(reply or "").split()).strip(" .!?")
    m = ALWAYS.match(text)
    return (True, m.group(1).strip()) if m else (False, text)


def pick_index(names: list[str], reply: str) -> int | None:
    """Which candidate the reply means: an ordinal, or a name that appears in exactly one candidate."""
    words = re.findall(r"\w+", reply.casefold())
    for w in words:
        if w in ORDINALS and ORDINALS[w] < len(names):
            return ORDINALS[w]
    hits = [i for i, n in enumerate(names) if n.casefold() in reply.casefold() or (reply.strip() and reply.casefold().strip() in n.casefold())]
    return hits[0] if len(hits) == 1 else None


def _same_action_plan(action) -> Plan:
    return Plan(actions=[PlanAction(tool=action.tool_name, args=json.loads(action.args_json or "{}"))], note="Local agent ne plan tayyar kiya; cloud API use nahi hui.")


def browser_answer(original, reply: str) -> Plan | None:
    from ..tools import browser_choice
    action = next((a for a in original.actions if a.status == "failed" and a.result_json and '"asking"' in a.result_json), None)
    if action is None:
        return None
    try:
        out = json.loads(action.result_json).get("output") or {}
    except ValueError:
        return None
    names = [str(n) for n in out.get("candidates") or []]
    always, spoken = split_always(reply)
    if out.get("asking") == "browser":
        key = browser_choice.key_of(spoken)
        if key is None:
            index = pick_index(names, spoken)
            key = browser_choice.key_of(names[index]) if index is not None else None
        if key is None or key not in {b.key for b in browser_choice.installed()}:
            return None
        browser_choice.remember_in_lane(key, None)
        if always:
            browser_choice.set_always(key, None)
        return _same_action_plan(action)
    if out.get("asking") == "profile":
        from ..tools.browser_profiles import list_profiles, match_profile
        browser = str(out.get("browser") or "chrome")
        profiles = list_profiles(browser)
        index = pick_index(names, spoken)
        chosen = None
        if index is not None:
            m = re.search(r"\((Profile \d+|Default)\)\s*$", names[index])
            chosen = next((p for p in profiles if p["dir"] == m.group(1)), None) if m else next((p for p in profiles if p["name"] == names[index]), None)
        if chosen is None:
            chosen, _ = match_profile(profiles, spoken)
        if chosen is None:
            return None
        browser_choice.remember_in_lane(browser, chosen["dir"])
        if always:
            browser_choice.set_always(browser, chosen["dir"])
        return _same_action_plan(action)
    return None

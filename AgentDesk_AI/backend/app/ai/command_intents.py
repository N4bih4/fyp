"""Shared bounded on/open and off/close grammar across target types.

Only known applications, sites, settings and explicit folder nouns are rewritten.
Device commands retain their own validated setting/action semantics.
"""
import re
from .command_language import END, LINK, POLITE, known_target

VERBS = {
    "open": "open", "on": "open", "start": "open", "launch": "open", "kholo": "open", "khol": "open",
    "اوپن": "open", "آن": "open", "ان": "open", "کھولو": "open", "کھول": "open", "ओपन": "open", "ऑन": "open", "खोलो": "open", "खोल": "open",
    "close": "close", "off": "close", "band": "close", "بند": "close", "کلوز": "close", "اف": "close", "آف": "close", "बंद": "close", "क्लोज": "close", "ऑफ": "close",
}
TARGETS = {"پاور شیل": "powershell", "پاورشیل": "powershell", "power shell": "powershell", "पावर शेल": "powershell", "पावरशेल": "powershell",
           "سیٹنگ": "settings", "سیٹنگز": "settings", "setting": "settings", "सेटिंग": "settings", "सेटिंग्स": "settings"}


def switch_followup(command, prior):
    """Use only the immediately preceding successful named app/site action."""
    import json
    verbs = "|".join(re.escape(verb) for verb in VERBS)
    match = re.fullmatch(rf"(?:again\s+|phir\s+|پھر\s+|دوبارہ\s+)?({verbs})(?:{END}|\s+کر)", command.strip(), re.I)
    if not match or not prior or prior.status != "completed" or not prior.actions:
        return None
    last = prior.actions[-1]
    if last.status != "succeeded":
        return None
    args = json.loads(last.args_json)
    target = None
    if last.tool_name == "open_application":
        target = args.get("app_name")
    elif last.tool_name == "open_url":
        from urllib.parse import urlsplit
        from ..tools.browser import SITES
        host = (urlsplit(args.get("url", "")).hostname or "").removeprefix("www.")
        target = next((name for name, domains in SITES.items() if host in domains), None)
        if target and args.get("browser") == "chrome":
            target += " in chrome"
    elif last.tool_name == "control_browser":
        from ..tools.browser import SITES
        if args.get("target") in SITES:
            target = args["target"]
            if re.search(r"(?<!\w)(?:chrome|کروم|क्रोम)(?!\w)", prior.command, re.I):
                target += " in chrome"
    elif last.tool_name == "control_desktop" and args.get("steps") == [{"action": "close_window"}]:
        previous = canonical_command(prior.command)
        if previous.startswith("close "):
            from ..tools.apps import APP_TARGETS, APP_ALIASES
            candidate = previous.removeprefix("close ")
            if candidate in set(APP_TARGETS) | set(APP_ALIASES) | {"settings"}:
                target = candidate
    return canonical_command(f"{match.group(1)} {target}") if target else None


def canonical_command(command):
    from .speech_commands import normalize_speech, NEGATIONS
    from .browser_commands import SITES
    from ..tools.apps import APP_TARGETS, APP_ALIASES
    if any(word in NEGATIONS for word in normalize_speech(command).split()):
        return command
    text = re.sub(POLITE, "", command.strip().rstrip("۔।!?"), flags=re.I)
    text = re.sub(r"^(?:turn|ٹرن)\s+", "", text, flags=re.I)
    verbs = "|".join(re.escape(verb) for verb in VERBS)
    suffix = rf"(?:{END}|\s+کر)"
    match = re.fullmatch(rf"({verbs})\s+(.+?){suffix}", text, re.I)
    if match:
        action, target = VERBS[match.group(1).casefold()], match.group(2).strip()
    else:
        match = re.fullmatch(rf"(.+?){LINK}\s+({verbs}){suffix}", text, re.I)
        if not match:
            return command
        target, action = match.group(1).strip(), VERBS[match.group(2).casefold()]
    browser = False
    chrome = r"(?:chrome|google chrome|کروم|گوگل کروم|क्रोम)"
    for pattern in (rf"(.+?)\s+(?:in|ان|mein|میں|में|इन)\s+{chrome}", rf"(.+?)\s+{chrome}\s+(?:mein|میں|में)"):
        situated = re.fullmatch(pattern, target, re.I)
        if situated:
            target, browser = situated.group(1).strip(), True
            break
    lower = target.casefold()
    site = SITES.get(lower, lower)
    if site in set(SITES.values()):
        return f"{action} {site}" + (" in chrome" if browser and action == "open" else "")
    target = TARGETS.get(lower, known_target(target))
    lower = target.casefold()
    app_noun = r"(?:app|application|ایپ|ایپلیکیشن|ऐप|एप्लिकेशन)"
    named_app = re.fullmatch(rf"(?:{app_noun}\s+(.+)|(.+?)\s+{app_noun})", target, re.I)
    if named_app:
        name = known_target(named_app.group(1) or named_app.group(2))
        return f"{action} " + ("app " if action == "open" else "") + name
    if lower in {"settings", "windows settings"}:
        return f"{action} settings"
    if re.search(r"(?:^|\s)(?:folder|فولڈر|فولدر|फोल्डर)(?:$|\s)", target, re.I):
        if any(word.casefold() in VERBS for word in target.split()):
            return command  # preserve existing folder grammar and literal names
        return f"{action} {target}"
    if lower in set(APP_TARGETS) | set(APP_ALIASES) | {"whatsapp", "visual studio code"}:
        return f"{action} " + ("app " if action == "open" else "") + lower
    return command

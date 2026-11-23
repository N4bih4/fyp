"""Resolve an explicitly named close/off request against current window titles."""
import json
import re
from .base import Plan, PlanAction
from .command_language import END, LINK, POLITE, known_target
from .speech_commands import normalize_speech, NEGATIONS

CLOSE = r"(?:close|off|band|بند|کلوز|اف|آف|बंद|क्लोज|ऑफ)"
FOLDER = r"(?:folder|فولڈر|فولدر|फोल्डर)"
WINDOW = r"(?:window|ونڈو|ونڈوز|विंडो)"
SETTING = r"(?:settings?|سیٹنگ|سیٹنگز|سیٹنگس|सेटिंग|सेटिंग्स)"


def all_powershell_request(command):
    text = normalize_speech(command)
    if any(word in NEGATIONS for word in text.split()):
        return False
    text = re.sub(r"(?:power\s*shell|پاور\s*شیل|पावर\s*शेल)", "powershell", text, flags=re.I)
    words = set(text.split())
    allowed = set("powershell all every close off windows window opened open the that are is please currently تمام ساری سب جتنی بھی پاور شیل کی کے ونڈو ونڈوز کھلی کھلے ہوئی ہوا ہے ہیں بند کر کرو دو सभी सारी जितनी भी की के विंडो खुली है हैं बंद कर करो दो".split())
    return bool("powershell" in words and words & {"all", "every", "تمام", "ساری", "سب", "सभी", "सारी"} and words & {"close", "off", "بند", "बंद"} and words <= allowed)


def close_request(command):
    if all_powershell_request(command):
        return "__all_powershell__"
    text = re.sub(POLITE, "", command.strip().rstrip("۔।!?"), flags=re.I)
    if any(word in NEGATIONS for word in normalize_speech(text).split()):
        return None
    text = re.sub(r"^(?:turn|ٹرن)\s+", "", text, flags=re.I)
    match = re.fullmatch(rf"{CLOSE}\s+(.+?){END}", text, re.I)
    if not match:
        match = re.fullmatch(rf"(.+?){LINK}\s+{CLOSE}{END}", text, re.I)
    if not match:
        return None
    target = match.group(1).strip()
    if re.search(r"(?:^|\s)(?:tabs?|ٹیبز|ٹیب|टैब्स|टैब)(?:$|\s)", target, re.I):
        return None  # tab identity belongs to the browser integration
    target = re.sub(rf"\s+{WINDOW}$", "", target, flags=re.I).strip()
    if re.fullmatch(SETTING, target, re.I):
        return "settings"
    target = re.sub(rf"(?:^|\s){FOLDER}(?:$|\s)", " ", target, flags=re.I).strip()
    target = re.sub(r"^(?:app|application|window)\s+", "", target, flags=re.I)
    return known_target(target)


def spoken_app_name(target):
    """"Axel 316" -> "excel", "ایکسل" -> "excel": the digits speech-to-text appends are dropped and the app's known spoken spellings are applied."""
    words = target.split()                                     # (not \w: Hindi vowel signs are not "word" characters and would split the name)
    letters = [w for w in words if not re.fullmatch(r"\d+", w)]
    cleaned = " ".join(letters) if letters else target.strip()
    from ..tools.apps import APP_ALIASES
    low = cleaned.casefold().strip()
    return APP_ALIASES.get(low) or APP_ALIASES.get(low.replace(" ", "")) or cleaned


def similar_titles(target, titles):
    """Open window titles whose first part (before " - File Explorer") sounds like the spoken name: "diagramms" -> "diagrams". Best first, at most 5."""
    import difflib
    from ..nlu.phonetic import phonetic_key
    want = re.sub(r"[^\w\s]", "", target.casefold()).strip()
    if len(want) < 4:
        return []
    scored = []
    for title in dict.fromkeys(titles):
        segments = [s.casefold().strip() for s in re.split(r"\s[-\u2013\u2014]\s", title)]          # "Book1 - Excel": the app's name is the LAST part
        pieces = segments + [w for s in segments for w in re.findall(r"\w+", s)]
        best = max((difflib.SequenceMatcher(None, want, piece).ratio() for piece in pieces if piece), default=0.0)
        if any(len(piece) >= 3 and phonetic_key(piece) == phonetic_key(want) for piece in pieces):
            best = max(best, 0.95)                                   # they SOUND the same ("exsel" / "excel")
        if best >= 0.72:
            scored.append((best, title))
    scored.sort(key=lambda pair: -pair[0])
    return [title for _, title in scored[:5]]


def window_guess(target, titles):
    """([titles], plain): plain=True when the name is spelled (almost) the same or every word of it is in the title, so the user plainly meant it."""
    import difflib
    guesses = similar_titles(target, titles)
    want = re.findall(r"\w+", target.casefold())
    plain = False
    if len(guesses) == 1:
        segments = [s.casefold().strip() for s in re.split(r"\s[-\u2013\u2014]\s", guesses[0])]
        plain = bool(want) and (all(w in set(re.findall(r"\w+", guesses[0].casefold())) for w in want)
                               or max(difflib.SequenceMatcher(None, " ".join(want), s).ratio() for s in segments) >= 0.9)
    return guesses, plain


def close_action(title):
    return Plan(actions=[PlanAction(tool="control_desktop", args={"target_window": title, "steps": [{"action": "close_window"}]})], note=f"'{title}' window band karne ka plan tayyar hai.")


def window_plan(task, registry, command=None):
    target = close_request(command if command is not None else task.command)
    if target is None:
        return None
    if not target:
        return Plan(note="Kaunsa folder/app band karna hai? Naam batayein.")
    if not target.startswith("__") and target != "settings":
        target = spoken_app_name(target)
    inspected = registry.get("control_desktop").execute(registry.get("control_desktop").validate_args({"steps": [{"action": "inspect"}]}))
    if not inspected.success:
        return Plan(note=inspected.error or "Windows ki list nahi mil saki.")
    if target == "__all_powershell__":
        steps = inspected.output.get("completed_steps", [])
        if any(step.get("windows_truncated") for step in steps):
            return Plan(note="Windows ki list mukammal nahi mili. Abhi koi window band nahi ki.")
        windows = [window for step in steps for window in step.get("windows", [])]
        shells = [window for window in windows if window.get("process") in {"powershell.exe", "pwsh.exe"} or ("powershell" in window.get("title", "").casefold() and window.get("process") in {"conhost.exe", "windowsterminal.exe"})]
        if any("powershell" in window.get("title", "").casefold() and not window.get("process") for window in windows):
            return Plan(note="PowerShell window ka process verify nahi hua. Windows permissions check karein.")
        if not shells:
            return Plan(note="Koi visible PowerShell window khuli nahi mili. Background processes ko band nahi kiya.")
        if len(shells) > 20 or any(not window.get("id") or not window.get("pid") for window in shells):
            return Plan(note="PowerShell window identity verify nahi hui. Abhi koi window band nahi ki.")
        terminal_note = " Windows Terminal window band hone se uske doosre tabs bhi band ho sakte hain." if any(window.get("process") == "windowsterminal.exe" for window in shells) else ""
        return Plan(actions=[PlanAction(tool="control_desktop", args={"target_window": window["title"], "target_window_id": window["id"], "target_process_id": window["pid"], "steps": [{"action": "close_window"}]}) for window in shells], note=f"{len(shells)} visible PowerShell windows band karne ka plan tayyar hai. Running shell commands interrupt ho sakti hain; list review karein." + terminal_note)
    titles = [title for step in inspected.output.get("completed_steps", []) for title in step.get("open_windows", [])]
    # Known bilingual folder names map only for title discovery, never paths.
    from .command_language import search_name_key
    key = search_name_key(target)
    matches = [title for title in titles if target.casefold() in title.casefold() or (key and key in search_name_key(title))]
    matches = list(dict.fromkeys(matches))                       # Calculator is listed twice (its frame and its window): one title, one choice
    if len(matches) == 1:
        return close_action(matches[0])
    if matches:
        task.agent_state_json = json.dumps({"provider": "local", "window_choices": matches})
        return Plan(note="Kaunsi window band karni hai? Number batayein.\n" + "\n".join(f"{i+1}. {title}" for i, title in enumerate(matches)))
    guesses, plain = window_guess(target, titles)
    if len(guesses) == 1:
        plan = close_action(guesses[0])
        if not plain:                                   # a looser spelling: the Approve / Reject popup decides, nothing closes before it
            plan.actions[0].confirm = True
            plan.note = f"'{target}' naam ki window nahi mili; milti-julti: '{guesses[0]}'. Approve karein to yahi band hogi."
        return plan
    if guesses:
        # Several look alike: the user picks one by number.
        task.agent_state_json = json.dumps({"provider": "local", "window_choices": guesses})
        return Plan(note=f"'{target}' naam ki window nahi mili, lekin milti-julti hain. Kaunsi band karni hai? Number ya 'haan' batayein (abhi kuch band nahi hua):\n"
                         + "\n".join(f"{i+1}. {title}" for i, title in enumerate(guesses)))
    return Plan(note=f"'{target}' ki khuli window nahi mili. Khuli window ka naam batayein.")

"""Spoken browser-profile commands -> open_browser_profile ("open Chrome with the Work profile", "Zain wali profile kholo", "edge profile 2 kholo").

Needs the word "profile" (or its Urdu / Hindi spelling) so ordinary "open chrome" is untouched. The profile's name is what is left after the filler words.
"""
from __future__ import annotations

import re

from .base import Plan, PlanAction

PROFILE_WORD = re.compile(r"\b(?:profiles?|prophile|profil)\b|پروفائل|प्रोफ़ाइल|प्रोफाइल", re.I)
OPEN_WORD = re.compile(r"\b(?:open|launch|start|run|switch|use|show|change|kholo|khol|kholna|kholni|chalao|chalu|lagao|dikhao|dikha|dikhani)\b|کھولو|کھول|खोलो|खोल", re.I)
FILLER = {"open", "launch", "start", "run", "switch", "use", "show", "change", "kholni", "dikha", "dikhani", "me", "main", "kholo", "khol", "kholna", "chalao", "chalu", "lagao", "karo", "kar", "do", "dein", "den", "please",
          "chrome", "edge", "browser", "google", "microsoft", "with", "in", "on", "to", "using", "mein", "me", "main", "ka", "ki", "ke", "saath", "sath", "se",
          "the", "my", "a", "an", "wali", "wala", "waali", "wale", "profile", "profiles", "prophile", "profil", "number", "no", "ek", "meri", "mera", "apni", "apna",
          "پروفائل", "प्रोफ़ाइल", "प्रोफाइल"}


ANOTHER = {"another", "other", "different", "new", "next", "some", "any", "dusri", "doosri", "dusra", "doosra", "koi", "aur", "or", "alag", "naya", "nayi", "nai", "change",
           "switch", "all", "list", "show", "screen", "choose", "select", "pick", "chunna", "chuno", "dikhao", "dikha", "sab", "saari", "sari", "who", "using", "karni", "kholni",
           "hai", "hain", "chahiye", "dena", "do", "de", "mujhe", "mujhay", "me", "main", "meri", "dekhni", "dekhna", "banani", "banana", "kya", "kaun", "si", "se"}
EXPLORER_WORD = re.compile(r"\b(?:file\s+)?explorer\b|\bfolder\b|एक्सप्लोरर|ایکسپلورر", re.I)
USER_FILLER = FILLER | {"explorer", "file", "folder", "user", "users", "windows", "pc", "computer", "laptop", "home"}


def user_folder_plan(low: str) -> Plan:
    """"File Explorer mein Zain ki profile kholo": the Windows user folder (C:\\Users\\<name>), not a browser profile. The name is matched against the
    folders that exist (Whisper hears "Jain" for "Zain"); with no name the user's own folder, with a name that matches none the Users folder."""
    import difflib
    import os
    from pathlib import Path
    users = Path(os.environ.get("SystemDrive", "C:") + "\\Users")
    names = [p.name for p in users.iterdir() if p.is_dir() and p.name not in {"All Users", "Default", "Default User"}] if users.is_dir() else []
    spoken = " ".join(w for w in re.findall(r"[\w@.\-]+", low) if w not in USER_FILLER)
    path = os.path.expanduser("~")
    if spoken:
        scored = sorted(((difflib.SequenceMatcher(None, spoken, n.casefold()).ratio(), n) for n in names), reverse=True)
        path = str(users / scored[0][1]) if scored and scored[0][0] >= 0.6 else str(users)
    return Plan(actions=[PlanAction(tool="explorer_navigate", args={"path": path})], note="Local agent ne plan tayyar kiya; cloud API use nahi hui.")


def profile_plan(text: str) -> Plan | None:
    low = " ".join(str(text or "").casefold().split()).strip(" .!?")
    if not PROFILE_WORD.search(low) or not OPEN_WORD.search(low) or len(low) > 120:
        return None
    if EXPLORER_WORD.search(low):
        return user_folder_plan(low)
    browser = "edge" if re.search(r"\bedge\b", low) else "chrome"
    name = " ".join(w for w in re.findall(r"[\w@.\-]+", low) if w not in FILLER)
    if not name or set(name.split()) <= ANOTHER:                      # "open another profile": no name, so the browser's own profile screen is shown
        return Plan(actions=[PlanAction(tool="open_browser_profile", args={"profile": "", "browser": browser, "picker": True})],
                    note="Local agent ne plan tayyar kiya; cloud API use nahi hui.")
    return Plan(actions=[PlanAction(tool="open_browser_profile", args={"profile": name, "browser": browser})],
                note="Local agent ne plan tayyar kiya; cloud API use nahi hui.")


ORDINALS = {"first": 0, "1st": 0, "pehla": 0, "pehli": 0, "pehle": 0, "second": 1, "2nd": 1, "doosra": 1, "dusra": 1, "doosri": 1, "dusri": 1,
            "third": 2, "3rd": 2, "teesra": 2, "teesri": 2}


def profile_answer(original, reply: str) -> Plan | None:
    """The user's answer to "Which chrome profile: A (Profile 3), A (Profile 5)?": a folder ("profile 5", "5"), an ordinal ("second") or a full name."""
    import json
    action = next((a for a in original.actions if a.tool_name == "open_browser_profile" and a.status == "failed"), None)
    if action is None:
        return None
    try:
        args = json.loads(action.args_json or "{}")
        shown = [str(c) for c in (json.loads(action.result_json or "{}").get("output") or {}).get("candidates") or []]
    except ValueError:
        return None
    folders = [m.group(1) for c in shown for m in [re.search(r"\((Profile \d+|Default)\)\s*$", c)] if m]
    words = [w for w in re.findall(r"[\w@.\-]+", str(reply).casefold()) if w not in FILLER]
    if not words:
        return None
    choice = None
    if len(words) == 1 and words[0] in ORDINALS and ORDINALS[words[0]] < len(shown):
        choice = shown[ORDINALS[words[0]]]
    elif len(words) == 1 and words[0].isdigit():
        by_folder = [c for c, f in zip(shown, folders) if f.casefold() == f"profile {words[0]}"] if len(folders) == len(shown) else []
        choice = by_folder[0] if by_folder else (shown[int(words[0]) - 1] if 1 <= int(words[0]) <= len(shown) else None)
    if choice is not None:
        m = re.search(r"\((Profile \d+|Default)\)\s*$", choice)
        name = m.group(1) if m else re.sub(r"\s*\(.*\)$", "", choice)
        name = name.casefold().replace("profile ", "") if name.casefold().startswith("profile ") else name
    else:
        name = " ".join(words)
    return Plan(actions=[PlanAction(tool="open_browser_profile", args={"profile": name, "browser": args.get("browser", "chrome")})],
                note="Local agent ne plan tayyar kiya; cloud API use nahi hui.")


def drive_plan(text: str) -> Plan | None:
    """"C drive kholo" / "open drive D" -> a File Explorer window on that drive (explorer_navigate with no window: a new one, whose handle the lane then keeps)."""
    import os

    from ..orchestration.lane_commands import DEVANAGARI_DRIVE, DEVA_LETTER, drive_letter
    low = " ".join(str(text or "").casefold().split()).strip(" .!?")
    letter = drive_letter(low)
    if letter:
        pass
    elif DEVANAGARI_DRIVE.match(low):
        letter = DEVA_LETTER.get(low.split()[0], "C")
    if not letter:
        return None                                  # a drive that is not on this PC still gets a plan: the tool answers "there is no D: drive here, drives: C:, F:"
    return Plan(actions=[PlanAction(tool="explorer_navigate", args={"path": f"{letter}:\\"})], note="Local agent ne plan tayyar kiya; cloud API use nahi hui.")


def profile_followup(text: str, recent) -> Plan | None:
    """After the profile screen was shown, a short answer names the profile to open ("Nabiha", "Work wali", "number 3")."""
    import json
    if recent is None or not getattr(recent, "actions", None):
        return None
    last = recent.actions[-1]
    if last.tool_name != "open_browser_profile" or last.status != "succeeded":
        return None
    from datetime import datetime, timedelta, timezone
    made = getattr(recent, "created_at", None)
    if made is not None and datetime.now(timezone.utc) - (made if made.tzinfo else made.replace(tzinfo=timezone.utc)) > timedelta(minutes=5):
        return None                                                   # the profile screen was shown long ago: this is another request
    try:
        out = json.loads(last.result_json or "{}").get("output") or {}
        args = json.loads(last.args_json or "{}")
    except ValueError:
        return None
    if not out.get("picker"):
        return None
    low = " ".join(str(text or "").casefold().split()).strip(" .!?")
    words = [w for w in re.findall(r"[\w@.\-]+", low) if w not in FILLER]
    if not words or len(low.split()) > 5:
        return None
    from ..tools.browser_profiles import list_profiles, match_profile
    profile, _ = match_profile(list_profiles(args.get("browser", "chrome")), " ".join(words))
    if profile is None:
        return None
    folder = profile["dir"]
    return Plan(actions=[PlanAction(tool="open_browser_profile", args={"profile": folder.replace("Profile ", "") if folder.startswith("Profile ") else folder, "browser": args.get("browser", "chrome")})],
                note="Local agent ne plan tayyar kiya; cloud API use nahi hui.")

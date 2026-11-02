"""Inside an open task, "here" means the folder the task is working in.

"Make a folder called Notes here", "go back", "what is in here" (and their Roman Urdu forms) are rewritten into the full command the normal parsers
already understand, using the folder the session remembers (`TaskSession.current_folder`, set by a VERIFIED open / list / create). Nothing is
guessed: with no open session or no remembered folder the sentence is left exactly as it was. The planner also receives the session
(goal, app, folder, steps) as DESKTOP_CONTEXT, so a follow-up that is not one of these patterns is still read inside the task.
"""
from __future__ import annotations

import re
from pathlib import Path

from sqlalchemy.orm import Session

from . import session as sessions

_HERE = r"(?:here|in this folder|in the same folder|in the current folder|inside it|in here)"
_NAME = r"([^\s].*?)"
_CREATE = [
    re.compile(rf"(?i)^(?:please )?(?:make|create|add|new)(?: a| an)?(?: new)? folder(?: (?:called|named))? {_NAME}\s+{_HERE}\s*$"),
    re.compile(rf"(?i)^(?:please )?(?:make|create|add)(?: a| an)?(?: new)? folder\s+{_HERE}\s+(?:called|named)\s+{_NAME}\s*$"),
    re.compile(r"(?i)^(?:yahan|yahaan|yaha|is folder mein|isi folder mein)\s+" + _NAME + r"\s+(?:naam ka|naam ka naya|naam se)\s+(?:naya\s+)?folder\s+(?:banao|bana do|banado)\s*$"),
    re.compile(r"(?i)^" + _NAME + r"\s+(?:naam ka|naam se)\s+(?:naya\s+)?folder\s+yahan\s+(?:banao|bana do|banado)\s*$"),
]
_BACK = re.compile(r"(?i)^(?:please )?(?:go back|go up|up one level|one level up|parent folder|go to the parent folder|back one folder|peeche jao|upar jao|ek folder peeche jao)\s*$")
_LIST = re.compile(r"(?i)^(?:please )?(?:what(?:'s| is) in here|what is here|list (?:the )?files here|show (?:me )?the files here|show what is here|yahan kya hai|yahan ki files dikhao)\s*\??$")


def rewrite(db: Session, command: str) -> str:
    """The command with "here" / "go back" resolved against the open task's folder; unchanged when there is nothing to resolve."""
    state = sessions.current(db)
    folder = state.current_folder if state else None
    if not folder:
        return command
    text = (command or "").strip().rstrip(".!?")
    for pattern in _CREATE:
        m = pattern.match(text)
        if m:
            return f"create a folder called {m.group(1).strip()} in {folder}"
    if _BACK.match(text):
        parent = str(Path(folder).parent)
        return f"open {parent}" if parent and parent != folder else command
    if _LIST.match(text):
        return f"list the files in {folder}"
    return command


def planner_view(db: Session) -> dict:
    """The open task as the planner sees it (data, never instructions)."""
    state = sessions.current(db)
    if state is None:
        return {}
    return {"task_session": {"goal": state.goal, "current_app": state.current_app, "current_folder": state.current_folder,
                             "steps_done": [{"tool": s.get("tool"), "ok": s.get("ok"), "verified": s.get("verified")} for s in state.steps_done[-8:]],
                             "waiting_for": (state.open_items or {}).get("waiting_for")}}

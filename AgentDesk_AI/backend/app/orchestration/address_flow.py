"""Calling an agent by name (the team is on screen: Shadow lead, Scout browser, Atlas files/system, Forge coding, Echo research).

* "Shadow" / "Scout" ... said alone: the agent answers ("Ji, Shadow hoon. Kahiye.") and is on standby for 60 seconds: the NEXT sentence is a request to
  that agent (Shadow, the team lead, then splits it and hands the parts to the others: agents/splitter.py + agents/dispatcher.py).
* "Scout, open youtube" (name first, then the request) is handled by the dispatcher itself.
The standby lives in a preference row, so it survives a restart and times out by itself.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from ..agents.roster import load_roster
from ..models import Preference, Task
from .lane_flow import _done, _lang

KEY = "addressed"
STANDBY_SECONDS = 60
ROLE_WORDS = {
    "shadow": {"en": "the team lead", "roman_ur": "team lead"}, "scout": {"en": "the browser agent", "roman_ur": "browser wala agent"},
    "atlas": {"en": "the files and system agent", "roman_ur": "files aur system wala agent"}, "forge": {"en": "the coding agent", "roman_ur": "coding wala agent"},
    "echo": {"en": "the research and mail agent", "roman_ur": "research aur mail wala agent"},
}
SAYS = {"en": "Yes, {name} here, {role}. What should I do?", "roman_ur": "Ji, main {name} hoon, {role}. Kya karna hai?"}


def _norm(text: str) -> str:
    return " ".join(re.sub(r"[.,;:!?،۔।\-]+", " ", str(text or "").casefold()).split())


def _agent_named(said: str):
    """The agent whose name (any spelling) is ALL that was said, optionally after "hey" / "ok"."""
    said = re.sub(r"^(?:hey|hi|ok|okay|ae|oye)\s+", "", said)
    for agent in load_roster():
        if any(said == _norm(alias) for alias in agent.aliases):
            return agent
    return None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _standby(db: Session) -> str | None:
    row = db.get(Preference, KEY)
    try:
        data = json.loads(row.value_json) if row and row.value_json else {}
        if data.get("agent") and _now() - datetime.fromisoformat(data["at"]) < timedelta(seconds=STANDBY_SECONDS):
            return data["agent"]
    except (ValueError, KeyError):
        pass
    return None


def _set(db: Session, agent: str | None) -> None:
    row = db.get(Preference, KEY) or Preference(key=KEY)
    row.value_json = json.dumps({"agent": agent, "at": _now().isoformat()} if agent else {})
    db.add(row)
    db.commit()


def greet(db: Session, task: Task, command: str) -> Task | None:
    """A bare agent name: answer and put the agent on standby. None when the sentence is more than a name."""
    agent = _agent_named(_norm(command))
    if agent is None:
        return None
    _set(db, agent.name)
    from ..voice.reply_script import reply_lang
    lang = reply_lang(_lang(command))
    role = ROLE_WORDS.get(agent.key, {}).get(lang, agent.role)
    return _done(db, task, SAYS.get(lang, SAYS["en"]).format(name=agent.name, role=role))


def hand_over(db: Session, task: Task, command: str) -> str:
    """After a bare name the next request goes to that agent: "open youtube" -> "Scout, open youtube". Returns the command to run (unchanged when nobody is on standby)."""
    agent = _standby(db)
    if agent is None:
        return command
    _set(db, None)
    from ..agents.dispatcher import address
    named, _ = address(command, load_roster())
    return command if named is not None else f"{agent}, {command}"

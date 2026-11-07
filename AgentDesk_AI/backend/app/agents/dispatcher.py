"""Shadow, the team lead, decides who does a request.

1. A request that starts with an agent's name ("Scout, search chairs on Daraz") goes to that agent.
2. Otherwise the kind of work is read from the words (browser, files, system, coding, research).
3. Among the agents that can do that kind of work, the best FREE one gets it; Shadow himself only takes work when
   nobody else who can do it is free. If every capable agent is busy, the request waits with the best of them.
4. A named agent who is busy does not make the user wait: Shadow gives the job to a free agent who can do it and says so.

"Busy" means the agent's last job is not finished yet (read from the task statuses), so nothing needs to be released by hand.
"""
from __future__ import annotations

import re
import threading
from dataclasses import dataclass

from ..models import Task, TaskStatus
from .roster import Agent, load_roster

DONE = {TaskStatus.COMPLETED, TaskStatus.PARTIALLY_COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED, TaskStatus.REJECTED}

# Words that show the kind of work (English, Roman Urdu, Urdu, Hindi). Substring match on the lower-cased request.
KEYWORDS: dict[str, tuple[str, ...]] = {
    "browser": ("youtube", "chrome", "browser", "tab", "website", "google", "daraz", "amazon", "search", "filter", "rating", "gmail", "whatsapp",
                "یوٹیوب", "کروم", "ٹیب", "سرچ", "تلاش", "यूट्यूब", "क्रोम", "टैब", "सर्च", "खोजो"),
    "files": ("folder", "file", "directory", "drive", "copy", "move", "rename", "delete", "zip", "download", "documents", "desktop",
              "فولڈر", "فائل", "ڈرائیو", "फोल्डर", "फाइल", "ड्राइव"),
    "system": ("volume", "brightness", "bluetooth", "wifi", "wi-fi", "mute", "shutdown", "restart", "lock", "sleep", "battery", "dark mode", "settings",
               "آواز", "والیوم", "برائٹنس", "بلوٹوتھ", "आवाज", "वॉल्यूम", "ब्राइटनेस", "ब्लूटूथ"),
    "coding": ("antigravity", "codex", "claude", "cursor", "vscode", "vs code", "visual studio", "code", "prompt", "terminal", "powershell", "cmd",
               "git ", "pytest", "npm", "python", "build", "bug", "اینٹی گریویٹی", "کوڈ", "टर्मिनल", "एंटी ग्रेविटी", "कोड", "प्रॉम्प्ट"),
    "research": ("summar", "explain", "research", "transcript", "story", "email", "mail", "document", "report", "news", "music", "song", "movie",
                 "خلاصہ", "ای میل", "گانا", "فلم", "समरी", "ईमेल", "गाना", "फिल्म", "स्टोरी"),
}


def kind_of_work(text: str) -> str:
    low = f" {text.casefold()} "
    scores = {kind: sum(1 for w in words if w in low) for kind, words in KEYWORDS.items()}
    best = max(scores, key=lambda k: scores[k])
    return best if scores[best] > 0 else "files"


def address(text: str, team: list[Agent]) -> tuple[Agent | None, str]:
    """('Scout, search chairs' -> Scout, 'search chairs'). Only a name at the very start counts."""
    stripped = text.strip()
    for agent in team:
        for alias in sorted(agent.aliases, key=len, reverse=True):
            m = re.match(rf"^(?:hey |hi |ok )?{re.escape(alias)}(?![\w])[\s,:.\-،]*", stripped, re.I)
            if m and stripped[m.end():].strip():
                return agent, stripped[m.end():].strip()
    return None, stripped


@dataclass
class Assignment:
    agent: str
    task_id: str | None
    kind: str
    queued: bool = False
    note: str = ""


class Dispatcher:
    def __init__(self, team: list[Agent] | None = None):
        self.team = team or load_roster()
        self._current: dict[str, str] = {}      # agent key -> task id
        self._lock = threading.Lock()

    def _busy(self, db, key: str) -> bool:
        task_id = self._current.get(key)
        if not task_id:
            return False
        task = db.get(Task, task_id)
        return task is not None and task.status not in DONE

    def status(self, db) -> list[dict]:
        out = []
        with self._lock:
            for a in self.team:
                tid = self._current.get(a.key)
                task = db.get(Task, tid) if tid else None
                busy = task is not None and task.status not in DONE
                out.append({"name": a.name, "role": a.role, "lead": a.is_lead, "skills": a.skills, "busy": busy,
                            "task_id": tid if busy else None, "doing": task.command[:120] if busy and task else None})
        return out

    def choose(self, db, text: str) -> tuple[Assignment, str]:
        """Pick the agent for a request and return (assignment, request without the agent's name)."""
        named, body = address(text, self.team)
        kind = kind_of_work(body)
        with self._lock:
            capable = sorted((a for a in self.team if a.skills.get(kind, 0) > 0),
                             key=lambda a: (a.is_lead, -a.skills.get(kind, 0)))   # the lead comes last: he delegates
            free = [a for a in capable if not self._busy(db, a.key)]
            if named is not None and not named.is_lead:
                if not self._busy(db, named.key):
                    return Assignment(named.name, None, kind), body
                other = next((a for a in free if a.key != named.key), None)
                if other is not None:
                    return Assignment(other.name, None, kind, note=f"{named.name} is busy, so Shadow gave it to {other.name}."), body
                return Assignment(named.name, None, kind, queued=True, note=f"{named.name} is busy; the request waits."), body
            if free:
                return Assignment(free[0].name, None, kind), body
            best = capable[0] if capable else next(a for a in self.team if a.is_lead)
            return Assignment(best.name, None, kind, queued=True, note=f"Everyone who can do this is busy; {best.name} will take it next."), body

    def record(self, assignment: Assignment, task_id: str) -> None:
        assignment.task_id = task_id
        with self._lock:
            self._current[assignment.agent.casefold()] = task_id


_dispatcher: Dispatcher | None = None


def get_dispatcher() -> Dispatcher:
    global _dispatcher
    if _dispatcher is None:
        _dispatcher = Dispatcher()
    return _dispatcher

"""The team: five named agents. Every agent has a skill level (0..1) per kind of work, so the skills overlap and
a job can move to whoever is free. Names, wake spellings and skills can be changed in `data/agents.json`
(same shape as DEFAULT_ROSTER); a missing or broken file means the defaults."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

SKILLS = ("browser", "files", "system", "coding", "research")
LEAD = "shadow"

# Spellings Whisper may write when the user says the name (Latin, Urdu script, Devanagari).
DEFAULT_ROSTER: list[dict] = [
    {"name": "Shadow", "role": "Team lead: hears every request, hands it to the right free agent, reports back",
     "aliases": ["shadow", "shado", "شیڈو", "شیڈؤ", "शैडो", "शेडो"],
     "skills": {"browser": 0.6, "files": 0.6, "system": 0.6, "coding": 0.6, "research": 0.6}},
    {"name": "Scout", "role": "Browser automation: search, filters, YouTube, shopping sites",
     "aliases": ["scout", "اسکاؤٹ", "سکاؤٹ", "स्काउट"],
     "skills": {"browser": 1.0, "research": 0.8, "files": 0.4}},
    {"name": "Atlas", "role": "Files, folders, drives and PC settings",
     "aliases": ["atlas", "اٹلس", "ایٹلس", "एटलस", "अटलस"],
     "skills": {"files": 1.0, "system": 0.9, "browser": 0.5}},
    {"name": "Forge", "role": "Coding apps: Antigravity, Codex, Claude, VS Code, terminal",
     "aliases": ["forge", "فورج", "फोर्ज"],
     "skills": {"coding": 1.0, "files": 0.6, "system": 0.5, "browser": 0.4}},
    {"name": "Echo", "role": "Research, summaries, documents, mail and media",
     "aliases": ["echo", "ایکو", "ईको", "इको"],
     "skills": {"research": 1.0, "browser": 0.7, "files": 0.5}},
]


@dataclass
class Agent:
    name: str
    role: str
    aliases: list[str]
    skills: dict[str, float] = field(default_factory=dict)

    @property
    def key(self) -> str:
        return self.name.casefold()

    @property
    def is_lead(self) -> bool:
        return self.key == LEAD


def _config_path() -> Path:
    return Path(__file__).resolve().parents[3] / "data" / "agents.json"


def load_roster(path: Path | None = None) -> list[Agent]:
    raw = DEFAULT_ROSTER
    path = path or _config_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list) and data and any(str(a.get("name", "")).casefold() == LEAD for a in data):
            raw = data
    except (OSError, ValueError):
        pass
    team: list[Agent] = []
    for item in raw:
        name = str(item.get("name", "")).strip()
        if not name:
            continue
        skills = {k: float(v) for k, v in (item.get("skills") or {}).items() if k in SKILLS}
        aliases = [str(a).casefold() for a in item.get("aliases", [])] + [name.casefold()]
        team.append(Agent(name, str(item.get("role", "")), list(dict.fromkeys(aliases)), skills))
    return team

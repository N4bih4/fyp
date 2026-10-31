"""Conversation memory: last 10 turns, last results and reference resolution.

A turn stores what the user said, the validated steps, the outcome and any
result list the user may refer to next (e.g. `candidates` from find_paths).
Results are DATA: they are shown to the planner as context, never as
instructions.

Reference resolution is deliberately narrow:
- "it / isay / اسے / इसे" -> the target of the most recent *successful* turn
  (app, site, folder, file or setting). Failed or pending turns are skipped
  only for results lists, never to reach an older target.
- "the second one / doosra wala / دوسرا والا / दूसरा वाला" -> item N of the
  most recent turn's result list.
"""
from __future__ import annotations

import json
from collections import deque
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

MAX_TURNS = 10
_SITE_HOSTS = {"youtube.com": "youtube", "mail.google.com": "gmail", "web.whatsapp.com": "whatsapp",
               "chatgpt.com": "chatgpt", "drive.google.com": "google drive"}
ORDINALS = {"FIRST": 0, "SECOND": 1, "THIRD": 2}


@dataclass
class Turn:
    command: str
    steps: list[dict[str, Any]] = field(default_factory=list)
    status: str = "completed"          # completed | failed | awaiting_input | ...
    results: dict[str, Any] = field(default_factory=dict)
    reply: str = ""


@dataclass
class Entity:
    kind: str      # app | site | folder | file | setting
    value: str

    def as_dict(self) -> dict[str, str]:
        return {"kind": self.kind, "value": self.value}


def _site_from_url(url: str) -> str | None:
    host = (urlsplit(url).hostname or "").removeprefix("www.")
    return _SITE_HOSTS.get(host)


def entity_of(step: dict[str, Any]) -> Entity | None:
    tool, args = step.get("tool"), step.get("args") or {}
    if tool == "open_application" and args.get("app_name"):
        return Entity("app", args["app_name"])
    if tool == "open_url":
        site = _site_from_url(args.get("url", ""))
        return Entity("site", site) if site else Entity("url", args.get("url", ""))
    if tool == "control_browser" and args.get("target"):
        return Entity("site", args["target"])
    if tool in {"open_folder", "create_folder", "list_folder"} and args.get("path"):
        return Entity("folder", args["path"])
    if tool in {"open_file", "read_text_file", "write_text_file"} and args.get("path"):
        return Entity("file", args["path"])
    if tool == "manage_system_setting" and args.get("setting"):
        return Entity("setting", args["setting"])
    if tool == "control_desktop" and args.get("target_window"):
        return Entity("window", args["target_window"])
    return None


class ConversationMemory:
    def __init__(self, turns: list[Turn] | None = None, profile: dict[str, Any] | None = None):
        self.turns: deque[Turn] = deque(turns or [], maxlen=MAX_TURNS)
        self.profile = profile or {}      # only when the user opted in

    @classmethod
    def from_context(cls, context: dict[str, Any] | None) -> "ConversationMemory":
        memory = cls()
        for raw in (context or {}).get("turns", []):
            memory.add(Turn(command=raw.get("command", ""), steps=raw.get("steps", []),
                            status=raw.get("status", "completed"), results=raw.get("results") or {}))
        return memory

    def add(self, turn: Turn) -> None:
        self.turns.append(turn)

    def last(self) -> Turn | None:
        return self.turns[-1] if self.turns else None

    def last_target(self) -> Entity | None:
        """Target of the immediately preceding successful turn (not older ones)."""
        turn = self.last()
        if turn is None or turn.status != "completed":
            return None
        for step in reversed(turn.steps):
            entity = entity_of(step)
            if entity is not None:
                return entity
        return None

    def last_setting(self) -> str | None:
        target = self.last_target()
        return target.value if target and target.kind == "setting" else None

    def last_results(self) -> tuple[list[str], str | None]:
        """Result list of the most recent turn, and the kind of item (file/folder)."""
        turn = self.last()
        if turn is None:
            return [], None
        items = turn.results.get("candidates") or turn.results.get("items") or []
        kind = None
        for step in turn.steps:
            if step.get("tool") == "find_paths":
                kind = (step.get("args") or {}).get("kind", "folder")
            elif step.get("tool") == "find_files":
                kind = "file"
        return [str(i) for i in items], kind

    def resolve_ordinal(self, ordinal: str) -> tuple[str, str | None] | None:
        items, kind = self.last_results()
        index = ORDINALS.get(ordinal)
        if index is None or index >= len(items):
            return None
        return items[index], kind

    def to_prompt(self) -> str:
        """Compact JSON for the planner. Marked as data by the prompt builder."""
        turns = [{"command": t.command, "status": t.status,
                  "steps": [{"tool": s.get("tool"), "args": s.get("args")} for s in t.steps],
                  "results": t.results} for t in self.turns]
        target = self.last_target()
        return json.dumps({"turns": turns, "last_target": target.as_dict() if target else None,
                           "profile": self.profile}, ensure_ascii=False)

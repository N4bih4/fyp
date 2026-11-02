"""The conversation as the planner sees it: the last 10 tasks (what was said, which tools ran, how it ended).

Built from the task table, so a follow-up or a correction ("not only open the URL, play music on YouTube") is read together with the sentence before it.
Only short facts go in: tool names, arguments and statuses, never file contents or long output (the planner prompt treats all of it as data).
"""
from __future__ import annotations

import json

from sqlalchemy.orm import Session

from ..models import Task
from ..nlu.memory import ConversationMemory, Turn

TURNS = 10


def _short(value):
    if isinstance(value, str):
        return value if len(value) <= 120 else value[:120] + "..."
    if isinstance(value, dict):
        return {k: _short(v) for k, v in list(value.items())[:8]}
    if isinstance(value, list):
        return [_short(v) for v in value[:5]]
    return value


def recent_memory(db: Session, current: Task | None = None, limit: int = TURNS) -> ConversationMemory:
    rows = db.query(Task).order_by(Task.created_at.desc()).limit(limit + 1).all()
    memory = ConversationMemory()
    for task in reversed([t for t in rows if current is None or t.id != current.id][:limit]):
        steps = []
        for action in task.actions:
            try:
                args = json.loads(action.args_json or "{}")
            except ValueError:
                args = {}
            steps.append({"tool": action.tool_name, "args": _short(args)})
        status = "completed" if task.status == "completed" else ("failed" if task.status == "failed" else task.status)
        memory.add(Turn(command=(task.command or "")[:300], steps=steps, status=status, reply=(task.plan_note or task.error or "")[:160]))
    return memory

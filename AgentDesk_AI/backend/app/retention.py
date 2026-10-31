"""Opt-in data retention. Disabled unless RETENTION_DAYS > 0.

What it may remove, and nothing else:
- the stored AI conversation (`tasks.agent_state_json`) of tasks that finished
  more than RETENTION_DAYS ago (it can hold file listings and prior tool output);
- rollback checkpoint backups of those same old, finished tasks.
Task rows, actions, results and history are never deleted. A task whose
backup is removed shows `rollback_status = "expired"` so the UI never offers
an undo that can no longer work.
"""
from __future__ import annotations

import json
import shutil
from datetime import timedelta
from pathlib import Path

from sqlalchemy.orm import Session

from .logging_setup import log_event
from .models import Task, TaskStatus, utcnow
from .orchestration.rollback import BACKUP_DIR_NAME

_FINISHED = (TaskStatus.COMPLETED, TaskStatus.PARTIALLY_COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED, TaskStatus.REJECTED)


def _backup_folder(plan: dict) -> Path | None:
    """The checkpoint folder is <...>/.agentdesk_checkpoints/<id>/content.bak; refuse anything else."""
    raw = plan.get("backup")
    if not raw:
        return None
    path = Path(raw)
    if path.name != "content.bak" or path.parent.parent.name != BACKUP_DIR_NAME:
        return None
    return path.parent


def prune(db: Session, settings) -> dict:
    days = int(getattr(settings, "retention_days", 0) or 0)
    if days <= 0:
        return {"enabled": False, "conversations_cleared": 0, "backups_removed": 0}
    cutoff = utcnow() - timedelta(days=days)
    cleared = removed = 0
    old = db.query(Task).filter(Task.status.in_(_FINISHED), Task.updated_at < cutoff).all()
    for task in old:
        if task.agent_state_json:
            task.agent_state_json = None
            cleared += 1
        for action in task.actions:
            if not action.rollback_json or action.rollback_status not in ("available", "failed"):
                continue
            try:
                folder = _backup_folder(json.loads(action.rollback_json))
            except (json.JSONDecodeError, TypeError, AttributeError):
                folder = None
            if folder is not None and folder.is_dir():
                shutil.rmtree(folder, ignore_errors=True)
                removed += 1
                action.rollback_status = "expired"
                action.rollback_detail = f"Checkpoint removed after {days} days (retention policy)."
    db.commit()
    log_event("retention_pruned", count=cleared + removed, detail=f"conversations={cleared} backups={removed}")
    return {"enabled": True, "conversations_cleared": cleared, "backups_removed": removed}

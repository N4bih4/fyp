"""Task metrics for the pilot: one CSV row per finished task, written automatically.

Privacy: a row holds counts, timings, tool names, risk levels and an error *category*. It never holds
the command text, file paths, arguments, results, phone numbers or e-mail addresses. The command's
language and length are kept so recognition quality can still be compared.

Automatic export: with `PILOT_METRICS=1` every task that reaches a final state appends a row to
`<AgentDesk data>/pilot/task_metrics.csv` (folder overridable with `AGENTDESK_PILOT_DIR`).
`GET /metrics/tasks.csv` returns the same rows computed from the database at any time.
"""
from __future__ import annotations

import csv
import io
import json
import os
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import event
from sqlalchemy.orm import Session

from .models import Action, ActionStatus, Task, TaskStatus

TERMINAL = {TaskStatus.COMPLETED, TaskStatus.PARTIALLY_COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED,
            TaskStatus.REJECTED}
# A command the assistant did not understand stops at awaiting_input with no actions; the pilot must count it.
REPORTED = TERMINAL | {TaskStatus.AWAITING_INPUT}
FIELDS = ("task_id", "created_at", "finished_at", "duration_s", "status", "language", "command_chars", "source",
          "actions", "tools", "max_risk", "approvals_required", "approval_wait_s", "verified_actions",
          "failed_actions", "stopped", "error_kind")
_RISK_ORDER = {"low": 0, "medium": 1, "high": 2}


def error_kind(text: str | None) -> str:
    """A coarse category; the error text itself may contain paths or names and is not exported."""
    if not text:
        return ""
    t = text.casefold()
    for kind, words in (("unsupported_platform", ("windows only", "needs windows", "only available on windows",
                                                  "requires windows", "supported on windows")),
                        ("timeout", ("timed out", "timeout", "stopped after")),
                        ("verification", ("verif", "evidence", "not confirmed", "did not")),
                        ("approval", ("approval", "approve", "altered")),
                        ("not_found", ("not found", "nahi mila", "does not exist", "no such")),
                        ("refused", ("refused", "not allowed", "outside", "blocked")),
                        ("provider", ("groq", "rate limit", "api key", "provider")),
                        ("restart", ("restart",))):
        if any(w in t for w in words):
            return kind
    return "other"


def row_for(task: Task) -> dict[str, Any]:
    from .nlu.normalizer import detect_language

    actions: list[Action] = sorted(task.actions, key=lambda a: a.seq)
    approvals = [a for a in actions if a.approved_at is not None]
    wait = (min(a.approved_at for a in approvals) - task.created_at).total_seconds() if approvals else ""
    stopped = ""
    verified = 0
    for a in actions:
        try:
            result = json.loads(a.result_json or "{}")
            verification = json.loads(a.verification_json or "{}")
        except ValueError:
            result, verification = {}, {}
        stopped = stopped or (result.get("output") or {}).get("stopped") or ""
        verified += bool(a.status == ActionStatus.SUCCEEDED and verification.get("passed") and verification.get("evidence"))
    try:
        source = json.loads(task.agent_state_json or "{}").get("provider") or ("local" if not actions else "")
    except ValueError:
        source = ""
    first_error = task.error or next((a.error for a in actions if a.error), None)
    return {
        "task_id": task.id,
        "created_at": task.created_at.isoformat(timespec="seconds"),
        "finished_at": task.updated_at.isoformat(timespec="seconds"),
        "duration_s": round((task.updated_at - task.created_at).total_seconds(), 3),
        "status": "not_understood" if task.status == TaskStatus.AWAITING_INPUT and not actions else task.status,
        "language": detect_language(task.command or ""),
        "command_chars": len(task.command or ""),
        "source": source or "cloud",
        "actions": len(actions),
        "tools": ";".join(a.tool_name for a in actions),
        "max_risk": max((a.risk for a in actions), key=lambda r: _RISK_ORDER.get(r, 0), default=""),
        "approvals_required": sum(a.risk in ("medium", "high") for a in actions),
        "approval_wait_s": round(wait, 3) if wait != "" else "",
        "verified_actions": verified,
        "failed_actions": sum(a.status == ActionStatus.FAILED for a in actions),
        "stopped": stopped,
        "error_kind": error_kind(first_error),
    }


def export_csv(db: Session, days: int | None = None) -> str:
    query = db.query(Task).filter(Task.status.in_(REPORTED)).order_by(Task.created_at)
    if days:
        query = query.filter(Task.created_at >= datetime.utcnow() - timedelta(days=days))
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    for task in query.all():
        writer.writerow(row_for(task))
    return buffer.getvalue()


# ------------------------------------------------------------------ automatic export
def pilot_csv_path() -> Path:
    override = os.environ.get("AGENTDESK_PILOT_DIR")
    if override:
        return Path(override) / "task_metrics.csv"
    from .logging_setup import log_dir

    return log_dir().parent / "pilot" / "task_metrics.csv"


_pending: set[str] = set()
_written: set[str] = set()
_lock = threading.Lock()


def _enabled() -> bool:
    from .config import get_settings

    return bool(getattr(get_settings(), "pilot_metrics", False))


def append_row(row: dict[str, Any], path: Path | None = None) -> Path:
    path = path or pilot_csv_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    new = not path.exists() or path.stat().st_size == 0
    with path.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS, lineterminator="\n")
        if new:
            writer.writeheader()
        writer.writerow(row)
    return path


@event.listens_for(Task.status, "set")
def _on_status(target: Task, value, oldvalue, initiator):
    if value in REPORTED and target.id:
        with _lock:
            _pending.add(target.id)


@event.listens_for(Session, "after_commit")
def _after_commit(session: Session) -> None:
    """Write rows for tasks whose final status is now committed (read back in a fresh session)."""
    with _lock:
        if not _pending:
            return
        ids = list(_pending)
    if not _enabled():
        with _lock:
            _pending.difference_update(ids)
        return
    from .database import SessionLocal

    reader = SessionLocal()
    try:
        for task in reader.query(Task).filter(Task.id.in_(ids)).all():
            if task.status not in REPORTED:
                continue  # another session has not committed it yet
            with _lock:
                if task.id in _written:
                    _pending.discard(task.id)
                    continue
                _written.add(task.id)
                _pending.discard(task.id)
            try:
                append_row(row_for(task))
            except OSError:
                pass  # metrics must never break a task
    finally:
        reader.close()

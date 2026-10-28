"""Approval binding: an approval is valid only for the exact action it was given for.

Each action gets a SHA-256 binding over (task id, action id, tool, canonical
args, risk) when it is created. Approval records a time and, for medium/high
risk, an expiry. Immediately before execution the hash is recomputed, so an
action whose stored tool/args/risk changed after planning, or whose approval
is stale, is rejected rather than run.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta

from ..models import Action, utcnow


def _canonical(args_json: str | None) -> str:
    try:
        return json.dumps(json.loads(args_json or "{}"), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    except json.JSONDecodeError:
        return args_json or ""


def compute_binding(task_id: str, action_id: str, tool_name: str, args_json: str | None, risk: str) -> str:
    material = "\x1f".join([task_id, action_id, tool_name, _canonical(args_json), risk])
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def binding_for(action: Action) -> str:
    return compute_binding(action.task_id, action.id, action.tool_name, action.args_json, action.risk)


def expiry_for(risk: str, ttl_seconds: int, now: datetime | None = None) -> datetime | None:
    """Low-risk actions auto-approve and run at once; others expire if left waiting."""
    if risk == "low":
        return None
    return (now or utcnow()) + timedelta(seconds=ttl_seconds)


class ApprovalError(ValueError):
    pass


def check_before_execution(action: Action, now: datetime | None = None) -> None:
    """Raise ApprovalError unless this exact action is still validly approved."""
    now = now or utcnow()
    if not action.binding_hash:
        raise ApprovalError("Action has no approval binding; refusing to run.")
    if binding_for(action) != action.binding_hash:
        raise ApprovalError("Action was altered after it was planned; approval is void. Request the action again.")
    if action.approval_expires_at is not None and now > action.approval_expires_at:
        raise ApprovalError("Approval expired before the action ran. Ask again and approve promptly.")

"""Local entitlements and usage metering (no accounts, no network, no payments).

A *plan* is a named set of limits read from local configuration. Usage is
counted in the local database as small events that hold no command text,
arguments or file data. Limits apply only to things that cost money or
resources: new tasks and calls to a cloud AI provider. Safety features
(approvals, rollback, logging, local commands) never depend on the plan.

Honest scope: this is a budget/metering guard on the user's own machine. The
user (or anyone with access to the database or .env) can change it, so it is
NOT licence enforcement. A real paid tier needs a server that issues and
verifies signed entitlements; that is out of scope for this local design.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from .ai.base import AIRateLimitError
from .logging_setup import log_event
from .models import UsageEvent, utcnow

# Placeholder limits pending a business decision on the approved release scope.
# "unlimited" (the default) preserves the behaviour of earlier phases exactly.
PLANS: dict[str, dict[str, int]] = {
    "free": {"tasks_day": 20, "ai_calls_day": 20, "ai_calls_month": 200},
    "standard": {"tasks_day": 200, "ai_calls_day": 300, "ai_calls_month": 5000},
    "unlimited": {},
}

KINDS = ("task", "action", "ai_call")


class QuotaExceeded(Exception):
    """A plan limit was reached. `message` is safe to show to the user."""

    def __init__(self, message: str, snapshot: dict | None = None):
        super().__init__(message)
        self.message = message
        self.snapshot = snapshot or {}


class AIQuotaExceeded(AIRateLimitError):
    """Cloud-AI limit reached: the task pauses (waiting_retry) until the period resets."""

    def __init__(self, message: str, retry_after: float):
        super().__init__(message, retry_after)
        self.user_note = message + " Reset ke baad Resume dabayein; local PC commands abhi bhi chalengi."


def get_plan(settings) -> tuple[str, dict[str, int]]:
    name = str(getattr(settings, "entitlement_plan", "unlimited")).strip().lower()
    if name not in PLANS:
        raise ValueError(f"Unknown plan {name!r}. Use one of: {', '.join(sorted(PLANS))}.")
    return name, PLANS[name]


def _local_midnight(now: datetime) -> datetime:
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def period_bounds(now_local: datetime | None = None) -> dict[str, datetime]:
    """Day/month starts in local time, returned as naive UTC (the database convention)."""
    now_local = now_local or datetime.now().astimezone()
    day = _local_midnight(now_local)
    month = day.replace(day=1)
    next_day = day + timedelta(days=1)
    to_utc = lambda d: d.astimezone(timezone.utc).replace(tzinfo=None)  # noqa: E731
    return {"day": to_utc(day), "month": to_utc(month), "next_day": to_utc(next_day)}


def record(db: Session, kind: str, task_id: str | None = None, units: int = 1) -> None:
    if kind not in KINDS:
        raise ValueError(f"Unknown usage kind {kind!r}")
    db.add(UsageEvent(kind=kind, task_id=task_id, units=units, ts=utcnow()))
    db.commit()


def _sum(db: Session, kind: str, since: datetime) -> int:
    total = db.query(func.coalesce(func.sum(UsageEvent.units), 0)).filter(UsageEvent.kind == kind, UsageEvent.ts >= since).scalar()
    return int(total or 0)


def snapshot(db: Session, settings, now_local: datetime | None = None) -> dict:
    name, limits = get_plan(settings)
    bounds = period_bounds(now_local)
    used = {
        "tasks_day": _sum(db, "task", bounds["day"]),
        "actions_day": _sum(db, "action", bounds["day"]),
        "ai_calls_day": _sum(db, "ai_call", bounds["day"]),
        "ai_calls_month": _sum(db, "ai_call", bounds["month"]),
    }
    remaining = {key: max(0, limit - used.get(key, 0)) for key, limit in limits.items()}
    return {"plan": name, "limits": limits, "used": used, "remaining": remaining,
            "resets_at_utc": bounds["next_day"].isoformat() + "Z"}


def check_task(db: Session, settings) -> None:
    snap = snapshot(db, settings)
    limit = snap["limits"].get("tasks_day")
    if limit is not None and snap["used"]["tasks_day"] >= limit:
        log_event("quota_exceeded", level=30, detail="tasks_day")
        raise QuotaExceeded(f"Daily task limit reached for the '{snap['plan']}' plan ({limit} tasks). It resets at local midnight.", snap)


def check_ai(db: Session, settings) -> None:
    snap = snapshot(db, settings)
    for key, label in (("ai_calls_day", "daily"), ("ai_calls_month", "monthly")):
        limit = snap["limits"].get(key)
        if limit is not None and snap["used"][key] >= limit:
            bounds = period_bounds()
            reset = bounds["next_day"] if key == "ai_calls_day" else (bounds["next_day"] + timedelta(days=32)).replace(day=1)
            log_event("quota_exceeded", level=30, detail=key)
            raise AIQuotaExceeded(
                f"Cloud AI {label} limit reached for the '{snap['plan']}' plan ({limit} calls).",
                max(60.0, (reset - utcnow()).total_seconds()),
            )

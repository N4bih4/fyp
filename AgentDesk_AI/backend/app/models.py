"""SQLAlchemy persistence models: tasks and their planned actions."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import event, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from .database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    """Naive UTC now (SQLite-friendly)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class TaskStatus:
    CREATED = "created"
    PLANNED = "planned"
    AWAITING_APPROVAL = "awaiting_approval"
    AWAITING_INPUT = "awaiting_input"
    APPROVED = "approved"
    EXECUTING = "executing"
    WAITING_RETRY = "waiting_retry"
    PAUSED = "paused"  # user-requested pause (between actions, or a stopped resumable step)
    COMPLETED = "completed"
    PARTIALLY_COMPLETED = "partially_completed"  # some steps verified, a later one failed
    FAILED = "failed"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class ActionStatus:
    PENDING = "pending"  # waiting for user approval/confirmation
    APPROVED = "approved"  # auto-approved (low risk) or user-approved
    REJECTED = "rejected"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"
    PAUSED = "paused"  # a resumable step (download) was stopped; resume continues it


class Task(Base):
    __tablename__ = "tasks"

    id = Column(String(36), primary_key=True, default=_uuid)
    command = Column(Text, nullable=False)
    idempotency_key = Column(String(128), unique=True, nullable=True)
    status = Column(String(32), nullable=False, default=TaskStatus.CREATED)
    plan_note = Column(Text, nullable=True)
    error = Column(Text, nullable=True)
    # Agentic-loop state (Groq provider): persisted conversation + bookkeeping
    # as JSON so the loop can pause for approval and resume across requests.
    agent_state_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    actions = relationship(
        "Action", back_populates="task", cascade="all, delete-orphan", order_by="Action.seq"
    )


class Action(Base):
    __tablename__ = "actions"

    id = Column(String(36), primary_key=True, default=_uuid)
    task_id = Column(String(36), ForeignKey("tasks.id"), nullable=False)
    seq = Column(Integer, nullable=False)
    tool_name = Column(String(64), nullable=False)
    args_json = Column(Text, nullable=False, default="{}")
    risk = Column(String(16), nullable=False, default="low")
    status = Column(String(32), nullable=False, default=ActionStatus.PENDING)
    result_json = Column(Text, nullable=True)
    verification_json = Column(Text, nullable=True)
    error = Column(Text, nullable=True)
    # The model-provider's tool-call id, for matching approvals/resumes.
    call_id = Column(String(128), nullable=True)
    # Approval binding (see security/approvals.py)
    binding_hash = Column(String(64), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    approval_expires_at = Column(DateTime, nullable=True)
    # Checkpoint / rollback (see orchestration/rollback.py)
    rollback_json = Column(Text, nullable=True)
    rollback_status = Column(String(16), nullable=True)  # available | unsupported | done | failed
    rollback_detail = Column(Text, nullable=True)

    task = relationship("Task", back_populates="actions")


class UsageEvent(Base):
    """One metered unit (a task, an action run, or a cloud-AI call). Never holds command text or data."""

    __tablename__ = "usage_events"

    id = Column(String(36), primary_key=True, default=_uuid)
    ts = Column(DateTime, default=utcnow, nullable=False, index=True)
    kind = Column(String(16), nullable=False)
    task_id = Column(String(36), nullable=True)  # no foreign key: usage history outlives task cleanup
    units = Column(Integer, nullable=False, default=1)


@event.listens_for(Action, "before_insert")
def _bind_action(mapper, connection, target: Action) -> None:
    """Fix the action's identity at creation so later edits are detectable."""
    from .security.approvals import binding_for

    if target.id is None:
        target.id = _uuid()
    if target.status is None:
        target.status = ActionStatus.PENDING
    target.binding_hash = binding_for(target)
    if target.status == ActionStatus.APPROVED and target.approved_at is None:
        target.approved_at = utcnow()


class Preference(Base):
    """One user preference (persona, listen mode, provider mode, risk policy). Never secrets."""

    __tablename__ = "preferences"

    key = Column(String(64), primary_key=True)
    value_json = Column(Text, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class MemoryItem(Base):
    """Something the user asked AgentDesk to remember. Shown and editable on the Memory page.
    Planner context treats it as data, never as instructions."""

    __tablename__ = "memory_items"

    id = Column(String(36), primary_key=True, default=_uuid)
    kind = Column(String(16), nullable=False, default="fact")
    text = Column(Text, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


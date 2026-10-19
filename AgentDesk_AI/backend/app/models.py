"""SQLAlchemy persistence models: tasks and their planned actions."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
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
    COMPLETED = "completed"
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

    task = relationship("Task", back_populates="actions")

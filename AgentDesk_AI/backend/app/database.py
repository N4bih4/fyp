"""SQLite database setup via SQLAlchemy."""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from .config import get_settings


def _build_engine():
    settings = get_settings()
    connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
    return create_engine(settings.database_url, connect_args=connect_args)


engine = _build_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from . import models  # noqa: F401  (register models)

    Base.metadata.create_all(bind=engine)
    _migrate()


def _migrate() -> None:
    """Lightweight SQLite migrations for columns added after v0.1.0.

    create_all() never adds columns to existing tables, so we check
    PRAGMA table_info and ALTER TABLE when needed. Safe to run repeatedly.
    """
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    if "tasks" not in inspector.get_table_names():
        return
    task_cols = {c["name"] for c in inspector.get_columns("tasks")}
    action_cols = {c["name"] for c in inspector.get_columns("actions")}
    with engine.begin() as conn:
        if "agent_state_json" not in task_cols:
            conn.execute(text("ALTER TABLE tasks ADD COLUMN agent_state_json TEXT"))
        if "call_id" not in action_cols:
            conn.execute(text("ALTER TABLE actions ADD COLUMN call_id VARCHAR(128)"))

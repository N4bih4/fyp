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

if engine.url.get_backend_name() == "sqlite":
    from sqlalchemy import event as _event

    @_event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_connection, _record):
        """Reliability: WAL lets the UI poll while a task runs; busy_timeout turns
        brief lock contention into a short wait instead of 'database is locked'."""
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA busy_timeout = 5000")
            cursor.execute("PRAGMA journal_mode = WAL")
            cursor.execute("PRAGMA synchronous = NORMAL")
            cursor.execute("PRAGMA foreign_keys = ON")
        finally:
            cursor.close()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Bump when the schema changes and add a step to _migrate(). Stored in SQLite's
# PRAGMA user_version so an older database is never silently treated as current.
SCHEMA_VERSION = 6  # v6: preferences, memory_items


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
        for column, ddl in (("binding_hash", "VARCHAR(64)"), ("approved_at", "DATETIME"), ("approval_expires_at", "DATETIME"),
                               ("rollback_json", "TEXT"), ("rollback_status", "VARCHAR(16)"), ("rollback_detail", "TEXT")):
            if column not in action_cols:
                conn.execute(text(f"ALTER TABLE actions ADD COLUMN {column} {ddl}"))
    _stamp_version()


def _stamp_version() -> None:
    from sqlalchemy import text

    if not engine.url.get_backend_name() == "sqlite":
        return
    with engine.begin() as conn:
        current = conn.execute(text("PRAGMA user_version")).scalar() or 0
        if current > SCHEMA_VERSION:
            raise RuntimeError(
                f"Database schema v{current} is newer than this app (v{SCHEMA_VERSION}). Refusing to start."
            )
        if current < SCHEMA_VERSION:
            conn.execute(text(f"PRAGMA user_version = {SCHEMA_VERSION}"))

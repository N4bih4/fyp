"""Pytest configuration: isolated env, temp workspace, fresh database.

Environment variables are set BEFORE any app modules are imported, because
the settings object and DB engine are created at import time.
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

# --- isolated sandbox for the whole test session ------------------------------
SESSION_TMP = Path(tempfile.mkdtemp(prefix="agentdesk_tests_"))
os.environ["AI_PROVIDER"] = "mock"
os.environ["AI_MODEL"] = "mock-test-model"
os.environ.pop("OPENAI_API_KEY", None)
os.environ["DATABASE_URL"] = f"sqlite:///{SESSION_TMP / 'test.db'}"
os.environ["AGENTDESK_ALLOWED_DIRECTORIES"] = ",".join(
    str(SESSION_TMP / sub) for sub in ("allowed", "home", "testdir")
)
os.environ["AGENTDESK_MOCK_HOME"] = str(SESSION_TMP / "home")
os.environ["AGENTDESK_TEST_DIR"] = str(SESSION_TMP / "testdir")
os.environ["TOOL_TIMEOUT_SECONDS"] = "10"

for sub in ("allowed", "home", "testdir"):
    (SESSION_TMP / sub).mkdir(parents=True, exist_ok=True)

import pytest  # noqa: E402

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.tools.base import ToolContext  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

Base.metadata.create_all(bind=engine)


def _make_ctx(tmp_path: Path) -> ToolContext:
    return ToolContext(
        allowed_directories=[tmp_path],
        approved_applications=["chrome", "notepad"],
        test_dir=tmp_path / "testdir",
    )


@pytest.fixture()
def ctx(tmp_path: Path) -> ToolContext:
    return _make_ctx(tmp_path)


@pytest.fixture()
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
    # clean all rows after each test for isolation
    session = SessionLocal()
    for table in reversed(Base.metadata.sorted_tables):
        session.execute(table.delete())
    session.commit()
    session.close()


@pytest.fixture()
def client(db):
    with TestClient(app) as c:
        yield c


def pytest_sessionfinish(session, exitstatus):
    shutil.rmtree(SESSION_TMP, ignore_errors=True)

"""Local API token: a random secret shared by the launcher, backend and UI.

The token lives in a per-user file (not in source, logs or URLs sent to the
server). The launcher opens the UI with the token in the URL *fragment*, which
browsers never transmit, and the UI sends it as a Bearer header.
"""
from __future__ import annotations

import os
import secrets
from functools import lru_cache
from pathlib import Path


def token_path() -> Path:
    override = os.environ.get("AGENTDESK_TOKEN_FILE")
    if override:
        return Path(override)
    base = os.environ.get("LOCALAPPDATA")
    return (Path(base) if base else Path.home() / ".agentdesk") / "AgentDesk" / "api_token"


def load_or_create_token() -> str:
    path = token_path()
    try:
        existing = path.read_text(encoding="utf-8").strip()
        if len(existing) >= 32:
            return existing
    except OSError:
        pass
    token = secrets.token_urlsafe(32)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(token, encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return token


@lru_cache
def get_api_token() -> str | None:
    """None only when auth is explicitly disabled (tests, AGENTDESK_REQUIRE_API_TOKEN=0)."""
    if os.environ.get("AGENTDESK_REQUIRE_API_TOKEN", "1").strip().lower() in {"0", "false", "no"}:
        return None
    return load_or_create_token()

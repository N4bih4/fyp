"""Structured JSON-lines logging with secret redaction.

One line per event: timestamp, level, event name and correlation fields
(request id, task id, action id, tool). Commands, tool arguments, file
contents and prompts are never logged. Error text is truncated and passed
through `redact` so keys, bearer tokens and URL tokens cannot reach the file.
"""
from __future__ import annotations

import json
import logging
import logging.handlers
import os
import re
from datetime import datetime, timezone
from pathlib import Path

LOGGER_NAME = "agentdesk"
_REDACTIONS = [
    (re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]{8,}"), "Bearer [REDACTED]"),
    (re.compile(r"(?i)(token|api[_-]?key|authorization|secret|password)(\s*[=:]\s*|=)[^\s,;&\"']+"), r"\1\2[REDACTED]"),
    (re.compile(r"\bgsk_[A-Za-z0-9]{10,}"), "[REDACTED]"),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{16,}"), "[REDACTED]"),
    (re.compile(r"\bAIza[0-9A-Za-z_-]{20,}"), "[REDACTED]"),
    (re.compile(r"(?i)([?&#]token=)[^&\s]+"), r"\1[REDACTED]"),
    (re.compile(r"\b[A-Za-z0-9_-]{40,}\b"), "[REDACTED-LONG-TOKEN]"),
]
_FIELDS = ("request_id", "task_id", "action_id", "tool", "status", "risk", "method", "path", "http_status", "duration_ms", "detail", "count")


def redact(text: str, limit: int = 300) -> str:
    text = str(text)
    for pattern, replacement in _REDACTIONS:
        text = pattern.sub(replacement, text)
    return text if len(text) <= limit else text[:limit] + "..."


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "ts": datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "event": getattr(record, "event", record.getMessage()),
        }
        for key in _FIELDS:
            value = getattr(record, key, None)
            if value is not None:
                entry[key] = redact(value) if isinstance(value, str) else value
        if record.exc_info:
            entry["exception"] = redact(self.formatException(record.exc_info), 600)
        return json.dumps(entry, ensure_ascii=False)


def log_dir() -> Path:
    override = os.environ.get("AGENTDESK_LOG_DIR")
    if override:
        return Path(override)
    base = os.environ.get("LOCALAPPDATA")
    return (Path(base) if base else Path.home() / ".agentdesk") / "AgentDesk" / "logs"


def setup_logging() -> logging.Logger:
    """Idempotent: attach one rotating JSON file handler (5 MB x 3) to the app logger."""
    logger = logging.getLogger(LOGGER_NAME)
    if getattr(logger, "_agentdesk_ready", False):
        return logger
    logger.setLevel(logging.INFO)
    logger.propagate = False
    try:
        folder = log_dir()
        folder.mkdir(parents=True, exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(
            folder / "agentdesk.log", maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
        )
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
    except OSError:
        logger.addHandler(logging.NullHandler())  # logging must never stop the app
    logger._agentdesk_ready = True  # type: ignore[attr-defined]
    return logger


def log_event(event: str, level: int = logging.INFO, **fields) -> None:
    """Log one event. Only the whitelisted correlation fields are written."""
    logging.getLogger(LOGGER_NAME).log(level, event, extra={"event": event, **{k: v for k, v in fields.items() if k in _FIELDS}})

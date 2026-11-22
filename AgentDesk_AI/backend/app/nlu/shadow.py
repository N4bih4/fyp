"""Shadow mode for the local intent model: predict in the background and log, change NOTHING.

For every command the executor calls `observe(task_id, command)`. If the model files exist (models/intent/), a daemon thread asks the model and appends
one line to logs/intent_shadow.jsonl (task id, intent, confidence, top 3, slots, ms). Later `ml/shadow_report.py` joins that file with what the app
really did (the tools that ran) to show how often the local model would have been right, and at which confidence it can be trusted.
The file holds the sentences you speak: it stays on this PC (logs/ is not committed). Off with AGENTDESK_INTENT_SHADOW=off.
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

LOG = Path(__file__).resolve().parents[3] / "logs" / "intent_shadow.jsonl"
_write_lock = threading.Lock()


def _run(task_id: str, command: str) -> None:
    try:
        from .local_model import get_model
        model = get_model()
        if model is None:
            return
        pred = model.predict(command)
        if pred is None:
            return
        row = {"ts": round(time.time(), 1), "task_id": task_id, "text": command[:300], "intent": pred.intent, "confidence": round(pred.confidence, 4),
               "top": [(i, round(p, 4)) for i, p in pred.top], "slots": pred.slots, "ms": round(pred.ms, 1)}
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with _write_lock, LOG.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001 - shadow mode must never disturb a command
        return


def observe(task_id: str, command: str) -> None:
    if os.environ.get("AGENTDESK_INTENT_SHADOW", "").lower() == "off" or not command.strip():
        return
    threading.Thread(target=_run, args=(task_id, command), daemon=True, name="intent-shadow").start()

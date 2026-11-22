#!/usr/bin/env python3
r"""Compare the local model (logs/intent_shadow.jsonl) with what the app really did (tools that ran), per confidence band.

    backend\.venv\Scripts\python ml\shadow_report.py

"Right" = the intent the executed tools stand for (ml/collect_history.label) equals the model's intent. It tells you from which confidence the model can
replace the cloud planner (agreement >= 97% is a good bar) and which intents it gets wrong. Local only; prints no sentence.
"""
from __future__ import annotations

import collections
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "ml"))
sys.path.insert(0, str(ROOT / "backend"))
from collect_history import label  # noqa: E402


def main() -> int:
    log = ROOT / "logs" / "intent_shadow.jsonl"
    if not log.exists():
        print("no shadow log yet: use the app (voice or text) with models/intent/ present")
        return 1
    shadow = {}
    for line in log.read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        shadow[r["task_id"]] = r
    db = sqlite3.connect(f"file:{ROOT / 'backend' / 'agentdesk.db'}?mode=ro", uri=True)
    truth = {}
    for task_id, tool, args, status in db.execute("select task_id, tool_name, args_json, status from actions order by task_id, seq"):
        if str(status).lower() not in ("succeeded", "success", "completed", "verified") or task_id not in shadow or task_id in truth:
            continue
        got = label(tool, json.loads(args or "{}"))
        if got:
            truth[task_id] = got[0]
    bands = [(0.0, 0.5), (0.5, 0.7), (0.7, 0.85), (0.85, 0.95), (0.95, 1.01)]
    stat = {b: [0, 0] for b in bands}
    wrong = collections.Counter()
    for tid, real in truth.items():
        p = shadow[tid]
        for b in bands:
            if b[0] <= p["confidence"] < b[1]:
                stat[b][0] += 1
                stat[b][1] += p["intent"] == real
        if p["intent"] != real and p["confidence"] >= 0.85:
            wrong[(p["intent"], real)] += 1
    print(f"commands logged {len(shadow)}, with a known outcome {len(truth)}")
    for b, (n, ok) in stat.items():
        print(f"confidence {b[0]:.2f}-{min(b[1], 1):.2f}: {n:4d} commands, agree {ok / n:.1%}" if n else f"confidence {b[0]:.2f}-{min(b[1], 1):.2f}:    0")
    for (said, real), n in wrong.most_common(10):
        print(f"confident but different: model {said}, app did {real}: {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

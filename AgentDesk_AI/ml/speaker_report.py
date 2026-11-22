#!/usr/bin/env python3
r"""How well the local intent model understands EACH speaker (Phase 6 of docs/VOICE_AUTOMATION_PLAN.md).

    backend\.venv\Scripts\python ml\speaker_report.py                 # every data/real/history_<speaker>.jsonl
    backend\.venv\Scripts\python ml\speaker_report.py --speaker nabiha

For every speaker file written by `ml/collect_history.py --speaker <name>`: the share of sentences the model labels correctly, the share it answers at the
calibrated threshold (models/intent/calibration.json) and how often it is right when it answers. That last number is the one that matters: it must stay
>= 97% for a NEW voice too, or the model must not act alone for that person. With two or more speakers the report also says which speaker is the weakest,
which is the "new speaker" test: train without that speaker's file (`ml\retrain.ps1` reads data/real/*.jsonl; move one file away), run this report with
that speaker, and compare. Nothing leaves this PC and no sentence is printed.
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))


def score(rows: list[dict], model) -> dict:
    """Accuracy of `model` on rows with {"text", "intent"}: overall, answered (confident) share, accuracy when answered, and the wrong intents."""
    right = answered = right_answered = 0
    wrong = collections.Counter()
    for row in rows:
        pred = model.predict(row["text"])
        if pred is None:
            continue
        ok = pred.intent == row["intent"]
        right += ok
        if pred.confident:
            answered += 1
            right_answered += ok
        if not ok:
            wrong[f"{row['intent']} -> {pred.intent}"] += 1
    n = len(rows)
    return {"n": n, "accuracy": right / n if n else 0.0, "answered": answered / n if n else 0.0,
            "accuracy_when_answered": right_answered / answered if answered else 0.0, "wrong": wrong.most_common(5)}


def load(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            if r.get("text") and r.get("intent"):
                rows.append(r)
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--speaker", default="", help="only this speaker")
    args = ap.parse_args()
    from app.nlu.local_model import get_model
    model = get_model()
    if model is None:
        print("no local model: models/intent/ is missing")
        return 1
    files = sorted((ROOT / "data" / "real").glob("history_*.jsonl"))
    if args.speaker:
        files = [f for f in files if f.stem == f"history_{args.speaker}"]
    results = {}
    for path in files:
        rows = load(path)
        if rows:
            results[path.stem.removeprefix("history_")] = score(rows, model)
    if not results:
        print("no speaker data yet: say commands into the orb, then `ml\\collect_history.py --i-consent --speaker <name>`")
        return 1
    print(f"model threshold {model.threshold:.3f}")
    print(f"{'speaker':14} {'n':>5} {'accuracy':>9} {'answers':>8} {'right when it answers':>22}")
    for name, r in results.items():
        flag = "" if r["accuracy_when_answered"] >= 0.97 or r["answered"] == 0 else "   <- below 97%: do not let the model act alone for this voice"
        print(f"{name:14} {r['n']:>5} {r['accuracy']:>8.1%} {r['answered']:>8.1%} {r['accuracy_when_answered']:>21.1%}{flag}")
        for pair, count in r["wrong"]:
            print(f"{'':14}   wrong: {pair} x{count}")
    if len(results) > 1:
        weakest = min(results, key=lambda k: results[k]["accuracy"])
        print(f"weakest speaker: {weakest} ({results[weakest]['accuracy']:.1%})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

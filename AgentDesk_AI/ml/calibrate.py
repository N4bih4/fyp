#!/usr/bin/env python3
r"""Fit a temperature and pick the confidence threshold for models/intent/ (writes models/intent/calibration.json).

    backend\.venv\Scripts\python ml\calibrate.py [--precision 0.97]

Uses sentences the model never trained on: data/val.jsonl would be too easy, so it prefers data/test_noisy.jsonl + data/test_public.jsonl
(+ the speaker-held-out real test rows). Temperature T minimises the log-loss of softmax(logits / T); the threshold is the lowest confidence at which the
accuracy of the answers above it is >= --precision (default 97%). 'unknown' and risky intents are never auto-run anyway (Prediction.may_act).
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "ml"))
from common import DATA, read_jsonl  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--precision", type=float, default=0.97)
    a = ap.parse_args()
    import numpy as np
    from app.nlu.local_model import LocalIntentModel, model_dir
    directory = model_dir()
    (directory / "calibration.json").unlink(missing_ok=True)       # measure the raw model
    model = LocalIntentModel(directory)
    rows = [r for name in ("test_noisy.jsonl", "test_public.jsonl") for r in read_jsonl(DATA / name)]
    logits, gold = [], []
    for r in rows:
        if model.predict(r["text"]) is None or r["intent"] not in model.intents:
            continue
        logits.append(model.last_logits.copy())
        gold.append(model.intents.index(r["intent"]))
    L, y = np.stack(logits), np.array(gold)

    def probs(T):
        z = (L - L.max(1, keepdims=True)) / T
        e = np.exp(z)
        return e / e.sum(1, keepdims=True)

    best = min((float(np.mean(-np.log(probs(T)[np.arange(len(y)), y] + 1e-12))), T) for T in np.arange(0.5, 6.01, 0.1))
    T = round(float(best[1]), 2)
    p = probs(T)
    conf, pred = p.max(1), p.argmax(1)
    ok = pred == y
    threshold = 0.99
    for t in np.arange(0.30, 0.995, 0.005):
        mask = conf >= t
        if mask.sum() >= 20 and ok[mask].mean() >= a.precision:
            threshold = round(float(t), 3)
            break
    mask = conf >= threshold
    report = {"n": len(y), "temperature": T, "threshold": threshold, "accuracy_all": round(float(ok.mean()), 4),
              "answered_share": round(float(mask.mean()), 4), "accuracy_when_answered": round(float(ok[mask].mean()), 4) if mask.any() else None,
              "wrong_and_answered": int((mask & ~ok).sum())}
    (directory / "calibration.json").write_text(json.dumps({"temperature": T, "threshold": threshold, **report}, indent=1), encoding="utf-8")
    print(json.dumps(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

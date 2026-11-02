#!/usr/bin/env python3
"""Evaluate the exported int8 model on the held-out test split, compare it with the regex matcher, and time it on the CPU.

    ml\\.venv\\Scripts\\python ml\\evaluate.py [--report docs/eval/f2_report.json]

Needs the app package on the path (the backend code): run it with the ml venv; it adds backend/ to sys.path and imports only
app.nlu.local_model and app.nlu.local_matcher (no database is touched).
"""
from __future__ import annotations

import argparse
import collections
import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "ml"))
sys.path.insert(0, str(ROOT / "backend"))
from common import DATA, read_jsonl, slot_word_labels  # noqa: E402

# my intent -> the intents the older regex matcher (app.nlu.local_matcher) names for the same request
MATCHER_INTENTS = {
    "open_app": {"open_app"}, "close_app": {"close_window"}, "switch_app": {"window_control", "open_app"}, "window_control": {"window_control"},
    "open_website": {"open_website"}, "web_search": {"web_search"}, "youtube_play": {"play_youtube"},
    "youtube_pause": {"browser_tab", "media_control"}, "youtube_resume": {"browser_tab", "media_control"}, "media_control": {"media_control"},
    "browser_tab": {"browser_tab"}, "open_folder": {"open_folder"}, "open_file": {"open_file"}, "list_folder": {"list_folder"},
    "find_files": {"find_files"}, "create_folder": {"create_folder"}, "copy_file": {"copy"}, "move_file": {"move"}, "rename_file": {"rename"},
    "delete_file": {"delete"}, "restore_file": {"restore"}, "read_file": {"read_file"}, "write_file": {"write_file"},
    "volume_set": {"system_setting"}, "volume_change": {"system_setting"}, "brightness_set": {"system_setting"}, "wifi_toggle": {"system_setting"},
    "bluetooth_toggle": {"system_setting"}, "dark_mode": {"system_setting"}, "battery_status": {"system_setting"}, "screenshot": {"screenshot"},
    "whatsapp_draft": {"whatsapp_draft"}, "email_compose": {"email_draft"}, "install_app": {"app_install"}, "terminal_run": {"terminal"},
    "ui_click": {"ui_control"}, "ui_type": {"ui_control"}, "memory_remember": {"memory"}, "memory_recall": {"memory"}, "summarise": {"summarise"},
    "web_answer": {"web_answer"}, "chat": {"chat"},
}


def per_intent(gold: list[str], pred: list[str], intents: list[str]) -> dict:
    rows = {}
    for intent in intents:
        tp = sum(1 for g, p in zip(gold, pred) if g == intent and p == intent)
        fp = sum(1 for g, p in zip(gold, pred) if g != intent and p == intent)
        fn = sum(1 for g, p in zip(gold, pred) if g == intent and p != intent)
        n = tp + fn
        if n == 0 and fp == 0:
            continue
        pr, rc = tp / (tp + fp) if tp + fp else 0.0, tp / n if n else 0.0
        rows[intent] = {"support": n, "precision": round(pr, 3), "recall": round(rc, 3), "f1": round(2 * pr * rc / (pr + rc), 3) if pr + rc else 0.0}
    return rows


def slot_f1(model, rows) -> dict:
    tp = fp = fn = 0
    for row, pred in rows:
        gold = {k: str(v).casefold() for k, v in (row.get("slots") or {}).items() if v}
        got = {k: str(v).casefold().strip() for k, v in (pred.slots if pred else {}).items()}
        for k, v in gold.items():
            if got.get(k) == v:
                tp += 1
            else:
                fn += 1
        fp += sum(1 for k, v in got.items() if gold.get(k) != v)
    pr, rc = tp / (tp + fp) if tp + fp else 0.0, tp / (tp + fn) if tp + fn else 0.0
    return {"precision": round(pr, 3), "recall": round(rc, 3), "f1": round(2 * pr * rc / (pr + rc), 3) if pr + rc else 0.0, "gold_slots": tp + fn}


def evaluate_split(model, rows: list[dict], intents: list[str]) -> tuple[dict, list]:
    preds = [model.predict(r["text"]) for r in rows]
    gold = [r["intent"] for r in rows]
    guess = [p.intent if p else "?" for p in preds]
    acc = sum(g == p for g, p in zip(gold, guess)) / len(rows)
    langs = collections.defaultdict(lambda: [0, 0])
    for r, p in zip(rows, guess):
        langs[r["lang"]][0] += 1
        langs[r["lang"]][1] += int(p == r["intent"])
    confident = [(g == p) for g, p, pr in zip(gold, guess, preds) if pr and pr.confident]
    confusion = collections.Counter((g, p) for g, p in zip(gold, guess) if g != p)
    wrong_confident = sum(1 for g, p, pr in zip(gold, guess, preds) if pr and pr.confident and g != p)
    result = {
        "n": len(rows), "intent_accuracy": round(acc, 4),
        "per_language_accuracy": {k: {"n": n, "accuracy": round(c / n, 3)} for k, (n, c) in sorted(langs.items())},
        "confident_share": round(len(confident) / len(rows), 3), "accuracy_when_confident": round(sum(confident) / len(confident), 4) if confident else None,
        "wrong_and_confident": wrong_confident, "slot": slot_f1(model, list(zip(rows, preds))),
        "per_intent": per_intent(gold, guess, intents),
        "top_confusions": [{"gold": g, "predicted": p, "count": c} for (g, p), c in confusion.most_common(15)],
    }
    return result, preds


def regex_baseline(rows: list[dict]) -> dict:
    from app.nlu import THRESHOLD, match
    answered = right = covered = 0
    for r in rows:
        want = MATCHER_INTENTS.get(r["intent"])
        if not want:
            continue
        covered += 1
        try:
            result = match(r["text"])
        except Exception:  # noqa: BLE001
            continue
        if result.plan is None or result.confidence < THRESHOLD:
            continue
        answered += 1
        right += int(result.plan.intent in want)
    return {"sentences_it_could_be_asked": covered, "answered": answered, "answered_share": round(answered / covered, 3) if covered else 0,
            "correct_of_answered": right, "accuracy_of_answered": round(right / answered, 3) if answered else None,
            "accuracy_over_all": round(right / covered, 3) if covered else 0}


def latency(model, rows: list[dict]) -> dict:
    sample = [r["text"] for r in rows][:200]
    for text in sample[:10]:
        model.predict(text)
    ms = []
    for text in sample:
        t = time.perf_counter()
        model.predict(text)
        ms.append((time.perf_counter() - t) * 1000)
    ms.sort()
    return {"runs": len(ms), "p50_ms": round(statistics.median(ms), 1), "p90_ms": round(ms[int(len(ms) * 0.9) - 1], 1), "max_ms": round(ms[-1], 1)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", default=str(ROOT / "docs" / "eval" / "f2_report.json"))
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    from app.nlu.local_model import get_model
    model = get_model()
    if model is None:
        print("no model in models/intent (run ml/retrain.ps1 first)")
        return 1
    intents = model.intents
    test, noisy = read_jsonl(DATA / "test.jsonl"), read_jsonl(DATA / "test_noisy.jsonl")
    clean_res, _ = evaluate_split(model, test, intents)
    noisy_res, _ = evaluate_split(model, noisy, intents)
    report = {"model": "xlm-roberta-base, int8 ONNX", "test_clean": clean_res, "test_noisy": noisy_res, "regex_matcher_on_test": regex_baseline(test),
              "regex_matcher_on_test_noisy": regex_baseline(noisy), "cpu_latency": latency(model, test),
              "train_log": json.loads((model_dir() / "train_log.json").read_text(encoding="utf-8")) if (model_dir() / "train_log.json").exists() else None,
              "note": "Seed data was written by one author from templates; the test split is held out by template and by filler value. Real speakers will score lower."}
    Path(a.report).parent.mkdir(parents=True, exist_ok=True)
    Path(a.report).write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    brief = {k: report[k] for k in ("regex_matcher_on_test", "cpu_latency")}
    brief["clean"] = {k: clean_res[k] for k in ("n", "intent_accuracy", "per_language_accuracy", "confident_share", "accuracy_when_confident", "wrong_and_confident", "slot")}
    brief["noisy"] = {k: noisy_res[k] for k in ("n", "intent_accuracy", "confident_share", "accuracy_when_confident", "wrong_and_confident")}
    print(json.dumps(brief, ensure_ascii=False, indent=1))
    return 0


def model_dir() -> Path:
    from app.nlu.local_model import model_dir as md
    return md()


if __name__ == "__main__":
    raise SystemExit(main())

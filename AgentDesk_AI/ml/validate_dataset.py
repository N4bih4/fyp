#!/usr/bin/env python3
"""Check the JSONL files: valid JSON, known intents, slots that belong to the intent and really appear in the text, duplicates, language balance,
at least 30 examples per intent, and no sentence in both train and test.

    python ml/validate_dataset.py [files...]      (default: data/train.jsonl data/val.jsonl data/test.jsonl data/real/*.jsonl)

Exit code 1 when there is an error; warnings do not fail it.
"""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DATA, LANGS, intent_slots, load_spec, slot_word_labels  # noqa: E402


def check(paths: list[Path], spec: dict) -> tuple[list[str], list[str], dict]:
    errors, warnings = [], []
    allowed = intent_slots(spec)
    per_intent, per_lang, per_file = collections.Counter(), collections.Counter(), {}
    texts: dict[str, set] = {}
    for path in paths:
        if not path.exists():
            continue
        seen = set()
        n = 0
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            where = f"{path.name}:{lineno}"
            try:
                row = json.loads(line)
            except ValueError:
                errors.append(f"{where}: not valid JSON")
                continue
            n += 1
            text, intent = row.get("text"), row.get("intent")
            if not isinstance(text, str) or not text.strip():
                errors.append(f"{where}: empty text")
                continue
            if intent not in allowed:
                errors.append(f"{where}: unknown intent {intent!r}")
                continue
            if row.get("lang") not in LANGS:
                errors.append(f"{where}: lang must be one of {', '.join(LANGS)} (got {row.get('lang')!r})")
            slots = row.get("slots") or {}
            if not isinstance(slots, dict):
                errors.append(f"{where}: slots must be an object")
                continue
            for name, value in slots.items():
                if name not in allowed[intent]:
                    errors.append(f"{where}: slot {name!r} does not belong to intent {intent!r} (allowed: {', '.join(allowed[intent]) or 'none'})")
                elif value and not any(label.endswith(name) for label in slot_word_labels(text, {name: value})):
                    errors.append(f"{where}: slot {name}={value!r} does not appear in the text {text!r}")
            key = text.casefold().strip()
            if key in seen:
                warnings.append(f"{where}: duplicate sentence {text!r}")
            seen.add(key)
            per_intent[intent] += 1
            per_lang[row.get("lang")] += 1
        texts[path.name] = seen
        per_file[path.name] = n
    if "train.jsonl" in texts and "test.jsonl" in texts:
        leak = texts["train.jsonl"] & texts["test.jsonl"]
        if leak:
            errors.append(f"{len(leak)} sentences are in both train and test, e.g. {sorted(leak)[:3]}")
    if per_intent:
        for intent in allowed:
            if per_intent[intent] < 30:
                warnings.append(f"intent {intent}: only {per_intent[intent]} examples (aim for 30+)")
        total = sum(per_lang.values())
        for lang in LANGS:
            share = per_lang[lang] / total if total else 0
            if share < 0.10:
                warnings.append(f"language {lang}: only {share:.0%} of the sentences (aim for 15-35%)")
    return errors, warnings, {"files": per_file, "intents": dict(per_intent), "languages": dict(per_lang)}


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    args = [Path(a) for a in sys.argv[1:]]
    if not args:
        args = [DATA / "train.jsonl", DATA / "val.jsonl", DATA / "test.jsonl"] + sorted((DATA / "real").glob("*.jsonl"))
    errors, warnings, stats = check(args, load_spec())
    print(json.dumps(stats, ensure_ascii=False))
    for w in warnings[:40]:
        print("WARN ", w)
    for e in errors[:60]:
        print("ERROR", e)
    print(f"{len(errors)} errors, {len(warnings)} warnings")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())

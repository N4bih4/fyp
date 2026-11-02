#!/usr/bin/env python3
"""Build data/train.jsonl, data/val.jsonl, data/test.jsonl and data/labels.json from data/intents.yaml (+ real sentences in data/real/*.jsonl).

    python ml/build_dataset.py [--per-lang 1500] [--seed 7]

The TEST split is held out by TEMPLATE and by slot VALUE: no test sentence uses a template or a filler value that training saw (for the seed data),
so the numbers are not just "the model remembered the sentence". Real sentences (data/real/*.jsonl) are split 80/20 by a hash of their text.
Training rows get augmentation (typos, Roman Urdu spelling variants, ASR-style mistakes, lower-casing, punctuation); test rows stay clean AND a
second, noisy copy of the test set is written to data/test_noisy.jsonl.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DATA, LANGS, PLACEHOLDER, label_list, load_spec, read_jsonl, slot_name, split_templates, write_jsonl  # noqa: E402

ROMAN_VARIANTS = {"karo": ["kro", "karo", "kero"], "kar": ["kr", "kar"], "kholo": ["kholo", "khollo", "kholdo", "kholu"], "nahi": ["nahin", "nai", "nahi", "nhi"],
                  "gana": ["gaana", "gana", "gaanaa"], "chalao": ["chalao", "chalaao", "chala", "chalau"], "chala": ["chala", "chalaa"], "band": ["band", "bund", "bnd"],
                  "mein": ["mein", "main", "me", "mai"], "aur": ["aur", "or", "our"], "hai": ["hai", "he", "hy", "hay"], "mujhe": ["mujhe", "mujhay", "mjhe"],
                  "dikhao": ["dikhao", "dikhaao", "dikha"], "banao": ["banao", "banaao", "bnao"], "kya": ["kya", "kia", "kiya"], "bhej": ["bhej", "bhaij", "bhez"],
                  "awaz": ["awaz", "aawaz", "awaaz"], "barhao": ["barhao", "badhao", "barha"], "pe": ["pe", "par", "pr"], "dobara": ["dobara", "dubara", "dobaraa"]}
ASR_SWAPS = {"wifi": ["why fi", "wi-fi", "wife i"], "youtube": ["you tube", "u tube", "youtub"], "chrome": ["crome", "chrom", "krom"], "notepad": ["note pad", "not pad"],
             "bluetooth": ["blue tooth", "bluetoth"], "whatsapp": ["whats app", "whatsup", "what's app"], "excel": ["excell", "xl"], "spotify": ["spotifi", "spot if i"],
             "screenshot": ["screen shot"], "download": ["down load"], "downloads": ["down loads"], "folder": ["folders", "foldar"], "explorer": ["explorar"],
             "calculator": ["calculater", "calc"], "volume": ["volum", "volium"], "brightness": ["brightnes", "brightnes"]}


MIN_PER_INTENT = 150


def fills(rng: random.Random, spec: dict, template: str, held: dict[str, tuple[set, bool]]) -> dict[str, str]:
    values = {}
    for ph in sorted(set(PLACEHOLDER.findall(template))):
        pool = list(spec["fillers"].get(ph) or spec["fillers"].get(slot_name(ph)) or [])
        if not pool:
            raise SystemExit(f"no fillers for {{{ph}}} in template: {template}")
        keep = held.get(ph)
        if keep:
            test_values, want_test = keep
            filtered = [v for v in pool if (v in test_values) == want_test]
            pool = filtered or pool
        values[ph] = str(rng.choice(pool))
    return values


def render(template: str, values: dict[str, str]) -> tuple[str, dict[str, str]]:
    slots: dict[str, str] = {}
    text = template
    for ph, value in values.items():
        text = text.replace("{" + ph + "}", value)
        slots.setdefault(slot_name(ph), value)
    return text, slots


def noisy(rng: random.Random, text: str, slots: dict[str, str], lang: str) -> str:
    """ASR-style and typing mistakes that never touch the slot values."""
    protected = {w.casefold() for v in slots.values() for w in str(v).replace(",", " ").split()}
    out = []
    for word in text.split():
        core = word.strip(".,?!")
        low = core.casefold()
        if low in protected:
            out.append(word)
            continue
        r = rng.random()
        if lang == "roman_ur" and low in ROMAN_VARIANTS and r < 0.5:
            out.append(rng.choice(ROMAN_VARIANTS[low]))
        elif low in ASR_SWAPS and r < 0.4:
            out.append(rng.choice(ASR_SWAPS[low]))
        elif lang in ("en", "roman_ur") and len(low) > 3 and r < 0.07:
            i = rng.randrange(1, len(low) - 1)
            kind = rng.choice(["swap", "drop", "dup"])
            chars = list(low)
            if kind == "swap":
                chars[i], chars[i + 1 if i + 1 < len(chars) else i - 1] = chars[i + 1 if i + 1 < len(chars) else i - 1], chars[i]
            elif kind == "drop":
                del chars[i]
            else:
                chars.insert(i, chars[i])
            out.append("".join(chars))
        elif low in ("the", "a", "please", "to") and r < 0.25:
            continue
        else:
            out.append(word)
    text = " ".join(out) or text
    r = rng.random()
    if r < 0.3:
        text = text.lower()
    elif r < 0.4:
        text = text.capitalize()
    if rng.random() < 0.15:
        text += rng.choice([".", "?", " please", " yaar", " na"] if lang != "ur" else ["۔", "؟"])
    return text


def build(spec: dict, per_lang: int, seed: int) -> tuple[list, list, list, list]:
    rng = random.Random(seed)
    train, test = [], []
    # value-held-out fillers: ~25% of each slot's values go to the test pool only (the same words may recur in real use; that is why it is a harsh split)
    held: dict[str, tuple[set, bool]] = {}
    held_test: dict[str, tuple[set, bool]] = {}
    for ph, pool in spec["fillers"].items():
        pool = [str(v) for v in pool]
        if len(pool) >= 8:
            test_vals = set(rng.sample(pool, max(2, len(pool) // 4)))
            held[ph] = (test_vals, False)
            held_test[ph] = (test_vals, True)
    for intent, body in spec["intents"].items():
        for lang in LANGS:
            templates = split_templates(body.get(lang, ""))
            if not templates:
                continue
            rng.shuffle(templates)
            n_test = max(1, round(len(templates) * 0.25)) if len(templates) >= 3 else 0
            test_templates, train_templates = templates[:n_test], templates[n_test:]
            for group, bucket, pools in ((train_templates, train, held), (test_templates, test, held_test)):
                if not group:
                    continue
                each = 8 if bucket is train else 6
                for template in group:
                    correction = template.startswith("!")
                    template = template.lstrip("!").strip()
                    seen = set()
                    for _ in range(each * 4):
                        values = fills(rng, spec, template, pools)
                        text, slots = render(template, values)
                        if text in seen:
                            continue
                        seen.add(text)
                        row = {"text": text, "intent": intent, "slots": {s: slots.get(s) for s in sorted(set(slot_name(p) for p in PLACEHOLDER.findall(template)))},
                               "lang": lang, "is_correction": correction or intent == "correction"}
                        bucket.append(row)
                        if len(seen) >= each:
                            break
    return train, test, [], []


def augment(rng: random.Random, rows: list[dict], copies: int = 2) -> list[dict]:
    out = []
    for row in rows:
        for _ in range(copies):
            text = noisy(rng, row["text"], {k: v for k, v in row["slots"].items() if v}, row["lang"])
            if text != row["text"]:
                out.append({**row, "text": text})
    return out


def real_rows() -> tuple[list[dict], list[dict]]:
    train, test = [], []
    for path in sorted((DATA / "real").glob("*.jsonl")) if (DATA / "real").exists() else []:
        for row in read_jsonl(path):
            bucket = test if int(hashlib.sha1(row["text"].encode("utf-8")).hexdigest(), 16) % 5 == 0 else train
            row.setdefault("slots", {})
            row.setdefault("lang", "en")
            row.setdefault("is_correction", False)
            row["source"] = "real"
            bucket.append(row)
    return train, test


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-lang", type=int, default=1500, help="target clean training sentences per language (before augmentation)")
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    spec = load_spec()
    train, test, _, _ = build(spec, a.per_lang, a.seed)
    rt, rs = real_rows()
    rng = random.Random(a.seed + 1)
    train = train + rt
    test = test + rs
    texts_in_test = {r["text"].casefold() for r in test}
    train = [r for r in train if r["text"].casefold() not in texts_in_test]      # no sentence is in both
    train += augment(rng, train, copies=1)
    # every intent gets at least MIN_PER_INTENT training rows: slot-less intents have few clean sentences, so add more noisy variants of them
    counts = {}
    for r in train:
        counts[r["intent"]] = counts.get(r["intent"], 0) + 1
    for intent in spec["intents"]:
        pool = [r for r in train if r["intent"] == intent]
        tries = 0
        while counts.get(intent, 0) < MIN_PER_INTENT and pool and tries < 40:
            tries += 1
            for extra in augment(rng, pool, copies=1):
                train.append(extra)
                counts[intent] = counts.get(intent, 0) + 1
    seen, unique = set(), []
    for r in train:
        key = r["text"].casefold()
        if key not in seen:
            seen.add(key)
            unique.append(r)
    rng.shuffle(unique)
    cut = max(1, len(unique) // 10)
    val, train = unique[:cut], unique[cut:]
    test_noisy = [{**r, "text": noisy(rng, r["text"], {k: v for k, v in r["slots"].items() if v}, r["lang"])} for r in test]
    write_jsonl(DATA / "train.jsonl", train)
    write_jsonl(DATA / "val.jsonl", val)
    write_jsonl(DATA / "test.jsonl", test)
    write_jsonl(DATA / "test_noisy.jsonl", test_noisy)
    (DATA / "labels.json").write_text(json.dumps(label_list(spec), ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"train": len(train), "val": len(val), "test": len(test), "test_noisy": len(test_noisy), "intents": len(spec["intents"]),
                      "real_train": len(rt), "real_test": len(rs)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

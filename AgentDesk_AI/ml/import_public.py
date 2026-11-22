#!/usr/bin/env python3
"""Import public datasets into data/public/*.jsonl (TRAIN ONLY: they never enter the honest test set).

    python ml/import_public.py            # needs ml/public_cache/massive/1.1/data/*.jsonl and ml/public_cache/clinc.json (see --help for URLs)

* MASSIVE (Amazon, CC-BY 4.0): en-US, hi-IN, ur-PK with slot annotations. Mapped to our intents (volume, music->youtube_play, email, reminder,
  questions/weather/news -> web_answer, greetings/jokes -> chat). Scenarios we do not support (lights, taxi, takeaway, ...) become `unknown`.
* hi-IN is also transliterated to Latin letters -> lang "roman_ur" (Hinglish-style; rough, but spoken Hindi and Urdu share grammar and words).
* CLINC150 out-of-scope sentences (CC-BY-3.0) -> `unknown`.
"""
from __future__ import annotations

import hashlib
import json
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "ml"))
from common import DATA, write_jsonl  # noqa: E402

CACHE = ROOT / "ml" / "public_cache"
OUT = DATA / "public"
LOCALES = {"en-US": "en", "hi-IN": "hi", "ur-PK": "ur"}
CAP_MAPPED, CAP_UNKNOWN = 100, 200             # rows per (intent, language): kept small so public data does not drown the desktop intents

# MASSIVE intent -> (our intent, {MASSIVE slot: our slot}); None slot map = row must carry no slots (or only those listed)
MAP = {
    "audio_volume_up": ("volume_change", {}), "audio_volume_down": ("volume_change", {}), "audio_volume_mute": ("volume_change", {}),
    "play_music": ("youtube_play", {"song_name": "query", "artist_name": "query"}),
    "email_sendemail": ("email_compose", {"person": "recipient"}),
    "alarm_set": ("reminder", {"time": "time"}),
    "qa_factoid": ("web_answer", "question"), "qa_definition": ("web_answer", "question"), "qa_maths": ("web_answer", "question"),
    "qa_currency": ("web_answer", "question"), "weather_query": ("web_answer", "question"), "news_query": ("web_answer", "question"),
    "general_greet": ("chat", {}), "general_joke": ("chat", {}), "general_quirky": ("chat", {}),
}
UNKNOWN_SCENARIOS = {"iot", "transport", "takeaway", "recommendation", "cooking", "lists", "social", "calendar", "datetime"}
SKIP = {"play_radio", "play_podcasts", "play_audiobook", "play_game", "music_settings", "music_query", "music_likeness", "music_dislikeness",
        "audio_volume_other", "email_query", "email_addcontact", "email_querycontact", "qa_stock", "alarm_query", "alarm_remove"}
SPAN = re.compile(r"\[([\w ]+?) : (.+?)\]")

# ---- Devanagari -> Latin (rough Hinglish spelling; final schwa dropped)
VOW = {"अ": "a", "आ": "a", "इ": "i", "ई": "i", "उ": "u", "ऊ": "u", "ए": "e", "ऐ": "ai", "ओ": "o", "औ": "au", "ऑ": "o", "ऋ": "ri"}
MAT = {"ा": "a", "ि": "i", "ी": "i", "ु": "u", "ू": "u", "े": "e", "ै": "ai", "ो": "o", "ौ": "au", "ॉ": "o", "ृ": "ri"}
CON = {"क": "k", "ख": "kh", "ग": "g", "घ": "gh", "ङ": "n", "च": "ch", "छ": "chh", "ज": "j", "झ": "jh", "ञ": "n", "ट": "t", "ठ": "th", "ड": "d", "ढ": "dh",
       "ण": "n", "त": "t", "थ": "th", "द": "d", "ध": "dh", "न": "n", "प": "p", "फ": "f", "ब": "b", "भ": "bh", "म": "m", "य": "y", "र": "r", "ल": "l",
       "व": "v", "श": "sh", "ष": "sh", "स": "s", "ह": "h", "क़": "q", "ख़": "kh", "ग़": "gh", "ज़": "z", "ड़": "r", "ढ़": "rh", "फ़": "f"}
NUKTA, VIRAMA, ANUS = "़", "्", {"ं": "n", "ँ": "n", "ः": "h"}
DIGITS = {c: str(i) for i, c in enumerate("०१२३४५६७८९")}


def translit_word(word: str) -> str:
    word = word.replace("क" + NUKTA, "क़").replace("ख" + NUKTA, "ख़").replace("ग" + NUKTA, "ग़").replace("ज" + NUKTA, "ज़").replace("फ" + NUKTA, "फ़")
    word = word.replace("ड" + NUKTA, "ड़").replace("ढ" + NUKTA, "ढ़")
    out, i = [], 0
    while i < len(word):
        ch = word[i]
        nxt = word[i + 1] if i + 1 < len(word) else ""
        if ch in CON:
            out.append(CON[ch])
            if nxt == VIRAMA:
                i += 2
                continue
            if nxt in MAT:
                out.append(MAT[nxt])
                i += 2
                continue
            out.append("\0")                       # inherent 'a', decided below
        elif ch in VOW:
            out.append(VOW[ch])
        elif ch in ANUS:
            out.append(ANUS[ch])
        elif ch in DIGITS:
            out.append(DIGITS[ch])
        elif ch == VIRAMA or ch == NUKTA:
            pass
        else:
            out.append(ch)
        i += 1
    s = "".join(out)
    s = s.rstrip("\0") if s.endswith("\0") else s
    return s.replace("\0", "a")


def translit(text: str) -> str:
    return " ".join(translit_word(w) for w in text.split())


def parse(annot: str) -> tuple[str, list[tuple[str, str]]]:
    spans = [(m.group(1), m.group(2).strip()) for m in SPAN.finditer(annot)]
    text = SPAN.sub(lambda m: m.group(2).strip(), annot)
    return re.sub(r"\s+", " ", text).strip(), spans


def convert(row: dict, lang: str) -> dict | None:
    intent_in = row["intent"]
    text, spans = parse(row["annot_utt"])
    if intent_in in SKIP:
        return None
    if intent_in in MAP:
        intent, smap = MAP[intent_in]
        if smap == "question":
            slots = {"question": text}
        else:
            slots, used = {}, set()
            for name, value in spans:
                target = smap.get(name)
                if not target or target in used:
                    return None                       # a slot we cannot express: skip the row rather than teach a wrong label
                slots[target] = value
                used.add(target)
            if intent == "reminder" and "time" not in slots:
                return None
    elif row["scenario"] in UNKNOWN_SCENARIOS:
        intent, slots = "unknown", {}
    else:
        return None
    return {"text": text, "intent": intent, "slots": slots, "lang": lang, "is_correction": False, "source": "massive"}


def main() -> int:
    rng = random.Random(11)
    rows: list[dict] = []
    base = CACHE / "massive" / "1.1" / "data"
    for locale, lang in LOCALES.items():
        path = base / f"{locale}.jsonl"
        if not path.exists():
            print(f"missing {path}: download https://amazon-massive-nlu-dataset.s3.amazonaws.com/amazon-massive-dataset-1.1.tar.gz and unpack into {CACHE / 'massive'}")
            return 1
        for line in path.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            out = convert(r, lang)
            if not out:
                continue
            rows.append(out)
            if lang == "hi":                          # Roman Urdu / Hinglish copy of the Hindi sentence (slot values transliterated the same way)
                rows.append({**out, "text": translit(out["text"]), "slots": {k: translit(v) for k, v in out["slots"].items()}, "lang": "roman_ur",
                             "source": "massive_translit"})
    clinc = CACHE / "clinc.json"
    if clinc.exists():
        data = json.loads(clinc.read_text(encoding="utf-8"))
        for key in ("oos_train", "oos_val", "oos_test"):
            for text, _ in data.get(key, []):
                rows.append({"text": text, "intent": "unknown", "slots": {}, "lang": "en", "is_correction": False, "source": "clinc_oos"})
    else:
        print("clinc.json missing (optional): https://raw.githubusercontent.com/clinc/oos-eval/master/data/data_full.json")

    # drop rows whose slot words are not in the sentence, dedupe, cap per (intent, lang)
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    seen = set()
    for r in rows:
        low = r["text"].casefold()
        if not r["text"] or low in seen or re.search(r"\b\w\.", r["text"]) or any(v.casefold() not in low for v in r["slots"].values()):
            continue
        seen.add(low)
        groups[(r["intent"], r["lang"])].append(r)
    train, test = [], []
    for (intent, lang), items in sorted(groups.items()):
        rng.shuffle(items)
        items = items[: (CAP_UNKNOWN if intent == "unknown" else CAP_MAPPED)]
        for r in items:
            bucket = test if int(hashlib.sha1(r["text"].encode("utf-8")).hexdigest(), 16) % 20 == 0 else train
            bucket.append(r)
    OUT.mkdir(parents=True, exist_ok=True)
    write_jsonl(OUT / "public_train.jsonl", train)
    write_jsonl(DATA / "test_public.jsonl", test)
    print(json.dumps({"public_train": len(train), "test_public": len(test),
                      "by_intent": dict(Counter(r["intent"] for r in train)), "by_lang": dict(Counter(r["lang"] for r in train))}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

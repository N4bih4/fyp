"""Shared helpers for the local intent+slot model: reading data/intents.yaml, slot names, and turning (text, slots) into word labels.

Runs with any Python that has PyYAML (the backend venv is enough); only train.py / export_onnx.py need the ml venv.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
INTENTS_YAML = DATA / "intents.yaml"
LANGS = ("en", "roman_ur", "ur", "hi")
PLACEHOLDER = re.compile(r"\{(\w+)\}")
_SUFFIX = re.compile(r"_(ur|hi)$")


def slot_name(placeholder: str) -> str:
    """{app_ur} and {app_hi} are fillers in another script for the slot 'app'."""
    return _SUFFIX.sub("", placeholder)


def load_spec(path: Path = INTENTS_YAML) -> dict:
    import yaml
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def intent_slots(spec: dict) -> dict[str, list[str]]:
    """Every intent -> the slot names it may carry (placeholders in its templates + the `slots:` list)."""
    out: dict[str, list[str]] = {}
    for name, body in spec["intents"].items():
        found = set(body.get("slots") or [])
        for lang in LANGS:
            for template in split_templates(body.get(lang, "")):
                found.update(slot_name(p) for p in PLACEHOLDER.findall(template))
        out[name] = sorted(found)
    return out


def split_templates(line: str) -> list[str]:
    return [t.strip() for t in str(line or "").split(" | ") if t.strip()]


def all_slots(spec: dict) -> list[str]:
    return sorted({s for slots in intent_slots(spec).values() for s in slots})


def label_list(spec: dict) -> dict:
    slots = all_slots(spec)
    tags = ["O"] + [f"{p}-{s}" for s in slots for p in ("B", "I")]
    return {"intents": sorted(spec["intents"]), "tags": tags, "slots": slots}


def words_of(text: str) -> list[tuple[str, int, int]]:
    """Whitespace words with their character span."""
    return [(m.group(0), m.start(), m.end()) for m in re.finditer(r"\S+", text)]


def _strip_punct(word: str) -> str:
    return word.strip(".,?!;:\"'()۔؟،।")


def slot_word_labels(text: str, slots: dict) -> list[str]:
    """BIO label per whitespace word from the slot VALUES found in the text (whole-word, first free occurrence, case-insensitive)."""
    words = words_of(text)
    norm = [_strip_punct(w).casefold() for w, _, _ in words]
    labels = ["O"] * len(words)
    for name, value in (slots or {}).items():
        if not value:
            continue
        target = [_strip_punct(t).casefold() for t in str(value).split()]
        if not target:
            continue
        for i in range(len(words) - len(target) + 1):
            if norm[i:i + len(target)] == target and all(label == "O" for label in labels[i:i + len(target)]):
                labels[i] = f"B-{name}"
                for j in range(1, len(target)):
                    labels[i + j] = f"I-{name}"
                break
    return labels


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")

"""The local intent + slot model (docs/DATASET_GUIDE.md, ml/): xlm-roberta-base fine-tuned on the project's dataset, exported to int8 ONNX.

Runs on the CPU with onnxruntime + tokenizers + numpy only (no torch). `get_model()` returns None when the model files or those packages
are not there: nothing else depends on it, and the app works exactly as before. The model files live in `models/intent/` (not in git, ~100 MB;
build them with `ml\\retrain.ps1`).

predict(text) -> Prediction(intent, confidence, slots, top). `confidence >= THRESHOLD` (0.85) means "act on it"; below that the caller asks the
planner. A prediction only NAMES an intent and slot words: turning it into a plan, naming the tool and deciding risk stays server-side as for every plan.
"""
from __future__ import annotations

import json
import os
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path

THRESHOLD = 0.85
MAX_LEN = 48
_PUNCT = ".,?!;:\"'()۔؟،।"
_lock = threading.Lock()
_model: "LocalIntentModel | None" = None
_tried = False


@dataclass
class Prediction:
    intent: str
    confidence: float
    slots: dict[str, str] = field(default_factory=dict)
    top: list[tuple[str, float]] = field(default_factory=list)
    ms: float = 0.0

    @property
    def confident(self) -> bool:
        return self.confidence >= THRESHOLD


def model_dir() -> Path:
    override = os.environ.get("AGENTDESK_INTENT_MODEL")
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[3] / "models" / "intent"


class LocalIntentModel:
    def __init__(self, directory: Path):
        import numpy as np
        import onnxruntime as ort
        from tokenizers import Tokenizer

        self.np = np
        labels = json.loads((directory / "labels.json").read_text(encoding="utf-8"))
        self.intents, self.tags = labels["intents"], labels["tags"]
        keep = json.loads((directory / "vocab_map.json").read_text(encoding="utf-8"))
        self.id_map = {old: new for new, old in enumerate(keep)}
        self.unk = self.id_map.get(3, 0)
        self.tok = Tokenizer.from_file(str(directory / "tokenizer.json"))
        self.tok.no_truncation()
        options = ort.SessionOptions()
        options.intra_op_num_threads = max(1, min(8, os.cpu_count() or 4))
        options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self.session = ort.InferenceSession(str(directory / "intent_int8.onnx"), options, providers=["CPUExecutionProvider"])

    def _words(self, text: str) -> list[str]:
        return re.findall(r"\S+", text)

    def predict(self, text: str) -> Prediction | None:
        import time

        np = self.np
        words = self._words(text)
        if not words:
            return None
        started = time.perf_counter()
        enc = self.tok.encode(words, is_pretokenized=True)
        ids, wids = enc.ids[:MAX_LEN], enc.word_ids[:MAX_LEN]
        arr = np.array([[self.id_map.get(i, self.unk) for i in ids]], dtype=np.int64)
        mask = np.ones_like(arr)
        intent_logits, slot_logits = self.session.run(None, {"input_ids": arr, "attention_mask": mask})
        z = intent_logits[0] - intent_logits[0].max()
        probs = np.exp(z) / np.exp(z).sum()
        order = probs.argsort()[::-1]
        pred = slot_logits[0].argmax(-1)
        tags, prev = [], None
        word_tag = ["O"] * len(words)
        for pos, wid in enumerate(wids):
            if wid is not None and wid != prev:
                word_tag[wid] = self.tags[int(pred[pos])]
            prev = wid
        slots: dict[str, str] = {}
        current, name = [], None
        for word, tag in zip(words + [""], word_tag + ["O"]):
            if tag.startswith("I-") and name == tag[2:]:
                current.append(word)
                continue
            if name and current:
                slots.setdefault(name, " ".join(current).strip(_PUNCT))
            current, name = ([word], tag[2:]) if tag.startswith(("B-", "I-")) else ([], None)
        return Prediction(self.intents[int(order[0])], float(probs[order[0]]), slots,
                          [(self.intents[int(i)], float(probs[i])) for i in order[:3]], (time.perf_counter() - started) * 1000)


def get_model() -> "LocalIntentModel | None":
    """The loaded model, or None (files missing, packages missing, or AGENTDESK_INTENT_MODEL=off). Loaded once."""
    global _model, _tried
    with _lock:
        if _tried:
            return _model
        _tried = True
        if os.environ.get("AGENTDESK_INTENT_MODEL", "").lower() == "off":
            return None
        directory = model_dir()
        if not (directory / "intent_int8.onnx").exists():
            return None
        try:
            _model = LocalIntentModel(directory)
        except Exception:  # noqa: BLE001 - a missing package or a broken file means "no local model", never a crash
            _model = None
        return _model


def set_model(model: "LocalIntentModel | None") -> None:
    global _model, _tried
    with _lock:
        _model, _tried = model, True

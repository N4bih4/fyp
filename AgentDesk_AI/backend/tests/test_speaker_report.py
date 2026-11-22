"""ml/speaker_report.py: per-speaker accuracy of the local intent model."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("speaker_report", ROOT / "ml" / "speaker_report.py")
speaker_report = importlib.util.module_from_spec(spec)
sys.modules["speaker_report"] = speaker_report
spec.loader.exec_module(speaker_report)


class FakeModel:
    threshold = 0.9

    def __init__(self, table):
        self.table = table

    def predict(self, text):
        intent, confidence = self.table[text]
        return SimpleNamespace(intent=intent, confidence=confidence, confident=confidence >= self.threshold)


def test_score_separates_overall_accuracy_from_accuracy_when_the_model_answers():
    model = FakeModel({"chrome kholo": ("open_app", 0.99), "volume kam": ("volume_change", 0.95), "kuch aur": ("unknown", 0.3), "gana lagao": ("youtube_pause", 0.97)})
    rows = [{"text": "chrome kholo", "intent": "open_app"}, {"text": "volume kam", "intent": "volume_change"},
            {"text": "kuch aur", "intent": "open_app"}, {"text": "gana lagao", "intent": "youtube_play"}]
    result = speaker_report.score(rows, model)
    assert result["n"] == 4 and result["accuracy"] == 0.5                 # two of four labelled right
    assert result["answered"] == 0.75                                    # three were confident enough to act
    assert abs(result["accuracy_when_answered"] - 2 / 3) < 1e-9          # and two of those three were right: the number that decides trust
    assert ("youtube_play -> youtube_pause", 1) in result["wrong"]


def test_rows_without_text_or_intent_are_ignored(tmp_path):
    path = tmp_path / "history_x.jsonl"
    path.write_text('{"text": "a", "intent": "open_app"}\n{"text": "", "intent": "open_app"}\n{"text": "b"}\n\n')
    assert len(speaker_report.load(path)) == 1

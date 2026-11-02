"""F2: the dataset (data/intents.yaml -> JSONL), its validator, and the run-time wrapper of the local intent model. The trained model itself is
measured by ml/evaluate.py (docs/eval/f2_report.json); these tests need no torch and no model file."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ml"))

import build_dataset  # noqa: E402
import validate_dataset  # noqa: E402
from common import LANGS, PLACEHOLDER, label_list, load_spec, slot_name, slot_word_labels, split_templates  # noqa: E402

from app.nlu import local_model  # noqa: E402

SPEC = load_spec()


def test_the_spec_has_about_sixty_intents_and_every_intent_speaks_english_and_roman_urdu():
    assert len(SPEC["intents"]) >= 55
    for name, body in SPEC["intents"].items():
        assert split_templates(body.get("en")) and split_templates(body.get("roman_ur")), name
    assert sum(1 for b in SPEC["intents"].values() if split_templates(b.get("ur")) and split_templates(b.get("hi"))) >= 55


def test_every_placeholder_has_fillers():
    for name, body in SPEC["intents"].items():
        for lang in LANGS:
            for template in split_templates(body.get(lang)):
                for ph in PLACEHOLDER.findall(template):
                    assert SPEC["fillers"].get(ph) or SPEC["fillers"].get(slot_name(ph)), (name, template, ph)


def test_the_bio_labels_follow_the_slot_words():
    assert slot_word_labels("play Atif Aslam songs on youtube", {"query": "Atif Aslam songs"}) == ["O", "B-query", "I-query", "I-query", "O", "O"]
    assert slot_word_labels("open Chrome.", {"app": "chrome"}) == ["O", "B-app"]
    assert slot_word_labels("کروم کھولو۔", {"app": "کروم"}) == ["B-app", "O"]
    assert slot_word_labels("hello there", {"app": None}) == ["O", "O"]


def test_build_makes_valid_files_with_no_train_test_leak(tmp_path, monkeypatch):
    monkeypatch.setattr(build_dataset, "DATA", tmp_path)
    monkeypatch.setattr(sys, "argv", ["build_dataset", "--per-lang", "300"])
    assert build_dataset.main() == 0
    errors, warnings, stats = validate_dataset.check([tmp_path / "train.jsonl", tmp_path / "val.jsonl", tmp_path / "test.jsonl"], SPEC)
    assert errors == [] and stats["files"]["test.jsonl"] > 100
    assert set(stats["languages"]) == set(LANGS)
    train = {json.loads(l)["text"].casefold() for l in (tmp_path / "train.jsonl").read_text(encoding="utf-8").splitlines()}
    test = {json.loads(l)["text"].casefold() for l in (tmp_path / "test.jsonl").read_text(encoding="utf-8").splitlines()}
    assert not train & test
    labels = json.loads((tmp_path / "labels.json").read_text(encoding="utf-8"))
    assert labels == label_list(SPEC) and labels["tags"][0] == "O"


def test_the_correction_example_from_the_bug_report_is_in_the_data():
    templates = split_templates(SPEC["intents"]["youtube_play"]["en"])
    assert any(t.startswith("!") and "not only open the url" in t for t in templates)


def test_the_validator_finds_the_usual_mistakes(tmp_path):
    f = tmp_path / "bad.jsonl"
    rows = [{"text": "open chrome", "intent": "open_app", "slots": {"app": "Chrome"}, "lang": "en"},
            {"text": "open chrome", "intent": "open_app", "slots": {"app": "Chrome"}, "lang": "en"},
            {"text": "open firefox", "intent": "open_app", "slots": {"app": "Edge"}, "lang": "en"},
            {"text": "do it", "intent": "no_such_intent", "slots": {}, "lang": "en"},
            {"text": "open chrome", "intent": "open_app", "slots": {"colour": "red"}, "lang": "en"},
            {"text": "open chrome", "intent": "open_app", "slots": {}, "lang": "klingon"}]
    f.write_text("\n".join(json.dumps(r) for r in rows) + "\nnot json\n", encoding="utf-8")
    errors, warnings, _ = validate_dataset.check([f], SPEC)
    joined = "\n".join(errors)
    for needle in ("does not appear in the text", "unknown intent", "does not belong", "lang must be", "not valid JSON"):
        assert needle in joined, needle
    assert any("duplicate" in w for w in warnings)


def test_a_sentence_in_both_train_and_test_is_an_error(tmp_path):
    row = json.dumps({"text": "open chrome", "intent": "open_app", "slots": {"app": "chrome"}, "lang": "en"}) + "\n"
    (tmp_path / "train.jsonl").write_text(row, encoding="utf-8")
    (tmp_path / "test.jsonl").write_text(row, encoding="utf-8")
    errors, _, _ = validate_dataset.check([tmp_path / "train.jsonl", tmp_path / "test.jsonl"], SPEC)
    assert any("both train and test" in e for e in errors)


def test_the_model_is_optional_and_can_be_switched_off(monkeypatch, tmp_path):
    local_model.set_model(None)
    monkeypatch.setattr(local_model, "_tried", False)
    monkeypatch.setenv("AGENTDESK_INTENT_MODEL", str(tmp_path))      # an empty folder: no model file
    assert local_model.get_model() is None
    monkeypatch.setattr(local_model, "_tried", False)
    monkeypatch.setenv("AGENTDESK_INTENT_MODEL", "off")
    assert local_model.get_model() is None
    local_model.set_model(None)


class FakeSession:
    def __init__(self, n_intents, n_tags, intent, tags):
        self.n_intents, self.n_tags, self.intent, self.tags = n_intents, n_tags, intent, tags

    def run(self, _outputs, feeds):
        length = feeds["input_ids"].shape[1]
        intent = np.full((1, self.n_intents), -4.0, dtype=np.float32)
        intent[0, self.intent] = 6.0
        slot = np.zeros((1, length, self.n_tags), dtype=np.float32)
        for pos in range(length):
            slot[0, pos, self.tags.get(pos, 0)] = 5.0
        return intent, slot


class FakeEncoding:
    def __init__(self, count):
        self.ids = [0] + [10 + i for i in range(count)] + [2]
        self.word_ids = [None] + list(range(count)) + [None]


class FakeTokenizer:
    """One piece per word, with <s> and </s> around them, like the real one after the post-processor."""

    def encode(self, words, is_pretokenized=True):
        return FakeEncoding(len(words))


def make_fake(intents, tags, session):
    m = object.__new__(local_model.LocalIntentModel)
    m.np, m.intents, m.tags, m.id_map, m.unk = np, intents, tags, {i: i for i in range(100)}, 3
    m.tok, m.session = FakeTokenizer(), session
    return m


def test_the_wrapper_decodes_intent_confidence_and_slot_words():
    intents = ["chat", "open_app", "youtube_play"]
    tags = ["O", "B-app", "I-app", "B-query"]
    # words: "open File Explorer now" -> positions 1..4 (position 0 is <s>): File = B-app, Explorer = I-app
    model = make_fake(intents, tags, FakeSession(3, 4, 1, {2: 1, 3: 2}))
    p = model.predict("open File Explorer now")
    assert p.intent == "open_app" and p.confident and p.confidence > 0.99
    assert p.slots == {"app": "File Explorer"} and p.top[0][0] == "open_app" and p.ms >= 0
    assert model.predict("   ") is None


def test_a_low_confidence_prediction_is_not_confident():
    assert not local_model.Prediction("chat", 0.6).confident and local_model.Prediction("chat", 0.85).confident

"""ml/collect_history.py: real spoken commands + the tool that worked = labelled training sentences, with privacy and quality filters."""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ML = Path(__file__).resolve().parents[2] / "ml"
sys.path.insert(0, str(ML))
import collect_history as ch  # noqa: E402
from common import intent_slots, load_spec  # noqa: E402

ALLOWED = intent_slots(load_spec())


def row(text, tool, args):
    got, why = ch.example(text, tool, args, ALLOWED)
    return got, why


@pytest.mark.parametrize("text,tool,args,intent,slots", [
    ("Chrome kholo", "open_application", {"app_name": "Chrome"}, "open_app", {"app": "Chrome"}),
    ("youtube pe atif aslam ka gana chala do", "play_youtube_video", {"query": "atif aslam ka gana"}, "youtube_play", {"query": "atif aslam ka gana"}),
    ("YouTube open karo", "open_url", {"url": "https://www.youtube.com"}, "open_website", {"site": "YouTube"}),
    ("volume 40 karo", "manage_system_setting", {"setting": "volume", "action": "set", "value": 40}, "volume_set", {"level": "40"}),
    ("ab gazaarish music isi tab pe search karo", "control_browser", {"action": "search", "query": "gazaarish music"}, "youtube_play", {"query": "gazaarish music"}),
    ("video roko", "control_browser", {"action": "pause"}, "youtube_pause", {}),
    ("Documents mein Notes folder banao", "create_folder", {"path": "C:/Users/me/Documents/Notes"}, "create_folder", {"name": "Notes"}),
])
def test_a_tool_that_worked_labels_the_sentence(text, tool, args, intent, slots):
    got, _ = row(text, tool, args)
    assert got["intent"] == intent and got["slots"] == slots and got["source"] == "history"


def test_a_slot_that_is_not_words_in_the_sentence_is_left_out_not_invented():
    got, _ = row("کروم کھولو", "open_application", {"app_name": "chrome"})        # Urdu sentence, the tool says "chrome": no such word in the text
    assert got["intent"] == "open_app" and got["slots"] == {} and got["lang"] == "ur"


@pytest.mark.parametrize("text", ["my email is zain@example.com open it", "pay 12345678 now", "my password is abc open chrome", r"open C:\Users\HP\secret.txt",
                                  "AI: tell me a story", "x"])
def test_private_looking_cloud_and_tiny_sentences_are_skipped(text):
    got, why = row(text, "open_application", {"app_name": "x"})
    assert got is None and why


def test_tools_without_an_intent_are_skipped_not_guessed():
    for tool in ("drive_coding_agent", "list_trash", "unknown_tool"):
        assert row("do the thing", tool, {})[0] is None


def make_db(tmp_path, tasks):
    path = tmp_path / "t.db"
    con = sqlite3.connect(path)
    con.execute("create table tasks (id text, command text, idempotency_key text, status text, created_at text)")
    con.execute("create table actions (task_id text, seq integer, tool_name text, args_json text, status text)")
    for i, (command, key, status, actions) in enumerate(tasks):
        con.execute("insert into tasks values (?,?,?,?,?)", (f"t{i}", command, key, status, f"2026-11-0{i + 1}"))
        for seq, (tool, args, astatus) in enumerate(actions):
            con.execute("insert into actions values (?,?,?,?,?)", (f"t{i}", seq, tool, json.dumps(args), astatus))
    con.commit()
    con.close()
    return path


def test_only_completed_tasks_made_by_a_person_with_a_succeeded_action_are_used(tmp_path):
    db = make_db(tmp_path, [
        ("Chrome kholo", "uuid-1", "completed", [("open_application", {"app_name": "Chrome"}, "succeeded")]),
        ("Notepad kholo", "", "failed", [("open_application", {"app_name": "Notepad"}, "failed")]),                     # failed: never a label
        ("Word kholo", "live-123", "completed", [("open_application", {"app_name": "Word"}, "succeeded")]),            # made by a test script
        ("Excel kholo", "uuid-4", "completed", [("open_application", {"app_name": "Excel"}, "failed")]),
        ("chrome kholo", "uuid-5", "completed", [("open_application", {"app_name": "Chrome"}, "succeeded")]),         # the same sentence again
    ])
    new, skipped, review = ch.collect(db, [], ALLOWED)
    assert [r["text"] for r in new] == ["Chrome kholo"] and skipped["already collected"] == 1 and review == []


def test_a_sentence_the_model_is_sure_means_something_else_goes_to_review(tmp_path):
    db = make_db(tmp_path, [("isi YouTube page par search karo", "u1", "completed", [("web_search", {"query": "x"}, "succeeded")]),
                            ("Chrome kholo", "u2", "completed", [("open_application", {"app_name": "Chrome"}, "succeeded")])])

    class Model:
        def predict(self, text):
            return SimpleNamespace(intent="youtube_play", confidence=0.95) if "YouTube" in text else SimpleNamespace(intent="open_app", confidence=0.99)

    new, _skipped, review = ch.collect(db, [], ALLOWED, Model())
    assert [r["intent"] for r in new] == ["open_app"]
    assert review[0]["tool_said"] == "web_search" and review[0]["model_said"] == "youtube_play"

    class Unsure:
        def predict(self, text):
            return SimpleNamespace(intent="youtube_play", confidence=0.4)       # a shaky opinion never overrules the tool

    assert ch.collect(db, [], ALLOWED, Unsure())[2] == []


def test_the_checklist_never_asks_for_anything_that_deletes_powers_off_installs_or_sends():
    for risky in ("delete_file", "shutdown_pc", "restart_pc", "sleep_pc", "lock_pc", "install_app", "email_send", "whatsapp_draft", "terminal_run",
                  "write_file", "move_file", "rename_file", "copy_file"):
        assert risky not in ch.SAFE_INTENTS
    text = ch.checklist(load_spec(), 3, seed=7)
    assert text.startswith("# Say these") and "## youtube_play" in text and "## open_app" in text


def test_the_report_lists_what_is_still_missing():
    rows = [{"text": "a", "intent": "open_app", "slots": {}, "lang": "en"}]
    text = ch.report(rows, ch.collections.Counter())
    assert "need more" in text and "open_app (1/30)" in text and "youtube_play (0/30)" in text

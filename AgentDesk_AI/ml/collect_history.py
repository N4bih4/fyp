#!/usr/bin/env python3
"""Turn what you really said and what really worked into training sentences, with no hand labelling.

Every task in the app's database is a real sentence (the transcript of your voice, mistakes included) plus the tool that finally did the job.
A tool is a label: play_youtube_video = "youtube_play", open_application = "open_app", and the slot words are found inside the sentence.
Only tasks that COMPLETED with a succeeded action are used, so a misheard command that failed never becomes a wrong example.

    backend\\.venv\\Scripts\\python ml\\collect_history.py --i-consent            # write data/real/history.jsonl and print what is missing
    backend\\.venv\\Scripts\\python ml\\collect_history.py --i-consent --dry-run  # only print
    backend\\.venv\\Scripts\\python ml\\collect_history.py --checklist 3          # data/real/SPEAK_THESE.md: safe commands to say into the orb

Nothing leaves this PC. Sentences with an e-mail address, a long number, a password word or a Windows user-name path are skipped, tasks made by
test scripts are skipped, and the file stays in data/real/ for you to look at (and to decide whether to share it).
Then: ml\\validate_dataset.py, ml\\retrain.ps1 (docs/DATASET_GUIDE.md).
"""
from __future__ import annotations

import argparse
import collections
import json
import random
import re
import sqlite3
import sys
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "ml"))
sys.path.insert(0, str(ROOT / "backend"))
from common import DATA, LANGS, intent_slots, load_spec, read_jsonl, slot_word_labels, words_of, write_jsonl  # noqa: E402

TEST_KEY_PREFIXES = ("live-", "par-", "api-", "bg-", "test-", "smoke-")      # tasks made by the scripts and tests, not by a person
UNSAFE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+|\d{7,}|pass(?:word|code)|\botp\b|\btoken\b|api[ _-]?key|c:\\users\\[^\\\s]+|"
                    r"پاس ?ورڈ|पासवर्ड", re.I)
MIN_PER_INTENT = 30                     # docs/DATASET_GUIDE.md: 30+ per intent, ideally 100+


# --------------------------------------------------------------------------------------------- tool -> intent
def _base(path: str) -> str:
    text = str(path or "").rstrip("/\\")
    return re.split(r"[\\/]", text)[-1] if text else ""


def _site(url: str) -> str:
    host = urlsplit(str(url or "")).hostname or ""
    parts = [p for p in host.split(".") if p and p != "www"]
    return parts[-2] if len(parts) >= 2 else (parts[0] if parts else "")


YOUTUBE_CONTROL = {"speed", "volume", "mute", "unmute", "fullscreen", "next", "previous", "theatre", "captions", "quality", "loop", "skip_ad", "like", "subscribe",
                   "scroll", "results"}
DEVICE = {"lock": "lock_pc", "sleep": "sleep_pc", "shutdown": "shutdown_pc", "restart": "restart_pc", "keep_awake": "keep_awake", "battery": "battery_status"}


def label(tool: str, args: dict) -> tuple[str, dict] | None:
    """(intent, slot values) for one executed tool call, or None when no intent of the local model stands for it."""
    a = args or {}
    if tool == "open_application":
        return "open_app", {"app": a.get("app_name")}
    if tool == "open_url":
        return "open_website", {"site": _site(a.get("url", ""))}
    if tool == "web_search":
        return "web_search", {"search": a.get("query")}
    if tool == "play_youtube_video":
        return "youtube_play", {"query": a.get("query")}
    if tool == "control_browser":
        action = a.get("action")
        if action == "search":
            return "youtube_play", {"query": a.get("query")}
        if action == "pause":
            return "youtube_pause", {}
        if action == "resume":
            return "youtube_resume", {}
        if action == "seek":
            return "youtube_seek", {}
        if action == "now_playing":
            return "youtube_now_playing", {}
        if action in {"close", "switch", "inspect", "read"}:
            return "browser_tab", {"site": a.get("target")}
        if action in YOUTUBE_CONTROL:
            return "youtube_control", {}
        return None
    if tool == "manage_system_setting":
        setting, action = str(a.get("setting", "")).lower(), str(a.get("action", "")).lower()
        if setting == "volume":
            return ("volume_set", {"level": a.get("value")}) if action == "set" else ("volume_change", {})
        if setting == "brightness":
            return "brightness_set", {"level": a.get("value")}
        if setting == "wifi":
            return "wifi_toggle", {}
        if setting == "bluetooth":
            return "bluetooth_toggle", {}
        if setting in {"theme", "dark_mode", "dark"}:
            return "dark_mode", {}
        return None
    if tool == "device_control":
        intent = DEVICE.get(str(a.get("action", "")).lower())
        return (intent, {"minutes": a.get("minutes")} if intent == "keep_awake" else {}) if intent else None
    if tool == "take_screenshot":
        return "screenshot", {}
    if tool == "media_control":
        return "media_control", {}
    if tool == "list_folder":
        return "list_folder", {"path": _base(a.get("path"))}
    if tool == "open_folder":
        return "open_folder", {"path": _base(a.get("path"))}
    if tool == "open_file":
        return "open_file", {"file": _base(a.get("path"))}
    if tool == "create_folder":
        return "create_folder", {"name": _base(a.get("path"))}
    if tool in {"find_files", "find_paths"}:
        return "find_files", {"name": a.get("name") or a.get("query") or a.get("pattern")}
    if tool == "copy_file":
        return "copy_file", {"file": _base(a.get("source"))}
    if tool == "move_file":
        return "move_file", {"file": _base(a.get("source"))}
    if tool == "rename_file":
        return "rename_file", {"file": _base(a.get("path")), "new_name": a.get("new_name")}
    if tool == "delete_file":
        return "delete_file", {"file": _base(a.get("path"))}
    if tool == "restore_file":
        return "restore_file", {}
    if tool == "read_text_file":
        return "read_file", {"file": _base(a.get("path"))}
    if tool == "write_text_file":
        return "write_file", {"file": _base(a.get("path"))}
    if tool == "control_desktop":
        steps = a.get("steps") or [{}]
        action = str(steps[0].get("action", ""))
        if action == "close_window":
            return "close_app", {"app": a.get("target_window")}
        if action in {"minimize_window", "maximize_window", "restore_window", "focus_window"}:
            return "window_control", {"app": a.get("target_window")}
        return None
    if tool == "ui_act":
        if a.get("action") == "click":
            return "ui_click", {"button": a.get("control")}
        if a.get("action") == "type":
            return "ui_type", {"field": a.get("control")}
        return None
    if tool == "run_terminal_command":
        return "terminal_run", {"command": a.get("command")}
    if tool in {"application_package", "winget_install"}:
        return "install_app", {"package": a.get("query") or a.get("package_id")}
    if tool == "compose_email":
        return "email_compose", {"recipient": a.get("to"), "subject": a.get("subject")}
    if tool == "web_answer":
        return "web_answer", {"question": a.get("query")}
    if tool in {"summarise_page", "summarise_file"}:
        return "summarise", {"file": _base(a.get("path"))}
    if tool == "memory_remember":
        return "memory_remember", {}
    if tool == "memory_recall":
        return "memory_recall", {}
    if tool == "make_document":
        return "research_task", {"topic": a.get("topic")}
    return None                                           # drive_coding_agent has no intent in the local model yet; unknown tools too


# --------------------------------------------------------------------------------------------- one sentence
def language_of(text: str) -> str:
    try:
        from app.voice.langdetect import detect
        seen = detect(text)
    except Exception:  # noqa: BLE001 - the heuristic below is enough
        seen = None
    if seen == "roman":
        return "roman_ur"
    if seen in LANGS:
        return seen
    if re.search(r"[\u0600-\u06ff]", text):
        return "ur"
    if re.search(r"[\u0900-\u097f]", text):
        return "hi"
    return "en"


def example(text: str, tool: str, args: dict, allowed: dict[str, list[str]]) -> tuple[dict | None, str]:
    """(training row, "") or (None, why it was skipped)."""
    text = " ".join(str(text or "").split())
    if not 2 <= len(text) <= 200:
        return None, "length"
    if text.casefold().startswith("ai:"):
        return None, "cloud prefix"
    if UNSAFE.search(text):
        return None, "private looking"
    found = label(tool, args)
    if found is None:
        return None, "no intent for " + tool
    intent, slots = found
    if intent not in allowed:
        return None, "unknown intent"
    kept = {}
    for name, value in slots.items():
        if value in (None, "") or name not in allowed[intent]:
            continue
        labels = slot_word_labels(text, {name: str(value)})
        words = [w.strip(".,?!;:\"'()۔؟،।") for (w, _a, _b), lab in zip(words_of(text), labels) if lab.endswith(name)]
        if words:                                                                          # the slot must be words that are in the sentence,
            kept[name] = " ".join(words)                                                   # written the way the sentence writes them
    return {"text": text, "intent": intent, "slots": kept, "lang": language_of(text), "source": "history"}, ""


# --------------------------------------------------------------------------------------------- the database
def read_tasks(db: Path) -> list[tuple[str, str, list[tuple[str, dict]]]]:
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        tasks = con.execute("select id, command, coalesce(idempotency_key, '') from tasks where status = 'completed' order by created_at").fetchall()
        out = []
        for task_id, command, key in tasks:
            if key.startswith(TEST_KEY_PREFIXES):
                continue
            rows = con.execute("select tool_name, args_json from actions where task_id = ? and status = 'succeeded' order by seq", (task_id,)).fetchall()
            if rows:
                out.append((task_id, command, [(tool, json.loads(args or "{}")) for tool, args in rows]))
        return out
    finally:
        con.close()


def load_model():
    """The local intent model as a second, independent opinion (None when it is not installed)."""
    try:
        from app.nlu.local_model import get_model
        return get_model()
    except Exception:  # noqa: BLE001 - without it every labelled sentence is accepted
        return None


def disagrees(model, row: dict, confidence: float = 0.8) -> str | None:
    """The model's intent when it is sure (confidence >= 0.8) and different from the tool's label: such a sentence goes to review, not to training.
    A success only shows the app DID something, not that it was what the person asked for."""
    if model is None:
        return None
    try:
        guess = model.predict(row["text"])
    except Exception:  # noqa: BLE001
        return None
    return guess.intent if guess is not None and guess.confidence >= confidence and guess.intent != row["intent"] else None


def collect(db: Path, existing: list[dict], allowed: dict[str, list[str]], model=None) -> tuple[list[dict], collections.Counter, list[dict]]:
    have = {r["text"].casefold() for r in existing}
    new, review, skipped = [], [], collections.Counter()
    for _task_id, command, actions in read_tasks(db):
        tool, args = actions[0]                           # the first thing that worked is what the sentence asked for
        row, why = example(command, tool, args, allowed)
        if row is None:
            skipped[why] += 1
        elif row["text"].casefold() in have:
            skipped["already collected"] += 1
        else:
            have.add(row["text"].casefold())
            other = disagrees(model, row)
            if other:
                review.append({**row, "tool_said": row["intent"], "model_said": other})
                skipped["sent to review (the model disagrees)"] += 1
            else:
                new.append(row)
    return new, skipped, review


def report(rows: list[dict], skipped: collections.Counter) -> str:
    per_intent = collections.Counter(r["intent"] for r in rows)
    per_lang = collections.Counter(r["lang"] for r in rows)
    lines = [f"{len(rows)} real sentences  |  by language: " + ", ".join(f"{k} {v}" for k, v in sorted(per_lang.items()))]
    lines.append("by intent: " + (", ".join(f"{k} {v}" for k, v in per_intent.most_common()) or "none"))
    if skipped:
        lines.append("skipped: " + ", ".join(f"{k} {v}" for k, v in skipped.most_common()))
    spec_intents = sorted(load_spec()["intents"])
    short = [f"{i} ({per_intent.get(i, 0)}/{MIN_PER_INTENT})" for i in spec_intents if per_intent.get(i, 0) < MIN_PER_INTENT and i in SAFE_INTENTS]
    lines.append(f"need more (safe to say aloud, target {MIN_PER_INTENT}+ each): " + (", ".join(short) or "none"))
    return "\n".join(lines)


# --------------------------------------------------------------------------------------------- what to say
SAFE_INTENTS = ["open_app", "open_website", "web_search", "youtube_play", "youtube_pause", "youtube_resume", "youtube_seek", "youtube_control",
                "youtube_now_playing", "media_control", "browser_tab", "open_folder", "open_file", "list_folder", "find_files", "read_file",
                "volume_set", "volume_change", "brightness_set", "battery_status", "screenshot", "web_answer", "window_control", "switch_app"]
# not asked for aloud: they change or delete things, power the PC off, install, send or run commands (they would wait for an approval, not succeed)


def checklist(spec: dict, per_intent: int, seed: int) -> str:
    rng = random.Random(seed)
    fillers = spec.get("fillers", {})
    lines = ["# Say these into the orb", "",
             "Say each one naturally (your own words are even better), one at a time, and let it finish. Whisper's mistakes are what the model must learn.",
             "Afterwards: `backend\\.venv\\Scripts\\python ml\\collect_history.py --i-consent`. Commands that succeed are labelled by themselves.", ""]
    for intent in SAFE_INTENTS:
        body = spec["intents"].get(intent) or {}
        sentences = []
        for lang in LANGS:
            templates = [t.strip() for t in str(body.get(lang, "")).split(" | ") if t.strip() and not t.startswith("!")]
            rng.shuffle(templates)
            for template in templates[:max(1, per_intent // 2)]:
                names = re.findall(r"\{(\w+)\}", template)
                if all(n in fillers and fillers[n] for n in names):
                    sentences.append(re.sub(r"\{(\w+)\}", lambda m: str(rng.choice(fillers[m.group(1)])), template))
        if sentences:
            lines += [f"## {intent}", *[f"- {s}" for s in sentences[:per_intent * 2]], ""]
    return "\n".join(lines)


# --------------------------------------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--i-consent", action="store_true", help="I agree that my own commands are used as training sentences on this PC")
    ap.add_argument("--db", default=str(ROOT / "backend" / "agentdesk.db"))
    ap.add_argument("--out", default=str(DATA / "real" / "history.jsonl"))
    ap.add_argument("--dry-run", action="store_true", help="print the report, write nothing")
    ap.add_argument("--no-model-check", action="store_true", help="do not compare with the local model (every labelled sentence is accepted)")
    ap.add_argument("--checklist", type=int, metavar="N", help="write data/real/SPEAK_THESE.md with about N sentences per intent per language and exit")
    a = ap.parse_args()
    spec = load_spec()
    if a.checklist:
        path = DATA / "real" / "SPEAK_THESE.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(checklist(spec, a.checklist, seed=7), encoding="utf-8")
        print(f"wrote {path}")
        return 0
    if not a.i_consent:
        print("Nothing read: pass --i-consent to use your own commands as training data (they stay on this PC).")
        return 2
    db = Path(a.db)
    if not db.exists():
        print(f"no database at {db}")
        return 1
    out = Path(a.out)
    existing = read_jsonl(out)
    new, skipped, review = collect(db, existing, intent_slots(spec), None if a.no_model_check else load_model())
    rows = existing + new
    print(report(rows, skipped))
    if not a.dry_run:
        write_jsonl(out, rows)
        print(f"{len(new)} new sentences added -> {out}")
        if review:
            path = DATA / "review" / "history_review.jsonl"       # outside data/real: nothing in here is trained on until you move a line over
            write_jsonl(path, read_jsonl(path) + review)
            print(f"{len(review)} sentences where the tool and the model disagree -> {path} (check them; fix 'intent' and move the good ones to data/real/)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

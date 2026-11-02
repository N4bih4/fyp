#!/usr/bin/env python3
"""Turn the corrections you made in the app ("no, I said Firefox") into training sentences: data/real/corrections.jsonl.

    backend\.venv\Scripts\python ml\collect_corrections.py --i-consent [--db backend\agentdesk.db]

ONLY with --i-consent: it reads the "alias" rows of the Memory page (heard => meant) and writes two sentences per row ("open <heard>" and
"<heard> kholo") as open_app examples whose app slot is the words the recogniser heard. Nothing leaves this PC; the file stays in data/real/
and you decide whether to share it with the team.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "ml"))
from common import DATA, read_jsonl, write_jsonl  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--i-consent", action="store_true", help="I agree that my corrected app names are used as training sentences on this PC")
    ap.add_argument("--db", default=str(ROOT / "backend" / "agentdesk.db"))
    a = ap.parse_args()
    if not a.i_consent:
        print("Nothing read: pass --i-consent to use your corrections as training data.")
        return 2
    path = Path(a.db)
    if not path.exists():
        print(f"no database at {path}")
        return 1
    con = sqlite3.connect(str(path))
    try:
        rows = con.execute("select text from memory_items where kind = 'alias'").fetchall()
    finally:
        con.close()
    out_path = DATA / "real" / "corrections.jsonl"
    have = {r["text"].casefold() for r in read_jsonl(out_path)}
    new = []
    for (text,) in rows:
        if "=>" not in text:
            continue
        heard, meant = (x.strip() for x in text.split("=>", 1))
        if not heard or not meant:
            continue
        for sentence, lang in ((f"open {heard}", "en"), (f"{heard} kholo", "roman_ur")):
            if sentence.casefold() not in have:
                have.add(sentence.casefold())
                new.append({"text": sentence, "intent": "open_app", "slots": {"app": heard}, "lang": lang, "is_correction": False})
    write_jsonl(out_path, read_jsonl(out_path) + new)
    print(json.dumps({"corrections_read": len(rows), "sentences_added": len(new), "file": str(out_path)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""F6 live run: the REAL search (Wikipedia / Tavily), the REAL pages, the REAL cloud AI (your Groq key) and the REAL file writers (.docx, .md, .pdf through Edge).

    python scripts/document_live.py [--out ../docs/eval/f6_live.json] [--keep ../docs/eval/f6_samples] [--open]

The search PROVIDERS (Wikipedia / Tavily) are not used by default because they need a contact e-mail / API key that you set in backend/.env; the pages the run reads are
fixed public pages (National Geographic, World History, Ducksters), fetched and read by the real fetcher. Use --real-search once the providers are set up.
Everything is written to a temporary folder (copied to --keep if given); your own Documents folder is not touched. Documents are NOT opened unless --open.
It uses a temporary database in which "cloud answers" is on. Takes 3-6 minutes; about 30 AI calls on the small model.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
TMP = Path(tempfile.mkdtemp(prefix="agentdesk_f6_"))
os.environ["DATABASE_URL"] = f"sqlite:///{TMP / 'f6.db'}"
os.environ["AGENTDESK_LATENCY_LOG"] = str(TMP / "lat.jsonl")

from app import progress  # noqa: E402
from app.database import SessionLocal, init_db  # noqa: E402
from app.preferences import PreferencesUpdate, update_preferences  # noqa: E402
from app.tools import documents  # noqa: E402
from app.tools.base import ToolContext  # noqa: E402

rows: list[dict] = []


PAGES = {"solar energy": ["https://education.nationalgeographic.org/resource/solar-energy/"],
         "the indus valley civilisation": ["https://www.worldhistory.org/Indus_Valley_Civilization/"],
         "photosynthesis": ["https://www.ducksters.com/science/photosynthesis.php"], "water cycle": ["https://education.nationalgeographic.org/resource/water-cycle/"]}


class QuietPipeline(documents.Pipeline):
    open_files = False
    use_real_search = False

    def search(self, topic):
        if self.use_real_search:
            return super().search(topic)
        from app.search.provider import SearchResult
        urls = PAGES.get(topic.casefold().strip(), [])
        return [SearchResult(u.rstrip("/").rsplit("/", 1)[-1].replace("_", " ").replace("-", " ").replace(".php", ""), u, "", "fixed-page") for u in urls]      # real pages, fetched and read by the real fetcher

    def open(self, path):
        if self.open_files:
            return super().open(path)
        return True


def case(name: str, tool, **raw) -> dict:
    args = tool.validate_args(raw)
    action = f"live-{len(rows)}"
    token = progress.bind(action)
    started = time.time()
    try:
        result = tool.execute(args)
    finally:
        lines = progress.lines(action)
        progress.unbind(token, action)
    total = round(time.time() - started, 1)
    ver = tool.verify(args, result) if result.success else None
    first = round(lines[0]["at"] - started, 2) if lines else None
    row = {"case": name, "ok": bool(result.success and ver and ver.passed), "seconds": total, "first_progress_seconds": first, "progress_lines": len(lines),
           "error": result.error, "spoken": (result.output or {}).get("spoken"), "checks": ver.checks if ver else None, "path": (result.output or {}).get("path"),
           "sources": (result.output or {}).get("sources"), "sections": (result.output or {}).get("sections"), "bytes": (result.output or {}).get("bytes")}
    if row["path"]:
        try:
            text, headings = documents.read_back(Path(row["path"]))
            row["headings"] = headings[:10]
            row["words"] = len(text.split())
            row["excerpt"] = " ".join(text.split())[:420]
        except Exception as exc:  # noqa: BLE001
            row["read_back_error"] = f"{type(exc).__name__}: {exc}"
    rows.append(row)
    print(("PASS " if row["ok"] else "FAIL ") + f"{name:34} {total:6.1f}s  {row['spoken'] or row['error']}", flush=True)
    return row


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT.parent / "docs" / "eval" / "f6_live.json"))
    ap.add_argument("--keep", default=None)
    ap.add_argument("--open", action="store_true")
    ap.add_argument("--pause", type=float, default=8.0)
    ap.add_argument("--real-search", action="store_true", help="use the configured search providers (needs WIKIPEDIA_CONTACT_EMAIL or a Tavily key)")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    init_db()
    with SessionLocal() as db:
        update_preferences(db, PreferencesUpdate(cloud_answers=True))
    home = TMP / "home"
    (home / "Documents").mkdir(parents=True)
    pipe = QuietPipeline()
    pipe.open_files = a.open
    pipe.use_real_search = a.real_search
    documents.set_pipeline(pipe)
    tool = documents.MakeDocumentTool(ToolContext(allowed_directories=[home]))

    case("research docx (brief, English)", tool, kind="research", topic="solar energy", depth="brief", language="en", format="docx")
    time.sleep(a.pause)
    case("research markdown (brief)", tool, kind="research", topic="the Indus Valley civilisation", depth="brief", format="md")
    time.sleep(a.pause)
    case("research PDF via Edge (brief)", tool, kind="research", topic="photosynthesis", depth="brief", format="pdf")
    time.sleep(a.pause)
    case("study plan docx (brief)", tool, kind="plan", topic="study plan for my final exams in physics and mathematics, 4 weeks", depth="brief")
    time.sleep(a.pause)
    case("research in Urdu (brief)", tool, kind="research", topic="water cycle", depth="brief", language="ur")
    time.sleep(a.pause)
    (home / "Documents" / "lecture_one.txt").write_text("Lecture one covers vectors, dot products and the cross product. " * 12, encoding="utf-8")
    (home / "Documents" / "lecture_two.txt").write_text("Lecture two covers matrices, determinants, inverses and eigenvalues. " * 12, encoding="utf-8")
    case("notes from two files (brief)", tool, kind="notes", files=["lecture_one.txt", "lecture_two.txt"], depth="brief")
    broad = case("broad topic asks first", tool, kind="research", topic="cricket")
    rows[-1]["ok"] = (not broad["ok"]) and "How detailed" in (broad["error"] or "")        # the right outcome here is the question, not a file
    print(("PASS " if rows[-1]["ok"] else "FAIL ") + "broad topic asks first (the question is the right answer)")

    summary = {"cases": len(rows), "passed": sum(1 for r in rows if r["ok"])}
    summary["pct"] = round(100 * summary["passed"] / len(rows), 1)
    print(json.dumps(summary))
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps({"summary": summary, "rows": rows}, indent=1, ensure_ascii=False), encoding="utf-8")
    if a.keep:
        dest = Path(a.keep)
        dest.mkdir(parents=True, exist_ok=True)
        for f in (home / "Documents" / "AgentDesk").glob("*"):
            shutil.copy(f, dest / f.name)
    return 0 if summary["pct"] >= 85 else 1


if __name__ == "__main__":
    raise SystemExit(main())

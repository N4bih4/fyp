"""Live voice probe against the running backend: every reply language through /voice/tts (engine, size, time), then each clip back
through /voice/stt (Groq Whisper) and the local command matcher. No microphone needed: it tests everything except the room and the mic.

    backend/.venv/Scripts/python.exe backend/scripts/voice_probe.py [--stt]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

BASE = "http://127.0.0.1:8000"
TTS_CASES = [
    ("en", "Chrome is open."),
    ("roman", "Chrome khul gaya hai."),
    ("ur-PK", "کروم کھل گیا ہے۔"),
    ("hi-IN", "क्रोम खुल गया है।"),
]
STT_CASES = [
    ("ur-PK", "کروم کھولو", "chrome"),
    ("ur-PK", "اینٹی گریویٹی کھولو", "antigravity"),
    ("hi-IN", "एंटी ग्रेविटी खोलो", "antigravity"),
    ("hi-IN", "यूट्यूब खोलो", "youtube"),
    ("en", "open Notepad", "notepad"),
    ("en", "create a folder called Notes in Documents", "notes"),
    ("ur-PK", "آواز کم کرو", "volume"),
]


def token() -> str:
    from app.security.token import load_or_create_token
    return load_or_create_token()


def post_json(path: str, body: dict, tok: str) -> tuple[int, dict | bytes, dict]:
    req = urllib.request.Request(BASE + path, json.dumps(body).encode(), {"Authorization": "Bearer " + tok, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, r.read(), dict(r.headers)
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read() or b"{}"), dict(exc.headers)


def stt(audio: bytes, mime: str, lang: str, tok: str) -> str:
    boundary = uuid.uuid4().hex
    ext = "mp3" if "mpeg" in mime else "wav"
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"audio\"; filename=\"speech.{ext}\"\r\nContent-Type: {mime}\r\n\r\n").encode() + audio + \
           (f"\r\n--{boundary}\r\nContent-Disposition: form-data; name=\"language\"; \r\n\r\nauto\r\n--{boundary}--\r\n").encode()
    req = urllib.request.Request(BASE + "/voice/stt", body, {"Authorization": "Bearer " + tok, "Content-Type": "multipart/form-data; boundary=" + boundary})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())["text"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stt", action="store_true", help="also send the clips back through speech-to-text")
    args = ap.parse_args()
    tok = token()
    print("== TTS (reply voice)")
    for lang, text in TTS_CASES:
        t = time.perf_counter()
        status, data, headers = post_json("/voice/tts", {"text": text, "language": lang}, tok)
        ms = round((time.perf_counter() - t) * 1000)
        if status == 200:
            print(f"  OK   {lang:6} {headers.get('X-TTS-Engine')}/{headers.get('X-TTS-Voice')}  {len(data)} bytes  {ms} ms")
        else:
            print(f"  FAIL {lang:6} HTTP {status}  {ms} ms  {data}")
    if not args.stt:
        return 0
    print("== speech -> STT -> local matcher")
    from app.nlu.local_matcher import match
    from app.nlu.memory import ConversationMemory
    for lang, text, expect in STT_CASES:
        status, audio, headers = post_json("/voice/tts", {"text": text, "language": lang}, tok)
        if status != 200:
            print(f"  SKIP {text}  (no audio: HTTP {status})")
            continue
        t = time.perf_counter()
        heard = stt(audio, headers.get("Content-Type", "audio/mpeg"), lang, tok)
        ms = round((time.perf_counter() - t) * 1000)
        plan = match(heard, ConversationMemory()).plan
        steps = [(s.tool, dict(s.args)) for s in plan.steps] if plan else None
        ok = bool(steps) and expect in json.dumps(steps, ensure_ascii=False).casefold()
        print(f"  {'OK  ' if ok else 'MISS'} said={text!r} heard={heard!r} {ms} ms -> {steps}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

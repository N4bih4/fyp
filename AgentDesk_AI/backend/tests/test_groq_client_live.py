"""Live Groq smoke test for GroqClient: chat, TTS and STT round trip.

Skipped automatically when GROQ_API_KEY is missing. Cost: one tiny chat
completion, one short TTS clip and one transcription of that clip.

    $env:GROQ_API_KEY="gsk_..."   # PowerShell, never commit the key
    .venv\\Scripts\\python -m pytest tests/test_groq_client_live.py -v
"""
from __future__ import annotations

import os

import pytest

KEY = os.environ.get("GROQ_API_KEY")
pytestmark = pytest.mark.skipif(not KEY, reason="GROQ_API_KEY not set: live Groq smoke test skipped.")


@pytest.fixture(scope="module")
def client():
    pytest.importorskip("groq")
    from app.ai.groq_client import GroqClient

    return GroqClient(KEY, timeout_seconds=30, max_retries=2)


def test_live_chat(client):
    out = client.chat([{"role": "user", "content": "Reply with exactly this word: ok"}], max_tokens=200)
    assert out["content"] and "ok" in out["content"].lower()
    assert client.usage.snapshot()["chat"]["succeeded"] >= 1


def test_live_tts_then_stt_round_trip(client):
    audio = client.speak("Open notepad please.")
    assert audio[:4] == b"RIFF", "expected WAV audio"
    out = client.transcribe(audio, language="en", prompt="Notepad, Chrome")
    assert "notepad" in out["text"].lower()
    assert out["model"] in client.stt_models

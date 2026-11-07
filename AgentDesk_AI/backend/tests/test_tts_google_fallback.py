"""Urdu / Hindi replies when the Microsoft online voices are blocked: Google's voice answers, English keeps its own order."""
from __future__ import annotations

import io
import wave

from app.voice.tts import NETWORK_COOLDOWN, TTSChain, VoiceChoice


def silent_wav(*_):
    """What SAPI returns for text its voices cannot read: a valid WAV with no sound."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(16000)
    return buf.getvalue(), "audio/wav"


def failing(*_):
    raise ConnectionError("The specified network name is no longer available")


def audio(tag: str):
    return lambda text, voice: (tag.encode() * 300, "audio/mpeg")


def test_urdu_falls_back_to_google_when_edge_is_blocked():
    clock = [0.0]
    chain = TTSChain(edge=failing, google=audio("g"), sapi=silent_wav, clock=lambda: clock[0], cache=False)
    clip = chain.synthesize("کروم کھل گیا ہے", VoiceChoice(language="ur-PK"))
    assert clip.engine == "google" and clip.voice == "ur"
    assert chain.synthesize("ہندی", VoiceChoice(language="hi-IN")).voice == "hi"


def test_a_blocked_network_is_retried_after_30_seconds_not_5_minutes():
    clock = [0.0]
    calls = []

    def edge(text, voice):
        calls.append(1)
        raise ConnectionError("blocked")

    chain = TTSChain(edge=edge, google=audio("g"), clock=lambda: clock[0], cache=False)
    chain.synthesize("a", VoiceChoice(language="ur-PK"))
    chain.synthesize("b", VoiceChoice(language="ur-PK"))
    assert len(calls) == 1                                   # cooling down: Google answers without waiting for edge again
    clock[0] += NETWORK_COOLDOWN + 1
    chain.synthesize("c", VoiceChoice(language="ur-PK"))
    assert len(calls) == 2


def test_english_still_prefers_orpheus_then_edge_then_the_offline_voice():
    chain = TTSChain(orpheus=failing, edge=failing, google=audio("g"), sapi=audio("s"), cache=False)
    assert [name for name, _e, _v in chain.plan(VoiceChoice(language="en"))] == ["orpheus", "edge", "sapi"]
    assert chain.synthesize("Chrome is open", VoiceChoice(language="en")).engine == "sapi"


def test_error_message_names_every_engine():
    chain = TTSChain(edge=failing, google=failing, sapi=silent_wav, cache=False)
    try:
        chain.synthesize("x", VoiceChoice(language="ur-PK"))
    except RuntimeError as exc:
        text = str(exc)
    assert "edge: ConnectionError" in text and "google: ConnectionError" in text and "sapi: silent" in text

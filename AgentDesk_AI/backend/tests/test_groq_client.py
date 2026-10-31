"""GroqClient: timeouts, 429 backoff, fallback, usage counting, redacted logging.

All calls go to an injected fake SDK; no network.
"""
from __future__ import annotations

import json
import logging
from types import SimpleNamespace

import pytest

from app.ai.base import AIConfigError, AIError, AIRateLimitError
from app.ai.groq_client import GroqClient
from app.logging_setup import LOGGER_NAME

SECRET = "gsk_" + "A1b2C3d4E5f6G7h8J9k0" * 2


class FakeStatusError(Exception):
    def __init__(self, status: int, headers: dict | None = None, message: str = "boom"):
        super().__init__(message)
        self.status_code = status
        self.response = SimpleNamespace(status_code=status, headers=headers or {})


class RateLimitError(FakeStatusError):
    def __init__(self, headers=None, message="rate limited"):
        super().__init__(429, headers, message)


class APITimeoutError(Exception):
    pass


def chat_response(text="ok", prompt=12, completion=3):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=text), finish_reason="stop")],
        usage=SimpleNamespace(prompt_tokens=prompt, completion_tokens=completion),
        model="openai/gpt-oss-120b",
    )


class Endpoint:
    """Callable that returns/raises a scripted sequence and records kwargs."""

    def __init__(self, *script):
        self.script = list(script)
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def fake_sdk(chat=None, stt=None, tts=None):
    return SimpleNamespace(
        chat=SimpleNamespace(completions=chat or Endpoint()),
        audio=SimpleNamespace(transcriptions=stt or Endpoint(), speech=tts or Endpoint()),
    )


def make(sdk, **kw):
    sleeps: list[float] = []
    client = GroqClient(SECRET, client=sdk, sleep=sleeps.append, base_backoff_seconds=1.0, **kw)
    return client, sleeps


def test_missing_key_is_config_error():
    with pytest.raises(AIConfigError):
        GroqClient(None)
    with pytest.raises(AIConfigError):
        GroqClient("")


def test_retry_limit_capped_at_two():
    with pytest.raises(ValueError):
        GroqClient(SECRET, client=fake_sdk(), max_retries=3)


def test_chat_success_counts_tokens_and_passes_timeout():
    chat = Endpoint(chat_response("hello"))
    client, sleeps = make(fake_sdk(chat=chat), timeout_seconds=7)
    out = client.chat([{"role": "user", "content": "hi"}], response_format={"type": "json_object"})
    assert out["content"] == "hello"
    assert out["usage"] == {"prompt_tokens": 12, "completion_tokens": 3}
    assert chat.calls[0]["timeout"] == 7.0
    assert chat.calls[0]["response_format"] == {"type": "json_object"}
    usage = client.usage.snapshot()["chat"]
    assert usage["calls"] == 1 and usage["succeeded"] == 1 and usage["prompt_tokens"] == 12
    assert sleeps == []


def test_429_retried_with_exponential_backoff_then_succeeds():
    chat = Endpoint(RateLimitError(), RateLimitError(), chat_response())
    client, sleeps = make(fake_sdk(chat=chat))
    assert client.chat([{"role": "user", "content": "x"}])["content"] == "ok"
    assert len(sleeps) == 2
    assert 1.0 <= sleeps[0] <= 1.1 and 2.0 <= sleeps[1] <= 2.2  # 1 s, 2 s (+<=10% jitter)
    usage = client.usage.snapshot()["chat"]
    assert usage["calls"] == 3 and usage["retries"] == 2 and usage["rate_limited"] == 2
    assert usage["succeeded"] == 1 and usage["failed"] == 0


def test_429_honours_retry_after_header():
    chat = Endpoint(RateLimitError({"retry-after": "3"}), chat_response())
    client, sleeps = make(fake_sdk(chat=chat))
    client.chat([{"role": "user", "content": "x"}])
    assert sleeps == [3.0]


def test_429_after_max_retries_raises_rate_limit_error():
    chat = Endpoint(RateLimitError(), RateLimitError(), RateLimitError())
    client, sleeps = make(fake_sdk(chat=chat))
    with pytest.raises(AIRateLimitError) as info:
        client.chat([{"role": "user", "content": "x"}])
    assert len(chat.calls) == 3 and len(sleeps) == 2
    assert info.value.retry_after >= 1
    assert client.usage.snapshot()["chat"]["failed"] == 1


def test_long_retry_after_is_not_waited_out():
    chat = Endpoint(RateLimitError({"retry-after": "120"}))
    client, sleeps = make(fake_sdk(chat=chat))
    with pytest.raises(AIRateLimitError) as info:
        client.chat([{"role": "user", "content": "x"}])
    assert sleeps == [] and len(chat.calls) == 1
    assert info.value.retry_after == 120


def test_server_error_retried_but_auth_and_timeout_are_not():
    chat = Endpoint(FakeStatusError(503), chat_response())
    client, sleeps = make(fake_sdk(chat=chat))
    assert client.chat([{"role": "user", "content": "x"}])["content"] == "ok"
    assert len(sleeps) == 1

    chat = Endpoint(FakeStatusError(401))
    client, sleeps = make(fake_sdk(chat=chat))
    with pytest.raises(AIConfigError):
        client.chat([{"role": "user", "content": "x"}])
    assert len(chat.calls) == 1 and sleeps == []

    chat = Endpoint(APITimeoutError("slow"))
    client, sleeps = make(fake_sdk(chat=chat), timeout_seconds=5)
    with pytest.raises(AIError, match="timed out after 5 s"):
        client.chat([{"role": "user", "content": "x"}])
    assert len(chat.calls) == 1 and sleeps == []


def test_real_sdk_rate_limit_exception_is_recognised():
    groq = pytest.importorskip("groq")
    httpx = pytest.importorskip("httpx")
    request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    response = httpx.Response(429, headers={"retry-after": "2"}, request=request)
    exc = groq.RateLimitError("rate limited", response=response, body=None)
    chat = Endpoint(exc, chat_response())
    client, sleeps = make(fake_sdk(chat=chat))
    client.chat([{"role": "user", "content": "x"}])
    assert sleeps == [2.0]


def test_transcribe_passes_language_and_prompt_and_counts_audio():
    stt = Endpoint(SimpleNamespace(text=" volume kam karo ", language="ur", duration=1.5))
    client, _ = make(fake_sdk(stt=stt))
    out = client.transcribe(b"RIFFfake", language="ur", prompt="Chrome, Notepad, 6th sem")
    assert out == {"text": "volume kam karo", "language": "ur", "duration": 1.5, "model": "whisper-large-v3-turbo"}
    call = stt.calls[0]
    assert call["language"] == "ur" and call["prompt"].startswith("Chrome")
    assert call["file"][0] == "speech.wav" and call["file"][1].read() == b"RIFFfake"
    assert client.usage.snapshot()["stt"]["audio_seconds"] == 1.5


def test_transcribe_falls_back_to_second_model():
    stt = Endpoint(FakeStatusError(404), SimpleNamespace(text="hello", language="en", duration=0.8))
    client, _ = make(fake_sdk(stt=stt))
    out = client.transcribe(b"x")
    assert out["model"] == "whisper-large-v3"
    assert [c["model"] for c in stt.calls] == ["whisper-large-v3-turbo", "whisper-large-v3"]


def test_transcribe_bad_key_does_not_try_fallback():
    stt = Endpoint(FakeStatusError(401))
    client, _ = make(fake_sdk(stt=stt))
    with pytest.raises(AIConfigError):
        client.transcribe(b"x")
    assert len(stt.calls) == 1


def test_speak_returns_wav_bytes_and_counts_characters():
    tts = Endpoint(SimpleNamespace(read=lambda: b"RIFF....WAVE"))
    client, _ = make(fake_sdk(tts=tts))
    audio = client.speak("Volume 40 percent kar diya.")
    assert audio.startswith(b"RIFF")
    call = tts.calls[0]
    assert call["model"] == "canopylabs/orpheus-v1-english" and call["response_format"] == "wav"
    assert client.usage.snapshot()["tts"]["tts_characters"] == len("Volume 40 percent kar diya.")


def test_empty_inputs_rejected_without_calls():
    client, _ = make(fake_sdk())
    with pytest.raises(AIError):
        client.transcribe(b"")
    with pytest.raises(AIError):
        client.speak("   ")
    assert client.usage.snapshot()["stt"]["calls"] == 0


def test_logs_never_contain_key_prompt_or_audio_text(caplog):
    leaked = f"invalid api_key={SECRET} for request"
    chat = Endpoint(FakeStatusError(400, message=leaked))
    client, _ = make(fake_sdk(chat=chat))
    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        with pytest.raises(AIError) as info:
            client.chat([{"role": "user", "content": "PRIVATE-PROMPT-TEXT"}])
        tts = Endpoint(SimpleNamespace(read=lambda: b"RIFF"))
        client2, _ = make(fake_sdk(tts=tts))
        client2.speak("PRIVATE-SPOKEN-TEXT")
    assert SECRET not in str(info.value)
    dumped = json.dumps([r.__dict__ for r in caplog.records], default=str)
    assert SECRET not in dumped
    assert "PRIVATE-PROMPT-TEXT" not in dumped and "PRIVATE-SPOKEN-TEXT" not in dumped
    assert any(getattr(r, "event", "") == "groq_call" for r in caplog.records)
    assert SECRET not in repr(client)


def test_from_settings_uses_configured_models():
    settings = SimpleNamespace(
        groq_api_key=SECRET, ai_timeout_seconds=9, ai_max_retries=5, ai_model="openai/gpt-oss-20b",
        groq_stt_model="whisper-large-v3-turbo", groq_stt_fallback_model="whisper-large-v3",
        groq_tts_model="canopylabs/orpheus-v1-english", groq_tts_voice="troy",
    )
    client = GroqClient.from_settings(settings, client=fake_sdk())
    assert client.max_retries == 2 and client.timeout_seconds == 9
    assert client.chat_model == "openai/gpt-oss-20b" and client.tts_voice == "troy"
    assert client.stt_models == ("whisper-large-v3-turbo", "whisper-large-v3")

"""OPT-IN live Groq integration test. NEVER runs by default.

To run a single real (cheap) Groq call:

    $env:GROQ_API_KEY="gsk_..."            # PowerShell
    $env:AGENTDESK_LIVE_GROQ="1"
    .venv\\Scripts\\python -m pytest tests/test_groq_live.py -v

What it costs: one tiny chat completion with no tools (a few dozen tokens).
Free tier: no credit card required - https://console.groq.com/keys

This test is the ONLY place a live call may happen, and only when you
explicitly opt in. Do not claim it passed unless you actually ran it.
"""
from __future__ import annotations

import os

import pytest

LIVE = os.environ.get("AGENTDESK_LIVE_GROQ") == "1" and bool(os.environ.get("GROQ_API_KEY"))


@pytest.mark.skipif(
    not LIVE,
    reason="Opt-in only: set AGENTDESK_LIVE_GROQ=1 and GROQ_API_KEY to run one real Groq call.",
)
def test_live_groq_single_cheap_turn():
    from app.ai.groq_provider import GroqProvider

    provider = GroqProvider(
        api_key=os.environ["GROQ_API_KEY"],
        model=os.environ.get("AI_MODEL", "openai/gpt-oss-120b"),
        max_retries=0,
    )
    resp = provider.complete(
        [{"role": "user", "content": "Reply with exactly this word: ok"}],
        tools=None,
    )
    assert resp["content"] and "ok" in resp["content"].lower()
    assert resp["tool_calls"] == []

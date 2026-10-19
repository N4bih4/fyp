"""OpenAI-backed planning provider with structured JSON output."""
from __future__ import annotations

import json
import time

from .base import AIConfigError, AIError, AIProvider, Plan

SYSTEM_PROMPT = """You are the planner for AgentDesk AI, a Windows desktop assistant.
Turn the user's natural-language command into a JSON plan using ONLY the registered tools below.

TOOLS:
{tools}

RULES:
- Output ONLY valid JSON: {{"actions": [{{"tool": "<name>", "args": {{...}}, "rationale": "<why>"}}], "note": "<optional message>"}}
- Use only tool names from the list. Never invent tools.
- Do not guess Windows user names or construct paths such as C:\\Users\\HP. For the current user's Desktop, Documents, or Downloads, use ~/Desktop/..., ~/Documents/..., or ~/Downloads/...; the backend expands ~ to the actual user home and enforces allowed-directory permissions. For other locations, use absolute paths provided or otherwise known; never invent a path.
- Never output Python, PowerShell, shell commands, or scripts - only tool calls.
- If the command is ambiguous (missing file name, folder, or app), return {{"actions": [], "note": "clarification question"}}.
- If the user asks to "show the result of the previous task", return {{"actions": [], "note": "__PREVIOUS_TASK__"}}.
- Keep plans short: the minimum actions needed.
"""


class OpenAIProvider(AIProvider):
    name = "openai"
    is_mock = False

    def __init__(self, api_key: str, model: str, timeout_seconds: int = 30, max_retries: int = 2):
        if not api_key:
            raise AIConfigError(
                "OPENAI_API_KEY is not set. Add it to backend/.env, or set "
                "AI_PROVIDER=mock to run in offline mock mode."
            )
        self._api_key = api_key
        self._model = model
        self._timeout = timeout_seconds
        self._max_retries = max_retries

    def _client(self):
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise AIConfigError(
                "The 'openai' package is not installed. Run: pip install openai"
            ) from exc
        return OpenAI(api_key=self._api_key, timeout=self._timeout)

    def generate_plan(self, command: str, tool_descriptions: str) -> Plan:
        from openai import (
            APIConnectionError,
            APIError,
            APITimeoutError,
            AuthenticationError,
            RateLimitError,
        )

        client = self._client()
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT.format(tools=tool_descriptions)},
            {"role": "user", "content": command},
        ]
        last_error: Exception | None = None
        for attempt in range(1 + self._max_retries):
            try:
                response = client.chat.completions.create(
                    model=self._model,
                    messages=messages,  # type: ignore[arg-type]
                    response_format={"type": "json_object"},
                    temperature=0,
                    max_tokens=1000,
                )
                content = response.choices[0].message.content or "{}"
                data = json.loads(content)
                return Plan.model_validate(data)
            except AuthenticationError as exc:
                raise AIConfigError(
                    "OpenAI rejected the API key. Check OPENAI_API_KEY in backend/.env."
                ) from exc
            except RateLimitError as exc:
                last_error = exc
                if attempt < self._max_retries:
                    time.sleep(2**attempt)  # bounded backoff, then give up
                    continue
                raise AIError(
                    "OpenAI rate limit exceeded after retries. Try again in a minute."
                ) from exc
            except APITimeoutError as exc:
                raise AIError(
                    f"OpenAI request timed out after {self._timeout}s. Try again."
                ) from exc
            except APIConnectionError as exc:
                raise AIError(f"Could not reach OpenAI: {exc}. Check your network.") from exc
            except APIError as exc:
                raise AIError(f"OpenAI API error: {exc}") from exc
            except (json.JSONDecodeError, ValueError) as exc:
                raise AIError(f"OpenAI returned an invalid plan: {exc}") from exc
        raise AIError(f"OpenAI request failed: {last_error}")

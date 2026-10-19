"""Explicit cloud failover and shared cooldowns; desktop execution stays in the executor."""
from __future__ import annotations
import hashlib
import threading
import time
from .base import AIConfigError, AIError, AIRateLimitError
from .groq_provider import GroqProvider

_COOLDOWNS = {}
_LOCK = threading.RLock()


class CompatibleAgentProvider(GroqProvider):
    def __init__(self, api_key, model, provider_name, timeout_seconds=30, client=None):
        super().__init__(api_key=api_key, model=model, timeout_seconds=timeout_seconds, client=client)
        self.name = provider_name

    def _get_client(self):
        if self._client is not None:
            return self._client
        from openai import OpenAI
        options = {"api_key": self._api_key, "timeout": self._timeout, "max_retries": 0}
        if self.name == "gemini":
            options["base_url"] = "https://generativelanguage.googleapis.com/v1beta/openai/"
        return OpenAI(**options)

    def complete(self, messages, tools=None):
        from openai import AuthenticationError, RateLimitError, APIError
        kwargs = {"model": self._model, "messages": self._sanitize_messages(messages), "max_completion_tokens": 1600}
        if tools:
            kwargs.update(tools=tools, tool_choice="auto", parallel_tool_calls=False)
        try:
            response = self._get_client().chat.completions.create(**kwargs)
            if getattr(response.choices[0], "finish_reason", None) == "length":
                raise AIError(f"{self.name} response was cut short; no incomplete action was executed.")
            return self._normalize(response)
        except AuthenticationError as exc:
            raise AIConfigError(f"{self.name} backup API key rejected. Update its key in backend/.env.") from exc
        except RateLimitError as exc:
            raise AIRateLimitError(f"{self.name} backup quota/limit reached.", self._rate_limit_retry_delay(exc, 0)) from exc
        except APIError as exc:
            raise AIError(f"{self.name} backup request failed (HTTP {getattr(exc, 'status_code', 'network')}).") from exc


class ResilientProvider(GroqProvider):
    def __init__(self, primary, backup=None):
        super().__init__(api_key=primary._api_key, model=primary._model)
        self.primary = primary
        self.backup = backup
        self.last_provider = primary.name
        self.notice = None

    def _call(self, provider, messages, tools):
        key = hashlib.sha256(f"{provider.name}:{provider._model}:{provider._api_key}".encode()).hexdigest()
        with _LOCK:
            remaining = _COOLDOWNS.get(key, 0) - time.monotonic()
            if remaining > 0:
                raise AIRateLimitError(f"{provider.name} cooldown active.", remaining)
            try:
                result = provider.complete(messages, tools)
            except AIRateLimitError as exc:
                _COOLDOWNS[key] = time.monotonic() + max(5, exc.retry_after)
                raise
        self.last_provider = provider.name
        return result

    def complete(self, messages, tools=None):
        self.notice = None
        try:
            return self._call(self.primary, messages, tools)
        except AIRateLimitError as primary_error:
            if self.backup is None:
                raise
            # Switching changes only the model turn; executed tools are not replayed.
            try:
                result = self._call(self.backup, messages, tools)
                self.notice = f"{self.primary.name} limit par {self.backup.name} backup use hua."
                return result
            except AIRateLimitError as backup_error:
                raise AIRateLimitError("Primary aur backup dono ki limit active hai.", min(primary_error.retry_after, backup_error.retry_after)) from backup_error
            except AIError:
                self.notice = "Backup available nahi; primary reset par task resume ho sakta hai."
                raise AIRateLimitError(self.notice, primary_error.retry_after) from primary_error

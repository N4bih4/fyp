"""Phase 3: provider error matrix, argument integrity, prompt minimisation.

The provider error tests use a stub `groq` module (the real SDK may not be
installed), so they prove our mapping logic, not the SDK's real exception
behaviour. test_groq_provider.py covers the real SDK when it is present.
"""
from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import pytest

from app.ai.base import AIConfigError, AIError, AIRateLimitError
from app.ai.groq_provider import GroqProvider
from app.config import Settings
from app.models import Action, ActionStatus, TaskStatus
from app.orchestration import executor
from app.tools.base import ToolContext
from app.tools.registry import ToolRegistry


# --------------------------------------------------------------- stub SDK
class _E(Exception):
    def __init__(self, message="boom", response=None):
        super().__init__(message)
        self.response = response


def _stub_groq(monkeypatch):
    mod = types.ModuleType("groq")
    for name in ("APIConnectionError", "APIError", "APITimeoutError", "AuthenticationError",
                 "BadRequestError", "NotFoundError", "RateLimitError"):
        setattr(mod, name, type(name, (_E,), {}))
    mod.APITimeoutError = type("APITimeoutError", (mod.APIError,), {})
    mod.APIConnectionError = type("APIConnectionError", (mod.APIError,), {})
    for name in ("AuthenticationError", "BadRequestError", "NotFoundError", "RateLimitError"):
        setattr(mod, name, type(name, (mod.APIError,), {}))
    monkeypatch.setitem(sys.modules, "groq", mod)
    return mod


def _provider(raising):
    class _C:
        class chat:
            class completions:
                @staticmethod
                def create(**kw):
                    raise raising
    return GroqProvider(api_key="k", model="m", client=_C, max_retries=0)


@pytest.mark.parametrize("exc_name,expected", [
    ("AuthenticationError", AIConfigError),
    ("NotFoundError", AIConfigError),
    ("APITimeoutError", AIError),
    ("APIConnectionError", AIError),
    ("APIError", AIError),
    ("BadRequestError", AIError),
])
def test_provider_errors_map_to_typed_errors(monkeypatch, exc_name, expected):
    mod = _stub_groq(monkeypatch)
    with pytest.raises(expected):
        _provider(getattr(mod, exc_name)("x")).complete([{"role": "user", "content": "hi"}])


def test_rate_limit_is_recoverable_and_carries_retry_delay(monkeypatch):
    mod = _stub_groq(monkeypatch)
    resp = types.SimpleNamespace(headers={"retry-after": "42"})
    with pytest.raises(AIRateLimitError) as info:
        _provider(mod.RateLimitError("limit", response=resp)).complete([{"role": "user", "content": "hi"}])
    assert info.value.retry_after == 42


def test_error_messages_never_contain_api_key(monkeypatch):
    mod = _stub_groq(monkeypatch)
    provider = GroqProvider(api_key="SECRET-KEY-123", model="m", client=_provider(mod.AuthenticationError("x"))._client, max_retries=0)
    with pytest.raises(AIConfigError) as info:
        provider.complete([{"role": "user", "content": "hi"}])
    assert "SECRET-KEY-123" not in str(info.value)


def test_missing_key_fails_loudly():
    with pytest.raises(AIConfigError):
        GroqProvider(api_key="", model="m")


# --------------------------------------------------------- argument integrity
def _response(arguments, finish_reason="tool_calls"):
    fn = types.SimpleNamespace(name="create_folder", arguments=arguments)
    call = types.SimpleNamespace(id="c1", function=fn)
    msg = types.SimpleNamespace(content="", tool_calls=[call])
    return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg, finish_reason=finish_reason)])


@pytest.mark.parametrize("raw", ['{"path": "C:/x"', "not json", "[1, 2]", '"str"'])
def test_malformed_arguments_are_flagged_not_defaulted(raw):
    call = GroqProvider._normalize(_response(raw))["tool_calls"][0]
    assert call["invalid_arguments"] is True


def test_valid_arguments_are_not_flagged():
    call = GroqProvider._normalize(_response('{"path": "C:/x"}'))["tool_calls"][0]
    assert call["invalid_arguments"] is False and call["arguments"] == {"path": "C:/x"}


def test_truncated_tool_call_is_rejected():
    with pytest.raises(AIError, match="cut short"):
        GroqProvider._normalize(_response('{"path": "C:/x', finish_reason="length"))


class _ScriptedProvider(GroqProvider):
    def __init__(self, turns):
        super().__init__(api_key="k", model="m", client=object())
        self.turns = list(turns)

    def complete(self, messages, tools=None):
        return self.turns.pop(0)


def test_executor_rejects_invalid_arguments_without_creating_action(db, tmp_path: Path):
    registry = ToolRegistry(ToolContext(allowed_directories=[tmp_path], test_dir=tmp_path))
    settings = Settings(ai_provider="groq", groq_api_key="k", agent_max_steps=4)
    bad = {"id": "c1", "name": "create_folder", "arguments": {}, "raw_arguments": "{}", "invalid_arguments": True}
    provider = _ScriptedProvider([{"content": "", "tool_calls": [bad]}, {"content": "Sorry, please repeat.", "tool_calls": []}])
    task = executor.create_task(db, "make a folder")
    task = executor.start_agent_task(db, task, registry, provider, settings)
    assert task.status == TaskStatus.COMPLETED
    assert task.actions == []
    tool_msgs = [m for m in json.loads(task.agent_state_json)["messages"] if m["role"] == "tool"]
    assert tool_msgs and "not valid JSON" in tool_msgs[0]["content"]


def test_unknown_tool_from_model_is_rejected(db, tmp_path: Path):
    registry = ToolRegistry(ToolContext(allowed_directories=[tmp_path], test_dir=tmp_path))
    settings = Settings(ai_provider="groq", groq_api_key="k", agent_max_steps=4)
    call = {"id": "c1", "name": "run_shell", "arguments": {"cmd": "del /s *"}, "raw_arguments": "{}", "invalid_arguments": False}
    provider = _ScriptedProvider([{"content": "", "tool_calls": [call]}, {"content": "Cannot do that.", "tool_calls": []}])
    task = executor.create_task(db, "wipe disk")
    task = executor.start_agent_task(db, task, registry, provider, settings)
    assert task.actions == [] and task.status == TaskStatus.COMPLETED


# ------------------------------------------------------ prompt minimisation
def test_compact_observation_drops_file_contents_and_bounds_size():
    out = executor._compact_observation({
        "output": {"path": "C:/a.txt", "content": "secret " * 500, "entries": [str(i) for i in range(50)], "note": "x" * 1000},
    })["output"]
    assert out["path"] == "C:/a.txt"
    assert out["content"].startswith("[omitted")
    assert "secret" not in json.dumps(out)
    assert len(out["entries"]) == 10
    assert len(out["note"]) <= 303


def test_follow_up_prompt_keeps_candidate_paths_but_not_file_text(db):
    prior = executor.create_task(db, "Read notes.txt")
    prior.status = TaskStatus.COMPLETED
    db.add(Action(task_id=prior.id, seq=0, tool_name="read_text_file", args_json="{}", risk="low",
                  status=ActionStatus.SUCCEEDED,
                  result_json=json.dumps({"success": True, "output": {"path": "C:/Users/me/notes.txt", "content": "PASSWORD hunter2 " * 40}})))
    db.commit()
    current = executor.create_task(db, "yes, that one")
    text = executor._session_user_message(db, current)
    assert "C:/Users/me/notes.txt" in text
    assert "hunter2" not in text

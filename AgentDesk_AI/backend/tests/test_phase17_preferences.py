"""Preferences, memory store, strict risk policy, local-only mode."""
from __future__ import annotations

import pytest

from app.ai.base import Plan, PlanAction
from app.config import Settings
from app.models import ActionStatus, TaskStatus
from app.orchestration import executor
from app.preferences import PreferencesUpdate, update_preferences
from app.tools.base import ToolContext
from app.tools.registry import ToolRegistry


def test_defaults_and_partial_update(client):
    body = client.get("/preferences").json()
    assert body["risk_policy"] == "standard" and body["listen_mode"] == "push_to_talk"
    assert body["persona"]["name"] == "Agent X" and body["onboarded"] is False
    body = client.put("/preferences", json={"listen_mode": "hands_free", "persona": {"name": "Zara", "language": "en-US",
                                                                                    "style": "brief", "speak_replies": False,
                                                                                    "orb_color": "emerald"}}).json()
    assert body["listen_mode"] == "hands_free" and body["persona"]["name"] == "Zara"
    assert client.get("/preferences").json()["risk_policy"] == "standard"


@pytest.mark.parametrize("payload", [{"groq_api_key": "gsk_x"}, {"risk_policy": "relaxed"}, {"risk_policy": "none"},
                                     {"listen_mode": "always"}, {"persona": {"name": ""}}])
def test_preferences_reject_unknown_or_looser_values(client, payload):
    assert client.put("/preferences", json=payload).status_code == 422


def test_preferences_never_return_secrets(client):
    text = client.get("/preferences").text.casefold()
    for word in ("api_key", "token", "gsk_", "secret"):
        assert word not in text


def test_memory_crud_and_secret_guard(client):
    created = client.post("/memory", json={"kind": "alias", "text": "6th sem means D:\\6th sem"}).json()
    assert client.get("/memory").json()["items"][0]["text"] == "6th sem means D:\\6th sem"
    edited = client.put(f"/memory/{created['id']}", json={"kind": "alias", "text": "lab means D:\\cn\\lab"}).json()
    assert edited["text"] == "lab means D:\\cn\\lab"
    for secret in ("my password: hunter2!", "groq key gsk_ABCDEFGHIJKLMNOP", "atm pin 4321"):
        assert client.post("/memory", json={"text": secret}).status_code == 422
    assert client.delete(f"/memory/{created['id']}").json() == {"deleted": created["id"]}
    assert client.get("/memory").json()["items"] == []
    assert client.delete(f"/memory/{created['id']}").status_code == 404


def test_forget_conversation_hides_older_turns(client, db):
    executor.create_task(db, "volume 30")
    assert client.get("/memory").json()["recent_turns"]
    assert client.post("/memory/forget-conversation").json()["conversation_cutoff"]
    assert client.get("/memory").json()["recent_turns"] == []


def _plan(db, registry, actions):
    task = executor.create_task(db, "x")
    return executor.plan_task(db, task, registry, Settings(), preplanned=Plan(actions=[PlanAction(tool=t, args=a) for t, a in actions]))


def test_strict_policy_requires_approval_even_for_low_risk(db, tmp_path):
    registry = ToolRegistry(ToolContext(allowed_directories=[tmp_path]))
    low = ("list_folder", {"path": str(tmp_path)})
    assert _plan(db, registry, [low]).status == TaskStatus.APPROVED
    update_preferences(db, PreferencesUpdate(risk_policy="strict"))
    task = _plan(db, registry, [low])
    assert task.status == TaskStatus.AWAITING_APPROVAL and task.actions[0].status == ActionStatus.PENDING
    task = executor.create_task(db, "y")
    task = executor.plan_task(db, task, registry, Settings(), auto_approve=True,
                              preplanned=Plan(actions=[PlanAction(tool=low[0], args=low[1])]))
    assert task.actions[0].status == ActionStatus.PENDING  # strict beats internal auto-approve


def test_local_only_mode_never_builds_a_cloud_provider(db, tmp_path, monkeypatch):
    registry = ToolRegistry(ToolContext(allowed_directories=[tmp_path]))
    monkeypatch.setattr(executor, "get_provider", lambda *_: pytest.fail("cloud used in local-only mode"))
    update_preferences(db, PreferencesUpdate(provider_mode="local_only"))
    task = executor.start_task(db, "AI: write me a poem about rain", None, registry,
                               Settings(ai_provider="groq", groq_api_key="gsk_test", ai_cloud_mode="automatic"))
    assert "Local-only mode" in (task.plan_note or "")

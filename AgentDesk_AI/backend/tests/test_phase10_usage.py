"""Phase 10: local entitlements and usage metering."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from app import usage
from app.ai.base import AIConfigError, AIError
from app.ai.groq_provider import GroqProvider
from app.config import Settings
from app.models import TaskStatus, UsageEvent, utcnow
from app.orchestration import executor
from app.tools.base import ToolContext
from app.tools.registry import ToolRegistry


@pytest.fixture()
def plan(monkeypatch):
    """Put the running app on a tiny test plan."""
    from app.config import get_settings

    monkeypatch.setitem(usage.PLANS, "tiny", {"tasks_day": 2, "ai_calls_day": 1, "ai_calls_month": 5})
    monkeypatch.setattr(get_settings(), "entitlement_plan", "tiny")


# ------------------------------------------------------------------ plans
def test_default_plan_is_unlimited_with_no_limits(db):
    settings = Settings()
    assert settings.entitlement_plan == "unlimited"
    snap = usage.snapshot(db, settings)
    assert snap["plan"] == "unlimited" and snap["limits"] == {} and snap["remaining"] == {}


def test_unknown_plan_fails_loudly_not_unlimited():
    with pytest.raises(ValueError, match="Unknown plan"):
        usage.get_plan(Settings(entitlement_plan="platinum"))


def test_plan_names_are_case_insensitive():
    assert usage.get_plan(Settings(entitlement_plan=" FREE "))[0] == "free"


def test_free_is_stricter_than_standard():
    free, standard = usage.PLANS["free"], usage.PLANS["standard"]
    assert all(free[k] < standard[k] for k in free)


# ----------------------------------------------------------------- periods
def test_period_bounds_use_local_midnight_and_month_start():
    tz = timezone(timedelta(hours=5))
    now = datetime(2026, 3, 15, 14, 30, tzinfo=tz)
    b = usage.period_bounds(now)
    assert b["day"] == datetime(2026, 3, 14, 19, 0)  # local 00:00 +05:00 in naive UTC
    assert b["month"] == datetime(2026, 2, 28, 19, 0)
    assert b["next_day"] - b["day"] == timedelta(days=1)


def test_events_before_the_period_do_not_count(db):
    old = utcnow() - timedelta(days=3)
    db.add(UsageEvent(kind="task", ts=old))
    db.add(UsageEvent(kind="task", ts=utcnow()))
    db.commit()
    assert usage.snapshot(db, Settings())["used"]["tasks_day"] == 1


def test_unknown_kind_rejected(db):
    with pytest.raises(ValueError):
        usage.record(db, "coffee")


# ------------------------------------------------------- task limit via API
def test_tasks_are_counted_and_limit_returns_429(client, db, plan):
    assert client.post("/tasks", json={"command": "hello one"}).status_code == 200
    assert client.post("/tasks", json={"command": "hello two"}).status_code == 200
    third = client.post("/tasks", json={"command": "hello three"})
    assert third.status_code == 429
    body = third.json()
    assert "Daily task limit" in body["detail"] and body["usage"]["used"]["tasks_day"] == 2
    assert client.get("/tasks").status_code == 200  # reading history is never blocked


def test_idempotent_replay_is_not_counted_or_blocked(client, db, plan):
    first = client.post("/tasks", json={"command": "hello", "idempotency_key": "k1"}).json()
    client.post("/tasks", json={"command": "hello b"})
    again = client.post("/tasks", json={"command": "hello", "idempotency_key": "k1"})  # limit already reached
    assert again.status_code == 200 and again.json()["id"] == first["id"]
    assert usage.snapshot(db, __import__("app.config", fromlist=["x"]).get_settings())["used"]["tasks_day"] == 2


def test_actions_are_metered_but_not_limited(client, db, plan):
    task = client.post("/tasks", json={"command": "Create a folder called p10_meter in Documents"}).json()
    client.post(f"/tasks/{task['id']}/approve", json={})
    assert client.post(f"/tasks/{task['id']}/run").json()["status"] == "completed"
    from app.config import get_settings

    assert usage.snapshot(db, get_settings())["used"]["actions_day"] == 1


def test_safety_features_work_when_task_limit_is_exhausted(client, db, plan):
    task = client.post("/tasks", json={"command": "Create a folder called p10_safe in Documents"}).json()
    client.post("/tasks", json={"command": "hello two"})
    assert client.post("/tasks", json={"command": "blocked"}).status_code == 429
    assert client.post(f"/tasks/{task['id']}/approve", json={}).status_code == 200
    assert client.post(f"/tasks/{task['id']}/run").json()["status"] == "completed"
    assert client.post(f"/tasks/{task['id']}/rollback").json()["actions"][0]["rollback_status"] == "done"


def test_usage_endpoint_and_config_status(client, plan):
    client.post("/tasks", json={"command": "hello"})
    data = client.get("/usage").json()
    assert data["plan"] == "tiny" and data["used"]["tasks_day"] == 1 and data["remaining"]["tasks_day"] == 1
    assert client.get("/config/status").json()["plan"] == "tiny"


def test_usage_requires_token_when_auth_enabled(client, monkeypatch):
    from app import main as app_main

    monkeypatch.setattr(app_main, "get_api_token", lambda: "s3cret-token-value")
    assert client.get("/usage").status_code == 401
    assert client.get("/usage", headers={"authorization": "Bearer s3cret-token-value"}).status_code == 200


def test_usage_events_hold_no_command_text(client, db):
    client.post("/tasks", json={"command": "my secret plan with password hunter2"})
    rows = db.query(UsageEvent).all()
    assert rows and "hunter2" not in json.dumps([[r.kind, r.task_id, r.units] for r in rows])
    assert {c.name for c in UsageEvent.__table__.columns} == {"id", "ts", "kind", "task_id", "units"}


# ------------------------------------------------- cloud-AI limit in the loop
class _Scripted(GroqProvider):
    def __init__(self, turns):
        super().__init__(api_key="k", model="m", client=object())
        self.turns = list(turns)
        self.calls = 0

    def complete(self, messages, tools=None):
        self.calls += 1
        item = self.turns.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _run_agent(db, tmp_path, provider, settings):
    registry = ToolRegistry(ToolContext(allowed_directories=[tmp_path], test_dir=tmp_path))
    task = executor.create_task(db, "do something")
    return executor.start_agent_task(db, task, registry, provider, settings)


def test_ai_calls_are_counted(db, tmp_path):
    settings = Settings(ai_provider="groq", groq_api_key="k")
    provider = _Scripted([{"content": "Done.", "tool_calls": []}])
    task = _run_agent(db, tmp_path, provider, settings)
    assert task.status == TaskStatus.COMPLETED
    assert usage.snapshot(db, settings)["used"]["ai_calls_day"] == 1


def test_failed_provider_call_still_counts_but_config_error_does_not(db, tmp_path):
    settings = Settings(ai_provider="groq", groq_api_key="k")
    _run_agent(db, tmp_path, _Scripted([AIError("network down")]), settings)
    assert usage.snapshot(db, settings)["used"]["ai_calls_day"] == 1
    _run_agent(db, tmp_path, _Scripted([AIConfigError("bad key")]), settings)
    assert usage.snapshot(db, settings)["used"]["ai_calls_day"] == 1  # nothing was sent


def test_ai_limit_pauses_task_without_calling_provider(db, tmp_path, monkeypatch):
    monkeypatch.setitem(usage.PLANS, "tiny", {"ai_calls_day": 1})
    settings = Settings(ai_provider="groq", groq_api_key="k", entitlement_plan="tiny")
    first = _run_agent(db, tmp_path, _Scripted([{"content": "ok", "tool_calls": []}]), settings)
    assert first.status == TaskStatus.COMPLETED
    blocked_provider = _Scripted([{"content": "must not be reached", "tool_calls": []}])
    second = _run_agent(db, tmp_path, blocked_provider, settings)
    assert blocked_provider.calls == 0, "no provider request may be made once the limit is reached"
    assert second.status == TaskStatus.WAITING_RETRY
    assert "Cloud AI daily limit" in second.plan_note or "limit" in second.plan_note
    assert json.loads(second.agent_state_json)["retry_at"] > 0
    assert usage.snapshot(db, settings)["used"]["ai_calls_day"] == 1  # blocked attempt not counted


def test_local_commands_are_not_limited_by_ai_quota(db, monkeypatch):
    """A local command never reaches the AI path, so an exhausted AI quota cannot block it."""
    monkeypatch.setitem(usage.PLANS, "tiny", {"ai_calls_day": 0})
    settings = Settings(ai_provider="groq", groq_api_key="k", entitlement_plan="tiny")
    usage.check_task(db, settings)  # no task limit defined: allowed
    with pytest.raises(usage.AIQuotaExceeded):
        usage.check_ai(db, settings)


def test_ai_quota_resumes_after_period_rolls_over(db, monkeypatch):
    monkeypatch.setitem(usage.PLANS, "tiny", {"ai_calls_day": 1})
    settings = Settings(ai_provider="groq", groq_api_key="k", entitlement_plan="tiny")
    db.add(UsageEvent(kind="ai_call", ts=utcnow() - timedelta(days=1, hours=1)))  # yesterday's call
    db.commit()
    usage.check_ai(db, settings)  # does not raise: yesterday no longer counts
    usage.record(db, "ai_call")
    with pytest.raises(usage.AIQuotaExceeded) as info:
        usage.check_ai(db, settings)
    assert info.value.retry_after >= 60

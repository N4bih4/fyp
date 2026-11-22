"""Calling an agent by name: a bare "Shadow" is answered and the next request is that agent's."""
from __future__ import annotations

from app.database import SessionLocal
from app.orchestration import address_flow, executor


def _task(db, text):
    task, _ = executor.create_or_get_task(db, text, None)
    return task


def test_a_bare_agent_name_is_answered_and_the_next_request_goes_to_that_agent():
    with SessionLocal() as db:
        address_flow._set(db, None)
        reply = address_flow.greet(db, _task(db, "Shadow."), "Shadow.")
        assert reply is not None and "Shadow" in reply.plan_note and "team lead" in reply.plan_note
        assert address_flow.hand_over(db, _task(db, "x"), "open youtube") == "Shadow, open youtube"
        assert address_flow.hand_over(db, _task(db, "y"), "open youtube") == "open youtube"       # the standby is used up by one request


def test_other_agents_and_whisper_spellings_are_known():
    with SessionLocal() as db:
        for said, name in (("hey Scout", "Scout"), ("Chadow", "Shadow"), ("atlas", "Atlas"), ("شیڈو", "Shadow")):
            address_flow._set(db, None)
            assert address_flow.greet(db, _task(db, said), said) is not None
            assert address_flow._standby(db) == name, said


def test_a_sentence_that_is_more_than_a_name_is_not_a_greeting():
    with SessionLocal() as db:
        assert address_flow.greet(db, _task(db, "Shadow open notepad"), "Shadow open notepad") is None
        assert address_flow.greet(db, _task(db, "open notepad"), "open notepad") is None


def test_a_request_that_names_its_own_agent_keeps_it():
    with SessionLocal() as db:
        address_flow._set(db, "Shadow")
        assert address_flow.hand_over(db, _task(db, "z"), "Scout, search chairs") == "Scout, search chairs"


def test_the_standby_ends_after_a_minute(monkeypatch):
    from datetime import datetime, timedelta, timezone
    with SessionLocal() as db:
        address_flow._set(db, "Echo")
        later = datetime.now(timezone.utc) + timedelta(seconds=address_flow.STANDBY_SECONDS + 5)
        monkeypatch.setattr(address_flow, "_now", lambda: later)
        assert address_flow.hand_over(db, _task(db, "w"), "open youtube") == "open youtube"

# Phase 2 Completion Report: architecture, contracts, state machine

Date: 2026-10-26. Nothing committed.

## Changes
- `backend/app/state.py`: enforced task/action transition tables (SQLAlchemy attribute listeners). Tables derived from transitions observed in the test run plus code reading.
- `backend/app/database.py`: `SCHEMA_VERSION=2` stamped via `PRAGMA user_version`; newer database aborts startup. Existing data untouched.
- `docs/API.md`: all routes documented (added `/reply`, `/browser/*`, request guard, error codes, states); stale "25 tools" in README fixed to 29.
- `docs/audit/ARCHITECTURE.md`: components, data model, state diagrams, error contract; states plainly that there is no separate desktop agent process.
- `tests/test_state_machine.py`: 10 tests (table coverage, terminal states, action cannot run unapproved, legal API flow, schema version, every route documented).

## Results (executed, Python 3.14.7)
Backend (Python 3.14): **292 passed, 13 skipped, 0 failed** (Phase 1: 282 passed; +10 new). Skips are the same SDK-dependent tests as Phase 1.

## NOT VERIFIED / open
- Agent-loop transitions in `state.py` (executing <-> awaiting_approval / waiting_retry) were never executed: groq SDK still not installable here. The listener is strict, so a legitimate unlisted transition in that path would raise at runtime. **Run `test_agent_loop.py` on a provisioned Python 3.12 venv before relying on it.**
- Phase 1's open blocker (groq/openai install, Python 3.12 pins) carries over.
- Docs not re-verified: older docs (`FEATURE_AUDIT.md`, `SECURITY.md`) still carry historical claims and the `auto_approve` finding as written.
- Frontend not touched this phase.


**Update (Phase 3):** the agent-loop blocker is resolved. On Python 3.12 with SDKs the full suite passes (337 passed, 1 skipped) including the agent loop and the state machine.

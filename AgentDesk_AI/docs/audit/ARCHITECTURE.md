# Architecture, Data Model and State Machines (Phase 2 contract)

## Components

| Component | Where | Responsibility |
|---|---|---|
| Frontend | `frontend/` (React, TS, Vite) | Command entry, voice, approvals, history. Talks only to the HTTP API |
| API | `backend/app/main.py` (FastAPI) | Routes, Host/Origin guard, serves built UI |
| Orchestrator | `orchestration/executor.py`, `local_agent.py` | Plan, approval pause, execute, verify, resume |
| Planner / providers | `ai/*` | Local rule routing first; Groq tool-calling loop for unmatched commands (explicit opt-in); OpenAI/Gemini backup; `mock` for tests only |
| Tool registry | `tools/*` (29 tools) | The only things that can act. Pydantic args, server-computed risk, `verify()` |
| Policy | `security/*` | Path containment, risk to approval mapping |
| State machine | `state.py` | Authoritative transition tables, enforced on every status assignment |
| Persistence | SQLite via SQLAlchemy (`models.py`, `database.py`) | Tasks and actions; single user |
| Browser bridge | `browser_bridge.py`, `browser-extension/` | Authenticated local WebSocket to Chrome/Edge |

**There is no separate Windows Desktop Agent process.** The FastAPI backend runs on the user's PC and executes tools in-process, bound to `127.0.0.1:8000`. This is the deliberate single-user prototype design (no microservices). Consequence: anyone who can call the API can act as the user, so request guarding (done) and token authentication (Phase 5) are mandatory before wider use.

## Request flow

`POST /tasks` -> local routing or provider plan -> each action: validate tool name, validate args, compute risk -> LOW auto-approved / MEDIUM, HIGH `pending` -> `approve` -> `run` (atomic claim, timeout, `verify`) -> task `completed` or `failed`. A failed action skips the rest.

## Data model (schema version 5, `PRAGMA user_version`)

**tasks**: `id` (uuid PK), `command`, `idempotency_key` (unique, nullable), `status`, `plan_note`, `error`, `agent_state_json` (provider, message history, fingerprints, retry time), `created_at`, `updated_at`.
**actions**: `id` (uuid PK), `task_id` (FK tasks.id), `seq`, `tool_name`, `args_json`, `risk`, `status`, `result_json`, `verification_json`, `error`, `call_id` (provider tool-call id), `binding_hash`, `approved_at`, `approval_expires_at` (approval binding, Phase 5), `rollback_json`, `rollback_status`, `rollback_detail` (checkpoint and rollback, Phase 6).
Relationship: one task has ordered actions (cascade delete). No foreign keys are enforced by SQLite unless `PRAGMA foreign_keys` is on (it is not).

Versioning: `database.SCHEMA_VERSION`. `init_db()` creates tables, applies idempotent `ALTER TABLE` steps, then stamps `user_version`. A database newer than the app aborts startup. Every future schema change must bump the version and add a step; existing data is never dropped or rewritten without an approved plan.

Approvals: an action's identity is hashed at creation (`security/approvals.py`); approval records time and expiry; the hash is re-checked immediately before the atomic `approved -> running` claim. An altered/expired action goes `approved -> failed` without running.

## Persistence, recovery and logging (Phase 9)

- SQLite runs in WAL mode with `busy_timeout=5000`, `synchronous=NORMAL`, `foreign_keys=ON` so UI polling does not lock out a running task.
- **Restart recovery** (`main.lifespan`): tasks left `executing` become `failed`; a `running` action becomes `failed` with `rollback_status=unsupported` and "outcome is unknown" (its change may have happened); still-`approved` actions become `skipped` and are never replayed. `paused`, `waiting_retry`, `awaiting_approval` and finished tasks are untouched.
- **Logging** (`logging_setup.py`): JSON lines, rotating 5 MB x 3, in `%LOCALAPPDATA%\AgentDesk\logs\agentdesk.log` (`AGENTDESK_LOG_DIR`). Only whitelisted correlation fields are written (request id, task id, action id, tool, status, risk, http status, duration, a truncated detail). Commands, tool arguments, file contents and prompts are never logged; `detail` is truncated to 300 characters and redacted for bearer tokens, `token=`/`api_key=` pairs, Groq/OpenAI/Google key shapes and long opaque tokens. Error details can still contain file paths.
- **Retention** (`retention.py`, `RETENTION_DAYS`, default 0 = off): when enabled, clears the stored AI conversation of finished tasks older than N days and deletes their rollback backup folders (only folders shaped `.agentdesk_checkpoints/<id>/content.bak`), marking the action `rollback_status=expired`. Task rows, actions and results are kept.

## Entitlements and usage metering (Phase 10, local-only)

`usage.py`, table `usage_events` (id, ts, kind = task | action | ai_call, task_id, units; **no command text, arguments or data**, no foreign key so history outlives task cleanup).
- **Plans** from `AGENTDESK_PLAN`: `unlimited` (default; identical to earlier behaviour), `standard`, `free`. Limits: tasks per day, cloud-AI calls per day and per month. Values are placeholders until the release scope fixes real tiers. An unknown plan name stops startup.
- **Enforcement points**: `start_task` (daily task limit; HTTP 429 with a usage snapshot; replays of an existing idempotency key are neither counted nor blocked) and the agent loop before each provider request (limit reached -> task `waiting_retry` until the period resets, no provider request is made). Provider failures that reached the network still count; configuration errors do not. Actions are metered but never limited.
- **Never gated by plan**: local PC commands, approvals, rollback, pause, logging, reading history.
- **Periods** reset at local midnight (day) and the first of the local month (month).
- **Trust model**: this is a budget/metering guard on the user's own machine. Anyone with access to the database or `.env` can change it, so it is not licence enforcement. A paid tier needs a server issuing signed, expiring entitlements, an account system and payment handling; none of that exists or is designed here.

Known gaps (planned): no checkpoints (Phase 6), no usage/entitlement tables (Phase 10), no retention policy for `agent_state_json` (Phase 9).

## Task state machine

```
created -> planned | awaiting_approval | awaiting_input | approved | executing | completed | failed | cancelled
planned -> awaiting_approval | approved | rejected | cancelled | failed
awaiting_approval -> approved | rejected | cancelled | executing
approved -> executing | rejected | cancelled
awaiting_input -> cancelled | rejected
executing -> completed | failed | cancelled | awaiting_approval | awaiting_input | waiting_retry | paused
paused -> executing | cancelled | failed
waiting_retry -> executing | cancelled | failed
completed, failed, cancelled, rejected : terminal
```

## Action state machine

```
pending -> approved | rejected | cancelled
approved -> running | skipped | cancelled | rejected | failed   (failed = approval void or expired)
running -> succeeded | failed
succeeded, failed, rejected, skipped, cancelled : terminal
```
`approved -> running` is the atomic execution claim. An action reaches `succeeded` only if the tool succeeded **and** `verify()` passed.

## Error contract

`404` unknown task; `409` illegal state for the requested operation; `422` invalid body (including unknown fields); `403` Host/Origin guard; tool failures are reported inside `TaskOut` (`status=failed`, `actions[].error`), not as HTTP errors.

## Verification status

Table coverage, terminal-state behaviour, schema stamping and "every route is documented" are enforced by `tests/test_state_machine.py` (executed, passing on Python 3.14). Agent-loop transitions (`executing <-> awaiting_approval / waiting_retry`) are in the table from code reading and are **NOT VERIFIED** by execution (groq SDK missing).

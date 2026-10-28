# Phase 10 Completion Report: entitlements and usage metering (local-only design)

Date: 2026-10-27. Nothing committed.

## Scope decision
The brief makes Phase 10 conditional on the approved release scope, which was not specified. As instructed, this is a **local-only** design: no accounts, no network, no payments, no licence keys. It meters usage and applies plan limits to the two things that cost money or resources (new tasks, cloud-AI calls). It is a budget guard, not licence enforcement: the user can edit `.env` or the database. A real paid tier would need a server issuing signed entitlements; that is out of scope and not simulated.

## Implemented
- `app/usage.py` and table `usage_events` (schema v5; created automatically, no existing data touched).
- Plans `unlimited` (default, no behaviour change), `standard`, `free` via `AGENTDESK_PLAN`; limits are placeholders (free: 20 tasks/day, 20 AI calls/day, 200/month; standard: 200 / 300 / 5000). Unknown plan name stops startup instead of silently meaning unlimited.
- Enforcement: daily task limit in `start_task` (HTTP 429 with message and usage snapshot; idempotent replays unaffected); cloud-AI limit before every provider request in the agent loop (task pauses as `waiting_retry` until the period resets; no request is sent).
- Metering: tasks, executed actions, cloud-AI calls (failed network calls count; config errors and blocked attempts do not).
- `GET /usage` (token-protected, no command text) and `plan` in `/config/status`; UI shows "Plan free: tasks today n/20, cloud AI calls today n/20" for non-unlimited plans.
- Docs: API reference, ARCHITECTURE, `.env.example`.

## Results (executed)
- Python 3.12 + SDKs: **457 passed, 1 skipped**; Python 3.14: 431 passed, 13 skipped; `tsc` and `vite build` pass.
- 19 new tests in `tests/test_phase10_usage.py`: default unlimited, unknown/case-insensitive plan, local-midnight period maths, old events excluded, 429 with usage snapshot, idempotent replay, actions metered not limited, approve/run/rollback still work when the task limit is exhausted, `/usage` and token protection, usage rows contain no command text (column set asserted), AI calls counted, failed call counted but config error not, limit pauses the task with **zero** provider requests, period rollover. Mutation check: removing the AI-limit check made the pause test fail; restored.
- **Real UI check** (throwaway server on the `free` plan, temp data): usage line showed 18/20, two UI commands brought it to 20/20, the next UI command showed "Request failed (429): Daily task limit reached for the 'free' plan (20 tasks). It resets at local midnight." and kept the typed text. Server stopped.

## NOT VERIFIED / limitations
- Cloud-AI limits were tested with a scripted provider only, never against live Groq/Gemini/OpenAI; a quota reset was simulated by back-dating events, not by waiting.
- Counts are per database (per PC), not per person; clearing or editing the database resets them. Time-zone changes or clock edits shift period boundaries.
- Concurrent requests can overshoot a limit by a few units (check-then-record is not atomic).
- Real tier values, upgrade/downgrade flows, grace periods, usage export/reset UI and cost estimation are undefined. Token-count (cost) metering is not done; only call counts.
- Usage events are not covered by retention pruning (they are tiny and hold no content).
- `/reply` and voice follow-ups each count as a new task.

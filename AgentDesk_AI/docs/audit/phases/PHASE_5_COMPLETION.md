# Phase 5 Completion Report: approvals, permissions, API access

Date: 2026-10-26. Nothing committed.

## Changes
- **Approval binding (B-04):** `security/approvals.py`. Every action gets a SHA-256 binding at creation (task, action, tool, canonical args, risk). Approval stores `approved_at` and, for MEDIUM/HIGH, `approval_expires_at` (default 600 s, `APPROVAL_TTL_SECONDS`). The hash and expiry are re-checked right before execution; altered or expired actions end `failed` and run nothing. Schema is now v3 (3 new nullable columns added by the idempotent migration; existing rows are untouched and their missing hash makes them non-runnable until re-planned, which only matters for in-flight tasks).
- **Explicit high-risk approval (B-05):** "approve all" skips HIGH-risk actions; they must be named by id. A bare "yes" approves exactly one on-screen pending action; with several pending it approves only if none is high-risk. UI "Yes, do it" now sends the displayed pending action ids; the per-action Approve button already did.
- **API authentication (B-03):** Bearer token on `/tasks*`, `/config*`, `/tools`. Token is a per-user random secret file (`security/token.py`); launcher passes it to the browser in the URL fragment; the UI keeps it in `sessionStorage`. `launch.py` readiness check sends it. `run_server.py` creates the token file at start.
- Tests: `tests/test_phase5_approvals.py` (15): binding present, args tampered before approval (task rejected), tampered after approval (run refused), expired approval, replay, cross-task id, approve-all vs HIGH, bare-yes with mixed pending, explicit ids, token creation, 401 cases, open health/preflight. Existing tests adjusted for the deliberate behaviour change (HIGH needs named ids).

## Results (executed)
- Python 3.12 + SDKs: **382 passed, 1 skipped**, 0 failed. Frontend `tsc` and `npm run build` pass.
- **Live check** (throwaway uvicorn on port 8765, temp DB and token file, mock provider, then stopped): `/tasks` without token 401; wrong token 401; correct token 200; `/health` 200; foreign Host 403; foreign Origin POST 403; `auto_approve` field 422.

## NOT VERIFIED / limitations
- The UI was not driven in a browser, so the fragment-to-header token flow and "Yes, do it" with ids are verified by typecheck/build only. The launcher (`launch.py`) token changes ran only through the existing mocked startup tests, not a real launch on port 8000.
- The token protects against other websites and unauthenticated callers, not against another process running as the same Windows user, which can read the token file.
- The Phase 1 concurrency and Phase 5 expiry checks are single-process.
- A bare "yes" to one pending HIGH action still approves it (usability decision); the pending action must be the one displayed, and binding/expiry still apply.
- `/browser/connect-token` and `/browser/status` remain unauthenticated (B-18, Phase 8).
- Old tasks planned before the migration have no binding hash and will refuse to run if still approved; not tested against a real pre-v3 database file.
- Prompt-injection resistance was not tested with adversarial content.

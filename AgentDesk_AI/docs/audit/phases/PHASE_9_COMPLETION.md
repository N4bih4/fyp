# Phase 9 Completion Report: persistence, restart recovery, logging, reliability

Date: 2026-10-27. Nothing committed. Tests use temp databases/folders; the kill test uses a separate server process on a free local port.

## Implemented
- **Structured logging (B-08)**: `logging_setup.py`, JSON lines, rotating, whitelisted fields only, redaction of bearer tokens / key shapes / `token=` / long opaque tokens, 300-char truncation. Events: server start/stop, every HTTP request (id, method, path, status, duration; `X-Request-Id` response header), task approval, action start/end/refused, restart recovery, retention.
- **SQLite reliability**: WAL, busy timeout, `synchronous=NORMAL`, foreign keys on. All 438 existing and new tests still pass with foreign keys enforced.
- **Restart recovery**: interrupted actions are marked failed with "outcome unknown, no verified rollback"; approved-but-unstarted actions are skipped and never replayed; other states untouched.
- **Retention (B-09, B-24)**: opt-in `RETENTION_DAYS` (default 0 = nothing is ever deleted). When on, only the stored AI conversation and checkpoint backup folders of finished tasks older than N days are removed, with strict path-shape checks; history rows are kept; actions show `expired`.

## Results (executed)
- Python 3.12 + SDKs: **438 passed, 1 skipped**. Python 3.14: 412 passed, 13 skipped.
- 24 new tests in `tests/test_phase9_reliability.py`, including:
  - **Real kill test**: a helper server makes the folder, then hangs before recording the result; the process is hard-killed; a new server on the same database reports the task `failed` ("interrupt"), the action `failed` with `rollback_status=unsupported` and "outcome unknown", the folder still exists, re-running does not replay it, and `PRAGMA integrity_check` returns ok.
  - Redaction cases for 7 secret shapes; logs from a full task contain no command text, secret or path from the command.
  - Retention off by default; on: old data cleared and recent kept; refuses a `content.bak` in the wrong folder; skips unfinished tasks.
  - WAL/pragmas present; concurrent polling while writing raised no lock errors.
- Mutation checks: disabling redaction and the recovery marking each made the right tests fail; restored.

## NOT VERIFIED / limitations
- The kill test runs one scenario (single action, mock provider, Windows process kill). Power loss, disk-full, corrupted-database and partial-WAL recovery were not tested. No long-running soak or load test.
- Log redaction is pattern-based. Unknown secret formats shorter than 40 characters that are not labelled `token=`/`key=` would be logged; error details may contain file paths or names. Logs are plaintext and not encrypted.
- Logging of the launcher process (`logs/launcher.log`, `logs/backend.log`) was not changed or redacted.
- Retention was tested with temp folders only; it was never enabled on a real database. It does not touch trash, downloads or the user's files, and does not cap log or database size growth beyond log rotation.
- `agent_state_json` still holds full AI conversations indefinitely unless `RETENTION_DAYS` is set.
- Migration from a real pre-v4 database file was still not tested.
- Concurrency tests are single-process; multi-process access to one SQLite file was not tested.

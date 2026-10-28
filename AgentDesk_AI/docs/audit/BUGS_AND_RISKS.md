# Bugs and Risks (Phase 0)

Severity: Critical / High / Medium / Low. Evidence: **VERIFIED** (I executed a probe), **READ** (seen in source, not executed), **SUSPECTED**.
Target phase is where the item will be fixed per IMPLEMENTATION_ROADMAP.md.

| ID | Sev | Evidence | Finding | Target |
|---|---|---|---|---|
| B-01 | Critical | VERIFIED | **Client-controlled approval bypass.** `TaskCreate.auto_approve` (schemas.py) flows to `plan_task`/`start_agent_task`. Probe: `POST /tasks {"command":"Create a folder called probe_1 in Documents","auto_approve":true}` returned `status=completed`, action `create_folder` risk `medium` status `succeeded`, folder exists. Same command with `false` stayed `awaiting_approval`. HIGH-risk tools take the same path (`plan_task` line ~153 approves regardless of risk). The shipped UI does not send it, but any API caller can. | 1 |
| B-02 | High | VERIFIED | **Tool timeout not enforced.** `_run_with_timeout` uses `with ThreadPoolExecutor`, whose exit waits for the worker. Probe: 4 s tool, 1 s timeout → call blocked 4.0 s and then returned "timed out". The tool keeps running and may complete its side effect while the task is reported failed (dishonest outcome). | 1 |
| B-03 | High | READ | **No API authentication or authorization.** Every route (create, approve, run, cancel, tools, config) is open to any local process; CORS limits browsers only. No Host-header validation (DNS-rebinding exposure SUSPECTED). | 1/5 |
| B-04 | High | READ | **Approvals are not bound or expiring.** `approve_task` flips `pending→approved` by id; there is no hash of tool+args+target, no expiry, no check that the action shown to the user is the one executed. Args are immutable in the DB today, which gives implicit binding only. Requirement "bind approvals to exact action and target; reject stale/expired" is NOT IMPLEMENTED. | 5 |
| B-05 | Medium | READ | **Free-text "yes" approves all pending actions** including HIGH risk (`main.reply_task`: `approve_task(db, task_id)` with no action ids), matching a fixed phrase list. No per-action explicit confirmation for HIGH risk. | 5 |
| B-06 | Medium | READ | **No execution lock.** `run_task` / `continue_agent_task` check status then execute with no compare-and-set or lock; two concurrent `/run` calls can both pass the check and execute the same approved action twice. Not reproduced. | 1 |
| B-07 | Medium | READ | **Typed input into a named foreground app is auto-approved** (README/SECURITY: bounded input without approval when the command names the app). Typing into PowerShell/cmd/Run is effectively shell execution, conflicting with "never execute arbitrary shell commands". `control_desktop` internals not line-reviewed. | 4/5 |
| B-08 | Medium | READ | **No application logging.** Zero `logging` usage in `backend/app`; `launch.py` only redirects stdout. SECURITY.md claims errors are logged server-side. No task correlation IDs or structured logs. | 9 |
| B-09 | Medium | READ | **Privacy:** `_session_user_message` embeds prior tasks' commands and tool outputs (up to 4 KB each) in LLM prompts; `agent_state_json` stores full message history indefinitely in SQLite. No retention/redaction policy. | 9 |
| B-10 | Medium | READ | **State machine is informal.** Status strings are set in many places; no transition table; `PLANNED`/`CREATED` rarely distinguishable; no `paused`/`checkpointed`; `awaiting_input` reused for tool-error clarifications. | 2 |
| B-11 | Medium | READ | **Test suite is not hermetic.** `tests/test_startup.py` fails unless `frontend/dist` has been built (2 failures before build, pass after); 13 tests hard-require installed `groq`/`openai` SDKs instead of skipping. | 1 |
| B-12 | Low | READ | **Doc drift.** README says 25 tools, registry exposes 29; mixed Agent X / AgentDesk naming; `agentdesk.spec` docstring says API-only though `main.py` serves the UI; existing `docs/FEATURE_AUDIT.md` test counts (208/236/263/275/300) are historical and conflict. | 2 |
| B-13 | Medium | READ | **Packaging risk:** spec `collect_all` list includes `openai` but not `groq`; PyInstaller build never exercised in this audit. | 12 |
| B-14 | Medium | READ | **Requirements unpinned** (`>=`), `pytest` in runtime requirements, no lock file for Python. Installs are not reproducible. | 1 |
| B-15 | Low | VERIFIED | `npm audit`: 3 moderate (tailwindcss → postcss-nested / postcss-selector-parser). Dev/build-time only; production bundle contains no Tailwind runtime. | 11 |
| B-16 | Medium | READ | **Rollback/checkpoint gaps.** Only delete→trash→restore exists. No generic checkpoints; move/rename/overwrite/edit have no verified rollback. Requirement Phase 6 NOT IMPLEMENTED. | 6 |
| B-17 | Low | READ | `_migrate()` in `database.py` is ad-hoc `ALTER TABLE`; no schema version table. Adequate for prototype; blocks safe schema evolution for new tables (checkpoints, usage). | 2/9 |
| B-18 | Low | READ | Bridge `/browser/connect-token` hands the token to any caller sending header `X-AgentX-Bridge: 1`; simple-request CORS protection only, any local process can obtain it. | 8 |

## Open risks (not defects yet)

- R-1: Download tool validates DNS then connects separately (TOCTOU/DNS rebinding). NOT VERIFIED.
- R-2: Groq/Gemini model IDs in `.env.example` (`openai/gpt-oss-120b`, `gemini-3.8-flash`, `gpt-5.4-mini`) are not validated in this audit; provider behaviour NOT VERIFIED.
- R-3: Hardware tools (Bluetooth/Wi-Fi/brightness/volume) behave per-machine; prior docs claim live verification on one PC. NOT VERIFIED here.
- R-4: Speech recognition uses the browser Web Speech service; audio may leave the device (already disclosed in README).
- R-5: Urdu/Hindi/Roman-Urdu intent routing is rule-based; coverage is limited to tested patterns.

## Status updates

| ID | Status | Date | Evidence |
|---|---|---|---|
| B-01 | FIXED (Phase 1) | 2026-10-26 | `TaskCreate` forbids extra fields; `auto_approve` request now returns 422 and creates no folder. `tests/test_phase1_safety.py` |
| B-02 | FIXED for reporting/blocking; thread cannot be killed | 2026-10-26 | Call returns within the limit; error states the tool may still be running. Test passes. Hard cancellation of in-flight tools is Phase 6 |
| B-03 | PARTIAL | 2026-10-26 | Host-header and foreign-Origin guard added (tests pass). Token authentication still NOT IMPLEMENTED, deferred to Phase 5 because the served UI needs a credential flow |
| B-06 | FIXED (single-process) | 2026-10-26 | Atomic approved→running claim; 3 concurrent `/run` calls produced 1 execution. Not tested against multiple server processes |
| B-11 | FIXED | 2026-10-26 | SDK/dist-dependent tests skip with a visible reason |
| B-14 | PARTIAL | 2026-10-26 | `pytest` moved to `requirements-dev.txt`. Exact pins NOT DONE: could not install on Python 3.12 (network) so versions are unverified |
| B-10 | FIXED (executed paths); agent-loop edges NOT VERIFIED | 2026-10-26 | `state.py` enforced transition tables; `tests/test_state_machine.py` |
| B-12 | PARTIAL | 2026-10-26 | README tool count and API.md corrected; older docs unchanged |
| B-17 | FIXED | 2026-10-26 | `PRAGMA user_version` stamp; newer DB refused |
| B-19 | FIXED (Phase 3) | 2026-10-26 | New finding: malformed tool-call JSON was coerced to `{}` and could run default-argument actions. Tests in `test_phase3_providers.py` |
| B-09 | PARTIAL (Phase 3) | 2026-10-26 | Prompt context minimised; stored `agent_state_json` retention still open (Phase 9) |
| B-11/B-14 | UPDATED | 2026-10-26 | Agent-loop and Groq tests executed and pass on Python 3.12 with SDKs (337 passed, 1 skipped). `requirements.lock.txt` added; installer not switched to it |
| B-07 | FIXED (fake-pyautogui tests); real windows NOT VERIFIED | 2026-10-26 | `is_shell_target` policy, `tests/test_phase4_tools.py` |
| B-20 | FIXED | 2026-10-26 | New: `open_file` could run scripts/executables; blocked, plus script authoring blocked |
| B-21 | FIXED | 2026-10-26 | New: extract overwrote files, no limits |
| B-22 | FIXED | 2026-10-26 | New: allowed roots movable/renamable; ADS names |
| B-23 | FIXED | 2026-10-26 | New: URL typed into shell windows titled "youtube" |
| B-03 | FIXED (token + Host/Origin guard); UI flow NOT VERIFIED in browser | 2026-10-26 | `security/token.py`, middleware; `tests/test_phase5_approvals.py`; live 401/200 check |
| B-04 | FIXED | 2026-10-26 | `security/approvals.py` binding, expiry, re-check before run |
| B-05 | FIXED (single bare "yes" still approves the one on-screen action) | 2026-10-26 | `/reply` and `approve_task` changes |
| B-16 | FIXED for supported file tools; others declared unsupported | 2026-10-26 | `orchestration/rollback.py`, `tests/test_phase6_rollback.py` (20, one mutation-checked) |
| B-24 | OPEN (new) | 2026-10-26 | Pause is not honored by the Groq agent loop; checkpoint backups have no retention/cleanup (Phase 9) |
| B-25 | FIXED (Phase 7) | 2026-10-27 | New, found in real UI: same-origin POSTs rejected on non-8000 ports; command box collapsed; no live progress during run |
| B-26 | OPEN | 2026-10-27 | No automated UI tests; pause/partial banner/native confirm not exercised in a browser |
| B-18 | FIXED in code; live browser NOT VERIFIED | 2026-10-27 | Pairing + bearer-protected connect-token (`tests/test_phase8_bridge.py`, `test_pairing.cjs`) |
| B-27 | FIXED | 2026-10-27 | WebSocket Host check |
| B-28 | FIXED | 2026-10-27 | Tab URLs redacted before leaving the backend |
| B-29 | FIXED | 2026-10-27 | Extension data validated |
| B-30 | OPEN | 2026-10-27 | Real Chrome/Edge never tested; extension hard-wired to port 8000; no extension-id pinning or revocation |
| B-08 | FIXED | 2026-10-27 | `logging_setup.py`; `tests/test_phase9_reliability.py` (redaction mutation-checked) |
| B-09 | FIXED when RETENTION_DAYS is set; default keeps data (user choice) | 2026-10-27 | `retention.py` |
| B-24 | PARTIAL | 2026-10-27 | Backups expire under retention; pause inside the Groq agent loop still not implemented |
| R-7 | OPEN (design) | 2026-10-27 | Local plans are bypassable by editing .env/DB; real licensing needs a server (not designed). Limits are placeholders |
| R-1 / B-31 | FIXED (peer-address check); live public download NOT VERIFIED | 2026-10-27 | `test_connected_peer_address_is_checked_against_dns_rebinding`; GET already sent before the check |
| B-32 | FIXED | 2026-10-27 | `GET /tasks` eager loading; 13.6 -> 7.3 ms |
| B-33 | OPEN (accepted pending pilot) | 2026-10-27 | See residual risk register in FINAL_ACCEPTANCE_AND_SECURITY_REPORT.md (items 1-12) |
| B-34 | FIXED | 2026-10-28 | Idempotency-key race crashed the loser with a unique-constraint error and could start a task twice; `create_or_get_task`; deterministic test reproduces the error without the fix |
| B-35 | FIXED | 2026-10-28 | Frozen-exe path/worker/data-location defects; `app/runtime.py`; exe smoke test passes |
| B-13 | FIXED | 2026-10-28 | Spec rewritten (bundles groq, UI, extension; fails loudly on missing packages) |
| B-14 | FIXED | 2026-10-28 | `requirements.lock.txt` resolved on a clean Python 3.12 venv; suite passes on it; installer uses it |
| B-36 | OPEN | 2026-10-28 | Local NL gaps: "volume kitni hai", "what is the volume" are not understood (other volume phrasings work) |
| B-37 | OPEN | 2026-10-28 | Packaging untested on another PC/Windows version/profile/offline/antivirus; exe unsigned; no uninstaller beyond deleting folders |

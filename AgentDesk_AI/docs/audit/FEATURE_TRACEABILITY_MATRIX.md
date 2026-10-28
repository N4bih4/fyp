# Feature Traceability Matrix (updated after Phase 11)

Status: **PASS** = implemented and the stated behaviour was executed in this environment (automated test or real-browser run). **PARTIAL** = part implemented or part verified. **FAIL**. **NOT IMPLEMENTED**. **NOT VERIFIED** = code exists but it was never executed against the real thing (live device, browser, cloud provider, installer).
The Phase 0 baseline status is shown for comparison. Test files are in `backend/tests/` unless noted.

| Req | Requirement | Phase 0 | Now | Evidence | Remaining gap |
|---|---|---|---|---|---|
| R-01 | Allowlisted tools; no LLM shell/Python | PARTIAL | **PASS** | `test_phase11_security` (invented tools never create actions, script open/author refused, shell typing refused even when approved); bandit: 0 medium/high; no `shell=True`/`eval`/`exec` | Real windows never typed into; `control_desktop` into non-shell apps is allowed with approval |
| R-02 | Validate tool, args, path, permission | PARTIAL | **PASS** | `test_phase11_security` path matrix (9 escape forms x 9 file tools), junction escape, delete refusals, `test_phase4_tools` | Delete may target any absolute path with explicit approval (documented design) |
| R-03 | Server-side risk policy | PARTIAL | **PASS** | `test_permissions`, `test_phase5_approvals`, self-approval via extra args blocked | none known |
| R-04 | Explicit approval for high risk | FAIL | **PASS** | `test_phase5_approvals`, injected-delete test; real UI dialog shows exact action | A bare "yes" approves the one on-screen action (usability decision) |
| R-05 | Approval bound to action; reject stale/altered/expired | NOT IMPL. | **PASS** | SHA-256 binding + expiry; tamper-before/after, expiry, replay, cross-task tests | Single process only |
| R-06 | API authentication | NOT IMPL. | **PASS** | bearer token on all data routes (route-matrix test), Host/Origin guard, real-server 401/200 check, real-browser fragment handoff | Same-Windows-user processes can read the token file |
| R-07 | Verify real outcome before success | PARTIAL | **PARTIAL** | File tools verify on disk; undo verified | Launch-only, system-setting and desktop tools rely on their own result |
| R-08 | Honest timeouts | FAIL | **PARTIAL** | Returns on time and says the tool may still be running | A Python thread cannot be killed |
| R-09 | No duplicate execution | PARTIAL | **PASS** | Atomic claim; idempotency-key race now handled (a real race defect was fixed in Phase 12, deterministic test); 3-way concurrent run against a real server | Single machine/process |
| R-10 | Task-state machine | PARTIAL | **PASS** | `state.py` tables enforced; agent-loop paths executed on 3.12 | none known |
| R-11 | Persistent history | PARTIAL | **PASS** | SQLite WAL, schema v5, opt-in retention | Retention never enabled on real data |
| R-12 | Restart recovery | PARTIAL | **PASS** | Real hard-kill test (`test_phase9_reliability`) | One scenario; no power-loss/corruption tests |
| R-13 | Structured logs | NOT IMPL. | **PASS** | JSON log, redaction (7 secret shapes), no command text | Paths may appear in error detail |
| R-14 | NL understanding and plan | PARTIAL | **PARTIAL** | Rule-based suites pass; compromised-model tests pass | Free-form quality with a live LLM never measured |
| R-15 | Clarification | PARTIAL | **PARTIAL** | Existing conversation tests | Limited multi-turn coverage |
| R-16 | Provider adapter and errors | NOT VERIFIED | **PARTIAL** | Real-SDK tests pass on 3.12; error matrix (stub); malformed/truncated tool calls handled | No live call to Groq/Gemini/OpenAI |
| R-17 | Windows file tools | PARTIAL | **PASS** | `test_tools`, `test_phase4_tools`, `test_phase6_rollback` on temp data | Trash/long-path edge cases |
| R-18 | App launch / URL / YouTube / search | PARTIAL | **NOT VERIFIED** | Mocked launches only | Never launched on a real desktop |
| R-19 | System controls (volume, brightness, Bluetooth, Wi-Fi, Settings) | NOT VERIFIED | **NOT VERIFIED** | Mock tests only; hardware libs not installed in the test venv | Needs the user's PC; Wi-Fi/Bluetooth changes deliberately not run |
| R-20 | Desktop control | NOT VERIFIED | **PARTIAL** | Shell policy and refusals tested with a fake `pyautogui` | Real window activate/close/type untested |
| R-21 | Package search/download | PARTIAL | **PARTIAL** | Code reviewed; argument injection not possible | `winget` never run |
| R-22 | Download safety | PARTIAL | **PASS** (validator) / **NOT VERIFIED** (live) | 25 SSRF URL forms blocked; redirect-to-internal blocked; connected-peer check against DNS rebinding | Live public download not run; peer check happens after the GET is sent |
| R-23 | Checkpoints, rollback, pause/resume | PARTIAL | **PARTIAL** | 20 rollback tests incl. mutation check, real-browser undo | Pause not honoured in the Groq agent loop; system actions unsupported |
| R-24 | Frontend workflows | PARTIAL | **PARTIAL** | Real-browser runs: command, approve, execute, undo, delete+restore, 429 message, usage line, 375 px layout | No automated UI tests; pause and partial banner unseen; no a11y testing |
| R-25 | Voice input | PARTIAL | **PARTIAL** | 4 helper tests | Microphone/hands-free never run |
| R-26 | Browser integration | PARTIAL | **PARTIAL** | Pairing + bridge hardened; 2 Node suites + backend tests | Never loaded into real Chrome/Edge |
| R-27 | Entitlements and metering | NOT IMPL. | **PARTIAL** | Local plans, 429, metering, usage API, real-UI check | Local guard, not licensing; placeholder limits |
| R-28 | Packaging and clean install | NOT VERIFIED | **PASS** (this PC, scratch folder) | Release zip built with guards + manifest; installer positive, negative and idempotent runs; 23/23 clean-install checks through the shipped launcher; exe built and smoke-tested; pinned lock verified by the full suite on a fresh venv | Not tried on another PC/Windows version/user profile, offline, or with antivirus; exe unsigned; no pilot run |
| R-29 | Secrets not in source/logs/responses | PARTIAL | **PASS** | Repo scan test, response/log scan with planted keys, `pip-audit`: none known | Short unlabeled secrets in free text could still be logged |
| R-30 | Documentation and traceability | PARTIAL | **PARTIAL** | `docs/audit/*`, API doc kept in sync by a test | Older docs (FEATURE_AUDIT, SECURITY) still contain historical statements |
| R-31 | Dependency and static scans | n/a | **PASS** | `pip-audit` (locked set): no known vulnerabilities; bandit: 17 Low, 0 Medium/High; `npm audit`: 1 moderate (dev-time) | Hardware libs not scanned (not installed) |
| R-32 | Performance baseline | n/a | **PASS** (baseline only) | `scripts/load_check.py` on this PC, see final report | Not a capacity guarantee |
| R-33 | Reproducible install (pinned deps) | n/a | **PASS** | `requirements.lock.txt` (49 packages incl. hardware libs) resolved in a clean venv; full suite 532 passed on it | Python 3.12 / Windows only |

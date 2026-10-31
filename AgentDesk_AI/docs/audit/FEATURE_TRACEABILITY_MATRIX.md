# Release 0.2.0 — measured results (2026-10-31)

Rule for this table: a status is written only for what was **executed** in this session; everything else is
NOT MEASURED. "Earlier" = the Windows-PC result of 2026-10-27 below, kept for history; it is not re-claimed here.
Environment of every measurement in this table: Linux cloud container, Python 3.13, Node 22, Chromium 153
(headless). No Windows desktop, microphone, speakers, Groq key or internet.

| Req | Requirement | 0.2.0 measured | Measurement (command -> result) | Not measured |
|---|---|---|---|---|
| R-01 | Allowlisted tools; no LLM shell/Python | PASS | `pytest tests` 717 passed incl. phase11 security, NLU "0 invented tools" | — |
| R-02 | Validate tool, args, path, permission | PASS | `validate_plan` tests (unknown tool/arg, bad ref, path outside roots) | — |
| R-03 | Server-side risk policy | PASS | strict policy tests; pilot B: delete = high | — |
| R-04 | Explicit approval for high risk; voice may approve medium only | PASS | `test_conversation_approval_is_bound_to_task` (4 languages); e2e high-risk card; pilot "spoken haan does not delete" | — |
| R-05 | Approval bound to action; stale/altered/expired rejected | PASS | existing approval tests in suite | — |
| R-06 | API authentication | PASS | route-matrix test covers every route incl. /preferences, /memory, /metrics | — |
| R-07 | Verify real outcome before success | PASS (files, browser tab, desktop logic) / NOT MEASURED (Windows) | 29+3 tools have verifiers; executor rejects pass without evidence; `live_check` 15 PASS with evidence; real-browser run | Window/settings/media/WhatsApp/winget verifiers on Windows |
| R-08 | Honest timeouts; timed-out task stopped | PASS | `test_phase16_worker`: worker + grandchild killed, marker never written; executor "Stopped after 2s" | Windows `spawn` worker |
| R-09 | No duplicate execution | PASS | suite (idempotency race test) | — |
| R-10 | Task-state machine | PASS | suite; new paused/partially_completed edges enforced | — |
| R-11 | Persistent history | PASS | pilot F: 7 -> 7 tasks after restart | — |
| R-12 | Restart recovery | PASS | `test_phase9_reliability` real hard kill (suite) | Power loss |
| R-13 | Structured logs, no secrets | PASS | pilot D: planted key in no log file and no API response | — |
| R-14 | NL understanding and plan (Gate G3) | PASS (local matcher) / NOT MEASURED (Groq) | `eval_nlu.py`: 99.3% intent+tool, 99.3% exact args, 0 invented, 0 bypasses; paraphrase probe 20/40 correct, 0 confidently wrong | Groq pipeline, real users' phrasing |
| R-15 | Clarification | PASS (tested set) | clarify items in eval set; follow-up/ordinal tests | Long multi-turn |
| R-16 | Provider adapter and errors | PASS (fakes, offline) / NOT MEASURED (live) | GroqClient 16 tests; pilot D: no network -> clear failed task | Live Groq/Gemini call |
| R-17 | Windows file tools | PASS (on Linux) | `live_check` 15 file tools PASS; pilot B create/undo, overwrite/undo, delete/restore | NTFS-specific cases on Windows |
| R-18 | App launch / URL / YouTube / search | NOT MEASURED | verifiers unit-tested with scripted probe only | Real desktop |
| R-19 | System controls | NOT MEASURED | read-back verifiers unit-tested; Linux run BLOCKED | Windows devices |
| R-20 | Desktop/window control | NOT MEASURED | window-state verifier + save-prompt logic unit-tested | Real windows |
| R-21 | Package search/download/install | NOT MEASURED | `winget_install` 7 tests with fake winget | winget on Windows |
| R-22 | Download safety + pause/resume/cancel | PASS (local server) | real HTTP server + real worker: pause keeps part, resume with Range = identical SHA-256, cancel deletes part | Public internet download |
| R-23 | Checkpoints, rollback, pause/resume | PASS | rollback tests; resume refused when checkpoint no longer holds; pilot undo ×3 | — |
| R-24 | Frontend workflows + accessibility | PASS (Chromium) | Playwright 8/8: onboarding, voice->approve->verified, keyboard only, focus trap + inert, high-risk card, memory, settings, mini orb, accessible names | WebView2 / screen reader |
| R-25 | Voice input | PASS (fake mic) / NOT MEASURED (real) | e2e with fake SpeechRecognition | Microphone, accents, latency |
| R-26 | Browser integration | PASS (Chromium headless, real extension) | `docs/live_runs/2026-10-31-browser-extension.json`: pair, handshake 1.1.0, list, open, close — all verified | Chrome/Edge user profile, YouTube media, 1.0->1.1 upgrade |
| R-27 | Entitlements and metering | PASS (unchanged tests) | suite | — |
| R-28 | Packaging and clean install | PASS (zip) / NOT MEASURED (install) | `build_release.py` -> `AgentDesk-AI-0.2.0-win.zip` 124 files; pilot A: SHA-256 + manifest + forbidden-file checks PASS | INSTALL.cmd / exe on Windows, second PC |
| R-29 | Secrets not in source/logs/responses | PASS | pilot D + suite secret tests; metrics CSV holds no command text/paths (test) | — |
| R-30 | Documentation and traceability | PASS (this table) | API doc route test passes; USER_GUIDE, DEMO_SCRIPT, INTEGRATIONS added | — |
| R-31 | Dependency and static scans | NOT MEASURED (0.2.0) | not re-run this session | pip-audit/bandit/npm audit on 0.2.0 |
| R-32 | Performance | PASS (server part only) | `latency_check.py` 30 local commands: p50 0.036 s, p90 0.054 s, 30/30 < 2.5 s | Speech end -> first spoken word; Groq plan < 4 s |
| R-33 | Reproducible install (pinned deps) | NOT MEASURED (0.2.0) | rapidfuzz, pywinauto added to lock unverified; pywebview/pystray not pinned | Clean Windows venv |
| R-34 | Groq client: timeouts, 429 backoff, usage, redacted logs | PASS (fakes) | 16 tests | Live key |
| R-35 | Every tool returns evidence | PASS | registry test: 32/32 tools have own verifier; executor test | — |
| R-36 | Desktop UI: orb, transcript, preview, memory, settings | PASS (Chromium) | Playwright 8/8 | WebView2 |
| R-37 | Desktop shell: tray, autostart, always-on-top orb | NOT MEASURED | 8 tests with fake pywebview/registry/tray | Windows run |
| R-38 | New user voice command + approve < 3 min | PASS (automated, 3.0 s) / NOT MEASURED (people) | `new_user.test.mjs` | `USABILITY_TEST.md` with 5 people |
| R-39 | Media keys, YouTube playing check | NOT MEASURED | 12 tests with scripted media session | Windows SMTC |
| R-40 | WhatsApp pre-fill, never send | NOT MEASURED | 12 tests (URI, never-send, contact from memory) | WhatsApp Desktop |
| R-41 | Email draft only | PASS | test: mailto only, no SMTP code, no send tool | — |
| R-42 | Pilot metrics export | PASS | 7 tests; pilot run wrote 7 rows automatically | Real pilot data |
| R-43 | Pilot checklist on a second PC | PARTIAL | automated pilot (Linux): 13 PASS, 0 FAIL, 7 NOT RUN (`docs/pilot/`) | Human pilot on a second Windows PC |

---

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

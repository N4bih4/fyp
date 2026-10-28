# Final Acceptance and Security Test Report (Phase 11, updated after Phase 12)

Date: 2026-10-27. Scope: AgentDesk AI as built through Phase 10. Environment: Windows 11, this PC only, Python 3.12.10 (+ SDKs) and 3.14.7 (no SDKs), Node 24. Nothing is committed. All destructive tests used temporary folders and databases.

## 0. Update after Phase 12 (2026-10-28)

Phase 12 closed the packaging gap: a verified release zip and a smoke-tested exe now exist, the dependency set is pinned and verified on a clean Python 3.12 venv (**532 passed, 1 skipped** on exactly those versions, with the real hardware libraries installed), and a clean install through the shipped launcher passes 23/23 checks in a sandboxed profile. Phase 12 also found and fixed one more genuine defect: an **idempotency-key race** (two simultaneous requests with the same key could crash the loser and start a task twice); the earlier Phase 11 test had passed only by luck, and is now backed by a deterministic regression test. Details: `phases/PHASE_12_COMPLETION.md`. A hands-on pilot protocol is in `PILOT_CHECKLIST.md`.

**Verdict is unchanged in substance: not accepted for release until the pilot (live devices, a second PC, real browser extension, optional cloud AI) has been run by a person.** Items 1 and 3 below are now narrower: packaging works on this PC, but live devices and UI automation are still open.

## 1. Verdict

**Not yet accepted for release.** The software core (approvals, execution safety, rollback, recovery, logging, API access control) now passes everything that could be executed here. Release is blocked by things this audit could not do or that belong to Phase 12:

1. Packaging and clean-install were never run (Phase 12).
2. Nothing was run against the real devices and services: volume/brightness/Bluetooth/Wi-Fi, real window control, real app launches, real Chrome/Edge extension, live Groq/Gemini/OpenAI calls, `winget`, microphone.
3. No automated UI tests; the UI was exercised manually in a real browser.
4. The business scope for entitlements is undecided (current plans are placeholders and are not licence enforcement).

A pilot on the user's own PC (Phase 12) is the next gate, with the NOT VERIFIED list below as its checklist.

## 2. Test results (all executed)

| Suite | Result |
|---|---|
| Backend, Python 3.12 + SDKs (`pytest`, 525 tests collected) | **524 passed, 1 skipped** (the opt-in live Groq test), 0 failed |
| Backend, Python 3.14, no SDKs | 498 passed, 13 skipped (SDK-dependent), 0 failed |
| `tsc --noEmit` + `vite build` | pass |
| Frontend voice helpers (Node) | 4/4 |
| Browser-extension logic (Node, mocked Chrome APIs) | `test_controls.cjs` and `test_pairing.cjs` pass |
| Real-server load check (`scripts/load_check.py`) | PASS |
| Real browser, final build | command -> approval dialog -> execute -> verified on disk -> Undo -> verified removed; no command text in the log |
| `pip-audit` (locked Python deps) | no known vulnerabilities |
| `bandit` (backend app) | 17 Low, 0 Medium, 0 High (subprocess/`try-except-pass`/`assert` notes; list-form calls only) |
| `npm audit` | 1 moderate (postcss-selector-parser, build-time only; fix not applied) |
| Secret-shaped strings in tracked files | none (test + earlier scan) |

Baseline (Phase 0) for comparison: 276 passed, 12 failed, 1 error (all failures were missing SDKs). Growth: 289 -> 525 tests.

## 3. Security tests added in Phase 11 (`tests/test_phase11_security.py`, 67 cases)

- **Auth matrix:** every route is enumerated from the app; each (except health/docs/bridge status/WebSocket) returns 401 without the token; near-miss and wrong-scheme headers and a token in the query string are rejected.
- **Compromised model:** a scripted model that proposes anything. Results: injected delete stays pending; 8 invented tool names (shell, powershell, eval, path-like) create no action; opening a `.bat` never reaches the OS; authoring a `.cmd` needs approval and is then refused; extra arguments (`auto_approve`, `approved`, `risk`) do not self-approve; typing into PowerShell is refused after approval (fake `pyautogui`, nothing sent); a download of `169.254.169.254` needs approval and is blocked; text inside a read file ("IGNORE ALL PREVIOUS INSTRUCTIONS...") does not change risk or approval.
- **Path attacks:** 9 escape forms (`..`, other drive, system files, UNC, `\\?\`, relative, `~`, nested traversal) against 9 file tools; a directory junction escape for read and write; delete refuses `C:\`, `C:\Windows`, System32, Program Files, allowed roots, non-empty folders without the explicit flag.
- **SSRF:** 25 URL forms blocked (loopback incl. `127.1`, decimal and hex IPs, `[::1]`, IPv4-mapped IPv6, link-local metadata, RFC1918, CGNAT, `.local`/`.internal`, userinfo, odd ports, `file://`, `ftp://`, `gopher://`, `javascript:`, empty host); redirect to an internal address blocked; **connected-peer check** against DNS rebinding.
- **Fuzzing:** 150 randomized requests across all routes (huge/NUL/unicode/injection strings, wrong JSON types, hostile ids and query values): zero 5xx and zero uncaught exceptions. Oversized/malformed/extra-field bodies rejected with 4xx. SQL-injection-shaped ids return 404.
- **Secrets:** planted Groq/OpenAI keys appear in no API response, OpenAPI document or log file.

## 4. Defects found in Phase 11 and fixed

| ID | Finding | Fix |
|---|---|---|
| R-1 -> B-31 | DNS-rebinding gap in the download tool (validation resolved the host separately from the connection) | After connecting, the real peer address must be public or the download is refused before any body is read. Limitation: the GET has already been sent, so this limits data exposure, not the request |
| B-32 | `GET /tasks` issued one extra query per task and parsed agent state twice | Eager loading and single parse: 13.6 ms -> 7.3 ms per call in-process |
| (test tooling) | First load run reported p50 1.5 s | Measurement artifact: the script opened a new connection per request; fixed to per-thread keep-alive. No server defect |
| (regression, fixed) | My peer check broke an existing test double lacking `extensions` | Tolerant lookup; real responses always have it |

## 5. Performance baseline (this PC, real server process, mock AI, `scripts/load_check.py`)

| Measure | p50 | p95 | notes |
|---|---|---|---|
| `GET /health`, sequential x300 | 1.2 ms | 2.4 ms | |
| `GET /tasks`, 500 requests, 20 concurrent keep-alive clients | 68 ms | 141 ms | ~200 req/s; 0 errors |
| Local task plan -> approve -> run (real folder creation), x50 | 39 ms | 64 ms | 0 failures |
| 20 concurrent requests with one idempotency key | - | - | exactly 1 task, all 200 |
| 60 concurrent task creations | - | - | 60 stored, all 200 |
| Database | integrity ok, WAL, 108 KB | | |

This is a single-user baseline for the local backend, not a capacity claim. Latency of cloud AI calls, hardware tools and real window control was not measured.

## 6. Residual risk register (open items, most important first)

1. **Never run live:** hardware controls, real window/desktop control, app launches, browser extension in Chrome/Edge, Groq/Gemini/OpenAI, `winget`, voice. Highest uncertainty; pilot checklist item.
2. **Same-user trust boundary:** any process running as the same Windows user can read the API token file, the database and the logs. The token defends against websites, other users and unauthenticated callers, not against malware running as the user.
3. **`control_desktop` into ordinary apps** is permitted with approval (and auto-approved when the user names the app and action). Shells/admin tools are blocked, but typing into e.g. a browser or mail client can still do harm.
4. **Thread timeouts cannot cancel work;** a timed-out tool may complete later. The UI says so, but the state must be checked by the user.
5. **No automated UI tests;** pause banner, partial-completion banner and native confirm were not observed in a browser; no accessibility testing.
6. **Local plans are bypassable** (edit `.env`/DB). Not a licensing system.
7. **Pause is not honoured inside the Groq agent loop;** rollback unsupported for system settings, desktop input and launches.
8. **Backups and logs are plaintext;** checkpoint backups of overwritten files live in `.agentdesk_checkpoints` until retention is enabled.
9. **Redaction is pattern-based;** short unlabeled secrets or file paths in error text can reach logs.
10. **Extension trust:** the bridge does not pin an extension id and has no revocation flow; it is fixed to port 8000.
11. **Dependency hygiene:** locked set recorded (`requirements.lock.txt`) but the installer does not yet use it; hardware libraries were never installed or scanned here; one moderate dev-time npm advisory.
12. **Older docs** (`docs/FEATURE_AUDIT.md`, `docs/SECURITY.md`) still hold historical claims that this audit supersedes.

## 7. Definition-of-done check

| Criterion | Status |
|---|---|
| Implementation exists | Yes for all phases 0-11 requirements except items marked NOT IMPLEMENTED/PARTIAL in the matrix |
| Behaviour matches the documented requirement | Verified for the PASS rows; others as listed |
| Positive and negative tests executed | Yes for backend; limited for UI/browser/hardware |
| Errors and security boundaries handled | Yes (section 3) |
| Integration with dependent modules verified | Backend integration and one real-browser path verified; live devices not |
| Documentation and traceability updated | Yes (matrix, bugs, phase reports, API, architecture) |
| No unresolved critical regression | None known; no Critical/High defect remains open in executed code paths |

## 8. Pilot checklist for Phase 12 (what must be run on the user's PC)

Install from a clean state; start via the launcher and confirm token handoff; real volume/brightness change and restore; Wi-Fi/Bluetooth only with the user's explicit authorisation and a recovery plan; open/close a real app window; load the extension in Chrome, pair it, inspect/close a tab, pause/resume a YouTube video; one live Groq command with the user's own key; microphone hands-free; confirm logs contain no secrets; confirm checkpoints and undo on real files in a scratch folder.

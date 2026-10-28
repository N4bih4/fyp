# Implementation Roadmap (from Phase 0 audit)

This supersedes `docs/IMPLEMENTATION_ROADMAP.md` for the 13-phase plan; the older file is retained as history. Each phase ends with a completion report in `docs/audit/phases/` and updated traceability. A phase is accepted only when its criteria below are met by executed tests.

| Phase | Scope (from audit) | Key files | Acceptance criteria |
|---|---|---|---|
| 1 | Fix B-01 (remove client `auto_approve`; server-only, test-only flag), B-02 (real timeout: worker process/thread that is abandoned safely, status honest), B-06 (compare-and-set execution lease), B-11 (hermetic tests; skip when SDK/dist missing or provision them), B-14 (pin deps, dev/runtime split), local API token (B-03 first step) | `schemas.py`, `main.py`, `executor.py`, `tests/`, `requirements*.txt` | probes for B-01/B-02 become regression tests and pass; concurrent `/run` executes once; 13 SDK-dependent tests run green in a provisioned env; full suite documented |
| 2 | State-machine transition table (B-10); API contract and DB docs; schema versioning (B-17); doc cleanup (B-12) | `models.py`, `database.py`, docs | invalid transitions rejected with tests; OpenAPI snapshot matches `docs/API.md` |
| 3 | Planning, clarification, provider error paths (verify R-16 with SDKs); prompt minimisation (B-09) | `ai/*`, `executor.py` | provider error matrix tested (auth, 429, timeout, malformed tool call); no unvalidated tool call executes |
| 4 | Line-review and test every tool; live-test on disposable data; decide `control_desktop` shell-typing policy (B-07) | `tools/*` | per-tool positive/negative tests; destructive tests only on temp dirs |
| 5 | Approval binding (B-04): hash of tool+args+target, expiry, one-shot; explicit per-action HIGH confirmation (B-05); API auth (B-03) | `permissions.py`, `executor.py`, `main.py`, UI | stale/altered/expired/replayed approvals rejected; no path executes MEDIUM/HIGH without a valid approval |
| 6 | Stronger `verify` per tool; checkpoints and verified rollback (B-16); partial-completion record; pause/resume | `tools/*`, `models.py` | rollback reported only after verification; failure leaves accurate partial state |
| 7 | UI approval/progress/history flows; split `App.tsx`; UI tests | `frontend/` | scripted browser run of command→approve→result→history |
| 8 | Browser bridge hardening (B-18), live Chrome tests | `browser_bridge.py`, extension | live tab open/close verified, bridge token flow tightened |
| 9 | Structured logging (B-08), retention/redaction (B-09), restart-recovery tests | `main.py`, `models.py` | kill-during-execution test; logs contain no secrets (tested) |
| 10 | Entitlements/metering only if release scope requires; otherwise record as out of scope | new | decision documented |
| 11 | Full regression, security and performance tests | tests | final acceptance and security report |
| 12 | PyInstaller (B-13), clean-VM install, pilot | spec, scripts | clean-machine install run recorded |

Order rationale: Phase 1 first because B-01 makes every later safety claim false. Approval binding (Phase 5) depends on the state machine (Phase 2) and is therefore not pulled earlier.

## Approval gates and blockers

- Phase 1 requires a network-stable Python environment to install `groq`/`openai`; otherwise the agent-loop tests stay NOT VERIFIED.
- Phase 4/8/12 need the user's Windows PC for live checks and explicit authorization for anything affecting Wi-Fi, Bluetooth or real files.
- Dependency pinning (B-14) changes install behaviour: needs the user's go-ahead on supported Python version (recommend 3.12).

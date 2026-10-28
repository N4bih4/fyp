# Current State Audit (Phase 0)

Audit date: 2026-10-26. Commit audited: `90b382b` (single commit, clean tree).
Product name note: the repository uses "AgentDesk AI" (code, API) and "Agent X AI" (README, launcher, UI strings). This is AgentDesk AI; the dual naming is a documentation defect (see BUGS_AND_RISKS B-12).

Status vocabulary: PASS, PARTIAL, FAIL, NOT IMPLEMENTED, NOT VERIFIED. "Read" = I read the source. "Grep" = located by search only. Nothing below is marked PASS unless I executed it.

## 1. Inventory

| Area | Files | Notes |
|---|---|---|
| Backend (Python/FastAPI) | `backend/app/**` ~7.3k LOC | `main.py` API, `orchestration/` (executor, local_agent), `ai/` (providers, local intent parsing), `tools/` (29 tools), `security/` (paths, permissions), `browser_bridge.py` |
| Frontend (React/TS/Vite/Tailwind) | `frontend/src/App.tsx` (1084 LOC), `api.ts`, `voice.ts` | single large component |
| Browser extension | `browser-extension/` | Chrome/Edge bridge over authenticated WebSocket |
| Tests | `backend/tests/` 289 tests, `frontend/voice.test.mjs` (4), `browser-extension/tests/test_controls.cjs` | |
| Docs | `docs/*.md` (14), `README.md` | extensive, partly stale/inconsistent |
| Launcher/packaging | `launch.py`, `backend/run_server.py`, `backend/agentdesk.spec`, `build_windows.ps1` | PyInstaller not exercised |

Stack matches the intended architecture: React+TS, FastAPI, Pydantic tool schemas, SQLite via SQLAlchemy, provider adapters (`groq`, `openai`, compatible Gemini/OpenAI backup, `mock`), allowlisted tool registry. **There is no separate "local Windows Desktop Agent" process**: the backend itself runs on the user's PC and executes tools in-process (Read: `main.py`, `executor.py`). That is acceptable for a single-user prototype but must be stated in the Phase 2 architecture contract.

## 2. Architecture as implemented (Read)

Flow: `POST /tasks` → `executor.start_task` → (non-mock) `local_agent.prepare_local_request` rule-based routing first; unmatched commands either return a clarification (`ai_cloud_mode=explicit`) or enter the Groq tool-calling loop (`start_agent_task/_agent_loop`). Every proposed tool call is validated against the registry and Pydantic schema, risk is computed server-side, MEDIUM/HIGH actions are persisted as `pending` and the task becomes `awaiting_approval`; `POST /tasks/{id}/approve` then `/run` resumes. Results are verified by `tool.verify()` before an action is marked `succeeded`.

Positive findings (Read):
- Tool names/args validated server-side independent of the LLM (`registry.get`, `validate_args`); unknown tools rejected.
- No `shell=True`, `eval`, or `exec` in `backend/app` (grep). Subprocess use limited to `packages.py`, `system.py`, `platform.py` with list arguments.
- Path policy resolves symlinks and `..` and checks containment (`security/paths.py`).
- Download tool blocks private/loopback hosts, re-validates each redirect, caps size at 20 MB, refuses overwrite (`tools/web.py`). Residual DNS-rebinding race between validation and connection (resolution is done separately from the request) is NOT VERIFIED.
- Browser bridge: extension-only origin check plus per-process random token with constant-time compare.
- Fingerprint de-duplication of repeated tool calls in the agent loop; stuck-`executing` tasks failed on restart (`main.lifespan`).
- No secrets in tracked files (regex scan for Groq/OpenAI/Google key shapes: no hits; `.env`, `*.db`, logs gitignored; history is one commit).

## 3. Requirement-area summary

Detailed per-requirement rows are in FEATURE_TRACEABILITY_MATRIX.md.

| Phase area | State |
|---|---|
| Startup/integration | PARTIAL: starts and serves UI+API in tests; 13 tests cannot run in my environment (missing `groq`/`openai` packages, see BASELINE_TEST_REPORT.md) |
| Security of approvals | FAIL: client-controlled `auto_approve` bypasses approval (verified); no API authentication; approvals not bound to a hash |
| Planning/NLU | PARTIAL: local rule engine plus Groq loop; clarification exists; provider-error handling exists; Groq paths NOT VERIFIED here |
| Windows tools | PARTIAL: 29 tools; hardware-dependent tools NOT VERIFIED in this audit (no live device actions were run) |
| Verification/recovery | PARTIAL: per-action verification exists; timeout enforcement broken (verified); no checkpoints; rollback only via trash/restore |
| Frontend workflows | PARTIAL: builds; behaviour NOT VERIFIED in a browser during Phase 0 |
| Browser integration | PARTIAL: extension tests pass with mocks; live Chrome NOT VERIFIED |
| Persistence/logging | PARTIAL: SQLite tasks/actions; no application logging (zero `logging` use) |
| Monetization | NOT IMPLEMENTED |
| Packaging | NOT VERIFIED |

## 4. Not reviewed in depth

`tools/filesystem.py`, `tools/apps.py`, `tools/desktop.py`, `tools/system*.py`, `orchestration/local_agent.py`, `ai/groq_provider.py`, `frontend/src/App.tsx` and the extension were located and risk-classified by grep and existing docs but not line-reviewed. They are the first targets of Phase 1 and Phase 4 reviews. No claim in this audit about their internal correctness should be read as PASS.

## 5. Constraints encountered

- System Python on PATH is the Microsoft Store stub; Python 3.12/3.13/3.14 are installed under `%LOCALAPPDATA%\Programs\Python`. Tests were run on 3.14.7.
- PyPI downloads were interrupted repeatedly from this environment, so `groq`, `openai`, `pyautogui`, `pycaw`, `screen-brightness-control`, `winsdk` could not be installed. Anything depending on them is NOT VERIFIED, not PASS.
- No live Windows device actions, real downloads, or destructive operations were performed.

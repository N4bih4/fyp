# Dependency and Security Audit (Phase 0)

Method: read `requirements.txt`, `frontend/package.json`, `package-lock.json`; `npm audit`; regex secret scan of tracked files; targeted source reading and grep for dangerous calls. No Python vulnerability scanner was run (could not install tooling reliably, PyPI unreliable here): Python CVE status is **NOT VERIFIED**.

## Python (`backend/requirements.txt`)

| Package | Constraint | Concern |
|---|---|---|
| fastapi, uvicorn[standard], pydantic, pydantic-settings, sqlalchemy, httpx | `>=` | unpinned; installed here: fastapi 0.141.1, pydantic 2.13.5, SQLAlchemy 2.0.54, starlette 1.6.0, httpx 0.28.1 |
| groq>=1.0, openai>=1.40 | `>=` | needed at runtime/tests; NOT installed in the audit environment |
| pyautogui, pycaw, screen-brightness-control, winsdk | `>=` | Windows-only, native; install on Python 3.14 NOT VERIFIED |
| pillow>=10.0 | `>=` | image handling for screenshots |
| pytest>=8.0 | `>=` | test-only dependency listed as runtime |

Recommendations (Phase 1): pin exact versions into a lock file, split `requirements-dev.txt`, document a supported Python version (3.12 is a safer target than 3.14 for native Windows wheels; to be verified), and run `pip-audit` in a network-stable environment.

## Frontend

- Runtime deps: react 18.3, react-dom 18.3 only. Dev: vite 6, tailwindcss 3.4, typescript 5.6.
- `npm audit`: 3 moderate, all in the tailwindcss → postcss-nested / postcss-selector-parser chain; build-time only. No high/critical.
- `npm ci` warned that esbuild's postinstall script is not on an allow-list; build succeeded.

## Secrets

- Tracked-file scan for `gsk_…`, `sk-…`, `AIza…` shaped strings: no matches. `.env`, `*.db`, `logs/` are gitignored. Repository history is a single commit.
- `config/status` returns only booleans for keys (Read).
- Not verified: whether prompts, DB rows (`agent_state_json`) or future logs could contain secrets users type into commands (B-09).

## Attack surface

| Surface | Control present | Gap |
|---|---|---|
| HTTP API on 127.0.0.1:8000 | loopback bind; CORS allow-list | no authentication (B-03); `auto_approve` bypass (B-01); no Host validation |
| Approval flow | server-side risk; pending state | not hash-bound/expiring (B-04); blanket text "yes" (B-05) |
| Tool execution | registry + Pydantic; list-form subprocess; no shell strings | timeout not enforced (B-02); typed input into shells (B-07) |
| Filesystem | resolved-path containment for mutating tools; delete→trash | open/delete scope broader than allow-list by design (documented in SECURITY.md); not line-reviewed |
| Downloads | public-host check, redirects re-checked, 20 MB cap, no overwrite | DNS rebinding race (R-1) |
| Browser bridge | extension origin check, random token, constant-time compare | token obtainable by any local caller with a header (B-18) |
| LLM provider | keys in env only; fixed tool list | prior task outputs sent to cloud (B-09) |
| Packaging | PyInstaller spec | `groq` not collected (B-13); unsigned executable |

## Prompt-injection posture

Tool results (file contents, web pages, window titles) are fed back to the LLM in the agent loop. The defence is architectural (server-side validation and risk), which is only as strong as the approval flow; therefore B-01/B-04/B-05 are prerequisites to claiming injection resistance. Not tested in Phase 0.

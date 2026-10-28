# Baseline Test Report (Phase 0)

Date: 2026-10-26. Commit `90b382b`. Windows 11, Python 3.14.7 (global install), Node v24.18.0. No code was modified to obtain these numbers.

## Results

| Suite | Command | Result |
|---|---|---|
| Backend pytest (first run, no frontend build) | `python -m pytest -q --continue-on-collection-errors` | 14 failed, 1 error (incl. 2 startup tests needing `frontend/dist`) |
| Backend pytest (after `npm run build`) | same | **276 passed, 12 failed, 1 skipped, 1 collection error** (7.7 s) |
| Frontend typecheck + build | `npm ci && npm run build` (`tsc && vite build`) | **PASS** (29 modules; JS 174 kB, CSS 16 kB) |
| Frontend voice helper tests | `node voice.test.mjs` | **PASS** 4/4 |
| Browser-extension mock controls | `node browser-extension/tests/test_controls.cjs` | **PASS** |
| `npm audit` | | 3 moderate (tailwindcss chain), see B-15 |

## The 12 failures and 1 error: NOT VERIFIED, environment-caused

All are `ModuleNotFoundError` for packages in `requirements.txt` that I could not install (PyPI downloads were interrupted in this environment):

- `tests/test_agent_loop.py` (10 tests) and `tests/test_groq_provider.py` (collection error): need `groq`.
- `tests/test_resilience.py` (2 tests): need `openai`.

I confirmed the missing-module cause from the tracebacks for `test_agent_loop`, `test_groq_provider` and `test_resilience`; I did not confirm that these tests pass once the packages are installed. They are therefore **NOT VERIFIED**, neither PASS nor genuine product FAIL. These tests cover the agentic approval loop, so they must be run before Phase 1 sign-off. Action: install the pinned dependencies on a network that allows it (Phase 1, B-14).

The 1 skipped test is the opt-in live Groq test (`test_groq_live.py`); no paid/live API call was made.

## Not executed in Phase 0

- Any hardware/desktop tool against the real machine (volume, Bluetooth, Wi-Fi, brightness, window control).
- Live browser-extension session; live Groq/Gemini/OpenAI calls; PyInstaller build; `backend/scripts/verify_windows.py`.
- Frontend interaction in a browser.

## Extra probes (temporary tests, removed afterward; tree is clean)

| Probe | Observation |
|---|---|
| `_run_with_timeout` with a 4 s tool and 1 s limit | returned after 4.0 s with "timed out" (B-02) |
| `POST /tasks` with `auto_approve: true` and a MEDIUM-risk command | executed immediately; without it, `awaiting_approval` (B-01) |

## Reproduce

```bash
cd backend
python -m pytest -q --continue-on-collection-errors
cd ../frontend && npm ci && npm run build && node voice.test.mjs
node ../browser-extension/tests/test_controls.cjs
```

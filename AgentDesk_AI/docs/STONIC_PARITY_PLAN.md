# Stonic-parity plan: voice control of the whole PC

Status: plan only (2026-11-22). Nothing in this file is built by this document. Each phase below ends with an acceptance test that must be run and shown before the phase counts as done.

## 1. What Stonic AI claims (from its own pages, marketing not verified)

Stonic AI (stonicai.com, Windows 10/11, paid) claims: push-to-talk from any app, open/close apps, create/find files and open known folders, play YouTube, open websites, send a short WhatsApp message by voice, spoken PC status (battery, RAM, storage), memory, Urdu/Hindi-English mix, confirmation before critical actions, action log, and it runs with normal user rights. Its own limits: no terminal, no system settings changes (volume, Wi-Fi, display, power), no email beyond WhatsApp, no reminders or scheduling, no complex step-by-step app operation, no bulk file work, internet required, Windows only.

Implication: this project already covers most of what Stonic claims (see section 2). The real gap is not the feature list. It is that the project's own coverage matrix shows many sentences still need the cloud (slow, needs internet) or fail when run live.

## 2. Measured gaps (run today, not assumed)

Source: `backend/scripts/coverage_live.py --routing` (offline, no side effects). 315 sentences = 105 rows x 3 languages (English, Roman Urdu, Hindi).

- Local planner understood 234 of 315 (74%). 81 fall to the cloud planner (needs internet, several seconds).
- 24 rows fall to cloud in ALL THREE languages (no local parser at all):
  - file operations: find, copy, move, rename, delete, read, write, zip, show deleted
  - apps: close app, switch to app
  - windows: show desktop
  - web: summarise this page
  - mail: write email; chat: WhatsApp message
  - coding: git status, coding agent; packages: install, uninstall
  - info: answer, remember, recall
  - UI: click, type
  - (Summarise a file is local in English only; Roman Urdu and Hindi go to the cloud.)
- Last live run: 35 pass, 8 fail, dated 2026-11-13 (not re-run today). The 8 failures are all YouTube rows (resume, next, skip ad, seek, speed, mute, fullscreen, now playing). Their messages say the browser helper (Agent X extension) is not connected or no YouTube window was seen. So the first suspect is the environment, not the parsers; P2 must confirm this before any code change.
- Rows never run live (`live: no`): gmail, WhatsApp, read/write file, notepad close, Word, VS Code, undo-able settings. These cannot be claimed as working without a live run.
- Safety: routing checks fail on any row where the planned risk is lower than the required risk. None were reported in this run.

## 3. Principles (from the project's own rules, kept)

1. Local first: a sentence the local parser understands must never wait for the cloud.
2. Nothing risky runs silently: delete, uninstall, power, send need an on-screen approval; spoken yes is only for medium risk.
3. Ask when ambiguous (browser, mail app, several matches) instead of guessing.
4. Verify after acting: a task is "done" only when the tool's verification passes.
5. Never type passwords; deletes go to the Recycle Bin.
6. Do not commit unless asked. The working tree already has many uncommitted changes from the user.

## 4. Phases (in order), each with an acceptance test

| # | Phase | Work | Done when |
|---|---|---|---|
| P1 | Local routing for the 3-language cloud gaps | Add local parsers for file find, copy, move, rename, read, show deleted, close app, switch app, show desktop, git status, WhatsApp draft (no send), "what is in my memory" style recall. Keep risk levels from the matrix. | `coverage_live.py --routing` shows `local` for >= 90% of these rows in all 3 languages; no `wrong` or `risk` results; `pytest backend/tests` still green |
| P2 | Fix YouTube live failures | First check that the browser helper (Agent X extension) is connected and a YouTube tab is open. Then diagnose each failing row on the real Chrome YouTube tab (control_browser path). Fix the root cause per row; do not special-case the test sentence. | `coverage_live.py --live --group youtube` passes all YouTube rows with the video state read back |
| P3 | Live proof of the "never run" rows that matter | Run gmail open, WhatsApp draft (stop at approval), read/write a file in a temp folder, close Notepad (approval), with cleanup afterwards. Record results in `docs/eval/coverage_results.json`. | Each row has a real pass/fail and a reason; no row stays "-" without a stated reason |
| P4 | Ask-first for browser and mail | Clarify when several browsers or mail clients exist; no silent default browser. The existing `browser_choice` path already does this; prove it with a live row. | "open browser" asks with the real installed list; test that fails if `open_url` picks a default silently passes |
| P5 | Speed | Put the local model in front of the cloud planner for confident, non-risky intents only after the calibration data is enough (the current log says it is not yet). Until then, measure. | p90 of local commands under 5 s on the checklist (current p90 for local execute+verify is 4.9 s per STATUS log) |
| P6 | Stability soak | Repeat the 102-command soak (`backend/scripts/soak.py`) three times; no stuck lane, no growth in handles. | Three soak runs with `completed` for all non-awaiting commands and handle growth under 10% |

Not in this plan (state it to the user, do not claim it): operating complex in-app software step by step, scheduled tasks, bulk file reorganising, and "working offline". The cloud planner is still needed for open questions.

## 5. How to run each acceptance test

- Routing (no side effects): `backend\.venv\Scripts\python backend\scripts\coverage_live.py --routing`
- Live for one group: `backend\.venv\Scripts\python backend\scripts\coverage_live.py --live --group youtube`
- Unit tests: `backend\.venv\Scripts\python -m pytest backend\tests -q`
- Restart the backend before live checks (the running process keeps old code): kill `launch.py` and `run_server.py` first.

## 6. Risks and what is not verified

- Live rows change the real PC. Run them only with the user present.
- The Stonic page claims are marketing. We have not tested Stonic AI itself.
- The local parser change in P1 can misroute: every new parser needs a negative test.

## 7. Progress (2026-11-22, run with the user present)

- P1 done in code: `backend/app/ai/parity_commands.py` (show deleted, git status, show desktop, switch app, WhatsApp draft, recall, find; copy/move/rename/read without "file"). `show_desktop` added to `control_desktop` (low risk, verified from the foreground window). Routing: 256 local, 18 ask, 41 cloud, 0 wrong, 0 risk (was 235 local, 80 "cloud" that included local questions). Copy/move/rename/read rows show `ask` because the test file does not exist; with a real file they become tool calls (unit-tested with stubbed lookups). Still cloud: file write/delete/zip/summarise in Roman Urdu/Hindi, summarise page, write email, coding agent, install/uninstall, answer, remember, click, type.
- P2 NOT done: all 9 YouTube rows fail with "Cannot access contents of the page. Extension manifest must request permission to access the respective host." The extension is connected (v2.0.0, expected 2.0.0). Retried three times (also with the YouTube tab in front): same error. Chrome's saved settings for the extension (profile 'Profile 2', loaded from this repo's browser-extension folder) show all-sites access granted and nothing withheld, so it is NOT the site-access setting and not the parsers; the cause is still unknown. Next step: open chrome://extensions, Agent X Browser Bridge, 'service worker' and read the console while a row runs. Gmail in Chrome fails the same way ("Browser did not confirm the requested tab navigation").
- P3 done via `backend/scripts/p3_live.py`: write+read a file (approved, verified, read back), close Notepad (ran without a card because the user named app and action; verified gone), WhatsApp draft (asks for the number, cancelled, nothing sent) pass. Gmail fails for the extension reason above. Bug found and fixed: "write X to <path with spaces>" was not understood (also fixed the failing test test_write_and_overwrite_by_command_use_the_local_matcher).
- P4 evidence: live "open gmail" answers "Which browser: Chrome or Edge?" and opens nothing; tests in `test_ask_first.py`.
- P5 measured only: soak p50 0.23 s, p90 0.63 s for local commands. Local-model-before-cloud NOT changed (calibration data still not enough).
- P6: three 3-minute soaks (not the 102-command shape: the script is time based, 141-143 commands each) all finished, handle growth 0%. The only failures are 17 per run of "what is the capital of france" (cloud question, no cloud key set). The memory figure (4.5 MB) looks like the wrong process was sampled, so memory growth is not proven.
- Open observation: an unanswered local question (WhatsApp "what is ahmed's number") swallowed every following unrelated command until "cancel" was said.

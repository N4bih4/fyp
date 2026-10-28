# Phase 12 Completion Report: packaging, clean install, pilot preparation

Date: 2026-10-28. Nothing committed. Wi-Fi and Bluetooth were not touched; no device setting was changed (one read-only volume query was made). All installs ran in scratch folders with the user profile redirected, and the real `%LOCALAPPDATA%\AgentDesk` was verified unchanged.

## Deliverables (in `AgentDesk_AI/dist-release/`, git-ignored)
| File | Size | SHA-256 |
|---|---|---|
| `AgentDesk-AI-0.1.0-win.zip` (source + prebuilt UI + installer) | 288 KB | in the `.sha256` file beside it |
| `AgentDeskAI-exe-0.1.0-win.zip` (PyInstaller one-folder exe, unsigned) | 54.6 MB (139 MB unpacked) | in the `.sha256` file beside it |

New files: `packaging/build_release.py`, `install.ps1`, `INSTALL.cmd`, `README-INSTALL.txt`, `validate_install.py`; `backend/app/runtime.py`, rewritten `backend/agentdesk.spec`, `build_windows.ps1`, `run_server.py`; `docs/INSTALL.md`, `docs/audit/PILOT_CHECKLIST.md`; `START_AGENT_X.cmd` now finds the installer's venv.

## What was done and verified (all executed)
1. **Pinned, installable dependencies (closes B-14).** A fresh Python 3.12 venv installed the whole `requirements.txt` including the Windows hardware libraries (pyautogui, pycaw, screen-brightness-control, winsdk, ...) for the first time; the result was frozen into `requirements.lock.txt` (49 packages). **The full test suite passes on exactly that set: 532 passed, 1 skipped.** Python 3.14 (no SDKs): 506 passed, 13 skipped.
2. **Release builder** refuses to package `.env`, databases, logs, tokens, venvs, tests or secret-shaped strings; writes per-file SHA-256 manifest. The final zip has 103 entries (101 hashed files plus VERSION and MANIFEST), zero suspicious entries, 0 hash mismatches, and its SHA-256 matches the `.sha256` file.
3. **Installer** (`INSTALL.cmd` -> `install.ps1`): requires Python 3.12, creates a private venv inside the folder, installs the pinned set, creates `.env` from the template (no keys), runs an import self-check. Negative test: pointing it at Python 3.14 fails with a clear message, exit 1, creates nothing. Re-running is idempotent. Clean install from the final zip into a brand-new folder: exit 0.
4. **Clean-install validation through the shipped launcher** (`packaging/validate_install.py`, user profile redirected): **23/23 checks pass**: launcher starts the server; UI and JS bundle served; token created in the per-user folder; API 401 without and 200 with the token; no key in config; a real command waits for approval, creates nothing before it, runs, verifies on disk, offers Undo, and Undo removes it; an unmatched command is handled gracefully; database and log created; log contains no command text or token; server stops cleanly; restart through the launcher keeps history; the real profile folder is untouched.
5. **Exe** (PyInstaller one-folder): built; smoke-tested in a sandbox with the working directory elsewhere: serves the bundled UI and extension files (without extension tests), enforces the token, executes and undoes a real command, keeps the database next to the exe, and runs the hardware worker through the exe (`--system-worker`, and through the server path with `get volume`; read-only, returned the real value).
6. **Final regression after all changes:** backend, Node (voice 4/4, extension controls, pairing), `tsc`, `vite build` pass.

## Defects found by packaging work
| ID | Finding | Fix |
|---|---|---|
| B-34 | **Idempotency race (found by a flaky test, genuine defect).** Two concurrent requests with the same idempotency key could both insert; the loser crashed with a database unique-constraint error (HTTP 500), and could have started the same task twice. My Phase 11 test passed earlier only by timing luck | `create_or_get_task` returns `(task, created)`, handles the unique violation by returning the winner, and only the creating request plans, runs or meters the task. Deterministic regression test added; with the fix removed it reproduces the exact error |
| B-35 | Frozen-exe breakages (would only show in an exe): UI resources resolved outside the bundle; hardware worker re-ran `python -m ...` using the exe itself; the working directory (and database) would be a temp extraction folder | `app/runtime.py` (resource root, data root next to the exe, worker command), `run_server.py --system-worker` mode, one-folder spec; 7 packaging tests |
| B-13 | Spec omitted `groq` and bundled only the API | Rewritten spec bundles all runtime packages, fails loudly if one is missing, includes UI and extension files |
| (finding) | "volume kitni hai" and "what is the volume" are not understood by the local parser (only phrasings such as "get volume", "volume check karo", "volume batao") | Not fixed; recorded as a natural-language coverage gap |

## NOT done / NOT verified
- **No pilot was run.** No person used the app; the checklist in `PILOT_CHECKLIST.md` is the pilot protocol. Real hardware *changes*, Wi-Fi, Bluetooth, real window control, a real Chrome/Edge extension, live Groq/Gemini/OpenAI, `winget` and microphone remain unexercised (this audit excluded them or lacked the access).
- **Not tested:** installation on a different PC, a different Windows version, a non-admin or non-English user profile, a path containing spaces or non-ASCII characters, an antivirus that blocks the unsigned exe, a machine without the `py` launcher (only `python` on PATH path exists in code but was not run), or an offline machine (the installer needs the package index).
- The installer requires internet for the one-time dependency install; there is no offline bundle. The exe is unsigned (SmartScreen/antivirus warnings expected) and has no auto-update. No uninstaller beyond deleting folders.
- The old `docs/SETUP_WINDOWS.md` still describes the developer flow; `docs/INSTALL.md` supersedes it for releases.
- `backend/scripts/verify_windows.py` and `verify_phase1.py` were not run (they open apps or change controls).
- Tests are not shipped in the zip; run them from the source tree.

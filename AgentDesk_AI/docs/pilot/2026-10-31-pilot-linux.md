# Automated pilot run — Linux (2026-10-31 10:51 UTC)

Release: `AgentDesk-AI-0.2.0-win.zip`. Machine: Linux-6.18.44-fc-v185-x86_64-with-glibc2.39. Python 3.13.18.
This is the automated part of the checklist on a second machine. It does not replace the human pilot on Windows.

**13 passed, 0 failed, 7 not run.**

| section | check | result | evidence |
|---|---|---|---|
| A | zip SHA-256 matches the .sha256 file | PASS | bb82612561c00775… |
| A | every file matches MANIFEST.sha256 | PASS | 124 files, 0 mismatched |
| A | no .env, database, logs, token or venv in the package | PASS |  |
| A | INSTALL.cmd run on Windows | NOT RUN | needs Windows (install.ps1 / .cmd) |
| A | START_AGENT_X.cmd opens the app | NOT RUN | needs Windows (install.ps1 / .cmd) |
| A | second INSTALL.cmd reuses the environment | NOT RUN | needs Windows (install.ps1 / .cmd) |
| B | create folder: approval shows the exact path, nothing exists before Yes | PASS | shown=/tmp/agentdesk_pilot_83lahz6v/home/Documents/pilot_test |
| B | after Yes: folder exists and the task is verified | PASS | status=completed evidence={'path': '/tmp/agentdesk_pilot_83lahz6v/home/Documents/pilot_test', 'exists': True, 'is_dir': True} |
| B | Undo: folder gone, undone and verified | PASS | rollback=done |
| B | write a text file, overwrite it (high risk), Undo restores the original text | PASS | rollback=done |
| B | delete is high risk; a spoken 'haan' does not delete | PASS |  |
| B | delete after explicit Approve, then Undo returns the file from Trash | PASS | rollback=done |
| B | Cancel on a pending action changes nothing | PASS |  |
| C | volume set (real device) | NOT RUN | not run here: Could not manage system setting: System brightness, volume, and Bluetooth controls are sup |
| D | cloud request with no network: clear error, not left running | PASS | status=failed error=Could not reach Groq: Connection error.. Check your network. |
| D | the API key appears in no log file and no API response | PASS | checked logs + 4 routes |
| F | history is still there after a restart | PASS | 7 -> 7 tasks |
| F | hard kill mid-run shows interrupted, not completed | NOT RUN | covered by tests/test_phase9_reliability.py (real kill); not re-run here |
| F | hands-free voice; own speech ignored | NOT RUN | needs a microphone (person) |
| E | browser extension in a real profile | NOT RUN | see docs/live_runs/*browser-extension.json (Chromium, headless) |

Task metrics written automatically: 7 rows (`2026-10-31-pilot-linux-task_metrics.csv`).
Median task duration 0.08 s (includes scripted approval wait); verified actions 4; statuses cancelled, completed, failed; approvals waited 5.

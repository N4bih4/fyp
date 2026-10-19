# Windows setup guide

Current verification and known limitations (19 October 2026): see [FEATURE_AUDIT.md](FEATURE_AUDIT.md), [TROUBLESHOOTING.md](TROUBLESHOOTING.md), and [WINDOWS_TEST_CHECKLIST.md](WINDOWS_TEST_CHECKLIST.md). Older demo instructions below are not evidence that every feature works. Use direct virtual-environment Python and npm.cmd when PowerShell blocks activation scripts; a broad execution-policy change is unnecessary.

Step-by-step instructions for the FYP demonstration machine. Run every
`powershell` block in **PowerShell** (not CMD). If something looks different
from the "expected" notes, share diagnostic output only after checking that it
contains no secrets. Never share the contents of `.env` or an API key.

## 0. Prerequisites

- **Python 3.11+** — https://www.python.org/downloads/
  (tick **"Add python.exe to PATH"** during installation)
- **Node.js 18+** — https://nodejs.org/
- **Google Chrome** (for the "Open Chrome" demo step; otherwise adapt)
- The `AgentDesk_AI` project folder copied to the laptop, e.g.
  `C:\Users\<you>\AgentDesk_AI`

Verify (expected output shown):

```powershell
python --version   # expected: Python 3.11.x or 3.12.x
node --version     # expected: v18.x.y or newer
npm --version      # expected: 9.x.y or newer
```

## 1. Backend: virtual environment + dependencies

```powershell
cd C:\Users\<you>\AgentDesk_AI\backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Expected: `pip` installs ~15 packages with no red errors. Prompt gains a
`(.venv)` prefix after activation.

> If PowerShell blocks the activation script with an execution-policy error:
> ```powershell
> Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
> ```
> then activate again.

## 2. Backend: configuration

```powershell
copy ..\.env.example .env
notepad .env
```

Run `copy` only if `backend\.env` does not already exist. If it does, open the
existing file in Notepad so you do not overwrite its local settings.

The template selects **Groq** by default. To use real AI, create a key at
https://console.groq.com/keys and enter it locally in `backend\.env`:

```
AI_PROVIDER=groq
AI_MODEL=openai/gpt-oss-120b
GROQ_API_KEY=your-key-here
AGENT_MAX_STEPS=10
```

Replace `your-key-here` with your key in Notepad on your computer; do not
include quotes, send it in chat, or put it in frontend code. Save the file and
restart the backend after changing it. The backend reads the key; the frontend
does not.

For offline testing without a key, explicitly set `AI_PROVIDER=mock` in
`backend\.env`. A missing or invalid Groq key does **not** cause a mock
fallback; real-provider requests fail with an error.

Recommended first-run safety setting — create the folder first, then point the
assistant at it:

```powershell
mkdir C:\Users\<you>\Documents\AgentDeskTest
```

```
AGENTDESK_ALLOWED_DIRECTORIES=C:\Users\<you>\Documents\AgentDeskTest
```

> **Verification runs in mock mode.** The checks in step 4 test the tool,
> permission, and approval layers — not the LLM. Start the server with
> `$env:AI_PROVIDER="mock"` for that step (see step 3). When finished, use a
> new PowerShell window to start the backend normally, or set
> `$env:AI_PROVIDER="groq"` in the current window before restarting it.

To use the alternative OpenAI API later (paid — ask before enabling on a shared
machine):

```
AI_PROVIDER=openai
AI_MODEL=gpt-4o-mini
OPENAI_API_KEY=paste-your-key-here
```

Never commit `.env`, never paste the key into chat, and never put it in
frontend code. The repository `.gitignore` excludes `.env` files.

## 3. Backend: start the server

```powershell
.\.venv\Scripts\Activate.ps1   # if not already active
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

> For the **verification step (step 4)**, start the server in explicit mock
> mode instead, so the checks exercise the tool/permission layers without
> spending Groq calls:
> ```powershell
> $env:AI_PROVIDER="mock"
> uvicorn app.main:app --host 127.0.0.1 --port 8000
> ```
> The environment setting applies to that PowerShell window. To return to
> Groq, open a fresh window or run `$env:AI_PROVIDER="groq"` before restarting
> the server.

Expected (last lines):

```
INFO:     Started server process [...]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
```

Smoke-test in a browser: http://127.0.0.1:8000/health
→ `{"status":"ok","version":"0.1.0"}`.
Interactive API docs: http://127.0.0.1:8000/docs.

## 4. Verify: tools, security, API (do this before the demo)

With the server from step 3 still running, open a **second** PowerShell:

```powershell
cd C:\Users\<you>\AgentDesk_AI\backend
.\.venv\Scripts\Activate.ps1
.\.venv\Scripts\python scripts\verify_windows.py --api
```

Expected: `N/N checks passed` / `All checks passed.`

What it verifies (safe — everything runs in a temp sandbox that is deleted):

- **All 11 tools**: folder create/list/rename/move, ZIP compress/extract,
  delete, app launch (Notepad opens, then is terminated by PID), folder open
  (Explorer), URL open (browser tab to example.com), screenshot (PNG in sandbox)
- **Security**: path traversal blocked, relative paths rejected, zip-slip
  archive blocked, delete refuses non-empty folders and allowed roots,
  move/rename/compress refuse to overwrite
- **API**: health, config (no secret leakage), low-risk auto-approval,
  medium-risk 409-before-approval, high-risk delete needs explicit approval,
  reject executes nothing, idempotency keys, no duplicate execution, honest
  errors for disallowed paths, previous-task summary
- **OpenAI config** (no network calls): SDK installed, key presence reported
  (value never printed), structured-output JSON parsing validated against the
  tool registry, unknown tools and invalid arguments rejected

Run with `--no-gui` to skip the Notepad/Explorer/browser popups.

## 5. Frontend

Third PowerShell (or a new tab):

```powershell
cd C:\Users\<you>\AgentDesk_AI\frontend
npm install
npm run dev
```

Expected last line: `Local: http://localhost:5173/`.
Open http://localhost:5173 — with a configured Groq key, the header badge
should read **"groq connected"**. If Groq is selected but no key is configured,
the UI currently labels its badge **"Mock AI mode"**, but the backend does not
fall back to mock; real requests fail until the key is configured.

## 6. First command in the UI

1. Type: `Create a folder called FYP in Documents` → **Run command**
2. Plan appears: `create_folder`, amber **medium** badge, status `pending`
3. **Approve** → status `approved` → **Execute**
4. Result: `succeeded`, verification `folder exists: True`; confirm the folder
   on disk.

Then try: `Open Chrome` (auto-runs, low risk), `Take a screenshot`
(medium — needs approval), and `Show the result of the previous task`.

## 7. Packaging (only after step 4 is green)

```powershell
cd C:\Users\<you>\AgentDesk_AI\backend
.\build_windows.ps1
```

Produces `dist\AgentDeskAI.exe` (serves the API on 127.0.0.1:8000).
Keep `backend\.env` next to the exe. The frontend still runs via
`npm run dev` or a static server for `frontend\dist`.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `python` not recognized | Reinstall Python with "Add python.exe to PATH" ticked; restart PowerShell |
| Activation blocked by execution policy | `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser` |
| `pip install` fails on one package | `pip install --upgrade pip`, then retry; paste the red error to your assistant |
| `uvicorn : The term 'uvicorn' is not recognized` | Venv not activated — check for the `(.venv)` prompt prefix |
| Port 8000 already in use | `netstat -ano \| findstr :8000` then `taskkill /PID <pid> /F`, or use `--port 8001` (and update the frontend `src/api.ts` base URL) |
| Frontend `fetch failed` / blank task list | Backend not running, or wrong port; check `http://127.0.0.1:8000/health` first |
| `npm install` very slow / errors | Check Node 18+; delete `node_modules` and retry; paste errors |
| Folder creation fails with "Access is denied" | Choose a location your Windows account can write to; folder creation requires confirmation and follows Windows permissions |
| Other file operations say "Path is outside the allowed directories" | Add the location to `AGENTDESK_ALLOWED_DIRECTORIES` in `backend\.env`, **restart** the server. Delete is allowed outside this list but still needs explicit approval and only accepts files or empty folders. |
| "GROQ_API_KEY is not set" | Set it in `backend\.env`, or explicitly set `AI_PROVIDER=mock` for offline testing |
| "Application 'chrome' was not found" | Install Chrome, or use an installed app name; add it to `AGENTDESK_APPROVED_APPLICATIONS` |
| Notepad shows "Cannot find the ..." for a deleted file every time it opens | Windows 11 Notepad restores tabs from the previous session. Open Notepad → Settings (gear icon) → "When Notepad starts" → select **"Open a new window"**, then close the stale tab. This is a Notepad setting, not an AgentDesk AI bug — verify by launching Notepad manually (Win+R → `notepad`) |
| Screenshot fails | Headless/remote session — Pillow's `ImageGrab` needs a real desktop session |
| `verify_windows.py` API section fails at "API reachable" | Server from step 3 isn't running on port 8000 |

## When something fails

Copy the **full** PowerShell output (command + all output, including red text)
and send it to your assistant. Also note: which step you were on, and the
contents of `backend\.env` **with the API key redacted**.

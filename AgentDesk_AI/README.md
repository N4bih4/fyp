# Agent X AI

**Start:** double-click `START_AGENT_X.cmd` in the workspace root. It opens http://127.0.0.1:8000 with the UI and backend served together. No separate frontend/backend terminals are needed for normal use.

See [the Agent X guide](docs/AGENT_X_GUIDE.md) for conversational confirmations, folder disambiguation, app downloads, and startup instructions.

**Final Year Project — an AI-powered Windows desktop assistant.**

AgentDesk AI lets you control supported computer operations with natural-language
text commands. It understands a command, creates a structured plan, selects
approved tools, enforces permissions, executes the actions, verifies the
outcomes, and reports the results.

Use the microphone button for hands-free commands in Urdu, Hindi, or English.
Voice recognition needs a supported browser (Chrome recommended), microphone
permission, and internet access. The transcript is sent to the configured AI
provider, and task results can be spoken aloud. Speech recognition uses the
browser's Web Speech service (not an offline/local recognizer), which may send
audio to the browser vendor's service. If that service has a network outage,
hands-free mode retries automatically. Keep hands-free mode enabled to speak
additional commands while a task is running; they are queued and executed one
at a time. Review and approve actions marked as requiring approval in the UI.

On Windows, the `control_desktop` tool can inspect the active window and perform
up to eight mouse/keyboard actions in the foreground application, including
closing a uniquely matched window on explicit request. When your command names
the app and the action, bounded input is performed without a separate approval;
unnamed or mismatched targets still require approval. The backend verifies a
window is gone before reporting a close as successful. Named close requests
(for example "Close Eclipse") run after the usual target match; unnamed close
requests still need approval. This uses screen
coordinates and is not guaranteed to work in every application or protected
window; it is not a full Gemini clone or unattended control of every app.

Opening an already-running app reuses its window when possible. YouTube search
uses YouTube results and reuses a visible YouTube window on Windows; it does
not automatically select or start a video. If you explicitly ask to play a
named video/song, the assistant opens the closest matching watch page; if the
match is unclear, it opens results so you can choose. Browser or YouTube
autoplay settings may still require you to press Play.

Example commands:

- "Open Chrome."
- "Open my Downloads folder."
- "Create a folder called FYP in Documents."
- "Copy the file C:\Temp\notes.txt to C:\Temp\backup."
- "Rename the file C:\Temp\notes.txt to todo.txt."
- "Compress the folder C:\Temp\project into a ZIP archive."
- "Extract the archive C:\Temp\project.zip."
- "Write an email to user@example.com with subject Project update and body ..."
- "Open the website example.com."
- "Set brightness to 40%." / "Turn volume up." / "Turn Bluetooth off."
- "Search YouTube for relaxing piano music."
- "Create a text file called notes.txt in Documents with ..."
- "Download https://example.com/report.pdf to Documents."
- "Show the result of the previous task."

## Architecture

```
┌──────────────┐      ┌──────────────────────────────┐
│   Frontend   │      │           Backend            │
│ React + TS   │─────▶│  FastAPI + SQLite            │
│ Vite +       │◀─────│  ┌─────────┐  ┌───────────┐  │
│ Tailwind     │      │  │ AI plan │  │   Tool    │  │
└──────────────┘      │  │(Groq/   │─▶│ registry  │──┼─▶ Windows
│  │ OpenAI) │  │(25 tools) │  │
                      │  └─────────┘  └───────────┘  │
                      │  ┌────────────────────────┐  │
                      │  │ Permission engine +    │  │
                      │  │ approval workflow      │  │
                      │  └────────────────────────┘  │
                      └──────────────────────────────┘
```

**Execution pipeline:**
Understand Command → Generate Plan → Validate Plan → Select Tool →
Check Permission → Request Approval (when required) → Execute →
Verify → Report or Recover.

The AI only ever returns **structured data** (tool name + arguments). It can never
emit arbitrary Python, PowerShell, or shell commands — every tool name and
argument is validated by the backend independently of the model.

## Tech stack

| Layer    | Technology                              |
|----------|-----------------------------------------|
| Frontend | React, TypeScript, Vite, Tailwind CSS   |
| Backend  | Python, FastAPI, Pydantic, SQLAlchemy   |
| Database | SQLite                                  |
| AI       | Groq API (primary), OpenAI API, or explicit mock mode |
| Testing  | pytest (backend), Vite build (frontend)  |

## Quickstart (Windows)

Prerequisites: **Python 3.11+**, **Node.js 18+**. Full details in
[`docs/SETUP_WINDOWS.md`](docs/SETUP_WINDOWS.md).

```powershell
# 1. Backend
cd AgentDesk_AI\backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy ..\.env.example .env
notepad .env                      # set GROQ_API_KEY locally (see Configuration)
uvicorn app.main:app --host 127.0.0.1 --port 8000

# 2. Frontend (new terminal)
cd AgentDesk_AI\frontend
npm install
npm run dev                      # http://localhost:5173
```

Open http://localhost:5173, speak or type a command, review the plan, approve
it, and run. Review every requested keyboard/mouse action before approving.

## Configuration

Copy `.env.example` to `backend/.env` and configure it there. The template
selects Groq by default; set `GROQ_API_KEY` in this local file before using
real AI. If `backend/.env` already exists, edit it rather than overwriting it.
Do not put the key in frontend files, source control, or chat.

| Variable | Purpose | Default |
|---|---|---|
| `AI_PROVIDER` | `groq` for real AI, `openai` for the alternative, `mock` for explicit offline mode | `groq` |
| `AI_MODEL` | Groq tool-calling model ID (check Groq's current model catalogue) | `openai/gpt-oss-120b` |
| `GROQ_API_KEY` | Groq secret key — **backend/.env only; never commit or put in frontend** | _(empty; required for Groq)_ |
| `OPENAI_API_KEY` | Optional OpenAI secret — **backend/.env only** | _(empty)_ |
| `DATABASE_URL` | SQLite location | `sqlite:///./agentdesk.db` |
| `FRONTEND_ORIGIN` | CORS origin for the UI | `http://localhost:5173` |
| `AGENTDESK_ALLOWED_DIRECTORIES` | Dirs the assistant may create/edit/delete in. Opening an existing folder (including other drives) does not require this list | home dir + `./agentdesk_test` |
| `AGENTDESK_APPROVED_APPLICATIONS` | Apps launchable without approval | `chrome,notepad,calc,explorer` |
| `TOOL_TIMEOUT_SECONDS` | Per-tool execution timeout | `30` |

With a configured Groq key, the UI header shows **"groq connected"**. If Groq
is selected but not configured, the UI currently labels its status badge
**"Mock AI mode"**; this is only a badge fallback, not a backend provider
fallback. Requests still fail until Groq is configured. Mock mode is selected
only by setting `AI_PROVIDER=mock`.

On Windows, `manage_system_setting` can read/change display brightness and
master volume, mute/unmute audio, and read/toggle the Bluetooth radio.
Changes require confirmation; brightness and volume adjustments default to
10 percentage points. Brightness control depends on the display exposing a
Windows-supported brightness interface, and Bluetooth toggling depends on
Windows granting radio access.

## AI provider setup

**Groq is the default provider** — a real LLM with real function calling.
Create a local key at https://console.groq.com/keys, then enter it only in
`backend/.env`. See [`docs/GROQ_SETUP.md`](docs/GROQ_SETUP.md).

```ini
# backend/.env
AI_PROVIDER=groq
AI_MODEL=openai/gpt-oss-120b
GROQ_API_KEY=<your Groq key>
```

Replace the placeholder locally; do not send the key in chat or add it to
frontend code. Restart the backend after editing `.env`.

How it works: the model proposes **one tool call at a time**; the backend
validates it, the permission engine checks risk (low runs at once,
medium/high pause for your approval), the real tool executes, and the result
goes back to the model for the next step — bounded by `AGENT_MAX_STEPS`.

If Groq is misconfigured or unreachable, tasks **fail with a clear error** —
never a silent mock fallback. `AI_PROVIDER=mock` remains available as an
**explicit** offline/test mode (used by the automated test suite, which costs
nothing to run).

## Usage, privacy, and current limits

- Each real model turn is an external Groq/OpenAI API request. A multi-step
  task may use several turns up to `AGENT_MAX_STEPS`; provider pricing, model
  access, and quotas change, so check your account's current limits.
- Speech recognition uses the browser's Web Speech service, not a local
  recognizer. Browser speech services may send audio over the network. The
  transcript is sent to the configured AI provider; microphone audio is not
  sent to this project's backend.
- Screenshots are saved locally to an allowed directory and are not sent to
  the model automatically.
- App control is limited to validated tools and foreground keyboard/mouse
  actions with approval. Protected windows and app-specific workflows may not
  work. Playwright browser automation and screenshot/image understanding are
  not implemented yet.
- Keep the backend on localhost. This MVP does not authenticate users and must
  not be exposed to a public network as-is.

## Testing

```powershell
cd AgentDesk_AI\backend
.venv\Scripts\activate
python -m pytest tests/ -q
```

The suite (42 tests) covers path/traversal security, every tool's
execute + verify logic, the permission matrix, plan validation (unknown tools
and bad arguments are rejected), and the full HTTP workflow with the mock
provider — including approval, rejection, idempotency, and no-duplicate-execution.
Mock mode means the suite costs nothing to run.

## Security model

- **Low risk** (auto-run): opening approved apps/folders, listing folders.
- **Medium risk** (needs confirmation): creating, moving, renaming, compressing.
- **High risk** (needs explicit approval): deleting, unapproved apps, unnamed
  or mismatched window closes.
- Allowed-directory enforcement with path normalization and traversal protection.
- Zip-slip protection on extraction; no-overwrite policy on move/rename/compress.
- Per-tool timeouts, idempotency keys, no re-execution of finished tasks.
- Backend binds to localhost only; secrets stay in `backend/.env`.

Details and known limitations: [`docs/SECURITY.md`](docs/SECURITY.md).

## API

Health, config status, task planning/execution, approval, history — documented in
[`docs/API.md`](docs/API.md). Interactive docs: http://127.0.0.1:8000/docs.

## Project structure

```
AgentDesk_AI/
├── .env.example            # placeholder config (no real secrets)
├── backend/
│   ├── requirements.txt
│   └── app/
│       ├── main.py         # FastAPI app + endpoints
│       ├── config.py       # env-based settings
│       ├── models.py       # Task/Action tables
│       ├── ai/             # provider abstraction, Groq + OpenAI + mock, planner
│       ├── tools/          # tool registry (filesystem/apps/system/web)
│       ├── security/       # path policy + permission engine
│       └── orchestration/  # plan → approve → execute → verify
│   └── tests/              # backend pytest suite
├── frontend/               # React + TS + Vite + Tailwind UI
└── docs/                   # setup, API, security, deployment guides
```

## Honest limitations

- Developed and tested on Linux; Windows application launching and
  `os.startfile` paths are implemented but need verification on a real Windows
  machine (see `docs/SETUP_WINDOWS.md`).
- The mock planner understands a fixed command set; the Groq and OpenAI
  planners use real LLMs and are more flexible.
- Web search opens Google results in the system browser; it does not read pages
  or control browser tabs. Public direct-file downloads and saving HTML pages
  are supported, with a 20 MB limit and approval. YouTube/video extraction is
  not supported.
- Text documents can be created, read, opened, and replaced. Replacements,
  downloads, and Trash restores require approval. Deletes move files and empty
  folders to AgentDesk's internal Trash; this is separate from the Windows
  Recycle Bin.
- When you ask the assistant to read a text file, its contents are sent to your
  configured AI provider. Review sensitive content before asking it to read.
- Copy, move, rename, ZIP, and unzip operations are supported inside allowed
  directories and refuse to overwrite existing destinations. Email compose
  opens a draft in the default email app; AgentDesk never sends the email.
- Voice commands use the browser Web Speech service as described above;
  advanced browser automation is out of scope for this MVP.

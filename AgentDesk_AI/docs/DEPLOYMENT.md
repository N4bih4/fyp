# Deployment & cost guide

## Local deployment (recommended for the FYP)

The MVP is designed to run on the user's own Windows machine:

1. Follow [`SETUP_WINDOWS.md`](SETUP_WINDOWS.md).
2. Keep the backend on `127.0.0.1:8000` and the frontend on `localhost:5173`.
3. Demo with `AI_PROVIDER=mock` for reliability, then show the OpenAI mode.

## Packaging

Two artifacts are built; the first is the supported one. Details: [INSTALL.md](INSTALL.md).

1. **Release zip** (source + prebuilt UI + pinned requirements + `INSTALL.cmd`): build the UI (`npm run build` in `frontend/`),
   then `python packaging/build_release.py --out <dir>`. The builder refuses to produce a zip containing `.env` files,
   databases, logs, tokens, virtual environments, tests or secret-shaped strings, writes a SHA-256 per file
   (`MANIFEST.sha256`) and a `.sha256` next to the zip. Validate an installed copy with
   `python packaging/validate_install.py <installed AgentDesk-AI folder>`.
2. **Single-folder exe** (`backend/build_windows.ps1`, PyInstaller). Unsigned. Keeps its database and `.env` next to the exe.

The frontend is not wrapped in Electron/Tauri; the app is a local web UI served by the backend on `127.0.0.1:8000`.

## Cost breakdown

| Item | Cost |
|---|---|
| Running locally (Python, Node, SQLite) | Free |
| Mock AI mode | Free, offline |
| OpenAI API (planning calls only) | **Paid per use** — check current pricing; only the command-understanding call hits the API, never filesystem operations |
| Optional cloud hosting / domains | Paid, not required for the MVP |

### Keeping API costs down

- The LLM is used **once per command** (planning), not per file operation.
- Prompts are capped (`max_tokens=1000`, temperature 0); screenshots and local
  file contents are never sent to the provider.
- Rate limits get one bounded retry with backoff, then a clear error — the app
  never retries expensive calls in a loop.
- Tests always use the mock provider: the suite costs nothing to run.
- Model IDs and prices change: verify against the provider's current docs
  before budgeting; never assume a model is free.

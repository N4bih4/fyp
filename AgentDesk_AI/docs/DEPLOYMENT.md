# Deployment & cost guide

## Local deployment (recommended for the FYP)

The MVP is designed to run on the user's own Windows machine:

1. Follow [`SETUP_WINDOWS.md`](SETUP_WINDOWS.md).
2. Keep the backend on `127.0.0.1:8000` and the frontend on `localhost:5173`.
3. Demo with `AI_PROVIDER=mock` for reliability, then show the OpenAI mode.

## Packaging (optional)

To distribute a desktop-style package later:

- Backend: [PyInstaller](https://pyinstaller.org/) can bundle the FastAPI app
  (`pyinstaller --onefile` with uvicorn). Not done in this MVP — verify the
  app on Windows first.
- Frontend: `npm run build` produces static files in `frontend/dist/` that any
  static server can host, or that an Electron/Tauri shell can wrap.

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

# Installing Agent X AI / AgentDesk AI (release zip)

This is the supported way to install a packaged release. For development setup see [SETUP_WINDOWS.md](SETUP_WINDOWS.md).

## Requirements

- Windows 10/11, **Python 3.12** (only this version was tested): https://www.python.org/downloads/ (tick "Add python.exe to PATH")
- Internet for the one-time dependency install. Node.js is **not** needed (the web UI is prebuilt).

## Steps

1. Verify the download (optional): `Get-FileHash AgentDesk-AI-0.1.0-win.zip -Algorithm SHA256` must equal the value in the `.sha256` file next to it.
2. Extract the zip to a folder you own (for example `C:\Users\<you>\AgentDesk-AI`), not Program Files.
3. Double-click **INSTALL.cmd**. It creates a private `.venv` inside the folder and installs pinned packages. It changes nothing outside the folder: no registry, PATH, Wi-Fi, Bluetooth or system settings. Re-running it is safe; it resumes and reuses the environment.
4. Double-click **START_AGENT_X.cmd**. The browser opens the app at `http://127.0.0.1:8000/`. Local PC commands work immediately.
5. Optional cloud AI: edit `AgentDesk_AI\backend\.env` and set `GROQ_API_KEY=` to your own key. Never share the file.
6. Optional browser tab control: follow [BROWSER_CONTROLS.md](BROWSER_CONTROLS.md) (load the extension, then open its setup page from the app link to pair).

## Where data lives

| What | Where |
|---|---|
| Task history | `AgentDesk_AI\backend\agentdesk.db` |
| Settings | `AgentDesk_AI\backend\.env` |
| Logs and API token | `%LOCALAPPDATA%\AgentDesk\` |
| Rollback checkpoints | `.agentdesk_checkpoints` inside the folder where you changed a file |

To uninstall: close the app, delete the install folder and `%LOCALAPPDATA%\AgentDesk`.

## Installer problems

| Message | Fix |
|---|---|
| "Python 3.12 was not found" | Install Python 3.12, or run `powershell -File install.ps1 -PythonExe C:\path\to\python.exe` |
| "... is not Python 3.12" | Only 3.12 is supported; delete `AgentDesk_AI\backend\.venv` if it was created by another version |
| "Dependency installation failed" / timeouts | Slow or blocked network: run INSTALL.cmd again (it resumes); add `-PipTimeout 600` for very slow links |
| Self-check failed | A package did not import; paste the printed error (no keys) when asking for help |
| "Port 8000 par koi purana server" | Another copy is running; close it, then start again |

## Optional single-folder exe

`AgentDesk_AI\backend\build_windows.ps1` builds `AgentDeskAI.exe` (PyInstaller, one-folder). The exe serves the API and the web UI, keeps its database and `.env` next to itself, and runs hardware operations through `AgentDeskAI.exe --system-worker`. It is **unsigned**, so Windows SmartScreen or antivirus may warn. It was smoke-tested but is not the primary supported install; see the Phase 12 report for what was and was not verified.

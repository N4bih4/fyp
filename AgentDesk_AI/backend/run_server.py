"""Entry point for the packaged Windows build (PyInstaller) and for source installs.

The dev server is started with: uvicorn app.main:app
The packaged exe runs this file instead, so the app works without a console-visible Python installation.
`AgentDeskAI.exe --system-worker` runs one isolated hardware operation (used internally by the app).
"""
import os
import sys
from pathlib import Path

import uvicorn


def main() -> None:
    # .env, SQLite and relative paths must not depend on where a shortcut was opened.
    # For the exe this is the folder next to AgentDeskAI.exe, never a temp extraction folder.
    from app.runtime import data_root

    os.chdir(data_root() if getattr(sys, "frozen", False) else Path(__file__).resolve().parent)
    if "--system-worker" in sys.argv:
        from app.tools.system_worker import main as worker_main

        worker_main()
        return
    from app.security.token import get_api_token

    get_api_token()  # create the per-user token file before serving
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, log_level="info")


if __name__ == "__main__":
    import multiprocessing

    multiprocessing.freeze_support()  # tool worker processes in the packaged exe
    main()

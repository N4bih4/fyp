"""Entry point for the packaged Windows build (PyInstaller).

The dev server is started with: uvicorn app.main:app
The packaged exe runs this file instead, so the app works without
a console-visible Python installation.
"""
import os
from pathlib import Path
import uvicorn


def main() -> None:
    # .env, SQLite and relative paths must not depend on where a shortcut was opened.
    os.chdir(Path(__file__).resolve().parent)
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, log_level="info")


if __name__ == "__main__":
    main()
